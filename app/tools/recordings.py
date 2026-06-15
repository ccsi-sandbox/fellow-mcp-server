"""Recordings tool handlers for Fellow.ai API.

Provides MCP tool handlers for listing, retrieving, and deleting
Fellow.ai meeting recordings, including transcripts and AI-generated notes.
"""

from typing import Any

from app.client.fellow_api import FellowApiClient
from app.client.paginator import CursorPaginator


# Filter fields for list_recordings
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

    Sends a POST request to /api/v1/recordings with the Fellow API's
    expected body structure:
        {
            "pagination": {"cursor": null, "page_size": 50},
            "filters": {...},
            "include": {...},
            "media_url": {...}
        }

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
    """
    body: dict[str, Any] = {}

    # Filters go in a nested "filters" object
    filters: dict[str, Any] = {}
    for key in _LIST_RECORDINGS_FILTERS:
        if key in arguments:
            filters[key] = arguments[key]
    if filters:
        body["filters"] = filters

    # Include options go in a nested "include" object
    # The API expects {"include": {"transcript": true, "ai_notes": true}}
    if "include" in arguments:
        include_obj: dict[str, bool] = {}
        for field in arguments["include"]:
            include_obj[field] = True
        body["include"] = include_obj

    # media_url is a nested config object
    if "media_url" in arguments and arguments["media_url"]:
        body["media_url"] = {"include": True}

    def request_fn(request_body: dict[str, Any]) -> dict[str, Any]:
        return client.post("/api/v1/recordings", body=request_body)

    results, was_truncated = paginator.fetch_all(
        request_fn=request_fn,
        base_body=body,
        response_key="recordings",
    )

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
    """
    recording_id = arguments["id"]

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
    """
    recording_id = arguments["id"]
    client.delete(f"/api/v1/recording/{recording_id}")
    return {"deleted": True, "id": recording_id}
