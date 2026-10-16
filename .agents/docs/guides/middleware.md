# Guia — escrevendo o middleware da aplicação-cliente

## Objetivo

Orientar quem integra uma aplicação (qualquer linguagem/framework) ao
Foreguard: o que enviar, o que recebe, como tratar falhas (fail-open) e como
usar o resultado. Contrato formal em
[`../specs/integracao.md`](../specs/integracao.md).

## Audiência

- **Devs de aplicações-cliente** — implementar o middleware.
- **Assistentes/agentes IA** — gerar middlewares para stacks específicas.

---

## Chamada

```
POST http://127.0.0.1:8000/v1/analyze
Content-Type: application/json
X-Foreguard-Key: <FOREGUARD_API_KEY do .env do Foreguard>
```

```json
{
  "method": "POST",
  "path": "/login",
  "headers": {"user-agent": "Mozilla/5.0", "referer": "https://app/x"},
  "query_params": {"next": "/home"},
  "body": {"username": "ana", "password": "segredo"},
  "ip": "203.0.113.42",
  "user_agent": "Mozilla/5.0",
  "jwt_token": null
}
```

| Campo | Origem na aplicação |
| ----- | ------------------- |
| `method`, `path` | método e path da requisição (sem querystring) |
| `headers` | headers recebidos; valor lista quando repetido |
| `query_params` | querystring decodificada; lista quando a chave repete |
| `body` | corpo já parseado (JSON/form) — qualquer valor JSON |
| `ip` | IP real do usuário (resolva `X-Forwarded-For` só se confiar no proxy) |
| `user_agent`, `jwt_token` | opcionais |

**Não envie** uploads/multipart nem binários: mande `body: null` (ou só os
campos de texto). O limite é `MAX_REQUEST_BYTES` (1 MiB) → acima disso, 413.

## Resposta

```json
{
  "log_id": "6f1c…",
  "timestamp": "2026-10-08T13:06:17.352314Z",
  "risk_score": 4.0,
  "risk_level": "MEDIUM",
  "reasons": ["Padrão de SQL Injection detectado"],
  "recommendation": "CHALLENGE: …",
  "analysis_source": "rules"
}
```

A decisão é da aplicação. Exemplo de política:

| `risk_level` | Sugestão |
| ------------ | -------- |
| `LOW` | prosseguir |
| `MEDIUM` | prosseguir e registrar, ou exigir CAPTCHA/reautenticação |
| `HIGH` | bloquear a requisição (403) |
| `CRITICAL` | bloquear e alertar a equipe |

## Fail-open (obrigatório)

O Foreguard nunca pode derrubar a aplicação:

```
try:
    resp = http.post(url, json=payload, headers=auth, timeout=0.2)  # 200 ms
    if resp.status == 200:
        aplicar_politica(resp.json())
    # qualquer outro status: segue sem análise
except (timeout, conexão recusada, erro qualquer):
    pass  # fail-open: segue o processamento normal
continuar_requisicao()
```

- **Timeout curto** (sugestão: 200 ms total). A análise local leva poucos
  milissegundos.
- 401 indica chave errada na configuração: registre no log da aplicação, mas
  siga em frente.
- Reutilize a conexão HTTP (keep-alive / pool) — cada requisição da aplicação
  gera uma chamada.

## Logs

- **`LOG_STORAGE=database`:** o Foreguard grava cada análise (com campos
  sensíveis mascarados); consulte por `GET /v1/logs`.
- **`LOG_STORAGE=client`:** o Foreguard não grava nada. Se quiser histórico,
  a aplicação armazena a resposta (`log_id`, `timestamp`, score, nível,
  motivos) junto com os dados da requisição que já possui.

O modo vigente aparece em `GET /health` (`log_storage`).

---

## Referências

- Contrato: [`../specs/integracao.md`](../specs/integracao.md)
- Entrada aceita: [`../specs/deteccao.md`](../specs/deteccao.md)
- Instalação: [`../specs/instalacao.md`](../specs/instalacao.md)
- Schemas atuais: [`foreguard/api/schemas.py`](../../../foreguard/api/schemas.py)
