# Spec — Integração com a aplicação-cliente

## Objetivo

Definir como o Foreguard se integra a uma aplicação-cliente de **qualquer
stack**: contrato HTTP local versionado, autenticação do middleware, modos de
armazenamento de logs (no Postgres do Foreguard ou por conta do cliente),
comportamento fail-open e proteção dos dados das requisições analisadas.

## Audiência

- **Devs do Foreguard** — critérios de aceite do contrato e do runtime.
- **Devs de aplicações-cliente** — o que o middleware envia, recebe e como
  deve reagir a falhas (detalhado em
  [`../guides/middleware.md`](../guides/middleware.md)).
- **Assistentes/agentes IA** — fonte para derivar testes.

---

## Modelo de implantação

```
┌──────────────────── servidor do cliente ─────────────────────┐
│                                                               │
│  usuário ──▶ aplicação-cliente (qualquer stack)               │
│               └─ middleware ──HTTP local──▶ Foreguard          │
│                    ▲   POST /v1/analyze      (127.0.0.1:8000)  │
│                    └── score/nível/motivos ◀─┘    │            │
│               decide: prosseguir, desafiar,       ▼ opcional   │
│               bloquear ou ignorar            Postgres (logs)   │
└───────────────────────────────────────────────────────────────┘
```

- O Foreguard é clonado e instalado **no mesmo servidor** da aplicação, só com
  Python (sem Docker) — ver [`instalacao.md`](./instalacao.md).
- O middleware da aplicação envia os dados de cada requisição; o Foreguard
  **analisa e informa**. A decisão (prosseguir, bloquear, ignorar) é sempre da
  aplicação-cliente.
- **Fail-open:** se o Foreguard não responder, responder com erro ou estourar o
  timeout, o middleware deixa a requisição seguir. O Foreguard, por sua vez,
  nunca falha a análise por causa de recursos acessórios (banco de logs).

## Escopo

**Entra:**

1. Contrato versionado `POST /v1/analyze` e `GET /v1/logs[/{log_id}]`.
2. Autenticação do middleware por chave compartilhada.
3. Bind padrão em `127.0.0.1`; remoção do CORS.
4. Modo de armazenamento `LOG_STORAGE`: `database` ou `client`.
5. Persistência que não bloqueia nem derruba a análise.
6. Mascaramento de dados sensíveis no `raw_request` persistido.
7. Limite de tamanho da requisição de análise.
8. Guia para quem escreve o middleware (contrato, timeout, fail-open).

**Fica de fora:**

- Middlewares prontos por stack (Fase 2 — o guia e o contrato bastam por ora).
- Pesos, thresholds e texto das recomendações → spec de calibração (TODO).
- Instalador e execução como serviço → [`instalacao.md`](./instalacao.md).
- Múltiplas aplicações por instância (`app_id`), rate limit, TLS.

## Contrato

### Autenticação

Toda rota sob `/v1` exige o header `X-Foreguard-Key` igual a
`FOREGUARD_API_KEY` (comparação em tempo constante). `/health` é público.

### `POST /v1/analyze`

Entrada: `IncomingRequest` (inalterado — ver [`deteccao.md`](./deteccao.md)).
Saída (`AnalysisResponse`):

| Campo | Tipo | Mudança |
| ----- | ---- | ------- |
| `log_id` | `str` (UUID) | inalterado |
| `timestamp` | ISO 8601 UTC | **novo** — momento da análise; permite ao cliente montar o próprio log |
| `risk_score`, `risk_level`, `reasons`, `recommendation`, `analysis_source` | | inalterados |

A resposta **não depende** do banco: o registro é gravado depois da resposta
(modo `database`) ou não é gravado (modo `client`).

### `GET /v1/logs`, `GET /v1/logs/{log_id}`

Mesmo contrato de [`arquitetura.md`](./arquitetura.md) (ARQ-10..12), agora sob
`/v1` e com autenticação. **Só existem no modo `database`.**

### `GET /health`

`{"status": "online", "version": "...", "log_storage": "database" | "client"}`.

### Configuração (novas/alteradas)

| Variável | Tipo | Default | Observação |
| -------- | ---- | ------- | ---------- |
| `LOG_STORAGE` | `"database" \| "client"` | `client` | `database` exige `DATABASE_URL` |
| `FOREGUARD_API_KEY` | `str` | — | **obrigatória** para subir a API; mínimo 32 caracteres |
| `API_HOST` | `str` | `127.0.0.1` | era `0.0.0.0` |
| `MAX_REQUEST_BYTES` | `int` | `1048576` (1 MiB) | tamanho máximo do corpo de `POST /v1/analyze` |
| `MASK_FIELDS` | `list[str]` | `[]` | nomes de campo extras a mascarar (somados à lista padrão) |
| `CORS_ORIGINS` | — | — | **removida** (tráfego servidor-a-servidor) |

### Mascaramento do `raw_request` persistido

A análise usa a requisição **original** (em memória). Antes de persistir:

- `jwt_token` → `"***"` quando presente;
- headers `authorization`, `proxy-authorization`, `cookie`, `set-cookie`,
  `x-api-key`, `x-foreguard-key` → `"***"` (nome case-insensitive);
- em `body` e `query_params`, recursivamente, o **valor** de toda chave cujo
  nome (case-insensitive) contém um destes termos → `"***"`: `password`,
  `senha`, `passwd`, `secret`, `token`, `api_key`, `apikey`, `authorization`,
  `cpf`, `cnpj`, `card`, `cartao`, `cvv`, mais os de `MASK_FIELDS`.

## Critérios de aceite

| ID | Critério |
| -- | -------- |
| INT-01 | `POST /v1/analyze` com chave válida retorna 200 com os campos de `AnalysisResponse`, incluindo `timestamp` ISO 8601 UTC. |
| INT-02 | Sem `X-Foreguard-Key` ou com chave errada, `/v1/analyze` e `/v1/logs` retornam 401 `{"detail": "Chave de API inválida"}`; `/health` responde 200 sem chave. |
| INT-03 | Rotas sem prefixo (`/analyze`, `/logs`) não existem (404). |
| INT-04 | Sem `FOREGUARD_API_KEY`, ou com menos de 32 caracteres, o startup falha com erro que cita `FOREGUARD_API_KEY`. |
| INT-05 | O default de `API_HOST` é `127.0.0.1`; o app não registra `CORSMiddleware` e `CORS_ORIGINS` não existe em `Settings`. |
| INT-06 | Modo `client`: a API sobe **sem** `DATABASE_URL`, `/v1/analyze` responde 200 e nenhuma conexão de banco é aberta; `/v1/logs` e `/v1/logs/{id}` retornam 404. |
| INT-07 | Modo `database`: sem `DATABASE_URL` o startup falha citando `DATABASE_URL`; com ela, cada análise é gravada com `id == log_id` e o mesmo `risk_score`/`risk_level`/`timestamp` da resposta. |
| INT-08 | Modo `database`: se a gravação falhar, `/v1/analyze` **ainda** retorna 200 com a análise, o erro é logado e a sessão sofre rollback (substitui ARQ-09). |
| INT-09 | `/health` informa `log_storage` vigente. |
| INT-10 | O `raw_request` persistido mascara `jwt_token`, os headers sensíveis e os campos sensíveis de `body`/`query_params` (inclusive aninhados e em listas) com `"***"`; campos não sensíveis ficam intactos. |
| INT-11 | `MASK_FIELDS=["rg"]` faz o campo `rg` ser mascarado além da lista padrão. |
| INT-12 | A detecção usa os dados originais: uma injeção dentro de `body.password` continua ativando `has_sqli`, embora o valor persistido seja `"***"`. |
| INT-13 | `POST /v1/analyze` com corpo maior que `MAX_REQUEST_BYTES` retorna 413, sem executar a análise. |
| INT-14 | Valor de `LOG_STORAGE` fora de `database`/`client` impede o carregamento das settings com erro que cita `LOG_STORAGE`. |
| INT-15 | Em modo `client`, 100 chamadas sequenciais a `/v1/analyze` com uma requisição típica têm mediana abaixo de 20 ms (TestClient, sem rede). |

## Casos-limite e erros

- **Banco cai com a API no ar (modo `database`):** análises continuam (INT-08);
  os logs do período são perdidos e o erro aparece no log da aplicação.
- **Foreguard fora do ar:** responsabilidade do middleware (fail-open) — ver
  guia.
- **Corpo acima do limite:** 413; o guia orienta o middleware a truncar ou
  omitir bodies grandes/multipart em vez de enviá-los.
- **Chave com espaços/quebra de linha no `.env`:** o valor é usado como está;
  o instalador gera chaves só com caracteres URL-safe.

## Decisões (aprovadas no gate da Fase 1)

1. **Default `LOG_STORAGE=client`** — sobe sem banco nenhum (zero dependência);
   o instalador sempre pergunta e grava o valor escolhido.
2. Nome do header `X-Foreguard-Key` e chave mínima de 32 caracteres.
3. Remover as rotas sem `/v1` em vez de manter alias (não há clientes ainda).
4. Lista padrão de campos mascarados (inclui `cpf`/`cnpj`, pensando em LGPD).
5. `MAX_REQUEST_BYTES` padrão de 1 MiB.

## Rastreabilidade (testes em `tests/test_integration.py`)

| Critério | Testes |
| -------- | ------ |
| INT-01 | `test_int01_analyze_contract` |
| INT-02 | `test_int02_requires_api_key` (3 rotas × 3 casos), `test_int02_health_is_public` |
| INT-03 | `test_int03_unversioned_routes_do_not_exist` |
| INT-04 | `test_int04_startup_requires_strong_key` |
| INT-05 | `test_int05_default_host_is_loopback`, `test_int05_no_cors_middleware`; `test_project.py::test_config_defaults` |
| INT-06 | `test_int06_client_mode_never_touches_database`, `test_int06_client_mode_has_no_logs_routes` |
| INT-07 | `test_int07_database_mode_persists_same_result`; `test_api.py::test_arq04_database_mode_startup_fails_without_database_url` |
| INT-08 | `test_int08_write_failure_still_returns_analysis` |
| INT-09 | `test_int09_health_reports_log_storage` |
| INT-10 | `test_int10_sensitive_data_is_masked`, `test_int10_jwt_absent_stays_null` |
| INT-11 | `test_int11_extra_mask_fields` |
| INT-12 | `test_int12_detection_uses_original_values` |
| INT-13 | `test_int13_oversized_request_is_rejected`, `test_int13_request_under_limit_is_accepted` |
| INT-14 | `test_int14_invalid_log_storage` |
| INT-15 | `test_int15_client_mode_latency` |

---

## Referências

- Rotas: [`foreguard/api/routes/analyze.py`](../../../foreguard/api/routes/analyze.py),
  [`foreguard/api/routes/logs.py`](../../../foreguard/api/routes/logs.py)
- App, startup e auth: [`foreguard/api/main.py`](../../../foreguard/api/main.py)
- Config: [`foreguard/config.py`](../../../foreguard/config.py)
- Schemas: [`foreguard/api/schemas.py`](../../../foreguard/api/schemas.py)
- Auth e limite de tamanho: [`foreguard/api/security.py`](../../../foreguard/api/security.py)
- Mascaramento: [`foreguard/core/masking.py`](../../../foreguard/core/masking.py)
- Guia do middleware: [`../guides/middleware.md`](../guides/middleware.md)
