# Spec — Detecção (extração de features)

## Objetivo

Corrigir os falsos positivos e falsos negativos do `FeatureExtractor`,
definindo **qual parte da requisição é inspecionada**, **como é normalizada**
e **o que deve ou não ser detectado** como SQLi, XSS e path traversal —
mantendo o vetor de features compatível com o motor de regras e com o
futuro modelo ML.

## Audiência

- **Devs** — contrato do extrator e corpus de exemplos obrigatórios.
- **Assistentes/agentes IA** — fonte para derivar testes parametrizados.

---

## Problemas que motivaram a spec (código anterior, já corrigidos)

| Problema | Exemplo | Resultado antes |
| -------- | ------- | --------------- |
| Body serializado com `str(dict)` gera aspas simples, que casam com o padrão `'` | `POST /users {"name": "Ana"}` | `has_sqli=1`, score 4.0 |
| `#` e palavras SQL soltas casam | `/docs#intro`, `/profile/update` | `has_sqli=1`, score 4.0 |
| `query_params` e headers não são inspecionados | `GET /search?q=' OR 1=1--` | score 0.0 |
| Sem URL-decode; `%3C` sozinho conta como XSS | `?q=price %3C 100` | `has_xss=1` |
| `user_agent` nulo ignora o header `User-Agent` | só header presente | `ua_is_empty=1` |

## Escopo

**Entra:** superfície inspecionada, normalização (URL-decode), padrões de
SQLi/XSS/path traversal, cálculo de `body_length`/`payload_entropy` para
bodies não-dict, fallback do User-Agent, tipos aceitos em `body`,
`query_params` e `headers`.

**Fica de fora:**

- Pesos das regras, thresholds, recomendações (spec de calibração — TODO).
  Consequência conhecida: SQLi isolado continua `MEDIUM` (4.0).
- Novas features, ou mudança de nome/ordem/tipo das 16 existentes
  (`FEATURE_ORDER` permanece idêntico).
- Detecção de outras classes (SSRF, command injection, NoSQLi, rate limit).
- Reestruturação de pacotes → [`arquitetura.md`](./arquitetura.md).

## Contrato

### Entrada (`IncomingRequest`)

| Campo | Antes | Depois |
| ----- | ----- | ------ |
| `body` | `dict \| None` | qualquer JSON: objeto, array, string, número, booleano ou `null` |
| `query_params` | `dict \| None` | `dict[str, str \| list[str]] \| None` |
| `headers` | `dict` | `dict[str, str \| list[str]]` |

Demais campos inalterados. A saída de `/analyze` não muda.

### Superfície inspecionada

| Feature | Onde os padrões são aplicados |
| ------- | ----------------------------- |
| `has_sqli`, `has_xss` | path, chaves e valores de `query_params`, chaves e valores (recursivos) de `body`, valores de `headers` |
| `has_path_traversal` | path, valores de `query_params`, valores (recursivos) de `body` |

Cada texto é avaliado **isoladamente** (não concatenado), em duas formas:
original e URL-decodificado até 2 vezes (cobre double encoding). Escalares
não-string do body (número, booleano) são convertidos com `str()`; `null` é
ignorado.

### Demais features

- `body_length`: comprimento do body como texto — string: o próprio texto;
  demais tipos: JSON compacto (`separators=(",", ":")`, `ensure_ascii=False`);
  `null` → 0. Teto 50000 (inalterado).
- `payload_entropy`: entropia de Shannon de `path + " " + body_como_texto`
  (sem decode — ofuscação por encoding é o sinal).
- `ua_is_empty` / `ua_is_bot` / `ua_is_scanner`: usam `user_agent`; se
  ausente ou vazio, usam o header `User-Agent` (nome case-insensitive).
- Demais features: inalteradas.

## Critérios de aceite

| ID | Critério |
| -- | -------- |
| DET-01 | `extract()` retorna exatamente as 16 chaves de `FEATURE_ORDER`, todas `int` ou `float`. |
| DET-02 | Todo exemplo da tabela **Deve detectar** produz a feature indicada = 1. |
| DET-03 | Nenhum exemplo da tabela **Não deve detectar** produz `has_sqli`, `has_xss` ou `has_path_traversal` = 1. |
| DET-04 | Requisição benigna `POST /users`, body `{"name": "Ana", "email": "ana@ex.com"}`, UA de navegador, termina com `risk_level == "LOW"` e `reasons == []`. |
| DET-05 | Payload malicioso em `query_params` é detectado igual ao mesmo payload no body. |
| DET-06 | Payload malicioso no valor de um header (ex.: `Referer`) ativa `has_sqli`/`has_xss`. |
| DET-07 | Payload em **chave** do body ou de `query_params` ativa `has_sqli`/`has_xss`. |
| DET-08 | Payload em objeto aninhado (≥ 3 níveis) ou dentro de array no body é detectado. |
| DET-09 | `body` como string, array, número, booleano e `null` é aceito por `POST /analyze` (200) e pelo extrator, sem exceção. |
| DET-10 | `body_length` de `{"a":"b"}` é 9; de `"abc"` é 3; de `null` é 0; de string com 60000 chars é 50000. |
| DET-11 | Com `user_agent=null` e header `User-Agent: Mozilla/5.0 ...`, `ua_is_empty == 0`; com header `user-agent: sqlmap/1.7`, `ua_is_scanner == 1`. |
| DET-12 | Percent-encoding inválido (`%zz`, `%`) não gera exceção e o texto segue inspecionado literalmente. |
| DET-13 | Body de 200 000 caracteres é extraído em menos de 1 s (sem backtracking catastrófico). |
| DET-14 | Body aninhado em 100 níveis não gera exceção (travessia não recursiva ou com limite). |
| DET-15 | `test_extract_*` e `test_rules_*` existentes continuam passando. |

## Corpus de exemplos

Cada exemplo é avaliado como valor de body `{"q": <exemplo>}` **e** como
valor de `query_params` `{"q": <exemplo>}`, exceto quando a coluna "Onde"
indicar outro local.

### Deve detectar

| Feature | Exemplo | Onde |
| ------- | ------- | ---- |
| `has_sqli` | `' OR '1'='1` | |
| `has_sqli` | `' OR 1=1--` | |
| `has_sqli` | `admin'--` | |
| `has_sqli` | `admin' #` | |
| `has_sqli` | `1 UNION SELECT username, password FROM users` | |
| `has_sqli` | `1 union all select null,null--` | |
| `has_sqli` | `1; DROP TABLE users` | |
| `has_sqli` | `'; WAITFOR DELAY '0:0:5'--` | |
| `has_sqli` | `1 AND SLEEP(5)` | |
| `has_sqli` | `1' AND BENCHMARK(1000000,MD5(1))--` | |
| `has_sqli` | `%27%20OR%201%3D1--` | |
| `has_sqli` | `%2527%2520OR%25201%253D1--` | |
| `has_sqli` | `/items/1' OR '1'='1` | path |
| `has_xss` | `<script>alert(1)</script>` | |
| `has_xss` | `<img src=x onerror=alert(1)>` | |
| `has_xss` | `<svg/onload=alert(1)>` | |
| `has_xss` | `<iframe src="https://evil.example">` | |
| `has_xss` | `javascript:alert(document.cookie)` | |
| `has_xss` | `"><script>alert(1)</script>` | |
| `has_xss` | `';alert(1);//` | |
| `has_xss` | `%3Cscript%3Ealert(1)%3C%2Fscript%3E` | |
| `has_path_traversal` | `/files/../../etc/passwd` | path |
| `has_path_traversal` | `../../etc/passwd` | |
| `has_path_traversal` | `..\..\windows\win.ini` | |
| `has_path_traversal` | `..%2f..%2fetc%2fpasswd` | |
| `has_path_traversal` | `%2e%2e%2f%2e%2e%2fetc%2fpasswd` | |
| `has_path_traversal` | `%252e%252e%252fetc%252fpasswd` | |

### Não deve detectar

| Exemplo | Onde |
| ------- | ---- |
| `Ana` | |
| `O'Brien` | |
| `Don't stop me now` | |
| `Rock and roll` | |
| `Please select an option from the menu` | |
| `I will update the order and delete the draft` | |
| `Note -- see below` | |
| `price < 100 and > 10` | |
| `price %3C 100` | |
| `I will alert you tomorrow` | |
| `online = 'yes'` | |
| `Loading...` | |
| `ana@ex.com` | |
| `/docs#intro` | path |
| `/profile/update` | path |
| `/orders/delete/42` | path |
| `/docs/v1.2/readme` | path |
| `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36` | header `User-Agent` |
| `text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8` | header `Accept` |

## Casos-limite e erros

- **Encoding inválido / parcial:** sem exceção; inspeciona o literal (DET-12).
- **Body enorme:** linear no tamanho; sem truncar a inspeção (truncar abriria
  evasão por padding) — ver decisão 1.
- **Aninhamento profundo:** sem `RecursionError` (DET-14). JSON além do
  limite de parsing do Pydantic pode virar 422 na API — aceitável; 500 não.
- **Header com valor lista:** cada item inspecionado.

## Decisões (aprovadas no gate da Fase 1)

1. O body é inspecionado inteiro (sem truncar); limite de tamanho do
   `POST /analyze` fica para a spec de segurança.
2. Valores de **todos** os headers são inspecionados (para `has_sqli` e
   `has_xss`), inclusive `Cookie` e `Authorization`.
3. Os padrões são definidos pelo comportamento do corpus, não por regex
   prescrito — a implementação escolhe as regex desde que o corpus passe.

## Rastreabilidade (testes em `tests/`)

| Critério | Testes |
| -------- | ------ |
| DET-01 | `test_extractor.py::test_det01_feature_keys_and_types` |
| DET-02 | `test_extractor.py::test_det02_must_detect` (corpus, body + query) |
| DET-03 | `test_extractor.py::test_det03_must_not_detect` (corpus, body + query) |
| DET-04 | `test_analyzer.py::test_det04_benign_post_with_body_is_low` |
| DET-05 | `test_extractor.py::test_det05_query_and_body_equivalent` |
| DET-06 | `test_extractor.py::test_det06_header_values_inspected` |
| DET-07 | `test_extractor.py::test_det07_keys_inspected` |
| DET-08 | `test_extractor.py::test_det08_nested_body_inspected` |
| DET-09 | `test_extractor.py::test_det09_*` (extrator e API) |
| DET-10 | `test_extractor.py::test_det10_body_length` |
| DET-11 | `test_extractor.py::test_det11_*` |
| DET-12 | `test_extractor.py::test_det12_invalid_percent_encoding_is_literal` |
| DET-13 | `test_extractor.py::test_det13_large_body_is_linear` |
| DET-14 | `test_extractor.py::test_det14_deeply_nested_body` |
| DET-15 | `test_extractor.py::test_extract_*`, `test_rules.py` |

---

## Referências

- Extrator: [`foreguard/core/extractor.py`](../../../foreguard/core/extractor.py)
- Regras e pesos: [`foreguard/core/rules.py`](../../../foreguard/core/rules.py)
- Ordem das features (ML): [`foreguard/core/ml_model.py`](../../../foreguard/core/ml_model.py)
- Schema de entrada: [`foreguard/api/schemas.py`](../../../foreguard/api/schemas.py)
- Testes: [`tests/`](../../../tests/)
