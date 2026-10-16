import sys
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from loguru import logger

from foreguard import __version__
from foreguard.api.routes.analyze import build_router as build_analyze_router
from foreguard.api.routes.logs import router as logs_router
from foreguard.api.security import require_api_key, require_valid_key_config
from foreguard.config import Settings, get_settings
from foreguard.db.session import require_database_url


# ── Logging ──────────────────────────────────────────────────────────────────
def configure_logging(settings: Settings) -> None:
    logger.remove()
    logger.add(sys.stdout, colorize=True, format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")
    if settings.LOG_DIR:
        logger.add(
            str(settings.LOG_DIR / "foreguard_{time:YYYY-MM-DD}.log"),
            rotation="00:00", retention="30 days", serialize=True,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Falha cedo, com mensagem clara
    require_valid_key_config()
    if settings.LOG_STORAGE == "database":
        require_database_url()
    configure_logging(settings)
    logger.info(f"Foreguard iniciando (logs: {settings.LOG_STORAGE})...")
    logger.info(f"API disponível em http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"Docs em http://{settings.API_HOST}:{settings.API_PORT}/docs")
    yield


# ── App ───────────────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title       = "Foreguard",
        description = "Middleware de segurança inteligente para análise de risco de requisições HTTP",
        version     = __version__,
        lifespan    = lifespan,
    )

    # Tráfego servidor-a-servidor (middleware local): sem CORS
    v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])
    v1.include_router(build_analyze_router(settings.LOG_STORAGE), tags=["Análise"])
    if settings.LOG_STORAGE == "database":
        v1.include_router(logs_router, tags=["Logs"])
    app.include_router(v1)

    @app.get("/health", tags=["Sistema"])
    async def health():
        return {
            "status": "online",
            "version": __version__,
            "log_storage": get_settings().LOG_STORAGE,
        }

    return app


app = create_app()


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from foreguard.cli import main

    sys.exit(main(["serve"]))
