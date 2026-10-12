"""Integration tests for tool annotations over the wire.

These drive the real Flask endpoint: what a client actually receives from
``tools/list`` and ``initialize`` is what decides whether individual tools can
be allow-listed.
"""

import json

import pytest

from app.config import AppConfig
from app.main import create_app
from app.mcp.definitions import READ_ONLY_TOOLS, WRITE_TOOLS
from app.mcp.protocol import (
    ANNOTATIONS_MIN_PROTOCOL_VERSION,
    LATEST_PROTOCOL_VERSION,
)


@pytest.fixture
def client():
    config = AppConfig(
        fellow_api_key="test-api-key-12345",
        fellow_subdomain="testworkspace",
        mcp_auth_enabled=False,
        mcp_auth_token=None,
        gunicorn_workers=2,
        log_level="DEBUG",
        mcp_endpoint_path="/mcp",
        fellow_base_url="https://testworkspace.fellow.app",
    )
    app = create_app(config={"TESTING": True, "APP_CONFIG": config})
    return app.test_client()


def _post(client, payload):
    response = client.post(
        "/mcp", data=json.dumps(payload), content_type="application/json"
    )
    return json.loads(response.data)


def _list_tools(client):
    body = _post(
        client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    return {tool["name"]: tool for tool in body["result"]["tools"]}


@pytest.mark.integration
def test_tools_list_includes_annotations_for_every_tool(client):
    tools = _list_tools(client)
    assert tools, "tools/list returned no tools"
    for name, tool in tools.items():
        assert "annotations" in tool, f"{name} advertised without annotations"


@pytest.mark.integration
def test_read_only_tools_advertise_read_only_hint(client):
    tools = _list_tools(client)
    for name in READ_ONLY_TOOLS:
        annotations = tools[name]["annotations"]
        assert annotations["readOnlyHint"] is True
        assert annotations["destructiveHint"] is False


@pytest.mark.integration
def test_write_tools_advertise_not_read_only(client):
    tools = _list_tools(client)
    for name in WRITE_TOOLS:
        assert tools[name]["annotations"]["readOnlyHint"] is False


@pytest.mark.integration
def test_annotations_survive_json_serialization_as_booleans(client):
    """Hints must be JSON booleans, not strings — policy engines compare types."""
    tools = _list_tools(client)
    for name, tool in tools.items():
        for hint in (
            "readOnlyHint",
            "destructiveHint",
            "idempotentHint",
            "openWorldHint",
        ):
            value = tool["annotations"][hint]
            assert value is True or value is False, f"{name}.{hint} = {value!r}"


@pytest.mark.integration
def test_read_and_write_tools_are_both_present_over_the_wire(client):
    """Non-vacuity: the two assertions above would pass on an empty split."""
    tools = _list_tools(client)
    read_only = [
        n for n, t in tools.items() if t["annotations"]["readOnlyHint"] is True
    ]
    writes = [
        n for n, t in tools.items() if t["annotations"]["readOnlyHint"] is False
    ]
    assert len(read_only) == 9
    assert len(writes) == 7


@pytest.mark.integration
def test_initialize_defaults_to_a_version_supporting_annotations(client):
    """A client that sends no version gets one new enough to read annotations."""
    body = _post(client, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    version = body["result"]["protocolVersion"]
    assert version == LATEST_PROTOCOL_VERSION
    assert version >= ANNOTATIONS_MIN_PROTOCOL_VERSION


@pytest.mark.integration
def test_initialize_echoes_a_supported_requested_version(client):
    body = _post(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        },
    )
    assert body["result"]["protocolVersion"] == "2025-03-26"


@pytest.mark.integration
def test_initialize_falls_back_for_an_unknown_version(client):
    body = _post(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "1999-01-01"},
        },
    )
    assert body["result"]["protocolVersion"] == LATEST_PROTOCOL_VERSION
