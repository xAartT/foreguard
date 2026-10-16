"""
Motor de regras estáticas.
Serve como baseline de comparação com o modelo ML
e como fallback quando o modelo não está disponível.
"""
from dataclasses import dataclass, field


@dataclass
class RuleResult:
    score: float = 0.0
    reasons: list = field(default_factory=list)


class RulesEngine:

    RULES = [
        # (feature, condição, pontuação, mensagem)
        ("has_sqli",            lambda v: v == 1,       4.0, "Padrão de SQL Injection detectado"),
        ("has_xss",             lambda v: v == 1,       3.5, "Padrão de XSS detectado"),
        ("has_path_traversal",  lambda v: v == 1,       3.0, "Tentativa de path traversal detectada"),
        ("ua_is_scanner",       lambda v: v == 1,       2.5, "Scanner de segurança conhecido detectado (ex: sqlmap, nikto)"),
        ("ua_is_empty",         lambda v: v == 1,       1.5, "User-Agent ausente"),
        ("ua_is_bot",           lambda v: v == 1,       1.0, "User-Agent de bot detectado"),
        ("ip_has_proxy_header", lambda v: v == 1,       0.8, "Tentativa de spoofing via proxy headers"),
        ("has_suspicious_hdrs", lambda v: v == 1,       0.5, "Headers suspeitos de IP presentes"),
        ("body_length",         lambda v: v > 10000,    1.0, "Corpo da requisição anormalmente grande"),
        ("param_count",         lambda v: v > 20,       0.5, "Número excessivo de parâmetros"),
        ("payload_entropy",     lambda v: v > 4.5,      0.8, "Alta entropia no payload — possível ofuscação"),
        ("method_risk",         lambda v: v >= 1.0,     0.5, "Método HTTP de alto risco (DELETE/TRACE)"),
    ]

    def evaluate(self, features: dict) -> RuleResult:
        result = RuleResult()

        for feature, condition, points, reason in self.RULES:
            value = features.get(feature, 0)
            if condition(value):
                result.score += points
                result.reasons.append(reason)

        result.score = round(min(result.score, 10.0), 2)
        return result
