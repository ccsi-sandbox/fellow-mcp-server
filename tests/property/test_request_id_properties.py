"""Property-based tests for request ID correlation in structured logging.

# Feature: fellow-mcp-server, Property 12: Request ID correlates all log entries

Validates: Requirements 10.7

Property Statement:
For any request processed by the server, all structlog entries emitted during
that request SHALL contain the same request_id field value, and that value SHALL
be unique across concurrent requests.
"""

import json
import logging

import pytest
import structlog
from flask import Flask, jsonify
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.logging.setup import bind_request_id, configure_logging


def _create_logging_app():
    """Create a Flask app with structured logging and request_id binding."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    configure_logging("DEBUG")
    bind_request_id(app)
    return app


@pytest.mark.property
class TestRequestIdCorrelation:
    """Property 12: Request ID correlates all log entries."""

    @settings(max_examples=100)
    @given(num_log_calls=st.integers(min_value=1, max_value=20))
    def test_all_log_entries_share_same_request_id(self, num_log_calls):
        """For any request emitting N log entries, all entries SHALL contain
        the same request_id field value.

        **Validates: Requirements 10.7**
        """
        app = _create_logging_app()

        # Dynamically create an endpoint that emits num_log_calls log entries
        @app.route("/test_logging")
        def test_endpoint():
            logger = structlog.get_logger()
            for i in range(num_log_calls):
                logger.info("log_entry", index=i)
            return jsonify({"ok": True})

        # Set up a logging handler to capture structured log output
        captured_records = []
        handler = logging.Handler()
        handler.emit = lambda record: captured_records.append(record)
        logging.getLogger().addHandler(handler)

        try:
            with app.test_client() as client:
                client.get("/test_logging")

            # Parse captured log entries and extract request_ids
            request_ids = set()
            matching_entries = 0
            for record in captured_records:
                try:
                    msg = record.getMessage()
                    entry = json.loads(msg)
                    if entry.get("event") == "log_entry":
                        assert "request_id" in entry, (
                            f"Log entry missing request_id: {entry}"
                        )
                        request_ids.add(entry["request_id"])
                        matching_entries += 1
                except (json.JSONDecodeError, ValueError):
                    continue

            # All log entries from the request must have been captured
            assert matching_entries == num_log_calls, (
                f"Expected {num_log_calls} log entries, found {matching_entries}"
            )

            # All entries must share the same request_id
            assert len(request_ids) == 1, (
                f"Expected 1 unique request_id, found {len(request_ids)}: {request_ids}"
            )
        finally:
            logging.getLogger().removeHandler(handler)

    @settings(max_examples=100)
    @given(num_requests=st.integers(min_value=2, max_value=10))
    def test_different_requests_get_unique_request_ids(self, num_requests):
        """For any N requests processed by the server, each request SHALL
        receive a unique request_id value.

        **Validates: Requirements 10.7**
        """
        app = _create_logging_app()

        @app.route("/test_unique")
        def test_endpoint():
            logger = structlog.get_logger()
            logger.info("request_marker")
            return jsonify({"ok": True})

        captured_records = []
        handler = logging.Handler()
        handler.emit = lambda record: captured_records.append(record)
        logging.getLogger().addHandler(handler)

        try:
            with app.test_client() as client:
                for _ in range(num_requests):
                    client.get("/test_unique")

            # Extract request_ids from all marker entries
            request_ids = []
            for record in captured_records:
                try:
                    msg = record.getMessage()
                    entry = json.loads(msg)
                    if entry.get("event") == "request_marker":
                        assert "request_id" in entry, (
                            f"Log entry missing request_id: {entry}"
                        )
                        request_ids.append(entry["request_id"])
                except (json.JSONDecodeError, ValueError):
                    continue

            # Must have captured one marker per request
            assert len(request_ids) == num_requests, (
                f"Expected {num_requests} markers, found {len(request_ids)}"
            )

            # All request_ids must be unique
            unique_ids = set(request_ids)
            assert len(unique_ids) == num_requests, (
                f"Expected {num_requests} unique request_ids, "
                f"found {len(unique_ids)}: {request_ids}"
            )
        finally:
            logging.getLogger().removeHandler(handler)

    @settings(max_examples=100)
    @given(
        num_log_calls=st.integers(min_value=1, max_value=10),
        num_requests=st.integers(min_value=2, max_value=5),
    )
    def test_request_ids_correlate_within_and_isolate_across(
        self, num_log_calls, num_requests
    ):
        """For any sequence of requests each emitting N log entries, entries
        within a single request SHALL share one request_id, and entries across
        different requests SHALL have different request_ids.

        **Validates: Requirements 10.7**
        """
        app = _create_logging_app()

        @app.route("/test_combined")
        def test_endpoint():
            logger = structlog.get_logger()
            for i in range(num_log_calls):
                logger.info("combined_marker", index=i)
            return jsonify({"ok": True})

        captured_records = []
        handler = logging.Handler()
        handler.emit = lambda record: captured_records.append(record)
        logging.getLogger().addHandler(handler)

        try:
            with app.test_client() as client:
                for _ in range(num_requests):
                    client.get("/test_combined")

            # Group entries by request_id
            entries_by_request_id = {}
            for record in captured_records:
                try:
                    msg = record.getMessage()
                    entry = json.loads(msg)
                    if entry.get("event") == "combined_marker":
                        rid = entry.get("request_id")
                        assert rid is not None, (
                            f"Log entry missing request_id: {entry}"
                        )
                        entries_by_request_id.setdefault(rid, []).append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue

            # There should be exactly num_requests distinct request_ids
            assert len(entries_by_request_id) == num_requests, (
                f"Expected {num_requests} distinct request_ids, "
                f"found {len(entries_by_request_id)}"
            )

            # Each request_id should have exactly num_log_calls entries
            for rid, entries in entries_by_request_id.items():
                assert len(entries) == num_log_calls, (
                    f"Request {rid}: expected {num_log_calls} entries, "
                    f"found {len(entries)}"
                )
        finally:
            logging.getLogger().removeHandler(handler)
