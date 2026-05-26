from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.session_auth import GAMMA_SESSION_HEADER, GammaSessionMiddleware, resolve_session_token
from src.api.routes import (
    copilot_router,
    commodities_router,
    crypto_router,
    fundamentals_router,
    iv_router,
    macro_router,
    maritime_router,
    news_router,
    portfolio_router,
    prediction_markets_router,
    research_router,
    risk_router,
    system_router,
)
from src.application.runtime import ApplicationRuntime, get_runtime


def create_app(runtime: ApplicationRuntime | None = None, *, session_token: str | None = None) -> FastAPI:
    owns_runtime = runtime is None
    runtime_instance = runtime or get_runtime()
    resolved_session_token = resolve_session_token(session_token)

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
    app.state.gamma_session_token = resolved_session_token
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
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", GAMMA_SESSION_HEADER],
    )
    app.add_middleware(GammaSessionMiddleware, session_token=resolved_session_token)
    app.include_router(system_router)
    app.include_router(copilot_router)
    app.include_router(commodities_router)
    app.include_router(crypto_router)
    app.include_router(fundamentals_router)
    app.include_router(portfolio_router)
    app.include_router(research_router)
    app.include_router(macro_router)
    app.include_router(maritime_router)
    app.include_router(news_router)
    app.include_router(prediction_markets_router)
    app.include_router(risk_router)
    app.include_router(iv_router)
    return app


app = create_app()
