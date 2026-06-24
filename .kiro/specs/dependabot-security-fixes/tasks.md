# Implementation Plan

## Overview

Bugfix implementation for resolving 13 Dependabot security alerts by upgrading production and development dependencies and migrating the Docker base image from python:3.11-slim to python:3.12-slim. No application code changes are needed — only version pins in requirements files and Dockerfile paths.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Vulnerable Dependency Versions Pinned
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate vulnerable versions are pinned
  - **Scoped PBT Approach**: Parse requirements.txt, requirements-dev.txt, and Dockerfile to verify all dependencies meet minimum patched versions
  - Test that `requirements.txt` contains `gunicorn>=26.0.0`, `requests>=2.34.2`, `Flask>=3.1.3`, `python-dotenv>=1.2.2`
  - Test that `requirements-dev.txt` contains `black>=26.3.1`, `pytest>=9.0.3`
  - Test that `Dockerfile` uses `python:3.12-slim` base image (not `python:3.11-slim`)
  - Test that `Dockerfile` site-packages path references `python3.12` (not `python3.11`)
  - Use Hypothesis to generate random subsets of the dependency list and verify all are at or above patched versions
  - Bug condition from design: `isBugCondition(input)` returns true when any dependency version is below its patched minimum or Dockerfile references python3.11
  - Expected behavior: all parsed versions >= minimum patched version for each CVE
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists by finding vulnerable versions)
  - Document counterexamples found (e.g., "gunicorn==21.2.0 < 26.0.0", "Dockerfile uses python:3.11-slim")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Application Configuration and Runtime Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: `gunicorn.conf.py` binds on `0.0.0.0:8000` with sync workers, 2 default workers, 500s timeout on unfixed code
  - Observe: Flask app imports and creates app successfully on unfixed code
  - Observe: `docker-compose.yml` healthcheck uses `python3 -c "import urllib.request; ..."` on unfixed code
  - Observe: Dockerfile creates non-root `appuser` and runs as that user on unfixed code
  - Observe: All existing pytest tests pass on unfixed code
  - Write property-based tests verifying:
    - Gunicorn config values are preserved: bind="0.0.0.0:8000", worker_class="sync", timeout=500, workers=2 (default)
    - Flask app can be created and `/health` endpoint is registered
    - All application module imports succeed (app.main, app handlers, etc.)
    - Dockerfile structure preserves non-root user, EXPOSE 8000, healthcheck, and gunicorn CMD
  - Use Hypothesis where applicable to generate varied environment configurations and verify gunicorn config stability
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 3. Fix for Dependabot security vulnerabilities in dependency versions

  - [x] 3.1 Upgrade production dependencies in requirements.txt
    - Change `Flask==3.0.0` to `Flask==3.1.3`
    - Change `gunicorn==21.2.0` to `gunicorn==26.0.0`
    - Change `requests==2.31.0` to `requests==2.34.2`
    - Change `python-dotenv==1.0.0` to `python-dotenv==1.2.2`
    - Leave other dependencies (tenacity, structlog, jsonschema) unchanged
    - _Bug_Condition: isBugCondition(input) where input.gunicorn_version < "26.0.0" OR input.requests_version < "2.34.2" OR input.flask_version < "3.1.3" OR input.python_dotenv_version < "1.2.2"_
    - _Expected_Behavior: All production dependencies at or above minimum patched versions_
    - _Preservation: tenacity==8.2.3, structlog==23.2.0, jsonschema==4.20.0 remain unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.8_

  - [x] 3.2 Upgrade development dependencies in requirements-dev.txt
    - Change `black==23.11.0` to `black==26.3.1`
    - Change `pytest==7.4.3` to `pytest==9.0.3`
    - Leave other dev dependencies (pytest-flask, pytest-mock, hypothesis, responses, flake8, mypy, pytest-cov) unchanged
    - _Bug_Condition: isBugCondition(input) where input.black_version < "26.3.1" OR input.pytest_version < "9.0.3"_
    - _Expected_Behavior: All dev dependencies at or above minimum patched versions_
    - _Preservation: pytest-flask==1.3.0, pytest-mock==3.12.0, hypothesis==6.92.1, responses==0.24.1, flake8==6.1.0, mypy==1.7.1, pytest-cov==4.1.0 remain unchanged_
    - _Requirements: 2.5, 2.6, 2.8_

  - [x] 3.3 Upgrade Dockerfile base image and site-packages path
    - Change builder stage `FROM python:3.11-slim AS builder` to `FROM python:3.12-slim AS builder`
    - Change production stage `FROM python:3.11-slim` to `FROM python:3.12-slim`
    - Change `COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages` to `COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages`
    - Preserve all other Dockerfile structure: non-root appuser, EXPOSE 8000, healthcheck, gunicorn CMD, tzdata installation
    - _Bug_Condition: isBugCondition(input) where input.docker_base_image != "python:3.12-slim" OR input.site_packages_path CONTAINS "python3.11"_
    - _Expected_Behavior: Dockerfile uses python:3.12-slim and references python3.12 in site-packages path_
    - _Preservation: Non-root user, port binding, healthcheck, gunicorn CMD, timezone config all unchanged_
    - _Requirements: 2.7, 2.8, 2.9, 3.7, 3.8_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - All Dependencies at Patched Versions
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (all versions >= minimum patched)
    - When this test passes, it confirms all 13 Dependabot alerts are resolved
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Application Configuration and Runtime Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm gunicorn config, Flask app creation, imports, and Dockerfile structure are all preserved
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite with `pytest` to confirm all existing tests pass with upgraded dependencies
  - Verify Docker build succeeds with `docker compose build`
  - Verify container starts and health check passes
  - Ensure all tests pass, ask the user if questions arise.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3"] },
    { "id": 3, "tasks": ["3.4", "3.5"] },
    { "id": 4, "tasks": ["4"] }
  ]
}
```

## Notes

- This is a dependency-only fix: no application code changes are needed
- gunicorn 26.0.0 requires Python 3.12+, which drives the Docker base image upgrade
- The Dockerfile site-packages path must change from python3.11 to python3.12 to match the new base image
- All tests should be run within the venv using `python3` commands
- Docker builds should use `docker compose build` (not `docker-compose`)
