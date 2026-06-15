"""Notes tool handlers for Fellow.ai API.

Provides MCP tool handlers for listing, retrieving, and deleting
Fellow.ai meeting notes.
"""

from typing import Any

from app.client.fellow_api import FellowApiClient
from app.client.paginator import CursorPaginator


# Filter fields that go into the POST body for list_notes
_LIST_NOTES_FILTERS = [
    "event_guid",
    "created_at_start",
    "created_at_end",
    "updated_at_start",
    "updated_at_end",
    "channel_id",
    "title",
    "event_attendees",
]


def list_notes(
    arguments: dict[str, Any],
    client: FellowApiClient,
    paginator: CursorPaginator,
) -> dict[str, Any]:
    """List notes with optional filters and include options.

    Sends a POST request to /api/v1/notes with filters and include options
    in the request body. Uses cursor pagination to retrieve all pages.

    Args:
        arguments: Validated tool arguments. Optional keys:
            - event_guid, created_at_start, created_at_end,
              updated_at_start, updated_at_end, channel_id,
              title, event_attendees (filters)
            - include (list of: event_attendees, content_markdown)
        client: Fellow API HTTP client.
        paginator: Cursor paginator for multi-page retrieval.

    Returns:
        Dict with 'results' list and optional 'truncated' indicator.
    """
    # Build request body from filters
    body: dict[str, Any] = {}
    for key in _LIST_NOTES_FILTERS:
        if key in arguments:
            body[key] = arguments[key]

    # Include options go in the body alongside filters
    if "include" in arguments:
        body["include"] = arguments["include"]

    def request_fn(params: dict) -> dict[str, Any]:
        # Merge pagination params (page_size, cursor) into the body
        request_body = {**body, **params}
        return client.post("/api/v1/notes", body=request_body)

    results, was_truncated = paginator.fetch_all(request_fn, {})

    response: dict[str, Any] = {"results": results}
    if was_truncated:
        response["truncated"] = True
        response["total_returned"] = len(results)
    return response


def get_note(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Retrieve a single note by ID.

    Sends a GET request to /api/v1/note/{id}.

    Args:
        arguments: Validated tool arguments with required 'id' key.
        client: Fellow API HTTP client.

    Returns:
        Note details from the Fellow API.
    """
    note_id = arguments["id"]
    return client.get(f"/api/v1/note/{note_id}")


def delete_note(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Delete a note by ID.

    Sends a DELETE request to /api/v1/note/{id}.

    Args:
        arguments: Validated tool arguments with required 'id' key.
        client: Fellow API HTTP client.

    Returns:
        Confirmation dict with 'deleted' flag and note 'id'.
    """
    note_id = arguments["id"]
    client.delete(f"/api/v1/note/{note_id}")
    return {"deleted": True, "id": note_id}
