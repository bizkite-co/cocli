import json
import logging
import hashlib
from typing import List, Optional, Dict

from ..models.email import EmailEntry
from .config import get_campaign_dir

logger = logging.getLogger(__name__)

class EmailIndexManager:
    """
    Manages a campaign-specific index of emails using a sharded USV structure.
    Architecture:
    - inbox/shard/email.usv (Hot layer, atomic writes)
    - shards/shard.usv (Cold layer, compacted)
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
        """Deterministic shard (00-ff) based on domain hash."""
        return hashlib.sha256(domain.encode()).hexdigest()[:2]

    def add_email(self, email_entry: EmailEntry) -> bool:
        """
        Adds an email entry to the sharded inbox.
        Uses the email address as the filename for atomic isolation in the hot layer.
        """
        shard_id = self.get_shard_id(email_entry.domain)
        shard_inbox = self.inbox_dir / shard_id
        shard_inbox.mkdir(parents=True, exist_ok=True)
        
        # Use raw email (lowercased) to avoid collisions with characters like '+' or '.'
        email_filename = str(email_entry.email).lower().strip()
        path = shard_inbox / f"{email_filename}.usv"
        
        try:
            # Simple append/overwrite for the hot layer
            with open(path, 'w', encoding='utf-8') as f:
                f.write(email_entry.to_usv())
            return True
        except Exception as e:
            logger.error(f"Error writing email to inbox {path}: {e}")
            return False

    def query(self, sql_where: Optional[str] = None) -> List[EmailEntry]:
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
        shard_paths = [str(p) for p in self.shards_dir.glob("*.usv")]
        if shard_paths:
            path_list = "', '".join(shard_paths)
            sub_queries.append(f"SELECT * FROM read_csv(['{path_list}'], delim='\x1f', header=False, columns={json.dumps(columns)}, auto_detect=False, ignore_errors=True)")

        # 2. Collect Inbox
        inbox_paths = [str(p) for p in self.inbox_dir.rglob("*.usv")]
        if inbox_paths:
            path_list = "', '".join(inbox_paths)
            sub_queries.append(f"SELECT * FROM read_csv(['{path_list}'], delim='\x1f', header=False, columns={json.dumps(columns)}, auto_detect=False, ignore_errors=True)")

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
        """
        Merges all inbox files into the deterministic shards.
        """
        logger.info(f"Starting email index compaction for {self.campaign_name}...")
        
        # 1. Load everything currently in the index (Inbox + Shards)
        all_entries = self.query()
        if not all_entries:
            return

        # 2. Group by shard ID
        shard_groups: Dict[str, List[EmailEntry]] = {}
        for entry in all_entries:
            shard_id = self.get_shard_id(entry.domain)
            if shard_id not in shard_groups:
                shard_groups[shard_id] = []
            shard_groups[shard_id].append(entry)

        # 3. Write new shards
        for shard_id, entries in shard_groups.items():
            shard_path = self.shards_dir / f"{shard_id}.usv"
            with open(shard_path, 'w', encoding='utf-8') as f:
                for entry in entries:
                    f.write(entry.to_usv())
            logger.info(f"Wrote shard {shard_id} ({shard_path}) with {len(entries)} emails.")

        # 4. Cleanup Inbox
        import shutil
        if self.inbox_dir.exists():
            shutil.rmtree(self.inbox_dir)
            self.inbox_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Email compaction complete.")