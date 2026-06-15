"""Unit tests for the CursorPaginator."""

import pytest

from app.client.paginator import CursorPaginator, PaginationError


class TestCursorPaginatorFetchAll:
    """Tests for CursorPaginator.fetch_all()."""

    def test_single_page_no_cursor(self):
        """Single page with null cursor returns results, not truncated."""
        responses = [{"results": [{"id": "1"}, {"id": "2"}], "cursor": None}]
        call_count = {"n": 0}

        def request_fn(params):
            call_count["n"] += 1
            return responses.pop(0)

        paginator = CursorPaginator(max_pages=20, page_size=50)
        results, was_truncated = paginator.fetch_all(request_fn, {})

        assert results == [{"id": "1"}, {"id": "2"}]
        assert was_truncated is False
        assert call_count["n"] == 1

    def test_multiple_pages_until_null_cursor(self):
        """Multiple pages fetched until cursor becomes null."""
        responses = [
            {"results": [{"id": "1"}], "cursor": "cursor_a"},
            {"results": [{"id": "2"}], "cursor": "cursor_b"},
            {"results": [{"id": "3"}], "cursor": None},
        ]

        def request_fn(params):
            return responses.pop(0)

        paginator = CursorPaginator(max_pages=20, page_size=50)
        results, was_truncated = paginator.fetch_all(request_fn, {})

        assert results == [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        assert was_truncated is False

    def test_results_combined_in_page_order(self):
        """Results from multiple pages are concatenated in order."""
        responses = [
            {"results": [{"id": "a"}, {"id": "b"}], "cursor": "next"},
            {"results": [{"id": "c"}, {"id": "d"}], "cursor": None},
        ]

        def request_fn(params):
            return responses.pop(0)

        paginator = CursorPaginator(max_pages=20, page_size=50)
        results, _ = paginator.fetch_all(request_fn, {})

        assert results == [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]

    def test_stops_at_max_pages_with_truncation(self):
        """Stops at max_pages and sets was_truncated=True."""
        page_count = {"n": 0}

        def request_fn(params):
            page_count["n"] += 1
            return {"results": [{"id": str(page_count["n"])}], "cursor": "more"}

        paginator = CursorPaginator(max_pages=3, page_size=50)
        results, was_truncated = paginator.fetch_all(request_fn, {})

        assert len(results) == 3
        assert was_truncated is True
        assert page_count["n"] == 3

    def test_default_max_pages_is_20(self):
        """Default max_pages is 20."""
        paginator = CursorPaginator()
        assert paginator._max_pages == 20

    def test_default_page_size_is_50(self):
        """Default page_size is 50."""
        paginator = CursorPaginator()
        assert paginator._page_size == 50

    def test_page_size_passed_to_request_fn(self):
        """page_size is included in params to request_fn."""
        captured_params = []

        def request_fn(params):
            captured_params.append(params)
            return {"results": [], "cursor": None}

        paginator = CursorPaginator(max_pages=20, page_size=50)
        paginator.fetch_all(request_fn, {"filter": "value"})

        assert captured_params[0] == {"filter": "value", "page_size": 50}

    def test_cursor_passed_on_subsequent_pages(self):
        """Cursor from previous response is included in next request params."""
        captured_params = []
        responses = [
            {"results": [{"id": "1"}], "cursor": "abc123"},
            {"results": [{"id": "2"}], "cursor": None},
        ]

        def request_fn(params):
            captured_params.append(params.copy())
            return responses.pop(0)

        paginator = CursorPaginator(max_pages=20, page_size=50)
        paginator.fetch_all(request_fn, {"filter": "x"})

        # First request: no cursor
        assert "cursor" not in captured_params[0]
        assert captured_params[0] == {"filter": "x", "page_size": 50}

        # Second request: includes cursor
        assert captured_params[1] == {"filter": "x", "page_size": 50, "cursor": "abc123"}

    def test_empty_results_with_null_cursor(self):
        """Handles empty results on first page gracefully."""

        def request_fn(params):
            return {"results": [], "cursor": None}

        paginator = CursorPaginator(max_pages=20, page_size=50)
        results, was_truncated = paginator.fetch_all(request_fn, {})

        assert results == []
        assert was_truncated is False

    def test_first_page_failure_raises_pagination_error(self):
        """Exception on first page raises PaginationError with page_number=1."""

        def request_fn(params):
            raise RuntimeError("connection failed")

        paginator = CursorPaginator(max_pages=20, page_size=50)

        with pytest.raises(PaginationError) as exc_info:
            paginator.fetch_all(request_fn, {})

        assert exc_info.value.page_number == 1
        assert isinstance(exc_info.value.cause, RuntimeError)
        assert "connection failed" in str(exc_info.value.cause)

    def test_mid_pagination_failure_raises_pagination_error(self):
        """Exception on page 3 raises PaginationError with page_number=3, discards results."""
        call_count = {"n": 0}

        def request_fn(params):
            call_count["n"] += 1
            if call_count["n"] == 3:
                raise ValueError("server error")
            return {"results": [{"id": str(call_count["n"])}], "cursor": "next"}

        paginator = CursorPaginator(max_pages=20, page_size=50)

        with pytest.raises(PaginationError) as exc_info:
            paginator.fetch_all(request_fn, {})

        assert exc_info.value.page_number == 3
        assert isinstance(exc_info.value.cause, ValueError)

    def test_pagination_error_discards_partial_results(self):
        """On failure, no partial results are returned (exception raised instead)."""
        call_count = {"n": 0}

        def request_fn(params):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("boom")
            return {"results": [{"id": "item"}], "cursor": "next"}

        paginator = CursorPaginator(max_pages=20, page_size=50)

        with pytest.raises(PaginationError):
            paginator.fetch_all(request_fn, {})
        # Results are discarded — caller gets no partial data

    def test_base_params_not_mutated(self):
        """Original base_params dict is not modified."""
        base_params = {"filter": "active"}
        original = base_params.copy()

        def request_fn(params):
            return {"results": [], "cursor": None}

        paginator = CursorPaginator(max_pages=20, page_size=50)
        paginator.fetch_all(request_fn, base_params)

        assert base_params == original

    def test_max_pages_exactly_reached_then_null_cursor(self):
        """If the last allowed page returns null cursor, was_truncated is False."""
        call_count = {"n": 0}

        def request_fn(params):
            call_count["n"] += 1
            if call_count["n"] < 3:
                return {"results": [{"id": str(call_count["n"])}], "cursor": "more"}
            return {"results": [{"id": "3"}], "cursor": None}

        paginator = CursorPaginator(max_pages=3, page_size=50)
        results, was_truncated = paginator.fetch_all(request_fn, {})

        assert len(results) == 3
        assert was_truncated is False

    def test_custom_page_size(self):
        """Custom page_size is passed to request_fn."""
        captured_params = []

        def request_fn(params):
            captured_params.append(params)
            return {"results": [], "cursor": None}

        paginator = CursorPaginator(max_pages=5, page_size=25)
        paginator.fetch_all(request_fn, {})

        assert captured_params[0]["page_size"] == 25
