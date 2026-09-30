import pytest

from cocli.tui.app import CocliApp
from cocli.tui.widgets.content_viewer_modal import ContentViewerModal


@pytest.mark.asyncio
async def test_content_viewer_modal_mounts_with_long_content_and_closes_on_escape():
    """Regression test: a long transcript with no scroll region pushed the
    'Press ESC to close' footer off-screen, making the modal look unclosable
    even though the escape binding worked all along."""
    long_content = "\n".join(f"[{i:02d}:00] line {i}" for i in range(500))

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        await app.push_screen(ContentViewerModal(title="Transcript", content=long_content))
        await pilot.pause()

        assert isinstance(app.screen, ContentViewerModal)

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, ContentViewerModal)
