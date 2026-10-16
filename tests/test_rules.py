"""Motor de regras — testes legados (ARQ-19, DET-15)."""
from foreguard.core.extractor import FeatureExtractor
from foreguard.core.rules import RulesEngine

from samples import SAFE_REQUEST, SCANNER_REQUEST, SQLI_REQUEST

extractor = FeatureExtractor()
rules = RulesEngine()


def test_rules_safe_request():
    r = rules.evaluate(extractor.extract(SAFE_REQUEST))
    assert r.score < 3.0
    assert len(r.reasons) == 0


def test_rules_sqli_high_score():
    r = rules.evaluate(extractor.extract(SQLI_REQUEST))
    assert r.score >= 4.0
    assert any("SQL" in reason for reason in r.reasons)


def test_rules_scanner_detected():
    r = rules.evaluate(extractor.extract(SCANNER_REQUEST))
    assert r.score >= 2.5
    assert any("Scanner" in reason for reason in r.reasons)


def test_rules_score_cap():
    """Score nunca deve ultrapassar 10.0."""
    malicious = {k: 1 for k in ["has_sqli", "has_xss", "has_path_traversal",
                                "ua_is_scanner", "ua_is_empty", "ua_is_bot",
                                "ip_has_proxy_header", "has_suspicious_hdrs"]}
    malicious.update({"body_length": 50000, "param_count": 30,
                      "payload_entropy": 5.0, "method_risk": 1.0})
    assert rules.evaluate(malicious).score <= 10.0
