# Foreguard — Visão geral

## Objetivo

Apresentar o produto, sua audiência, a stack e os domínios principais em um
único arquivo, suficiente para alguém novo (humano ou agente IA) entender o
escopo antes de aprofundar em `architecture/`, `guides/` e `specs/`.

## Audiência

- **Devs do projeto** — manutenção e evolução das fases 1–4.
- **Assistentes/agentes IA** — esta documentação foi estruturada para consumo
  automatizado: cada arquivo tem **Objetivo** + **Audiência** no topo e
  **Referências** para caminhos de código no fim.

## O que é o Foreguard

O Foreguard é uma API que recebe a **descrição** de uma requisição HTTP feita
a uma aplicação cliente (método, path, headers, body, query params, IP,
User-Agent, JWT) e devolve um **score de risco** de 0 a 10, um **nível**
(`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`), os **motivos** e uma **recomendação**
(`ALLOW`/`CHALLENGE`/`BAN_USER`/`LOCKDOWN`). Cada análise é persistida para
auditoria e futuro retreinamento.

O score vem de um **motor de regras estáticas** (soma de pesos por feature) ou,
quando existe um modelo treinado em disco, de um **modelo ML** — com as regras
como fallback e como fonte dos motivos.

**Modelo de implantação:** o Foreguard é clonado e instalado (só Python, sem
Docker) **no mesmo servidor** da aplicação-cliente, de qualquer stack. Um
middleware da aplicação envia os dados de cada requisição por HTTP local; o
Foreguard analisa e devolve o risco, e **a aplicação decide** o que fazer.
O middleware é fail-open. Os logs ficam no Postgres do Foreguard ou por
conta da aplicação, conforme escolhido na instalação — ver
[`specs/integracao.md`](./specs/integracao.md) e
[`specs/instalacao.md`](./specs/instalacao.md).

O projeto está em desenvolvimento, organizado em fases (README da raiz):
Fase 1 (API + banco + extrator + regras) implementada; Fase 2 (middleware
Node/Express), Fase 3 (modelo ML) e Fase 4 (carga com Locust) pendentes.

## Stack resumido

- **API**: FastAPI 0.111 + Pydantic 2.7 + pydantic-settings
  ([`foreguard/api/main.py`](../../foreguard/api/main.py))
- **Persistência (opcional, `LOG_STORAGE=database`)**: SQLAlchemy 2.0 + PostgreSQL (psycopg2); schema versionado
  por Alembic ([`foreguard/db/models.py`](../../foreguard/db/models.py),
  [`foreguard/db/migrations/`](../../foreguard/db/migrations/))
- **Análise**: regex + `user-agents` ([`foreguard/core/extractor.py`](../../foreguard/core/extractor.py)),
  regras ([`foreguard/core/rules.py`](../../foreguard/core/rules.py)), ML opcional via joblib/scikit-learn/
  xgboost ([`foreguard/core/ml_model.py`](../../foreguard/core/ml_model.py))
- **Logs**: loguru (stdout + arquivo JSON diário)
- **Testes/lint**: pytest + ruff ([`tests/`](../../tests/), [`pyproject.toml`](../../pyproject.toml))
- **Instalação**: só Python — `scripts/install.py` + CLI `foreguard install`/`serve`
  ([`foreguard/cli.py`](../../foreguard/cli.py))
- **CI**: TODO — inexistente.

## Padrão arquitetural vigente

Pacote `foreguard/` em camadas: `api` (rotas/schemas) → `core` (extração,
regras, ML, orquestração) e `api` → `db` (modelo/sessão); `core` não depende
de `api` nem de `db`. Ver [`architecture/overview.md`](./architecture/overview.md)
e [`specs/arquitetura.md`](./specs/arquitetura.md).

## Domínios principais

| Domínio      | Foco                                                        | Doc |
| ------------ | ----------------------------------------------------------- | --- |
| Arquitetura  | layout de pacotes, config, banco/migrações, robustez da API | [`specs/arquitetura.md`](./specs/arquitetura.md) |
| Detecção     | extração de features e padrões de ataque                    | [`specs/deteccao.md`](./specs/deteccao.md) |
| Integração   | contrato HTTP `/v1`, auth, modos de log, fail-open, mascaramento | [`specs/integracao.md`](./specs/integracao.md) |
| Instalação   | instalador só-Python, CLI `foreguard install`/`serve`       | [`specs/instalacao.md`](./specs/instalacao.md) |

TODO: spec de **calibração** (pesos, thresholds, recomendações como sugestão
e não ordem). Os itens de segurança da API foram absorvidos por
[`specs/integracao.md`](./specs/integracao.md).

## Glossário

| Termo             | Significado |
| ----------------- | ----------- |
| feature           | Sinal numérico extraído da requisição (16 no total, ver `FEATURE_ORDER`). |
| risk_score        | Pontuação 0.0–10.0 (soma das regras com teto 10, ou `proba * 10` do ML). |
| risk_level        | Faixa do score: `LOW` < 3.0 ≤ `MEDIUM` < 6.0 ≤ `HIGH` < 8.0 ≤ `CRITICAL`. |
| recommendation    | Ação sugerida ao cliente, derivada do nível. |
| analysis_source   | `rules`, `ml` ou `rules_fallback` (ML falhou na inferência). |
| superfície inspecionada | Partes da requisição sobre as quais os padrões de ataque são aplicados. |

## Referências

- Código: [`foreguard/core/analyzer.py`](../../foreguard/core/analyzer.py), [`foreguard/core/extractor.py`](../../foreguard/core/extractor.py),
  [`foreguard/core/rules.py`](../../foreguard/core/rules.py), [`foreguard/core/ml_model.py`](../../foreguard/core/ml_model.py)
- API: [`foreguard/api/main.py`](../../foreguard/api/main.py), [`foreguard/api/routes/analyze.py`](../../foreguard/api/routes/analyze.py),
  [`foreguard/api/routes/logs.py`](../../foreguard/api/routes/logs.py), [`foreguard/api/schemas.py`](../../foreguard/api/schemas.py)
- Banco: [`foreguard/db/models.py`](../../foreguard/db/models.py), [`foreguard/db/session.py`](../../foreguard/db/session.py)
- README da raiz: [`README.md`](../../README.md)
