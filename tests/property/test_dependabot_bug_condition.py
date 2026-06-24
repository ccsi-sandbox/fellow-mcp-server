"""Property-based tests for Dependabot security fixes bug condition.

# Feature: dependabot-security-fixes, Property 1: Bug Condition - Vulnerable Dependency Versions Pinned

GOAL: Surface counterexamples that demonstrate vulnerable versions are pinned
in requirements.txt, requirements-dev.txt, and Dockerfile.

These tests encode the EXPECTED behavior after the fix. They are expected to FAIL
on unfixed code because dependencies are still at vulnerable versions.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10**
"""

import os
import re
from pathlib import Path
from typing import Tuple

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# --- Constants ---

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Minimum patched versions for each dependency (major, minor, patch)
PATCHED_VERSIONS = {
    "gunicorn": (26, 0, 0),
    "requests": (2, 34, 2),
    "Flask": (3, 1, 3),
    "python-dotenv": (1, 2, 2),
}

PATCHED_DEV_VERSIONS = {
    "black": (26, 3, 1),
    "pytest": (9, 0, 3),
}

ALL_DEPENDENCIES = list(PATCHED_VERSIONS.keys()) + list(PATCHED_DEV_VERSIONS.keys())


# --- Helpers ---


def parse_version(version_str: str) -> Tuple[int, ...]:
    """Parse a version string like '21.2.0' into a tuple of ints."""
    parts = version_str.strip().split(".")
    return tuple(int(p) for p in parts)


def get_dependency_version(file_path: Path, package_name: str) -> str | None:
    """Parse a requirements file and return the pinned version for a package."""
    content = file_path.read_text()
    # Match patterns like: package==version or package>=version
    pattern = rf"^{re.escape(package_name)}[=><]+(.+)$"
    for line in content.splitlines():
        line = line.strip()
        match = re.match(pattern, line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def get_dockerfile_base_image(dockerfile_path: Path) -> list[str]:
    """Parse Dockerfile and return all FROM base images."""
    content = dockerfile_path.read_text()
    images = []
    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("FROM "):
            # Extract image name (before AS or end of line)
            parts = line.split()
            if len(parts) >= 2:
                images.append(parts[1])
    return images


def get_dockerfile_site_packages_paths(dockerfile_path: Path) -> list[str]:
    """Parse Dockerfile and return site-packages paths referenced."""
    content = dockerfile_path.read_text()
    paths = []
    pattern = r"/usr/local/lib/(python[\d.]+)/site-packages"
    for match in re.finditer(pattern, content):
        paths.append(match.group(1))
    return paths


# --- Strategies ---

# Strategy to pick random subsets of production dependencies
prod_dep_subsets = st.lists(
    st.sampled_from(list(PATCHED_VERSIONS.keys())),
    min_size=1,
    max_size=len(PATCHED_VERSIONS),
    unique=True,
)

# Strategy to pick random subsets of dev dependencies
dev_dep_subsets = st.lists(
    st.sampled_from(list(PATCHED_DEV_VERSIONS.keys())),
    min_size=1,
    max_size=len(PATCHED_DEV_VERSIONS),
    unique=True,
)

# Strategy to pick random subsets from all dependencies
all_dep_subsets = st.lists(
    st.sampled_from(ALL_DEPENDENCIES),
    min_size=1,
    max_size=len(ALL_DEPENDENCIES),
    unique=True,
)


# --- Property Tests ---


@pytest.mark.property
class TestDependabotBugCondition:
    """Property 1: Bug Condition - Vulnerable Dependency Versions Pinned.

    These tests verify that ALL dependencies are at or above the minimum patched
    versions. On unfixed code, these tests FAIL because vulnerable versions are
    pinned, proving the bug exists.

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10**
    """

    @given(deps=prod_dep_subsets)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_production_dependencies_at_patched_versions(self, deps: list[str]):
        """For any subset of production dependencies, all versions in requirements.txt
        SHALL be at or above their minimum patched version.

        Bug condition: isBugCondition returns true when any production dependency
        version is below its patched minimum.

        **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7**
        """
        requirements_path = PROJECT_ROOT / "requirements.txt"
        assert requirements_path.exists(), f"requirements.txt not found at {requirements_path}"

        for dep in deps:
            version_str = get_dependency_version(requirements_path, dep)
            assert version_str is not None, (
                f"Dependency '{dep}' not found in requirements.txt"
            )

            current_version = parse_version(version_str)
            minimum_version = PATCHED_VERSIONS[dep]

            assert current_version >= minimum_version, (
                f"VULNERABLE: {dep}=={version_str} is below minimum patched "
                f"version {'.'.join(str(v) for v in minimum_version)}. "
                f"CVE(s) remain unpatched."
            )

    @given(deps=dev_dep_subsets)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_dev_dependencies_at_patched_versions(self, deps: list[str]):
        """For any subset of dev dependencies, all versions in requirements-dev.txt
        SHALL be at or above their minimum patched version.

        Bug condition: isBugCondition returns true when any dev dependency
        version is below its patched minimum.

        **Validates: Requirements 1.8, 1.9, 1.10**
        """
        requirements_dev_path = PROJECT_ROOT / "requirements-dev.txt"
        assert requirements_dev_path.exists(), (
            f"requirements-dev.txt not found at {requirements_dev_path}"
        )

        for dep in deps:
            version_str = get_dependency_version(requirements_dev_path, dep)
            assert version_str is not None, (
                f"Dependency '{dep}' not found in requirements-dev.txt"
            )

            current_version = parse_version(version_str)
            minimum_version = PATCHED_DEV_VERSIONS[dep]

            assert current_version >= minimum_version, (
                f"VULNERABLE: {dep}=={version_str} is below minimum patched "
                f"version {'.'.join(str(v) for v in minimum_version)}. "
                f"CVE(s) remain unpatched."
            )

    @given(data=st.data())
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_dockerfile_uses_python312_base_image(self, data):
        """The Dockerfile SHALL use python:3.12-slim as the base image
        (not python:3.11-slim).

        Bug condition: isBugCondition returns true when docker_base_image
        is not python:3.12-slim.

        **Validates: Requirements 1.1, 1.2**
        """
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        assert dockerfile_path.exists(), f"Dockerfile not found at {dockerfile_path}"

        base_images = get_dockerfile_base_image(dockerfile_path)
        assert len(base_images) > 0, "No FROM statements found in Dockerfile"

        # Pick a random base image to check (there could be multiple stages)
        idx = data.draw(st.integers(min_value=0, max_value=len(base_images) - 1))
        image = base_images[idx]

        # Strip the AS alias if present in the raw image string
        # The image should be python:3.12-slim (with or without AS builder)
        assert "python:3.12-slim" in image, (
            f"VULNERABLE: Dockerfile uses '{image}' but should use 'python:3.12-slim'. "
            f"Python 3.11 is incompatible with gunicorn>=26.0.0."
        )

    @given(data=st.data())
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_dockerfile_site_packages_references_python312(self, data):
        """The Dockerfile site-packages path SHALL reference python3.12
        (not python3.11).

        Bug condition: isBugCondition returns true when site_packages_path
        contains 'python3.11'.

        **Validates: Requirements 1.1, 1.2**
        """
        dockerfile_path = PROJECT_ROOT / "Dockerfile"
        assert dockerfile_path.exists(), f"Dockerfile not found at {dockerfile_path}"

        paths = get_dockerfile_site_packages_paths(dockerfile_path)
        assert len(paths) > 0, "No site-packages paths found in Dockerfile"

        # Pick a random path reference to check
        idx = data.draw(st.integers(min_value=0, max_value=len(paths) - 1))
        python_version = paths[idx]

        assert python_version == "python3.12", (
            f"VULNERABLE: Dockerfile references '{python_version}' in site-packages "
            f"path but should reference 'python3.12'. "
            f"Path must match the base image Python version."
        )

    @given(deps=all_dep_subsets)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_no_bug_condition_for_any_dependency_subset(self, deps: list[str]):
        """For any random subset of all dependencies (production + dev),
        the bug condition isBugCondition(input) SHALL return false, meaning
        all versions are at or above their minimum patched versions.

        This is the comprehensive property test that combines all checks.

        **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10**
        """
        requirements_path = PROJECT_ROOT / "requirements.txt"
        requirements_dev_path = PROJECT_ROOT / "requirements-dev.txt"

        for dep in deps:
            if dep in PATCHED_VERSIONS:
                file_path = requirements_path
                minimum_version = PATCHED_VERSIONS[dep]
            else:
                file_path = requirements_dev_path
                minimum_version = PATCHED_DEV_VERSIONS[dep]

            version_str = get_dependency_version(file_path, dep)
            assert version_str is not None, (
                f"Dependency '{dep}' not found in {file_path.name}"
            )

            current_version = parse_version(version_str)
            assert current_version >= minimum_version, (
                f"BUG CONDITION: {dep}=={version_str} < "
                f"{'.'.join(str(v) for v in minimum_version)}. "
                f"Vulnerable version pinned."
            )
