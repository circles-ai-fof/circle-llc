"""
Tests for M12.2 (reviews) + M12.3 (job_boards) — pain sources.

Stubs urllib.request.urlopen so no real network calls happen.

Reviews pin-down:
  - target parser accepts bare id, country:id, full apps.apple.com URL
  - only 1-2 star reviews surface as signals (4-5 star skipped — happy
    customers don't reveal market gaps)
  - prefixed title shows the star rating
  - empty/garbage feed handled gracefully
  - dispatcher routes "reviews" → fetch_reviews

Job boards pin-down:
  - listings with automation keywords surface
  - generic engineering hire (no automation language) is dropped
  - salary range included in title when present
  - empty target hits the unfiltered feed
  - dispatcher routes "job_boards" → fetch_job_boards
"""
import json
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

def _stub_urlopen(json_body: dict | list):
    """Returns a fake urlopen that yields the given JSON body."""
    from io import BytesIO

    class _Resp:
        def __init__(self, body):
            self._body = body.encode("utf-8")
            self._reader = BytesIO(self._body)

        def read(self, n=-1):
            return self._reader.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    raw = json.dumps(json_body)

    def _open(req, timeout=None):
        return _Resp(raw)

    return _open


# ---------------------------------------------------------------------------
# Target parser — reviews
# ---------------------------------------------------------------------------

def test_parse_appstore_target_bare_id():
    from orchestrator.core.source_fetcher import _parse_appstore_target
    assert _parse_appstore_target("1635060198") == ("us", "1635060198")


def test_parse_appstore_target_country_id():
    from orchestrator.core.source_fetcher import _parse_appstore_target
    assert _parse_appstore_target("mx:1635060198") == ("mx", "1635060198")


def test_parse_appstore_target_full_url():
    from orchestrator.core.source_fetcher import _parse_appstore_target
    url = "https://apps.apple.com/ec/app/habitkit/id1635060198"
    assert _parse_appstore_target(url) == ("ec", "1635060198")


def test_parse_appstore_target_empty_returns_empty_app_id():
    from orchestrator.core.source_fetcher import _parse_appstore_target
    assert _parse_appstore_target("") == ("us", "")
    assert _parse_appstore_target("garbage") == ("us", "")


# ---------------------------------------------------------------------------
# Reviews fetch
# ---------------------------------------------------------------------------

# A realistic Apple JSON RSS shape: first entry = app metadata, rest = reviews
_REVIEW_FEED = {
    "feed": {
        "entry": [
            # app metadata (skipped)
            {
                "id": {"label": "1635060198"},
                "im:name": {"label": "HabitKit"},
                "title": {"label": "HabitKit"},
            },
            # 1-star → should surface
            {
                "id": {"label": "https://reviews.apple.com/r/1"},
                "title": {"label": "Crashes when I add 3 habits"},
                "content": {"label": "App constantly crashes! I wish there was a fix."},
                "im:rating": {"label": "1"},
                "author": {"name": {"label": "frustrated_user"}},
                "updated": {"label": "2026-05-01T10:00:00Z"},
            },
            # 2-star → should surface
            {
                "id": {"label": "https://reviews.apple.com/r/2"},
                "title": {"label": "Missing iCloud sync"},
                "content": {"label": "Why is there no sync across devices?"},
                "im:rating": {"label": "2"},
                "author": {"name": {"label": "casual_user"}},
                "updated": {"label": "2026-05-02T11:00:00Z"},
            },
            # 5-star → should be SKIPPED (happy customer, no signal)
            {
                "id": {"label": "https://reviews.apple.com/r/3"},
                "title": {"label": "Best habit app ever"},
                "content": {"label": "Love it."},
                "im:rating": {"label": "5"},
                "author": {"name": {"label": "fan"}},
                "updated": {"label": "2026-05-03T12:00:00Z"},
            },
        ]
    }
}


def test_fetch_reviews_extracts_only_low_stars():
    from orchestrator.core.source_fetcher import fetch_reviews
    with patch("urllib.request.urlopen", _stub_urlopen(_REVIEW_FEED)):
        items = fetch_reviews("1635060198")
    assert len(items) == 2  # 1-star + 2-star only
    titles = [i.title for i in items]
    assert any("★1" in t for t in titles)
    assert any("★2" in t for t in titles)
    assert not any("★5" in t for t in titles)


def test_fetch_reviews_source_kind_tagged():
    from orchestrator.core.source_fetcher import fetch_reviews
    with patch("urllib.request.urlopen", _stub_urlopen(_REVIEW_FEED)):
        items = fetch_reviews("us:1635060198")
    assert all(i.source_kind == "reviews" for i in items)


def test_fetch_reviews_empty_target_returns_empty():
    from orchestrator.core.source_fetcher import fetch_reviews
    assert fetch_reviews("") == []


def test_fetch_reviews_handles_empty_feed():
    from orchestrator.core.source_fetcher import fetch_reviews
    with patch("urllib.request.urlopen", _stub_urlopen({"feed": {"entry": []}})):
        assert fetch_reviews("1635060198") == []


def test_fetch_reviews_handles_network_failure():
    import urllib.error
    from orchestrator.core.source_fetcher import fetch_reviews

    def _boom(req, timeout=None):
        raise urllib.error.URLError("no network")

    with patch("urllib.request.urlopen", side_effect=_boom):
        assert fetch_reviews("1635060198") == []


def test_fetch_by_kind_reviews_dispatches():
    """SourcesStore.add(kind='reviews') must hit fetch_reviews."""
    from orchestrator.core import source_fetcher
    with patch("urllib.request.urlopen", _stub_urlopen(_REVIEW_FEED)):
        items = source_fetcher.fetch_by_kind("reviews", target="1635060198")
    assert len(items) == 2
    assert all(i.source_kind == "reviews" for i in items)


# ---------------------------------------------------------------------------
# Job boards fetch
# ---------------------------------------------------------------------------

# RemoteOK API shape: list of dicts. First entry is "legal" metadata.
_JOB_FEED = [
    {"legal": "by using this api you agree to the terms"},
    # automation gig → KEEP
    {
        "position": "Build an internal reporting tool with n8n",
        "company": "Acme Co",
        "description": (
            "We want to automate our weekly KPI reports. Build a workflow "
            "that scrapes our HubSpot and posts to Slack."
        ),
        "url": "https://remoteok.com/job/1",
        "apply_url": "https://acme.com/apply",
        "salary_min": 4000, "salary_max": 6000,
        "epoch": 1780000000,
    },
    # generic senior dev role → DROP (no automation language)
    {
        "position": "Senior Backend Engineer",
        "company": "BigCorp",
        "description": "Looking for an experienced backend engineer to scale our platform.",
        "url": "https://remoteok.com/job/2",
        "salary_min": 8000, "salary_max": 12000,
        "epoch": 1780000100,
    },
    # webhook integration → KEEP
    {
        "position": "Integration engineer",
        "company": "Beta SaaS",
        "description": "Set up webhook integrations between Stripe and our internal CRM.",
        "url": "https://remoteok.com/job/3",
        "salary_min": 0, "salary_max": 0,
        "epoch": 1780000200,
    },
]


def test_fetch_job_boards_filters_to_automation_gigs():
    from orchestrator.core.source_fetcher import fetch_job_boards
    with patch("urllib.request.urlopen", _stub_urlopen(_JOB_FEED)):
        items = fetch_job_boards("")
    # 2 of 3 listings have automation language → 2 kept
    assert len(items) == 2
    titles = " ".join(i.title for i in items)
    assert "Acme Co" in titles
    assert "Beta SaaS" in titles
    # Generic senior backend hire was DROPPED
    assert "BigCorp" not in titles


def test_fetch_job_boards_includes_salary_in_title_when_present():
    from orchestrator.core.source_fetcher import fetch_job_boards
    with patch("urllib.request.urlopen", _stub_urlopen(_JOB_FEED)):
        items = fetch_job_boards("")
    acme_item = next(i for i in items if "Acme" in i.title)
    assert "$4000" in acme_item.title
    assert "$6000" in acme_item.title


def test_fetch_job_boards_no_salary_omits_range():
    """When salary_min/max are 0, no salary bracket in title."""
    from orchestrator.core.source_fetcher import fetch_job_boards
    with patch("urllib.request.urlopen", _stub_urlopen(_JOB_FEED)):
        items = fetch_job_boards("")
    beta = next(i for i in items if "Beta" in i.title)
    assert "$0" not in beta.title


def test_fetch_job_boards_source_kind_tagged():
    from orchestrator.core.source_fetcher import fetch_job_boards
    with patch("urllib.request.urlopen", _stub_urlopen(_JOB_FEED)):
        items = fetch_job_boards("")
    assert all(i.source_kind == "job_boards" for i in items)


def test_fetch_job_boards_handles_garbage_response():
    from orchestrator.core.source_fetcher import fetch_job_boards
    # Non-list response → return empty
    with patch("urllib.request.urlopen", _stub_urlopen({"error": "rate limited"})):
        assert fetch_job_boards("") == []


def test_fetch_by_kind_job_boards_dispatches():
    from orchestrator.core import source_fetcher
    with patch("urllib.request.urlopen", _stub_urlopen(_JOB_FEED)):
        items = source_fetcher.fetch_by_kind("job_boards", target="")
    assert len(items) == 2
