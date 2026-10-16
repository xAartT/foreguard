"""Instalador e CLI — specs/instalacao.md (INS-*).

Contrato de teste da CLI (foreguard/cli.py):
- main(argv) -> int  (código de saída; erros de uso podem levantar SystemExit)
- build_database_url(host, port, database, user, password) -> str
- check_database(url) -> None   (levanta exceção se não conectar)
- run_migrations(url) -> None
- senha lida com getpass.getpass; demais perguntas com input()
"""
import ast
import importlib.util
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect

from conftest import KEY_HEADER, ROOT, SETTINGS_ENV

KEY_RE = re.compile(r"^[A-Za-z0-9_-]{32,}$")
UNREACHABLE_URL = "postgresql+psycopg2://u:p@127.0.0.1:1/foreguard"


def run(argv) -> int:
    from foreguard.cli import main

    try:
        return main(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1


def read_env(path: Path) -> dict:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


@pytest.fixture
def env_file(clean_env):
    return clean_env / ".env"


def answers(monkeypatch, inputs, passwords=()):
    """Alimenta input()/getpass na ordem; falha se perguntar além do previsto."""
    inputs, passwords = list(inputs), list(passwords)
    asked = {"input": 0, "getpass": 0}

    def fake_input(prompt=""):
        asked["input"] += 1
        if not inputs:
            raise AssertionError(f"pergunta inesperada: {prompt!r}")
        return inputs.pop(0)

    def fake_getpass(prompt="Password: ", stream=None):
        asked["getpass"] += 1
        if not passwords:
            raise AssertionError(f"senha inesperada: {prompt!r}")
        return passwords.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr("getpass.getpass", fake_getpass)
    return asked


# ── INS-01: CLI registrada ──────────────────────────────────────────────────

def test_ins01_console_script_registered():
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["foreguard"] == "foreguard.cli:main"


def test_ins01_module_help_lists_commands(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in SETTINGS_ENV}
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.run([sys.executable, "-m", "foreguard", "--help"], cwd=tmp_path,
                          env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "install" in proc.stdout and "serve" in proc.stdout


# ── INS-02 / INS-03 / INS-04: não interativo ────────────────────────────────

def test_ins02_client_mode(env_file):
    assert run(["install", "--non-interactive", "--storage", "client",
                "--env-file", str(env_file)]) == 0
    env = read_env(env_file)
    assert env["LOG_STORAGE"] == "client"
    assert KEY_RE.match(env["FOREGUARD_API_KEY"])
    assert env["API_HOST"] == "127.0.0.1"
    assert env["API_PORT"] == "8000"
    assert "DATABASE_URL" not in env


def test_ins03_database_mode_runs_migrations(env_file, clean_env):
    url = f"sqlite:///{clean_env / 'fg.db'}"
    assert run(["install", "--non-interactive", "--storage", "database",
                "--database-url", url, "--env-file", str(env_file)]) == 0
    env = read_env(env_file)
    assert env["LOG_STORAGE"] == "database"
    assert env["DATABASE_URL"] == url
    engine = create_engine(url)
    assert "request_logs" in sa_inspect(engine).get_table_names()
    engine.dispose()


def test_ins04_unreachable_database(env_file, capsys):
    code = run(["install", "--non-interactive", "--storage", "database",
                "--database-url", UNREACHABLE_URL, "--env-file", str(env_file)])
    assert code != 0
    out = capsys.readouterr()
    assert "conex" in (out.out + out.err).lower()
    assert not env_file.exists()


# ── INS-05: .env existente ──────────────────────────────────────────────────

def test_ins05_existing_env_is_preserved_without_force(env_file):
    env_file.write_text("X=1\n")
    code = run(["install", "--non-interactive", "--storage", "client",
                "--env-file", str(env_file)])
    assert code != 0
    assert env_file.read_text() == "X=1\n"


def test_ins05_force_overwrites(env_file):
    env_file.write_text("X=1\n")
    assert run(["install", "--non-interactive", "--storage", "client", "--force",
                "--env-file", str(env_file)]) == 0
    assert read_env(env_file)["LOG_STORAGE"] == "client"


# ── INS-06: uso inválido ────────────────────────────────────────────────────

@pytest.mark.parametrize("argv", [
    ["install", "--non-interactive"],
    ["install", "--non-interactive", "--storage", "database"],
], ids=["sem-storage", "database-sem-url"])
def test_ins06_usage_errors(env_file, argv):
    assert run([*argv, "--env-file", str(env_file)]) == 2
    assert not env_file.exists()


# ── INS-07 / INS-08 / INS-09: interativo ────────────────────────────────────

def test_ins07_interactive_client_mode(env_file, monkeypatch):
    answers(monkeypatch, ["9000", "2"])
    assert run(["install", "--env-file", str(env_file)]) == 0
    env = read_env(env_file)
    assert env["LOG_STORAGE"] == "client"
    assert env["API_PORT"] == "9000"
    assert "DATABASE_URL" not in env


def test_ins08_database_url_is_encoded():
    from foreguard.cli import build_database_url

    url = build_database_url("db.local", 5433, "foreguard", "us@er", "p@ss:w/rd")
    assert url == "postgresql+psycopg2://us%40er:p%40ss%3Aw%2Frd@db.local:5433/foreguard"


def test_ins08_interactive_database_mode(env_file, monkeypatch, capsys):
    import foreguard.cli as cli

    seen = {}
    monkeypatch.setattr(cli, "check_database", lambda url: seen.setdefault("checked", url))
    monkeypatch.setattr(cli, "run_migrations", lambda url: seen.setdefault("migrated", url))
    # porta da API, modo (1=Postgres), host, porta, banco, usuário; senha via getpass
    answers(monkeypatch, ["", "1", "db.local", "5433", "fg", "app"], passwords=["p@ss:w/rd"])

    assert run(["install", "--env-file", str(env_file)]) == 0
    expected = "postgresql+psycopg2://app:p%40ss%3Aw%2Frd@db.local:5433/fg"
    assert seen == {"checked": expected, "migrated": expected}
    env = read_env(env_file)
    assert env["LOG_STORAGE"] == "database"
    assert env["DATABASE_URL"] == expected

    out = capsys.readouterr()
    assert "p@ss:w/rd" not in out.out + out.err   # INS-09


def test_ins08_three_failed_connections_abort(env_file, monkeypatch, capsys):
    import foreguard.cli as cli

    def refuse(url):
        raise ConnectionError("recusada")

    monkeypatch.setattr(cli, "check_database", refuse)
    monkeypatch.setattr(cli, "run_migrations", lambda url: pytest.fail("não deveria migrar"))
    db_answers = ["localhost", "5432", "fg", "app"]
    passwords = ["pw-one-111", "pw-two-222", "pw-three-333"]
    asked = answers(monkeypatch, ["", "1", *db_answers * 3], passwords=passwords)

    assert run(["install", "--env-file", str(env_file)]) != 0
    assert asked["getpass"] == 3
    assert not env_file.exists()
    out = capsys.readouterr()
    assert not any(p in out.out + out.err for p in passwords)   # INS-09


def test_ins08_ctrl_c_exits_130(env_file, monkeypatch):
    def interrupt(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupt)
    assert run(["install", "--env-file", str(env_file)]) == 130
    assert not env_file.exists()


# ── INS-10 / INS-11 / INS-12: .env e resumo ─────────────────────────────────

@pytest.mark.skipif(os.name != "posix", reason="permissões POSIX")
def test_ins10_env_file_permissions(env_file):
    assert run(["install", "--non-interactive", "--storage", "client",
                "--env-file", str(env_file)]) == 0
    assert env_file.stat().st_mode & 0o777 == 0o600


def test_ins11_generated_env_loads_and_keys_differ(clean_env):
    from foreguard.config import Settings

    first, second = clean_env / "a.env", clean_env / "b.env"
    for path in (first, second):
        assert run(["install", "--non-interactive", "--storage", "client",
                    "--env-file", str(path)]) == 0
    s1, s2 = Settings(_env_file=first), Settings(_env_file=second)
    assert s1.LOG_STORAGE == "client"
    assert s1.FOREGUARD_API_KEY != s2.FOREGUARD_API_KEY


def test_ins12_summary(env_file, capsys):
    assert run(["install", "--non-interactive", "--storage", "client", "--port", "8123",
                "--env-file", str(env_file)]) == 0
    out = capsys.readouterr().out
    key = read_env(env_file)["FOREGUARD_API_KEY"]
    assert "http://127.0.0.1:8123/v1/analyze" in out
    assert KEY_HEADER in out
    assert key in out
    assert "client" in out


# ── INS-13: reinstalação idempotente ────────────────────────────────────────

def test_ins13_reinstall_same_database(env_file, clean_env):
    url = f"sqlite:///{clean_env / 'fg.db'}"
    argv = ["install", "--non-interactive", "--storage", "database",
            "--database-url", url, "--env-file", str(env_file), "--force"]
    assert run(argv) == 0
    assert run(argv) == 0


# ── INS-14: serve ───────────────────────────────────────────────────────────

def test_ins14_serve_uses_settings(clean_env, monkeypatch):
    import uvicorn

    from foreguard.config import get_settings

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    monkeypatch.setenv("API_HOST", "127.0.0.2")
    monkeypatch.setenv("API_PORT", "8124")
    get_settings.cache_clear()

    assert run(["serve"]) in (0, None)
    assert len(calls) == 1
    app, kwargs = calls[0]
    assert app == "foreguard.api.main:app"
    assert kwargs["host"] == "127.0.0.2"
    assert kwargs["port"] == 8124


# ── INS-15: bootstrap só com stdlib ─────────────────────────────────────────

BOOTSTRAP = ROOT / "scripts" / "install.py"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("fg_bootstrap", BOOTSTRAP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ins15_bootstrap_uses_only_stdlib():
    tree = ast.parse(BOOTSTRAP.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    assert modules - set(sys.stdlib_module_names) == set()


def test_ins15_python_version_check():
    bootstrap = _load_bootstrap()
    assert bootstrap.python_supported((3, 12, 0)) is True
    assert bootstrap.python_supported((3, 13, 1)) is True
    assert bootstrap.python_supported((3, 11, 9)) is False


@pytest.mark.parametrize("os_name,expected", [
    ("posix", ("bin", "python")),
    ("nt", ("Scripts", "python.exe")),
])
def test_ins15_venv_paths(os_name, expected):
    bootstrap = _load_bootstrap()
    venv = Path("/srv/foreguard/venv")
    assert bootstrap.venv_python(venv, os_name) == venv.joinpath(*expected)
