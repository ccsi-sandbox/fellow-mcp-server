"""Unit tests for action item tool handlers."""

from unittest.mock import MagicMock

import pytest

from app.tools.action_items import (
    archive_action_item,
    complete_action_item,
    get_action_item,
    list_action_items,
)


@pytest.fixture
def mock_client():
    """Create a mock FellowApiClient."""
    return MagicMock()


@pytest.fixture
def mock_paginator():
    """Create a mock CursorPaginator."""
    return MagicMock()


class TestListActionItems:
    """Tests for list_action_items handler."""

    def test_no_filters(self, mock_client, mock_paginator):
        """List action items with no filters passes empty body to paginator."""
        mock_paginator.fetch_all.return_value = (
            [{"id": "1", "title": "Task 1"}],
            False,
        )

        result = list_action_items({}, mock_client, mock_paginator)

        assert result == {"results": [{"id": "1", "title": "Task 1"}]}
        mock_paginator.fetch_all.assert_called_once()

    def test_with_all_filters(self, mock_client, mock_paginator):
        """List action items passes all recognized filters in nested structure."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {
            "completed": True,
            "archived": False,
            "ai_detected": True,
            "scope": "assigned_to_me",
            "ordering": "created_at_desc",
        }

        list_action_items(arguments, mock_client, mock_paginator)

        # Verify paginator was called with correct base_body
        call_kwargs = mock_paginator.fetch_all.call_args.kwargs
        base_body = call_kwargs["base_body"]

        # Filter keys should be in nested "filters" object
        assert base_body["filters"] == {
            "completed": True,
            "archived": False,
            "ai_detected": True,
            "scope": "assigned_to_me",
        }
        # "ordering" maps to "order_by" at top level
        assert base_body["order_by"] == "created_at_desc"
        assert call_kwargs["response_key"] == "action_items"

    def test_partial_filters(self, mock_client, mock_paginator):
        """List action items only includes provided filters."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {"completed": False, "scope": "all"}

        list_action_items(arguments, mock_client, mock_paginator)

        call_kwargs = mock_paginator.fetch_all.call_args.kwargs
        base_body = call_kwargs["base_body"]

        assert base_body["filters"] == {"completed": False, "scope": "all"}
        assert "order_by" not in base_body

    def test_truncated_results(self, mock_client, mock_paginator):
        """When paginator indicates truncation, response includes truncation info."""
        items = [{"id": str(i)} for i in range(100)]
        mock_paginator.fetch_all.return_value = (items, True)

        result = list_action_items({}, mock_client, mock_paginator)

        assert result["truncated"] is True
        assert result["total_returned"] == 100
        assert result["results"] == items

    def test_non_truncated_omits_flag(self, mock_client, mock_paginator):
        """When results are not truncated, no truncation fields in response."""
        mock_paginator.fetch_all.return_value = ([{"id": "1"}], False)

        result = list_action_items({}, mock_client, mock_paginator)

        assert "truncated" not in result
        assert "total_returned" not in result

    def test_ignores_unknown_arguments(self, mock_client, mock_paginator):
        """Unknown arguments are not included in the API request body."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {"completed": True, "unknown_param": "value"}

        list_action_items(arguments, mock_client, mock_paginator)

        call_kwargs = mock_paginator.fetch_all.call_args.kwargs
        base_body = call_kwargs["base_body"]

        # Only known filters should be present
        assert base_body["filters"] == {"completed": True}
        assert "unknown_param" not in base_body
        # No extra top-level keys
        assert set(base_body.keys()) == {"filters"}


class TestGetActionItem:
    """Tests for get_action_item handler."""

    def test_get_by_id(self, mock_client):
        """Get action item sends GET request with correct path."""
        expected = {"id": "abc123", "title": "My Task", "completed": False}
        mock_client.get.return_value = expected

        result = get_action_item({"id": "abc123"}, mock_client)

        assert result == expected
        mock_client.get.assert_called_once_with("/api/v1/action_item/abc123", metrics=None)

    def test_get_returns_full_response(self, mock_client):
        """Get action item returns the full API response."""
        expected = {
            "id": "xyz",
            "title": "Task",
            "completed": True,
            "archived": False,
            "ai_detected": True,
            "due_date": "2024-01-15",
        }
        mock_client.get.return_value = expected

        result = get_action_item({"id": "xyz"}, mock_client)

        assert result == expected


class TestCompleteActionItem:
    """Tests for complete_action_item handler."""

    def test_mark_complete(self, mock_client):
        """Complete action item sends POST with completed=true."""
        expected = {"id": "abc", "completed": True}
        mock_client.post.return_value = expected

        result = complete_action_item(
            {"id": "abc", "completed": True}, mock_client
        )

        assert result == expected
        mock_client.post.assert_called_once_with(
            "/api/v1/action_item/abc/complete",
            body={"completed": True},
            metrics=None,
        )

    def test_mark_incomplete(self, mock_client):
        """Complete action item sends POST with completed=false."""
        expected = {"id": "abc", "completed": False}
        mock_client.post.return_value = expected

        result = complete_action_item(
            {"id": "abc", "completed": False}, mock_client
        )

        assert result == expected
        mock_client.post.assert_called_once_with(
            "/api/v1/action_item/abc/complete",
            body={"completed": False},
            metrics=None,
        )

    def test_returns_updated_item(self, mock_client):
        """Complete action item returns the updated item from API."""
        updated = {
            "id": "item1",
            "title": "Updated Task",
            "completed": True,
            "archived": False,
        }
        mock_client.post.return_value = updated

        result = complete_action_item(
            {"id": "item1", "completed": True}, mock_client
        )

        assert result == updated


class TestArchiveActionItem:
    """Tests for archive_action_item handler."""

    def test_archive(self, mock_client):
        """Archive action item sends POST to archive endpoint."""
        expected = {"id": "abc", "archived": True}
        mock_client.post.return_value = expected

        result = archive_action_item({"id": "abc"}, mock_client)

        assert result == expected
        mock_client.post.assert_called_once_with(
            "/api/v1/action_item/abc/archive",
            metrics=None,
        )

    def test_returns_updated_item(self, mock_client):
        """Archive action item returns the updated item from API."""
        updated = {
            "id": "item2",
            "title": "Archived Task",
            "completed": False,
            "archived": True,
        }
        mock_client.post.return_value = updated

        result = archive_action_item({"id": "item2"}, mock_client)

        assert result == updated
