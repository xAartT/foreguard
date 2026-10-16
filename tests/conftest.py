from contextlib import ExitStack
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "foreguard" / "db" / "migrations"
API_KEY = "test-key-" + "x" * 32
KEY_HEADER = "X-Foreguard-Key"

# Variáveis que um .env/ambiente do dev poderia vazar para os testes
SETTINGS_ENV = [
    "DATABASE_URL", "API_HOST", "API_PORT", "DEBUG",
    "THRESHOLD_MEDIUM", "THRESHOLD_HIGH", "THRESHOLD_CRITICAL",
    "ML_MODEL_PATH", "LOG_DIR", "LOG_STORAGE", "FOREGUARD_API_KEY",
    "MAX_REQUEST_BYTES", "MASK_FIELDS",
]


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Ambiente sem .env, sem variáveis do Foreguard e sem arquivo de log."""
    from foreguard.config import get_settings

    monkeypatch.chdir(tmp_path)
    for name in SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOG_DIR", "")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture
def session_factory():
    """SQLite em memória com o schema do modelo."""
    import foreguard.db.models  # noqa: F401 — registra RequestLog no metadata
    from foreguard.db.base import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False)
    engine.dispose()


@pytest.fixture
def make_client(clean_env, monkeypatch, session_factory):
    """
    Constrói um TestClient (lifespan ativo) para um modo de log.
    No modo database, get_session_factory aponta para o SQLite em memória.
    """
    stack = ExitStack()

    def build(storage="database", key=API_KEY, factory=session_factory, **env):
        from foreguard.api.main import create_app
        from foreguard.config import get_settings
        from foreguard.db.session import get_session_factory

        monkeypatch.setenv("LOG_STORAGE", storage)
        if key is not None:
            monkeypatch.setenv("FOREGUARD_API_KEY", key)
        if storage == "database":
            monkeypatch.setenv("DATABASE_URL", "sqlite://")
        for name, value in env.items():
            monkeypatch.setenv(name, str(value))
        get_settings.cache_clear()

        app = create_app()
        if factory is not None:
            app.dependency_overrides[get_session_factory] = lambda: factory
        headers = {KEY_HEADER: key} if key else {}
        return stack.enter_context(TestClient(app, headers=headers))

    yield build
    stack.close()


@pytest.fixture
def client(make_client):
    """Modo database (SQLite em memória), autenticado."""
    return make_client()


@pytest.fixture
def client_mode(make_client):
    """Modo client (sem banco), autenticado."""
    return make_client(storage="client", factory=None)
