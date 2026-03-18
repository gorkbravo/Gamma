from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import (
    iv_router,
    portfolio_router,
    prediction_markets_router,
    research_router,
    risk_router,
    system_router,
)
from src.application.runtime import ApplicationRuntime, get_runtime


def create_app(runtime: ApplicationRuntime | None = None) -> FastAPI:
    owns_runtime = runtime is None
    runtime_instance = runtime or get_runtime()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime_instance
        yield
        if owns_runtime:
            runtime_instance.shutdown()

    app = FastAPI(
        title="Gamma API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.runtime = runtime_instance
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(system_router)
    app.include_router(portfolio_router)
    app.include_router(research_router)
    app.include_router(prediction_markets_router)
    app.include_router(risk_router)
    app.include_router(iv_router)
    return app


app = create_app()
