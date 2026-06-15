"""Unit tests for the structlog configuration and request ID binding."""

import json
import logging
import uuid

import pytest
import structlog

from app.logging.setup import bind_request_id, configure_logging


@pytest.mark.unit
class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_configures_json_output(self, capsys):
        """Verify structlog produces JSON-formatted output after configuration."""
        configure_logging("INFO")
        logger = structlog.get_logger()
        logger.info("test_message", key="value")

        captured = capsys.readouterr()
        entry = json.loads(captured.err)
        assert entry["event"] == "test_message"
        assert entry["key"] == "value"

    def test_sets_log_level_debug(self):
        """Verify DEBUG level is applied to the root logger."""
        configure_logging("DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_sets_log_level_warning(self):
        """Verify WARNING level is applied to the root logger."""
        configure_logging("WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_sets_log_level_error(self):
        """Verify ERROR level is applied to the root logger."""
        configure_logging("ERROR")
        assert logging.getLogger().level == logging.ERROR

    def test_sets_log_level_critical(self):
        """Verify CRITICAL level is applied to the root logger."""
        configure_logging("CRITICAL")
        assert logging.getLogger().level == logging.CRITICAL

    def test_invalid_log_level_defaults_to_info(self):
        """Verify invalid log level falls back to INFO."""
        configure_logging("INVALID")
        assert logging.getLogger().level == logging.INFO

    def test_empty_log_level_defaults_to_info(self):
        """Verify empty string log level falls back to INFO."""
        configure_logging("")
        assert logging.getLogger().level == logging.INFO

    def test_case_insensitive_log_level(self):
        """Verify log level parsing is case-insensitive."""
        configure_logging("debug")
        assert logging.getLogger().level == logging.DEBUG

    def test_log_entry_includes_timestamp(self, capsys):
        """Verify log entries contain an ISO timestamp."""
        configure_logging("INFO")
        logger = structlog.get_logger()
        logger.info("ts_test")

        captured = capsys.readouterr()
        entry = json.loads(captured.err)
        assert "timestamp" in entry

    def test_log_entry_includes_level(self, capsys):
        """Verify log entries contain the log level field."""
        configure_logging("INFO")
        logger = structlog.get_logger()
        logger.info("level_test")

        captured = capsys.readouterr()
        entry = json.loads(captured.err)
        assert entry["level"] == "info"


@pytest.mark.unit
class TestBindRequestId:
    """Tests for bind_request_id function."""

    @pytest.fixture
    def logging_app(self):
        """Create a minimal Flask app with logging configured."""
        from flask import Flask

        app = Flask(__name__)
        configure_logging("INFO")
        bind_request_id(app)

        @app.route("/test")
        def test_route():
            from flask import g, jsonify

            logger = structlog.get_logger()
            logger.info("inside_request")
            return jsonify({"request_id": g.request_id})

        return app

    def test_request_id_bound_to_flask_g(self, logging_app):
        """Verify request_id is stored in Flask's g object."""
        with logging_app.test_client() as client:
            resp = client.get("/test")
            data = resp.get_json()
            assert "request_id" in data
            # Validate it's a valid UUID4
            uuid.UUID(data["request_id"], version=4)

    def test_request_id_is_unique_per_request(self, logging_app):
        """Verify each request gets a unique request_id."""
        with logging_app.test_client() as client:
            resp1 = client.get("/test")
            resp2 = client.get("/test")
            id1 = resp1.get_json()["request_id"]
            id2 = resp2.get_json()["request_id"]
            assert id1 != id2

    def test_request_id_in_log_entries(self, logging_app, caplog):
        """Verify request_id appears in log entries within a request."""
        with caplog.at_level(logging.INFO):
            with logging_app.test_client() as client:
                client.get("/test")

        # pytest caplog captures the formatted message (which is JSON)
        found = False
        for record in caplog.records:
            msg = record.getMessage()
            try:
                entry = json.loads(msg)
                if entry.get("event") == "inside_request":
                    assert "request_id" in entry
                    uuid.UUID(entry["request_id"], version=4)
                    found = True
                    break
            except (json.JSONDecodeError, ValueError):
                continue
        assert found, "Expected 'inside_request' log entry with request_id not found"
