from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from pretrend.api.db import dispose_engine
from pretrend.api.routers import eod, explain, health, macro, meta, regime, report, similarity
from pretrend.api.schemas import ErrorResponse
from pretrend.api.settings import get_api_settings


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_api_settings()
    app = FastAPI(
        title="Pretrend Observability API",
        description=(
            "Read-only API for market structure observability "
            "(regime / similarity / macro / EOD / explainability)"
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_credentials=False,
        allow_headers=["X-API-Key", "Content-Type"],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts,
    )
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _generic_exception_handler)
    app.include_router(health.router)
    app.include_router(meta.router)
    app.include_router(regime.router)
    app.include_router(similarity.router)
    app.include_router(macro.router)
    app.include_router(eod.router)
    app.include_router(explain.router)
    app.include_router(report.router)
    return app


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        payload = exc.detail
    else:
        payload = ErrorResponse(detail=str(exc.detail)).model_dump(exclude_none=True)
    return JSONResponse(status_code=exc.status_code, content=payload)


async def _validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


async def _generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = str(uuid4())
    logger.exception("unhandled API error request_id=%s", request_id)
    payload = ErrorResponse(
        detail="Internal server error",
        request_id=request_id,
    ).model_dump(exclude_none=True)
    return JSONResponse(status_code=500, content=payload)


app = create_app()
