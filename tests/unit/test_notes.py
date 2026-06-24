"""Unit tests for notes tool handlers."""

from unittest.mock import MagicMock

import pytest

from app.tools.notes import delete_note, get_note, list_notes


@pytest.fixture
def mock_client():
    """Create a mock FellowApiClient."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_paginator():
    """Create a mock CursorPaginator."""
    paginator = MagicMock()
    return paginator


class TestListNotes:
    """Tests for list_notes handler."""

    def test_list_notes_no_filters(self, mock_client, mock_paginator):
        """list_notes with no filters sends empty body through paginator."""
        mock_paginator.fetch_all.return_value = (
            [{"id": "n1", "title": "Note 1"}],
            False,
        )

        result = list_notes({}, mock_client, mock_paginator)

        assert result == {"results": [{"id": "n1", "title": "Note 1"}]}
        mock_paginator.fetch_all.assert_called_once()

    def test_list_notes_with_filters(self, mock_client, mock_paginator):
        """list_notes passes filter params in nested 'filters' object."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {
            "event_guid": "guid-123",
            "created_at_start": "2024-01-01",
            "created_at_end": "2024-12-31",
            "title": "Standup",
        }
        list_notes(arguments, mock_client, mock_paginator)

        # Get the base_body passed to fetch_all via kwargs
        call_kwargs = mock_paginator.fetch_all.call_args.kwargs
        base_body = call_kwargs["base_body"]

        # Filters should be in nested "filters" key
        assert base_body["filters"] == {
            "event_guid": "guid-123",
            "created_at_start": "2024-01-01",
            "created_at_end": "2024-12-31",
            "title": "Standup",
        }
        # response_key should be "notes"
        assert call_kwargs["response_key"] == "notes"

    def test_list_notes_with_include_options(self, mock_client, mock_paginator):
        """list_notes passes include options as nested boolean object."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {"include": ["event_attendees", "content_markdown"]}
        list_notes(arguments, mock_client, mock_paginator)

        call_kwargs = mock_paginator.fetch_all.call_args.kwargs
        base_body = call_kwargs["base_body"]

        # Include should be a nested object with boolean values
        assert base_body["include"] == {
            "event_attendees": True,
            "content_markdown": True,
        }

    def test_list_notes_with_filters_and_includes(self, mock_client, mock_paginator):
        """list_notes combines filters and include options in the body."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {
            "channel_id": "ch-456",
            "include": ["content_markdown"],
        }
        list_notes(arguments, mock_client, mock_paginator)

        call_kwargs = mock_paginator.fetch_all.call_args.kwargs
        base_body = call_kwargs["base_body"]

        assert base_body["filters"] == {"channel_id": "ch-456"}
        assert base_body["include"] == {"content_markdown": True}

    def test_list_notes_truncated_results(self, mock_client, mock_paginator):
        """list_notes includes truncation indicator when paginator truncates."""
        mock_paginator.fetch_all.return_value = (
            [{"id": f"n{i}"} for i in range(1000)],
            True,
        )

        result = list_notes({}, mock_client, mock_paginator)

        assert result["truncated"] is True
        assert result["total_returned"] == 1000
        assert len(result["results"]) == 1000

    def test_list_notes_not_truncated_no_indicator(self, mock_client, mock_paginator):
        """list_notes does not include truncation indicator when not truncated."""
        mock_paginator.fetch_all.return_value = ([{"id": "n1"}], False)

        result = list_notes({}, mock_client, mock_paginator)

        assert "truncated" not in result
        assert "total_returned" not in result

    def test_list_notes_event_attendees_filter(self, mock_client, mock_paginator):
        """list_notes passes event_attendees as a filter."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {"event_attendees": "user@example.com"}
        list_notes(arguments, mock_client, mock_paginator)

        call_kwargs = mock_paginator.fetch_all.call_args.kwargs
        base_body = call_kwargs["base_body"]

        assert base_body["filters"] == {"event_attendees": "user@example.com"}


class TestGetNote:
    """Tests for get_note handler."""

    def test_get_note_success(self, mock_client):
        """get_note sends GET to correct endpoint and returns response."""
        mock_client.get.return_value = {
            "id": "note-123",
            "title": "Team Standup",
            "content_markdown": "# Notes\n- Item 1",
        }

        result = get_note({"id": "note-123"}, mock_client)

        mock_client.get.assert_called_once_with("/api/v1/note/note-123", metrics=None)
        assert result == {
            "id": "note-123",
            "title": "Team Standup",
            "content_markdown": "# Notes\n- Item 1",
        }

    def test_get_note_with_special_characters_in_id(self, mock_client):
        """get_note handles IDs with various characters."""
        mock_client.get.return_value = {"id": "abc-123_def"}

        result = get_note({"id": "abc-123_def"}, mock_client)

        mock_client.get.assert_called_once_with("/api/v1/note/abc-123_def", metrics=None)
        assert result["id"] == "abc-123_def"


class TestDeleteNote:
    """Tests for delete_note handler."""

    def test_delete_note_success(self, mock_client):
        """delete_note sends DELETE and returns confirmation."""
        mock_client.delete.return_value = {}

        result = delete_note({"id": "note-456"}, mock_client)

        mock_client.delete.assert_called_once_with("/api/v1/note/note-456", metrics=None)
        assert result == {"deleted": True, "id": "note-456"}

    def test_delete_note_returns_id_in_confirmation(self, mock_client):
        """delete_note includes the deleted note's ID in the response."""
        mock_client.delete.return_value = {}

        result = delete_note({"id": "my-note-id"}, mock_client)

        assert result["deleted"] is True
        assert result["id"] == "my-note-id"
