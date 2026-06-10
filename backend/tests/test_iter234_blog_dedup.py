"""Iter 234 — blog duplicate prevention (production shipped a rehash).

Production published two near-identical posts:
  * "Gym treadmill downtime impact on retention: the numbers you need"
  * "Gym treadmill downtime impact on retention: the numbers operators miss"

Root cause: the composite uniqueness score weights the article OPENER at
0.6, so an LLM-rephrased opener dragged the pair under the 0.6 gate even
though the titles are ~67 % identical.

Fixes under test:
1. ``check_article_uniqueness`` hard TITLE gate — near-duplicate titles
   fail regardless of the opener.
2. ``GET /articles/duplicates`` scores ``max(title_sim, composite)`` so
   historical rehashes surface in the admin scan.
3. Autopilot keyword pre-flight — queued keywords colliding with
   already-published topics are skipped (status='skipped_duplicate').
"""

from tests.shared_loop import run_async as drive_async

from utils.seo_article_freshness import check_article_uniqueness, keyword_similarity

PROD_TITLE_A = "Gym treadmill downtime impact on retention: the numbers you need"
PROD_TITLE_B = "Gym treadmill downtime impact on retention: the numbers operators miss"


class _FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)

    def __aiter__(self):
        self._it = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


class _FakeArticles:
    def __init__(self, rows):
        self._rows = rows

    def find(self, _filter, _projection=None):
        return _FakeCursor([r for r in self._rows if r.get("status") == "published"])


class _FakeDB:
    def __init__(self, articles):
        self.seo_articles = _FakeArticles(articles)


def test_production_pair_title_similarity_is_high():
    assert keyword_similarity(PROD_TITLE_A, PROD_TITLE_B) >= 0.6


def test_title_gate_blocks_the_production_pair():
    """The exact pair that shipped twice must now FAIL uniqueness even
    with a completely rephrased opener (composite alone would pass)."""
    db = _FakeDB(articles=[
        {"id": "a1", "title": PROD_TITLE_A, "slug": "downtime-numbers",
         "body_md": "# T\n\nA stalled belt at peak hour quietly erodes trust before "
                    "anyone files a complaint, and the cancellation data proves it.",
         "status": "published"},
    ])
    result = drive_async(check_article_uniqueness(
        db,
        title=PROD_TITLE_B,
        # Deliberately different opener — the old composite-only gate let
        # this through.
        body_md="# T\n\nOperators rarely connect a quiet cancellations uptick to "
                "last month's out-of-order cardio row, yet the correlation is stark.",
        threshold=0.6,
    ))
    assert not result["ok"], f"title-duplicate pair must be blocked: {result}"
    assert result["title_duplicate"] is True
    assert result["title_similarity"] >= 0.6
    assert result["best_match"]["id"] == "a1"


def test_distinct_articles_still_pass_title_gate():
    db = _FakeDB(articles=[
        {"id": "a1", "title": "Member retention playbook for boutique studios",
         "body_md": "# T\n\nMembers churn fast in the first 90 days.",
         "status": "published"},
    ])
    result = drive_async(check_article_uniqueness(
        db,
        title="PPM scheduling for multi-site gyms",
        body_md="# T\n\nA spreadsheet collapses by your fourth gym opening.",
        threshold=0.6,
    ))
    assert result["ok"], result
    assert result["title_duplicate"] is False


def test_exclude_id_still_respected_with_title_gate():
    db = _FakeDB(articles=[
        {"id": "self", "title": PROD_TITLE_A,
         "body_md": "# T\n\nSame opener text right here.",
         "status": "published"},
    ])
    result = drive_async(check_article_uniqueness(
        db, title=PROD_TITLE_A,
        body_md="# T\n\nSame opener text right here.",
        exclude_id="self", threshold=0.6,
    ))
    assert result["ok"]


def test_duplicates_scan_uses_title_similarity():
    """Source pin — the admin duplicate scan must score
    max(title_sim, composite) or title-only rehashes stay invisible."""
    src = open("/app/backend/routes/marketing/seo_autopilot.py", encoding="utf-8").read()
    block = src.split('@router.get("/articles/duplicates")')[1].split("@router.")[0]
    assert "keyword_similarity(a.get(\"title\", \"\"), b.get(\"title\", \"\"))" in block
    assert "max(composite, round(title_sim, 3))" in block
    assert '"title_similarity"' in block


def test_duplicates_endpoint_not_shadowed_by_article_id_route():
    """LIVE — /articles/duplicates was registered AFTER
    /articles/{article_id}, so FastAPI matched "duplicates" as an id and
    the scan ALWAYS 404'd ("Article not found"). The admin's historical
    duplicate scans silently never worked — this guards the route order."""
    import requests
    from tests.conftest import _test_backend_url
    base = _test_backend_url()
    s = requests.Session()
    r = s.post(f"{base}/api/auth/login",
               json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
               timeout=20)
    assert r.status_code == 200, r.text
    r = s.get(f"{base}/api/marketing/seo/articles/duplicates?threshold=0.55", timeout=60)
    assert r.status_code == 200, f"duplicates scan must not 404: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert "pairs" in body, body


def test_autopilot_preflight_skips_published_collisions():
    """Source pin — the autopilot walks the queue and retires keywords
    colliding with already-published topics instead of generating a
    rehash."""
    src = open("/app/backend/routes/marketing/seo_autopilot.py", encoding="utf-8").read()
    block = src.split('@router.post("/autopilot/run")')[1].split("@router.")[0]
    assert "find_similar_keywords(db, candidate[\"term\"], threshold=0.7)" in block
    assert '"skipped_duplicate"' in block
    assert '"near_duplicate_of"' in block
    # The generation gate itself must also pass the hard title gate result.
    assert "check_article_uniqueness" in src
