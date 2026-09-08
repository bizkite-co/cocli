"""Predictive prospect re-scoring engine & feedback loop recycler."""

from __future__ import annotations

import logging
from typing import Any, Optional

from cocli.application.icp_evaluator import IcpEvaluator
from cocli.application.to_call_disposition_service import (
    is_to_call_high_value,
    mark_to_call_high_value,
)
from cocli.core.config import load_campaign_config
from cocli.core.exclusions import ExclusionManager
from cocli.core.paths import paths
from cocli.models.campaigns.campaign import IcpSettings
from cocli.models.companies.company import Company

logger = logging.getLogger(__name__)


class IcpRescoringService:
    def __init__(self, campaign_name: str) -> None:
        self.campaign_name = campaign_name
        self.config_data = load_campaign_config(campaign_name)
        raw_icp = self.config_data.get("prospecting", {}).get("icp", {})
        self.icp_settings = IcpSettings.model_validate(raw_icp)
        self.evaluator = IcpEvaluator()
        self.exclusion_mgr = ExclusionManager(campaign_name)

    def calculate_feedback_multipliers(self) -> dict[str, float]:
        """Aggregate feedback signals by category/keyword to build dynamic multipliers."""
        multipliers: dict[str, float] = {}
        log_file = paths.campaign(self.campaign_name).path / "logs" / "engagement_events.usv"

        pos_counts: dict[str, int] = {}
        neg_counts: dict[str, int] = {}

        if log_file.exists():
            try:
                lines = log_file.read_text(encoding="utf-8").splitlines()
                for line in lines[1:]:  # skip header
                    if not line.strip():
                        continue
                    parts = line.split("\x1f")
                    if len(parts) >= 4:
                        slug = parts[2]
                        event_type = parts[3]
                        company = Company.get(slug) if slug else None
                        cats = (company.categories or []) if company else []
                        is_pos = event_type in (
                            "email_reply",
                            "cta_click",
                            "calculator_interactive_use",
                            "demo_video_start",
                            "Interested",
                        )
                        for cat in cats:
                            cat_lower = cat.lower()
                            if is_pos:
                                pos_counts[cat_lower] = pos_counts.get(cat_lower, 0) + 1
                            else:
                                neg_counts[cat_lower] = neg_counts.get(cat_lower, 0) + 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not parse engagement events log: %s", exc)

        # Include exclusion counts per category as negative feedback
        try:
            for ex in self.exclusion_mgr.list_exclusions():
                ex_slug = getattr(ex, "slug", None)
                if ex_slug:
                    company = Company.get(ex_slug)
                    if company:
                        for cat in company.categories or []:
                            c_lower = cat.lower()
                            neg_counts[c_lower] = neg_counts.get(c_lower, 0) + 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not list exclusions for rescoring: %s", exc)

        all_cats = set(pos_counts.keys()).union(set(neg_counts.keys()))
        for cat in all_cats:
            pos = pos_counts.get(cat, 0)
            neg = neg_counts.get(cat, 0)
            mult = 1.0 + (pos * 0.2) - (neg * 0.15)
            # Clamp multiplier between 0.5 and 2.0
            multipliers[cat] = max(0.5, min(2.0, round(mult, 2)))

        return multipliers

    def rescore_prospect(
        self,
        prospect_data: dict[str, Any],
        multipliers: Optional[dict[str, float]] = None,
    ) -> float:
        """Calculate dynamic ICP score adjusting base score by feedback multipliers."""
        base_score, _ = self.evaluator.evaluate(prospect_data, self.icp_settings)
        if multipliers is None:
            multipliers = self.calculate_feedback_multipliers()

        categories = prospect_data.get("categories") or []
        if isinstance(categories, str):
            categories = [c.strip() for c in categories.split(";") if c.strip()]

        mult = 1.0
        for cat in categories:
            c_lower = cat.lower()
            if c_lower in multipliers:
                mult *= multipliers[c_lower]

        mult = max(0.5, min(2.0, mult))
        final_score = base_score * mult
        return round(final_score, 2)

    def rescore_and_promote(self, high_value_threshold: float = 75.0) -> dict[str, Any]:
        """Rescore all campaign prospects and promote high-scoring targets to to-call-high-value queue."""
        multipliers = self.calculate_feedback_multipliers()
        evaluated_count = 0
        promoted_slugs: list[str] = []

        companies_dir = paths.companies.ensure()



        if not companies_dir.exists():
            return {
                "campaign": self.campaign_name,
                "evaluated": 0,
                "promoted_count": 0,
                "promoted_slugs": [],
                "multipliers": multipliers,
            }

        # Iterate over company directories
        for index_file in companies_dir.glob("*/_index.md"):
            try:
                company = Company.get(index_file.parent.name)

                if not company or not company.belongs_to_campaign(self.campaign_name):
                    continue

                if self.exclusion_mgr.is_excluded(
                    slug=company.slug, domain=company.domain
                ):
                    continue

                evaluated_count += 1
                co_dict = company.model_dump(mode="python")
                co_dict["reviews_count"] = company.reviews_count
                co_dict["average_rating"] = company.average_rating

                score = self.rescore_prospect(co_dict, multipliers)

                if (
                    score >= high_value_threshold
                    and not is_to_call_high_value(
                        campaign=self.campaign_name,
                        slug=company.slug,
                        domain=company.domain,
                    )
                ):
                    mark_to_call_high_value(
                        campaign=self.campaign_name,
                        slug=company.slug,
                        domain=company.domain,
                    )
                    promoted_slugs.append(company.slug)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error rescoring company %s: %s", index_file, exc)


        return {
            "campaign": self.campaign_name,
            "evaluated": evaluated_count,
            "promoted_count": len(promoted_slugs),
            "promoted_slugs": promoted_slugs,
            "multipliers": multipliers,
        }
