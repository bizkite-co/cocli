from cocli.models.campaigns.events import Event
from datetime import datetime
from pathlib import Path
import shutil

def test_event_dir_saving() -> None:
    test_wal = Path("temp/test_events_wal")
    if test_wal.exists():
        shutil.rmtree(test_wal)
    test_wal.mkdir(parents=True)

    event = Event(
        start_time=datetime(2026, 3, 15, 18, 0, 0),
        host_slug="fullerton-library",
        event_slug="coding-night",
        name="Coding Night at the Library",
        host_name="Fullerton Public Library",
        description="Join us for a night of coding and community.",
        category="Educational"
    )

    event_dir = event.save_to_wal(test_wal)
    print(f"Event saved to: {event_dir}")

    assert event_dir.exists()
    assert (event_dir / "README.md").exists()
    
    content = (event_dir / "README.md").read_text()
    print(f"README Content:\n{content}")
    
    assert "Coding Night at the Library" in content
    assert "Join us for a night of coding and community." in content
    assert "---" in content

    print("Event directory saving test passed!")

if __name__ == "__main__":
    test_event_dir_saving()
