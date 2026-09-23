from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import router
from app.core.config import get_settings
from app.core.errors import AppError
from app.db import Base
from app.db.session import engine


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        approved_extras = (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "assessment_id",
            "stage",
            "provider",
            "model",
            "exception_class",
        )
        for field in approved_extras:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info and "exception_class" not in payload:
            exception_type = record.exc_info[0]
            if exception_type is not None:
                payload["exception_class"] = exception_type.__name__
        return json.dumps(payload, ensure_ascii=False)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
logger = logging.getLogger("shambalens")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # Only the local adapter touches the disk. Serverless hosts such as Vercel
    # mount the app read-only, so creating the directory there regardless
    # crashed every cold start even though Firebase storage never uses it.
    if settings.image_storage == "local":
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
    # Alembic owns PostgreSQL migrations; this keeps the SQLite developer default runnable.
    if settings.async_database_url.startswith("sqlite"):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="ShambaLens AI API",
    version="1.0.0",
    description="Evidence-first crop triage with uncertainty and independent verification.",
    lifespan=lifespan,
)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Shamba-Token", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next: Any) -> Any:
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception(
            "HTTP request failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "exception_class": type(exc).__name__,
            },
        )
        raise
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    logger.info(
        "HTTP request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return response


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
    details: Any = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "request_id": getattr(request.state, "request_id", str(uuid4())),
                "details": jsonable_encoder(details),
            }
        },
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        retryable=exc.retryable,
        details=exc.details,
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        code, message = "not_found", "Route not found."
    elif exc.status_code == 405:
        code, message = "method_not_allowed", "Method not allowed for this route."
    else:
        code = "http_error"
        message = exc.detail if isinstance(exc.detail, str) else "The request could not be handled."
    return _error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(
        request,
        status_code=422,
        code="validation_error",
        message="The request data is invalid.",
        details=exc.errors(),
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database operation failed", exc_info=exc)
    return _error_response(
        request,
        status_code=503,
        code="database_unavailable",
        message="The database is temporarily unavailable.",
        retryable=True,
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error", exc_info=exc)
    return _error_response(
        request,
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred.",
    )


app.include_router(router)
