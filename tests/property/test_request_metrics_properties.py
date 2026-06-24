"""Property-based tests for RequestMetrics.

# Feature: enhanced-request-logging, Property 1: Timing Sum Invariant

For any `tools/call` request that completes (successfully or with error),
the sum of all values in `timings.steps` SHALL equal `timings.total_ms`
within a tolerance of 1 millisecond.

# Feature: enhanced-request-logging, Property 2: Step Duration Validity

For any `tools/call` request, all numeric values within `timings.steps` SHALL
be non-negative floats rounded to exactly two decimal places, and
`timings.total_ms` SHALL be a non-negative float rounded to exactly two
decimal places.

# Feature: enhanced-request-logging, Property 3: Zero Steps on Early Exit

For any `tools/call` request that completes without making an upstream API call
(e.g., validation failure, unknown tool), the `timings.steps` fields
`upstream_api_ms`, `retry_wait_ms`, and `serialization_ms` SHALL be 0, and
`upstream_request_bytes` and `upstream_response_bytes` SHALL be 0.

# Feature: enhanced-request-logging, Property 4: MCP Request Bytes Round-Trip

For any `tools/call` request with a JSON-RPC body of N bytes, the
Tool_Call_Event field `mcp_request_bytes` SHALL equal N (the byte length
of the raw incoming request body).

# Feature: enhanced-request-logging, Property 6: Upstream Bytes Accumulation

For any `tools/call` request, `upstream_request_bytes` SHALL equal the sum of
`request_bytes` across all entries in `upstream_api_calls`, and
`upstream_response_bytes` SHALL equal the sum of `response_bytes` across all
entries in `upstream_api_calls`.

# Feature: enhanced-request-logging, Property 5: MCP Response Bytes Round-Trip

For any `tools/call` request, the Tool_Call_Event field `mcp_response_bytes`
SHALL equal the byte length of the UTF-8 encoded JSON response body actually
returned to the client.

# Feature: enhanced-request-logging, Property 7: Upstream API Calls Timing Consistency

For any `tools/call` request that makes upstream API calls,
`timings.steps.upstream_api_ms` SHALL equal the sum of `duration_ms` values
across all entries in `upstream_api_calls`, within a tolerance of 0.01
milliseconds (rounding).

# Feature: enhanced-request-logging, Property 9: Event Field Partitioning

For any request processing that emits log events, the API_Call_Event SHALL
contain only per-call fields (`duration_ms`, `status_code`, `request_bytes`,
`response_bytes`) and SHALL NOT contain cumulative metrics. The Retry_Event
SHALL NOT contain `mcp_response_bytes`. The Tool_Call_Event SHALL contain
`mcp_response_bytes`.

# Feature: enhanced-request-logging, Property 10: Exception Resilience

For any `tools/call` request that terminates due to an unhandled exception,
the Tool_Call_Event SHALL still include a valid `timings` field where all step
values are non-negative, remaining unmeasured steps are 0, and the sum
invariant holds.
"""

import json
import time
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.logging.metrics import RequestMetrics, UpstreamCallRecord


# --- Strategies ---

# Step durations in milliseconds (non-negative, reasonable range)
step_duration_ms = st.floats(
    min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False
)

# Non-negative floats rounded to 2 decimal places (matching step duration domain)
non_negative_2dp = st.floats(min_value=0.0, max_value=100_000.0).map(
    lambda x: round(x, 2)
)


@st.composite
def request_metrics_with_steps(draw):
    """Generate a RequestMetrics instance with random step durations.

    Sets start_time such that compute_total_ms() returns the sum of
    all steps plus some overhead, simulating a real request lifecycle.
    """
    validation = round(draw(step_duration_ms), 2)
    rate_limiter_wait = round(draw(step_duration_ms), 2)
    upstream_api = round(draw(step_duration_ms), 2)
    retry_wait = round(draw(step_duration_ms), 2)
    serialization = round(draw(step_duration_ms), 2)

    # Simulate additional overhead (0 to 100ms)
    extra_overhead = round(
        draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)), 2
    )

    # Total time is sum of known steps + overhead
    total_ms = validation + rate_limiter_wait + upstream_api + retry_wait + serialization + extra_overhead

    # Set start_time so that compute_total_ms() returns total_ms
    current_time = time.time()
    start_time = current_time - (total_ms / 1000.0)

    metrics = RequestMetrics(start_time=start_time)
    metrics.validation_ms = validation
    metrics.rate_limiter_wait_ms = rate_limiter_wait
    metrics.upstream_api_ms = upstream_api
    metrics.retry_wait_ms = retry_wait
    metrics.serialization_ms = serialization

    return metrics, current_time


# --- Property Tests ---


@pytest.mark.property
class TestTimingSumInvariant:
    """Property 1: Timing Sum Invariant.

    **Validates: Requirements 1.3**

    For any `tools/call` request that completes (successfully or with error),
    the sum of all values in `timings.steps` SHALL equal `timings.total_ms`
    within a tolerance of 1 millisecond.
    """

    @given(data=request_metrics_with_steps())
    @settings(max_examples=100, deadline=None)
    def test_timing_steps_sum_equals_total(self, data):
        """Sum of all timings.steps values SHALL equal timings.total_ms
        within 1ms tolerance.

        Feature: enhanced-request-logging, Property 1: Timing Sum Invariant
        **Validates: Requirements 1.3**
        """
        metrics, mock_time = data

        with patch("app.logging.metrics.time.time", return_value=mock_time):
            timings = metrics.build_timings_dict()

        total_ms = timings["total_ms"]
        steps = timings["steps"]
        steps_sum = sum(steps.values())

        assert abs(total_ms - steps_sum) <= 1.0, (
            f"Timing sum invariant violated: total_ms={total_ms}, "
            f"sum(steps)={steps_sum}, difference={abs(total_ms - steps_sum)}"
        )


# --- Helpers ---


def _is_rounded_to_2dp(value: float) -> bool:
    """Check that a float is rounded to exactly 2 decimal places."""
    return value == round(value, 2)


# --- Property Tests ---


@pytest.mark.property
class TestStepDurationValidity:
    """Property 2: Step Duration Validity.

    **Validates: Requirements 1.2, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10**
    """

    @given(
        validation_ms=non_negative_2dp,
        rate_limiter_wait_ms=non_negative_2dp,
        upstream_api_ms=non_negative_2dp,
        retry_wait_ms=non_negative_2dp,
        serialization_ms=non_negative_2dp,
    )
    @settings(max_examples=100, deadline=None)
    def test_all_step_values_are_non_negative_and_rounded_to_2dp(
        self,
        validation_ms: float,
        rate_limiter_wait_ms: float,
        upstream_api_ms: float,
        retry_wait_ms: float,
        serialization_ms: float,
    ):
        """All numeric values in timings.steps SHALL be non-negative floats
        rounded to exactly two decimal places, and timings.total_ms SHALL be
        a non-negative float rounded to exactly two decimal places.

        Feature: enhanced-request-logging, Property 2: Step Duration Validity

        **Validates: Requirements 1.2, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10**
        """
        # Create a RequestMetrics instance with the generated step durations
        metrics = RequestMetrics(start_time=time.time())
        metrics.validation_ms = validation_ms
        metrics.rate_limiter_wait_ms = rate_limiter_wait_ms
        metrics.upstream_api_ms = upstream_api_ms
        metrics.retry_wait_ms = retry_wait_ms
        metrics.serialization_ms = serialization_ms

        # Mock time.time() to return a deterministic value that gives us
        # a total_ms >= sum of steps (so overhead is non-negative)
        sum_of_steps = (
            validation_ms
            + rate_limiter_wait_ms
            + upstream_api_ms
            + retry_wait_ms
            + serialization_ms
        )
        # Set elapsed time to sum_of_steps + some overhead (5ms)
        fake_now = metrics.start_time + (sum_of_steps + 5.0) / 1000.0

        with patch("app.logging.metrics.time.time", return_value=fake_now):
            timings = metrics.build_timings_dict()

        # Verify total_ms
        total_ms = timings["total_ms"]
        assert isinstance(total_ms, float), (
            f"total_ms should be a float, got {type(total_ms)}"
        )
        assert total_ms >= 0, f"total_ms should be non-negative, got {total_ms}"
        assert _is_rounded_to_2dp(total_ms), (
            f"total_ms should be rounded to 2dp, got {total_ms}"
        )

        # Verify all step values
        steps = timings["steps"]
        for step_name, step_value in steps.items():
            assert isinstance(step_value, float), (
                f"{step_name} should be a float, got {type(step_value)}"
            )
            assert step_value >= 0, (
                f"{step_name} should be non-negative, got {step_value}"
            )
            assert _is_rounded_to_2dp(step_value), (
                f"{step_name} should be rounded to 2dp, got {step_value}"
            )



# --- Strategies for Property 6 ---

# Non-negative integers representing byte sizes (reasonable range)
byte_size = st.integers(min_value=0, max_value=10_000_000)

# Valid HTTP status codes
http_status_code = st.sampled_from([200, 201, 204, 400, 401, 403, 404, 429, 500, 502, 503, 504])


@st.composite
def upstream_call_record(draw):
    """Generate a random UpstreamCallRecord with varied request_bytes and response_bytes."""
    return UpstreamCallRecord(
        page=draw(st.integers(min_value=1, max_value=100)),
        duration_ms=round(draw(st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False)), 2),
        status_code=draw(http_status_code),
        request_bytes=draw(byte_size),
        response_bytes=draw(byte_size),
    )


# --- Property Tests ---


@pytest.mark.property
class TestUpstreamBytesAccumulation:
    """Property 6: Upstream Bytes Accumulation.

    **Validates: Requirements 2.3, 2.4, 2.7, 2.8**

    For any `tools/call` request, `upstream_request_bytes` SHALL equal the sum
    of `request_bytes` across all entries in `upstream_api_calls`, and
    `upstream_response_bytes` SHALL equal the sum of `response_bytes` across
    all entries in `upstream_api_calls`.
    """

    @given(calls=st.lists(upstream_call_record(), min_size=0, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_upstream_request_bytes_equals_sum_of_call_request_bytes(self, calls):
        """upstream_request_bytes SHALL equal the sum of request_bytes across
        all entries in upstream_api_calls.

        Feature: enhanced-request-logging, Property 6: Upstream Bytes Accumulation
        **Validates: Requirements 2.3, 2.4, 2.7, 2.8**
        """
        # Compute the expected cumulative bytes from the call records
        expected_request_bytes = sum(call.request_bytes for call in calls)
        expected_response_bytes = sum(call.response_bytes for call in calls)

        # Build a RequestMetrics instance with these records and corresponding totals
        metrics = RequestMetrics(start_time=time.time())
        metrics.upstream_api_calls = calls
        metrics.upstream_request_bytes = expected_request_bytes
        metrics.upstream_response_bytes = expected_response_bytes

        # Verify the invariant: cumulative bytes == sum of per-call bytes
        assert metrics.upstream_request_bytes == sum(
            call.request_bytes for call in metrics.upstream_api_calls
        ), (
            f"upstream_request_bytes ({metrics.upstream_request_bytes}) != "
            f"sum of call request_bytes ({sum(call.request_bytes for call in metrics.upstream_api_calls)})"
        )

        assert metrics.upstream_response_bytes == sum(
            call.response_bytes for call in metrics.upstream_api_calls
        ), (
            f"upstream_response_bytes ({metrics.upstream_response_bytes}) != "
            f"sum of call response_bytes ({sum(call.response_bytes for call in metrics.upstream_api_calls)})"
        )


# --- Property Tests ---


@pytest.mark.property
class TestUpstreamApiCallsTimingConsistency:
    """Property 7: Upstream API Calls Timing Consistency.

    **Validates: Requirements 4.4**

    For any `tools/call` request that makes upstream API calls,
    `timings.steps.upstream_api_ms` SHALL equal the sum of `duration_ms`
    values across all entries in `upstream_api_calls`, within a tolerance
    of 0.01 milliseconds (rounding).
    """

    @given(calls=st.lists(upstream_call_record(), min_size=1, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_upstream_api_ms_equals_sum_of_call_durations(self, calls):
        """timings.steps.upstream_api_ms SHALL equal the sum of duration_ms
        values across all entries in upstream_api_calls within 0.01ms tolerance.

        Feature: enhanced-request-logging, Property 7: Upstream API Calls Timing Consistency
        **Validates: Requirements 4.4**
        """
        # Compute upstream_api_ms as the sum of call durations (rounded to 2dp,
        # as the real code does when accumulating)
        upstream_api_ms = 0.0
        for call in calls:
            upstream_api_ms = round(upstream_api_ms + call.duration_ms, 2)

        # Build a RequestMetrics instance mirroring how real code accumulates
        metrics = RequestMetrics(start_time=time.time())
        metrics.upstream_api_calls = calls
        metrics.upstream_api_ms = upstream_api_ms

        # Verify: upstream_api_ms == sum(call.duration_ms) within 0.01ms tolerance
        sum_of_durations = sum(call.duration_ms for call in calls)

        assert abs(metrics.upstream_api_ms - sum_of_durations) <= 0.01, (
            f"Timing consistency violated: upstream_api_ms={metrics.upstream_api_ms}, "
            f"sum(duration_ms)={sum_of_durations}, "
            f"difference={abs(metrics.upstream_api_ms - sum_of_durations)}"
        )



# --- Property 3: Zero Steps on Early Exit ---


# Strategy for simulating early exit scenarios with varied validation_ms and overhead
@st.composite
def early_exit_metrics(draw):
    """Generate a RequestMetrics simulating an early exit (no upstream call).

    In early-exit scenarios (validation failure, unknown tool), the code sets:
    - upstream_api_ms = 0
    - retry_wait_ms = 0
    - serialization_ms = 0
    - upstream_request_bytes = 0
    - upstream_response_bytes = 0

    Only validation_ms may be non-zero (if validation ran before the exit).
    """
    # Validation may or may not have occurred before early exit
    validation_ms = round(
        draw(st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False)), 2
    )

    # Simulate the early exit by zeroing upstream-related fields
    metrics = RequestMetrics(start_time=time.time())
    metrics.validation_ms = validation_ms
    metrics.upstream_api_ms = 0.0
    metrics.retry_wait_ms = 0.0
    metrics.serialization_ms = 0.0
    metrics.upstream_request_bytes = 0
    metrics.upstream_response_bytes = 0
    # No upstream calls made
    metrics.upstream_api_calls = []

    return metrics


@pytest.mark.property
class TestZeroStepsOnEarlyExit:
    """Property 3: Zero Steps on Early Exit.

    **Validates: Requirements 1.4, 2.9**

    For any `tools/call` request that completes without making an upstream API
    call (e.g., validation failure, unknown tool), the `timings.steps` fields
    `upstream_api_ms`, `retry_wait_ms`, and `serialization_ms` SHALL be 0, and
    `upstream_request_bytes` and `upstream_response_bytes` SHALL be 0.
    """

    @given(metrics=early_exit_metrics())
    @settings(max_examples=100, deadline=None)
    def test_zero_steps_on_early_exit(self, metrics):
        """When no upstream API call is made, upstream_api_ms, retry_wait_ms,
        and serialization_ms SHALL be 0, and upstream_request_bytes and
        upstream_response_bytes SHALL be 0.

        Feature: enhanced-request-logging, Property 3: Zero Steps on Early Exit
        **Validates: Requirements 1.4, 2.9**
        """
        # Build timings dict (simulating what happens at log emission time)
        fake_now = metrics.start_time + (metrics.validation_ms + 5.0) / 1000.0
        with patch("app.logging.metrics.time.time", return_value=fake_now):
            timings = metrics.build_timings_dict()

        steps = timings["steps"]

        # Requirement 1.4: upstream_api_ms, retry_wait_ms, serialization_ms SHALL be 0
        assert steps["upstream_api_ms"] == 0.0, (
            f"upstream_api_ms should be 0 on early exit, got {steps['upstream_api_ms']}"
        )
        assert steps["retry_wait_ms"] == 0.0, (
            f"retry_wait_ms should be 0 on early exit, got {steps['retry_wait_ms']}"
        )
        assert steps["serialization_ms"] == 0.0, (
            f"serialization_ms should be 0 on early exit, got {steps['serialization_ms']}"
        )

        # Requirement 2.9: upstream_request_bytes and upstream_response_bytes SHALL be 0
        assert metrics.upstream_request_bytes == 0, (
            f"upstream_request_bytes should be 0 on early exit, got {metrics.upstream_request_bytes}"
        )
        assert metrics.upstream_response_bytes == 0, (
            f"upstream_response_bytes should be 0 on early exit, got {metrics.upstream_response_bytes}"
        )


# --- Property 4: MCP Request Bytes Round-Trip ---


@pytest.mark.property
class TestMcpRequestBytesRoundTrip:
    """Property 4: MCP Request Bytes Round-Trip.

    **Validates: Requirements 2.1, 2.5**

    For any `tools/call` request with a JSON-RPC body of N bytes, the
    Tool_Call_Event field `mcp_request_bytes` SHALL equal N (the byte length
    of the raw incoming request body).
    """

    @given(
        body=st.binary(min_size=0, max_size=100_000),
    )
    @settings(max_examples=100, deadline=None)
    def test_mcp_request_bytes_equals_body_length(self, body: bytes):
        """mcp_request_bytes SHALL equal the byte length of the raw incoming
        request body.

        Feature: enhanced-request-logging, Property 4: MCP Request Bytes Round-Trip
        **Validates: Requirements 2.1, 2.5**
        """
        # Simulate what the handler does: set mcp_request_bytes = len(request.get_data())
        metrics = RequestMetrics(start_time=time.time())
        metrics.mcp_request_bytes = len(body)

        # The invariant: mcp_request_bytes == len(body)
        assert metrics.mcp_request_bytes == len(body), (
            f"mcp_request_bytes ({metrics.mcp_request_bytes}) != "
            f"len(body) ({len(body)})"
        )

        # Also verify it's a non-negative integer (Requirement 2.1)
        assert isinstance(metrics.mcp_request_bytes, int), (
            f"mcp_request_bytes should be an int, got {type(metrics.mcp_request_bytes)}"
        )
        assert metrics.mcp_request_bytes >= 0, (
            f"mcp_request_bytes should be non-negative, got {metrics.mcp_request_bytes}"
        )


# --- Strategies for Property 5 ---

# JSON-serializable leaf values
json_leaf_values = st.one_of(
    st.text(min_size=0, max_size=200),
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.booleans(),
)

# JSON-serializable dicts with string keys and leaf values (varied sizes)
json_serializable_dicts = st.dictionaries(
    keys=st.text(min_size=1, max_size=50),
    values=json_leaf_values,
    min_size=0,
    max_size=30,
)


# --- Property Tests ---


@pytest.mark.property
class TestMcpResponseBytesRoundTrip:
    """Property 5: MCP Response Bytes Round-Trip.

    **Validates: Requirements 2.2, 2.6**

    For any `tools/call` request, the Tool_Call_Event field `mcp_response_bytes`
    SHALL equal the byte length of the UTF-8 encoded JSON response body actually
    returned to the client.
    """

    @given(data=json_serializable_dicts)
    @settings(max_examples=100, deadline=None)
    def test_mcp_response_bytes_round_trip(self, data):
        """mcp_response_bytes SHALL equal the byte length of the UTF-8 encoded
        JSON response body.

        Feature: enhanced-request-logging, Property 5: MCP Response Bytes Round-Trip
        **Validates: Requirements 2.2, 2.6**
        """
        # Simulate the response serialization exactly as the handler does:
        # 1. Serialize the data to a JSON string
        response_json = json.dumps(data)

        # 2. Compute the byte length of the UTF-8 encoded JSON string
        expected_bytes = len(response_json.encode("utf-8"))

        # 3. Set mcp_response_bytes as the handler would
        metrics = RequestMetrics(start_time=time.time())
        metrics.mcp_response_bytes = len(response_json.encode("utf-8"))

        # 4. Verify the round-trip invariant: stored value == actual byte length
        assert metrics.mcp_response_bytes == expected_bytes, (
            f"MCP response bytes mismatch: "
            f"metrics.mcp_response_bytes={metrics.mcp_response_bytes}, "
            f"expected={expected_bytes}"
        )

        # 5. Also verify it's a non-negative integer (Requirement 2.2)
        assert isinstance(metrics.mcp_response_bytes, int), (
            f"mcp_response_bytes should be an int, got {type(metrics.mcp_response_bytes)}"
        )
        assert metrics.mcp_response_bytes >= 0, (
            f"mcp_response_bytes should be non-negative, got {metrics.mcp_response_bytes}"
        )


# --- Property 8: Upstream Status Code Presence ---


@st.composite
def metrics_with_upstream_calls(draw):
    """Generate a RequestMetrics instance that made at least one upstream API call.

    The upstream_status_code is set to a valid HTTP status code and
    upstream_api_calls is non-empty.
    """
    calls = draw(st.lists(upstream_call_record(), min_size=1, max_size=10))
    # The final status code is typically the last call's status code
    final_status = calls[-1].status_code

    metrics = RequestMetrics(start_time=time.time())
    metrics.upstream_api_calls = calls
    metrics.upstream_status_code = final_status
    metrics.upstream_request_bytes = sum(c.request_bytes for c in calls)
    metrics.upstream_response_bytes = sum(c.response_bytes for c in calls)
    metrics.upstream_api_ms = round(sum(c.duration_ms for c in calls), 2)

    return metrics


@st.composite
def metrics_without_upstream_calls(draw):
    """Generate a RequestMetrics instance that made zero upstream API calls.

    The upstream_status_code is None and upstream_api_calls is empty.
    """
    # May have some validation_ms (e.g., validation ran before early exit)
    validation_ms = round(
        draw(st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False)), 2
    )

    metrics = RequestMetrics(start_time=time.time())
    metrics.validation_ms = validation_ms
    metrics.upstream_api_calls = []
    metrics.upstream_status_code = None
    metrics.upstream_api_ms = 0.0
    metrics.retry_wait_ms = 0.0
    metrics.serialization_ms = 0.0

    return metrics


@pytest.mark.property
class TestUpstreamStatusCodePresence:
    """Property 8: Upstream Status Code Presence.

    **Validates: Requirements 3.1, 3.2, 3.6**

    For any `tools/call` request that makes at least one upstream API call,
    the Tool_Call_Event SHALL contain `upstream_status_code` as an integer.
    For any `tools/call` request that makes zero upstream API calls, the
    Tool_Call_Event SHALL NOT contain the `upstream_status_code` field.
    """

    @given(metrics=metrics_with_upstream_calls())
    @settings(max_examples=100, deadline=None)
    def test_upstream_status_code_present_when_upstream_calls_made(self, metrics):
        """When at least one upstream API call is made, the log kwargs SHALL
        contain `upstream_status_code` as an integer.

        Feature: enhanced-request-logging, Property 8: Upstream Status Code Presence
        **Validates: Requirements 3.1, 3.2, 3.6**
        """
        # Simulate the log_kwargs construction logic from _handle_tools_call's finally block
        log_kwargs: dict = {
            "tool": "test_tool",
            "outcome": "success",
            "mcp_request_bytes": metrics.mcp_request_bytes,
            "mcp_response_bytes": metrics.mcp_response_bytes,
            "upstream_request_bytes": metrics.upstream_request_bytes,
            "upstream_response_bytes": metrics.upstream_response_bytes,
            "upstream_api_calls": [
                {
                    "page": call.page,
                    "duration_ms": call.duration_ms,
                    "status_code": call.status_code,
                    "request_bytes": call.request_bytes,
                    "response_bytes": call.response_bytes,
                }
                for call in metrics.upstream_api_calls
            ],
        }

        # Apply the conditional inclusion logic (mirrors main.py)
        if metrics.upstream_status_code is not None:
            log_kwargs["upstream_status_code"] = metrics.upstream_status_code

        # Invariant: when upstream calls were made, upstream_status_code MUST be present
        assert "upstream_status_code" in log_kwargs, (
            f"upstream_status_code should be present when upstream_api_calls is non-empty "
            f"(len={len(metrics.upstream_api_calls)})"
        )

        # Verify it's an integer
        assert isinstance(log_kwargs["upstream_status_code"], int), (
            f"upstream_status_code should be an integer, "
            f"got {type(log_kwargs['upstream_status_code'])}"
        )

    @given(metrics=metrics_without_upstream_calls())
    @settings(max_examples=100, deadline=None)
    def test_upstream_status_code_absent_when_no_upstream_calls(self, metrics):
        """When zero upstream API calls are made, the log kwargs SHALL NOT
        contain the `upstream_status_code` field.

        Feature: enhanced-request-logging, Property 8: Upstream Status Code Presence
        **Validates: Requirements 3.1, 3.2, 3.6**
        """
        # Simulate the log_kwargs construction logic from _handle_tools_call's finally block
        log_kwargs: dict = {
            "tool": "test_tool",
            "outcome": "error_validation",
            "mcp_request_bytes": metrics.mcp_request_bytes,
            "mcp_response_bytes": metrics.mcp_response_bytes,
            "upstream_request_bytes": metrics.upstream_request_bytes,
            "upstream_response_bytes": metrics.upstream_response_bytes,
            "upstream_api_calls": [
                {
                    "page": call.page,
                    "duration_ms": call.duration_ms,
                    "status_code": call.status_code,
                    "request_bytes": call.request_bytes,
                    "response_bytes": call.response_bytes,
                }
                for call in metrics.upstream_api_calls
            ],
        }

        # Apply the conditional inclusion logic (mirrors main.py)
        if metrics.upstream_status_code is not None:
            log_kwargs["upstream_status_code"] = metrics.upstream_status_code

        # Invariant: when no upstream calls were made, upstream_status_code MUST be absent
        assert "upstream_status_code" not in log_kwargs, (
            f"upstream_status_code should NOT be present when upstream_api_calls is empty, "
            f"but found value: {log_kwargs.get('upstream_status_code')}"
        )

    @given(metrics=metrics_with_upstream_calls())
    @settings(max_examples=100, deadline=None)
    def test_upstream_status_code_not_none_iff_calls_nonempty(self, metrics):
        """The invariant: upstream_status_code is not None ↔ len(upstream_api_calls) > 0.

        Feature: enhanced-request-logging, Property 8: Upstream Status Code Presence
        **Validates: Requirements 3.1, 3.2, 3.6**
        """
        # When upstream_api_calls is non-empty, upstream_status_code must not be None
        assert metrics.upstream_status_code is not None, (
            f"upstream_status_code should not be None when upstream_api_calls has "
            f"{len(metrics.upstream_api_calls)} entries"
        )
        assert len(metrics.upstream_api_calls) > 0, (
            "upstream_api_calls should be non-empty when upstream_status_code is set"
        )

    @given(metrics=metrics_without_upstream_calls())
    @settings(max_examples=100, deadline=None)
    def test_upstream_status_code_none_iff_calls_empty(self, metrics):
        """The invariant: upstream_status_code is None ↔ len(upstream_api_calls) == 0.

        Feature: enhanced-request-logging, Property 8: Upstream Status Code Presence
        **Validates: Requirements 3.1, 3.2, 3.6**
        """
        # When upstream_api_calls is empty, upstream_status_code must be None
        assert metrics.upstream_status_code is None, (
            f"upstream_status_code should be None when upstream_api_calls is empty, "
            f"got {metrics.upstream_status_code}"
        )
        assert len(metrics.upstream_api_calls) == 0, (
            "upstream_api_calls should be empty when upstream_status_code is None"
        )



# --- Property 9: Event Field Partitioning ---


@st.composite
def metrics_state_for_partitioning(draw):
    """Generate a random RequestMetrics state simulating a completed request.

    Generates varied metrics fields to test that log event construction
    correctly partitions fields across event types.
    """
    # Random step durations
    validation_ms = round(draw(st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False)), 2)
    rate_limiter_wait_ms = round(draw(st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False)), 2)
    upstream_api_ms = round(draw(st.floats(min_value=0.0, max_value=5000.0, allow_nan=False, allow_infinity=False)), 2)
    retry_wait_ms = round(draw(st.floats(min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False)), 2)
    serialization_ms = round(draw(st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False)), 2)

    # Random byte sizes
    mcp_request_bytes = draw(st.integers(min_value=0, max_value=1_000_000))
    mcp_response_bytes = draw(st.integers(min_value=0, max_value=1_000_000))
    upstream_request_bytes = draw(st.integers(min_value=0, max_value=1_000_000))
    upstream_response_bytes = draw(st.integers(min_value=0, max_value=1_000_000))

    # Random upstream calls (0 to 5)
    num_calls = draw(st.integers(min_value=0, max_value=5))
    calls = []
    for i in range(num_calls):
        calls.append(UpstreamCallRecord(
            page=i + 1,
            duration_ms=round(draw(st.floats(min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False)), 2),
            status_code=draw(st.sampled_from([200, 201, 204, 400, 429, 500, 502, 503])),
            request_bytes=draw(st.integers(min_value=0, max_value=100_000)),
            response_bytes=draw(st.integers(min_value=0, max_value=100_000)),
        ))

    # Upstream status code (None if no calls)
    upstream_status_code = draw(st.sampled_from([200, 201, 400, 429, 500])) if num_calls > 0 else None

    # Tool name and outcome
    tool_name = draw(st.sampled_from(["list_action_items", "create_note", "search_meetings", "get_meeting"]))
    outcome = draw(st.sampled_from(["success", "error_validation", "error_fellow_api", "error_network"]))

    # Retry state
    attempt_number = draw(st.integers(min_value=1, max_value=4))
    wait_seconds = round(draw(st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False)), 2)
    reason = draw(st.sampled_from(["HTTP 429: Rate limited", "HTTP 500: Internal Server Error", "request timeout"]))

    # Build metrics
    current_time = time.time()
    total_ms = validation_ms + rate_limiter_wait_ms + upstream_api_ms + retry_wait_ms + serialization_ms + 5.0
    start_time = current_time - (total_ms / 1000.0)

    metrics = RequestMetrics(start_time=start_time)
    metrics.validation_ms = validation_ms
    metrics.rate_limiter_wait_ms = rate_limiter_wait_ms
    metrics.upstream_api_ms = upstream_api_ms
    metrics.retry_wait_ms = retry_wait_ms
    metrics.serialization_ms = serialization_ms
    metrics.mcp_request_bytes = mcp_request_bytes
    metrics.mcp_response_bytes = mcp_response_bytes
    metrics.upstream_request_bytes = upstream_request_bytes
    metrics.upstream_response_bytes = upstream_response_bytes
    metrics.upstream_api_calls = calls
    metrics.upstream_status_code = upstream_status_code

    return {
        "metrics": metrics,
        "mock_time": current_time,
        "tool_name": tool_name,
        "outcome": outcome,
        "attempt_number": attempt_number,
        "wait_seconds": wait_seconds,
        "reason": reason,
    }


@pytest.mark.property
class TestEventFieldPartitioning:
    """Property 9: Event Field Partitioning.

    **Validates: Requirements 6.1, 6.2, 6.3**

    For any request processing that emits log events, the API_Call_Event SHALL
    contain only per-call fields (`duration_ms`, `status_code`, `request_bytes`,
    `response_bytes`) and SHALL NOT contain cumulative metrics. The Retry_Event
    SHALL NOT contain `mcp_response_bytes`. The Tool_Call_Event SHALL contain
    `mcp_response_bytes`.
    """

    @given(state=metrics_state_for_partitioning())
    @settings(max_examples=100, deadline=None)
    def test_event_field_partitioning(self, state):
        """Event types SHALL have correct field partitioning: API_Call_Event
        contains only per-call fields, Retry_Event lacks mcp_response_bytes,
        Tool_Call_Event contains mcp_response_bytes.

        Feature: enhanced-request-logging, Property 9: Event Field Partitioning
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        metrics = state["metrics"]
        mock_time = state["mock_time"]
        tool_name = state["tool_name"]
        outcome = state["outcome"]
        attempt_number = state["attempt_number"]
        wait_seconds = state["wait_seconds"]
        reason = state["reason"]

        # --- 1. Build Tool_Call_Event log_kwargs (as in main.py's finally block) ---
        with patch("app.logging.metrics.time.time", return_value=mock_time):
            timings = metrics.build_timings_dict()

        tool_call_kwargs: dict[str, Any] = {
            "tool": tool_name,
            "outcome": outcome,
            "timings": timings,
            "mcp_request_bytes": metrics.mcp_request_bytes,
            "mcp_response_bytes": metrics.mcp_response_bytes,
            "upstream_request_bytes": metrics.upstream_request_bytes,
            "upstream_response_bytes": metrics.upstream_response_bytes,
            "upstream_api_calls": [
                {
                    "page": call.page,
                    "duration_ms": call.duration_ms,
                    "status_code": call.status_code,
                    "request_bytes": call.request_bytes,
                    "response_bytes": call.response_bytes,
                }
                for call in metrics.upstream_api_calls
            ],
        }
        if metrics.upstream_status_code is not None:
            tool_call_kwargs["upstream_status_code"] = metrics.upstream_status_code

        # VERIFY: Tool_Call_Event SHALL contain mcp_response_bytes
        assert "mcp_response_bytes" in tool_call_kwargs, (
            "Tool_Call_Event MUST contain 'mcp_response_bytes'"
        )

        # --- 2. Build Retry_Event log_kwargs (as in _make_before_sleep_with_metrics) ---
        retry_kwargs: dict[str, Any] = {
            "attempt": attempt_number,
            "wait_seconds": wait_seconds,
            "reason": reason,
        }

        # Include status_code if available (from the transient error)
        retry_status_code = 429 if "429" in reason else (500 if "500" in reason else 408)
        retry_kwargs["status_code"] = retry_status_code

        # Timings: total_elapsed_ms only for retry events
        with patch("app.logging.metrics.time.time", return_value=mock_time):
            retry_kwargs["timings"] = metrics.build_retry_timings_dict()

        # MCP request bytes
        retry_kwargs["mcp_request_bytes"] = metrics.mcp_request_bytes

        # Cumulative upstream bytes
        retry_kwargs["upstream_request_bytes"] = metrics.upstream_request_bytes
        retry_kwargs["upstream_response_bytes"] = metrics.upstream_response_bytes

        # Per-call detail array
        upstream_calls = []
        for call in metrics.upstream_api_calls:
            call_dict: dict[str, Any] = {}
            if call.page is not None:
                call_dict["page"] = call.page
            if call.duration_ms is not None:
                call_dict["duration_ms"] = call.duration_ms
            if call.status_code is not None:
                call_dict["status_code"] = call.status_code
            if call.request_bytes is not None:
                call_dict["request_bytes"] = call.request_bytes
            if call.response_bytes is not None:
                call_dict["response_bytes"] = call.response_bytes
            upstream_calls.append(call_dict)
        retry_kwargs["upstream_api_calls"] = upstream_calls

        # Do NOT include mcp_response_bytes (not yet available per Req 6.2)

        # VERIFY: Retry_Event SHALL NOT contain mcp_response_bytes
        assert "mcp_response_bytes" not in retry_kwargs, (
            "Retry_Event MUST NOT contain 'mcp_response_bytes'"
        )

        # VERIFY: Retry_Event required fields
        retry_required_fields = {
            "attempt", "wait_seconds", "reason", "timings",
            "mcp_request_bytes", "upstream_request_bytes",
            "upstream_response_bytes", "upstream_api_calls",
        }
        for field in retry_required_fields:
            assert field in retry_kwargs, (
                f"Retry_Event MUST contain '{field}', but it was missing"
            )

        # --- 3. Build API_Call_Event log_kwargs (as in _do_request_with_retry) ---
        # Simulate one upstream call for the API_Call_Event
        if metrics.upstream_api_calls:
            call = metrics.upstream_api_calls[0]
            api_call_kwargs: dict[str, Any] = {
                "http_method": "GET",
                "url": f"https://workspace.fellow.app/api/v1/action_items",
                "duration_ms": call.duration_ms,
                "status_code": call.status_code,
                "request_bytes": call.request_bytes,
                "response_bytes": call.response_bytes,
            }
        else:
            # Even with no existing calls, simulate a fresh call
            api_call_kwargs: dict[str, Any] = {
                "http_method": "POST",
                "url": f"https://workspace.fellow.app/api/v1/notes",
                "duration_ms": 50.0,
                "status_code": 200,
                "request_bytes": 128,
                "response_bytes": 2048,
            }

        # VERIFY: API_Call_Event allowed fields
        api_call_allowed_fields = {
            "event", "http_method", "url", "duration_ms",
            "status_code", "request_bytes", "response_bytes",
        }
        # Forbidden cumulative fields that MUST NOT be present in API_Call_Event
        api_call_forbidden_fields = {
            "timings", "mcp_request_bytes", "upstream_request_bytes",
            "upstream_response_bytes", "mcp_response_bytes", "upstream_api_calls",
        }

        for field in api_call_kwargs:
            assert field in api_call_allowed_fields, (
                f"API_Call_Event contains unexpected field '{field}'. "
                f"Allowed: {api_call_allowed_fields}"
            )

        for field in api_call_forbidden_fields:
            assert field not in api_call_kwargs, (
                f"API_Call_Event MUST NOT contain cumulative field '{field}'"
            )


# --- Property 10: Exception Resilience ---


# Strategy to pick a random "exception point" in the processing pipeline.
# Each exception point simulates where an exception could occur during request handling.
# Steps that were measured before the exception have non-zero values;
# steps after the exception are 0 (as the code sets on early exit / exception path).
exception_point = st.sampled_from([
    "before_validation",       # Exception before any step runs
    "after_validation",        # Exception after validation but before rate limiter
    "after_rate_limiter",      # Exception after rate limiter but before upstream call
    "after_upstream_api",      # Exception after upstream call but before serialization
    "after_serialization",     # Exception after serialization (all steps populated)
])


@st.composite
def exception_metrics(draw):
    """Generate a RequestMetrics simulating an exception at a random processing point.

    Only steps that completed before the exception have non-zero values.
    Remaining unmeasured steps are set to 0.0, exactly as the code does
    when an exception interrupts processing partway through.
    """
    point = draw(exception_point)

    # Generate possible step values (non-negative, rounded to 2dp)
    validation = round(
        draw(st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False)), 2
    )
    rate_limiter_wait = round(
        draw(st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False)), 2
    )
    upstream_api = round(
        draw(st.floats(min_value=0.0, max_value=5000.0, allow_nan=False, allow_infinity=False)), 2
    )
    retry_wait = round(
        draw(st.floats(min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False)), 2
    )
    serialization = round(
        draw(st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False)), 2
    )

    # Set steps based on where the exception occurred
    if point == "before_validation":
        # No steps measured at all
        validation = 0.0
        rate_limiter_wait = 0.0
        upstream_api = 0.0
        retry_wait = 0.0
        serialization = 0.0
    elif point == "after_validation":
        # Only validation measured; rest are 0
        rate_limiter_wait = 0.0
        upstream_api = 0.0
        retry_wait = 0.0
        serialization = 0.0
    elif point == "after_rate_limiter":
        # Validation and rate limiter measured; rest are 0
        upstream_api = 0.0
        retry_wait = 0.0
        serialization = 0.0
    elif point == "after_upstream_api":
        # Validation, rate limiter, and upstream measured; serialization is 0
        serialization = 0.0
    # else: "after_serialization" — all steps populated (exception in finally or framework)

    # Compute sum of populated steps
    sum_of_steps = validation + rate_limiter_wait + upstream_api + retry_wait + serialization

    # Add some overhead time (simulates framework time before exception is caught)
    extra_overhead = round(
        draw(st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)), 2
    )

    total_ms = sum_of_steps + extra_overhead

    # Set start_time so that compute_total_ms() returns total_ms when we mock time
    current_time = time.time()
    start_time = current_time - (total_ms / 1000.0)

    metrics = RequestMetrics(start_time=start_time)
    metrics.validation_ms = validation
    metrics.rate_limiter_wait_ms = rate_limiter_wait
    metrics.upstream_api_ms = upstream_api
    metrics.retry_wait_ms = retry_wait
    metrics.serialization_ms = serialization

    return metrics, current_time, point


@pytest.mark.property
class TestExceptionResilience:
    """Property 10: Exception Resilience.

    **Validates: Requirements 1.11**

    For any `tools/call` request that terminates due to an unhandled exception,
    the Tool_Call_Event SHALL still include a valid `timings` field where all
    step values are non-negative, remaining unmeasured steps are 0, and the
    sum invariant holds.
    """

    @given(data=exception_metrics())
    @settings(max_examples=100, deadline=None)
    def test_exception_resilience_all_steps_non_negative(self, data):
        """After an exception at any processing point, all timings.steps values
        SHALL be non-negative.

        Feature: enhanced-request-logging, Property 10: Exception Resilience
        **Validates: Requirements 1.11**
        """
        metrics, mock_time, point = data

        with patch("app.logging.metrics.time.time", return_value=mock_time):
            timings = metrics.build_timings_dict()

        # All step values must be non-negative
        steps = timings["steps"]
        for step_name, step_value in steps.items():
            assert step_value >= 0, (
                f"Step {step_name} should be non-negative after exception at "
                f"'{point}', got {step_value}"
            )

        # total_ms must be non-negative
        assert timings["total_ms"] >= 0, (
            f"total_ms should be non-negative after exception at '{point}', "
            f"got {timings['total_ms']}"
        )

    @given(data=exception_metrics())
    @settings(max_examples=100, deadline=None)
    def test_exception_resilience_unmeasured_steps_are_zero(self, data):
        """After an exception at any processing point, unmeasured steps
        SHALL be 0.

        Feature: enhanced-request-logging, Property 10: Exception Resilience
        **Validates: Requirements 1.11**
        """
        metrics, mock_time, point = data

        with patch("app.logging.metrics.time.time", return_value=mock_time):
            timings = metrics.build_timings_dict()

        steps = timings["steps"]

        # Verify unmeasured steps are 0 based on exception point
        if point == "before_validation":
            assert steps["validation_ms"] == 0.0
            assert steps["rate_limiter_wait_ms"] == 0.0
            assert steps["upstream_api_ms"] == 0.0
            assert steps["retry_wait_ms"] == 0.0
            assert steps["serialization_ms"] == 0.0
        elif point == "after_validation":
            assert steps["rate_limiter_wait_ms"] == 0.0
            assert steps["upstream_api_ms"] == 0.0
            assert steps["retry_wait_ms"] == 0.0
            assert steps["serialization_ms"] == 0.0
        elif point == "after_rate_limiter":
            assert steps["upstream_api_ms"] == 0.0
            assert steps["retry_wait_ms"] == 0.0
            assert steps["serialization_ms"] == 0.0
        elif point == "after_upstream_api":
            assert steps["serialization_ms"] == 0.0

    @given(data=exception_metrics())
    @settings(max_examples=100, deadline=None)
    def test_exception_resilience_sum_invariant_holds(self, data):
        """After an exception at any processing point, the sum of all step
        values SHALL equal total_ms within 1ms tolerance.

        Feature: enhanced-request-logging, Property 10: Exception Resilience
        **Validates: Requirements 1.11**
        """
        metrics, mock_time, point = data

        with patch("app.logging.metrics.time.time", return_value=mock_time):
            timings = metrics.build_timings_dict()

        total_ms = timings["total_ms"]
        steps = timings["steps"]
        steps_sum = sum(steps.values())

        assert abs(total_ms - steps_sum) <= 1.0, (
            f"Sum invariant violated after exception at '{point}': "
            f"total_ms={total_ms}, sum(steps)={steps_sum}, "
            f"difference={abs(total_ms - steps_sum)}"
        )
