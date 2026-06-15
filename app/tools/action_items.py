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

    Sends a POST request to /api/v1/action_items with the Fellow API's
    expected body structure:
        {
            "pagination": {"cursor": null, "page_size": 50},
            "filters": {...},
            "order_by": "..."
        }

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
        Dict with 'results' list and optional 'truncated' flag.
    """
    # Build the request body per Fellow API spec
    body: dict[str, Any] = {}

    # Filters go in a nested "filters" object
    filters: dict[str, Any] = {}
    filter_keys = ("completed", "archived", "ai_detected", "scope")
    for key in filter_keys:
        if key in arguments:
            filters[key] = arguments[key]
    if filters:
        body["filters"] = filters

    # order_by is a top-level parameter
    if "ordering" in arguments:
        body["order_by"] = arguments["ordering"]

    def request_fn(request_body: dict[str, Any]) -> dict[str, Any]:
        return client.post("/api/v1/action_items", body=request_body)

    results, was_truncated = paginator.fetch_all(
        request_fn=request_fn,
        base_body=body,
        response_key="action_items",
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
    """
    action_item_id = arguments["id"]
    return client.post(f"/api/v1/action_item/{action_item_id}/archive")
