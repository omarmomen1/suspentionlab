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
        if _env == "PROD":
            raise RuntimeError("CRITICAL: sentry_sdk is missing but SENTRY_DSN is provided in PROD environment.")
elif _env == "PROD":
    raise RuntimeError("CRITICAL: SENTRY_DSN is required in PROD environment.")

# Initialize OpenTelemetry
setup_opentelemetry()
from suspensionlab.backend.database.core import engine
from suspensionlab.backend.api.routes import simulate, optimize, analytics, users, jobs
from suspensionlab.backend.billing import checkout
from suspensionlab.backend.config import settings
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.security.rate_limit import RateLimiter
from suspensionlab.backend.security.logging_config import logging_middleware

from contextlib import asynccontextmanager
from suspensionlab.backend.core.redis_client import init_async_redis, close_async_redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    # SECURITY GATE: refuse to boot in PROD with missing/weak cryptographic secrets.
    from suspensionlab.backend.config import validate_prod_secrets
    validate_prod_secrets()

    # Database migrations are now handled by Alembic in deployment pipelines (Phase 2 Architecture)
    await init_async_redis()
    yield
    await close_async_redis()

app = FastAPI(title="SuspensionLab API", lifespan=lifespan)

# NOTE: Models are imported inside lifespan() above for table creation.
# No redundant module-level imports needed here.

from suspensionlab.backend.security.idempotency import IdempotencyMiddleware
from suspensionlab.backend.api.middleware import request_id_middleware, prometheus_middleware, security_headers_middleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(BaseHTTPMiddleware, dispatch=prometheus_middleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=logging_middleware)
# app.add_middleware(BaseHTTPMiddleware, dispatch=security_headers_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_middleware)

from suspensionlab.backend.api.exceptions import register_exception_handlers
register_exception_handlers(app)

# Auto-instrument FastAPI routes for OpenTelemetry Tracing
FastAPIInstrumentor.instrument_app(app)

# Production CORS hardening — already added above as outermost middleware.

# Protect routes with API key
protected = [Depends(verify_api_key)]
app.include_router(simulate.router, prefix="/api/v1", dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))])
app.include_router(analytics.router, prefix="/api/v1", dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))])
app.include_router(jobs.router, prefix="/api/v1", dependencies=protected)
from suspensionlab.backend.api.routes import profiles
app.include_router(profiles.router, prefix="/api/v1", dependencies=protected)

# --- New Commercial Routes ---
from suspensionlab.backend.api.routes.auth_routes import router as auth_router
app.include_router(
    auth_router,
    prefix="/api/v1",
    dependencies=[Depends(RateLimiter("rate_limit_auth"))]
)

from suspensionlab.backend.api.routes.lemon_squeezy_routes import router as billing_router
from suspensionlab.backend.api.routes.session_routes import router as session_router
from suspensionlab.backend.api.routes.device_sessions_routes import router as device_session_router
from suspensionlab.backend.api.routes.billing_routes import router as legacy_billing_router
app.include_router(billing_router, prefix="/api/v1")
app.include_router(session_router, prefix="/api/v1")
app.include_router(device_session_router, prefix="/api/v1")
app.include_router(legacy_billing_router, prefix="/api/v1")


from suspensionlab.backend.api.routes.api_key_routes import router as api_key_router
app.include_router(api_key_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.export_routes import router as export_router
app.include_router(export_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.report_routes import router as report_router
app.include_router(report_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.websockets import router as websockets_router
app.include_router(websockets_router, prefix="/api/v1")

from suspensionlab.backend.api.routes.audit_routes import router as audit_router
app.include_router(audit_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.teams_routes import router as teams_router
from suspensionlab.shared.models import PlanTier
app.include_router(teams_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.lap_sim_routes import router as lap_sim_router
app.include_router(lap_sim_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.kinematics_routes import router as kinematics_router
app.include_router(kinematics_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.vehicle_intelligence_routes import router as intelligence_router
app.include_router(intelligence_router, prefix="/api/v1", dependencies=protected)


from suspensionlab.backend.api.routes.telemetry_routes import router as telemetry_router
app.include_router(telemetry_router, prefix="/api/v1")  # WebSocket endpoint has its own connection manager

# --- Observability Endpoints ---

# Protect optimizer with API key AND Rate Limiter
app.include_router(optimize.router, prefix="/api/v1", dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_optimize"))])

# --- Sensitivity Analysis (Revolutionary Feature) ---
from suspensionlab.backend.api.routes.sensitivity import router as sensitivity_router
app.include_router(
    sensitivity_router,
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))],
)

# Public webhook route
# webhooks moved to billing_routes
app.include_router(checkout.router, prefix="/api/v1", dependencies=[Depends(RateLimiter("rate_limit_checkout"))])

# User settings route
app.include_router(users.router, prefix="/api/v1", dependencies=[Depends(RateLimiter("rate_limit_login"))])

# ── Revolutionary Features ────────────────────────────────────────────────────
from suspensionlab.backend.api.routes.ai_engineer_routes import router as ai_router
app.include_router(ai_router, prefix="/api/v1", dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))])

from suspensionlab.backend.api.routes.share_routes import router as share_router
app.include_router(share_router, prefix="/api/v1")  # GET /reports/{token} is public; POST requires auth via frontend

from suspensionlab.backend.api.routes.durability_routes import router as durability_router
app.include_router(durability_router, prefix="/api/v1", dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))])

from suspensionlab.backend.api.routes.model_validity_routes import router as model_validity_router
app.include_router(model_validity_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.vnv_routes import router as vnv_router
app.include_router(vnv_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.run_routes import router as run_router
app.include_router(run_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.twin_routes import router as twin_router
app.include_router(twin_router, prefix="/api/v1", dependencies=protected)

from suspensionlab.backend.api.routes.scim_routes import router as scim_router
app.include_router(scim_router, prefix="/api/v1")

from suspensionlab.backend.api.routes.sso_routes import router as sso_router
app.include_router(sso_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "SuspensionLab backend running"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/v1/me")
async def get_current_user(user: dict = Depends(verify_api_key)):
    # Legacy fallback, most places should use UserContext directly via /auth/me
    return {"user_id": user.user_id if hasattr(user, "user_id") else user.get("user_id"), 
            "plan": user.plan if hasattr(user, "plan") else user.get("plan", PlanTier.FREE)}

@app.get("/ready")
async def readiness():
    # Check DB is reachable
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database is unavailable")

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
    """Exposes Prometheus metrics for scraping."""
    return Response(generate_latest(), media_type="text/plain")


from suspensionlab.backend.api.docs import router as docs_router
app.include_router(docs_router)

