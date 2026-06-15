"""MCP/JSON-RPC error codes and exception classes."""

# JSON-RPC 2.0 standard error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcParseError(Exception):
    """Raised when JSON cannot be parsed from the request body."""

    def __init__(self, message: str = "Parse error: invalid JSON") -> None:
        self.code = PARSE_ERROR
        self.message = message
        super().__init__(message)


class JsonRpcInvalidRequest(Exception):
    """Raised when required JSON-RPC 2.0 fields are missing or invalid."""

    def __init__(self, message: str = "Invalid request") -> None:
        self.code = INVALID_REQUEST
        self.message = message
        super().__init__(message)
