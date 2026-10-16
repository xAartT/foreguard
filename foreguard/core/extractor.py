"""
Extrai features de uma requisição HTTP para alimentar o motor de análise.
Cada feature representa um sinal de risco independente.
Comportamento especificado em .agents/docs/specs/deteccao.md.
"""
import ipaddress
import json
import math
import re
from urllib.parse import unquote

from user_agents import parse as ua_parse

# ── Padrões de ataque ─────────────────────────────────────────────────────────
# Contextuais: exigem a "quebra" de sintaxe (aspas + operador, comentário,
# UNION SELECT, stacked query…) em vez de casar caractere ou palavra soltos.
# Quantificadores limitados para manter custo linear em payloads grandes.

SQLI_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    r"'\s{0,10}(?:or|and)\s{1,10}(?:'[^']{0,50}'|\w{1,50})\s{0,10}(?:=|<|>|like\b)",   # ' OR '1'='1
    r"\b(?:or|and)\s{1,10}(\d{1,10})\s{0,10}=\s{0,10}\1\b",                          # OR 1=1
    r"'\s{0,10}(?:--|#|/\*)",                                                        # admin'--
    r"\bunion(?:\s{1,10}all)?\s{1,10}select\b",
    r";\s{0,10}(?:drop|delete|insert|update|exec|execute|truncate|alter|create|shutdown)\b",
    r"\b(?:sleep|pg_sleep|benchmark)\s{0,10}\(\s{0,10}\d",
    r"\bwaitfor\s{1,10}delay\b",
)]

XSS_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    r"<\s{0,10}script\b",
    r"<[a-z][^<>]{0,300}?[\s/\"']on[a-z]{2,30}\s{0,10}=",   # <img src=x onerror=…>
    r"<\s{0,10}(?:iframe|frame|object|embed)\b",
    r"(?:javascript|vbscript)\s{0,10}:",
    r"['\"]\s{0,10};?\s{0,10}(?:alert|confirm|prompt|eval)\s{0,10}\(",   # ';alert(1)
)]

PATH_TRAVERSAL_PATTERNS = [re.compile(r"\.\.[\\/]")]

SCANNERS = [
    "sqlmap", "nikto", "nmap", "masscan", "zgrab",
    "dirbuster", "gobuster", "wfuzz", "burpsuite",
    "hydra", "metasploit", "openvas",
]

PROXY_HEADERS = {
    "via", "forwarded", "x-forwarded-host",
    "x-originating-ip", "x-remote-ip", "x-remote-addr",
}

SUSPICIOUS_HEADERS = {
    "x-forwarded-for", "x-real-ip", "x-cluster-client-ip",
}

METHOD_RISK = {
    "GET": 0.0, "HEAD": 0.0,
    "POST": 0.5, "PATCH": 0.6,
    "PUT": 0.8, "DELETE": 1.0,
    "OPTIONS": 0.3, "TRACE": 1.0,
}

BODY_LENGTH_CAP = 50000
DECODE_ROUNDS   = 2   # cobre double encoding (%252e → %2e → .)


# ── Extrator principal ────────────────────────────────────────────────────────

class FeatureExtractor:

    def extract(self, request: dict) -> dict:
        """
        Recebe o dicionário da requisição e retorna um dicionário de features.
        Todas as features são numéricas (int ou float) para compatibilidade com ML.
        """
        path      = request.get("path", "") or ""
        body      = request.get("body")
        headers   = request.get("headers", {}) or {}
        ip        = request.get("ip", "127.0.0.1") or "127.0.0.1"
        method    = request.get("method", "GET") or "GET"
        params    = request.get("query_params", {}) or {}
        jwt       = request.get("jwt_token", "") or ""
        ua_string = request.get("user_agent") or self._header(headers, "user-agent")

        body_text = self._body_text(body)

        # Superfície inspecionada (cada texto avaliado isoladamente)
        injection_texts = [path, *_texts(params, keys=True), *_texts(body, keys=True),
                           *_texts(list(headers.values()), keys=False)]
        traversal_texts = [path, *_texts(params, keys=False), *_texts(body, keys=False)]

        return {
            # ── Payload ──────────────────────────────────────────────────
            "has_sqli":            self._match(injection_texts, SQLI_PATTERNS),
            "has_xss":             self._match(injection_texts, XSS_PATTERNS),
            "has_path_traversal":  self._match(traversal_texts, PATH_TRAVERSAL_PATTERNS),
            "body_length":         min(len(body_text), BODY_LENGTH_CAP),
            "path_length":         len(path),
            "param_count":         len(params),
            "payload_entropy":     self._entropy(path + " " + body_text),

            # ── User-Agent ───────────────────────────────────────────────
            "ua_is_bot":           self._is_bot(ua_string),
            "ua_is_empty":         int(not ua_string.strip()),
            "ua_is_scanner":       self._is_scanner(ua_string),

            # ── IP ───────────────────────────────────────────────────────
            "ip_is_private":       self._is_private(ip),
            "ip_has_proxy_header": self._has_proxy_headers(headers),

            # ── Headers ──────────────────────────────────────────────────
            "has_suspicious_hdrs": self._has_suspicious_headers(headers),
            "header_count":        len(headers),
            "has_jwt":             int(bool(jwt.strip())),

            # ── Método HTTP ──────────────────────────────────────────────
            "method_risk":         METHOD_RISK.get(method.upper(), 1.0),
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _match(self, texts: list[str], patterns: list[re.Pattern]) -> int:
        for text in texts:
            for variant in _decoded_variants(text):
                if any(p.search(variant) for p in patterns):
                    return 1
        return 0

    def _body_text(self, body) -> str:
        if body is None:
            return ""
        if isinstance(body, str):
            return body
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))

    def _header(self, headers: dict, name: str) -> str:
        for key, value in headers.items():
            if key.lower() == name:
                if isinstance(value, list):
                    return str(value[0]) if value else ""
                return str(value)
        return ""

    def _is_bot(self, ua_string: str) -> int:
        if not ua_string:
            return 0
        try:
            return int(ua_parse(ua_string).is_bot)
        except Exception:
            return 0

    def _is_scanner(self, ua_string: str) -> int:
        ua_lower = ua_string.lower()
        return int(any(s in ua_lower for s in SCANNERS))

    def _has_proxy_headers(self, headers: dict) -> int:
        keys = {k.lower() for k in headers.keys()}
        return int(bool(PROXY_HEADERS & keys))

    def _has_suspicious_headers(self, headers: dict) -> int:
        keys = {k.lower() for k in headers.keys()}
        return int(bool(SUSPICIOUS_HEADERS & keys))

    def _is_private(self, ip: str) -> int:
        try:
            return int(ipaddress.ip_address(ip).is_private)
        except ValueError:
            return 0

    def _entropy(self, text: str) -> float:
        """Entropia de Shannon — payloads ofuscados tendem a ter alta entropia."""
        if not text:
            return 0.0
        freq = {}
        for c in text:
            freq[c] = freq.get(c, 0) + 1
        length = len(text)
        return -sum((f / length) * math.log2(f / length) for f in freq.values())


def _texts(value, keys: bool) -> list[str]:
    """
    Achata um valor JSON em textos: strings, escalares convertidos com str()
    e, se `keys`, as chaves dos objetos. Iterativo — sem RecursionError.
    """
    out, stack = [], [value]
    while stack:
        item = stack.pop()
        if item is None:
            continue
        if isinstance(item, dict):
            if keys:
                out.extend(str(k) for k in item.keys())
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        else:
            out.append(item if isinstance(item, str) else str(item))
    return out


def _decoded_variants(text: str) -> list[str]:
    """Texto original + até DECODE_ROUNDS rodadas de URL-decode (sem repetidos)."""
    variants = [text]
    for _ in range(DECODE_ROUNDS):
        decoded = unquote(variants[-1])
        if decoded == variants[-1]:
            break
        variants.append(decoded)
    return variants
