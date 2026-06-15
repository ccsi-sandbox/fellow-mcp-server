"""Webhook tool handlers for Fellow.ai API.

Provides MCP tool handlers for creating, listing, retrieving, updating,
and deleting Fellow.ai webhooks.
"""

from typing import Any

from app.client.fellow_api import FellowApiClient


def list_webhooks(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """List webhooks with optional limit and cursor query parameters.

    Sends a GET request to /api/v1/webhook with optional query params
    for limit and cursor. Unlike other list tools, this does NOT use
    POST-based pagination.

    Args:
        arguments: Validated tool arguments. Optional keys:
            - limit (int): Max results to return (1-50, default 50).
            - cursor (str): Pagination cursor for next page.
        client: Fellow API HTTP client.

    Returns:
        Webhook list response from the Fellow API.

    Validates: Requirements 8.2
    """
    params: dict[str, Any] = {}
    if "limit" in arguments:
        params["limit"] = arguments["limit"]
    if "cursor" in arguments:
        params["cursor"] = arguments["cursor"]

    return client.get("/api/v1/webhook", params=params or None)


def get_webhook(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Retrieve a single webhook by ID.

    Sends a GET request to /api/v1/webhook/{id}.

    Args:
        arguments: Validated tool arguments with required 'id' key.
        client: Fellow API HTTP client.

    Returns:
        Webhook details from the Fellow API.

    Validates: Requirements 8.3
    """
    webhook_id = arguments["id"]
    return client.get(f"/api/v1/webhook/{webhook_id}")


def create_webhook(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Create a new webhook.

    Sends a POST request to /api/v1/webhook with the provided parameters
    including url, enabled_events, and optional description and status.

    Args:
        arguments: Validated tool arguments with required keys:
            - url (str): Webhook destination URL.
            - enabled_events (list[str]): Events to subscribe to.
            Optional keys:
            - description (str): Human-readable description.
            - status (str): "active" or "inactive".
        client: Fellow API HTTP client.

    Returns:
        Created webhook details from the Fellow API.

    Validates: Requirements 8.1
    """
    body: dict[str, Any] = {
        "url": arguments["url"],
        "enabled_events": arguments["enabled_events"],
    }

    if "description" in arguments:
        body["description"] = arguments["description"]
    if "status" in arguments:
        body["status"] = arguments["status"]

    return client.post("/api/v1/webhook", body=body)


def update_webhook(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Update an existing webhook.

    Sends a PUT request to /api/v1/webhook/{id} with only the provided
    updatable fields included in the request body.

    Args:
        arguments: Validated tool arguments with required 'id' key.
            Optional updatable fields:
            - url (str): New webhook destination URL.
            - enabled_events (list[str]): New events to subscribe to.
            - description (str): New description.
            - status (str): "active" or "inactive".
        client: Fellow API HTTP client.

    Returns:
        Updated webhook details from the Fellow API.

    Validates: Requirements 8.4
    """
    webhook_id = arguments["id"]

    body: dict[str, Any] = {}
    updatable_fields = ("url", "enabled_events", "description", "status")
    for field in updatable_fields:
        if field in arguments:
            body[field] = arguments[field]

    return client.put(f"/api/v1/webhook/{webhook_id}", body=body)


def delete_webhook(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Delete a webhook by ID.

    Sends a DELETE request to /api/v1/webhook/{id}.

    Args:
        arguments: Validated tool arguments with required 'id' key.
        client: Fellow API HTTP client.

    Returns:
        Confirmation dict with 'deleted' flag and webhook 'id'.

    Validates: Requirements 8.5
    """
    webhook_id = arguments["id"]
    client.delete(f"/api/v1/webhook/{webhook_id}")
    return {"deleted": True, "id": webhook_id}
