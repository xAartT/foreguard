"""Migrações Alembic — specs/arquitetura.md (ARQ-05)."""
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect

from conftest import MIGRATIONS_DIR, ROOT


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def test_arq05_upgrade_matches_model_and_downgrade_drops(clean_env, monkeypatch):
    from foreguard.config import get_settings
    from foreguard.db.models import RequestLog

    url = f"sqlite:///{clean_env / 'mig.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    cfg = _alembic_config()

    command.upgrade(cfg, "head")
    engine = create_engine(url)
    insp = sa_inspect(engine)
    assert "request_logs" in insp.get_table_names()

    db_cols = {c["name"]: c["nullable"] for c in insp.get_columns("request_logs")}
    model_cols = {c.name: c.nullable for c in RequestLog.__table__.columns}
    assert db_cols == model_cols

    indexed = {col for ix in insp.get_indexes("request_logs") for col in ix["column_names"]}
    assert {"timestamp", "ip", "risk_level"} <= indexed
    engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(url)
    assert "request_logs" not in sa_inspect(engine).get_table_names()
    engine.dispose()
