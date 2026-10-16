import hmac

from fastapi import Header, HTTPException, Request

from foreguard.config import MIN_API_KEY_LENGTH, get_settings

API_KEY_HEADER = "X-Foreguard-Key"


def require_valid_key_config() -> str:
    """Valida a chave configurada; chamada no startup."""
    key = get_settings().FOREGUARD_API_KEY
    if not key or len(key) < MIN_API_KEY_LENGTH:
        raise RuntimeError(
            f"FOREGUARD_API_KEY ausente ou com menos de {MIN_API_KEY_LENGTH} caracteres "
            "— gere uma com `foreguard install`"
        )
    return key


def require_api_key(x_foreguard_key: str | None = Header(default=None, alias=API_KEY_HEADER)):
    """Dependency das rotas /v1 — compara a chave em tempo constante."""
    expected = get_settings().FOREGUARD_API_KEY or ""
    received = x_foreguard_key or ""
    if not expected or not hmac.compare_digest(received.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Chave de API inválida")


async def limit_request_size(request: Request):
    """Dependency de /v1/analyze — 413 acima de MAX_REQUEST_BYTES, antes da análise."""
    limit = get_settings().MAX_REQUEST_BYTES
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail=f"Requisição maior que {limit} bytes")
    if len(await request.body()) > limit:
        raise HTTPException(status_code=413, detail=f"Requisição maior que {limit} bytes")
