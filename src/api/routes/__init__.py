from src.api.routes.copilot import router as copilot_router
from src.api.routes.crypto import router as crypto_router
from src.api.routes.fundamentals import router as fundamentals_router
from src.api.routes.iv import router as iv_router
from src.api.routes.macro import router as macro_router
from src.api.routes.portfolio import router as portfolio_router
from src.api.routes.prediction_markets import router as prediction_markets_router
from src.api.routes.research import router as research_router
from src.api.routes.risk import router as risk_router
from src.api.routes.system import router as system_router

__all__ = [
    "copilot_router",
    "crypto_router",
    "fundamentals_router",
    "iv_router",
    "macro_router",
    "portfolio_router",
    "prediction_markets_router",
    "research_router",
    "risk_router",
    "system_router",
]
