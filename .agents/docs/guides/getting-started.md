# Getting started

## Objetivo

Descrever como instalar o Foreguard num servidor, subir a API e, para quem
desenvolve o projeto, rodar testes e lint.

## Audiência

- **Quem instala** o Foreguard ao lado de uma aplicação-cliente.
- **Devs do Foreguard** — setup de desenvolvimento.
- **Assistentes/agentes IA** — comandos canônicos para rodar e validar.

---

## Instalação num servidor (só Python 3.12+)

```sh
git clone <repo> foreguard && cd foreguard
python3 scripts/install.py
```

O bootstrap cria `venv/`, instala o pacote e roda `foreguard install`, que
pergunta a porta e onde gravar os logs:

1. **Postgres do Foreguard** — informe host, porta, banco (já existente),
   usuário e senha; o instalador testa a conexão e aplica as migrações.
2. **Aplicação-cliente armazena** — o Foreguard não grava nada.

Ao final grava `.env` (permissão 600) com uma `FOREGUARD_API_KEY` gerada e
mostra o endpoint, o header e a chave para configurar o middleware
([`middleware.md`](./middleware.md)).

Sem perguntas (automação):

```sh
python3 scripts/install.py --non-interactive --storage client --port 8000
python3 scripts/install.py --non-interactive --storage database \
    --database-url postgresql+psycopg2://user:senha@localhost:5432/foreguard
# --force sobrescreve um .env existente; --host altera o bind (padrão 127.0.0.1)
```

## Subir a API

A partir do diretório do repositório (onde está o `.env`):

```sh
venv/bin/foreguard serve        # Windows: venv\Scripts\foreguard serve
```

Para manter no ar após reboot, registre o comando como serviço do SO. Exemplo
systemd (fora do escopo do instalador):

```ini
[Unit]
Description=Foreguard
After=network.target

[Service]
WorkingDirectory=/opt/foreguard
ExecStart=/opt/foreguard/venv/bin/foreguard serve
Restart=always

[Install]
WantedBy=multi-user.target
```

## Desenvolvimento

```sh
python3.12 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"        # app + pytest, httpx, ruff
pytest                         # não precisa de .env nem de banco (usa SQLite)
ruff check .
```

Nova migração (com `DATABASE_URL` no ambiente/.env):

```sh
alembic revision --autogenerate -m "descrição"
alembic upgrade head
```

---

## Referências

- Bootstrap: [`scripts/install.py`](../../../scripts/install.py)
- CLI: [`foreguard/cli.py`](../../../foreguard/cli.py)
- Variáveis de ambiente: [`.env.example`](../../../.env.example)
- Dependências e ferramentas: [`pyproject.toml`](../../../pyproject.toml)
- Migrações: [`alembic.ini`](../../../alembic.ini), [`foreguard/db/migrations/`](../../../foreguard/db/migrations/)
- Specs: [`../specs/instalacao.md`](../specs/instalacao.md), [`../specs/integracao.md`](../specs/integracao.md)
