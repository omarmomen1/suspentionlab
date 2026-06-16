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
from suspensionlab.backend.billing import checkout
from suspensionlab.backend.config import settings
from suspensionlab.backend.security.auth import verify_api_key
from suspensionlab.backend.security.rate_limit import RateLimiter
from suspensionlab.backend.security.logging_config import logging_middleware

async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "0"  # Modern browsers ignore it; CSP supersedes it
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://assets.lemonsqueezy.com https://cdn.plot.ly 'unsafe-eval' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.lemonsqueezy.com; "
        "frame-ancestors 'none';"
    )
    return response

from contextlib import asynccontextmanager
from suspensionlab.backend.api.routes.optimize import init_async_redis, close_async_redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    from suspensionlab.backend.database.core import engine, Base
    from suspensionlab.backend.database.models.job import JobRecord  # noqa: F401
    from suspensionlab.backend.database.models.billing import LemonEvent  # noqa: F401
    from suspensionlab.backend.database.models.user import User  # noqa: F401
    from suspensionlab.backend.database.models.profile import VehicleProfile # noqa: F401
    from suspensionlab.backend.database.models.shared_report import SharedReport  # noqa: F401
    
    async with engine.begin() as conn:
        # Tables are managed by Alembic in production.
        # await conn.run_sync(Base.metadata.create_all)
        
        # Dev/local auto-seed
        if settings.environment == "DEV":
            from sqlalchemy import select, func
            result = await conn.execute(select(func.count()).select_from(User))
            count = result.scalar()
            
            if count == 0:
                from suspensionlab.backend.security.jwt_utils import hash_password
                await conn.execute(
                    User.__table__.insert().values(
                        email="admin@suspensionlab.pro",
                        password_hash=hash_password("change-me-immediately"),
                        api_key=settings.api_key,
                        onboarding_complete=False,
                        plan="ENTERPRISE",
                        is_admin=True
                    )
                )
        
    await init_async_redis()
    yield
    await close_async_redis()

app = FastAPI(title="SuspensionLab API", lifespan=lifespan)

# NOTE: Models are imported inside lifespan() above for table creation.
# No redundant module-level imports needed here.

# 1. Define all middleware functions
from suspensionlab.backend.security.logging_config import request_id_ctx

async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid_module.uuid4()))
    request_id_ctx.set(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

async def prometheus_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
        
    start_time = time.time()
    method = request.method
    route = request.url.path
    
    try:
        response = await call_next(request)
        status_code = response.status_code
        API_REQUESTS_TOTAL.labels(method=method, route=route, status_code=status_code).inc()
        API_REQUEST_DURATION.labels(method=method, route=route).observe(time.time() - start_time)
        return response
    except Exception as e:
        API_REQUESTS_TOTAL.labels(method=method, route=route, status_code=500).inc()
        API_REQUEST_DURATION.labels(method=method, route=route).observe(time.time() - start_time)
        raise e

from suspensionlab.backend.security.idempotency import IdempotencyMiddleware

# CORS must be added first so it is the outermost middleware layer.
# All other middleware wraps inside it, ensuring preflight OPTIONS
# requests get CORS headers before any auth/rate-limit middleware fires.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Add remaining middleware in reverse order (last added = outermost of these)
app.add_middleware(BaseHTTPMiddleware, dispatch=prometheus_middleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=logging_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=security_headers_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_middleware)

@app.exception_handler(AppError)
async def app_error_handler(request, exc: AppError):
    span = trace.get_current_span()
    request_id = request_id_ctx.get()
    if span and span.is_recording():
        span.record_exception(exc)
        span.set_status(trace.status.Status(trace.status.StatusCode.ERROR))
        span.set_attribute("error.type", exc.__class__.__name__)
        span.set_attribute("error.message", str(exc))
        span.set_attribute("request_id", request_id)
        
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code, 
            "message": exc.message, 
            "request_id": request_id
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    span = trace.get_current_span()
    request_id = request_id_ctx.get()
    if span and span.is_recording():
        span.record_exception(exc)
        span.set_status(trace.status.Status(trace.status.StatusCode.ERROR))
        span.set_attribute("error.type", exc.__class__.__name__)
        span.set_attribute("error.message", str(exc.errors()))
        span.set_attribute("request_id", request_id)
        
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error", 
            "message": "Invalid request payload", 
            "details": exc.errors(),
            "request_id": request_id
        }
    )

@app.exception_handler(404)
async def not_found_handler(request, exc):
    span = trace.get_current_span()
    request_id = request_id_ctx.get()
    detail = getattr(exc, "detail", "Not found")
    if span and span.is_recording():
        span.record_exception(exc)
        span.set_status(trace.status.Status(trace.status.StatusCode.ERROR))
        span.set_attribute("error.type", exc.__class__.__name__)
        span.set_attribute("error.message", str(detail))
        span.set_attribute("request_id", request_id)
        
    return JSONResponse(
        status_code=404,
        content={
            "error": "not_found", 
            "message": detail, 
            "request_id": request_id
        }
    )

@app.exception_handler(500)
async def server_error_handler(request, exc):
    span = trace.get_current_span()
    request_id = request_id_ctx.get()
    if span and span.is_recording():
        span.record_exception(exc)
        span.set_status(trace.status.Status(trace.status.StatusCode.ERROR))
        span.set_attribute("error.type", exc.__class__.__name__)
        span.set_attribute("error.message", str(exc))
        span.set_attribute("request_id", request_id)
        
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error", 
            "message": "Internal server error", 
            "request_id": request_id
        }
    )

# NOTE: RequestValidationError is handled above at line 129.
# The duplicate handler that was here has been removed to prevent
# silent override of the correct handler.

# Auto-instrument FastAPI routes for OpenTelemetry Tracing
FastAPIInstrumentor.instrument_app(app)

# Production CORS hardening — already added above as outermost middleware.

# Protect routes with API key
protected = [Depends(verify_api_key)]
app.include_router(simulate.router, dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))])
app.include_router(analytics.router, dependencies=protected)
app.include_router(jobs.router, dependencies=protected)
from suspensionlab.backend.api.routes import profiles
app.include_router(profiles.router, dependencies=protected)

# --- New Commercial Routes ---
from suspensionlab.backend.api.routes.auth_routes import router as auth_router
app.include_router(
    auth_router,
    dependencies=[Depends(RateLimiter("rate_limit_auth"))]
)

from suspensionlab.backend.api.routes.gumroad_routes import router as billing_router
from suspensionlab.backend.api.routes.session_routes import router as session_router
app.include_router(billing_router, prefix="/api/v1")
app.include_router(session_router)

from suspensionlab.backend.api.routes.api_key_routes import router as api_key_router
app.include_router(api_key_router, dependencies=protected)

from suspensionlab.backend.api.routes.export_routes import router as export_router
app.include_router(export_router, dependencies=protected)

from suspensionlab.backend.api.routes.report_routes import router as report_router
app.include_router(report_router, dependencies=protected)

from suspensionlab.backend.api.websockets import router as websockets_router
app.include_router(websockets_router)

from suspensionlab.backend.api.routes.audit_routes import router as audit_router
app.include_router(audit_router, dependencies=protected)

from suspensionlab.backend.api.routes.teams_routes import router as teams_router
from suspensionlab.shared.models import PlanTier
app.include_router(teams_router, dependencies=protected)

from suspensionlab.backend.api.routes.lap_sim_routes import router as lap_sim_router
app.include_router(lap_sim_router, dependencies=protected)

from suspensionlab.backend.api.routes.telemetry_routes import router as telemetry_router
app.include_router(telemetry_router)  # WebSocket endpoint has its own connection manager

# --- Observability Endpoints ---

# Protect optimizer with API key AND Rate Limiter
app.include_router(optimize.router, dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_optimize"))])

# --- Sensitivity Analysis (Revolutionary Feature) ---
from suspensionlab.backend.api.routes.sensitivity import router as sensitivity_router
app.include_router(
    sensitivity_router,
    dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))],
)

# Public webhook route
# webhooks moved to billing_routes
app.include_router(checkout.router, dependencies=[Depends(RateLimiter("rate_limit_checkout"))])

# User settings route
app.include_router(users.router, dependencies=[Depends(RateLimiter("rate_limit_login"))])

# ── Revolutionary Features ────────────────────────────────────────────────────
from suspensionlab.backend.api.routes.ai_engineer_routes import router as ai_router
app.include_router(ai_router, dependencies=[Depends(verify_api_key)])

from suspensionlab.backend.api.routes.share_routes import router as share_router
app.include_router(share_router)  # GET /reports/{token} is public; POST requires auth via frontend

from suspensionlab.backend.api.routes.durability_routes import router as durability_router
app.include_router(durability_router, dependencies=[Depends(verify_api_key), Depends(RateLimiter("rate_limit_simulate"))])

@app.get("/")
async def root():
    return {"message": "SuspensionLab backend running"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/me")
async def get_current_user(user: dict = Depends(verify_api_key)):
    return {"user_id": user["user_id"], "plan": user.get("plan", PlanTier.FREE)}

@app.get("/ready")
async def readiness():
    # Check DB is reachable
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database is unavailable")

@app.get("/metrics", dependencies=[Depends(verify_api_key)])
async def metrics():
    """Exposes Prometheus metrics for scraping."""
    return Response(generate_latest(), media_type="text/plain")
