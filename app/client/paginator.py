"""Cursor-based pagination for Fellow.ai API list endpoints."""

from __future__ import annotations

from typing import Any, Callable

from app.client.fellow_api import FellowApiError, TransientApiError
from app.logging.metrics import RequestMetrics


class PaginationError(Exception):
    """Raised when a page fetch fails mid-pagination.

    Attributes:
        page_number: The 1-based page number that failed.
        cause: The original exception that caused the failure.
    """

    def __init__(self, page_number: int, cause: Exception) -> None:
        self.page_number = page_number
        self.cause = cause
        super().__init__(
            f"Pagination failed on page {page_number}: {cause}"
        )


class CursorPaginator:
    """Handles cursor-based pagination for Fellow API list endpoints.

    The Fellow API uses a nested pagination structure:

    Request:
        {"pagination": {"cursor": null, "page_size": 20}, ...}

    Response:
        {"<resource_key>": {"page_info": {"cursor": "...", "page_size": 20}, "data": [...]}}

    Fetches all pages sequentially, combining results into a single list.
    Stops when cursor is null or max_pages reached.
    """

    def __init__(self, max_pages: int = 20, page_size: int = 50) -> None:
        self._max_pages = max_pages
        self._page_size = page_size

    def fetch_all(
        self,
        request_fn: Callable[[dict], dict[str, Any]],
        base_body: dict,
        response_key: str,
        metrics: RequestMetrics | None = None,
    ) -> tuple[list[dict], bool]:
        """Fetch all pages. Returns (combined_results, was_truncated).

        Args:
            request_fn: Function that takes a request body dict and returns
                the raw API response.
            base_body: Base request body (filters, include, etc). The pagination
                object will be added/updated automatically.
            response_key: The top-level key in the response containing the
                paginated data (e.g., "notes", "recordings", "action_items").
            metrics: Optional RequestMetrics to track page numbers on
                UpstreamCallRecord entries.

        Returns:
            Tuple of (all_results, was_truncated). was_truncated is True if
            pagination stopped due to max_pages limit rather than a null cursor.

        Raises:
            PaginationError: If a request fails mid-pagination (includes page number).
        """
        combined_results: list[dict] = []
        cursor: str | None = None
        was_truncated = False

        for page_number in range(1, self._max_pages + 1):
            # Build the request body with pagination nested correctly
            body = {**base_body}
            body["pagination"] = {
                "cursor": cursor,
                "page_size": self._page_size,
            }

            try:
                response = request_fn(body)
            except Exception as exc:
                # On failure, update the page number on any record that was
                # added by the request_fn (e.g., timeout records)
                if metrics is not None and metrics.upstream_api_calls:
                    last_record = metrics.upstream_api_calls[-1]
                    last_record.page = page_number

                # Propagate the HTTP status code to metrics
                if metrics is not None:
                    if isinstance(exc, FellowApiError):
                        metrics.upstream_status_code = exc.status_code
                    elif isinstance(exc, TransientApiError):
                        metrics.upstream_status_code = exc.status_code
                    elif metrics.upstream_api_calls:
                        last_status = metrics.upstream_api_calls[-1].status_code
                        if last_status != 0:
                            metrics.upstream_status_code = last_status

                raise PaginationError(page_number, exc) from exc

            # After a successful call, set the correct page number on the
            # most recently added UpstreamCallRecord
            if metrics is not None and metrics.upstream_api_calls:
                last_record = metrics.upstream_api_calls[-1]
                last_record.page = page_number

            # Extract data from the nested response structure
            resource_data = response.get(response_key, {})
            results = resource_data.get("data", [])
            page_info = resource_data.get("page_info", {})

            combined_results.extend(results)

            cursor = page_info.get("cursor")
            if cursor is None:
                # No more pages - pagination complete
                break
        else:
            # Loop completed without break: hit max_pages with a non-null cursor
            was_truncated = True

        return combined_results, was_truncated
