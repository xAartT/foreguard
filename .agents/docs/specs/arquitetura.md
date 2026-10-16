# Spec — Arquitetura e robustez da API

## Objetivo

Reorganizar o Foreguard em um pacote Python instalável e executável, com
configuração, banco/migrações e testes funcionando a partir da raiz, e
corrigir pontos de robustez da API — **sem alterar** a lógica de score
(extração, regras, thresholds, recomendações), que pertence a
[`deteccao.md`](./deteccao.md) e à futura spec de calibração.

## Audiência

- **Devs** — critérios de aceite e contrato da reestruturação.
- **Assistentes/agentes IA** — fonte para derivar testes (Fase 2) e guiar a
  implementação (Fase 3).

---

## Escopo

**Entra:**

1. Layout de pacote (`foreguard/`), `pyproject.toml`, `tests/` na raiz.
2. Configuração tipada sem efeitos colaterais no import.
3. Engine/sessão de banco criados sob demanda; Alembic como fonte única do
   schema, com migração inicial de `request_logs`.
4. App FastAPI com `lifespan`, logging configurado no startup, rota
   `/analyze` síncrona, schemas de resposta explícitos para `/logs`.
5. Injeção do modelo ML no `Analyzer` (para testar o fallback).
6. Repositório git com `.gitignore`; `.env.example`; README atualizado.

**Fica de fora:**

- Qualquer mudança em padrões de ataque, superfície inspecionada → 
  [`deteccao.md`](./deteccao.md).
- Pesos, thresholds e textos de recomendação (spec de calibração — TODO).
- Autenticação em `/logs`, remoção de dados sensíveis de `raw_request`,
  CORS restritivo (spec de segurança — TODO). O CORS só passa a ser lido da
  config, com o mesmo default `*`.
- Fases 2–4 (middleware Express, treino do modelo, Locust).

## Layout alvo

```
foreguard/                      # raiz do repo
├── pyproject.toml              # deps, extras [dev], config de pytest e ruff
├── .env.example
├── .gitignore
├── alembic.ini                 # script_location → foreguard/db/migrations
├── foreguard/
│   ├── __init__.py             # __version__
│   ├── config.py               # Settings + get_settings() (cache)
│   ├── api/
│   │   ├── main.py             # create_app() + app; lifespan; /health
│   │   ├── schemas.py
│   │   └── routes/{analyze.py, logs.py}
│   ├── core/
│   │   ├── analyzer.py
│   │   ├── extractor.py
│   │   ├── rules.py
│   │   └── ml_model.py
│   └── db/
│       ├── base.py             # Base declarativa
│       ├── models.py
│       ├── session.py          # get_engine(), get_session_factory(), get_db()
│       └── migrations/         # empacotadas: o instalador as aplica (instalacao.md)
│           ├── env.py          # usa Settings.DATABASE_URL e Base.metadata
│           └── versions/0001_create_request_logs.py
├── models/                     # .pkl treinado (ignorado pelo git)
└── tests/
    ├── conftest.py             # app com SQLite em memória
    ├── test_extractor.py, test_rules.py, test_analyzer.py
    ├── test_api.py
    └── test_migrations.py
```

Regra de dependência: `foreguard.core` não importa `foreguard.api` nem
`foreguard.db`.

## Contratos

### Configuração (`foreguard.config`)

| Variável | Tipo | Default | Observação |
| -------- | ---- | ------- | ---------- |
| `DATABASE_URL` | `str \| None` | `None` | Obrigatória só para quem usa o banco (API/Alembic). |
| `API_HOST` / `API_PORT` | `str` / `int` | `0.0.0.0` / `8000` | inalterado |
| `DEBUG` | `bool` | `False` | inalterado |
| `THRESHOLD_MEDIUM/HIGH/CRITICAL` | `float` | `3.0/6.0/8.0` | inalterado |
| `ML_MODEL_PATH` | `Path` | `models/foreguard.pkl` | relativo ao diretório de trabalho |
| `LOG_DIR` | `Path \| None` | `logs` | `None`/vazio desliga o arquivo de log |
| `CORS_ORIGINS` | `list[str]` | `["*"]` | |

`SECRET_KEY` e a dependência `python-jose` são **removidos** (não são usados;
voltam com a spec de segurança).

### Endpoints

| Método/rota | Mudança |
| ----------- | ------- |
| `GET /health` | Inalterado; `version` vem de `foreguard.__version__`. |
| `POST /analyze` | Contrato de entrada/saída inalterado. Erro de banco → 503. |
| `GET /logs` | Resposta tipada `list[LogSummary]`; `level` inválido → 422; `limit` 1–500. |
| `GET /logs/{log_id}` | Resposta tipada `LogDetail` (**muda**: chave `id` → `log_id`). |

`LogSummary`: `log_id, timestamp, method, path, ip, risk_score, risk_level,
reasons`. `LogDetail`: `LogSummary` + `user_agent, raw_request`.
`timestamp` sempre serializado como ISO 8601 em UTC com offset
(`...+00:00` ou `...Z`).

## Critérios de aceite

| ID | Critério |
| -- | -------- |
| ARQ-01 | O código-fonte vive em `foreguard/{api,core,db}` conforme o layout alvo; não restam módulos `.py` de aplicação na raiz do repo. |
| ARQ-02 | `pip install -e ".[dev]"` instala app + pytest, httpx e ruff; `requirements.txt` deixa de existir (deps pinadas nas versões atuais no `pyproject.toml`). Locust fica no extra `[load]` (Fase 4). |
| ARQ-03 | `pytest` executado na raiz, sem `.env` e sem `DATABASE_URL`, coleta e roda toda a suíte. |
| ARQ-04 | Importar `foreguard.core.*` e `foreguard.api.main` não abre conexão nem exige `DATABASE_URL`; sem ela, o **startup** da API falha com erro que cita `DATABASE_URL`. |
| ARQ-05 | `alembic upgrade head` em banco vazio cria `request_logs` com as mesmas colunas, tipos de nulidade e índices (`timestamp`, `ip`, `risk_level`) do modelo; `alembic downgrade base` a remove. |
| ARQ-06 | O startup da API **não** cria tabelas (`create_all` removido); o schema vem só das migrações. |
| ARQ-07 | `POST /analyze` com o payload de exemplo do schema retorna 200 com `log_id` e o registro correspondente existe no banco com o mesmo `id`, `risk_score` e `risk_level`. |
| ARQ-08 | A função da rota `/analyze` é síncrona (`def`), para que o acesso bloqueante ao banco rode no threadpool. |
| ARQ-09 | Se o commit no banco falhar em `/analyze`, a sessão sofre rollback, o erro é logado e a resposta é 503 com `detail` — nunca 500. |
| ARQ-10 | `GET /logs` respeita `limit` (1–500, fora disso 422), filtra por `level` (case-insensitive) e `ip`, e ordena por `timestamp` decrescente; `level` fora de `LOW/MEDIUM/HIGH/CRITICAL` → 422. |
| ARQ-11 | `GET /logs/{id}` retorna `LogDetail` com `log_id`; id inexistente → 404 `{"detail": "Log não encontrado"}`. |
| ARQ-12 | `timestamp` nas respostas de `/logs` é ISO 8601 com offset UTC, inclusive quando o banco devolve datetime sem fuso (SQLite). |
| ARQ-13 | O app usa `lifespan` (sem `on_event`) e `Settings` usa `model_config`; subir o app e importar a config não emite `DeprecationWarning` originado em `foreguard`. |
| ARQ-14 | O sink de arquivo do loguru é configurado no startup (não no import); com `LOG_DIR` vazio nenhum arquivo é criado. |
| ARQ-15 | `Analyzer` aceita o modelo ML por injeção: com um modelo cujo `predict` lança exceção, `analysis_source == "rules_fallback"` e o score é o das regras; com um modelo que retorna 7.5, `analysis_source == "ml"` e `risk_score == 7.5`. |
| ARQ-16 | `ml_model` lê o caminho de `ML_MODEL_PATH`; arquivo ausente → `available == False` sem exceção. |
| ARQ-17 | `foreguard.core` não importa `foreguard.api` nem `foreguard.db` (verificado por teste). |
| ARQ-18 | O repo é um repositório git cujo `.gitignore` faz o git ignorar `venv/`, `.venv/`, `__pycache__/`, `.env`, `logs/`, `models/*.pkl` e `*.db` (verificado com `git check-ignore`, independente da grafia das linhas); existe `.env.example` com todas as variáveis da tabela de configuração. |
| ARQ-19 | Os testes existentes de `test_analyzer.py` são preservados (divididos por camada); `test_analyzer_sqli_is_high_or_critical` fica marcado `xfail(strict=True)` com motivo apontando para a spec de calibração. |

## Casos-limite e erros

- **`DATABASE_URL` ausente:** só falha onde é usada (startup da API,
  `alembic`), com mensagem explícita (ARQ-04).
- **Banco indisponível em `/analyze`:** 503, sem vazar stack trace (ARQ-09).
- **Modelo `.pkl` corrompido:** `available == False`, log de warning, regras
  assumem (comportamento atual preservado).
- **Diretório de logs inexistente:** criado pelo loguru; `LOG_DIR` vazio
  desliga o arquivo (ARQ-14).
- **`GET /logs?limit=0`** ou `limit=501` → 422 (ARQ-10).

## Decisões (aprovadas no gate da Fase 1)

1. Pacote `foreguard/` (namespaced) em vez de `api/`, `core/`, `db/` soltos
   na raiz — evita colisão com nomes genéricos.
2. `/analyze` responde **503** quando o banco falha.
3. `GET /logs/{id}` usa a chave `log_id` (era `id`).

## Alterações por specs posteriores

[`integracao.md`](./integracao.md) (implementada) substitui os seguintes
pontos desta spec — onde houver conflito, vale a integração:

| Aqui | Passa a valer |
| ---- | ------------- |
| ARQ-09 — falha de banco → 503 | INT-08 — análise retorna 200; gravação falha só no log |
| ARQ-04/ARQ-07 — `DATABASE_URL` exigida no startup | INT-06/INT-07 — exigida só com `LOG_STORAGE=database` |
| Rotas `/analyze`, `/logs` | INT-03 — apenas sob `/v1`, com `X-Foreguard-Key` |
| `API_HOST` default `0.0.0.0`; `CORS_ORIGINS` | INT-05 — `127.0.0.1`; CORS removido |

## Rastreabilidade (testes em `tests/`)

| Critério | Testes |
| -------- | ------ |
| ARQ-01 | `test_project.py::test_arq01_*` |
| ARQ-02 | `test_project.py::test_arq02_*` |
| ARQ-03 | `test_project.py::test_arq03_collect_from_root_without_database_url`, fixture `clean_env` |
| ARQ-04 | `test_api.py::test_arq04_*`, `test_project.py::test_config_defaults` |
| ARQ-05 | `test_migrations.py::test_arq05_upgrade_matches_model_and_downgrade_drops` |
| ARQ-06 | `test_api.py::test_arq06_startup_does_not_create_tables` |
| ARQ-07 | `test_api.py::test_arq07_analyze_persists_log`, `test_health_reports_package_version` |
| ARQ-08 | `test_api.py::test_arq08_analyze_route_is_sync` |
| ARQ-09 | substituído por INT-08 (`test_integration.py`) |
| ARQ-10 | `test_api.py::test_arq10_*` |
| ARQ-11 | `test_api.py::test_arq11_*` |
| ARQ-12 | `test_api.py::test_arq12_timestamps_are_utc_iso` |
| ARQ-13 | `test_api.py::test_arq13_no_project_deprecation_warnings` |
| ARQ-14 | `test_api.py::test_arq14_*` |
| ARQ-15 | `test_analyzer.py::test_arq15_*` |
| ARQ-16 | `test_project.py::test_arq16_*` |
| ARQ-17 | `test_project.py::test_arq17_*` |
| ARQ-18 | `test_project.py::test_arq18_*` |
| ARQ-19 | `test_analyzer.py`, `test_rules.py`, `test_extractor.py::test_extract_*` (legados) |

---

## Referências

- Migrações: [`foreguard/db/migrations/`](../../../foreguard/db/migrations/)
- Implementação: [`foreguard/api/main.py`](../../../foreguard/api/main.py), [`foreguard/api/routes/analyze.py`](../../../foreguard/api/routes/analyze.py),
  [`foreguard/api/routes/logs.py`](../../../foreguard/api/routes/logs.py), [`foreguard/api/schemas.py`](../../../foreguard/api/schemas.py),
  [`foreguard/config.py`](../../../foreguard/config.py), [`foreguard/db/session.py`](../../../foreguard/db/session.py),
  [`foreguard/db/models.py`](../../../foreguard/db/models.py), [`foreguard/core/analyzer.py`](../../../foreguard/core/analyzer.py),
  [`foreguard/core/ml_model.py`](../../../foreguard/core/ml_model.py)
- Testes: [`tests/`](../../../tests/)
- Dependências e config de pytest/ruff: [`pyproject.toml`](../../../pyproject.toml)
- Arquitetura: [`../architecture/overview.md`](../architecture/overview.md)
