# Foreguard 🛡️
Middleware de segurança inteligente para análise de risco de requisições HTTP em tempo real.

O Foreguard roda **no mesmo servidor** da sua aplicação, de qualquer stack. Um
middleware da aplicação envia os dados de cada requisição por HTTP local, o
Foreguard analisa e devolve o risco, e **a aplicação decide** o que fazer:
prosseguir, desafiar, bloquear ou ignorar.

```
usuário ──▶ aplicação ──▶ middleware ──POST /v1/analyze──▶ Foreguard (127.0.0.1)
                              ◀── score, nível, motivos ──┘
```

---

## Instalação (só Python 3.12+)

```bash
git clone <repo> foreguard
cd foreguard
python3 scripts/install.py
```

O instalador cria o ambiente virtual, instala as dependências e pergunta:

- **porta** da API (padrão 8000);
- **onde gravar os logs**:
  1. no **Postgres do Foreguard**: informe host, porta, banco (já criado), usuário e senha. A conexão é testada e as tabelas são criadas;
  2. a **aplicação-cliente armazena**: o Foreguard não grava nada.

No fim, ele gera o `.env` com uma chave de API e mostra o endpoint e o header
para configurar o middleware.

Sem perguntas (automação):
```bash
python3 scripts/install.py --non-interactive --storage client
python3 scripts/install.py --non-interactive --storage database \
    --database-url postgresql+psycopg2://user:senha@localhost:5432/foreguard
```

### Subir a API
```bash
venv/bin/foreguard serve
curl http://127.0.0.1:8000/health
```

### Testar uma análise
```bash
curl -X POST http://127.0.0.1:8000/v1/analyze \
  -H "Content-Type: application/json" \
  -H "X-Foreguard-Key: <chave do .env>" \
  -d '{
    "method": "POST",
    "path": "/login",
    "headers": {"user-agent": "Mozilla/5.0"},
    "body": {"username": "admin", "password": "'"'"' OR '"'"'1'"'"'='"'"'1"},
    "query_params": {},
    "ip": "203.0.113.42",
    "user_agent": "Mozilla/5.0"
  }'
```

Docs interativos: `http://127.0.0.1:8000/docs`.

### Integrando sua aplicação
Veja o guia do middleware: contrato, timeout curto e **fail-open** (se o
Foreguard não responder, a requisição segue normalmente):
[`.agents/docs/guides/middleware.md`](.agents/docs/guides/middleware.md).

---

## Desenvolvimento
```bash
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"   # app + pytest, httpx, ruff
pytest                    # não precisa de .env nem de banco (usa SQLite)
ruff check .
```

## Estrutura
```
foreguard/                     # raiz do repo
├── pyproject.toml             # dependências, CLI, pytest, ruff
├── alembic.ini
├── scripts/install.py         # bootstrap da instalação (só stdlib)
├── foreguard/
│   ├── cli.py                 # foreguard install | serve
│   ├── config.py              # settings via .env
│   ├── api/
│   │   ├── main.py            # app FastAPI, /health
│   │   ├── security.py        # chave de API, limite de tamanho
│   │   ├── schemas.py         # modelos Pydantic
│   │   └── routes/
│   │       ├── analyze.py     # POST /v1/analyze
│   │       └── logs.py        # GET /v1/logs, GET /v1/logs/{id} (modo database)
│   ├── core/
│   │   ├── analyzer.py        # orquestrador
│   │   ├── extractor.py       # extração de 16 features
│   │   ├── rules.py           # motor de regras estáticas
│   │   ├── masking.py         # mascaramento de dados sensíveis nos logs
│   │   └── ml_model.py        # inferência ML (Fase 3)
│   └── db/
│       ├── models.py          # tabela request_logs
│       ├── session.py         # engine/sessão sob demanda
│       └── migrations/        # migrações Alembic
├── models/
│   └── foreguard.pkl          # modelo treinado (Fase 3, fora do git)
└── tests/
```

Documentação para devs e agentes (specs SDD): [`.agents/docs/`](.agents/docs/README.md).

---

## Fases
- ✅ **Fase 1**: API, banco, extrator, regras estáticas, instalador e contrato `/v1`
- ⬜ **Fase 2**: Middlewares de referência (o contrato HTTP já atende qualquer stack)
- ⬜ **Fase 3**: Modelo ML (CICIDS2017)
- ⬜ **Fase 4**: Testes de carga com Locust (`pip install -e ".[load]"`)
