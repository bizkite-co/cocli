from __future__ import annotations
import json
import logging
from typing import Optional

from ..models.campaigns.indexes.email import EmailEntry
from ..station_defs.path_helpers import email_inbox_rel, email_shard_id
from .config import get_campaign_dir

logger = logging.getLogger(__name__)


def filter_safe_usv_paths(paths: list[str]) -> list[str]:
    """Drop paths with control chars before they hit a DuckDB glob/SQL string.

    add_email() rejects these at write time now, but pre-existing on-disk
    junk (or a future bug in some other writer) can still produce one - and
    a single such path breaks read_csv's own glob matching for every file in
    the list, not just itself (confirmed production incident, 2026-09-13:
    one file named "is:\nsales@zfloor.com.usv" made
    `cocli data export-enriched-emails` fail for the whole campaign).
    """
    safe = []
    for p in paths:
        if any(ord(c) < 0x20 for c in p):
            logger.warning("Skipping email index file with unsafe characters in path: %r", p)
            continue
        safe.append(p)
    return safe


class EmailIndexManager:
    """
    Manages a campaign-specific index of emails using a sharded USV structure.
    Architecture:
    - inbox/shard/email.usv (Hot layer, atomic writes)
    - shards/shard.usv (Cold layer, compacted)
    - CURRENT + checkpoint.* (stations Compactor commit pointer; Phase 3)
    """
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        campaign_dir = get_campaign_dir(campaign_name)
        if not campaign_dir:
            from .config import get_campaigns_dir
            campaign_dir = get_campaigns_dir() / campaign_name
            
        self.index_root = campaign_dir / "indexes" / "emails"
        self.inbox_dir = self.index_root / "inbox"
        self.shards_dir = self.index_root / "shards"
        
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.shards_dir.mkdir(parents=True, exist_ok=True)

    def get_shard_id(self, domain: str) -> str:
        """Domain-hash shard from EMAIL_INBOX's declared combinator."""
        return email_shard_id(domain)

    def add_email(self, email_entry: EmailEntry) -> bool:
        """
        Adds an email entry to the sharded inbox.
        Uses the email address as the filename for atomic isolation in the hot layer.
        """
        email_filename = str(email_entry.email).lower().strip()

        # EmailEntry.email is deliberately lenient (accepts raw strings that
        # fail EmailAddress validation, to avoid silently dropping scraped
        # junk - see email.py's validate_email_lenient). That means a
        # mis-extracted value can carry embedded control characters (seen in
        # production: "is:\nsales@zfloor.com", from label text bleeding into
        # the email during scraping) straight through to a filesystem path.
        # One such file breaks every DuckDB glob read over this directory for
        # the whole campaign (`cocli data export-enriched-emails`, `query()`),
        # not just this one entry - so reject at the write boundary rather
        # than validating email *format* (is_valid_email is about filtering
        # resource-file false positives, not filename safety).
        if any(ord(c) < 0x20 for c in email_filename):
            logger.warning(
                "Refusing to index email with control characters (unsafe as a "
                "filename) for domain=%s: %r",
                email_entry.domain,
                email_filename,
            )
            try:
                from ..models.campaigns.queues.scraped_email_invalid import (
                    enqueue_scraped_email_invalid,
                )

                enqueue_scraped_email_invalid(
                    campaign_name=self.campaign_name,
                    company_slug=email_entry.company_slug or "unknown",
                    domain=email_entry.domain or "unknown",
                    email=email_filename,
                    reason="unsafe-filename-chars",
                    extracted_from=email_entry.source,
                )
            except Exception:
                logger.debug("Failed to enqueue unsafe email for review", exc_info=True)
            return False

        path = self.index_root / email_inbox_rel(
            f"{email_filename}.usv", domain=email_entry.domain
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Simple append/overwrite for the hot layer
            with open(path, 'w', encoding='utf-8') as f:
                f.write(email_entry.to_usv())
            return True
        except Exception as e:
            logger.error(f"Error writing email to inbox {path}: {e}")
            return False

    def query(self, sql_where: Optional[str] = None) -> list[EmailEntry]:
        """
        Queries the email index using DuckDB.
        Merges inbox and shards, taking the latest 'last_seen' for each email.
        """
        import duckdb
        con = duckdb.connect(database=':memory:')
        
        # Define Schema matching EmailEntry.to_usv()
        columns = {
            "email": "VARCHAR",
            "domain": "VARCHAR",
            "company_slug": "VARCHAR",
            "source": "VARCHAR",
            "found_at": "VARCHAR",
            "first_seen": "VARCHAR",
            "last_seen": "VARCHAR",
            "verification_status": "VARCHAR",
            "tags": "VARCHAR"
        }

        sub_queries = []
        
        # 1. Collect Shards
        shard_paths = filter_safe_usv_paths([str(p) for p in self.shards_dir.glob("*.usv")])
        if shard_paths:
            path_list = "', '".join(shard_paths)
            sub_queries.append(f"SELECT * FROM read_csv(['{path_list}'], delim='\x1f', header=False, columns={json.dumps(columns)}, auto_detect=False, ignore_errors=True, quote='')")

        # 2. Collect Inbox
        inbox_paths = filter_safe_usv_paths([str(p) for p in self.inbox_dir.rglob("*.usv")])
        if inbox_paths:
            path_list = "', '".join(inbox_paths)
            sub_queries.append(f"SELECT * FROM read_csv(['{path_list}'], delim='\x1f', header=False, columns={json.dumps(columns)}, auto_detect=False, ignore_errors=True, quote='')")

        if not sub_queries:
            return []

        try:
            base_query = " UNION ALL ".join(sub_queries)
            full_query = f"""
                SELECT * FROM (
                    SELECT *, row_number() OVER (PARTITION BY email ORDER BY last_seen DESC) as rn
                    FROM ({base_query})
                ) WHERE rn = 1
            """
            if sql_where:
                full_query = f"SELECT * FROM ({full_query}) WHERE {sql_where}"
            
            results = con.execute(full_query).fetchall()
            emails = []
            for row in results:
                # row[-1] is the row_number 'rn', we skip it
                data = dict(zip(columns.keys(), row[:-1]))
                # Convert tags back to list
                if data['tags']:
                    data['tags'] = data['tags'].split(';')
                else:
                    data['tags'] = []
                emails.append(EmailEntry.model_validate(data))
            return emails
        except Exception as e:
            logger.error(f"Email index query failed: {e}")
            return []

    def compact(self) -> None:
        """Single-authority email compact: stations fold, then shard materialization.

        1. ``DefaultCompactor`` folds inbox + existing shards → CURRENT/checkpoint
           (LWW by email/last_seen). Consuming mode retires inbox files.
        2. DuckDB-facing ``shards/*.usv`` are rewritten **from CURRENT only** —
           not a second independent query/LWW over inbox+shards.

        Readers keep using ``query()`` (shards + hot inbox between compacts).
        """
        logger.info("Starting email index compaction for %s...", self.campaign_name)

        from cocli.core.stations_runtime import (
            compact_email_index_stations_only,
            materialize_email_shards_from_current,
        )

        try:
            stations_ok = compact_email_index_stations_only(
                self, compactor_id=f"email-{self.campaign_name}"
            )
            logger.info(
                "stations Compactor email cycle committed=%s campaign=%s",
                stations_ok,
                self.campaign_name,
            )
        except Exception as exc:
            logger.error(
                "stations email compact failed (%s); not running dual legacy LWW",
                exc,
            )
            raise

        n = materialize_email_shards_from_current(self)
        logger.info(
            "email shards materialized from CURRENT count=%s campaign=%s",
            n,
            self.campaign_name,
        )

        # Inbox should already be empty (consuming); ensure clean hot layer
        import shutil

        if self.inbox_dir.exists():
            shutil.rmtree(self.inbox_dir)
            self.inbox_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Email compaction complete (stations authority + shard projection).")
