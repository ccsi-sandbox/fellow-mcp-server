"""User info tool handler for Fellow.ai API.

Provides the get_current_user MCP tool handler for retrieving
the authenticated user's information from the Fellow.ai API.
"""

from typing import Any

from app.client.fellow_api import FellowApiClient, FellowApiError


def get_current_user(
    arguments: dict[str, Any],
    client: FellowApiClient,
    **kwargs: Any,
) -> dict[str, Any]:
    """Get the authenticated user's info from /api/v1/me.

    Sends a GET request to /api/v1/me and returns user information
    including user ID, full name, email, workspace ID, workspace name,
    and workspace subdomain.

    Args:
        arguments: Empty dict (no input parameters required).
        client: Fellow API HTTP client.

    Returns:
        Dict with user info (user ID, full name, email, workspace ID,
        workspace name, workspace subdomain).

    Raises:
        dict: If Fellow API returns 401, returns a dict with an error
            message indicating the API key is invalid or expired.

    Validates: Requirements 9.1, 9.2
    """
    try:
        return client.get("/api/v1/me")
    except FellowApiError as e:
        if e.status_code == 401:
            return {
                "error": "Fellow API key is invalid or expired",
            }
        raise
