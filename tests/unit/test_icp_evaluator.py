from __future__ import annotations

from cocli.application.icp_evaluator import IcpEvaluator
from cocli.application.protocols import IcpEvaluatorProtocol
from cocli.models.campaigns.campaign import IcpSettings, IcpQualityWeights


def test_icp_evaluator_protocol_compliance() -> None:
    evaluator = IcpEvaluator()
    assert isinstance(evaluator, IcpEvaluatorProtocol)


def test_icp_reachability_filtering() -> None:
    evaluator = IcpEvaluator()
    settings = IcpSettings(require_email=True, require_phone=True)

    # Missing email
    prospect_no_email = {"phone": "555-1234", "average_rating": 4.8, "reviews_count": 50}
    score, eligible = evaluator.evaluate(prospect_no_email, settings)
    assert score == 0.0
    assert eligible is False

    # Missing phone
    prospect_no_phone = {"email": "test@example.com", "average_rating": 4.8, "reviews_count": 50}
    score, eligible = evaluator.evaluate(prospect_no_phone, settings)
    assert score == 0.0
    assert eligible is False

    # Has email and phone
    prospect_complete = {
        "email": "test@example.com",
        "phone": "555-1234",
        "average_rating": 4.8,
        "reviews_count": 50,
    }
    score, eligible = evaluator.evaluate(prospect_complete, settings)
    assert score > 0.0
    assert eligible is True


def test_icp_quality_threshold_filtering() -> None:
    evaluator = IcpEvaluator()
    settings = IcpSettings(
        min_quality_score=10.0,
        weights=IcpQualityWeights(google_maps_rating=1.0, reviews_count=0.5),
    )

    # Low rating / low reviews (Score below 10.0)
    low_prospect = {"average_rating": 3.0, "reviews_count": 2}
    score_low, eligible_low = evaluator.evaluate(low_prospect, settings)
    assert eligible_low is False

    # High rating / high reviews (Score above 10.0)
    high_prospect = {"average_rating": 4.9, "reviews_count": 100}
    score_high, eligible_high = evaluator.evaluate(high_prospect, settings)
    assert eligible_high is True
    assert score_high >= 10.0
