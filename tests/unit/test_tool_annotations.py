"""Guards on MCP tool annotations (read vs write classification).

A client builds its allow-list and its approval policy from the hints in
``tool.annotations``. If a tool is advertised without them, the MCP
specification's defaults apply (``readOnlyHint`` false, ``destructiveHint``
true) and the tool is treated as an unclassifiable destructive write. These
tests pin the classification so a new or renamed tool cannot ship unclassified,
and so a read-only tool cannot silently acquire a mutating handler.
"""

import inspect

import pytest

from app.mcp.definitions import (
    DESTRUCTIVE_TOOLS,
    READ_ONLY_TOOLS,
    TOOL_ANNOTATIONS,
    TOOL_DESCRIPTIONS,
    TOOL_HANDLERS,
    WRITE_TOOLS,
    create_registry,
)
from app.mcp.registry import ToolNotFoundError, ToolRegistry
from app.validation.schemas import TOOL_SCHEMAS


# The intended classification, written out literally. Deriving it from
# TOOL_ANNOTATIONS would make these tests vacuous — they must disagree with the
# code when the code changes.
EXPECTED_READ_ONLY = {
    "list_action_items",
    "get_action_item",
    "list_notes",
    "get_note",
    "list_recordings",
    "get_recording",
    "list_webhooks",
    "get_webhook",
    "get_current_user",
}

EXPECTED_WRITE = {
    "complete_action_item",
    "archive_action_item",
    "create_webhook",
    "update_webhook",
    "delete_note",
    "delete_recording",
    "delete_webhook",
}

EXPECTED_DESTRUCTIVE = {
    "update_webhook",
    "delete_note",
    "delete_recording",
    "delete_webhook",
}

_REQUIRED_HINTS = (
    "readOnlyHint",
    "destructiveHint",
    "idempotentHint",
    "openWorldHint",
)

# HTTP methods on FellowApiClient that change upstream state.
_MUTATING_CLIENT_CALLS = ("client.put(", "client.patch(", "client.delete(")


class TestAnnotationCoverage:
    """Every advertised tool carries a complete annotations object."""

    def test_every_handler_has_annotations(self):
        assert set(TOOL_ANNOTATIONS) == set(TOOL_HANDLERS)

    def test_every_handler_has_a_description(self):
        assert set(TOOL_DESCRIPTIONS) == set(TOOL_HANDLERS)

    def test_every_handler_has_a_validation_schema(self):
        assert set(TOOL_HANDLERS).issubset(set(TOOL_SCHEMAS))

    @pytest.mark.parametrize("tool_name", sorted(TOOL_ANNOTATIONS))
    def test_all_four_hints_are_explicit_booleans(self, tool_name):
        """No hint may be left to a specification default.

        ``destructiveHint`` defaults to TRUE when absent, so omitting it on a
        read-only tool would advertise that tool as destructive.
        """
        annotations = TOOL_ANNOTATIONS[tool_name]
        for hint in _REQUIRED_HINTS:
            assert hint in annotations, f"{tool_name} is missing {hint}"
            assert isinstance(
                annotations[hint], bool
            ), f"{tool_name}.{hint} must be a bool, got {annotations[hint]!r}"

    @pytest.mark.parametrize("tool_name", sorted(TOOL_ANNOTATIONS))
    def test_every_tool_has_a_human_readable_title(self, tool_name):
        title = TOOL_ANNOTATIONS[tool_name].get("title")
        assert isinstance(title, str) and title.strip()


class TestClassification:
    """The read/write split matches the intended classification exactly."""

    def test_read_only_set_is_exact(self):
        assert READ_ONLY_TOOLS == EXPECTED_READ_ONLY

    def test_write_set_is_exact(self):
        assert WRITE_TOOLS == EXPECTED_WRITE

    def test_destructive_set_is_exact(self):
        assert DESTRUCTIVE_TOOLS == EXPECTED_DESTRUCTIVE

    def test_read_only_and_write_sets_partition_all_tools(self):
        assert READ_ONLY_TOOLS | WRITE_TOOLS == set(TOOL_HANDLERS)
        assert not READ_ONLY_TOOLS & WRITE_TOOLS

    def test_at_least_one_tool_in_each_class(self):
        """Non-vacuity: an empty read-only set would pass every other check."""
        assert READ_ONLY_TOOLS
        assert WRITE_TOOLS
        assert DESTRUCTIVE_TOOLS

    @pytest.mark.parametrize("tool_name", sorted(EXPECTED_READ_ONLY))
    def test_read_only_tools_are_not_destructive(self, tool_name):
        annotations = TOOL_ANNOTATIONS[tool_name]
        assert annotations["readOnlyHint"] is True
        assert annotations["destructiveHint"] is False
        # A query returns the same thing when repeated.
        assert annotations["idempotentHint"] is True

    @pytest.mark.parametrize("tool_name", sorted(EXPECTED_DESTRUCTIVE))
    def test_destructive_tools_are_not_read_only(self, tool_name):
        annotations = TOOL_ANNOTATIONS[tool_name]
        assert annotations["readOnlyHint"] is False
        assert annotations["destructiveHint"] is True

    @pytest.mark.parametrize(
        "tool_name", sorted({"create_webhook", "update_webhook"})
    )
    def test_webhook_mutators_are_open_world(self, tool_name):
        """These accept an arbitrary external delivery URL."""
        assert TOOL_ANNOTATIONS[tool_name]["openWorldHint"] is True

    @pytest.mark.parametrize("tool_name", sorted(EXPECTED_READ_ONLY))
    def test_read_only_tools_are_closed_world(self, tool_name):
        assert TOOL_ANNOTATIONS[tool_name]["openWorldHint"] is False


class TestHandlerSourceAgreesWithAnnotation:
    """A read-only annotation must match what the handler actually does.

    Read-only handlers may use ``client.get`` and ``client.post`` (the Fellow
    API's list endpoints are POST queries that take a filter body), but must
    never use PUT, PATCH or DELETE.
    """

    @pytest.mark.parametrize("tool_name", sorted(EXPECTED_READ_ONLY))
    def test_read_only_handler_makes_no_mutating_upstream_call(self, tool_name):
        source = inspect.getsource(TOOL_HANDLERS[tool_name])
        for call in _MUTATING_CLIENT_CALLS:
            assert call not in source, (
                f"{tool_name} is annotated readOnlyHint=true but its handler "
                f"calls {call}"
            )

    def test_probe_detects_a_mutating_call(self):
        """Non-vacuity: the probe above finds a DELETE when one is present."""
        source = inspect.getsource(TOOL_HANDLERS["delete_note"])
        assert any(call in source for call in _MUTATING_CLIENT_CALLS)


class TestAnnotationValidator:
    """``_validate_annotations`` rejects an incomplete or incoherent table.

    It runs at import time, so these failures stop the server from starting
    rather than shipping a tool no client can classify.
    """

    def _run_with(self, annotations, handlers=None):
        from app.mcp import definitions

        patched_handlers = (
            handlers if handlers is not None else {k: lambda **kw: None for k in annotations}
        )
        original_ann = definitions.TOOL_ANNOTATIONS
        original_handlers = definitions.TOOL_HANDLERS
        definitions.TOOL_ANNOTATIONS = annotations
        definitions.TOOL_HANDLERS = patched_handlers
        try:
            definitions._validate_annotations()
        finally:
            definitions.TOOL_ANNOTATIONS = original_ann
            definitions.TOOL_HANDLERS = original_handlers

    def _complete(self, **overrides):
        base = {
            "title": "A tool",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
        base.update(overrides)
        return base

    def test_accepts_the_real_table(self):
        from app.mcp.definitions import _validate_annotations

        _validate_annotations()  # must not raise

    def test_accepts_a_valid_synthetic_table(self):
        """Non-vacuity: the validator passes a well-formed table."""
        self._run_with({"a_tool": self._complete()})

    def test_rejects_a_handler_with_no_annotations(self):
        with pytest.raises(ValueError, match="has no annotations"):
            self._run_with(
                {"a_tool": self._complete()},
                handlers={"a_tool": lambda **kw: None, "b_tool": lambda **kw: None},
            )

    def test_rejects_annotations_with_no_handler(self):
        with pytest.raises(ValueError, match="no handler"):
            self._run_with(
                {"a_tool": self._complete(), "ghost": self._complete()},
                handlers={"a_tool": lambda **kw: None},
            )

    @pytest.mark.parametrize("hint", _REQUIRED_HINTS)
    def test_rejects_a_missing_hint(self, hint):
        annotations = self._complete()
        del annotations[hint]
        with pytest.raises(ValueError, match=f"missing required hint '{hint}'"):
            self._run_with({"a_tool": annotations})

    def test_rejects_a_non_boolean_hint(self):
        with pytest.raises(ValueError, match="must be a bool"):
            self._run_with({"a_tool": self._complete(readOnlyHint="true")})

    def test_rejects_read_only_and_destructive_together(self):
        with pytest.raises(ValueError, match="both readOnlyHint and destructiveHint"):
            self._run_with(
                {"a_tool": self._complete(readOnlyHint=True, destructiveHint=True)}
            )

    def test_error_names_the_offending_tool(self):
        annotations = self._complete()
        del annotations["openWorldHint"]
        with pytest.raises(ValueError, match="my_broken_tool"):
            self._run_with({"my_broken_tool": annotations})


class TestRegistryAdvertisesAnnotations:
    """tools/list output carries the annotations, for both transports."""

    def test_every_listed_tool_includes_annotations(self):
        registry = create_registry()
        for tool in registry.list_tools():
            assert "annotations" in tool, f"{tool['name']} listed without annotations"
            assert tool["annotations"] == TOOL_ANNOTATIONS[tool["name"]]

    def test_registry_reports_read_only_flag(self):
        registry = create_registry()
        assert registry.is_read_only("get_note") is True
        assert registry.is_read_only("delete_note") is False

    def test_is_read_only_defaults_to_false_without_annotations(self):
        """An unannotated tool must NOT be reported as read-only."""
        registry = ToolRegistry()
        registry.register(
            name="unannotated",
            description="No annotations supplied",
            input_schema={"type": "object", "properties": {}},
            handler=lambda **kwargs: None,
        )
        assert registry.is_read_only("unannotated") is False
        assert registry.get_annotations("unannotated") == {}
        assert "annotations" not in registry.list_tools()[0]

    def test_annotations_lookup_rejects_unknown_tool(self):
        registry = create_registry()
        with pytest.raises(ToolNotFoundError):
            registry.get_annotations("no_such_tool")

    def test_registered_annotations_are_copied_not_aliased(self):
        """Mutating the caller's dict cannot change what was advertised."""
        registry = ToolRegistry()
        source = {"readOnlyHint": True}
        registry.register(
            name="copied",
            description="Annotation copy check",
            input_schema={"type": "object", "properties": {}},
            handler=lambda **kwargs: None,
            annotations=source,
        )
        source["readOnlyHint"] = False
        assert registry.is_read_only("copied") is True

    def test_both_transports_advertise_identical_metadata(self):
        """The HTTP and stdio transports must not drift apart."""
        from app import main, stdio

        assert main.create_registry is create_registry
        assert stdio.create_registry is create_registry
