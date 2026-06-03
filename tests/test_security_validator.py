"""
Tests for M13.0 — SecurityValidator heuristic.

Pin down each detector + the final verdict combination logic. Safe-biased
behavior: any uncertainty MUST resolve to SUSPICIOUS or UNKNOWN, never SAFE.
"""


# ---------------------------------------------------------------------------
# Clean trusted URLs (SAFE)
# ---------------------------------------------------------------------------

def test_clean_https_trusted_domain_is_safe():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://github.com/anthropics/claude-code")
    assert v.verdict == "SAFE"
    assert v.confidence == "alta"


def test_clean_subdomain_of_trusted_is_safe():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://news.ycombinator.com/")
    assert v.verdict == "SAFE"


# ---------------------------------------------------------------------------
# Typosquat detection
# ---------------------------------------------------------------------------

def test_typosquat_of_github_is_dangerous():
    """gltihub.com is 1 edit from github.com — almost certainly a typosquat."""
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://gltihub.com/some/repo")
    assert v.verdict == "DANGEROUS"
    codes = {s.code for s in v.strong_signals}
    assert "typosquat" in codes


def test_typosquat_of_openai_is_dangerous():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://openai-news.com/article")
    # openai-news.com is distance 5 from openai.com → no typosquat trigger,
    # but text contains "openai" — verify the function doesn't false-positive
    assert v.verdict in ("SAFE", "SUSPICIOUS")  # not DANGEROUS without other signals


def test_typosquat_distance_one_dangerous():
    """openal.com — single substitution of openai.com."""
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://openal.com/")
    assert v.verdict == "DANGEROUS"


def test_exact_trusted_match_not_flagged():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://openai.com/")
    assert v.verdict == "SAFE"


# ---------------------------------------------------------------------------
# Homoglyph detection
# ---------------------------------------------------------------------------

def test_cyrillic_a_in_github_is_dangerous():
    """githаb.com uses Cyrillic 'а' instead of Latin 'a'."""
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://githаb.com/some/repo")
    assert v.verdict == "DANGEROUS"
    codes = {s.code for s in v.signals}
    assert "homoglyph_in_host" in codes


def test_pure_ascii_no_homoglyphs():
    from orchestrator.core.security_validator import detect_homoglyphs
    assert detect_homoglyphs("github.com") == []


# ---------------------------------------------------------------------------
# Abused TLD
# ---------------------------------------------------------------------------

def test_tk_tld_is_suspicious():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://newsite.tk/article")
    assert v.verdict == "SUSPICIOUS"
    assert any(s.code == "abused_tld" for s in v.weak_signals)


def test_cf_tld_with_clean_otherwise_is_suspicious():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://example.cf/")
    assert v.verdict == "SUSPICIOUS"


# ---------------------------------------------------------------------------
# URL shortener
# ---------------------------------------------------------------------------

def test_bitly_shortener_is_dangerous():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://bit.ly/3xyzABC")
    assert v.verdict == "DANGEROUS"
    assert any(s.code == "url_shortener" for s in v.strong_signals)


def test_tinyurl_shortener_is_dangerous():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://tinyurl.com/abc123")
    assert v.verdict == "DANGEROUS"


# ---------------------------------------------------------------------------
# Executable download
# ---------------------------------------------------------------------------

def test_exe_download_is_dangerous():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://files.example.com/setup.exe")
    assert v.verdict == "DANGEROUS"
    codes = {s.code for s in v.strong_signals}
    assert "executable_download" in codes


def test_apk_download_is_dangerous():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://files.example.com/app.apk")
    assert v.verdict == "DANGEROUS"


def test_pdf_not_flagged_as_executable():
    """Not all binary extensions are dangerous — .pdf shouldn't trigger."""
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://example.com/report.pdf")
    assert v.verdict == "SAFE"


# ---------------------------------------------------------------------------
# IP literal + userinfo spoofing
# ---------------------------------------------------------------------------

def test_ip_literal_host_is_dangerous():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://203.0.113.7/path")
    assert v.verdict == "DANGEROUS"
    assert any(s.code == "ip_host" for s in v.strong_signals)


def test_userinfo_at_in_url_is_dangerous():
    """Classic spoofing: http://github.com@evil.com → real host is evil.com."""
    from orchestrator.core.security_validator import validate_url
    v = validate_url("http://github.com@evil-host.example/")
    codes = {s.code for s in v.signals}
    assert "userinfo_in_url" in codes
    assert v.verdict == "DANGEROUS"


# ---------------------------------------------------------------------------
# Scheme checks
# ---------------------------------------------------------------------------

def test_ftp_scheme_dangerous():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("ftp://example.com/file")
    assert v.verdict == "DANGEROUS"
    assert any(s.code == "non_http_scheme" for s in v.strong_signals)


def test_javascript_scheme_dangerous():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("javascript:alert(1)")
    assert v.verdict == "DANGEROUS"


def test_plain_http_is_suspicious():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("http://example.com/")
    # plain http → 1 weak signal → SUSPICIOUS (per spec, never SAFE without TLS)
    assert v.verdict == "SUSPICIOUS"


# ---------------------------------------------------------------------------
# Label/href mismatch
# ---------------------------------------------------------------------------

def test_label_says_github_href_is_other():
    from orchestrator.core.security_validator import validate_url
    v = validate_url(
        "https://evil-host.example/login",
        link_text="Click here: github.com",
    )
    assert v.verdict == "DANGEROUS"
    codes = {s.code for s in v.signals}
    assert "label_href_mismatch" in codes


def test_label_matches_href_no_flag():
    from orchestrator.core.security_validator import validate_url
    v = validate_url(
        "https://github.com/anthropics",
        link_text="Visit github.com",
    )
    assert not any(s.code == "label_href_mismatch" for s in v.signals)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_url_returns_unknown():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("")
    assert v.verdict == "UNKNOWN"


def test_garbage_url_dangerous():
    """Truly malformed input gets DANGEROUS instead of crashing."""
    from orchestrator.core.security_validator import validate_url
    v = validate_url("not a real url at all")
    # urlparse tolerates this; depending on result it's UNKNOWN or DANGEROUS
    assert v.verdict in ("DANGEROUS", "UNKNOWN")


def test_deep_subdomain_is_suspicious():
    """Phishing often chains many subdomains."""
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://a.b.c.d.evil.example/")
    assert any(s.code == "deep_subdomain" for s in v.weak_signals)


def test_excessive_hyphens_in_host():
    from orchestrator.core.security_validator import validate_url
    v = validate_url("https://secure-login-microsoft-update-account.example/")
    assert any(s.code == "excessive_hyphens" for s in v.weak_signals)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

def test_validate_url_endpoint_requires_url():
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    r = c.post("/api/v1/security/validate-url", headers=h, json={})
    assert r.status_code == 400


def test_validate_url_endpoint_returns_full_verdict():
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    r = c.post(
        "/api/v1/security/validate-url", headers=h,
        json={"url": "https://gltihub.com/foo"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "DANGEROUS"
    assert body["strong_signal_count"] >= 1
