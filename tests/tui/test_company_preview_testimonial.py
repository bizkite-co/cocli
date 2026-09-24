from __future__ import annotations

import pytest
from cocli.models.companies.company import Company
from cocli.tui.app import CocliApp
from cocli.tui.widgets.company_preview import CompanyPreview


@pytest.mark.asyncio
async def test_preview_renders_testimonial_banner_and_metrics() -> None:
    company = Company(
        name="Higginbotham - Jan Mohamed",
        slug="higginbotham-jan-mohamed",
        domain="higginbotham.net",
        tags=["testimonial-target", "rta-user", "rta-rank-1"],
        rta_metrics={
            "rank": 1,
            "login_count": 33,
            "active_minutes": 515,
            "event_count": 1820,
            "active_days": 21,
        },
    )

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        preview = CompanyPreview()
        await app.query_one("#app_content").mount(preview)
        await pilot.pause()

        await preview.update_preview(company)
        await pilot.pause()

        # Check for banner
        banners = list(preview.query(".testimonial-target-banner"))
        assert len(banners) == 1
        assert "TESTIMONIAL TARGET" in str(banners[0].render())
        assert "Active RTA User" in str(banners[0].render())

        # Check for stats
        stats = list(preview.query(".testimonial-target-stats"))
        assert len(stats) == 1
        rendered_stats = str(stats[0].render())
        assert "Rank" in rendered_stats
        assert "#1" in rendered_stats
        assert "33" in rendered_stats
        assert "515" in rendered_stats


@pytest.mark.asyncio
async def test_preview_skips_testimonial_widgets_for_regular_company() -> None:
    regular_company = Company(
        name="Acme Corp",
        slug="acme-corp",
        domain="acme.com",
        tags=["lead"],
    )

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        preview = CompanyPreview()
        await app.query_one("#app_content").mount(preview)
        await pilot.pause()

        await preview.update_preview(regular_company)
        await pilot.pause()

        banners = list(preview.query(".testimonial-target-banner"))
        assert len(banners) == 0

        stats = list(preview.query(".testimonial-target-stats"))
        assert len(stats) == 0


@pytest.mark.asyncio
async def test_preview_renders_rank_from_tag_fallback() -> None:
    tag_only_company = Company(
        name="Higginbotham - Cooper Gerami",
        slug="higginbotham-cooper-gerami",
        domain="higginbotham.com",
        tags=["testimonial-target", "rta-rank-5"],
    )

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        preview = CompanyPreview()
        await app.query_one("#app_content").mount(preview)
        await pilot.pause()

        await preview.update_preview(tag_only_company)
        await pilot.pause()

        banners = list(preview.query(".testimonial-target-banner"))
        assert len(banners) == 1

        stats = list(preview.query(".testimonial-target-stats"))
        assert len(stats) == 1
        assert "#5" in str(stats[0].render())
