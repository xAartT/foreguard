"""Integração com a aplicação-cliente — specs/integracao.md (INT-*)."""
import re
import statistics
import time
from datetime import UTC, datetime

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from conftest import API_KEY, KEY_HEADER
from samples import EXAMPLE_PAYLOAD, make_request

UTC_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$")
RESPONSE_FIELDS = {
    "log_id", "timestamp", "risk_score", "risk_level",
    "reasons", "recommendation", "analysis_source",
}


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _row(session_factory, log_id):
    from foreguard.db.models import RequestLog

    with session_factory() as db:
        return db.get(RequestLog, log_id)


# ── INT-01: contrato de /v1/analyze ─────────────────────────────────────────

def test_int01_analyze_contract(client_mode):
    resp = client_mode.post("/v1/analyze", json=EXAMPLE_PAYLOAD)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data) == RESPONSE_FIELDS
    assert UTC_ISO.match(data["timestamp"]), data["timestamp"]


# ── INT-02: autenticação ────────────────────────────────────────────────────

@pytest.mark.parametrize("headers", [{}, {KEY_HEADER: "errada"}, {KEY_HEADER: API_KEY + "x"}],
                         ids=["sem-chave", "chave-errada", "chave-maior"])
@pytest.mark.parametrize("method,path", [("POST", "/v1/analyze"), ("GET", "/v1/logs"),
                                         ("GET", "/v1/logs/abc")])
def test_int02_requires_api_key(make_client, headers, method, path):
    c = make_client(key=API_KEY)
    c.headers.pop(KEY_HEADER, None)
    resp = c.request(method, path, json=EXAMPLE_PAYLOAD if method == "POST" else None,
                     headers=headers)
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Chave de API inválida"}


def test_int02_health_is_public(make_client):
    c = make_client(storage="client", factory=None)
    c.headers.pop(KEY_HEADER, None)
    assert c.get("/health").status_code == 200


# ── INT-03: só rotas versionadas ────────────────────────────────────────────

@pytest.mark.parametrize("method,path", [("POST", "/analyze"), ("GET", "/logs"), ("GET", "/logs/a")])
def test_int03_unversioned_routes_do_not_exist(client, method, path):
    resp = client.request(method, path, json=EXAMPLE_PAYLOAD if method == "POST" else None)
    assert resp.status_code == 404


# ── INT-04: chave obrigatória no startup ────────────────────────────────────

@pytest.mark.parametrize("key", [None, "", "curta" * 6], ids=["ausente", "vazia", "30-chars"])
def test_int04_startup_requires_strong_key(clean_env, monkeypatch, key):
    from foreguard.api.main import create_app
    from foreguard.config import get_settings

    monkeypatch.setenv("LOG_STORAGE", "client")
    if key is not None:
        monkeypatch.setenv("FOREGUARD_API_KEY", key)
    get_settings.cache_clear()
    with pytest.raises(Exception, match="FOREGUARD_API_KEY"):
        with TestClient(create_app()):
            pass


# ── INT-05: bind local, sem CORS ────────────────────────────────────────────

def test_int05_default_host_is_loopback(clean_env):
    from foreguard.config import Settings

    assert Settings().API_HOST == "127.0.0.1"
    assert "CORS_ORIGINS" not in Settings.model_fields


def test_int05_no_cors_middleware(client_mode):
    assert all(m.cls is not CORSMiddleware for m in client_mode.app.user_middleware)


# ── INT-06: modo client ─────────────────────────────────────────────────────

def test_int06_client_mode_never_touches_database(make_client, monkeypatch):
    import foreguard.db.session as session_module

    def no_db(*args, **kwargs):
        raise AssertionError("modo client não deve criar engine")

    monkeypatch.setattr(session_module, "create_engine", no_db)
    c = make_client(storage="client", factory=None)
    assert c.post("/v1/analyze", json=EXAMPLE_PAYLOAD).status_code == 200


@pytest.mark.parametrize("path", ["/v1/logs", "/v1/logs/abc"])
def test_int06_client_mode_has_no_logs_routes(client_mode, path):
    assert client_mode.get(path).status_code == 404


# ── INT-07: modo database ───────────────────────────────────────────────────

def test_int07_database_mode_persists_same_result(client, session_factory):
    data = client.post("/v1/analyze", json=EXAMPLE_PAYLOAD).json()
    row = _row(session_factory, data["log_id"])
    assert row is not None
    assert (row.risk_score, row.risk_level) == (data["risk_score"], data["risk_level"])
    stored = row.timestamp if row.timestamp.tzinfo else row.timestamp.replace(tzinfo=UTC)
    assert stored == _parse_utc(data["timestamp"])


# ── INT-08: falha de gravação não derruba a análise ─────────────────────────

class BrokenSession:
    instances: list = []

    def __init__(self):
        self.rolled_back = False
        BrokenSession.instances.append(self)

    def add(self, obj):
        pass

    def commit(self):
        raise OperationalError("INSERT", {}, Exception("db down"))

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def test_int08_write_failure_still_returns_analysis(make_client):
    BrokenSession.instances = []
    c = make_client(factory=BrokenSession)
    resp = c.post("/v1/analyze", json=EXAMPLE_PAYLOAD)
    assert resp.status_code == 200
    assert set(resp.json()) == RESPONSE_FIELDS
    assert BrokenSession.instances and all(s.rolled_back for s in BrokenSession.instances)


# ── INT-09: /health informa o modo ──────────────────────────────────────────

@pytest.mark.parametrize("storage", ["client", "database"])
def test_int09_health_reports_log_storage(make_client, storage):
    c = make_client(storage=storage)
    assert c.get("/health").json()["log_storage"] == storage


# ── INT-10 .. INT-12: mascaramento ──────────────────────────────────────────

SENSITIVE_REQUEST = make_request(
    method="POST",
    path="/checkout",
    headers={
        "User-Agent": "Mozilla/5.0",
        "Authorization": "Bearer abc.def.ghi",
        "Cookie": "session=xyz",
        "X-Api-Key": "k-123",
        "Accept": "application/json",
    },
    query_params={"api_key": "q-123", "page": "2"},
    body={
        "username": "ana",
        "password": "s3cr3t",
        "user_token": "t-1",
        "card": {"number": "4111111111111111", "cvv": "123"},
        "items": [{"sku": "A1", "senha": "x"}],
        "Documento_CPF": "123.456.789-00",
    },
    jwt_token="eyJhbGciOi.payload.sig",
)


def _persisted_raw(client, session_factory, payload):
    data = client.post("/v1/analyze", json=payload).json()
    return data, _row(session_factory, data["log_id"]).raw_request


def test_int10_sensitive_data_is_masked(client, session_factory):
    _, raw = _persisted_raw(client, session_factory, SENSITIVE_REQUEST)

    assert raw["jwt_token"] == "***"
    headers = raw["headers"]
    for name in ("Authorization", "Cookie", "X-Api-Key"):
        assert headers[name] == "***", name
    assert headers["User-Agent"] == "Mozilla/5.0"
    assert headers["Accept"] == "application/json"

    assert raw["query_params"] == {"api_key": "***", "page": "2"}

    body = raw["body"]
    assert body["username"] == "ana"
    assert body["password"] == "***"
    assert body["user_token"] == "***"
    assert body["card"] == "***"
    assert body["items"] == [{"sku": "A1", "senha": "***"}]
    assert body["Documento_CPF"] == "***"


def test_int10_jwt_absent_stays_null(client, session_factory):
    _, raw = _persisted_raw(client, session_factory, make_request(jwt_token=None))
    assert raw["jwt_token"] is None


def test_int11_extra_mask_fields(make_client, session_factory):
    c = make_client(MASK_FIELDS='["rg"]')
    payload = make_request(method="POST", body={"rg": "12.345.678-9", "nome": "Ana"})
    _, raw = _persisted_raw(c, session_factory, payload)
    assert raw["body"] == {"rg": "***", "nome": "Ana"}


def test_int12_detection_uses_original_values(client, session_factory):
    payload = make_request(method="POST", path="/login",
                           body={"username": "ana", "password": "' OR '1'='1"})
    data, raw = _persisted_raw(client, session_factory, payload)
    assert any("SQL" in r for r in data["reasons"])
    assert raw["body"]["password"] == "***"


# ── INT-13: limite de tamanho ───────────────────────────────────────────────

def test_int13_oversized_request_is_rejected(make_client, monkeypatch):
    import foreguard.api.routes.analyze as analyze_module

    def must_not_run(*args, **kwargs):
        raise AssertionError("análise não deveria executar")

    c = make_client(storage="client", factory=None, MAX_REQUEST_BYTES=1000)
    monkeypatch.setattr(analyze_module.analyzer, "analyze", must_not_run)
    payload = make_request(method="POST", body={"q": "a" * 2000})
    assert c.post("/v1/analyze", json=payload).status_code == 413


def test_int13_request_under_limit_is_accepted(make_client):
    c = make_client(storage="client", factory=None, MAX_REQUEST_BYTES=5000)
    payload = make_request(method="POST", body={"q": "a" * 2000})
    assert c.post("/v1/analyze", json=payload).status_code == 200


# ── INT-14: LOG_STORAGE inválido ────────────────────────────────────────────

def test_int14_invalid_log_storage(clean_env, monkeypatch):
    from foreguard.config import Settings

    monkeypatch.setenv("LOG_STORAGE", "arquivo")
    with pytest.raises(ValidationError, match="LOG_STORAGE"):
        Settings()


# ── INT-15: latência em modo client ─────────────────────────────────────────

def test_int15_client_mode_latency(client_mode):
    payload = make_request(method="POST", path="/users",
                           body={"name": "Ana", "email": "ana@ex.com"},
                           query_params={"page": "1"})
    client_mode.post("/v1/analyze", json=payload)  # aquecimento
    durations = []
    for _ in range(100):
        start = time.perf_counter()
        assert client_mode.post("/v1/analyze", json=payload).status_code == 200
        durations.append(time.perf_counter() - start)
    assert statistics.median(durations) < 0.020
