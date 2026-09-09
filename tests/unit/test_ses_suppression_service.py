from __future__ import annotations

from unittest.mock import MagicMock, patch

from cocli.application.protocols import SesSuppressionProtocol
from cocli.application.ses_suppression_service import SesSuppressionService


def test_ses_suppression_service_protocol_and_methods() -> None:
    mock_boto_client = MagicMock()
    mock_boto_client.put_suppressed_destination.return_value = {}
    mock_boto_client.get_suppressed_destination.return_value = {
        "SuppressedDestination": {"EmailAddress": "test@example.com", "Reason": "COMPLAINT"}
    }
    mock_boto_client.list_suppressed_destinations.return_value = {
        "SuppressedDestinationSummaries": [
            {"EmailAddress": "test@example.com", "Reason": "COMPLAINT", "LastUpdateTime": 12345}
        ]
    }

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_boto_client

        service = SesSuppressionService(region="us-east-1", profile="test")
        assert isinstance(service, SesSuppressionProtocol)

        # Test suppress_email
        assert service.suppress_email("test@example.com", "COMPLAINT") is True
        mock_boto_client.put_suppressed_destination.assert_called_with(
            EmailAddress="test@example.com", Reason="COMPLAINT"
        )

        # Test is_suppressed
        assert service.is_suppressed("test@example.com") is True

        # Test unsuppress_email
        assert service.unsuppress_email("test@example.com") is True
        mock_boto_client.delete_suppressed_destination.assert_called_with(
            EmailAddress="test@example.com"
        )

        # Test list_suppressed
        suppressed_list = service.list_suppressed()
        assert len(suppressed_list) == 1
        assert suppressed_list[0]["email"] == "test@example.com"
