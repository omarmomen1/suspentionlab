# Handoff Report: Sprint 2, Sprint 3, and Phase 2/3 Core Features Implementation Strategy

## 1. Observation

During my investigation of the SuspensionLab codebase, I directly observed the following:

### Routing Prefixing & main.py Syntax Errors
- In `src/suspensionlab/backend/api/main.py`, multiple `app.include_router` calls contain a critical syntax error where a comma is missing between the route path/prefix string and the `dependencies` parameter. This prevents compilation and breaks all tests:
  - **Line 275**: `app.include_router(api_key_router, prefix="/api/v1"dependencies=protected)`
  - **Line 278**: `app.include_router(export_router, prefix="/api/v1"dependencies=protected)`
  - **Line 281**: `app.include_router(report_router, prefix="/api/v1"dependencies=protected)`
  - **Line 287**: `app.include_router(audit_router, prefix="/api/v1"dependencies=protected)`
  - **Line 291**: `app.include_router(teams_router, prefix="/api/v1"dependencies=protected)`
  - **Line 294**: `app.include_router(lap_sim_router, prefix="/api/v1"dependencies=protected)`
  - **Line 320**: `app.include_router(ai_router, prefix="/api/v1"dependencies=[Depends(verify_api_key)])`
  - **Line 326**: `app.include_router(durability_router, prefix="/api/v1"dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))])`
- Running `pytest` fails immediately with:
  ```
  ImportError while loading conftest 'D:\project\tests\conftest.py'.
  tests\conftest.py:14: in <module>
      from suspensionlab.backend.api.main import app
  E     File "D:\project\tests\..\src\suspensionlab\backend\api\main.py", line 275
  E       app.include_router(api_key_router, prefix="/api/v1"dependencies=protected)
  E                                                 ^^^^^^^^^^^^^^^^^^^^^
  E   SyntaxError: invalid syntax. Perhaps you forgot a comma?
  ```
- Many endpoints are currently registered on `app` directly without a prefix:
  - Lines 254-258: `simulate.router`, `analytics.router`, `jobs.router`, `profiles.router` (personal mode endpoints).
  - Line 262: `auth_router`.
  - Line 302: `optimize.router`.
  - Line 305: `sensitivity_router`.
  - Line 313: `checkout.router`.
  - Line 316: `users.router`.
- PDF generation libraries are not listed in `requirements-backend.txt` (which has a packaging typo: `httpx>=0.27.0user-agents>=2.2.0` on Line 23) or in `pyproject.toml` dependencies.

### Team RBAC
- User model (`src/suspensionlab/backend/database/models/user.py`) has:
  - Line 44: `team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)`
- Team model (`src/suspensionlab/backend/database/models/team.py`) has:
  - Line 17: `owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)`
- Team workspace endpoints (`src/suspensionlab/backend/api/routes/teams_routes.py`) hardcodes member roles:
  - Line 82: `members=[TeamMemberResponse(..., role="Owner")]`
  - Lines 111-112: `role="Owner" if m.id == team.owner_id else "Member"`
- There is no `team_role` column or role-based check inside `User` or `teams_routes.py`.

### Priority Queue
- Queue lazy initialization (`src/suspensionlab/backend/workers/queue.py`) has:
  - Lines 17-21:
    ```python
    def _get_job_queue():
        global _job_queue
        if _job_queue is None:
            _job_queue = Queue("default", connection=_get_redis_conn())
        return _job_queue
    ```
  - It exposes a single lazy-loaded `job_queue` representing the `"default"` Redis queue.
- Jobs are submitted to `job_queue` in `optimize.py` (Line 128) and `sweep.py` (Line 100).

### Audit Logs
- Structured JSON logging helper is in `src/suspensionlab/backend/security/audit.py`:
  - Line 29: `def log_audit_event(event_type: str, user_id: str | None = None, ip: str | None = None, metadata: dict[str, Any] | None = None) -> None:`
  - Formats events to standard output stream via a custom logger `JSONAuditFormatter()`.
- Audit routes (`src/suspensionlab/backend/api/routes/audit_routes.py`) contains a broken dependency:
  - Line 42: `from suspensionlab.backend.security.audit import AuditLog`
  - Line 43: `result = await db.execute(select(AuditLog)...)`
  - However, no `AuditLog` class is defined in `security/audit.py` or anywhere else in the codebase, leading to runtime failures on `GET /audit/logs`.

### Physics Engine Natural Frequencies & Sweeps
- Natural frequencies are computed in `src/suspensionlab/physics/full_car.py` inside `calculate_full_car_kpis`:
  - Line 132: `vals, vecs = np.linalg.eig(A)` where `A` is the 14x14 state-space matrix.
  - Natural frequencies are extracted on Line 140: `freq = float(np.imag(vals[i]) / (2 * np.pi))`. Damping ratios and complex eigenvector shapes are not extracted or exposed.
- Sensitivity analysis is in `src/suspensionlab/backend/api/routes/sensitivity.py`, which runs local ±10% finite difference sweeps. There is no ISO 8608 road roughness sensitivity sweep implementation.

### Diff View
- Models `SimSession` (`src/suspensionlab/backend/database/models/session.py`) and `VehicleProfile` (`src/suspensionlab/backend/database/models/profile.py`) exist, but no comparison logic or diffing routes are present.

---

## 2. Logic Chain

1. **Routing Prefixing**: The syntax errors in `main.py` directly crash the FastAPI app compilation (Observation 1.1). Fixing these syntax errors via a comma insertion will restore functionality. To make prefixing consistent and robust without repetition, rather than adding `prefix="/api/v1"` to each individual router, we should instantiate a master router `api_router = APIRouter(prefix="/api/v1")`, include all routes into it, and register it on the `app`. Serving `/docs/api-reference.pdf` requires PDF rendering, which can be accomplished by adding `reportlab` to requirements and writing a PDF builder that parses the output of `app.openapi()`.
2. **Team RBAC**: Currently, the application hardcodes team member roles as `"Owner"` or `"Member"` (Observation 1.7-1.8). Supporting Owner, Admin, and Viewer roles requires adding a persistent `team_role` column to the `User` model. Write paths can then be secured by extracting `team_role` in `verify_api_key`, creating a `require_team_role(["OWNER", "ADMIN"])` dependency, and applying it to modifying endpoints.
3. **Priority Queue**: The queue system currently routes all tasks (simulations, genetic optimization, parameter sweeps) to the `"default"` queue (Observation 1.10). By adding a lazy `priority_queue` mapping to the `"priority"` queue in `queue.py`, and checking the user's plan tier at the API route layer, we can route Enterprise/PRO users to the `"priority"` queue. High-priority workers can then be started as `rq worker priority` (or `rq worker priority default`) to process urgent jobs first.
4. **Audit Logs**: The `GET /audit/logs` route fails because it tries to query a non-existent `AuditLog` database model (Observation 1.12-1.14). To solve this, we must define the `AuditLog` model in SQLAlchemy. The logging helper `log_audit_event` should be augmented with an async db-writing wrapper `log_audit_event_async` that writes to the database for API query and CSV/JSON export endpoints.
5. **Physics**: Eigenvalues (damping ratios, mode shapes) are computed during full-car simulations (Observation 1.15-1.16). By extracting the real and imaginary components of all 7 positive imaginary eigenvalues, we can compute natural frequencies ($\omega_n$), damped frequencies ($\omega_d$), and damping ratios ($\zeta$). Returning the first 7 indices of the complex eigenvectors (displacements) allows the frontend to animate the vehicle's heave, pitch, roll, and hop modes using sinusoidal functions. To implement the ISO 8608 sweep, we can build a 64-simulation grid (8 road classes × 8 parameter steps) run in parallel via a thread pool, returning RMS comfort metric heatmaps.
6. **Diff View**: The `SimSession` model stores snapshots of parameters (`params_snapshot`, Observation 1.18). We can expose a comparison endpoint `/simulate/diff` to fetch two snapshots, perform key-by-key delta analysis, and return aligned telemetry arrays for side-by-side frontend plotting.
7. **Phase 2 & 3**: Worker cancellation is difficult because physics solvers run in thread pools. Implementing a check callback inside SciPy's `solve_ivp` that queries a Redis cancellation key `job:cancelled:{job_id}` will allow clean and immediate solver termination. Progress can be reported by updating Redis status keys with completion percentages. Webhooks can be triggered via `httpx` from the worker handlers. SSO/SCIM prep requires domain connections mapped to Teams, and standard RFC 7643/7644 endpoints under `/scim/v2/`.

---

## 3. Caveats

- **System Compatibility**: The worker cancellation mechanism using a SciPy solver callback relies on active Redis check latency (polling Redis on each integration step). This might add minor overhead to the solver runtime; therefore, the callback should check Redis at a throttled interval (e.g. every 10-50 integration steps or based on simulated time steps) rather than every single step.
- **SSO Connection**: This architecture assumes that user authentication will still produce a valid local JWT token. For SSO, an identity provider configuration interface must be built in Phase 2.
- **SCIM Integration**: Okta SCIM sync operates on standard JSON payloads. The proposed strategy maps this directly to User/Team tables, but requires handling transaction safety during batch provisioning.

---

## 4. Conclusion

Sprint 2, 3, and Phase 2/3 core features are highly viable to implement using the existing codebase structure once the compile-blocking syntax errors in `main.py` are resolved. The following strategy maps out the implementation:

### Sprint 2 Strategy

#### 1. Routing Prefixing & main.py Fixes
- Apply the `.patch` file created in `D:\project\.agents\teamwork_preview_explorer_investigation\main_syntax_fixes.patch` to resolve all compiler-blocking syntax errors.
- Refactor route inclusion in `main.py` using a central API router:
  ```python
  from fastapi import APIRouter
  api_router = APIRouter(prefix="/api/v1")
  
  # Register all sub-routers with api_router
  api_router.include_router(simulate.router, dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))])
  api_router.include_router(analytics.router, dependencies=protected)
  # ... Include all other routers
  
  # Mount the API router
  app.include_router(api_router)
  ```
- Generate OpenAPI Spec PDF:
  - Add `reportlab` to `requirements-backend.txt` (and fix the typo on Line 23).
  - Implement a PDF generator endpoint `/docs/api-reference.pdf` which:
    1. Grabs `app.openapi()` to collect all tags, paths, and models.
    2. Builds a formatted PDF using ReportLab Flowables (Paragraph, Table, PageBreak).
    3. Serves the PDF as `Response(content=pdf_bytes, media_type="application/pdf")`.

#### 2. Team RBAC (Owner, Admin, Viewer)
- In `src/suspensionlab/backend/database/models/user.py`, add:
  ```python
  team_role = Column(String(50), default="VIEWER", nullable=True) # OWNER | ADMIN | VIEWER
  ```
- Create a migration to populate `team_role` for existing users (setting it to `"OWNER"` if they own a team, otherwise `"VIEWER"`).
- In `src/suspensionlab/backend/security/auth.py`, update `verify_api_key` payload:
  ```python
  return {
      "user_id": str(user.id),
      "plan":    user.plan,
      "email":   user.email,
      "name":    user.name or "",
      "onboarding_complete": user.onboarding_complete,
      "team_id": str(user.team_id) if user.team_id else None,
      "team_role": user.team_role if user.team_id else "OWNER",
  }
  ```
- Add the `require_team_role` dependency factory to `auth.py`:
  ```python
  def require_team_role(allowed_roles: list[str]):
      async def dependency(user: dict = Depends(verify_api_key)):
          role = user.get("team_role", "VIEWER")
          if role not in allowed_roles:
              raise HTTPException(status_code=403, detail="Insufficient team permissions.")
          return user
      return dependency
  ```
- Gate all write routes (POST/PUT/PATCH/DELETE on `/simulate/*`, `/profiles/*`, `/optimize/*`) by applying `Depends(require_team_role(["OWNER", "ADMIN"]))`.

---

### Sprint 3 Strategy

#### 3. Priority Queue Setup
- In `src/suspensionlab/backend/workers/queue.py`, add:
  ```python
  _priority_queue = None
  
  def _get_priority_queue():
      global _priority_queue
      if _priority_queue is None:
          _priority_queue = Queue("priority", connection=_get_redis_conn())
      return _priority_queue
  
  class _LazyPriorityQueue:
      def __getattr__(self, name):
          return getattr(_get_priority_queue(), name)
      def enqueue(self, *args, **kwargs):
          return _get_priority_queue().enqueue(*args, **kwargs)
          
  priority_queue = _LazyPriorityQueue()
  ```
- In `optimize.py` (Line 128) and `sweep.py` (Line 100), select the queue based on the user's plan:
  ```python
  from suspensionlab.backend.workers.queue import job_queue, priority_queue
  
  target_queue = priority_queue if user.get("plan") == PlanTier.ENTERPRISE else job_queue
  # Enqueue using target_queue
  ```
- Run workers dedicated to priority:
  - High-priority only: `rq worker priority`
  - Combined priority-first worker: `rq worker priority default`

#### 4. Audit Log Fixes & Export
- Create `src/suspensionlab/backend/database/models/audit_log.py`:
  ```python
  from sqlalchemy import Column, String, DateTime, JSON, UUID, func
  import uuid
  from suspensionlab.backend.database.core import Base
  
  class AuditLog(Base):
      __tablename__ = "audit_logs"
      
      id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      event = Column(String(255), nullable=False)
      user_id = Column(UUID(as_uuid=True), nullable=True)
      ip = Column(String(45), nullable=True)
      timestamp = Column(DateTime(timezone=True), server_default=func.now())
      metadata = Column(JSON, nullable=True)
  ```
- In `src/suspensionlab/backend/security/audit.py`, export the `AuditLog` model so the import inside `audit_routes.py` succeeds.
- Implement an async helper to record log entries:
  ```python
  async def log_audit_event_async(db: AsyncSession, event_type: str, user_id: str | None, ip: str | None, metadata: dict | None = None):
      import uuid
      log_entry = AuditLog(
          event=event_type,
          user_id=uuid.UUID(user_id) if user_id else None,
          ip=ip,
          metadata=metadata or {}
      )
      db.add(log_entry)
      await db.commit()
      log_audit_event(event_type, user_id, ip, metadata) # also write to stdout
  ```
- In `src/suspensionlab/backend/api/routes/audit_routes.py`, add `GET /audit/export`:
  ```python
  @router.get("/export", response_class=Response)
  async def export_audit_logs(
      format: str = "csv",
      user: dict = Depends(verify_api_key),
      db: AsyncSession = Depends(get_db_dependency)
  ):
      plan = user.get("tier", PlanTier.FREE)
      if plan != PlanTier.ENTERPRISE and user.get("user_id") != "admin-001":
          raise HTTPException(status_code=403, detail="Enterprise plan required.")
          
      result = await db.execute(select(AuditLog).order_by(desc(AuditLog.timestamp)))
      logs = result.scalars().all()
      
      if format == "json":
          import json
          data = [{"id": str(log.id), "event": log.event, "user_id": str(log.user_id), "ip": log.ip, "timestamp": log.timestamp.isoformat(), "metadata": log.metadata} for log in logs]
          return Response(content=json.dumps(data), media_type="application/json", headers={"Content-Disposition": "attachment; filename=audit_logs.json"})
      else:
          import csv, io
          output = io.StringIO()
          writer = csv.writer(output)
          writer.writerow(["ID", "Timestamp", "Event", "User ID", "IP", "Metadata"])
          for log in logs:
              writer.writerow([str(log.id), log.timestamp.isoformat(), log.event, str(log.user_id), log.ip, str(log.metadata)])
          return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit_logs.csv"})
  ```

#### 5. Physics: Eigenvalues & ISO 8608 Sweeps
- Eigenvalue extraction in `src/suspensionlab/physics/full_car.py`:
  - Natural Frequency ($f_n$), Damped Frequency ($f_d$), and Damping Ratio ($\zeta$) for each mode `i`:
    $$\omega_n = |\lambda_i| \implies f_n = \omega_n / 2\pi$$
    $$\omega_d = \text{Im}(\lambda_i) \implies f_d = \omega_d / 2\pi$$
    $$\zeta_i = -\text{Re}(\lambda_i) / \omega_n$$
  - Extract the first 7 elements of the eigenvector (displacements $q = [z_s, \theta, \phi, z_{ufl}, z_{ufr}, z_{url}, z_{urr}]^T$) to represent the mode shape amplitude and phase.
  - Return this structured list of 7 modes from the endpoint so the frontend can animate each mode using a sinusoidal interpolation:
    $$q_{node}(t) = |V_{node}| \cos(\omega_d t + \angle V_{node})$$
- ISO 8608 Sensitivity Sweep:
  - Implement a `POST /simulate/sweep/iso8608` endpoint.
  - Generates road profiles matching ISO 8608 Classes A (smooth) to H (rough).
  - Sweeps a select vehicle parameter (e.g. `k_sf` from 15,000 to 45,000 N/m) across 8 increments.
  - Executes the 64 simulations concurrently via `asyncio.gather` wrapping threadpool executors.
  - Returns a 2D matrix representing RMS comfort values for mapping onto a frontend heatmap.

#### 6. Diff View (Comparison Engine)
- Expose a `GET /simulate/diff` endpoint taking `id1` and `id2` query parameters.
- Retrieve both simulation sessions from `SimSession` table.
- Calculate:
  - Numerical parameter deltas: $X_{diff} = X_2 - X_1$, $X_{\%_{diff}} = (X_2 - X_1)/X_1 \times 100$.
  - KPI improvement rates: Comfort (RMS heave accel reduction), mechanical grip (RMS tire load reduction), and travel control.
- If both simulations use identical road profiles and durations, align and return downsampled time-series arrays of displacements (e.g. `z_s`, `theta`, `phi`) so the frontend can display overlapping line plots.

---

### Phase 2 & 3 Strategy

#### 7. Worker Cancellation & Progress Reporting
- Cancellation:
  - Expose `POST /optimize/{job_id}/cancel`. This sets a Redis key `job:cancelled:{job_id}` to `True`.
  - In `src/suspensionlab/physics/quarter_car.py` (and half/full car integrations), pass a callback function to `solve_ivp`:
    ```python
    def check_cancellation(t, y):
        # Read from Redis (using standard sync connection in worker thread)
        if redis_conn.exists(f"job:cancelled:{job_id}"):
            raise JobCancelledError()
    ```
    This instantly aborts running CPU-bound solver math.
- Progress Reporting:
  - Within loops (e.g. generations in GAs, steps in sweeps), calculate progress:
    `progress = (current / total) * 100`.
  - Save progress status back to Redis:
    ```python
    redis_conn.setex(f"job_status:{job_id}", 86400, json.dumps({
        "status": "RUNNING",
        "progress": progress,
        "user_id": user_id
    }))
    ```
  - UI pulls this directly via `GET /optimize/{job_id}/status`.

#### 8. Webhooks & SSO/SCIM
- Webhooks:
  - Model a `webhook_subscriptions` table (fields: URL, secret, subscribed events, active status).
  - In worker success/failure blocks (`unified_worker.py`), query subscriptions for the job owner's team.
  - Generate an HMAC-SHA256 signature of the payload using the webhook secret, include it as a `X-SuspensionLab-Signature` header, and POST the event payload to the URL via `httpx`.
- SSO (SAML 2.0 / OIDC):
  - Model an `sso_connections` table to store domain-to-IdP metadata mappings (SAML Issuer, Login URL, cert).
  - Implement `/auth/sso/login` (redirects user to corporate identity provider) and `/auth/sso/callback` (validates identity assertion and issues local JWT).
- SCIM (User Provisioning):
  - Expose directory sync endpoints complying with SCIM 2.0 (RFC 7643/7644) under `/scim/v2/Users` and `/scim/v2/Groups`.
  - Support GET, POST, PUT, PATCH, and DELETE operations using a dedicated API token generated for the enterprise team's Okta/Azure AD sync utility.

---

## 5. Verification Method

### 1. Verification of Syntax Error
- Run the python pytest collector to verify compilation status:
  ```powershell
  venv\Scripts\pytest
  ```
  - **Before Fix**: Fails during import of `suspensionlab/backend/api/main.py` due to `SyntaxError` at line 275.
  - **After Fix**: Successfully compiles and begins test collection.

### 2. Verification of RBAC
- Write integration tests (e.g., in `tests/api/test_rbac.py`) using `httpx` to verify role gating:
  - Perform write operations (e.g., `POST /api/v1/profiles`) using an API key mapped to a Viewer role. Verify that the response is `HTTP 403 Forbidden` with the details `"Insufficient team permissions."`.
  - Perform the same operation using an API key mapped to an Admin or Owner role and verify it returns `HTTP 201 Created` or `HTTP 200 OK`.

### 3. Verification of Priority Queue
- Enqueue a job using a mock user with `PlanTier.ENTERPRISE` plan. Inspect the Redis queue metadata:
  ```python
  from rq import Queue
  from redis import Redis
  q = Queue("priority", connection=Redis.from_url(redis_url))
  assert job_id in q.job_ids
  ```

### 4. Verification of Audit Export
- Call `GET /api/v1/audit/export?format=csv` using an Enterprise user's API key.
- Verify that response headers contain `Content-Type: text/csv` and `Content-Disposition: attachment; filename=audit_logs.csv`.
- Verify the body contains a CSV header and valid audit log rows matching the database entries.
