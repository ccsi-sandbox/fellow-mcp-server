"""Unit tests for user info tool handler."""

from unittest.mock import MagicMock

import pytest

from app.client.fellow_api import FellowApiError
from app.tools.user import get_current_user


@pytest.fixture
def mock_client():
    """Create a mock FellowApiClient."""
    return MagicMock()


class TestGetCurrentUser:
    """Tests for get_current_user handler."""

    def test_get_current_user_success(self, mock_client):
        """get_current_user sends GET to /api/v1/me and returns user info."""
        mock_client.get.return_value = {
            "id": "user-123",
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "workspace_id": "ws-456",
            "workspace_name": "Acme Corp",
            "workspace_subdomain": "acme",
        }

        result = get_current_user({}, mock_client)

        mock_client.get.assert_called_once_with("/api/v1/me", metrics=None)
        assert result == {
            "id": "user-123",
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "workspace_id": "ws-456",
            "workspace_name": "Acme Corp",
            "workspace_subdomain": "acme",
        }

    def test_get_current_user_401_returns_error_message(self, mock_client):
        """get_current_user returns error dict on 401 (invalid/expired API key)."""
        mock_client.get.side_effect = FellowApiError(
            status_code=401,
            message="Unauthorized",
        )

        result = get_current_user({}, mock_client)

        assert result == {"error": "Fellow API key is invalid or expired"}

    def test_get_current_user_non_401_error_raises(self, mock_client):
        """get_current_user re-raises FellowApiError for non-401 status codes."""
        mock_client.get.side_effect = FellowApiError(
            status_code=403,
            message="Forbidden",
        )

        with pytest.raises(FellowApiError) as exc_info:
            get_current_user({}, mock_client)

        assert exc_info.value.status_code == 403
        assert exc_info.value.message == "Forbidden"

    def test_get_current_user_ignores_arguments(self, mock_client):
        """get_current_user ignores any passed arguments (tool takes no input)."""
        mock_client.get.return_value = {"id": "user-1", "full_name": "Test"}

        result = get_current_user(
            {"unexpected_param": "value"}, mock_client
        )

        mock_client.get.assert_called_once_with("/api/v1/me", metrics=None)
        assert result["id"] == "user-1"

    def test_get_current_user_500_error_raises(self, mock_client):
        """get_current_user re-raises FellowApiError for server errors."""
        mock_client.get.side_effect = FellowApiError(
            status_code=500,
            message="Internal Server Error",
        )

        with pytest.raises(FellowApiError) as exc_info:
            get_current_user({}, mock_client)

        assert exc_info.value.status_code == 500
