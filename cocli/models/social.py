"""Social URL fields shared by Company and Person."""

from __future__ import annotations

from typing import Optional, Protocol

# (model field, editor label). Order is the order both editors and the
# person profile show them.
SOCIAL_URL_FIELDS: tuple[tuple[str, str], ...] = (
    ("facebook_url", "Facebook"),
    ("linkedin_url", "LinkedIn"),
    ("instagram_url", "Instagram"),
    ("twitter_url", "Twitter"),
    ("youtube_url", "YouTube"),
)


class SocialLinks(Protocol):
    """The social URL set stored on both a company and a person."""

    facebook_url: Optional[str]
    linkedin_url: Optional[str]
    instagram_url: Optional[str]
    twitter_url: Optional[str]
    youtube_url: Optional[str]
