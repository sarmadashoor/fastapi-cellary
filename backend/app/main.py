"""
Backend main
Starts FASTAPI app
"""

import logging
from typing import Any, Callable

import app.config as app_config  # to not shadow global app var with FastAPI app
from app.logging_config import configure_logging, get_logger
import app.db.session as app_session
import sqlalchemy.exc
import sqlalchemy.orm.exc
from app.api.exception_handlers import (
    db_exception_handler,
    db_not_found_exception_handler,
    general_exception_handler,
    unhandled_exception_middleware,
    validation_exception_handler,
)
from app.api.routing import TAGS, router
from app.config import API_V1_STR
from app.middleware.rate_limiting import rate_limit_middleware
from app.middleware.observability import ObservabilityMiddleware
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

# Configure structured logging
configure_logging(log_level="INFO")
logger = get_logger(__name__)


app = FastAPI(
    title="FastAPI service template",
    openapi_tags=TAGS,
    description="[API summary](https://example.com)",
    version="1.0.0",
    exception_handlers={
        Exception: general_exception_handler,
        RequestValidationError: validation_exception_handler,
        sqlalchemy.exc.IntegrityError: db_exception_handler,
        sqlalchemy.orm.exc.NoResultFound: db_not_found_exception_handler,
    },
)

# Add CORS middleware with enhanced security for resume processing
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",        # Local development
        "http://localhost:8000",        # Local API testing
        "https://yourdomain.com",       # Production domain
        "https://app.yourdomain.com",   # Production app subdomain
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Explicit method list
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Content-Language",
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ],
    expose_headers=[
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining", 
        "X-RateLimit-Reset",
        "Retry-After",
    ],
    max_age=86400,  # Cache preflight response for 24 hours
)

# Add observability middleware (first for comprehensive monitoring)
app.add_middleware(ObservabilityMiddleware, collect_detailed_metrics=True)

# Add rate limiting middleware
app.middleware("http")(rate_limit_middleware)

app.middleware("http")(unhandled_exception_middleware)
app.include_router(router, prefix=API_V1_STR)


@app.middleware("http")
async def db_session_middleware(
    request: Request,
    call_next: Callable[[Request], Any],
) -> Any:
    """
    Opens DB session for each API request
    """
    try:
        request.state.db = app_session.get_session(app_config.get_config())
        response = await call_next(request)
    except Exception as e:
        logger.error(
            "Database session middleware error",
            extra={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "request_path": request.url.path,
                "request_method": request.method,
                "event": "db_session_error"
            }
        )
        raise
    finally:
        request.state.db.close()
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
