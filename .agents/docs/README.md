# Documentação do Foreguard

Documentação interna do Foreguard — API de análise de risco de requisições
HTTP em tempo real — organizada em estilo **Spec-Driven Development (SDD)**: as
especificações descrevem o comportamento esperado e direcionam a evolução do
código. Cada arquivo aqui é fonte verificável — quando código e spec divergem,
um dos dois precisa ser corrigido (e o MR/PR deve registrar qual).
`.agents/docs` indica que a estrutura também foi pensada para consumo por
agentes/assistentes IA.

## Estrutura

- [`overview.md`](./overview.md) — produto, audiência, stack, domínios e
  glossário.
- [`architecture/`](./architecture/) — estado atual e alvo da arquitetura
  ([`overview.md`](./architecture/overview.md)).
- [`guides/`](./guides/) — guias operacionais
  ([`getting-started.md`](./guides/getting-started.md),
  [`middleware.md`](./guides/middleware.md)).
- [`specs/`](./specs/) — especificações por domínio:
  - [`arquitetura.md`](./specs/arquitetura.md) — layout de pacotes, config,
    banco/migrações, robustez da API.
  - [`deteccao.md`](./specs/deteccao.md) — superfície inspecionada e padrões
    de SQLi/XSS/path traversal do extrator.
  - [`integracao.md`](./specs/integracao.md) — contrato HTTP com a
    aplicação-cliente, auth, modos de log, fail-open, mascaramento.
  - [`instalacao.md`](./specs/instalacao.md) — instalador só-Python e CLI.

TODO: `guides/development.md`, `guides/commit-conventions.md`,
`architecture/deployment.md` — sem evidência no repositório ainda (não há
CI nem processo de deploy definido).

## Como contribuir

Ao alterar código que muda comportamento observável, atualize a spec
correspondente no mesmo MR/PR. Fluxo: spec → testes (red) → implementação
(green); divergência descoberta na implementação volta para a spec.

## Convenções de estilo (todos os arquivos)

- Idioma: pt-BR. Identificadores em inglês quando o código também usa.
- Cada arquivo começa com seção curta **Objetivo / Audiência**.
- Cada arquivo termina com **Referências** apontando para caminhos de código.
- Diagramas em `mermaid`/ASCII quando úteis; preferir prosa curta a diagrama
  vago.
- Linhas curtas; tabelas podem ser largas.

## Verificação de integridade

Para checar se nenhum link relativo dentro de `.agents/docs/**/*.md` aponta
para arquivo inexistente, rode na raiz do repositório:

```sh
find .agents/docs -name '*.md' | while read f; do
  dir=$(dirname "$f")
  grep -oE '\]\([^)]+\)' "$f" | sed -E 's/^\]\(([^)]+)\)$/\1/' | \
  while read link; do
    case "$link" in
      http://*|https://*|mailto:*|tel:*|\#*) continue ;;
    esac
    target="${link%#*}"
    target="${target%\?*}"
    [ -z "$target" ] && continue
    [ ! -e "$dir/$target" ] && echo "BROKEN: $f → $link"
  done
done
```

Saída vazia = todos os links resolvem.
