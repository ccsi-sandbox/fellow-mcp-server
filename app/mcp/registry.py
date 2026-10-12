"""Tool definitions registry for MCP tool routing."""

from typing import Any, Callable


class ToolNotFoundError(Exception):
    """Raised when tools/call references an unknown tool name."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Unknown tool: {tool_name}")


class ToolRegistry:
    """Maps tool names to handler functions and stores tool definitions.

    The registry stores both the tool metadata (name, description, inputSchema,
    annotations) used for tools/list responses, and the handler callables used
    for tools/call dispatch.
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
        annotations: dict[str, Any] | None = None,
    ) -> None:
        """Register a tool with its definition and handler.

        Args:
            name: Unique tool name used for routing.
            description: Human-readable description of the tool.
            input_schema: JSON Schema dict describing the tool's input parameters.
            handler: Callable that executes the tool logic.
            annotations: Optional MCP tool annotations (``title``,
                ``readOnlyHint``, ``destructiveHint``, ``idempotentHint``,
                ``openWorldHint``). Clients use these to tell reads from writes
                when applying allow-lists and approval policy. Omitting them
                makes a client fall back on the specification's conservative
                defaults (not read-only, destructive), so production tools
                should always supply them -- see ``app.mcp.definitions``.
        """
        definition: dict[str, Any] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }
        if annotations:
            # Copy so a later mutation of the caller's dict cannot change what
            # has already been advertised to clients.
            definition["annotations"] = dict(annotations)
        self._tools[name] = definition
        self._handlers[name] = handler

    def get_annotations(self, name: str) -> dict[str, Any]:
        """Return the annotations advertised for a tool.

        Args:
            name: The tool name to look up.

        Returns:
            The tool's annotations dict, or an empty dict if it has none.

        Raises:
            ToolNotFoundError: If the tool name is not registered.
        """
        if name not in self._tools:
            raise ToolNotFoundError(name)
        return dict(self._tools[name].get("annotations", {}))

    def is_read_only(self, name: str) -> bool:
        """Report whether a tool is advertised as read-only.

        Follows the MCP default: a tool with no ``readOnlyHint`` is NOT
        read-only.

        Args:
            name: The tool name to look up.

        Returns:
            True only when the tool explicitly advertises ``readOnlyHint``.

        Raises:
            ToolNotFoundError: If the tool name is not registered.
        """
        return bool(self.get_annotations(name).get("readOnlyHint", False))

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
            and inputSchema keys, plus an annotations key for every tool
            registered with annotations.
        """
        return list(self._tools.values())
