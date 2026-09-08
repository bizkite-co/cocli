"""
icp_evaluator.py — ICP Quality and Reachability Evaluation Service

Evaluates prospect records against campaign/initiative ICP settings:
  1. Reachability Checks (email, phone, domain)
  2. Quality Score Calculation (Google Maps rating * log10(reviews_count + 1), keyword relevance weights)
  3. Minimum Quality Threshold validation
"""

from __future__ import annotations

import math
import logging
from typing import Any
from cocli.models.campaigns.campaign import IcpSettings

logger = logging.getLogger(__name__)


class IcpEvaluator:
    """
    Evaluates prospect data dictionary or record against configured IcpSettings.
    Conforms to IcpEvaluatorProtocol.
    """

    def evaluate(self, prospect_data: dict[str, Any], icp_settings: IcpSettings) -> tuple[float, bool]:
        """
        Evaluates a prospect record.
        Returns (quality_score, is_eligible).
        """
        email = str(prospect_data.get("email") or "").strip()
        phone = str(
            prospect_data.get("phone")
            or prospect_data.get("phone_number")
            or prospect_data.get("phone_1")
            or ""
        ).strip()
        domain = str(prospect_data.get("domain") or "").strip()

        # 1. Reachability Checks
        if icp_settings.require_email and not email:
            return (0.0, False)
        if icp_settings.require_phone and not phone:
            return (0.0, False)
        if icp_settings.require_domain and not domain:
            return (0.0, False)

        # 2. Quality Score Calculation
        raw_rating = prospect_data.get("average_rating") or prospect_data.get("rating") or 0.0
        try:
            rating = float(raw_rating)
        except (ValueError, TypeError):
            rating = 0.0

        raw_reviews = prospect_data.get("reviews_count") or prospect_data.get("review_count") or 0
        try:
            reviews_count = int(raw_reviews)
        except (ValueError, TypeError):
            reviews_count = 0

        # Base rating * log10(reviews_count + 1)
        base_score = rating * math.log10(reviews_count + 1)

        # Apply weights from config
        weighted_rating = base_score * icp_settings.weights.google_maps_rating
        reviews_boost = math.log10(reviews_count + 1) * icp_settings.weights.reviews_count
        score = round(weighted_rating + reviews_boost, 2)

        # Search phrase relevance weight
        search_phrase = str(prospect_data.get("query") or prospect_data.get("search_phrase") or "").lower()
        if search_phrase:
            score = round(score * icp_settings.weights.search_phrase_relevance, 2)

        # 3. Minimum Quality Threshold validation
        is_eligible = score >= icp_settings.min_quality_score
        return (score, is_eligible)
