# Spec — Instalação (somente Python)

## Objetivo

Permitir que o Foreguard seja instalado no servidor da aplicação-cliente
tendo **apenas Python 3.12+** — sem Docker —, com um instalador que pergunta
onde os logs ficam (Postgres do próprio Foreguard ou por conta da
aplicação-cliente), gera a configuração e deixa a API pronta para subir.

## Audiência

- **Quem instala o Foreguard** num servidor (dev/ops da aplicação-cliente).
- **Devs do Foreguard** — critérios de aceite do instalador e da CLI.
- **Assistentes/agentes IA** — fonte para derivar testes.

---

## Fluxo

```
git clone <repo> foreguard && cd foreguard
python3 scripts/install.py          # bootstrap: só stdlib
  ├─ verifica Python >= 3.12
  ├─ cria venv/ (se não existir) e instala o pacote nele
  └─ executa: venv/bin/foreguard install [args repassados]
        ├─ pergunta: porta (8000)
        ├─ pergunta: onde gravar os logs?
        │     1) Postgres do Foreguard  → host, porta, banco, usuário, senha
        │                                → testa conexão → roda migrações
        │     2) A aplicação-cliente armazena (Foreguard não grava)
        ├─ gera FOREGUARD_API_KEY
        ├─ grava .env (permissão 600)
        └─ imprime o resumo para configurar o middleware
venv/bin/foreguard serve            # sobe a API (uvicorn) com as settings
```

## Escopo

**Entra:** script de bootstrap `scripts/install.py`; CLI `foreguard` com os
subcomandos `install` e `serve`; modo interativo e não interativo; teste de
conexão e migrações no modo Postgres; geração do `.env`.
As migrações ficam dentro do pacote (`foreguard/db/migrations/`), para que
o instalador as aplique sem depender do diretório de trabalho.

**Fica de fora:**

- Registrar como serviço do SO (systemd, Windows Service) — o guia traz um
  exemplo de unit systemd, sem automação.
- Criar o banco/usuário no Postgres (o instalador usa um banco existente).
- Atualização de versão (`git pull` + migrações) — TODO em spec futura.
- Instalar o próprio Python ou o Postgres.

## Contrato

### `python3 scripts/install.py [args]`

Usa só a biblioteca padrão. Python < 3.12 → mensagem e saída 1. Cria
`venv/` na raiz do repo se não existir, roda `pip install .` nele e repassa os
argumentos para `foreguard install`. Funciona em POSIX (`venv/bin/`) e
Windows (`venv\Scripts\`).

### `foreguard install`

| Opção | Efeito |
| ----- | ------ |
| (sem opções) | modo interativo |
| `--non-interactive` | não pergunta nada; exige `--storage` |
| `--storage client\|database` | modo de logs |
| `--database-url URL` | obrigatório com `--storage database` não interativo |
| `--port N` | default 8000 |
| `--host H` | default `127.0.0.1` |
| `--env-file PATH` | default `.env` no diretório atual |
| `--force` | sobrescreve `.env` existente |

No modo interativo, Postgres é perguntado campo a campo (host `localhost`,
porta `5432`, banco `foreguard`, usuário, senha via `getpass`) e a URL é
montada como `postgresql+psycopg2://usuario:senha@host:porta/banco`, com
usuário e senha URL-encoded.

`.env` gerado (chaves de [`integracao.md`](./integracao.md) e
[`arquitetura.md`](./arquitetura.md)):

```
LOG_STORAGE=client|database
DATABASE_URL=...            # só no modo database
FOREGUARD_API_KEY=<43 chars url-safe>
API_HOST=127.0.0.1
API_PORT=8000
LOG_DIR=logs
```

Resumo final (stdout): URL `http://<host>:<porta>/v1/analyze`, header
`X-Foreguard-Key`, a chave gerada, o modo de logs e o comando para subir.
**Nunca** imprime a senha do banco.

### `foreguard serve`

Sobe `foreguard.api.main:app` com uvicorn usando `API_HOST`/`API_PORT` das
settings. `python -m foreguard` é equivalente a `foreguard`.

## Critérios de aceite

| ID | Critério |
| -- | -------- |
| INS-01 | `pyproject.toml` registra o script `foreguard = "foreguard.cli:main"`; `python -m foreguard --help` lista `install` e `serve`. |
| INS-02 | `install --non-interactive --storage client` grava `.env` com `LOG_STORAGE=client`, `FOREGUARD_API_KEY` (≥ 32 chars, só `[A-Za-z0-9_-]`), `API_HOST=127.0.0.1`, `API_PORT=8000`, **sem** `DATABASE_URL`; saída 0. |
| INS-03 | `install --non-interactive --storage database --database-url <URL válida>` testa a conexão, aplica as migrações (tabela `request_logs` existe) e grava `LOG_STORAGE=database` e `DATABASE_URL`; saída 0. |
| INS-04 | Com URL de banco inacessível: saída ≠ 0, mensagem cita a falha de conexão, `.env` **não** é criado. |
| INS-05 | `.env` existente sem `--force`: saída ≠ 0 e o arquivo fica intacto; com `--force`, é sobrescrito. No interativo, pergunta antes de sobrescrever. |
| INS-06 | `--non-interactive` sem `--storage`, ou `--storage database` sem `--database-url`: saída 2 com mensagem de uso. |
| INS-07 | Interativo escolhendo "aplicação-cliente armazena": resultado igual a INS-02 (com a porta informada). |
| INS-08 | Interativo escolhendo Postgres: monta a URL com usuário/senha URL-encoded (ex.: senha `p@ss:w/rd`); falha de conexão pede os dados de novo, até 3 tentativas, depois aborta com saída ≠ 0 sem gravar `.env`. |
| INS-09 | A senha é lida com `getpass` e não aparece no stdout/stderr do instalador. |
| INS-10 | Em POSIX, o `.env` é criado com permissão `0600`. |
| INS-11 | O `.env` gerado carrega em `Settings` sem erro, e duas instalações geram chaves diferentes. |
| INS-12 | O resumo final contém a URL `/v1/analyze`, o header `X-Foreguard-Key`, a chave e o modo de logs. |
| INS-13 | Reinstalar com `--force` no mesmo banco não falha (migrações idempotentes). |
| INS-14 | `foreguard serve` chama `uvicorn.run` com `"foreguard.api.main:app"`, `host`/`port` das settings. |
| INS-15 | `scripts/install.py` importa só módulos da biblioteca padrão; recusa Python < 3.12 com saída 1; resolve o executável do venv em `bin/` (POSIX) ou `Scripts\` (Windows). |

## Casos-limite e erros

- **Ctrl+C durante o interativo:** sai com código 130 sem gravar `.env`.
- **Diretório sem permissão de escrita:** erro claro, saída ≠ 0.
- **`venv/` já existe:** reaproveita; `pip install .` atualiza o pacote.
- **Postgres acessível mas usuário sem permissão de CREATE TABLE:** a
  migração falha → saída ≠ 0, `.env` não gravado, mensagem com a causa.

## Decisões (aprovadas no gate da Fase 1)

1. Bootstrap em `scripts/install.py` (não na raiz — mantém ARQ-01).
2. CLI `foreguard install` / `foreguard serve` como interface oficial.
3. O instalador **não** cria banco nem usuário no Postgres; usa um existente.
4. Pergunta só a porta no interativo; host fica em `127.0.0.1` (alterável
   por `--host`).

## Rastreabilidade (testes em `tests/test_install.py`)

| Critério | Testes |
| -------- | ------ |
| INS-01 | `test_ins01_console_script_registered`, `test_ins01_module_help_lists_commands` |
| INS-02 | `test_ins02_client_mode` |
| INS-03 | `test_ins03_database_mode_runs_migrations` |
| INS-04 | `test_ins04_unreachable_database` |
| INS-05 | `test_ins05_existing_env_is_preserved_without_force`, `test_ins05_force_overwrites` |
| INS-06 | `test_ins06_usage_errors` |
| INS-07 | `test_ins07_interactive_client_mode` |
| INS-08 | `test_ins08_database_url_is_encoded`, `test_ins08_interactive_database_mode`, `test_ins08_three_failed_connections_abort`, `test_ins08_ctrl_c_exits_130` |
| INS-09 | asserts de senha em `test_ins08_interactive_database_mode` e `test_ins08_three_failed_connections_abort` |
| INS-10 | `test_ins10_env_file_permissions` |
| INS-11 | `test_ins11_generated_env_loads_and_keys_differ` |
| INS-12 | `test_ins12_summary` |
| INS-13 | `test_ins13_reinstall_same_database` |
| INS-14 | `test_ins14_serve_uses_settings` |
| INS-15 | `test_ins15_bootstrap_uses_only_stdlib`, `test_ins15_python_version_check`, `test_ins15_venv_paths` |

Contrato interno fixado pelos testes (`foreguard/cli.py`): `main(argv) -> int`,
`build_database_url(...)`, `check_database(url)`, `run_migrations(url)`;
senha via `getpass.getpass`. Em `scripts/install.py`: `python_supported(version)`
e `venv_python(venv_dir, os_name)`.

---

## Referências

- CLI: [`foreguard/cli.py`](../../../foreguard/cli.py)
- Bootstrap: [`scripts/install.py`](../../../scripts/install.py)
- Config: [`foreguard/config.py`](../../../foreguard/config.py)
- Migrações: [`foreguard/db/migrations/`](../../../foreguard/db/migrations/),
  [`alembic.ini`](../../../alembic.ini)
- Empacotamento: [`pyproject.toml`](../../../pyproject.toml)
- Integração: [`integracao.md`](./integracao.md)
