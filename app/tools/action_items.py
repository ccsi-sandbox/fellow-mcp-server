"""Action item tool handlers for Fellow.ai API."""

from typing import Any

from app.client.fellow_api import FellowApiClient
from app.client.paginator import CursorPaginator


def list_action_items(
    arguments: dict[str, Any],
    client: FellowApiClient,
    paginator: CursorPaginator,
) -> dict[str, Any]:
    """List action items with optional filters and pagination.

    Sends a POST request to /api/v1/action_items with optional filters
    for completed, archived, ai_detected, scope, and ordering.
    Uses the paginator to automatically retrieve all pages.

    Args:
        arguments: Optional filter parameters:
            - completed (bool): Filter by completion status.
            - archived (bool): Filter by archived status.
            - ai_detected (bool): Filter by AI detection flag.
            - scope (str): One of assigned_to_me, assigned_to_others, all.
            - ordering (str): One of created_at_desc, created_at_asc, due_date.
        client: Fellow API client instance.
        paginator: Cursor paginator for fetching all pages.

    Returns:
        Dict with 'results' list and 'truncated' flag.

    Validates: Requirements 5.1, 5.7
    """
    body: dict[str, Any] = {}

    # Build body from optional filters
    filter_keys = ("completed", "archived", "ai_detected", "scope", "ordering")
    for key in filter_keys:
        if key in arguments:
            body[key] = arguments[key]

    def request_fn(params: dict[str, Any]) -> dict[str, Any]:
        return client.post("/api/v1/action_items", body={**body, **params})

    results, was_truncated = paginator.fetch_all(
        request_fn=request_fn,
        base_params={},
    )

    response: dict[str, Any] = {"results": results}
    if was_truncated:
        response["truncated"] = True
        response["total_returned"] = len(results)

    return response


def get_action_item(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Get a single action item by ID.

    Sends a GET request to /api/v1/action_item/{id}.

    Args:
        arguments: Must contain 'id' (str) - the action item ID.
        client: Fellow API client instance.

    Returns:
        The action item details from the Fellow API.

    Validates: Requirements 5.2
    """
    action_item_id = arguments["id"]
    return client.get(f"/api/v1/action_item/{action_item_id}")


def complete_action_item(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Complete or uncomplete an action item.

    Sends a POST request to /api/v1/action_item/{id}/complete
    with {"completed": true/false}.

    Args:
        arguments: Must contain:
            - id (str): The action item ID.
            - completed (bool): True to mark complete, False to mark incomplete.
        client: Fellow API client instance.

    Returns:
        The updated action item from the Fellow API.

    Validates: Requirements 5.3, 5.4, 5.6
    """
    action_item_id = arguments["id"]
    completed = arguments["completed"]
    return client.post(
        f"/api/v1/action_item/{action_item_id}/complete",
        body={"completed": completed},
    )


def archive_action_item(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Archive an action item.

    Sends a POST request to /api/v1/action_item/{id}/archive.

    Args:
        arguments: Must contain 'id' (str) - the action item ID.
        client: Fellow API client instance.

    Returns:
        The updated action item from the Fellow API.

    Validates: Requirements 5.5, 5.6
    """
    action_item_id = arguments["id"]
    return client.post(f"/api/v1/action_item/{action_item_id}/archive")
