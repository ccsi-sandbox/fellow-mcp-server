"""Single source of truth for MCP tool definitions.

Holds the tool descriptions, the MCP tool *annotations* (read-only /
destructive / idempotent / open-world hints) and the JSON Schema builder,
plus the registry factory used by BOTH transports (``app.main`` for HTTP and
``app.stdio`` for stdio). Keeping one copy is what makes a client's allow-list
trustworthy: if the two transports could drift, the same tool name could be
advertised read-only on one and unclassified on the other.

Why annotations matter
----------------------
MCP clients decide whether a tool is a read or a write from
``tool.annotations``, not from the tool's name. Per the MCP specification the
defaults for an *absent* annotations object are the conservative ones:

    readOnlyHint    default false  -> assume the tool mutates state
    destructiveHint default true   -> assume the mutation is destructive
    idempotentHint  default false
    openWorldHint   default true

So a server that omits annotations is telling every client that all 16 tools
are potentially destructive writes, which is exactly why they cannot be
allow-listed individually. Every tool below therefore carries an EXPLICIT
value for all four hints -- including the ``false`` ones -- so no consumer has
to fall back on a default, and a naive reader that looks only at
``destructiveHint`` still gets the right answer.

``destructiveHint`` is only semantically meaningful when ``readOnlyHint`` is
false, but it is still emitted as ``false`` on read-only tools for that reason.
"""

from typing import Any, Callable

from app.mcp.registry import ToolRegistry
from app.tools.action_items import (
    archive_action_item,
    complete_action_item,
    get_action_item,
    list_action_items,
)
from app.tools.notes import delete_note, get_note, list_notes
from app.tools.recordings import delete_recording, get_recording, list_recordings
from app.tools.user import get_current_user
from app.tools.webhooks import (
    create_webhook,
    delete_webhook,
    get_webhook,
    list_webhooks,
    update_webhook,
)
from app.validation.schemas import TOOL_SCHEMAS


# Tool descriptions for the MCP tools/list response.
TOOL_DESCRIPTIONS: dict[str, str] = {
    "list_action_items": (
        "Read-only. List action items with optional filters for completed "
        "status, archived status, AI detection, scope, and ordering."
    ),
    "get_action_item": "Read-only. Retrieve a single action item by its ID.",
    "complete_action_item": (
        "Mark an action item as complete or incomplete. Modifies the action "
        "item's completion state."
    ),
    "archive_action_item": "Archive an action item by its ID. Modifies the action item.",
    "list_notes": (
        "Read-only. List meeting notes with optional filters for event, "
        "dates, channel, title, and attendees."
    ),
    "get_note": "Read-only. Retrieve a single note by its ID.",
    "delete_note": "Permanently delete a note by its ID. This cannot be undone.",
    "list_recordings": (
        "Read-only. List recordings with optional filters for event, dates, "
        "channel, and title. Supports include options for transcript and AI notes."
    ),
    "get_recording": (
        "Read-only. Retrieve a single recording by its ID with optional "
        "includes for transcript, AI notes, and media URL."
    ),
    "delete_recording": (
        "Permanently delete a recording by its ID. This cannot be undone."
    ),
    "list_webhooks": (
        "Read-only. List webhooks with optional limit and cursor for pagination."
    ),
    "get_webhook": "Read-only. Retrieve a single webhook by its ID.",
    "create_webhook": (
        "Create a new webhook with a URL, enabled events, and optional "
        "description and status. Sends future event data to the given URL."
    ),
    "update_webhook": (
        "Update an existing webhook's URL, enabled events, description, or "
        "status. Overwrites the previous values of the fields supplied."
    ),
    "delete_webhook": "Delete a webhook by its ID.",
    "get_current_user": (
        "Read-only. Get the authenticated user's information including "
        "user ID, name, email, and workspace details."
    ),
}


# MCP tool annotations, per tool. See the module docstring for why every hint
# is spelled out rather than left to a default.
#
# openWorldHint: false for every tool that stays inside the caller's own Fellow
# workspace -- the entity domain is closed and enumerable. It is true only for
# the two webhook mutators, which accept an arbitrary operator-supplied
# destination URL and therefore arrange delivery of workspace data to an
# external endpoint of the caller's choosing.
TOOL_ANNOTATIONS: dict[str, dict[str, Any]] = {
    # --- Read-only: no state is modified anywhere. -----------------------
    # NOTE: several of these call the Fellow API over HTTP POST (its list
    # endpoints take a filter/pagination body). The upstream HTTP verb is an
    # API-shape detail and says nothing about whether state changes -- these
    # are queries, and are annotated as such.
    "list_action_items": {
        "title": "List action items",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "get_action_item": {
        "title": "Get action item",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "list_notes": {
        "title": "List meeting notes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "get_note": {
        "title": "Get meeting note",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "list_recordings": {
        "title": "List recordings",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "get_recording": {
        "title": "Get recording",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "list_webhooks": {
        "title": "List webhooks",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "get_webhook": {
        "title": "Get webhook",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "get_current_user": {
        "title": "Get current user",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    # --- Non-destructive writes: reversible or purely additive. ----------
    "complete_action_item": {
        "title": "Complete or uncomplete an action item",
        "readOnlyHint": False,
        # Flips a boolean the caller can flip back; destroys nothing.
        "destructiveHint": False,
        # Same arguments -> same end state.
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "archive_action_item": {
        "title": "Archive an action item",
        "readOnlyHint": False,
        # Archiving hides the item; it does not delete it.
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "create_webhook": {
        "title": "Create a webhook",
        "readOnlyHint": False,
        # Purely additive -- overwrites no existing record.
        "destructiveHint": False,
        # Each call creates another distinct webhook.
        "idempotentHint": False,
        # Registers an arbitrary external delivery URL.
        "openWorldHint": True,
    },
    # --- Destructive writes: overwrite or remove data. -------------------
    "update_webhook": {
        "title": "Update a webhook",
        "readOnlyHint": False,
        # Replaces the prior value of each supplied field, so not additive.
        "destructiveHint": True,
        "idempotentHint": True,
        # Can repoint delivery at an arbitrary external URL.
        "openWorldHint": True,
    },
    "delete_note": {
        "title": "Delete a meeting note",
        "readOnlyHint": False,
        "destructiveHint": True,
        # A second call fails rather than succeeding silently.
        "idempotentHint": False,
        "openWorldHint": False,
    },
    "delete_recording": {
        "title": "Delete a recording",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
    "delete_webhook": {
        "title": "Delete a webhook",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
}


# Tool handlers mapped by name.
TOOL_HANDLERS: dict[str, Callable] = {
    "list_action_items": list_action_items,
    "get_action_item": get_action_item,
    "complete_action_item": complete_action_item,
    "archive_action_item": archive_action_item,
    "list_notes": list_notes,
    "get_note": get_note,
    "delete_note": delete_note,
    "list_recordings": list_recordings,
    "get_recording": get_recording,
    "delete_recording": delete_recording,
    "list_webhooks": list_webhooks,
    "get_webhook": get_webhook,
    "create_webhook": create_webhook,
    "update_webhook": update_webhook,
    "delete_webhook": delete_webhook,
    "get_current_user": get_current_user,
}


# The four hints every tool must declare explicitly. See the module docstring:
# an omitted hint falls back to a specification default, and for
# ``destructiveHint`` that default is True.
REQUIRED_HINTS: tuple[str, ...] = (
    "readOnlyHint",
    "destructiveHint",
    "idempotentHint",
    "openWorldHint",
)


def _validate_annotations() -> None:
    """Fail at import time if the annotation table is incomplete or incoherent.

    A tool advertised with a missing or non-boolean hint is unallow-listable by
    every client, and a read-only tool marked destructive is actively
    misleading. Both are configuration bugs that must not reach a running
    server, so this raises rather than warning.

    Raises:
        ValueError: If any tool lacks annotations, lacks one of the four
            required hints, declares a non-boolean hint, or claims to be both
            read-only and destructive.
    """
    problems: list[str] = []

    missing = set(TOOL_HANDLERS) - set(TOOL_ANNOTATIONS)
    for name in sorted(missing):
        problems.append(f"{name}: registered handler has no annotations")

    orphaned = set(TOOL_ANNOTATIONS) - set(TOOL_HANDLERS)
    for name in sorted(orphaned):
        problems.append(f"{name}: annotations for a tool with no handler")

    for name in sorted(set(TOOL_ANNOTATIONS) & set(TOOL_HANDLERS)):
        annotations = TOOL_ANNOTATIONS[name]
        for hint in REQUIRED_HINTS:
            if hint not in annotations:
                problems.append(f"{name}: missing required hint {hint!r}")
            elif not isinstance(annotations[hint], bool):
                problems.append(
                    f"{name}: hint {hint!r} must be a bool, "
                    f"got {annotations[hint]!r}"
                )
        if annotations.get("readOnlyHint") and annotations.get("destructiveHint"):
            problems.append(
                f"{name}: cannot be both readOnlyHint and destructiveHint"
            )

    if problems:
        raise ValueError(
            "Invalid MCP tool annotations in app.mcp.definitions:\n  - "
            + "\n  - ".join(problems)
        )


_validate_annotations()


# Derived views over TOOL_ANNOTATIONS. These are computed from the annotations
# rather than maintained by hand, so an allow-list built from them can never
# disagree with what tools/list advertises.
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    name for name, ann in TOOL_ANNOTATIONS.items() if ann["readOnlyHint"]
)
WRITE_TOOLS: frozenset[str] = frozenset(
    name for name, ann in TOOL_ANNOTATIONS.items() if not ann["readOnlyHint"]
)
DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    name
    for name, ann in TOOL_ANNOTATIONS.items()
    if not ann["readOnlyHint"] and ann["destructiveHint"]
)


def build_input_schema(tool_name: str) -> dict[str, Any]:
    """Build a JSON Schema dict from the internal TOOL_SCHEMAS definition.

    Converts the internal param spec format into a standard JSON Schema
    object suitable for MCP tools/list responses.

    Args:
        tool_name: The tool name to build schema for.

    Returns:
        A JSON Schema dict with type, properties, and required fields.
    """
    schema_def = TOOL_SCHEMAS[tool_name]
    properties: dict[str, Any] = {}

    for param_name, param_spec in schema_def["params"].items():
        param_type = param_spec["type"]

        if param_type == "bool":
            properties[param_name] = {"type": "boolean"}
        elif param_type == "int":
            prop: dict[str, Any] = {"type": "integer"}
            if "min" in param_spec:
                prop["minimum"] = param_spec["min"]
            if "max" in param_spec:
                prop["maximum"] = param_spec["max"]
            properties[param_name] = prop
        elif param_type in ("string", "id", "date", "url"):
            properties[param_name] = {"type": "string"}
        elif param_type == "enum":
            properties[param_name] = {
                "type": "string",
                "enum": param_spec["enum_values"],
            }
        elif param_type == "enum_list":
            properties[param_name] = {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": param_spec["enum_values"],
                },
            }

    return {
        "type": "object",
        "properties": properties,
        "required": schema_def["required"],
    }


def create_registry() -> ToolRegistry:
    """Create and populate the tool registry with all tools and annotations.

    Returns:
        A fully populated ToolRegistry instance.

    Raises:
        KeyError: If a registered handler has no description or no annotations.
            This is deliberate -- a tool advertised without annotations would be
            treated as an unclassified write by every client, so failing at
            startup is better than shipping an unallow-listable tool.
    """
    registry = ToolRegistry()

    for tool_name, handler in TOOL_HANDLERS.items():
        registry.register(
            name=tool_name,
            description=TOOL_DESCRIPTIONS[tool_name],
            input_schema=build_input_schema(tool_name),
            handler=handler,
            annotations=TOOL_ANNOTATIONS[tool_name],
        )

    return registry
