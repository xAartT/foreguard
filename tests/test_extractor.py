"""Extrator de features — specs/deteccao.md (DET-*) e testes legados (DET-15)."""
import time

import pytest

from foreguard.core.extractor import FeatureExtractor
from foreguard.core.ml_model import FEATURE_ORDER

from samples import (
    BROWSER_UA,
    SAFE_REQUEST,
    SCANNER_REQUEST,
    SQLI_REQUEST,
    XSS_REQUEST,
    make_request,
)

extractor = FeatureExtractor()
ATTACK_FEATURES = ("has_sqli", "has_xss", "has_path_traversal")


# ── Testes legados (DET-15) ──────────────────────────────────────────────────

def test_extract_safe_request():
    f = extractor.extract(SAFE_REQUEST)
    assert f["has_sqli"] == 0
    assert f["has_xss"] == 0
    assert f["ua_is_empty"] == 0
    assert f["method_risk"] == 0.0


def test_extract_sqli():
    assert extractor.extract(SQLI_REQUEST)["has_sqli"] == 1


def test_extract_xss():
    assert extractor.extract(XSS_REQUEST)["has_xss"] == 1


def test_extract_scanner():
    assert extractor.extract(SCANNER_REQUEST)["ua_is_scanner"] == 1


# ── DET-01: contrato do vetor ────────────────────────────────────────────────

def test_det01_feature_keys_and_types():
    f = extractor.extract(make_request(body={"a": [1, "x"]}))
    assert set(f.keys()) == set(FEATURE_ORDER)
    assert len(FEATURE_ORDER) == 16
    for key, value in f.items():
        assert type(value) in (int, float), key


# ── DET-02 / DET-03: corpus ─────────────────────────────────────────────────

MUST_DETECT = [
    ("has_sqli", "' OR '1'='1", None),
    ("has_sqli", "' OR 1=1--", None),
    ("has_sqli", "admin'--", None),
    ("has_sqli", "admin' #", None),
    ("has_sqli", "1 UNION SELECT username, password FROM users", None),
    ("has_sqli", "1 union all select null,null--", None),
    ("has_sqli", "1; DROP TABLE users", None),
    ("has_sqli", "'; WAITFOR DELAY '0:0:5'--", None),
    ("has_sqli", "1 AND SLEEP(5)", None),
    ("has_sqli", "1' AND BENCHMARK(1000000,MD5(1))--", None),
    ("has_sqli", "%27%20OR%201%3D1--", None),
    ("has_sqli", "%2527%2520OR%25201%253D1--", None),
    ("has_sqli", "/items/1' OR '1'='1", "path"),
    ("has_xss", "<script>alert(1)</script>", None),
    ("has_xss", "<img src=x onerror=alert(1)>", None),
    ("has_xss", "<svg/onload=alert(1)>", None),
    ("has_xss", '<iframe src="https://evil.example">', None),
    ("has_xss", "javascript:alert(document.cookie)", None),
    ("has_xss", '"><script>alert(1)</script>', None),
    ("has_xss", "';alert(1);//", None),
    ("has_xss", "%3Cscript%3Ealert(1)%3C%2Fscript%3E", None),
    ("has_path_traversal", "/files/../../etc/passwd", "path"),
    ("has_path_traversal", "../../etc/passwd", None),
    ("has_path_traversal", r"..\..\windows\win.ini", None),
    ("has_path_traversal", "..%2f..%2fetc%2fpasswd", None),
    ("has_path_traversal", "%2e%2e%2f%2e%2e%2fetc%2fpasswd", None),
    ("has_path_traversal", "%252e%252e%252fetc%252fpasswd", None),
]

MUST_NOT_DETECT = [
    ("Ana", None),
    ("O'Brien", None),
    ("Don't stop me now", None),
    ("Rock and roll", None),
    ("Please select an option from the menu", None),
    ("I will update the order and delete the draft", None),
    ("Note -- see below", None),
    ("price < 100 and > 10", None),
    ("price %3C 100", None),
    ("I will alert you tomorrow", None),
    ("online = 'yes'", None),
    ("Loading...", None),
    ("ana@ex.com", None),
    ("/docs#intro", "path"),
    ("/profile/update", "path"),
    ("/orders/delete/42", "path"),
    ("/docs/v1.2/readme", "path"),
    (BROWSER_UA, "header:User-Agent"),
    ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "header:Accept"),
]


def _placements(example: str, where: str | None):
    """Gera (id, request) para cada local onde o exemplo deve ser avaliado."""
    if where == "path":
        return [("path", make_request(path=example))]
    if where and where.startswith("header:"):
        name = where.split(":", 1)[1]
        return [(where, make_request(headers={name: example}))]
    return [
        ("body", make_request(method="POST", path="/search", body={"q": example})),
        ("query", make_request(path="/search", query_params={"q": example})),
    ]


@pytest.mark.parametrize(
    "feature,request_,place",
    [
        pytest.param(feat, req, place, id=f"{feat}|{place}|{ex}")
        for feat, ex, where in MUST_DETECT
        for place, req in _placements(ex, where)
    ],
)
def test_det02_must_detect(feature, request_, place):
    assert extractor.extract(request_)[feature] == 1


@pytest.mark.parametrize(
    "request_,place",
    [
        pytest.param(req, place, id=f"{place}|{ex}")
        for ex, where in MUST_NOT_DETECT
        for place, req in _placements(ex, where)
    ],
)
def test_det03_must_not_detect(request_, place):
    f = extractor.extract(request_)
    assert {k: f[k] for k in ATTACK_FEATURES} == dict.fromkeys(ATTACK_FEATURES, 0)


# ── DET-05 .. DET-08: superfície inspecionada ───────────────────────────────

def test_det05_query_and_body_equivalent():
    payload = "' OR 1=1--"
    in_body = extractor.extract(make_request(method="POST", body={"q": payload}))
    in_query = extractor.extract(make_request(query_params={"q": payload}))
    assert in_body["has_sqli"] == in_query["has_sqli"] == 1


@pytest.mark.parametrize(
    "value,feature",
    [("' OR '1'='1", "has_sqli"), ("<script>alert(1)</script>", "has_xss")],
)
def test_det06_header_values_inspected(value, feature):
    f = extractor.extract(make_request(headers={"Referer": value}))
    assert f[feature] == 1


@pytest.mark.parametrize(
    "request_,feature",
    [
        (make_request(method="POST", body={"' OR 1=1--": "x"}), "has_sqli"),
        (make_request(query_params={"<script>alert(1)</script>": "1"}), "has_xss"),
    ],
    ids=["body-key-sqli", "query-key-xss"],
)
def test_det07_keys_inspected(request_, feature):
    assert extractor.extract(request_)[feature] == 1


@pytest.mark.parametrize(
    "body,feature",
    [
        ({"a": {"b": {"c": {"d": "' OR '1'='1"}}}}, "has_sqli"),
        ({"items": [1, {"x": "<script>alert(1)</script>"}]}, "has_xss"),
        (["ok", ["../../etc/passwd"]], "has_path_traversal"),
    ],
    ids=["nested-dict", "array-of-dict", "nested-array"],
)
def test_det08_nested_body_inspected(body, feature):
    f = extractor.extract(make_request(method="POST", body=body))
    assert f[feature] == 1


# ── DET-09 / DET-10: tipos de body e body_length ────────────────────────────

@pytest.mark.parametrize("body", ["texto livre", ["a", 1], 42, 3.5, True, None])
def test_det09_extractor_accepts_any_json_body(body):
    f = extractor.extract(make_request(method="POST", body=body))
    assert set(f) == set(FEATURE_ORDER)


@pytest.mark.parametrize("body", ["texto livre", ["a", 1], 42, True, None])
def test_det09_api_accepts_any_json_body(client, body):
    payload = make_request(method="POST", path="/x", body=body)
    resp = client.post("/v1/analyze", json=payload)
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize(
    "body,expected",
    [({"a": "b"}, 9), ("abc", 3), (None, 0), ("x" * 60000, 50000)],
    ids=["dict", "str", "null", "cap"],
)
def test_det10_body_length(body, expected):
    f = extractor.extract(make_request(method="POST", body=body))
    assert f["body_length"] == expected


# ── DET-11: fallback do User-Agent ──────────────────────────────────────────

def test_det11_ua_falls_back_to_header():
    f = extractor.extract(make_request(user_agent=None, headers={"User-Agent": BROWSER_UA}))
    assert f["ua_is_empty"] == 0


def test_det11_scanner_detected_from_header():
    f = extractor.extract(make_request(user_agent=None, headers={"user-agent": "sqlmap/1.7"}))
    assert f["ua_is_scanner"] == 1


# ── DET-12 .. DET-14: robustez ──────────────────────────────────────────────

def test_det12_invalid_percent_encoding_is_literal():
    f = extractor.extract(make_request(path="/a%zz%", query_params={"q": "%"}))
    assert f["has_sqli"] == 0
    f = extractor.extract(make_request(query_params={"q": "%zz' OR '1'='1"}))
    assert f["has_sqli"] == 1


@pytest.mark.parametrize("unit", ["a", "'", "<", "a' ", "%2", "../"])
def test_det13_large_body_is_linear(unit):
    body = {"q": unit * (200_000 // len(unit))}
    start = time.perf_counter()
    extractor.extract(make_request(method="POST", body=body))
    assert time.perf_counter() - start < 1.0


def test_det14_deeply_nested_body():
    body: dict = {"leaf": "' OR '1'='1"}
    for _ in range(100):
        body = {"n": body}
    f = extractor.extract(make_request(method="POST", body=body))
    assert f["has_sqli"] == 1
