"""Unit tests for webhook tool handlers."""

from unittest.mock import MagicMock

import pytest

from app.tools.webhooks import (
    create_webhook,
    delete_webhook,
    get_webhook,
    list_webhooks,
    update_webhook,
)
from app.validation.schemas import InputValidator


@pytest.fixture
def mock_client():
    """Create a mock FellowApiClient."""
    client = MagicMock()
    return client


class TestListWebhooks:
    """Tests for list_webhooks handler."""

    def test_list_webhooks_no_params(self, mock_client):
        """list_webhooks with no params sends GET with no query params."""
        mock_client.get.return_value = {
            "results": [{"id": "wh1", "url": "https://example.com/hook"}],
            "cursor": None,
        }

        result = list_webhooks({}, mock_client)

        mock_client.get.assert_called_once_with("/api/v1/webhook", params=None, metrics=None)
        assert result == {
            "results": [{"id": "wh1", "url": "https://example.com/hook"}],
            "cursor": None,
        }

    def test_list_webhooks_with_limit(self, mock_client):
        """list_webhooks passes limit as a query parameter."""
        mock_client.get.return_value = {"results": [], "cursor": None}

        result = list_webhooks({"limit": 10}, mock_client)

        mock_client.get.assert_called_once_with(
            "/api/v1/webhook", params={"limit": 10}, metrics=None
        )

    def test_list_webhooks_with_cursor(self, mock_client):
        """list_webhooks passes cursor as a query parameter."""
        mock_client.get.return_value = {"results": [], "cursor": None}

        result = list_webhooks({"cursor": "abc123"}, mock_client)

        mock_client.get.assert_called_once_with(
            "/api/v1/webhook", params={"cursor": "abc123"}, metrics=None
        )

    def test_list_webhooks_with_limit_and_cursor(self, mock_client):
        """list_webhooks passes both limit and cursor as query parameters."""
        mock_client.get.return_value = {"results": [], "cursor": None}

        result = list_webhooks({"limit": 25, "cursor": "next-page"}, mock_client)

        mock_client.get.assert_called_once_with(
            "/api/v1/webhook", params={"limit": 25, "cursor": "next-page"}, metrics=None
        )


class TestGetWebhook:
    """Tests for get_webhook handler."""

    def test_get_webhook_success(self, mock_client):
        """get_webhook sends GET to correct endpoint and returns response."""
        mock_client.get.return_value = {
            "id": "wh-123",
            "url": "https://example.com/hook",
            "status": "active",
            "enabled_events": ["action_item.completed"],
        }

        result = get_webhook({"id": "wh-123"}, mock_client)

        mock_client.get.assert_called_once_with("/api/v1/webhook/wh-123", metrics=None)
        assert result == {
            "id": "wh-123",
            "url": "https://example.com/hook",
            "status": "active",
            "enabled_events": ["action_item.completed"],
        }

    def test_get_webhook_with_special_characters_in_id(self, mock_client):
        """get_webhook handles IDs with various characters."""
        mock_client.get.return_value = {"id": "abc-123_def"}

        result = get_webhook({"id": "abc-123_def"}, mock_client)

        mock_client.get.assert_called_once_with("/api/v1/webhook/abc-123_def", metrics=None)
        assert result["id"] == "abc-123_def"


class TestCreateWebhook:
    """Tests for create_webhook handler."""

    def test_create_webhook_required_fields_only(self, mock_client):
        """create_webhook sends POST with url and enabled_events."""
        mock_client.post.return_value = {
            "id": "wh-new",
            "url": "https://example.com/hook",
            "enabled_events": ["action_item.completed"],
        }

        result = create_webhook(
            {
                "url": "https://example.com/hook",
                "enabled_events": ["action_item.completed"],
            },
            mock_client,
        )

        mock_client.post.assert_called_once_with(
            "/api/v1/webhook",
            body={
                "url": "https://example.com/hook",
                "enabled_events": ["action_item.completed"],
            },
            metrics=None,
        )
        assert result["id"] == "wh-new"

    def test_create_webhook_with_all_fields(self, mock_client):
        """create_webhook sends POST with all optional fields included."""
        mock_client.post.return_value = {
            "id": "wh-full",
            "url": "https://example.com/hook",
            "enabled_events": ["ai_note.generated", "action_item.assigned"],
            "description": "My webhook",
            "status": "active",
        }

        result = create_webhook(
            {
                "url": "https://example.com/hook",
                "enabled_events": ["ai_note.generated", "action_item.assigned"],
                "description": "My webhook",
                "status": "active",
            },
            mock_client,
        )

        mock_client.post.assert_called_once_with(
            "/api/v1/webhook",
            body={
                "url": "https://example.com/hook",
                "enabled_events": ["ai_note.generated", "action_item.assigned"],
                "description": "My webhook",
                "status": "active",
            },
            metrics=None,
        )

    def test_create_webhook_with_description_only(self, mock_client):
        """create_webhook includes description but not status when only description provided."""
        mock_client.post.return_value = {"id": "wh-desc"}

        create_webhook(
            {
                "url": "https://example.com/hook",
                "enabled_events": ["ai_note.shared_to_channel"],
                "description": "Test hook",
            },
            mock_client,
        )

        mock_client.post.assert_called_once_with(
            "/api/v1/webhook",
            body={
                "url": "https://example.com/hook",
                "enabled_events": ["ai_note.shared_to_channel"],
                "description": "Test hook",
            },
            metrics=None,
        )

    def test_create_webhook_with_status_only(self, mock_client):
        """create_webhook includes status but not description when only status provided."""
        mock_client.post.return_value = {"id": "wh-status"}

        create_webhook(
            {
                "url": "https://example.com/hook",
                "enabled_events": ["action_item.completed"],
                "status": "inactive",
            },
            mock_client,
        )

        mock_client.post.assert_called_once_with(
            "/api/v1/webhook",
            body={
                "url": "https://example.com/hook",
                "enabled_events": ["action_item.completed"],
                "status": "inactive",
            },
            metrics=None,
        )


class TestUpdateWebhook:
    """Tests for update_webhook handler."""

    def test_update_webhook_single_field(self, mock_client):
        """update_webhook sends PUT with only the provided field."""
        mock_client.put.return_value = {
            "id": "wh-123",
            "url": "https://new-url.com/hook",
        }

        result = update_webhook(
            {"id": "wh-123", "url": "https://new-url.com/hook"},
            mock_client,
        )

        mock_client.put.assert_called_once_with(
            "/api/v1/webhook/wh-123",
            body={"url": "https://new-url.com/hook"},
            metrics=None,
        )

    def test_update_webhook_multiple_fields(self, mock_client):
        """update_webhook sends PUT with multiple updatable fields."""
        mock_client.put.return_value = {"id": "wh-123"}

        update_webhook(
            {
                "id": "wh-123",
                "url": "https://updated.com/hook",
                "enabled_events": ["ai_note.generated"],
                "description": "Updated desc",
                "status": "inactive",
            },
            mock_client,
        )

        mock_client.put.assert_called_once_with(
            "/api/v1/webhook/wh-123",
            body={
                "url": "https://updated.com/hook",
                "enabled_events": ["ai_note.generated"],
                "description": "Updated desc",
                "status": "inactive",
            },
            metrics=None,
        )

    def test_update_webhook_enabled_events_only(self, mock_client):
        """update_webhook sends PUT with only enabled_events when that's all provided."""
        mock_client.put.return_value = {"id": "wh-123"}

        update_webhook(
            {
                "id": "wh-123",
                "enabled_events": ["action_item.assigned", "action_item.completed"],
            },
            mock_client,
        )

        mock_client.put.assert_called_once_with(
            "/api/v1/webhook/wh-123",
            body={
                "enabled_events": ["action_item.assigned", "action_item.completed"],
            },
            metrics=None,
        )

    def test_update_webhook_excludes_id_from_body(self, mock_client):
        """update_webhook does not include the 'id' field in the PUT body."""
        mock_client.put.return_value = {"id": "wh-123"}

        update_webhook(
            {"id": "wh-123", "status": "active"},
            mock_client,
        )

        call_body = mock_client.put.call_args[1]["body"]
        assert "id" not in call_body
        assert call_body == {"status": "active"}


class TestDeleteWebhook:
    """Tests for delete_webhook handler."""

    def test_delete_webhook_success(self, mock_client):
        """delete_webhook sends DELETE and returns confirmation."""
        mock_client.delete.return_value = {}

        result = delete_webhook({"id": "wh-456"}, mock_client)

        mock_client.delete.assert_called_once_with("/api/v1/webhook/wh-456", metrics=None)
        assert result == {"deleted": True, "id": "wh-456"}

    def test_delete_webhook_returns_id_in_confirmation(self, mock_client):
        """delete_webhook includes the deleted webhook's ID in the response."""
        mock_client.delete.return_value = {}

        result = delete_webhook({"id": "my-webhook-id"}, mock_client)

        assert result["deleted"] is True
        assert result["id"] == "my-webhook-id"


class TestWebhookEnabledEventsValidation:
    """Tests that enabled_events are validated before API call.

    Validates: Requirements 8.6, 8.7
    """

    @pytest.fixture
    def validator(self):
        """Create an InputValidator instance."""
        return InputValidator()

    def test_invalid_enabled_events_rejected_before_api_call(
        self, mock_client, validator
    ):
        """Invalid enabled_events are caught by validation, preventing API call."""
        arguments = {
            "url": "https://example.com/hook",
            "enabled_events": ["invalid.event"],
        }
        errors = validator.validate("create_webhook", arguments)

        # Validation rejects the request
        assert len(errors) > 0
        assert any("enabled_events" in e for e in errors)
        assert any("invalid.event" in e for e in errors)

        # API client is never called because validation happens first
        mock_client.post.assert_not_called()

    def test_valid_enabled_events_pass_validation(self, mock_client, validator):
        """Valid enabled_events pass validation and allow API call."""
        arguments = {
            "url": "https://example.com/hook",
            "enabled_events": ["ai_note.generated", "action_item.completed"],
        }
        errors = validator.validate("create_webhook", arguments)

        # Validation passes
        assert errors == []

        # Now the handler can proceed
        mock_client.post.return_value = {"id": "wh-new"}
        create_webhook(arguments, mock_client)
        mock_client.post.assert_called_once()

    def test_update_webhook_invalid_enabled_events_rejected(
        self, mock_client, validator
    ):
        """Invalid enabled_events in update_webhook are caught by validation."""
        arguments = {
            "id": "wh-123",
            "enabled_events": ["not.a.real.event"],
        }
        errors = validator.validate("update_webhook", arguments)

        # Validation rejects the request
        assert len(errors) > 0
        assert any("enabled_events" in e for e in errors)

        # API client is never called
        mock_client.put.assert_not_called()

    def test_mixed_valid_and_invalid_enabled_events_rejected(
        self, mock_client, validator
    ):
        """A mix of valid and invalid events is still rejected."""
        arguments = {
            "url": "https://example.com/hook",
            "enabled_events": [
                "ai_note.generated",
                "invalid.event",
                "action_item.assigned",
            ],
        }
        errors = validator.validate("create_webhook", arguments)

        # Validation catches the invalid event
        assert len(errors) == 1
        assert "invalid.event" in errors[0]

        # API client not called
        mock_client.post.assert_not_called()

    def test_all_valid_enabled_events_accepted(self, validator):
        """All allowed enabled_events values pass validation."""
        arguments = {
            "url": "https://example.com/hook",
            "enabled_events": [
                "ai_note.shared_to_channel",
                "ai_note.generated",
                "action_item.assigned",
                "action_item.completed",
            ],
        }
        errors = validator.validate("create_webhook", arguments)
        assert errors == []
