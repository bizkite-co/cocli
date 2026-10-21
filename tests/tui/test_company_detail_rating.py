# POLICY: frictionless-data-policy-enforcement
import pytest
from textual.widgets import DataTable
from cocli.tui.app import CocliApp
from cocli.models.companies.company import Company
from cocli.core.paths import paths

@pytest.mark.asyncio
async def test_company_detail_rating_display(mock_cocli_env, mocker):
    """Verify that ratings are correctly displayed in the company detail view."""
    
    # 1. Create a mock company with ratings
    slug = "rated-company"
    company = Company(
        name="Rated Company",
        slug=slug,
        average_rating=4.8,
        reviews_count=120,
        phone_number="1234567890",
        email="test@example.com"
    )
    
    # Mock Company.get to return our company
    mocker.patch("cocli.models.companies.company.Company.get", return_value=company)
    # Mock services.get_company_details to return our data
    company_data = {
        "company": company.model_dump(),
        "notes": [],
        "meetings": [],
        "contacts": [],
        "website_data": {},
        "enrichment_path": str(paths.companies.entry(slug) / "enrichment.md")
    }
    mocker.patch("cocli.application.services.ServiceContainer.get_company_details", return_value=company_data)

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        # Manually trigger company selection
        from cocli.tui.widgets.company_list import CompanyList
        app.on_company_list_company_selected(CompanyList.CompanySelected(slug))
        await pilot.pause()
        
        # Verify info table contains the rating
        table = app.query_one("#info-table", DataTable)
        
        # Extract rows to check content
        rows = []
        for i in range(table.row_count):
            rows.append(table.get_row_at(i))
            
        # Rating should be present
        rating_row = next((r for r in rows if r[0] == "Rating"), None)
        assert rating_row is not None, "Rating row not found in Info Table"
        assert "4.8" in str(rating_row[1])
        assert "120 reviews" in str(rating_row[1])
        assert "/5.0" not in str(rating_row[1])


@pytest.mark.asyncio
async def test_company_detail_shows_roadmap_usage(mock_cocli_env, mocker):
    slug = "roadmap-user"
    company = Company(
        name="Roadmap User",
        slug=slug,
        phone_number="12142158004",
        tags=["testimonial-target", "rta-rank-2"],
        rta_metrics={
            "rank": 2,
            "login_count": 308,
            "active_minutes": 900,
            "active_days": 80,
            "event_count": 12078,
            "last_activity": "2026-10-19 20:29:47",
        },
    )
    mocker.patch("cocli.models.companies.company.Company.get", return_value=company)
    company_data = {
        "company": company.model_dump(),
        "notes": [],
        "meetings": [],
        "contacts": [],
        "tags": company.tags,
        "website_data": {},
        "enrichment_path": str(paths.companies.entry(slug) / "enrichment.md"),
    }
    mocker.patch(
        "cocli.application.services.ServiceContainer.get_company_details",
        return_value=company_data,
    )

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        from cocli.tui.widgets.company_list import CompanyList

        app.on_company_list_company_selected(CompanyList.CompanySelected(slug))
        await pilot.pause()
        table = app.query_one("#info-table", DataTable)
        rows = [table.get_row_at(i) for i in range(table.row_count)]
        usage = next(row for row in rows if row[0] == "Usage")
        rendered = str(usage[1])
        assert "Rank #2" in rendered
        assert "308 logins" in rendered
        assert "2026-10-19" in rendered


@pytest.mark.asyncio
async def test_company_detail_shows_maps_and_website_phones(mock_cocli_env, mocker):
    slug = "two-phones"
    company = Company(
        name="Two Phones",
        slug=slug,
        phone_number="18007282374",
        phone_1="19093995460",
        phone_from_website="18173362377",
    )
    mocker.patch("cocli.models.companies.company.Company.get", return_value=company)
    company_data = {
        "company": company.model_dump(),
        "notes": [],
        "meetings": [],
        "contacts": [],
        "tags": [],
        "website_data": {},
        "enrichment_path": str(paths.companies.entry(slug) / "enrichment.md"),
    }
    mocker.patch(
        "cocli.application.services.ServiceContainer.get_company_details",
        return_value=company_data,
    )

    app = CocliApp(auto_show=False)
    async with app.run_test() as pilot:
        from cocli.tui.widgets.company_list import CompanyList

        app.on_company_list_company_selected(CompanyList.CompanySelected(slug))
        await pilot.pause()
        table = app.query_one("#info-table", DataTable)
        rows = {row[0]: str(row[1]) for row in (table.get_row_at(i) for i in range(table.row_count))}
        assert "800" in rows["Phone"]
        assert "909" in rows["Phone (Maps)"]
        assert "817" in rows["Phone (Site)"]


if __name__ == "__main__":
    import subprocess
    subprocess.run(["pytest", "-s", __file__])
