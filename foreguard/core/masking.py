"""
Mascara dados sensíveis da requisição antes de persisti-la.
A análise usa sempre a requisição original; só o registro gravado é mascarado.
Comportamento especificado em .agents/docs/specs/integracao.md.
"""
MASK = "***"

SENSITIVE_HEADERS = {
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "x-foreguard-key",
}

# Termos procurados (case-insensitive) no nome dos campos de body/query_params
SENSITIVE_TERMS = (
    "password", "senha", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "cpf", "cnpj", "card", "cartao", "cvv",
)


def mask_request(request: dict, extra_terms: list[str] | tuple[str, ...] = ()) -> dict:
    """Retorna uma cópia da requisição com valores sensíveis trocados por MASK."""
    terms = tuple(t.lower() for t in (*SENSITIVE_TERMS, *extra_terms))
    masked = dict(request)

    if masked.get("jwt_token"):
        masked["jwt_token"] = MASK

    headers = masked.get("headers") or {}
    masked["headers"] = {
        name: MASK if name.lower() in SENSITIVE_HEADERS else value
        for name, value in headers.items()
    }

    for field in ("query_params", "body"):
        if masked.get(field) is not None:
            masked[field] = _mask_fields(masked[field], terms)
    return masked


def _mask_fields(value, terms: tuple[str, ...]):
    if isinstance(value, dict):
        return {
            key: MASK if _is_sensitive(key, terms) else _mask_fields(item, terms)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_fields(item, terms) for item in value]
    return value


def _is_sensitive(key, terms: tuple[str, ...]) -> bool:
    name = str(key).lower()
    return any(term in name for term in terms)
