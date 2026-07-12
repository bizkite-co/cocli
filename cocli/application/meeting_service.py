import datetime
import logging
import re
from typing import List, Any
import yaml
from pytz import timezone
from tzlocal import get_localzone

from cocli.core.config import get_companies_dir
from cocli.models.companies.meeting import CompanyMeeting

logger = logging.getLogger(__name__)


class MeetingService:

    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name

    def get_all_meetings(self) -> List[CompanyMeeting]:
        """Gathers all meeting data from all companies."""
        all_meetings: List[CompanyMeeting] = []
        companies_dir = get_companies_dir()

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
