"""Recordings tool handlers for Fellow.ai API.

Provides MCP tool handlers for listing, retrieving, and deleting
Fellow.ai meeting recordings, including transcripts and AI-generated notes.
"""

from typing import Any

from app.client.fellow_api import FellowApiClient
from app.client.paginator import CursorPaginator


# Filter fields that go into the POST body for list_recordings
_LIST_RECORDINGS_FILTERS = [
    "event_guid",
    "created_at_start",
    "created_at_end",
    "updated_at_start",
    "updated_at_end",
    "channel_id",
    "title",
]


def list_recordings(
    arguments: dict[str, Any],
    client: FellowApiClient,
    paginator: CursorPaginator,
) -> dict[str, Any]:
    """List recordings with optional filters, includes, and media_url flag.

    Sends a POST request to /api/v1/recordings with filters, include options
    (transcript, ai_notes), and media_url flag in the request body.
    Uses cursor pagination to retrieve all pages.

    Args:
        arguments: Validated tool arguments. Optional keys:
            - event_guid, created_at_start, created_at_end,
              updated_at_start, updated_at_end, channel_id,
              title (filters)
            - include (list of: transcript, ai_notes)
            - media_url (bool): Whether to return pre-signed media URLs.
        client: Fellow API HTTP client.
        paginator: Cursor paginator for multi-page retrieval.

    Returns:
        Dict with 'results' list and optional 'truncated' indicator.

    Validates: Requirements 7.1, 7.2, 7.5
    """
    # Build request body from filters
    body: dict[str, Any] = {}
    for key in _LIST_RECORDINGS_FILTERS:
        if key in arguments:
            body[key] = arguments[key]

    # Include options go in the body alongside filters
    if "include" in arguments:
        body["include"] = arguments["include"]

    # media_url flag goes in the body
    if "media_url" in arguments:
        body["media_url"] = arguments["media_url"]

    def request_fn(params: dict) -> dict[str, Any]:
        # Merge pagination params (page_size, cursor) into the body
        request_body = {**body, **params}
        return client.post("/api/v1/recordings", body=request_body)

    results, was_truncated = paginator.fetch_all(request_fn, {})

    response: dict[str, Any] = {"results": results}
    if was_truncated:
        response["truncated"] = True
        response["total_returned"] = len(results)
    return response


def get_recording(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Retrieve a single recording by ID with optional includes.

    Sends a GET request to /api/v1/recording/{id} with optional query
    parameters for include (transcript, ai_notes) and media_url.

    Args:
        arguments: Validated tool arguments with required 'id' key.
            Optional keys:
            - include (list of: transcript, ai_notes)
            - media_url (bool): Whether to return pre-signed media URL.
        client: Fellow API HTTP client.

    Returns:
        Recording details from the Fellow API.

    Validates: Requirements 7.3
    """
    recording_id = arguments["id"]

    # Build query params from optional includes and media_url
    params: dict[str, Any] = {}
    if "include" in arguments:
        params["include"] = ",".join(arguments["include"])
    if "media_url" in arguments:
        params["media_url"] = arguments["media_url"]

    return client.get(f"/api/v1/recording/{recording_id}", params=params or None)


def delete_recording(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Delete a recording by ID.

    Sends a DELETE request to /api/v1/recording/{id}.

    Args:
        arguments: Validated tool arguments with required 'id' key.
        client: Fellow API HTTP client.

    Returns:
        Confirmation dict with 'deleted' flag and recording 'id'.

    Validates: Requirements 7.4
    """
    recording_id = arguments["id"]
    client.delete(f"/api/v1/recording/{recording_id}")
    return {"deleted": True, "id": recording_id}
