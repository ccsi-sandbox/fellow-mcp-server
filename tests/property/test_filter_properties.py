"""Property-based tests for filter parameter passthrough.

# Feature: fellow-mcp-server, Property 7: Filter parameters pass through to Fellow API requests

Tests that filter parameters provided to list tools are passed through exactly
to the Fellow API request body, with no omissions and no additions beyond
pagination parameters (page_size, cursor).
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.client.paginator import CursorPaginator
from app.tools.action_items import list_action_items
from app.tools.notes import list_notes
from app.tools.recordings import list_recordings
from app.validation.schemas import (
    SCOPE_VALUES,
    ORDERING_VALUES,
    NOTE_INCLUDE_VALUES,
    RECORDING_INCLUDE_VALUES,
)


# --- Strategies ---

# Action item filter combinations
action_item_filters = st.fixed_dictionaries({}, optional={
    "completed": st.booleans(),
    "archived": st.booleans(),
    "ai_detected": st.booleans(),
    "scope": st.sampled_from(SCOPE_VALUES),
    "ordering": st.sampled_from(ORDERING_VALUES),
})

# Valid date strings for note/recording filters
valid_date_strings = st.dates().map(lambda d: d.isoformat())

# Note filter combinations
note_filters = st.fixed_dictionaries({}, optional={
    "event_guid": st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N"), min_codepoint=48
    )),
    "created_at_start": valid_date_strings,
    "created_at_end": valid_date_strings,
    "updated_at_start": valid_date_strings,
    "updated_at_end": valid_date_strings,
    "channel_id": st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N"), min_codepoint=48
    )),
    "title": st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"), min_codepoint=32
    )),
    "event_attendees": st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N"), min_codepoint=48
    )),
    "include": st.lists(
        st.sampled_from(NOTE_INCLUDE_VALUES), min_size=1, max_size=2, unique=True
    ),
})

# Recording filter combinations
recording_filters = st.fixed_dictionaries({}, optional={
    "event_guid": st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N"), min_codepoint=48
    )),
    "created_at_start": valid_date_strings,
    "created_at_end": valid_date_strings,
    "updated_at_start": valid_date_strings,
    "updated_at_end": valid_date_strings,
    "channel_id": st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N"), min_codepoint=48
    )),
    "title": st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"), min_codepoint=32
    )),
    "include": st.lists(
        st.sampled_from(RECORDING_INCLUDE_VALUES), min_size=1, max_size=3, unique=True
    ),
    "media_url": st.booleans(),
})


# Pagination keys that the paginator is allowed to add
PAGINATION_KEYS = {"page_size", "cursor"}


def _make_mock_client() -> MagicMock:
    """Create a mock FellowApiClient whose post() returns a single page response."""
    mock_client = MagicMock()
    mock_client.post.return_value = {"results": [{"id": "test-1"}], "cursor": None}
    return mock_client


def _extract_body_from_post_call(mock_client: MagicMock) -> dict[str, Any]:
    """Extract the body dict passed to mock_client.post()."""
    assert mock_client.post.called, "client.post was not called"
    call_args = mock_client.post.call_args
    # post(path, body={...})
    if call_args.kwargs.get("body") is not None:
        return call_args.kwargs["body"]
    # post(path, body={...}) as positional
    if len(call_args.args) >= 2:
        return call_args.args[1]
    return {}


# --- Property 7: Filter parameters pass through to Fellow API requests ---


@pytest.mark.property
class TestFilterPassthrough:
    """Property 7: Filter parameters pass through to Fellow API requests.

    For any valid combination of filter parameters for list tools
    (action items, notes, recordings), the request sent to the Fellow API
    SHALL contain exactly those filter values in the request body, with no
    omissions and no additions beyond pagination parameters.

    **Validates: Requirements 5.1, 6.1, 7.1**
    """

    @given(filters=action_item_filters)
    @settings(max_examples=100)
    def test_action_item_filters_pass_through(self, filters: dict[str, Any]):
        """All provided action item filters appear in the Fellow API request body.

        **Validates: Requirements 5.1**
        """
        mock_client = _make_mock_client()
        paginator = CursorPaginator(max_pages=20, page_size=50)

        list_action_items(
            arguments=filters,
            client=mock_client,
            paginator=paginator,
        )

        body = _extract_body_from_post_call(mock_client)

        # All provided filter values must appear in the body
        for key, value in filters.items():
            assert key in body, f"Filter '{key}' missing from request body"
            assert body[key] == value, (
                f"Filter '{key}' has wrong value: expected {value!r}, got {body[key]!r}"
            )

        # No extra keys beyond filters + pagination params
        extra_keys = set(body.keys()) - set(filters.keys()) - PAGINATION_KEYS
        assert extra_keys == set(), (
            f"Unexpected extra keys in request body: {extra_keys}"
        )

    @given(filters=note_filters)
    @settings(max_examples=100)
    def test_note_filters_pass_through(self, filters: dict[str, Any]):
        """All provided note filters appear in the Fellow API request body.

        **Validates: Requirements 6.1**
        """
        mock_client = _make_mock_client()
        paginator = CursorPaginator(max_pages=20, page_size=50)

        list_notes(
            arguments=filters,
            client=mock_client,
            paginator=paginator,
        )

        body = _extract_body_from_post_call(mock_client)

        # All provided filter values must appear in the body
        for key, value in filters.items():
            assert key in body, f"Filter '{key}' missing from request body"
            assert body[key] == value, (
                f"Filter '{key}' has wrong value: expected {value!r}, got {body[key]!r}"
            )

        # No extra keys beyond filters + pagination params
        extra_keys = set(body.keys()) - set(filters.keys()) - PAGINATION_KEYS
        assert extra_keys == set(), (
            f"Unexpected extra keys in request body: {extra_keys}"
        )

    @given(filters=recording_filters)
    @settings(max_examples=100)
    def test_recording_filters_pass_through(self, filters: dict[str, Any]):
        """All provided recording filters and options appear in the Fellow API request body.

        **Validates: Requirements 7.1**
        """
        mock_client = _make_mock_client()
        paginator = CursorPaginator(max_pages=20, page_size=50)

        list_recordings(
            arguments=filters,
            client=mock_client,
            paginator=paginator,
        )

        body = _extract_body_from_post_call(mock_client)

        # All provided filter values must appear in the body
        for key, value in filters.items():
            assert key in body, f"Filter '{key}' missing from request body"
            assert body[key] == value, (
                f"Filter '{key}' has wrong value: expected {value!r}, got {body[key]!r}"
            )

        # No extra keys beyond filters + pagination params
        extra_keys = set(body.keys()) - set(filters.keys()) - PAGINATION_KEYS
        assert extra_keys == set(), (
            f"Unexpected extra keys in request body: {extra_keys}"
        )

    def test_action_item_empty_filters_only_adds_pagination(self):
        """When no filters are provided, only pagination params appear in body.

        **Validates: Requirements 5.1**
        """
        mock_client = _make_mock_client()
        paginator = CursorPaginator(max_pages=20, page_size=50)

        list_action_items(
            arguments={},
            client=mock_client,
            paginator=paginator,
        )

        body = _extract_body_from_post_call(mock_client)

        # Body should only contain pagination keys
        non_pagination_keys = set(body.keys()) - PAGINATION_KEYS
        assert non_pagination_keys == set(), (
            f"Unexpected keys when no filters provided: {non_pagination_keys}"
        )

    def test_note_empty_filters_only_adds_pagination(self):
        """When no note filters are provided, only pagination params appear in body.

        **Validates: Requirements 6.1**
        """
        mock_client = _make_mock_client()
        paginator = CursorPaginator(max_pages=20, page_size=50)

        list_notes(
            arguments={},
            client=mock_client,
            paginator=paginator,
        )

        body = _extract_body_from_post_call(mock_client)

        # Body should only contain pagination keys
        non_pagination_keys = set(body.keys()) - PAGINATION_KEYS
        assert non_pagination_keys == set(), (
            f"Unexpected keys when no filters provided: {non_pagination_keys}"
        )

    def test_recording_empty_filters_only_adds_pagination(self):
        """When no recording filters are provided, only pagination params appear in body.

        **Validates: Requirements 7.1**
        """
        mock_client = _make_mock_client()
        paginator = CursorPaginator(max_pages=20, page_size=50)

        list_recordings(
            arguments={},
            client=mock_client,
            paginator=paginator,
        )

        body = _extract_body_from_post_call(mock_client)

        # Body should only contain pagination keys
        non_pagination_keys = set(body.keys()) - PAGINATION_KEYS
        assert non_pagination_keys == set(), (
            f"Unexpected keys when no filters provided: {non_pagination_keys}"
        )
