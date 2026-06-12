# Handoff: Backend Testing Strategy

## 1. Observation
- The project test runner is `pytest`, driven via `python -m pytest` or virtual environment scripts.
- Running `pytest` currently yields `31 passed, 3 warnings in 14.34s`.
- The `tests/` directory contains:
  - `test_physics.py` (24 tests): Comprehensive coverage of backend physics models (`QuarterCar`, `HalfCar`, `MagicFormula`).
  - `test_api.py` (6 tests): Basic health checks, root endpoint tests, and unauthenticated access checks to `/simulate`.
  - `test_integration_e2e.py` (1 test): A singular end-to-end flow from register -> login -> simulate -> checkout.
- Missing API Coverage: There are no unit tests for most of the FastAPI endpoints found in `src/suspensionlab/backend/api/routes/`. This includes `auth_routes.py`, `billing_routes.py`, `api_key_routes.py`, `profiles.py`, `teams_routes.py`, `lap_sim_routes.py`, `optimize.py`, `report_routes.py`, etc.
- Missing Layer Coverage: Database interactions (`database/`), security middleware (`security/`), services, and background workers (`workers/`) lack dedicated test coverage.
- The `pytest-cov` package is missing, making it difficult to generate automated coverage reports.

## 2. Logic Chain
1. **Goal**: Milestone 3 requires a comprehensive pytest suite for the FastAPI backend.
2. **Current State**: Physics logic is well-tested. The API layer and business layers are mostly untested outside of a single happy-path E2E script.
3. **Requirement**: We need to expand test coverage. A flat `tests/` directory will become unwieldy. We must structure the tests to mirror the application architecture.
4. **Strategy Formulation**:
   - **Structure**: Create subdirectories in `tests/` like `tests/api`, `tests/services`, `tests/security`, `tests/database`, and `tests/workers`.
   - **API Tests**: Implement unit tests for each route in `api/routes/` using FastAPI's `TestClient`. Focus on request validation, response schemas, error handling (404, 401, 422), and mock out external services (Stripe, Redis, DB).
   - **Database Tests**: Use SQLAlchemy's test strategies (e.g., an in-memory SQLite database or a test-specific postgres container) to validate CRUD operations and Alembic migrations.
   - **Security Tests**: Validate JWT issuance, expiration, password hashing (`bcrypt`), and rate-limiting limits.
   - **Workers Tests**: Verify task execution logic without needing a running Redis/Celery instance.
5. **Tooling**: Install `pytest-cov` to track and enforce testing progress. Add configuration to `pyproject.toml` to enforce coverage minimums.

## 3. Caveats
- I did not run a full trace on every database model, but the lack of DB tests suggests the ORM logic is currently unverified programmatically.
- The integration test relies on a live-like environment setup. The test strategy requires robust mocking for unit testing endpoints to ensure they are fast and deterministic.
- Stripe logic in the e2e test falls back to expecting a 503 if not configured. True mock implementation is needed for accurate billing tests.

## 4. Conclusion
The testing strategy requires a structured expansion of the pytest suite:
1. Re-organize the `tests/` directory by component (`api/`, `database/`, `security/`, etc.).
2. Focus immediate implementation on writing unit tests using `TestClient` for the 15+ missing API routers.
3. Add `pytest-cov` and set up test coverage reporting.
4. Add unit tests for inner security and database/worker modules.
This comprehensive approach will fulfill the scope of Milestone 3.

## 5. Verification Method
- Install `pytest-cov` (`pip install pytest-cov`).
- Run `python -m pytest --cov=src/suspensionlab/backend tests/` to confirm coverage has increased across the specific modules after tests are added.
- The tests must all pass without critical errors (`pytest`).
