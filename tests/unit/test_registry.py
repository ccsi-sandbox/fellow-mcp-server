"""Unit tests for MCP tool registry."""

import pytest

from app.mcp.registry import ToolNotFoundError, ToolRegistry


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def test_register_and_get_handler(self):
        """Register a tool and get_handler returns its handler."""
        registry = ToolRegistry()

        def my_handler(args):
            return {"result": "ok"}

        registry.register(
            name="my_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
            handler=my_handler,
        )

        handler = registry.get_handler("my_tool")
        assert handler is my_handler
        assert handler({"foo": "bar"}) == {"result": "ok"}

    def test_register_multiple_tools_and_list_returns_all(self):
        """Register multiple tools and list_tools returns all definitions."""
        registry = ToolRegistry()

        def handler_a(args):
            return "a"

        def handler_b(args):
            return "b"

        def handler_c(args):
            return "c"

        registry.register(
            name="tool_a",
            description="Tool A description",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
            handler=handler_a,
        )
        registry.register(
            name="tool_b",
            description="Tool B description",
            input_schema={"type": "object", "properties": {}},
            handler=handler_b,
        )
        registry.register(
            name="tool_c",
            description="Tool C description",
            input_schema={"type": "object", "properties": {"id": {"type": "string"}}},
            handler=handler_c,
        )

        tools = registry.list_tools()
        assert len(tools) == 3

        tool_names = [t["name"] for t in tools]
        assert "tool_a" in tool_names
        assert "tool_b" in tool_names
        assert "tool_c" in tool_names

    def test_get_handler_unknown_tool_raises_tool_not_found_error(self):
        """get_handler for unknown tool raises ToolNotFoundError."""
        registry = ToolRegistry()

        with pytest.raises(ToolNotFoundError) as exc_info:
            registry.get_handler("nonexistent_tool")

        assert exc_info.value.tool_name == "nonexistent_tool"
        assert "nonexistent_tool" in str(exc_info.value)

    def test_list_tools_returns_proper_format(self):
        """list_tools returns entries with name, description, and inputSchema."""
        registry = ToolRegistry()

        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "The item ID"},
            },
            "required": ["id"],
        }

        registry.register(
            name="get_action_item",
            description="Get an action item by ID",
            input_schema=schema,
            handler=lambda args: args,
        )

        tools = registry.list_tools()
        assert len(tools) == 1

        tool = tools[0]
        assert tool["name"] == "get_action_item"
        assert tool["description"] == "Get an action item by ID"
        assert tool["inputSchema"] == schema

    def test_list_tools_empty_registry(self):
        """list_tools on empty registry returns empty list."""
        registry = ToolRegistry()
        assert registry.list_tools() == []

    def test_register_overwrites_existing_tool(self):
        """Registering a tool with the same name overwrites the previous one."""
        registry = ToolRegistry()

        def handler_v1(args):
            return "v1"

        def handler_v2(args):
            return "v2"

        registry.register(
            name="my_tool",
            description="Version 1",
            input_schema={"type": "object"},
            handler=handler_v1,
        )
        registry.register(
            name="my_tool",
            description="Version 2",
            input_schema={"type": "object", "properties": {"x": {"type": "int"}}},
            handler=handler_v2,
        )

        handler = registry.get_handler("my_tool")
        assert handler is handler_v2

        tools = registry.list_tools()
        assert len(tools) == 1
        assert tools[0]["description"] == "Version 2"


class TestToolNotFoundError:
    """Tests for ToolNotFoundError exception."""

    def test_error_stores_tool_name(self):
        """ToolNotFoundError stores the tool name."""
        error = ToolNotFoundError("bad_tool")
        assert error.tool_name == "bad_tool"

    def test_error_message_contains_tool_name(self):
        """ToolNotFoundError message includes the tool name."""
        error = ToolNotFoundError("missing_tool")
        assert "missing_tool" in str(error)

    def test_error_code_maps_to_invalid_params(self):
        """ToolNotFoundError should be caught and mapped to -32602 by the protocol layer."""
        # This test documents the expected usage pattern: the protocol handler
        # catches ToolNotFoundError and returns a JSON-RPC error with code -32602
        from app.mcp.errors import INVALID_PARAMS

        error = ToolNotFoundError("unknown_tool")
        # The error itself doesn't carry a code, but the message is used
        # to build a -32602 response
        assert INVALID_PARAMS == -32602
        assert "unknown_tool" in str(error)
