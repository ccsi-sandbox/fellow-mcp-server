"""Property-based tests for cursor pagination.

# Feature: fellow-mcp-server, Property 10: Pagination combines results in order and terminates correctly
# Feature: fellow-mcp-server, Property 11: Mid-pagination failure discards partial results

Property 10: For any sequence of Fellow API paginated responses where pages 1
through K-1 have non-null cursors and page K has a null cursor (or K equals the
max page limit of 20), the paginator SHALL: (a) make exactly K requests,
(b) return results as the ordered concatenation of all pages (first page first,
last page last), (c) include a truncation indicator if and only if stopped by
page limit rather than null cursor.

Property 11: For any pagination sequence where page K fails (K > 1, after K-1
successful pages), the paginator SHALL discard all previously retrieved results
and return an error indicating which page number failed.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.client.paginator import CursorPaginator, PaginationError


# --- Strategies ---

# Random page count (1-25, capped at max_pages during test)
page_counts = st.integers(min_value=1, max_value=25)

# Random page sizes (0-50 items per page)
page_item_counts = st.integers(min_value=0, max_value=50)


def page_items_strategy(num_pages: int):
    """Generate a list of lists, where each inner list represents page items."""
    return st.lists(
        st.integers(min_value=0, max_value=50),
        min_size=num_pages,
        max_size=num_pages,
    )


# --- Helpers ---


def make_mock_request_fn(pages: list[list[dict]], max_pages: int = 20):
    """Create a mock request function that returns paginated responses.

    Args:
        pages: List of page results. Each element is a list of result dicts.
        max_pages: The max page limit used by the paginator.

    Returns:
        A callable that simulates the Fellow API pagination behavior.
    """
    call_count = {"value": 0}

    def request_fn(params: dict) -> dict:
        page_idx = call_count["value"]
        call_count["value"] += 1

        results = pages[page_idx]
        # Pages 1 to K-1 have non-null cursor; page K has null cursor
        is_last_page = page_idx == len(pages) - 1
        cursor = None if is_last_page else f"cursor-page-{page_idx + 2}"

        return {"results": results, "cursor": cursor}

    return request_fn, call_count


def make_failing_request_fn(
    pages: list[list[dict]], fail_on_page: int, error_msg: str = "API Error"
):
    """Create a mock request function that fails on a specific page.

    Args:
        pages: List of page results for successful pages.
        fail_on_page: 1-based page number to fail on.
        error_msg: Error message for the raised exception.

    Returns:
        A callable that simulates pagination with a mid-pagination failure.
    """
    call_count = {"value": 0}

    def request_fn(params: dict) -> dict:
        page_idx = call_count["value"]
        call_count["value"] += 1

        # 1-based page number
        page_number = page_idx + 1

        if page_number == fail_on_page:
            raise RuntimeError(error_msg)

        results = pages[page_idx]
        is_last_page = page_idx == len(pages) - 1
        cursor = None if is_last_page else f"cursor-page-{page_idx + 2}"

        return {"results": results, "cursor": cursor}

    return request_fn, call_count


# --- Property Tests ---


@pytest.mark.property
class TestPaginationCombinesResultsProperty:
    """Property 10: Pagination combines results in order and terminates correctly.

    **Validates: Requirements 12.1, 12.2, 12.4, 12.5**
    """

    @given(
        num_pages=st.integers(min_value=1, max_value=20),
        items_per_page=st.lists(
            st.integers(min_value=0, max_value=50),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_pagination_makes_exactly_k_requests_and_combines_in_order(
        self, num_pages, items_per_page
    ):
        """For K pages where pages 1..K-1 have non-null cursors and page K has
        null cursor, the paginator makes exactly K requests and returns results
        concatenated in page order.

        **Validates: Requirements 12.1, 12.2**
        """
        # Adjust items_per_page to match num_pages
        while len(items_per_page) < num_pages:
            items_per_page.append(0)
        items_per_page = items_per_page[:num_pages]

        # Build pages with identifiable items
        pages: list[list[dict]] = []
        for page_idx, item_count in enumerate(items_per_page):
            page_results = [
                {"page": page_idx, "item": i} for i in range(item_count)
            ]
            pages.append(page_results)

        request_fn, call_count = make_mock_request_fn(pages, max_pages=20)
        paginator = CursorPaginator(max_pages=20, page_size=50)

        results, was_truncated = paginator.fetch_all(request_fn, {})

        # (a) Exactly K requests made
        assert call_count["value"] == num_pages

        # (b) Results concatenated in page order
        expected_results = []
        for page in pages:
            expected_results.extend(page)
        assert results == expected_results

        # (c) Not truncated since we stopped by null cursor (num_pages <= 20)
        assert was_truncated is False

    @given(
        items_per_page=st.lists(
            st.integers(min_value=0, max_value=50),
            min_size=20,
            max_size=20,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_pagination_truncates_at_max_page_limit(self, items_per_page):
        """When K equals max_pages and cursor is still non-null, the paginator
        stops and sets was_truncated to True.

        **Validates: Requirements 12.4, 12.5**
        """
        max_pages = 20

        # Build pages with identifiable items - all pages have non-null cursors
        pages: list[list[dict]] = []
        for page_idx, item_count in enumerate(items_per_page):
            page_results = [
                {"page": page_idx, "item": i} for i in range(item_count)
            ]
            pages.append(page_results)

        call_count = {"value": 0}

        def request_fn(params: dict) -> dict:
            page_idx = call_count["value"]
            call_count["value"] += 1
            results = pages[page_idx]
            # ALL pages return non-null cursor (simulating more pages exist)
            cursor = f"cursor-page-{page_idx + 2}"
            return {"results": results, "cursor": cursor}

        paginator = CursorPaginator(max_pages=max_pages, page_size=50)

        results, was_truncated = paginator.fetch_all(request_fn, {})

        # (a) Exactly max_pages requests made
        assert call_count["value"] == max_pages

        # (b) Results concatenated in page order
        expected_results = []
        for page in pages:
            expected_results.extend(page)
        assert results == expected_results

        # (c) Truncated since stopped by page limit, not null cursor
        assert was_truncated is True

    @given(
        num_pages=st.integers(min_value=1, max_value=25),
        items_per_page=st.lists(
            st.integers(min_value=0, max_value=50),
            min_size=1,
            max_size=25,
        ),
        max_pages=st.integers(min_value=1, max_value=25),
    )
    @settings(max_examples=100, deadline=None)
    def test_truncation_flag_correct_for_various_max_pages(
        self, num_pages, items_per_page, max_pages
    ):
        """Truncation indicator is set if and only if stopped by page limit
        rather than null cursor, across various max_pages configurations.

        **Validates: Requirements 12.4, 12.5**
        """
        # Adjust items_per_page to match num_pages
        while len(items_per_page) < num_pages:
            items_per_page.append(0)
        items_per_page = items_per_page[:num_pages]

        # Build pages
        pages: list[list[dict]] = []
        for page_idx, item_count in enumerate(items_per_page):
            page_results = [
                {"page": page_idx, "item": i} for i in range(item_count)
            ]
            pages.append(page_results)

        call_count = {"value": 0}

        def request_fn(params: dict) -> dict:
            page_idx = call_count["value"]
            call_count["value"] += 1
            results = pages[page_idx]
            # Pages 1..num_pages-1 have cursor, page num_pages has null
            is_last_page = page_idx == num_pages - 1
            cursor = None if is_last_page else f"cursor-page-{page_idx + 2}"
            return {"results": results, "cursor": cursor}

        paginator = CursorPaginator(max_pages=max_pages, page_size=50)
        results, was_truncated = paginator.fetch_all(request_fn, {})

        # How many pages actually fetched
        actual_pages_fetched = min(num_pages, max_pages)
        assert call_count["value"] == actual_pages_fetched

        # Results are from fetched pages in order
        expected_results = []
        for page in pages[:actual_pages_fetched]:
            expected_results.extend(page)
        assert results == expected_results

        # Truncation: True iff we hit max_pages before reaching null cursor
        if num_pages <= max_pages:
            # We reached null cursor naturally
            assert was_truncated is False
        else:
            # We hit max_pages limit before null cursor
            assert was_truncated is True


@pytest.mark.property
class TestMidPaginationFailureProperty:
    """Property 11: Mid-pagination failure discards partial results.

    **Validates: Requirements 12.6**
    """

    @given(
        total_pages=st.integers(min_value=2, max_value=20),
        fail_page=st.integers(min_value=2, max_value=20),
        items_per_page=st.lists(
            st.integers(min_value=0, max_value=50),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_mid_pagination_failure_raises_pagination_error(
        self, total_pages, fail_page, items_per_page
    ):
        """For a pagination sequence where page K fails (K > 1), the paginator
        raises PaginationError with the correct page_number and discards all
        partial results.

        **Validates: Requirements 12.6**
        """
        # Ensure fail_page is within the total_pages range
        fail_page = min(fail_page, total_pages)
        if fail_page < 2:
            fail_page = 2

        # Adjust items_per_page to match total_pages
        while len(items_per_page) < total_pages:
            items_per_page.append(0)
        items_per_page = items_per_page[:total_pages]

        # Build pages for successful responses (before the failing page)
        pages: list[list[dict]] = []
        for page_idx, item_count in enumerate(items_per_page):
            page_results = [
                {"page": page_idx, "item": i} for i in range(item_count)
            ]
            pages.append(page_results)

        error_msg = f"Simulated failure on page {fail_page}"
        request_fn, call_count = make_failing_request_fn(
            pages, fail_on_page=fail_page, error_msg=error_msg
        )

        paginator = CursorPaginator(max_pages=20, page_size=50)

        with pytest.raises(PaginationError) as exc_info:
            paginator.fetch_all(request_fn, {})

        # PaginationError should report the correct page number
        assert exc_info.value.page_number == fail_page

        # The cause should be the original RuntimeError
        assert isinstance(exc_info.value.cause, RuntimeError)
        assert str(exc_info.value.cause) == error_msg

        # Exactly fail_page requests were made (up to and including the failing one)
        assert call_count["value"] == fail_page

    @given(
        total_pages=st.integers(min_value=3, max_value=15),
        items_per_page=st.lists(
            st.integers(min_value=1, max_value=30),
            min_size=3,
            max_size=15,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_partial_results_not_returned_on_failure(
        self, total_pages, items_per_page
    ):
        """When a mid-pagination failure occurs, partial results from
        successful pages are discarded - the caller only gets the error.

        **Validates: Requirements 12.6**
        """
        # Adjust items_per_page to match total_pages
        while len(items_per_page) < total_pages:
            items_per_page.append(1)
        items_per_page = items_per_page[:total_pages]

        # Fail on the last page to maximize partial results that must be discarded
        fail_page = total_pages

        # Build pages
        pages: list[list[dict]] = []
        for page_idx, item_count in enumerate(items_per_page):
            page_results = [
                {"page": page_idx, "item": i} for i in range(item_count)
            ]
            pages.append(page_results)

        request_fn, _ = make_failing_request_fn(
            pages, fail_on_page=fail_page, error_msg="Connection timeout"
        )

        paginator = CursorPaginator(max_pages=20, page_size=50)

        # The only outcome is an exception - no partial results are accessible
        with pytest.raises(PaginationError) as exc_info:
            paginator.fetch_all(request_fn, {})

        assert exc_info.value.page_number == fail_page
        # Partial results are discarded (exception is the only return path)
        # The caller cannot access any previously retrieved results
