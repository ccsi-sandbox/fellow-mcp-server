"""Property-based tests for preservation of application configuration and runtime behavior.

# Feature: dependabot-security-fixes, Property 2: Preservation
# Application Configuration and Runtime Behavior Unchanged

These tests capture existing behavior BEFORE implementing the dependency upgrades.
They must PASS on the unfixed code, confirming that:
- Gunicorn config values are stable: bind="0.0.0.0:8000", worker_class="sync", timeout=500, workers=2
- Flask app can be created and /health endpoint is registered
- All application module imports succeed
- Dockerfile structure preserves non-root user, EXPOSE 8000, healthcheck, and gunicorn CMD

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
"""

import importlib
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st


# --- Constants ---

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Expected gunicorn config values (observed on unfixed code)
EXPECTED_GUNICORN_BIND = "0.0.0.0:8000"
EXPECTED_GUNICORN_WORKER_CLASS = "sync"
EXPECTED_GUNICORN_TIMEOUT = 500
EXPECTED_GUNICORN_DEFAULT_WORKERS = 2

# Application modules that must import successfully
APP_MODULES = [
    "app",
    "app.main",
    "app.config",
    "app.auth",
    "app.auth.guard",
    "app.client",
    "app.client.fellow_api",
    "app.client.paginator",
    "app.client.rate_limiter",
    "app.logging",
    "app.logging.setup",
    "app.logging.metrics",
    "app.mcp",
    "app.mcp.errors",
    "app.mcp.protocol",
    "app.mcp.registry",
    "app.tools",
    "app.tools.action_items",
    "app.tools.notes",
    "app.tools.recordings",
    "app.tools.user",
    "app.tools.webhooks",
    "app.validation",
    "app.validation.schemas",
]

# Dockerfile patterns that must be preserved
DOCKERFILE_REQUIRED_PATTERNS = {
    "non_root_user_creation": r"adduser\s+--disabled-password.*appuser",
    "user_switch": r"^USER\s+appuser",
    "expose_8000": r"^EXPOSE\s+8000",
    "healthcheck": r"HEALTHCHECK[\s\S]*?python3[\s\S]*?urllib\.request[\s\S]*?localhost:8000/health",
    "gunicorn_cmd": r'CMD\s+\["gunicorn".*"app\.main:create_app\(\)"\]',
}


# --- Strategies ---

# Generate varied environment configurations for GUNICORN_WORKERS
worker_count_strategy = st.integers(min_value=1, max_value=16)

# Generate random environment variable combinations that should NOT affect
# core gunicorn config (bind, worker_class, timeout)
env_override_strategy = st.fixed_dictionaries({
    "LOG_LEVEL": st.sampled_from(["debug", "info", "warning", "error", "critical"]),
    "TZ": st.sampled_from([
        "America/Los_Angeles",
        "America/New_York",
        "UTC",
        "Europe/London",
        "Asia/Tokyo",
    ]),
})

# Strategy for picking random subsets of app modules to test
module_subsets = st.lists(
    st.sampled_from(APP_MODULES),
    min_size=1,
    max_size=len(APP_MODULES),
    unique=True,
)

# Strategy for picking random Dockerfile required patterns to verify
dockerfile_pattern_subsets = st.lists(
    st.sampled_from(list(DOCKERFILE_REQUIRED_PATTERNS.keys())),
    min_size=1,
    max_size=len(DOCKERFILE_REQUIRED_PATTERNS),
    unique=True,
)


# --- Helpers ---


def load_gunicorn_config(env_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    """Load gunicorn.conf.py and extract configuration values.

    Executes the gunicorn config file in a controlled namespace to extract
    the configuration variables it sets.

    Args:
        env_overrides: Optional environment variable overrides to set before loading.

    Returns:
        Dictionary of gunicorn configuration values.
    """
    config_path = PROJECT_ROOT / "gunicorn.conf.py"
    assert config_path.exists(), f"gunicorn.conf.py not found at {config_path}"

    # Save and set environment variables
    saved_env = {}
    if env_overrides:
        for key, value in env_overrides.items():
            saved_env[key] = os.environ.get(key)
            os.environ[key] = value

    try:
        # Execute gunicorn config in its own namespace
        namespace: dict[str, Any] = {"__builtins__": __builtins__}
        exec(compile(config_path.read_text(), str(config_path), "exec"), namespace)

        return {
            "bind": namespace.get("bind"),
            "workers": namespace.get("workers"),
            "worker_class": namespace.get("worker_class"),
            "timeout": namespace.get("timeout"),
            "graceful_timeout": namespace.get("graceful_timeout"),
            "accesslog": namespace.get("accesslog"),
            "errorlog": namespace.get("errorlog"),
            "loglevel": namespace.get("loglevel"),
        }
    finally:
        # Restore environment
        if env_overrides:
            for key, original_value in saved_env.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value


def read_dockerfile() -> str:
    """Read the Dockerfile content."""
    dockerfile_path = PROJECT_ROOT / "Dockerfile"
    assert dockerfile_path.exists(), f"Dockerfile not found at {dockerfile_path}"
    return dockerfile_path.read_text()


# --- Property Tests ---


@pytest.mark.property
class TestGunicornConfigPreservation:
    """Property 2: Gunicorn configuration values are preserved across dependency upgrades.

    Verifies that bind, worker_class, timeout, and default workers remain stable
    regardless of environment variable combinations.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
    """

    @given(env_overrides=env_override_strategy)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_gunicorn_bind_preserved_across_environments(self, env_overrides: dict):
        """For any combination of LOG_LEVEL and TZ environment variables,
        gunicorn SHALL CONTINUE TO bind on 0.0.0.0:8000.

        **Validates: Requirements 3.1**
        """
        config = load_gunicorn_config(env_overrides)
        assert config["bind"] == EXPECTED_GUNICORN_BIND, (
            f"Expected bind='{EXPECTED_GUNICORN_BIND}', got bind='{config['bind']}' "
            f"with env={env_overrides}"
        )

    @given(env_overrides=env_override_strategy)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_gunicorn_worker_class_preserved_across_environments(self, env_overrides: dict):
        """For any combination of LOG_LEVEL and TZ environment variables,
        gunicorn SHALL CONTINUE TO use sync worker_class.

        **Validates: Requirements 3.1**
        """
        config = load_gunicorn_config(env_overrides)
        assert config["worker_class"] == EXPECTED_GUNICORN_WORKER_CLASS, (
            f"Expected worker_class='{EXPECTED_GUNICORN_WORKER_CLASS}', "
            f"got worker_class='{config['worker_class']}' with env={env_overrides}"
        )

    @given(env_overrides=env_override_strategy)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_gunicorn_timeout_preserved_across_environments(self, env_overrides: dict):
        """For any combination of LOG_LEVEL and TZ environment variables,
        gunicorn SHALL CONTINUE TO use a timeout of 500 seconds.

        **Validates: Requirements 3.1**
        """
        config = load_gunicorn_config(env_overrides)
        assert config["timeout"] == EXPECTED_GUNICORN_TIMEOUT, (
            f"Expected timeout={EXPECTED_GUNICORN_TIMEOUT}, "
            f"got timeout={config['timeout']} with env={env_overrides}"
        )

    @given(worker_count=worker_count_strategy)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_gunicorn_workers_configurable_via_env(self, worker_count: int):
        """For any valid GUNICORN_WORKERS value (1-16), the workers config
        SHALL reflect the environment variable. Default SHALL be 2.

        **Validates: Requirements 3.1**
        """
        # Test with explicit GUNICORN_WORKERS set
        config = load_gunicorn_config({"GUNICORN_WORKERS": str(worker_count)})
        assert config["workers"] == worker_count, (
            f"Expected workers={worker_count} when GUNICORN_WORKERS={worker_count}, "
            f"got workers={config['workers']}"
        )

    def test_gunicorn_default_workers_is_2(self):
        """When GUNICORN_WORKERS is not set, workers SHALL default to 2.

        **Validates: Requirements 3.1**
        """
        # Ensure GUNICORN_WORKERS is not set
        saved = os.environ.pop("GUNICORN_WORKERS", None)
        try:
            config = load_gunicorn_config()
            assert config["workers"] == EXPECTED_GUNICORN_DEFAULT_WORKERS, (
                f"Expected default workers={EXPECTED_GUNICORN_DEFAULT_WORKERS}, "
                f"got workers={config['workers']}"
            )
        finally:
            if saved is not None:
                os.environ["GUNICORN_WORKERS"] = saved


@pytest.mark.property
class TestFlaskAppPreservation:
    """Property 2: Flask app can be created and /health endpoint is registered.

    Verifies the application factory works correctly and endpoints are available.

    **Validates: Requirements 3.3, 3.5, 3.6, 3.7, 3.8**
    """

    def test_flask_app_creates_successfully(self):
        """Flask app SHALL create successfully using the app factory pattern.

        **Validates: Requirements 3.3**
        """
        from app.config import AppConfig
        from app.main import create_app

        config = AppConfig(
            fellow_api_key="test-key-preservation",
            fellow_subdomain="testworkspace",
            mcp_auth_enabled=False,
            mcp_auth_token=None,
            gunicorn_workers=2,
            log_level="INFO",
            mcp_endpoint_path="/mcp",
            fellow_base_url="https://testworkspace.fellow.app",
        )
        app = create_app(config={"TESTING": True, "APP_CONFIG": config})
        assert app is not None
        assert app.name == "app.main"

    def test_health_endpoint_registered(self):
        """The /health endpoint SHALL be registered in the Flask app.

        **Validates: Requirements 3.3, 3.5**
        """
        from app.config import AppConfig
        from app.main import create_app

        config = AppConfig(
            fellow_api_key="test-key-preservation",
            fellow_subdomain="testworkspace",
            mcp_auth_enabled=False,
            mcp_auth_token=None,
            gunicorn_workers=2,
            log_level="INFO",
            mcp_endpoint_path="/mcp",
            fellow_base_url="https://testworkspace.fellow.app",
        )
        app = create_app(config={"TESTING": True, "APP_CONFIG": config})

        # Verify /health route exists
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert "/health" in rules, (
            f"/health endpoint not registered. Available routes: {rules}"
        )

    def test_mcp_endpoint_registered(self):
        """The /mcp endpoint SHALL be registered in the Flask app.

        **Validates: Requirements 3.3**
        """
        from app.config import AppConfig
        from app.main import create_app

        config = AppConfig(
            fellow_api_key="test-key-preservation",
            fellow_subdomain="testworkspace",
            mcp_auth_enabled=False,
            mcp_auth_token=None,
            gunicorn_workers=2,
            log_level="INFO",
            mcp_endpoint_path="/mcp",
            fellow_base_url="https://testworkspace.fellow.app",
        )
        app = create_app(config={"TESTING": True, "APP_CONFIG": config})

        # Verify /mcp route exists
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert "/mcp" in rules, (
            f"/mcp endpoint not registered. Available routes: {rules}"
        )

    @given(log_level=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR"]))
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_health_endpoint_responds_200(self, log_level: str):
        """For any log level, the /health endpoint SHALL respond with status 200.

        **Validates: Requirements 3.3, 3.5**
        """
        import responses as responses_mock
        from app.config import AppConfig
        from app.main import create_app

        config = AppConfig(
            fellow_api_key="test-key-preservation",
            fellow_subdomain="testworkspace",
            mcp_auth_enabled=False,
            mcp_auth_token=None,
            gunicorn_workers=2,
            log_level=log_level,
            mcp_endpoint_path="/mcp",
            fellow_base_url="https://testworkspace.fellow.app",
        )
        app = create_app(config={"TESTING": True, "APP_CONFIG": config})

        with responses_mock.RequestsMock() as rsps:
            # Mock the health check call to Fellow API
            rsps.add(
                responses_mock.GET,
                "https://testworkspace.fellow.app/api/v1/me",
                json={"id": "user-1"},
                status=200,
            )
            with app.test_client() as client:
                resp = client.get("/health")
                assert resp.status_code == 200, (
                    f"Expected 200 from /health at LOG_LEVEL={log_level}, "
                    f"got {resp.status_code}"
                )


@pytest.mark.property
class TestModuleImportsPreservation:
    """Property 2: All application module imports succeed.

    Verifies that all app modules can be imported successfully, confirming
    no import breakage from dependency changes.

    **Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
    """

    @given(modules=module_subsets)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_app_modules_import_successfully(self, modules: list[str]):
        """For any subset of application modules, all imports SHALL succeed.

        **Validates: Requirements 3.2, 3.3, 3.4**
        """
        for module_name in modules:
            try:
                mod = importlib.import_module(module_name)
                assert mod is not None, (
                    f"Module '{module_name}' imported but is None"
                )
            except ImportError as e:
                pytest.fail(
                    f"Module '{module_name}' failed to import: {e}"
                )

    def test_all_app_modules_importable(self):
        """All known application modules SHALL import without error.

        **Validates: Requirements 3.2, 3.3, 3.4**
        """
        failures = []
        for module_name in APP_MODULES:
            try:
                importlib.import_module(module_name)
            except ImportError as e:
                failures.append(f"{module_name}: {e}")

        assert not failures, (
            f"Module import failures:\n" + "\n".join(f"  - {f}" for f in failures)
        )


@pytest.mark.property
class TestDockerfilePreservation:
    """Property 2: Dockerfile structure preserves critical configurations.

    Verifies the Dockerfile maintains non-root user, EXPOSE 8000, healthcheck,
    and gunicorn CMD regardless of base image changes.

    **Validates: Requirements 3.5, 3.6, 3.7, 3.8**
    """

    @given(patterns=dockerfile_pattern_subsets)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_dockerfile_preserves_required_patterns(self, patterns: list[str]):
        """For any subset of required Dockerfile patterns, all SHALL be present.

        **Validates: Requirements 3.5, 3.7, 3.8**
        """
        dockerfile_content = read_dockerfile()

        for pattern_name in patterns:
            pattern = DOCKERFILE_REQUIRED_PATTERNS[pattern_name]
            match = re.search(pattern, dockerfile_content, re.MULTILINE)
            assert match is not None, (
                f"Dockerfile missing required pattern '{pattern_name}': "
                f"regex '{pattern}' not found in Dockerfile"
            )

    def test_dockerfile_has_non_root_user(self):
        """Dockerfile SHALL create and switch to non-root appuser.

        **Validates: Requirements 3.7**
        """
        dockerfile_content = read_dockerfile()

        # Verify appuser is created
        assert re.search(
            r"adduser\s+--disabled-password.*appuser", dockerfile_content
        ), "Dockerfile does not create non-root 'appuser'"

        # Verify USER switch to appuser
        assert re.search(
            r"^USER\s+appuser", dockerfile_content, re.MULTILINE
        ), "Dockerfile does not switch to 'appuser'"

    def test_dockerfile_exposes_port_8000(self):
        """Dockerfile SHALL expose port 8000.

        **Validates: Requirements 3.7**
        """
        dockerfile_content = read_dockerfile()
        assert re.search(
            r"^EXPOSE\s+8000", dockerfile_content, re.MULTILINE
        ), "Dockerfile does not EXPOSE 8000"

    def test_dockerfile_has_healthcheck(self):
        """Dockerfile SHALL include healthcheck using python3 urllib.

        **Validates: Requirements 3.5, 3.7**
        """
        dockerfile_content = read_dockerfile()
        assert re.search(
            r"HEALTHCHECK[\s\S]*?python3[\s\S]*?urllib\.request[\s\S]*?localhost:8000/health",
            dockerfile_content,
        ), "Dockerfile missing healthcheck with python3 urllib to localhost:8000/health"

    def test_dockerfile_uses_gunicorn_cmd(self):
        """Dockerfile SHALL use gunicorn CMD with app.main:create_app().

        **Validates: Requirements 3.7**
        """
        dockerfile_content = read_dockerfile()
        assert re.search(
            r'CMD\s+\["gunicorn".*"app\.main:create_app\(\)"\]',
            dockerfile_content,
        ), "Dockerfile missing gunicorn CMD with app.main:create_app()"

    def test_docker_compose_healthcheck_preserved(self):
        """docker-compose.yml SHALL include healthcheck using python3 urllib.

        **Validates: Requirements 3.5, 3.7**
        """
        compose_path = PROJECT_ROOT / "docker-compose.yml"
        assert compose_path.exists(), "docker-compose.yml not found"
        content = compose_path.read_text()

        assert "python3" in content, (
            "docker-compose.yml healthcheck does not use python3"
        )
        assert "urllib.request" in content, (
            "docker-compose.yml healthcheck does not use urllib.request"
        )
        assert "localhost:8000/health" in content, (
            "docker-compose.yml healthcheck does not target localhost:8000/health"
        )
