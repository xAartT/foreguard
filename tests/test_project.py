"""Layout, empacotamento e config — specs/arquitetura.md (ARQ-01..03, 16..18)."""
import ast
import os
import subprocess
import sys
import tomllib

import joblib
import pytest

from conftest import ROOT

# ── ARQ-01: layout de pacote ─────────────────────────────────────────────────

def test_arq01_no_application_modules_at_root():
    assert sorted(p.name for p in ROOT.glob("*.py")) == []


@pytest.mark.parametrize("module", [
    "foreguard/__init__.py",
    "foreguard/config.py",
    "foreguard/api/main.py",
    "foreguard/api/schemas.py",
    "foreguard/api/routes/analyze.py",
    "foreguard/api/routes/logs.py",
    "foreguard/core/analyzer.py",
    "foreguard/core/extractor.py",
    "foreguard/core/rules.py",
    "foreguard/core/ml_model.py",
    "foreguard/db/base.py",
    "foreguard/db/models.py",
    "foreguard/db/session.py",
    "foreguard/db/migrations/env.py",
    "foreguard/db/migrations/versions/0001_create_request_logs.py",
])
def test_arq01_package_layout(module):
    assert (ROOT / module).is_file()


def test_arq01_no_root_migrations_dir():
    assert not (ROOT / "migrations").exists()


# ── ARQ-02: pyproject ────────────────────────────────────────────────────────

EXPECTED_DEPS = {
    "fastapi==0.111.0", "uvicorn==0.30.0", "pydantic==2.7.0",
    "pydantic-settings==2.3.0", "python-dotenv==1.0.1",
    "sqlalchemy==2.0.30", "alembic==1.13.1", "psycopg2-binary==2.9.9",
    "scikit-learn==1.5.0", "xgboost==2.0.3", "joblib==1.4.2",
    "pandas==2.2.2", "numpy==1.26.4", "user-agents==2.2.0",
    "loguru==0.7.2",
}


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def _names(reqs) -> set[str]:
    return {r.split("==")[0].split(">")[0].split("<")[0].strip().lower() for r in reqs}


def test_arq02_pyproject_dependencies():
    project = _pyproject()["project"]
    assert EXPECTED_DEPS <= {d.lower() for d in project["dependencies"]}
    assert "python-jose" not in _names(project["dependencies"])


def test_arq02_dev_extra():
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    assert {"pytest", "httpx", "ruff"} <= _names(dev)


def test_arq02_requirements_txt_removed():
    assert not (ROOT / "requirements.txt").exists()


# ── ARQ-03: pytest roda da raiz sem DATABASE_URL ─────────────────────────────

def test_arq03_collect_from_root_without_database_url():
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "PYTHONPATH")}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]


# ── ARQ-16: caminho do modelo via ML_MODEL_PATH ─────────────────────────────

def _reload_model(monkeypatch, path):
    from foreguard.config import get_settings
    from foreguard.core.ml_model import MLModel

    monkeypatch.setenv("ML_MODEL_PATH", str(path))
    get_settings.cache_clear()
    return MLModel()


def test_arq16_model_loaded_from_setting(clean_env, monkeypatch):
    path = clean_env / "m.pkl"
    joblib.dump({"stub": True}, path)
    assert _reload_model(monkeypatch, path).available


def test_arq16_missing_model_is_unavailable(clean_env, monkeypatch):
    assert not _reload_model(monkeypatch, clean_env / "nao-existe.pkl").available


def test_arq16_corrupted_model_is_unavailable(clean_env, monkeypatch):
    path = clean_env / "ruim.pkl"
    path.write_bytes(b"isso nao e um pickle")
    assert not _reload_model(monkeypatch, path).available


# ── ARQ-17: core não depende de api/db ──────────────────────────────────────

@pytest.mark.parametrize(
    "path", sorted((ROOT / "foreguard" / "core").glob("*.py")), ids=lambda p: p.name
)
def test_arq17_core_does_not_import_api_or_db(path):
    tree = ast.parse(path.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {m for m in imported if m.startswith(("foreguard.api", "foreguard.db"))}
    assert forbidden == set()


def test_arq17_core_package_exists():
    assert list((ROOT / "foreguard" / "core").glob("*.py"))


# ── ARQ-18: git, .gitignore, .env.example, config ───────────────────────────

def test_arq18_git_repository():
    assert (ROOT / ".git").is_dir()


@pytest.mark.parametrize(
    "path",
    ["venv/bin/python", ".venv/bin/python", "foreguard/__pycache__/x.pyc", ".env",
     "logs/foreguard.log", "models/foreguard.pkl", "foreguard.db"],
)
def test_arq18_gitignore_covers(path):
    """Verifica a semântica (o git ignora o caminho), não a grafia da linha."""
    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path], cwd=ROOT, capture_output=True
    )
    assert proc.returncode == 0, f"{path} não é ignorado pelo .gitignore"


SETTINGS_VARS = [
    "DATABASE_URL", "API_HOST", "API_PORT", "DEBUG",
    "THRESHOLD_MEDIUM", "THRESHOLD_HIGH", "THRESHOLD_CRITICAL",
    "ML_MODEL_PATH", "LOG_DIR",
    "LOG_STORAGE", "FOREGUARD_API_KEY", "MAX_REQUEST_BYTES", "MASK_FIELDS",
]


def test_arq18_env_example_lists_all_settings():
    keys = {
        line.split("=", 1)[0].strip().lstrip("# ")
        for line in (ROOT / ".env.example").read_text().splitlines()
        if "=" in line
    }
    assert set(SETTINGS_VARS) <= keys


def test_arq18_settings_fields_match_spec():
    from foreguard.config import Settings

    assert set(Settings.model_fields) == set(SETTINGS_VARS)


def test_config_defaults(clean_env):
    from foreguard.config import get_settings

    s = get_settings()
    assert s.DATABASE_URL is None
    assert (s.THRESHOLD_MEDIUM, s.THRESHOLD_HIGH, s.THRESHOLD_CRITICAL) == (3.0, 6.0, 8.0)
    assert s.API_HOST == "127.0.0.1"
    assert s.LOG_STORAGE == "client"
    assert s.FOREGUARD_API_KEY is None
    assert s.MAX_REQUEST_BYTES == 1_048_576
    assert s.MASK_FIELDS == []
    assert str(s.ML_MODEL_PATH) == os.path.join("models", "foreguard.pkl")
