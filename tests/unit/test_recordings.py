"""Unit tests for recordings tool handlers."""

from unittest.mock import MagicMock

import pytest

from app.tools.recordings import delete_recording, get_recording, list_recordings


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


class TestListRecordings:
    """Tests for list_recordings handler."""

    def test_list_recordings_no_filters(self, mock_client, mock_paginator):
        """list_recordings with no filters sends empty body through paginator."""
        mock_paginator.fetch_all.return_value = (
            [{"id": "r1", "title": "Recording 1"}],
            False,
        )

        result = list_recordings({}, mock_client, mock_paginator)

        assert result == {"results": [{"id": "r1", "title": "Recording 1"}]}
        mock_paginator.fetch_all.assert_called_once()

    def test_list_recordings_with_filters(self, mock_client, mock_paginator):
        """list_recordings passes filter params to the request body."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {
            "event_guid": "guid-abc",
            "created_at_start": "2024-01-01",
            "created_at_end": "2024-06-30",
            "title": "Sprint Review",
        }
        list_recordings(arguments, mock_client, mock_paginator)

        # Get the request_fn that was passed to fetch_all
        request_fn = mock_paginator.fetch_all.call_args[0][0]

        # Call request_fn with pagination params to verify body content
        mock_client.post.return_value = {"results": [], "cursor": None}
        request_fn({"page_size": 50})

        mock_client.post.assert_called_once_with(
            "/api/v1/recordings",
            body={
                "event_guid": "guid-abc",
                "created_at_start": "2024-01-01",
                "created_at_end": "2024-06-30",
                "title": "Sprint Review",
                "page_size": 50,
            },
        )

    def test_list_recordings_with_include_options(self, mock_client, mock_paginator):
        """list_recordings passes include options in the request body."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {"include": ["transcript", "ai_notes"]}
        list_recordings(arguments, mock_client, mock_paginator)

        request_fn = mock_paginator.fetch_all.call_args[0][0]
        mock_client.post.return_value = {"results": [], "cursor": None}
        request_fn({"page_size": 50})

        mock_client.post.assert_called_once_with(
            "/api/v1/recordings",
            body={
                "include": ["transcript", "ai_notes"],
                "page_size": 50,
            },
        )

    def test_list_recordings_with_media_url_flag(self, mock_client, mock_paginator):
        """list_recordings passes media_url flag in the request body."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {"media_url": True}
        list_recordings(arguments, mock_client, mock_paginator)

        request_fn = mock_paginator.fetch_all.call_args[0][0]
        mock_client.post.return_value = {"results": [], "cursor": None}
        request_fn({"page_size": 50})

        mock_client.post.assert_called_once_with(
            "/api/v1/recordings",
            body={
                "media_url": True,
                "page_size": 50,
            },
        )

    def test_list_recordings_with_filters_includes_and_media_url(
        self, mock_client, mock_paginator
    ):
        """list_recordings combines filters, includes, and media_url in the body."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {
            "channel_id": "ch-789",
            "include": ["transcript"],
            "media_url": True,
        }
        list_recordings(arguments, mock_client, mock_paginator)

        request_fn = mock_paginator.fetch_all.call_args[0][0]
        mock_client.post.return_value = {"results": [], "cursor": None}
        request_fn({"page_size": 50})

        mock_client.post.assert_called_once_with(
            "/api/v1/recordings",
            body={
                "channel_id": "ch-789",
                "include": ["transcript"],
                "media_url": True,
                "page_size": 50,
            },
        )

    def test_list_recordings_truncated_results(self, mock_client, mock_paginator):
        """list_recordings includes truncation indicator when paginator truncates."""
        mock_paginator.fetch_all.return_value = (
            [{"id": f"r{i}"} for i in range(1000)],
            True,
        )

        result = list_recordings({}, mock_client, mock_paginator)

        assert result["truncated"] is True
        assert result["total_returned"] == 1000
        assert len(result["results"]) == 1000

    def test_list_recordings_not_truncated_no_indicator(
        self, mock_client, mock_paginator
    ):
        """list_recordings does not include truncation indicator when not truncated."""
        mock_paginator.fetch_all.return_value = ([{"id": "r1"}], False)

        result = list_recordings({}, mock_client, mock_paginator)

        assert "truncated" not in result
        assert "total_returned" not in result

    def test_list_recordings_all_filters(self, mock_client, mock_paginator):
        """list_recordings handles all filter fields correctly."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {
            "event_guid": "guid-1",
            "created_at_start": "2024-01-01",
            "created_at_end": "2024-12-31",
            "updated_at_start": "2024-06-01",
            "updated_at_end": "2024-06-30",
            "channel_id": "ch-1",
            "title": "Retro",
        }
        list_recordings(arguments, mock_client, mock_paginator)

        request_fn = mock_paginator.fetch_all.call_args[0][0]
        mock_client.post.return_value = {"results": [], "cursor": None}
        request_fn({"page_size": 50})

        mock_client.post.assert_called_once_with(
            "/api/v1/recordings",
            body={
                "event_guid": "guid-1",
                "created_at_start": "2024-01-01",
                "created_at_end": "2024-12-31",
                "updated_at_start": "2024-06-01",
                "updated_at_end": "2024-06-30",
                "channel_id": "ch-1",
                "title": "Retro",
                "page_size": 50,
            },
        )

    def test_list_recordings_media_url_false(self, mock_client, mock_paginator):
        """list_recordings passes media_url=False when explicitly set."""
        mock_paginator.fetch_all.return_value = ([], False)

        arguments = {"media_url": False}
        list_recordings(arguments, mock_client, mock_paginator)

        request_fn = mock_paginator.fetch_all.call_args[0][0]
        mock_client.post.return_value = {"results": [], "cursor": None}
        request_fn({"page_size": 50})

        mock_client.post.assert_called_once_with(
            "/api/v1/recordings",
            body={
                "media_url": False,
                "page_size": 50,
            },
        )


class TestGetRecording:
    """Tests for get_recording handler."""

    def test_get_recording_no_includes(self, mock_client):
        """get_recording sends GET to correct endpoint with no params."""
        mock_client.get.return_value = {
            "id": "rec-123",
            "title": "Team Standup",
        }

        result = get_recording({"id": "rec-123"}, mock_client)

        mock_client.get.assert_called_once_with(
            "/api/v1/recording/rec-123", params=None
        )
        assert result == {"id": "rec-123", "title": "Team Standup"}

    def test_get_recording_with_includes(self, mock_client):
        """get_recording passes include options as query params."""
        mock_client.get.return_value = {
            "id": "rec-456",
            "title": "Sprint Review",
            "transcript": "Hello everyone...",
        }

        result = get_recording(
            {"id": "rec-456", "include": ["transcript", "ai_notes"]},
            mock_client,
        )

        mock_client.get.assert_called_once_with(
            "/api/v1/recording/rec-456",
            params={"include": "transcript,ai_notes"},
        )
        assert result["id"] == "rec-456"
        assert result["transcript"] == "Hello everyone..."

    def test_get_recording_with_media_url(self, mock_client):
        """get_recording passes media_url flag as query param."""
        mock_client.get.return_value = {
            "id": "rec-789",
            "media_url": "https://example.com/media.mp4",
        }

        result = get_recording(
            {"id": "rec-789", "media_url": True},
            mock_client,
        )

        mock_client.get.assert_called_once_with(
            "/api/v1/recording/rec-789",
            params={"media_url": True},
        )
        assert result["media_url"] == "https://example.com/media.mp4"

    def test_get_recording_with_includes_and_media_url(self, mock_client):
        """get_recording passes both include and media_url as query params."""
        mock_client.get.return_value = {"id": "rec-100"}

        get_recording(
            {"id": "rec-100", "include": ["transcript"], "media_url": True},
            mock_client,
        )

        mock_client.get.assert_called_once_with(
            "/api/v1/recording/rec-100",
            params={"include": "transcript", "media_url": True},
        )

    def test_get_recording_with_special_characters_in_id(self, mock_client):
        """get_recording handles IDs with various characters."""
        mock_client.get.return_value = {"id": "abc-123_def"}

        result = get_recording({"id": "abc-123_def"}, mock_client)

        mock_client.get.assert_called_once_with(
            "/api/v1/recording/abc-123_def", params=None
        )
        assert result["id"] == "abc-123_def"


class TestDeleteRecording:
    """Tests for delete_recording handler."""

    def test_delete_recording_success(self, mock_client):
        """delete_recording sends DELETE and returns confirmation."""
        mock_client.delete.return_value = {}

        result = delete_recording({"id": "rec-456"}, mock_client)

        mock_client.delete.assert_called_once_with("/api/v1/recording/rec-456")
        assert result == {"deleted": True, "id": "rec-456"}

    def test_delete_recording_returns_id_in_confirmation(self, mock_client):
        """delete_recording includes the deleted recording's ID in the response."""
        mock_client.delete.return_value = {}

        result = delete_recording({"id": "my-recording-id"}, mock_client)

        assert result["deleted"] is True
        assert result["id"] == "my-recording-id"
