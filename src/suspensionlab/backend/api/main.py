import time
import os
from fastapi import FastAPI, Depends, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from suspensionlab.backend.core.errors import AppError
from opentelemetry import trace
from sqlalchemy import text
import uuid as uuid_module
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from suspensionlab.backend.observability import setup_opentelemetry, API_REQUESTS_TOTAL, API_REQUEST_DURATION, generate_latest

# ── Sentry (silent no-op if SENTRY_DSN is not set) ───────────────────────────
_sentry_dsn = os.environ.get("SENTRY_DSN", "")
_env = os.environ.get("ENVIRONMENT", "DEV")

if _sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=_sentry_dsn,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
        )
    except ImportError:
        pass

# Initialize OpenTelemetry
setup_opentelemetry()
from suspensionlab.backend.database.core import engine
from suspensionlab.backend.api.routes import simulate, optimize, analytics, users, jobs
from suspensionlab.backend.config import settings
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.security.rate_limit import RateLimiter
from suspensionlab.backend.core.compute_governance import inline_compute_guard
from suspensionlab.backend.security.logging_config import logging_middleware

from contextlib import asynccontextmanager
from suspensionlab.backend.core.redis_client import init_async_redis, close_async_redis

is_prod_or_trial = _env in ("PROD", "TRIAL")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # SECURITY GATE: refuse to boot in PROD or TRIAL with missing/weak cryptographic secrets.
    from suspensionlab.backend.config import validate_prod_secrets
    validate_prod_secrets()

    # Database migrations are now handled by Alembic in deployment pipelines (Phase 2 Architecture)
    from suspensionlab.backend.observability import validate_alerting_configuration
    import logging
    alert_status = validate_alerting_configuration()
    await init_async_redis()
    
    # Auto-seed development demo users ONLY in DEV
    if _env == "DEV":
        try:
            from suspensionlab.backend.database.seed import seed_demo_users
            await seed_demo_users()
        except Exception as e:
            logging.warning("Demo user seeding warning: %s", e)
    else:
        try:
            from suspensionlab.backend.database.core import engine, Base
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception as e:
            logging.warning("Schema table initialization notice: %s", e)

    yield
    await close_async_redis()


app = FastAPI(
    title="SuspensionLab API",
    lifespan=lifespan,
    docs_url=None if is_prod_or_trial else "/docs",
    redoc_url=None if is_prod_or_trial else "/redoc",
    openapi_url=None if is_prod_or_trial else "/openapi.json",
)

# NOTE: Models are imported inside lifespan() above for table creation.
# No redundant module-level imports needed here.

from suspensionlab.backend.security.idempotency import IdempotencyMiddleware
from suspensionlab.backend.api.middleware import (
    request_id_middleware,
    prometheus_middleware,
    security_headers_middleware,
    payload_size_limit_middleware,
)

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

_frontend_url = (os.environ.get("FRONTEND_URL") or "").strip()
_cors_origins = list(settings.allow_origins_list)
if _frontend_url and _frontend_url not in _cors_origins:
    _cors_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def block_docs_middleware(request: Request, call_next):
    env = os.environ.get("ENVIRONMENT", "DEV")
    if env in ("PROD", "TRIAL"):
        path = request.url.path
        if path in ("/docs", "/redoc", "/openapi.json") or path.startswith("/docs/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return await call_next(request)

app.add_middleware(BaseHTTPMiddleware, dispatch=block_docs_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=prometheus_middleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=logging_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=security_headers_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=payload_size_limit_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_middleware)


from suspensionlab.backend.api.exceptions import register_exception_handlers
register_exception_handlers(app)

# Auto-instrument FastAPI routes for OpenTelemetry Tracing
FastAPIInstrumentor.instrument_app(app)

# Production CORS hardening — already added above as outermost middleware.

# Protect routes with API key
protected = [Depends(verify_api_key)]
app.include_router(simulate.router, prefix="/api/v1", dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))])
app.include_router(simulate.router, dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))])
app.include_router(analytics.router, prefix="/api/v1", dependencies=[Depends(inline_compute_guard), Depends(RateLimiter("rate_limit_simulate"))])
app.include_router(jobs.router, prefix="/api/v1", dependencies=protected)
app.include_router(jobs.router, dependencies=protected)
from suspensionlab.backend.api.routes import profiles
app.include_router(profiles.router, prefix="/api/v1", dependencies=protected)
app.include_router(profiles.router, dependencies=protected)

# --- New Commercial Routes ---
from suspensionlab.backend.api.routes.auth_routes import router as auth_router
app.include_router(
    auth_router,
    prefix="/api/v1",
)
app.include_router(
    auth_router,
)

from suspensionlab.backend.api.routes.billing_routes import router as stripe_billing_router
from suspensionlab.backend.api.routes.gumroad_routes import router as gumroad_billing_router
from suspensionlab.backend.api.routes.session_routes import router as session_router
from suspensionlab.backend.api.routes.device_sessions_routes import router as device_session_router
app.include_router(stripe_billing_router, prefix="/api/v1")
app.include_router(gumroad_billing_router, prefix="/api/v1")
app.include_router(gumroad_billing_router)
app.include_router(session_router, prefix="/api/v1")
app.include_router(device_session_router, prefix="/api/v1")


from suspensionlab.backend.api.routes.api_key_routes import router as api_key_router
app.include_router(api_key_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.export_routes import router as export_router
app.include_router(export_router, prefix="/api/v1", dependencies=protected)
app.include_router(export_router, dependencies=protected)

from suspensionlab.backend.api.routes.report_routes import router as report_router
app.include_router(report_router, prefix="/api/v1", dependencies=protected)
app.include_router(report_router, dependencies=protected)

from suspensionlab.backend.api.websockets import router as websockets_router
app.include_router(websockets_router, prefix="/api/v1")

from suspensionlab.backend.api.routes.audit_routes import router as audit_router
app.include_router(audit_router, prefix="/api/v1", dependencies=protected)
app.include_router(audit_router, dependencies=protected)

from suspensionlab.backend.api.routes.teams_routes import router as teams_router
from suspensionlab.shared.models import PlanTier
app.include_router(teams_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.lap_sim_routes import router as lap_sim_router
app.include_router(lap_sim_router, prefix="/api/v1", dependencies=protected)
app.include_router(lap_sim_router, dependencies=protected)

from suspensionlab.backend.api.routes.kinematics_routes import router as kinematics_router
app.include_router(kinematics_router, prefix="/api/v1", dependencies=[Depends(inline_compute_guard), Depends(RateLimiter("rate_limit_simulate"))])
app.include_router(kinematics_router, dependencies=[Depends(inline_compute_guard), Depends(RateLimiter("rate_limit_simulate"))])

from suspensionlab.backend.api.routes.vehicle_intelligence_routes import router as intelligence_router
app.include_router(intelligence_router, prefix="/api/v1", dependencies=protected)
app.include_router(intelligence_router, dependencies=protected)

from suspensionlab.backend.api.routes.telemetry_routes import router as telemetry_router
app.include_router(telemetry_router, prefix="/api/v1")  # WebSocket endpoint has its own connection manager
app.include_router(telemetry_router)

# --- Observability Endpoints ---

# Protect optimizer with API key AND Rate Limiter
app.include_router(optimize.router, prefix="/api/v1", dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_optimize"))])
app.include_router(optimize.router, dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_optimize"))])

# --- Sensitivity Analysis (Revolutionary Feature) ---
from suspensionlab.backend.api.routes.sensitivity import router as sensitivity_router
app.include_router(
    sensitivity_router,
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))],
)
app.include_router(
    sensitivity_router,
    dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))],
)


# User settings route
app.include_router(users.router, prefix="/api/v1", dependencies=[Depends(RateLimiter("rate_limit_login"))])
app.include_router(users.router, dependencies=[Depends(RateLimiter("rate_limit_login"))])

# ── Revolutionary Features ────────────────────────────────────────────────────
from suspensionlab.backend.api.routes.ai_engineer_routes import router as ai_router
app.include_router(ai_router, prefix="/api/v1", dependencies=[Depends(inline_compute_guard), Depends(RateLimiter("rate_limit_simulate"))])
app.include_router(ai_router, dependencies=[Depends(inline_compute_guard), Depends(RateLimiter("rate_limit_simulate"))])

from suspensionlab.backend.api.routes.share_routes import router as share_router
app.include_router(share_router, prefix="/api/v1")  # GET /reports/{token} is public; POST requires auth via frontend
app.include_router(share_router)

from suspensionlab.backend.api.routes.durability_routes import router as durability_router
app.include_router(durability_router, prefix="/api/v1", dependencies=[Depends(inline_compute_guard), Depends(RateLimiter("rate_limit_simulate"))])
app.include_router(durability_router, dependencies=[Depends(inline_compute_guard), Depends(RateLimiter("rate_limit_simulate"))])

from suspensionlab.backend.api.routes.model_validity_routes import router as model_validity_router
app.include_router(model_validity_router, prefix="/api/v1", dependencies=[Depends(inline_compute_guard), Depends(RateLimiter("rate_limit_simulate"))])
app.include_router(model_validity_router, dependencies=[Depends(inline_compute_guard), Depends(RateLimiter("rate_limit_simulate"))])

from suspensionlab.backend.api.routes.vnv_routes import router as vnv_router
app.include_router(vnv_router, prefix="/api/v1")
app.include_router(vnv_router)

# ── Monetization Tier A ───────────────────────────────────────────────────────
from suspensionlab.backend.api.routes.usage_routes import router as usage_router
app.include_router(usage_router, prefix="/api/v1", dependencies=protected)
app.include_router(usage_router, dependencies=protected)

from suspensionlab.backend.api.routes.score_routes import router as score_router
app.include_router(score_router, prefix="/api/v1", dependencies=[Depends(RateLimiter("rate_limit_simulate"))])
app.include_router(score_router, dependencies=[Depends(RateLimiter("rate_limit_simulate"))])

# ── Trust & compliance (Tier C1) — public by design ──────────────────────────
from suspensionlab.backend.api.routes.trust_routes import router as trust_router
app.include_router(trust_router, prefix="/api/v1")

# ── Outbound webhooks (Tier C2) ───────────────────────────────────────────────
from suspensionlab.backend.api.routes.webhook_routes import router as webhook_router
app.include_router(webhook_router, prefix="/api/v1", dependencies=[Depends(RateLimiter("rate_limit_simulate"))])

from suspensionlab.backend.api.routes.run_routes import router as run_router
app.include_router(run_router, prefix="/api/v1", dependencies=protected)
app.include_router(run_router, dependencies=protected)

from suspensionlab.backend.api.routes.twin_routes import router as twin_router
app.include_router(twin_router, prefix="/api/v1/twins", dependencies=protected)
app.include_router(twin_router, prefix="/twins", dependencies=protected)
app.include_router(twin_router, prefix="/api/v1/twin", dependencies=protected)
app.include_router(twin_router, prefix="/twin", dependencies=protected)

from suspensionlab.backend.api.routes.experiment_routes import router as experiment_router
app.include_router(experiment_router, prefix="/api/v1", dependencies=protected)
app.include_router(experiment_router, dependencies=protected)

from suspensionlab.backend.api.routes.correlation_routes import router as correlation_router
app.include_router(correlation_router, prefix="/api/v1", dependencies=protected)
app.include_router(correlation_router, dependencies=protected)

from suspensionlab.backend.api.routes.decision_routes import router as decision_router
app.include_router(decision_router, prefix="/api/v1", dependencies=protected)
app.include_router(decision_router, dependencies=protected)

from suspensionlab.backend.api.routes.scim_routes import router as scim_router
app.include_router(scim_router, prefix="/api/v1")

from suspensionlab.backend.api.routes.sso_routes import router as sso_router
app.include_router(sso_router, prefix="/api/v1")

from suspensionlab.backend.api.routes.saml_routes import router as saml_router
app.include_router(saml_router, prefix="/api/v1")

from suspensionlab.backend.api.routes.organization_routes import router as org_router
app.include_router(org_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.retention_routes import router as retention_router
app.include_router(retention_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.search_routes import router as search_router
app.include_router(search_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.cae_routes import router as cae_router
app.include_router(cae_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.question_routes import router as question_router
app.include_router(question_router, prefix="/api/v1", dependencies=protected)
app.include_router(question_router, dependencies=protected)

from suspensionlab.backend.api.routes.trial_routes import router as trial_router
app.include_router(trial_router, prefix="/api/v1")
app.include_router(trial_router)

from suspensionlab.backend.api.routes.decision_loop_routes import router as decision_loop_router
app.include_router(decision_loop_router, prefix="/api/v1", dependencies=protected)
app.include_router(decision_loop_router, dependencies=protected)

from suspensionlab.backend.api.routes.setup_engineering_routes import router as setup_engineering_router
app.include_router(setup_engineering_router, prefix="/api/v1", dependencies=protected)
app.include_router(setup_engineering_router, dependencies=protected)

from suspensionlab.backend.api.routes.evidence_graph_routes import router as evidence_graph_router
app.include_router(evidence_graph_router, prefix="/api/v1", dependencies=protected)
app.include_router(evidence_graph_router, dependencies=protected)

from suspensionlab.backend.api.routes.blind_session_routes import router as blind_session_router
app.include_router(blind_session_router, prefix="/api/v1", dependencies=protected)
app.include_router(blind_session_router, dependencies=protected)

from suspensionlab.backend.api.routes.blind_calibration_routes import router as blind_calibration_router
app.include_router(blind_calibration_router, prefix="/api/v1", dependencies=protected)
app.include_router(blind_calibration_router, dependencies=protected)

from suspensionlab.backend.api.routes.parameter_trust_routes import router as parameter_trust_router
app.include_router(parameter_trust_router, prefix="/api/v1", dependencies=protected)
app.include_router(parameter_trust_router, dependencies=protected)

from suspensionlab.backend.api.routes.solver_interop_routes import router as solver_interop_router
app.include_router(solver_interop_router, prefix="/api/v1", dependencies=protected)
app.include_router(solver_interop_router, dependencies=protected)





@app.get("/")
async def root():
    return {"message": "SuspensionLab backend running"}

@app.get("/health")
async def health_check():
    """Liveness probe: confirms the process is alive and accepting connections."""
    return {"status": "alive", "timestamp": time.time()}

@app.get("/api/v1/me")
async def get_current_user(user: dict = Depends(verify_api_key)):
    # Legacy fallback, most places should use UserContext directly via /auth/me
    return {"user_id": user.user_id if hasattr(user, "user_id") else user.get("user_id"), 
            "plan": user.plan if hasattr(user, "plan") else user.get("plan", PlanTier.FREE)}

@app.get("/ready")
async def readiness():
    """
    Readiness probe (Step 5): verifies all critical runtime dependencies are usable:
    - PostgreSQL Database (SELECT 1)
    - Redis Task Queue / Cache (PING)
    Returns HTTP 200 when ready, HTTP 503 if any dependency is impaired.
    """
    from suspensionlab.backend.observability import record_dependency_health
    from suspensionlab.backend.database.core import sync_db_pool_metrics
    from suspensionlab.backend.core.redis_client import get_async_redis

    db_ok = False
    redis_ok = False
    errors = {}

    # Check Database
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        errors["database"] = str(exc)

    # Check Redis
    try:
        r = get_async_redis()
        if r is not None:
            pong = await r.ping()
            if pong:
                redis_ok = True
            else:
                errors["redis"] = "ping returned falsy"
        else:
            # Fallback to checking sync redis connection from RQ
            try:
                from suspensionlab.backend.workers.task_queue import job_queue
                pong = job_queue.connection.ping()
                if pong:
                    redis_ok = True
                else:
                    errors["redis"] = "redis ping returned falsy"
            except Exception as rq_exc:
                errors["redis"] = f"redis client unavailable: {rq_exc}"
    except Exception as exc:
        errors["redis"] = str(exc)

    # Record real dependency health gauges and sync DB pool
    record_dependency_health(db_ok=db_ok, redis_ok=redis_ok)
    sync_db_pool_metrics()

    redis_required = bool((os.getenv("REDIS_URL") or "").strip())
    is_ready = db_ok and (redis_ok or not redis_required)

    if not is_ready:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unready",
                "database": "healthy" if db_ok else "unreachable",
                "redis": "healthy" if redis_ok else ("unreachable" if redis_required else "disabled_in_process"),
                "errors": errors,
            }
        )

    return {
        "status": "ready",
        "database": "healthy",
        "redis": "healthy" if redis_ok else "disabled_in_process",
    }

from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import status
import secrets

metrics_security = HTTPBasic()

def verify_metrics_auth(credentials: HTTPBasicCredentials = Depends(metrics_security)):
    target_user = os.environ.get("METRICS_USERNAME")
    target_pass = os.environ.get("METRICS_PASSWORD")
    if not target_user or not target_pass:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Metrics auth not configured")
    correct_username = secrets.compare_digest(credentials.username, target_user)
    correct_password = secrets.compare_digest(credentials.password, target_pass)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/metrics", dependencies=[Depends(verify_metrics_auth)])
async def metrics():
    """Exposes Prometheus metrics for scraping with fresh pool and queue gauges."""
    from suspensionlab.backend.database.core import sync_db_pool_metrics
    from suspensionlab.backend.workers.orchestrator import refresh_queue_depth
    sync_db_pool_metrics()
    refresh_queue_depth()
    return Response(generate_latest(), media_type="text/plain")


if not is_prod_or_trial:
    from suspensionlab.backend.api.docs import router as docs_router
    app.include_router(docs_router)

