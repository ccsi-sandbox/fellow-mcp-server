"""Tool definitions registry for MCP tool routing."""

from typing import Any, Callable


class ToolNotFoundError(Exception):
    """Raised when tools/call references an unknown tool name."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Unknown tool: {tool_name}")


class ToolRegistry:
    """Maps tool names to handler functions and stores tool definitions.

    The registry stores both the tool metadata (name, description, inputSchema)
    used for tools/list responses, and the handler callables used for tools/call
    dispatch.
    """

    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}  # name -> definition
        self._handlers: dict[str, Callable] = {}  # name -> handler func

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: Callable,
    ) -> None:
        """Register a tool with its definition and handler.

        Args:
            name: Unique tool name used for routing.
            description: Human-readable description of the tool.
            input_schema: JSON Schema dict describing the tool's input parameters.
            handler: Callable that executes the tool logic.
        """
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }
        self._handlers[name] = handler

    def get_handler(self, name: str) -> Callable:
        """Get handler for a tool name.

        Args:
            name: The tool name to look up.

        Returns:
            The handler callable for the given tool name.

        Raises:
            ToolNotFoundError: If the tool name is not registered.
        """
        if name not in self._handlers:
            raise ToolNotFoundError(name)
        return self._handlers[name]

    def list_tools(self) -> list[dict]:
        """Return all tool definitions for tools/list response.

        Returns:
            List of tool definition dicts, each containing name, description,
            and inputSchema keys.
        """
        return list(self._tools.values())
