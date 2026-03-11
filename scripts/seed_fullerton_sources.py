from cocli.models.campaigns.queues.events import EventScrapeTask
from cocli.core.ordinant import QueueIdentity
from cocli.core.paths import paths
from cocli.core.config import set_campaign

def seed_sources() -> None:
    set_campaign("fullertonian")
    
    # 1. Ensure queue directories exist
    q_paths = paths.campaign("fullertonian").queue(QueueIdentity.EVENTS)
    q_paths.pending.mkdir(parents=True, exist_ok=True)
    q_paths.completed.mkdir(parents=True, exist_ok=True)

    sources = [
        EventScrapeTask(
            url="https://www.eventbrite.com/d/ca--fullerton/events/",
            host_name="EventBrite Fullerton",
            host_slug="eventbrite-fullerton",
            scraper_type="eventbrite",
            ack_token=None
        ),
        EventScrapeTask(
            url="https://fullertonobserver.com/events/",
            host_name="Fullerton Observer",
            host_slug="fullerton-observer",
            scraper_type="fullerton-observer",
            ack_token=None
        ),
        EventScrapeTask(
            url="https://fullertonlibrary.org/calendar",
            host_name="Fullerton Public Library",
            host_slug="fullerton-public-library",
            scraper_type="fullerton-library",
            ack_token=None
        ),
        EventScrapeTask(
            url="https://www.cityoffullerton.com/government/departments/parks-recreation/community-calendar",
            host_name="City of Fullerton Parks & Rec",
            host_slug="fullerton-parks-rec",
            scraper_type="generic-calendar",
            ack_token=None
        ),
        EventScrapeTask(
            search_phrase="Current local events and restaurant openings in Fullerton CA March 2026",
            host_name="Google Search: Fullerton March 2026",
            host_slug="google-fullerton-mar-2026",
            scraper_type="web-search",
            ack_token=None
        ),
        EventScrapeTask(
            search_phrase="Free family events in Fullerton CA this week",
            host_name="Bing Search: Free Fullerton Family",
            host_slug="bing-fullerton-free-family",
            scraper_type="web-search",
            ack_token=None
        )
    ]

    for task in sources:
        task_file = task.save()
        print(f"Seeded Task: {task.host_name} -> {task_file}")

if __name__ == "__main__":
    seed_sources()
