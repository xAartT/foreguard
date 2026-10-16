"""API — specs/arquitetura.md (ARQ-04, 06 .. 14), ajustada por specs/integracao.md."""
import inspect
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect

from conftest import API_KEY, KEY_HEADER, ROOT, SETTINGS_ENV
from samples import EXAMPLE_PAYLOAD


def _subprocess_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in SETTINGS_ENV}
    env["PYTHONPATH"] = str(ROOT)
    env["LOG_DIR"] = ""
    env.update(extra)
    return env


# ── ARQ-04: import sem DATABASE_URL; startup (modo database) falha ───────────

def test_arq04_import_does_not_require_database_url(tmp_path):
    code = "import foreguard.core.analyzer, foreguard.api.main"
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=_subprocess_env(),
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_arq04_database_mode_startup_fails_without_database_url(clean_env, monkeypatch):
    from foreguard.api.main import create_app
    from foreguard.config import get_settings

    monkeypatch.setenv("LOG_STORAGE", "database")
    monkeypatch.setenv("FOREGUARD_API_KEY", API_KEY)
    get_settings.cache_clear()
    with pytest.raises(Exception, match="DATABASE_URL"):
        with TestClient(create_app()):
            pass


# ── ARQ-06: startup não cria tabelas ─────────────────────────────────────────

def test_arq06_startup_does_not_create_tables(clean_env, monkeypatch):
    from foreguard.api.main import create_app
    from foreguard.config import get_settings

    url = f"sqlite:///{clean_env / 'empty.db'}"
    monkeypatch.setenv("LOG_STORAGE", "database")
    monkeypatch.setenv("FOREGUARD_API_KEY", API_KEY)
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        assert c.get("/health").status_code == 200
    engine = create_engine(url)
    assert sa_inspect(engine).get_table_names() == []
    engine.dispose()


# ── /health ──────────────────────────────────────────────────────────────────

def test_health_reports_package_version(client):
    import foreguard

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "online", "version": foreguard.__version__, "log_storage": "database",
    }


# ── ARQ-07: /v1/analyze persiste o resultado (modo database) ────────────────

def test_arq07_analyze_persists_log(client, session_factory):
    from foreguard.db.models import RequestLog

    resp = client.post("/v1/analyze", json=EXAMPLE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    with session_factory() as db:
        row = db.get(RequestLog, data["log_id"])
    assert row is not None
    assert row.risk_score == data["risk_score"]
    assert row.risk_level == data["risk_level"]


# ── ARQ-08: rota síncrona ────────────────────────────────────────────────────

def test_arq08_analyze_route_is_sync():
    from foreguard.api.routes.analyze import analyze_request

    assert not inspect.iscoroutinefunction(analyze_request)


# ── ARQ-10 .. ARQ-12: /v1/logs ───────────────────────────────────────────────

@pytest.fixture
def seeded(session_factory):
    from foreguard.db.models import RequestLog

    base = datetime(2026, 1, 1, 12, 0, 0)  # naive, como o SQLite devolve
    rows = [
        ("a", base, "LOW", "1.1.1.1"),
        ("b", base + timedelta(minutes=1), "HIGH", "2.2.2.2"),
        ("c", base + timedelta(minutes=2), "HIGH", "1.1.1.1"),
    ]
    with session_factory() as db:
        for log_id, ts, level, ip in rows:
            db.add(RequestLog(
                id=log_id, timestamp=ts, method="GET", path="/", ip=ip,
                user_agent="ua", risk_score=1.0, risk_level=level,
                reasons=[], raw_request={"path": "/"},
            ))
        db.commit()
    return rows


def test_arq10_logs_ordered_desc(client, seeded):
    ids = [log["log_id"] for log in client.get("/v1/logs").json()]
    assert ids == ["c", "b", "a"]


def test_arq10_logs_limit(client, seeded):
    assert len(client.get("/v1/logs", params={"limit": 2}).json()) == 2


@pytest.mark.parametrize("limit", [0, 501])
def test_arq10_logs_limit_out_of_range(client, limit):
    assert client.get("/v1/logs", params={"limit": limit}).status_code == 422


def test_arq10_logs_filter_level_case_insensitive(client, seeded):
    ids = {log["log_id"] for log in client.get("/v1/logs", params={"level": "high"}).json()}
    assert ids == {"b", "c"}


def test_arq10_logs_filter_ip(client, seeded):
    ids = {log["log_id"] for log in client.get("/v1/logs", params={"ip": "1.1.1.1"}).json()}
    assert ids == {"a", "c"}


def test_arq10_logs_invalid_level(client):
    assert client.get("/v1/logs", params={"level": "FOO"}).status_code == 422


def test_arq10_logs_summary_shape(client, seeded):
    log = client.get("/v1/logs").json()[0]
    assert set(log) == {
        "log_id", "timestamp", "method", "path", "ip",
        "risk_score", "risk_level", "reasons",
    }


def test_arq11_log_detail(client, seeded):
    resp = client.get("/v1/logs/b")
    assert resp.status_code == 200
    data = resp.json()
    assert data["log_id"] == "b"
    assert "id" not in data
    assert data["user_agent"] == "ua"
    assert data["raw_request"] == {"path": "/"}


def test_arq11_log_not_found(client):
    resp = client.get("/v1/logs/nao-existe")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Log não encontrado"}


UTC_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$")


def test_arq12_timestamps_are_utc_iso(client, seeded):
    for log in client.get("/v1/logs").json():
        assert UTC_ISO.match(log["timestamp"]), log["timestamp"]
    detail = client.get("/v1/logs/a").json()
    assert UTC_ISO.match(detail["timestamp"]), detail["timestamp"]
    assert detail["timestamp"].startswith("2026-01-01T12:00:00")


# ── ARQ-13: sem DeprecationWarning do projeto ────────────────────────────────

WARNINGS_SCRIPT = textwrap.dedent("""
    import warnings
    warnings.simplefilter("always")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from fastapi.testclient import TestClient
        from foreguard.config import get_settings
        from foreguard.api.main import create_app
        from foreguard.db.base import Base
        from foreguard.db.session import get_engine
        import foreguard.db.models
        get_settings()
        Base.metadata.create_all(get_engine())
        with TestClient(create_app(), headers={KEY_HEADER: API_KEY}) as c:
            assert c.post("/v1/analyze", json=PAYLOAD).status_code == 200
    markers = ("on_event", "class-based `config`", "utcnow")
    for w in caught:
        if not issubclass(w.category, DeprecationWarning):
            continue
        if w.filename.startswith(PKG_DIR) or any(m in str(w.message) for m in markers):
            print(f"WARN: {w.filename}:{w.lineno}: {w.message}")
""")


def test_arq13_no_project_deprecation_warnings(tmp_path):
    # PKG_DIR: só o pacote do projeto (o venv também fica sob a raiz do repo)
    script = (
        f"PAYLOAD = {EXAMPLE_PAYLOAD!r}\n"
        f"PKG_DIR = {str(ROOT / 'foreguard') + os.sep!r}\n"
        f"API_KEY = {API_KEY!r}\nKEY_HEADER = {KEY_HEADER!r}\n"
        + WARNINGS_SCRIPT
    )
    env = _subprocess_env(
        DATABASE_URL=f"sqlite:///{tmp_path / 'w.db'}",
        LOG_STORAGE="database",
        FOREGUARD_API_KEY=API_KEY,
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env,
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    # stdout também recebe os logs da app; só as linhas WARN: importam
    offending = [line for line in proc.stdout.splitlines() if line.startswith("WARN: ")]
    assert offending == []


# ── ARQ-14: log em arquivo configurado no startup ───────────────────────────

def test_arq14_log_file_created_on_startup_only(clean_env, monkeypatch):
    from foreguard.api.main import create_app
    from foreguard.config import get_settings

    log_dir = clean_env / "logs"
    monkeypatch.setenv("LOG_DIR", str(log_dir))
    monkeypatch.setenv("LOG_STORAGE", "client")
    monkeypatch.setenv("FOREGUARD_API_KEY", API_KEY)
    get_settings.cache_clear()

    app = create_app()
    assert not log_dir.exists() or not any(log_dir.iterdir())
    with TestClient(app):
        pass
    assert log_dir.exists() and any(log_dir.iterdir())


def test_arq14_empty_log_dir_creates_no_file(client, clean_env):
    client.get("/health")
    assert not (clean_env / "logs").exists()
