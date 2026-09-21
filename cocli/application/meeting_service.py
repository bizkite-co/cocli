import datetime
import logging
import re
from pathlib import Path
from typing import Any
import yaml
from pytz import timezone
from tzlocal import get_localzone

from cocli.core.paths import paths
from cocli.models.companies.meeting import CompanyCall, CompanyMeeting, Meeting

logger = logging.getLogger(__name__)


class MeetingService:

    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name

    def get_all_meetings(self) -> list[CompanyMeeting]:
        """Gathers all meeting data from all companies."""
        all_meetings: list[CompanyMeeting] = []
        companies_dir = paths.companies.ensure()

        local_tz: Any
        try:
            local_tz = get_localzone()
        except Exception:
            local_tz = timezone("UTC")

        if not companies_dir.exists():
            return all_meetings

        for company_dir in companies_dir.iterdir():
            if company_dir.is_dir():
                company_name = company_dir.name.replace("-", " ").title()
                meetings_dir = company_dir / "meetings"

                if meetings_dir.exists():
                    for meeting_file in meetings_dir.iterdir():
                        if meeting_file.is_file() and meeting_file.suffix == ".md":
                            try:
                                # Parse filename: YYYY-MM-DDTHHMMZ-slugified-title.md
                                match = re.match(
                                    r"^(\d{4}-\d{2}-\d{2}(?:T\d{4}Z)?)-",
                                    meeting_file.name,
                                )
                                if match:
                                    datetime_str_raw = match.group(1)
                                else:
                                    logger.warning(
                                        f"Could not extract datetime from filename {meeting_file.name}. Skipping."
                                    )
                                    continue

                                # Handle both YYYY-MM-DDTHHMMZ and YYYY-MM-DD formats
                                if (
                                    "T" in datetime_str_raw
                                    and datetime_str_raw.endswith("Z")
                                ):
                                    datetime_utc = datetime.datetime.strptime(
                                        datetime_str_raw, "%Y-%m-%dT%H%MZ"
                                    ).replace(tzinfo=timezone("UTC"))
                                else:
                                    datetime_utc = datetime.datetime.strptime(
                                        datetime_str_raw, "%Y-%m-%d"
                                    ).replace(tzinfo=timezone("UTC"))

                                datetime_local = datetime_utc.astimezone(local_tz)

                                # Extract title from filename
                                title_start_index = len(datetime_str_raw) + 1
                                meeting_title_raw = meeting_file.name[
                                    title_start_index:
                                ].replace(".md", "")
                                meeting_title = (
                                    meeting_title_raw.replace("-", " ").strip()
                                )
                                if not meeting_title:
                                    meeting_title = "Untitled Meeting"

                                # Read frontmatter for more accurate title if available
                                content = meeting_file.read_text()
                                if content.startswith("---") and "---" in content[3:]:
                                    frontmatter_str, _ = content.split("---", 2)[1:]
                                    try:
                                        frontmatter_data = (
                                            yaml.safe_load(frontmatter_str) or {}
                                        )
                                        if "title" in frontmatter_data:
                                            meeting_title = frontmatter_data[
                                                "title"
                                            ]
                                    except yaml.YAMLError:
                                        pass

                                all_meetings.append(
                                    CompanyMeeting(
                                        datetime_utc=datetime_utc,
                                        datetime_local=datetime_local,
                                        company_name=company_name,
                                        title=meeting_title,
                                        file_path=meeting_file,
                                    )
                                )
                            except (ValueError, IndexError, FileNotFoundError) as e:
                                logger.warning(
                                    f"Could not parse meeting file {meeting_file.name}: {e}"
                                )
                                continue
        return all_meetings

    def get_upcoming_meetings(self) -> list[CompanyMeeting]:
        """Gathers and returns sorted list of upcoming meetings."""
        all_meetings = self.get_all_meetings()
        local_tz = get_localzone()
        now_local = datetime.datetime.now(local_tz)
        return sorted(
            [m for m in all_meetings if m.datetime_local > now_local],
            key=lambda m: m.datetime_local,
        )

    def get_recent_meetings(self, days_limit: int = 180) -> list[CompanyMeeting]:
        """Gathers and returns sorted list of recent meetings within a day limit."""
        all_meetings = self.get_all_meetings()
        local_tz = get_localzone()
        now_local = datetime.datetime.now(local_tz)
        limit_date_local = now_local - datetime.timedelta(days=days_limit)
        return sorted(
            [
                m
                for m in all_meetings
                if m.datetime_local < now_local
                and m.datetime_local >= limit_date_local
            ],
            key=lambda m: m.datetime_local,
            reverse=True,
        )

    def _cache_path(self) -> Path:
        campaign = self.campaign_name or "default"
        return paths.campaign(campaign).path / "indexes" / "recent_calls" / "cache.json"

    def _write_cache(self, calls: list[CompanyCall]) -> None:
        import json

        try:
            cache_path = self._cache_path()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "calls": [c.model_dump(mode="json") for c in calls],
            }
            cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to write recent calls cache: {e}")

    def record_call_in_cache(self, call: CompanyCall) -> None:
        """Write-through: prepends a newly logged call into cache.json without scanning."""
        try:
            calls = self.get_recent_calls(use_cache=True)
            calls = [c for c in calls if str(c.file_path) != str(call.file_path)]
            calls.insert(0, call)
            calls.sort(key=lambda c: c.datetime_utc, reverse=True)
            self._write_cache(calls)
        except Exception as e:
            logger.warning(f"Failed to record call in cache: {e}")

    def rebuild_recent_calls_cache(self, days_limit: int = 30) -> list[CompanyCall]:
        """Scans disk, rebuilds recent calls cache, saves to disk, and returns calls."""
        calls = self._scan_recent_calls(days_limit=days_limit)
        self._write_cache(calls)
        return calls

    def _scan_recent_calls(self, days_limit: int = 30) -> list[CompanyCall]:
        calls: list[CompanyCall] = []
        for meeting_summary in self.get_recent_meetings(days_limit=days_limit):
            meeting = Meeting.from_file(meeting_summary.file_path)
            if meeting is None or meeting.type != "phone-call":
                continue
            calls.append(
                CompanyCall(
                    datetime_utc=meeting_summary.datetime_utc,
                    datetime_local=meeting_summary.datetime_local,
                    company_name=meeting_summary.company_name,
                    company_slug=meeting_summary.file_path.parent.parent.name,
                    title=meeting.title,
                    content=meeting.content,
                    file_path=meeting_summary.file_path,
                )
            )
        return calls

    def get_recent_calls(self, days_limit: int = 30, use_cache: bool = True) -> list[CompanyCall]:
        """Return recent phone-call meetings with their recorded notes.
        Uses cache.json for instant responses when use_cache=True.
        """
        import json

        cache_path = self._cache_path()
        if use_cache and cache_path.exists():
            try:
                content = json.loads(cache_path.read_text(encoding="utf-8"))
                raw_calls = content.get("calls", [])
                return [CompanyCall.model_validate(c) for c in raw_calls]
            except Exception as e:
                logger.warning(f"Failed to read recent calls cache, falling back to disk scan: {e}")

        return self.rebuild_recent_calls_cache(days_limit=days_limit)

