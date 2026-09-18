"""e2e tests need live 1Password (Cognito test users, etc.)."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    marker = pytest.mark.live_1password
    for item in items:
        item.add_marker(marker)
