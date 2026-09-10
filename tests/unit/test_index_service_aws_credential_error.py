"""Unit tests verifying that AWS credential errors during index compaction are caught gracefully."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from botocore.exceptions import CredentialRetrievalError
from cocli.application.index_service import IndexService


def test_compact_handles_aws_credential_error(tmp_path: Path) -> None:
    service = IndexService(campaign_name="test-campaign")

    with patch.object(
        IndexService,
        "list_interrupted_runs",
        side_effect=CredentialRetrievalError(
            provider="custom-process", error_msg="Failed to retrieve credentials from 1Password."
        ),
    ):
        result = service.compact(index_name="google_maps_prospects")

    assert result.success is False
    assert "AWS Credential Error" in result.message
    assert "1Password" in result.message
