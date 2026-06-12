# Handoff: Backend Testing Strategy

## Observation
- Currently, 31 tests are passing when running `python -m pytest c:\Users\omaar\Downloads\project\tests`.
- **High Coverage in Physics**: `tests/test_physics.py` contains 24 robust tests for the Quarter Car, Half Car, and Magic Formula models.
- **Low Coverage in API Routes**: `tests/test_api.py` has only 6 tests, covering basic endpoints like `/`, `/health`, and a basic check on `/simulate`.
- **E2E coverage**: `tests/test_integration_e2e.py` has 1 integration flow test covering auth, basic quarter-car simulation, and checkout.
- **Uncovered Areas**: `src/suspensionlab/backend/api/routes` contains over 20 route modules (e.g., `auth_routes.py`, `billing_routes.py`, `lap_sim_routes.py`, `users.py`, `telemetry_routes.py`, `websockets.py`, etc.) that have zero dedicated test coverage.
- **Tooling**: `tests/conftest.py` is essentially empty. Test setup involves verbose inline patching (as seen in `test_api.py`). Coverage tools like `pytest-cov` and mocking utilities like `pytest-mock` are missing from `pyproject.toml`.

## Logic Chain
1. The system's core physics calculations are well-tested, meaning the risk is concentrated in the API, business logic, and integrations layer.
2. Because there are no centralized fixtures in `conftest.py`, any new tests written for the API will require repetitive and fragile patching of SQLAlchemy sessions, Redis instances, and Stripe API calls.
3. To achieve comprehensive coverage:
    - **Tooling upgrade:** We must add `pytest-cov` to measure our baseline and target. `pytest-mock` will simplify the heavy patching required for external services.
    - **Centralized Fixtures:** We need to populate `tests/conftest.py` with standard fixtures: `db_session` (mocked or in-memory SQLite), `redis_mock`, `authenticated_client`, and `admin_client`.
    - **Systematic Test Expansion:** We need to map test files to the route domains. For instance, creating `tests/api/test_auth.py`, `tests/api/test_billing.py`, and `tests/api/test_simulations.py`.
    - **Async Client:** Since FastAPI uses async endpoints heavily, we should consider using `httpx.AsyncClient` for route testing instead of the synchronous `fastapi.testclient.TestClient`.

## Caveats
- I did not deeply analyze the specific business logic inside each uncovered route.
- Depending on how tightly coupled the database logic is to the route handlers, mocking the DB via `AsyncMock` might become too complex, and using an in-memory SQLite database for tests might be preferable.
- External integrations (like Stripe in billing) must be strictly mocked to prevent network calls during testing.

## Conclusion
The backend testing strategy should be executed in three phases:
1. **Infrastructure**: Update `pyproject.toml` with `pytest-cov` and `pytest-mock`. Overhaul `conftest.py` to provide reusable database, Redis, and authenticated HTTP client fixtures.
2. **Coverage Expansion**: Systematically create unit tests for all uncovered route modules in `src/suspensionlab/backend/api/routes/`, starting with critical paths like authentication, user management, and simulation endpoints.
3. **Integration & Telemetry**: Write specific tests for websocket connections and background job handling (RQ/Redis).

## Verification Method
1. Run the existing suite: `python -m pytest c:\Users\omaar\Downloads\project\tests` (Currently 31 tests pass).
2. To verify the new strategy during implementation, run `python -m pytest c:\Users\omaar\Downloads\project\tests --cov=src/suspensionlab/backend` and ensure coverage increases systematically as new test files are added.
