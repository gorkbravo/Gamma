from src.api.routes.iv import router as iv_router
from src.api.routes.portfolio import router as portfolio_router
from src.api.routes.research import router as research_router
from src.api.routes.risk import router as risk_router
from src.api.routes.system import router as system_router

__all__ = [
    "iv_router",
    "portfolio_router",
    "research_router",
    "risk_router",
    "system_router",
]
