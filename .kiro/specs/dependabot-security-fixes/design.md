# Dependabot Security Fixes Bugfix Design

## Overview

The project carries 13 open Dependabot security alerts across production and development dependencies. The fix upgrades all affected packages to their patched versions and migrates the Docker base image from `python:3.11-slim` to `python:3.12-slim` (required by gunicorn 26.0.0). The changes are limited to version pins in requirements files and Docker image/path references — no application code changes are needed.

## Glossary

- **Bug_Condition (C)**: The state where the application runs with dependency versions that contain known CVEs
- **Property (P)**: The application runs with dependency versions at or above the minimum patched version for each CVE
- **Preservation**: All existing runtime behavior (gunicorn binding, Flask routing, requests+tenacity HTTP calls, dotenv loading, pytest execution, black formatting) remains unchanged after the upgrade
- **gunicorn.conf.py**: The gunicorn configuration in the project root that binds port 8000 with sync workers and 500s timeout
- **site-packages path**: The Dockerfile `COPY --from=builder` path referencing the Python version-specific site-packages directory

## Bug Details

### Bug Condition

The bug manifests when the application is deployed with outdated dependency versions containing known security vulnerabilities. The vulnerable versions are pinned in `requirements.txt` and `requirements-dev.txt`, and the Dockerfile uses `python:3.11-slim` which is incompatible with the required gunicorn upgrade.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type DependencyManifest (requirements.txt + requirements-dev.txt + Dockerfile)
  OUTPUT: boolean

  RETURN input.gunicorn_version < "26.0.0"
         OR input.requests_version < "2.34.2"
         OR input.flask_version < "3.1.3"
         OR input.python_dotenv_version < "1.2.2"
         OR input.black_version < "26.3.1"
         OR input.pytest_version < "9.0.3"
         OR input.docker_base_image != "python:3.12-slim"
         OR input.site_packages_path CONTAINS "python3.11"
END FUNCTION
```

### Examples

- **gunicorn 21.2.0**: Vulnerable to HTTP request smuggling (CVE-2024-1135, CVE-2024-6827). Attacker can bypass endpoint restrictions via malformed Transfer-Encoding headers.
- **requests 2.31.0**: Ships with session verification bypass (CVE-2024-35195), .netrc credential leak (CVE-2024-47081), and insecure temp file reuse (CVE-2026-25645). While `verify=False` and `.netrc` are not used in this codebase, the vulnerabilities exist in shipped code.
- **Flask 3.0.0**: Missing Vary:Cookie header (CVE-2026-27205). Not directly exploitable since no Flask sessions are used, but the vulnerability surface exists.
- **python-dotenv 1.0.0**: Symlink-following file overwrite (CVE-2026-28684). Not directly exploitable via docker env_file usage, but the vulnerability exists.
- **black 23.11.0**: Arbitrary file writes from cache (CVE-2026-32274) and ReDoS (PYSEC-2024-48) in dev toolchain.
- **pytest 7.4.3**: Insecure tmpdir handling (CVE-2025-71176) in dev toolchain.
- **Dockerfile python:3.11-slim**: Incompatible with gunicorn>=23.0.0 which requires Python 3.12+. Also, site-packages path hardcoded to `python3.11`.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Gunicorn binds on `0.0.0.0:8000` with sync workers, 2 default workers, and 500s timeout
- Flask serves all existing endpoints including `/health`
- Outbound HTTP calls via `requests.Session` with tenacity retry logic function identically
- Environment variables loaded via docker `env_file` configuration
- Container runs as non-root `appuser`
- Docker healthcheck via `python3 -c "import urllib.request; ..."` passes
- `pytest` executes all existing tests successfully
- `black` formats code according to project conventions

**Scope:**
All application logic, configuration, and runtime behavior should be completely unaffected by this fix. The changes are strictly:
- Version pins in requirements files
- Docker base image tag
- Python version in site-packages path

## Hypothesized Root Cause

Based on the bug analysis, the root causes are straightforward:

1. **Outdated Version Pins**: `requirements.txt` and `requirements-dev.txt` pin vulnerable versions. The packages have since released fixes but the pins were never updated.

2. **Docker Image Lag**: The Dockerfile uses `python:3.11-slim` which was appropriate for the original dependency set but is incompatible with gunicorn 26.0.0 (requires Python 3.12+).

3. **Hardcoded Site-Packages Path**: The Dockerfile `COPY --from=builder` instruction references `/usr/local/lib/python3.11/site-packages` which must change to `python3.12` when the base image is upgraded.

4. **No Automated Dependency Updates**: The project lacks automated merge of Dependabot PRs, allowing alerts to accumulate.

## Correctness Properties

Property 1: Bug Condition - All Dependencies at Patched Versions

_For any_ deployment where the application is built from the project's Dockerfile and requirements files, the resulting container SHALL run with gunicorn>=26.0.0, requests>=2.34.2, Flask>=3.1.3, python-dotenv>=1.2.2, and the dev environment SHALL use black>=26.3.1 and pytest>=9.0.3, eliminating all 13 Dependabot security alerts.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8**

Property 2: Preservation - Application Runtime Behavior Unchanged

_For any_ HTTP request to the application (inbound via gunicorn or outbound via requests), the fixed deployment SHALL produce the same behavior as the original deployment, preserving gunicorn binding/timeout configuration, Flask endpoint routing, requests+tenacity retry logic, and environment variable loading.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

## Fix Implementation

### Changes Required

**File**: `requirements.txt`

**Specific Changes**:
1. **Flask**: `Flask==3.0.0` → `Flask==3.1.3`
2. **gunicorn**: `gunicorn==21.2.0` → `gunicorn==26.0.0`
3. **requests**: `requests==2.31.0` → `requests==2.34.2`
4. **python-dotenv**: `python-dotenv==1.0.0` → `python-dotenv==1.2.2`

**File**: `requirements-dev.txt`

**Specific Changes**:
1. **black**: `black==23.11.0` → `black==26.3.1`
2. **pytest**: `pytest==7.4.3` → `pytest==9.0.3`

**File**: `Dockerfile`

**Specific Changes**:
1. **Builder stage base image**: `python:3.11-slim` → `python:3.12-slim`
2. **Production stage base image**: `python:3.11-slim` → `python:3.12-slim`
3. **Site-packages COPY path**: `/usr/local/lib/python3.11/site-packages` → `/usr/local/lib/python3.12/site-packages`

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, verify the bug condition exists (vulnerable versions pinned), then verify the fix resolves all alerts and preserves runtime behavior.

### Exploratory Bug Condition Checking

**Goal**: Confirm that the current codebase pins vulnerable dependency versions before applying the fix.

**Test Plan**: Parse `requirements.txt`, `requirements-dev.txt`, and `Dockerfile` to assert vulnerable versions are present. This establishes the baseline.

**Test Cases**:
1. **Requirements Version Check**: Assert `requirements.txt` contains `gunicorn==21.2.0`, `requests==2.31.0`, `Flask==3.0.0`, `python-dotenv==1.0.0`
2. **Dev Requirements Version Check**: Assert `requirements-dev.txt` contains `black==23.11.0`, `pytest==7.4.3`
3. **Dockerfile Base Image Check**: Assert Dockerfile contains `python:3.11-slim`
4. **Site-Packages Path Check**: Assert Dockerfile references `python3.11` in site-packages path

**Expected Counterexamples**:
- All assertions pass on unfixed code, confirming the vulnerable state
- After fix, these assertions will fail (demonstrating the bug is resolved)

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed files contain the expected patched versions.

**Pseudocode:**
```
FOR ALL dependency WHERE isBugCondition(dependency) DO
  result := parse_requirements_fixed(dependency)
  ASSERT version(result) >= minimum_patched_version(dependency)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (application runtime behavior), the fixed system produces the same result as the original system.

**Pseudocode:**
```
FOR ALL request WHERE NOT isBugCondition(request) DO
  ASSERT application_behavior_original(request) = application_behavior_fixed(request)
END FOR
```

**Testing Approach**: Integration testing is primary for preservation checking in this case because:
- The changes are version bumps with no application code modifications
- Runtime behavior verification requires actually running the application
- Docker build success confirms dependency compatibility
- Health check success confirms Flask+gunicorn integration

**Test Plan**: Build the Docker image with upgraded dependencies, start the container, and verify health checks pass and existing endpoints respond correctly.

**Test Cases**:
1. **Docker Build Preservation**: Verify the image builds successfully with python:3.12-slim and all upgraded deps
2. **Health Check Preservation**: Verify `/health` endpoint responds 200 after upgrade
3. **Gunicorn Config Preservation**: Verify gunicorn starts with correct bind, workers, and timeout settings
4. **Import Compatibility**: Verify all application imports resolve correctly under Python 3.12

### Unit Tests

- Parse `requirements.txt` and assert each dependency meets minimum patched version
- Parse `requirements-dev.txt` and assert dev dependencies meet minimum patched version
- Parse `Dockerfile` and assert base image is `python:3.12-slim`
- Parse `Dockerfile` and assert site-packages path references `python3.12`

### Property-Based Tests

- Generate random subsets of the dependency list and verify all are at or above patched versions
- Generate version strings and verify the version comparison logic correctly identifies vulnerable vs patched

### Integration Tests

- Build Docker image and verify it completes without errors
- Start container and verify health check passes within timeout
- Verify gunicorn binds on port 8000 and serves requests
- Verify `pip install -r requirements.txt` succeeds in a Python 3.12 environment
- Verify `pip install -r requirements-dev.txt` succeeds and tools (pytest, black) run
