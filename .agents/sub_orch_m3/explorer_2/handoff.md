# Handoff Report: Backend Testing Strategy

## Observation
- **Existing Tests**: Running `.\venv\Scripts\pytest` executes 31 passing tests across three files: `tests/test_api.py`, `tests/test_physics.py`, and `tests/test_integration_e2e.py`.
- **Current Coverage**:
  - `test_physics.py` adequately covers the core domain logic (`quarter_car.py`, `half_car.py`, `magic_formula.py`).
  - API testing is extremely sparse. `test_api.py` tests only `/health`, `/simulate` (auth failures), and generic error handling. `test_integration_e2e.py` tests a basic `register -> login -> simulate -> checkout` flow.
- **Uncovered Areas**: The FastAPI router in `src/suspensionlab/backend/api/routes/` contains over 16 modules (`auth_routes.py`, `teams_routes.py`, `api_key_routes.py`, `billing_routes.py`, `optimize.py`, `profiles.py`, `telemetry_routes.py`, etc.) that lack dedicated API tests.
- **Architecture**: Almost all endpoints in `routes/` request the database session via FastAPI's dependency injection `Depends(get_db_dependency)`.
- **Tooling**: `pytest-cov` and `pytest-mock` are not installed (missing from `requirements-backend.txt` and `venv`). `test_api.py` relies heavily on standard library `unittest.mock` to monkey-patch the SQLAlchemy engine globally, which is brittle and prevents testing actual database queries.

## Logic Chain
1. **Dependency Overrides**: Since endpoints use `Depends(get_db_dependency)`, we can and should use FastAPI's `app.dependency_overrides[get_db_dependency]` to inject an isolated test database (e.g., in-memory SQLite via `aiosqlite`) or a mock session, rather than monkey-patching `engine` globally.
2. **Structural Organization**: The monolithic `test_api.py` does not scale. To support comprehensive coverage, tests must be split into a structured `tests/api/` directory (e.g., `test_auth.py`, `test_teams.py`, `test_billing.py`, `test_simulation.py`, `test_profiles.py`).
3. **Fixture Management**: A central `tests/conftest.py` should be expanded to provide reusable fixtures:
   - `client`: A configured `TestClient` with dependency overrides.
   - `db_session`: A transaction-rolled-back database session or in-memory DB.
   - `mock_redis` / `mock_stripe`: For rate limiting, background jobs (RQ), and billing.
   - `auth_token`: Pre-authenticated user contexts.
4. **Tooling Enhancement**: Adding `pytest-cov`, `pytest-mock`, and optionally `fakeredis` or `httpx` (to resolve StarletteDeprecationWarning) is necessary to measure success and implement robust mocks.

## Caveats
- Moving to an in-memory SQLite database (`aiosqlite`) for tests might hide PostgreSQL-specific syntax errors if any raw SQL is used (though ORM usage seems prevalent). If raw Postgres features are used, a tool like `pytest-postgresql` or `testcontainers` would be required instead.
- Background jobs using `rq` might need special test workers or mocks to execute synchronously during tests.

## Conclusion
To achieve Milestone 3, the implementer should:
1. Update test dependencies (`pytest-cov`, `pytest-mock`, `httpx`, `pytest-asyncio`).
2. Revamp `tests/conftest.py` to provide robust fixtures (specifically overriding `get_db_dependency` using a test DB setup).
3. Create a `tests/api/` directory and implement test modules for all major route groups (`auth`, `teams`, `billing`, `profiles`, `simulate`, `api_keys`).
4. Ensure target test coverage (e.g., >80%) is met across the `src/suspensionlab/backend` package.

## Verification Method
- Execute the tests using: `.\venv\Scripts\pytest`
- Once `pytest-cov` is installed, verify coverage using: `.\venv\Scripts\pytest --cov=src/suspensionlab/backend --cov-report=term-missing`
- Inspect the output to ensure that the newly created `tests/api/*.py` files are executed and that coverage metrics have improved significantly.
