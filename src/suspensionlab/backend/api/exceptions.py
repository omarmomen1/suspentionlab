from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from suspensionlab.backend.core.errors import AppError
from opentelemetry import trace
from suspensionlab.backend.security.logging_config import request_id_ctx

def register_exception_handlers(app):
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
                "type": f"https://api.suspensionlab.com/errors/{exc.code}",
                "title": "Application Error",
                "status": exc.status_code,
                "detail": exc.message,
                "instance": request.url.path,
                "request_id": request_id
            },
            headers={"Content-Type": "application/problem+json"}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        span = trace.get_current_span()
        request_id = request_id_ctx.get()
        
        # Clean validation errors to make sure they are JSON serializable
        cleaned_errors = []
        for err in exc.errors():
            err_copy = dict(err)
            if "ctx" in err_copy and isinstance(err_copy["ctx"], dict):
                ctx_copy = dict(err_copy["ctx"])
                for k, v in ctx_copy.items():
                    if isinstance(v, Exception):
                        ctx_copy[k] = str(v)
                err_copy["ctx"] = ctx_copy
            cleaned_errors.append(err_copy)
            
        if span and span.is_recording():
            span.record_exception(exc)
            span.set_status(trace.status.Status(trace.status.StatusCode.ERROR))
            span.set_attribute("error.type", exc.__class__.__name__)
            span.set_attribute("error.message", str(cleaned_errors))
            span.set_attribute("request_id", request_id)
            
        return JSONResponse(
            status_code=422,
            content={
                "type": "https://api.suspensionlab.com/errors/validation_error",
                "title": "Validation Error",
                "status": 422,
                "detail": "Invalid request payload",
                "errors": cleaned_errors,
                "instance": request.url.path,
                "request_id": request_id
            },
            headers={"Content-Type": "application/problem+json"}
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
                "type": "https://api.suspensionlab.com/errors/not_found",
                "title": "Not Found",
                "status": 404,
                "detail": detail,
                "instance": request.url.path,
                "request_id": request_id
            },
            headers={"Content-Type": "application/problem+json"}
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
                "type": "https://api.suspensionlab.com/errors/internal_error",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "Internal server error",
                "instance": request.url.path,
                "request_id": request_id
            },
            headers={"Content-Type": "application/problem+json"}
        )
