from __future__ import annotations

from typing import Any

from cocli.application.engagement_service import EngagementService
from cocli.application.icp_rescoring_service import IcpRescoringService
from cocli.models.campaigns.queues.to_call_high_value import ToCallHighValueTask
from cocli.models.companies.company import Company
from cocli.models.engagement import EngagementEvent


def test_calculate_feedback_multipliers(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    company = Company(
        name="Tech Solutions",
        slug="tech-solutions",
        domain="techsolutions.com",
        categories=["Financial Planner", "Wealth Management"],
    )
    company.save()

    eng_service = EngagementService("roadmap")
    eng_service.record_event(
        EngagementEvent(
            campaign_name="roadmap",
            company_slug="tech-solutions",
            event_type="email_reply",
            source="imap",
        )
    )

    rescoring_service = IcpRescoringService("roadmap")
    multipliers = rescoring_service.calculate_feedback_multipliers()

    assert "financial planner" in multipliers
    assert multipliers["financial planner"] > 1.0


def test_rescore_prospect_applies_multipliers(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    prospect_data = {
        "name": "High Potential Co",
        "slug": "high-potential-co",
        "domain": "highpotential.com",
        "email": "contact@highpotential.com",
        "phone_number": "555-444-3333",
        "reviews_count": 50,
        "average_rating": 4.8,
        "categories": ["Financial Planner"],
    }

    rescoring_service = IcpRescoringService("roadmap")
    base_score = rescoring_service.rescore_prospect(prospect_data, multipliers={})
    boosted_score = rescoring_service.rescore_prospect(
        prospect_data, multipliers={"financial planner": 1.5}
    )

    assert boosted_score > base_score


def test_rescore_and_promote_enqueues_high_value_queue(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    company = Company(
        name="Top Prospect",
        slug="top-prospect",
        domain="topprospect.com",
        email="info@topprospect.com",
        phone_number="555-777-8888",
        reviews_count=100,
        average_rating=4.9,
        campaigns=["roadmap"],
        tags=["roadmap"],
    )

    company.save()

    rescoring_service = IcpRescoringService("roadmap")
    result = rescoring_service.rescore_and_promote(high_value_threshold=10.0)

    assert result["promoted_count"] >= 1

    assert "top-prospect" in result["promoted_slugs"]

    # Verify high value task USV file exists
    task = ToCallHighValueTask(
        company_slug="top-prospect", domain="topprospect.com", campaign_name="roadmap"
    )
    assert task.get_local_path().exists()
