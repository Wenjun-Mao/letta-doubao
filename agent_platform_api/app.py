from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_platform_api.routers import (
    agents,
    commenting,
    core,
    labeling,
    platform_meta,
    platform_runtime,
    prompt_center,
    schema_center,
    tool_center,
)
from agent_platform_api.runtime import APP_VERSION, validate_platform_capabilities_startup


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    validate_platform_capabilities_startup()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent Platform API",
        version=APP_VERSION,
        summary="Runtime and control APIs for ADE and local Agent Platform workflows",
        lifespan=app_lifespan,
        description=(
            "Provides versioned API routes for Agent Platform runtime/control/test orchestration. "
            "Designed for backend-first API consumption and ADE frontend integration."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(core.router)
    app.include_router(agents.router)
    app.include_router(platform_meta.router)
    app.include_router(prompt_center.router)
    app.include_router(schema_center.router)
    app.include_router(tool_center.router)
    app.include_router(platform_runtime.router)
    app.include_router(commenting.router)
    app.include_router(labeling.router)
    return app


app = create_app()

