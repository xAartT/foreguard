"""
CLI do Foreguard: `foreguard install` (configura o .env) e `foreguard serve`.
Comportamento especificado em .agents/docs/specs/instalacao.md.
"""
import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

from foreguard.api.security import API_KEY_HEADER

DEFAULT_PORT = 8000
DEFAULT_HOST = "127.0.0.1"
MAX_DB_ATTEMPTS = 3
MIGRATIONS_DIR = Path(__file__).resolve().parent / "db" / "migrations"


class InstallError(Exception):
    """Falha esperada da instalação — mensagem vai para o usuário."""


# ── Banco ─────────────────────────────────────────────────────────────────────

def build_database_url(host: str, port: int | str, database: str, user: str, password: str) -> str:
    return (
        f"postgresql+psycopg2://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(database, safe='')}"
    )


def check_database(url: str) -> None:
    """Abre uma conexão e executa SELECT 1; levanta exceção se falhar."""
    from sqlalchemy import create_engine, pool, text

    connect_args = {} if url.startswith("sqlite") else {"connect_timeout": 5}
    engine = create_engine(url, poolclass=pool.NullPool, connect_args=connect_args)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def run_migrations(url: str) -> None:
    """Aplica as migrações empacotadas (alembic upgrade head) no banco informado."""
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")


def _describe_error(exc: Exception, secrets_to_hide: tuple[str, ...] = ()) -> str:
    message = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    for secret in secrets_to_hide:
        if secret:
            message = message.replace(secret, "***")
    return message


def _prepare_database(url: str, hide: tuple[str, ...] = ()) -> None:
    try:
        check_database(url)
    except Exception as exc:
        raise InstallError(f"Falha de conexão com o banco: {_describe_error(exc, hide)}") from exc
    try:
        run_migrations(url)
    except Exception as exc:
        raise InstallError(f"Falha ao aplicar as migrações: {_describe_error(exc, hide)}") from exc


# ── Perguntas (modo interativo) ──────────────────────────────────────────────

def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or (default or "")


def _ask_port(prompt: str, default: int) -> int:
    while True:
        answer = _ask(prompt, str(default))
        if answer.isdigit() and 1 <= int(answer) <= 65535:
            return int(answer)
        print("Porta inválida — informe um número entre 1 e 65535.")


def _ask_storage() -> str:
    print("\nOnde os logs das análises devem ser gravados?")
    print("  1) No Postgres do Foreguard")
    print("  2) A aplicação-cliente armazena (o Foreguard não grava nada)")
    while True:
        answer = _ask("Opção", "2")
        if answer in ("1", "2"):
            return "database" if answer == "1" else "client"
        print("Opção inválida — responda 1 ou 2.")


def _ask_database_url() -> str:
    """Pede os dados do Postgres até conectar (máx. MAX_DB_ATTEMPTS tentativas)."""
    for attempt in range(1, MAX_DB_ATTEMPTS + 1):
        print(f"\nConexão com o Postgres (tentativa {attempt}/{MAX_DB_ATTEMPTS}) — o banco já deve existir.")
        host = _ask("Host", "localhost")
        port = _ask_port("Porta", 5432)
        database = _ask("Banco", "foreguard")
        user = _ask("Usuário", "foreguard")
        password = getpass.getpass("Senha: ")
        url = build_database_url(host, port, database, user, password)
        try:
            check_database(url)
            return url
        except Exception as exc:
            hide = (password, quote(password, safe=""))
            print(f"Falha de conexão com o banco: {_describe_error(exc, hide)}")
    raise InstallError(f"Não foi possível conectar ao banco após {MAX_DB_ATTEMPTS} tentativas.")


# ── .env ──────────────────────────────────────────────────────────────────────

def _write_env(path: Path, values: dict[str, str]) -> None:
    content = "".join(f"{key}={value}\n" for key, value in values.items())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(content)
    if os.name == "posix":
        os.chmod(path, 0o600)   # O_CREAT não altera a permissão de arquivo existente


# ── Subcomandos ───────────────────────────────────────────────────────────────

def cmd_install(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file)
    interactive = not args.non_interactive
    try:
        if env_file.exists() and not args.force:
            if not interactive:
                print(f"{env_file} já existe — use --force para sobrescrever.", file=sys.stderr)
                return 1
            if _ask(f"{env_file} já existe. Sobrescrever? (s/N)", "N").lower() not in ("s", "sim", "y"):
                print("Instalação cancelada.")
                return 1

        port = _ask_port("Porta da API", args.port) if interactive else args.port
        storage = args.storage or (_ask_storage() if interactive else None)

        values = {"LOG_STORAGE": storage}
        if storage == "database":
            if interactive and not args.database_url:
                url = _ask_database_url()
                _prepare_database(url, hide=())
            else:
                url = args.database_url
                _prepare_database(url)
            values["DATABASE_URL"] = url

        api_key = secrets.token_urlsafe(32)
        values.update({
            "FOREGUARD_API_KEY": api_key,
            "API_HOST": args.host,
            "API_PORT": str(port),
            "LOG_DIR": "logs",
        })
        _write_env(env_file, values)
    except KeyboardInterrupt:
        print("\nInstalação interrompida.", file=sys.stderr)
        return 130
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Não foi possível gravar {env_file}: {exc}", file=sys.stderr)
        return 1

    print(f"""
Foreguard configurado ({env_file}).

  Logs:     {"Postgres do Foreguard" if storage == "database" else "por conta da aplicação-cliente"} (LOG_STORAGE={storage})
  Endpoint: POST http://{args.host}:{port}/v1/analyze
  Header:   {API_KEY_HEADER}: {api_key}

Configure o middleware da aplicação com o endpoint e a chave acima
(guia: .agents/docs/guides/middleware.md) e suba a API, a partir deste diretório, com:

  {_serve_command()}
""")
    return 0


def _serve_command() -> str:
    """Comando para subir a API com o executável do venv em uso (pode não estar no PATH)."""
    script = Path(sys.executable).parent / ("foreguard.exe" if os.name == "nt" else "foreguard")
    if not script.exists():
        return "foreguard serve"
    try:
        script = script.relative_to(Path.cwd())
    except ValueError:
        pass
    return f"{script} serve"


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from foreguard.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "foreguard.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="foreguard", description="Foreguard — análise de risco de requisições HTTP")
    sub = parser.add_subparsers(dest="command", metavar="{install,serve}")

    install = sub.add_parser("install", help="configura o .env (interativo por padrão)")
    install.add_argument("--non-interactive", action="store_true", help="não pergunta nada; exige --storage")
    install.add_argument("--storage", choices=["client", "database"], help="onde os logs são gravados")
    install.add_argument("--database-url", help="URL do banco (obrigatória com --storage database não interativo)")
    install.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"porta da API (padrão {DEFAULT_PORT})")
    install.add_argument("--host", default=DEFAULT_HOST, help=f"host da API (padrão {DEFAULT_HOST})")
    install.add_argument("--env-file", default=".env", help="arquivo de configuração (padrão .env)")
    install.add_argument("--force", action="store_true", help="sobrescreve o .env existente")
    install.set_defaults(func=cmd_install)

    serve = sub.add_parser("serve", help="sobe a API com as configurações do .env")
    serve.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    if args.command == "install" and args.non_interactive:
        if not args.storage:
            parser.error("--non-interactive exige --storage")
        if args.storage == "database" and not args.database_url:
            parser.error("--storage database exige --database-url no modo não interativo")
    return args.func(args)
