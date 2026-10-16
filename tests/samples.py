"""Requisições de exemplo compartilhadas pelos testes."""

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def make_request(**overrides) -> dict:
    """Requisição benigna base; campos sobrescritos via kwargs."""
    request = {
        "method": "GET",
        "path": "/",
        "headers": {},
        "body": None,
        "query_params": {},
        "ip": "8.8.8.8",
        "user_agent": BROWSER_UA,
        "jwt_token": None,
    }
    request.update(overrides)
    return request


SAFE_REQUEST = {
    "method": "GET",
    "path": "/products",
    "headers": {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    "body": None,
    "query_params": {"page": "1"},
    "ip": "177.45.23.100",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "jwt_token": None,
}

SQLI_REQUEST = {
    "method": "POST",
    "path": "/login",
    "headers": {"user-agent": "Mozilla/5.0"},
    "body": {"username": "admin", "password": "' OR '1'='1' --"},
    "query_params": {},
    "ip": "203.0.113.42",
    "user_agent": "Mozilla/5.0",
    "jwt_token": None,
}

SCANNER_REQUEST = {
    "method": "GET",
    "path": "/admin",
    "headers": {"user-agent": "sqlmap/1.7.8"},
    "body": None,
    "query_params": {},
    "ip": "198.51.100.5",
    "user_agent": "sqlmap/1.7.8",
    "jwt_token": None,
}

XSS_REQUEST = {
    "method": "POST",
    "path": "/comment",
    "headers": {"user-agent": "Mozilla/5.0"},
    "body": {"comment": "<script>alert('xss')</script>"},
    "query_params": {},
    "ip": "10.0.0.5",
    "user_agent": "Mozilla/5.0",
    "jwt_token": None,
}

# Payload de exemplo do schema IncomingRequest (ARQ-07)
EXAMPLE_PAYLOAD = {
    "method": "POST",
    "path": "/login",
    "headers": {"content-type": "application/json", "user-agent": "Mozilla/5.0"},
    "body": {"username": "admin", "password": "' OR '1'='1"},
    "query_params": {},
    "ip": "192.168.1.100",
    "user_agent": "Mozilla/5.0",
    "jwt_token": None,
}
