from functools import lru_cache

from fastapi import Depends
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from foreguard.config import get_settings


def require_database_url() -> str:
    url = get_settings().DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL não configurada — defina no .env ou no ambiente")
    return url


@lru_cache
def _engine_for(url: str) -> Engine:
    options = {"pool_pre_ping": True}   # reconecta automaticamente se a conexão cair
    if not url.startswith("sqlite"):
        options.update(pool_size=10, max_overflow=20)
    return create_engine(url, **options)


@lru_cache
def _session_factory_for(url: str) -> sessionmaker:
    return sessionmaker(bind=_engine_for(url), autocommit=False, autoflush=False)


def get_engine() -> Engine:
    """Engine criado na primeira utilização, um por DATABASE_URL."""
    return _engine_for(require_database_url())


def get_session_factory() -> sessionmaker:
    """Dependency do FastAPI — fábrica de sessões (sobrescrita nos testes)."""
    return _session_factory_for(require_database_url())


def get_db(factory: sessionmaker = Depends(get_session_factory)):
    """Dependency do FastAPI — injeta sessão do banco nas rotas."""
    db = factory()
    try:
        yield db
    finally:
        db.close()
