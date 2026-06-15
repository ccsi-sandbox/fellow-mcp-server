"""Cursor-based pagination for Fellow.ai API list endpoints."""

from typing import Any, Callable


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

    Fetches all pages sequentially, combining results into a single list.
    Stops when cursor is null or max_pages reached.
    """

    def __init__(self, max_pages: int = 20, page_size: int = 50) -> None:
        self._max_pages = max_pages
        self._page_size = page_size

    def fetch_all(
        self,
        request_fn: Callable[[dict], dict[str, Any]],
        base_params: dict,
    ) -> tuple[list[dict], bool]:
        """Fetch all pages. Returns (combined_results, was_truncated).

        Args:
            request_fn: Function that takes params dict and returns API response.
                The response must have 'results' (list) and 'cursor' (str or None).
            base_params: Base request parameters (filters, etc).

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
            params = {**base_params, "page_size": self._page_size}
            if cursor is not None:
                params["cursor"] = cursor

            try:
                response = request_fn(params)
            except Exception as exc:
                raise PaginationError(page_number, exc) from exc

            results = response.get("results", [])
            combined_results.extend(results)

            cursor = response.get("cursor")
            if cursor is None:
                # No more pages - pagination complete
                break
        else:
            # Loop completed without break: hit max_pages with a non-null cursor
            was_truncated = True

        return combined_results, was_truncated
