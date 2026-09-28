"""
Offline acceptance tests for the Sicon READ-side (spec §29/§30).

No live Sicon server is reachable from CI/preview (it lives at localhost:51080
on the customer network), so these drive the central SiconClient through an
httpx MockTransport and assert the EXACT wire behaviour — most importantly the
`query=$skip=0%26$max=50` pagination encoding, idempotent paging, GetOne paths,
reference lookups, token re-auth, and that SICON_ALLOW_WRITES=false blocks every
write.
"""
import contextlib
import httpx
import pytest

from tests.conftest import drive_async
import utils.sicon_client as sc
from utils.sicon_client import SiconClient, SiconAPIError


# ── MockTransport plumbing ────────────────────────────────────────
class _Recorder:
    def __init__(self):
        self.requests = []
        self.auth_count = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/authentication/authenticate"):
            self.auth_count += 1
            return httpx.Response(200, json={"accessToken": f"TOK{self.auth_count}"})
        if path.endswith("/SiconService/Equipment"):
            skip = request.url.params.get("query", "")
            if "$skip=0" in skip:
                return httpx.Response(200, json={
                    "currentPage": 1, "previousPage": None, "nextPage": 2,
                    "totalPages": 2, "totalRecords": 3, "pageSize": 2,
                    "records": [{"siconEquipmentId": 1}, {"siconEquipmentId": 2}],
                })
            return httpx.Response(200, json={
                "currentPage": 2, "previousPage": 1, "nextPage": None,
                "totalPages": 2, "totalRecords": 3, "pageSize": 2,
                "records": [{"siconEquipmentId": 3}],
            })
        if "/SiconService/Equipment/" in path:
            eid = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"siconEquipmentId": int(eid)})
        if path.endswith("/SiconService/CaseSearch"):
            return httpx.Response(200, json={
                "currentPage": 1, "nextPage": None, "records": [{"siSMCaseId": 900}]})
        if "/SiconService/CaseSearch/" in path:
            cid = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"siSMCaseId": int(cid)})
        if path.endswith("/SiconService/CaseType"):
            return httpx.Response(200, json={"records": [{"siSMCaseTypeId": 1, "name": "Repair"}]})
        if path.endswith("/SiconService/Priority"):
            return httpx.Response(200, json={"records": [{"siSMPriorityId": 1, "name": "High"}]})
        if path.endswith("/SiconService/TrackingStatus"):
            return httpx.Response(200, json={"records": [{"id": 1, "name": "Open"}]})
        return httpx.Response(404, json={"error": "unexpected", "path": path})


@contextlib.contextmanager
def mock_sicon(recorder: _Recorder, expiring_token: bool = False):
    """Patch httpx.AsyncClient used inside sicon_client to route through the
    recorder's MockTransport. If expiring_token, the FIRST Equipment GET with
    TOK1 returns 401 to exercise the auto re-auth path."""
    real = httpx.AsyncClient
    state = {"expired_once": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if (expiring_token and request.url.path.endswith("/SiconService/Equipment")
                and request.headers.get("Authorization") == "Bearer TOK1"
                and not state["expired_once"]):
            state["expired_once"] = True
            recorder.requests.append(request)
            return httpx.Response(401, json={"error": "token expired"})
        return recorder.handler(request)

    def factory(*args, **kwargs):
        kwargs.pop("verify", None)
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    sc.httpx.AsyncClient = factory
    try:
        yield
    finally:
        sc.httpx.AsyncClient = real


def _client(allow_writes=False, page_size=50):
    return SiconClient("https://sicon.test", "svc", "pw", company_id=2,
                       allow_writes=allow_writes, page_size=page_size)


# ── §30 pagination encoding ───────────────────────────────────────
def test_page1_wire_encoding_exact():
    rec = _Recorder()
    with mock_sicon(rec):
        drive_async(_client().svc_get_equipment_page(0, 50))
    eq = [r for r in rec.requests if r.url.path.endswith("/SiconService/Equipment")][0]
    raw = eq.url.query  # bytes, exactly as sent
    assert b"query=$skip=0%26$max=50" in raw, raw
    assert b"companyId=2" in raw
    assert b"%2526" not in raw            # the %26 must NOT be double-encoded
    # Parsed: exactly two params, and the inner %26 decodes back to a single &
    assert eq.url.params.get("query") == "$skip=0&$max=50"
    assert set(eq.url.params.keys()) == {"companyId", "query"}
    assert "$max" not in dict(eq.url.params)  # $max never leaked as its own param


def test_page2_skip_calculation():
    rec = _Recorder()
    with mock_sicon(rec):
        drive_async(_client().svc_get_equipment_page(50, 50))
    eq = [r for r in rec.requests if r.url.path.endswith("/SiconService/Equipment")][0]
    assert b"query=$skip=50%26$max=50" in eq.url.query


def test_build_page_query_formula():
    # skip = (page-1)*size
    assert SiconClient.build_page_query(0, 50) == "query=$skip=0%26$max=50"
    assert SiconClient.build_page_query(100, 50) == "query=$skip=100%26$max=50"


def test_paginate_advances_until_nextpage_null_no_dupes():
    rec = _Recorder()
    pages = []
    with mock_sicon(rec):
        async def run():
            async for meta, records in _client(page_size=2).svc_paginate("equipment"):
                pages.append((meta.get("currentPage"), [r["siconEquipmentId"] for r in records]))
        drive_async(run())
    assert pages == [(1, [1, 2]), (2, [3])]           # stops at nextPage=None
    first_ids = {i for _, ids in pages for i in ids}
    assert first_ids == {1, 2, 3}                     # no duplicate page retrieval


# ── GetOne + reference data ───────────────────────────────────────
def test_equipment_getone_path():
    rec = _Recorder()
    with mock_sicon(rec):
        out = drive_async(_client().svc_get_equipment_one(123))
    assert out["siconEquipmentId"] == 123
    assert rec.requests[-1].url.path.endswith("/SiconService/Equipment/123")


def test_casesearch_getone_by_sismcaseid():
    rec = _Recorder()
    with mock_sicon(rec):
        out = drive_async(_client().svc_get_casesearch_one(555))
    assert out["siSMCaseId"] == 555
    assert rec.requests[-1].url.path.endswith("/SiconService/CaseSearch/555")


def test_reference_lookups():
    rec = _Recorder()
    with mock_sicon(rec):
        ct = drive_async(_client().svc_get_case_types())
        pr = drive_async(_client().svc_get_priorities())
        ts = drive_async(_client().svc_get_tracking_statuses())
    assert ct["records"][0]["name"] == "Repair"
    assert pr["records"][0]["name"] == "High"
    assert ts["records"][0]["name"] == "Open"


# ── §3 token re-authentication ────────────────────────────────────
def test_reauth_on_token_expiry():
    rec = _Recorder()
    with mock_sicon(rec, expiring_token=True):
        out = drive_async(_client().svc_get_equipment_page(0, 50))
    assert out["currentPage"] == 1                    # succeeded after re-auth
    assert rec.auth_count == 2                         # authed twice (initial + refresh)
    # final successful Equipment GET carried the refreshed token
    ok = [r for r in rec.requests if r.url.path.endswith("/SiconService/Equipment")
          and r.headers.get("Authorization") == "Bearer TOK2"]
    assert ok, "retry did not use refreshed token"


# ── §18/§35 writes disabled ───────────────────────────────────────
def test_writes_blocked_when_allow_writes_false():
    rec = _Recorder()
    with mock_sicon(rec), pytest.raises(SiconAPIError) as ei:
        drive_async(_client(allow_writes=False).svc_create_case({"x": 1}))
    assert ei.value.http_status == 403
    # No HTTP request should even be attempted for a blocked write
    assert rec.requests == []


def test_legacy_writes_also_blocked():
    rec = _Recorder()
    with mock_sicon(rec):
        for coro in (
            _client(allow_writes=False).svc_update_equipment(1, {}),
            _client(allow_writes=False).svc_create_appointment({}),
            _client(allow_writes=False).create_case({}),
        ):
            with pytest.raises(SiconAPIError):
                drive_async(coro)
    assert rec.requests == []


def test_writes_allowed_when_flag_true():
    rec = _Recorder()
    # With the flag on, the guard must NOT pre-empt the write — it should
    # reach the transport. (The mock accepts it; the point is it was sent.)
    with mock_sicon(rec):
        drive_async(_client(allow_writes=True).svc_create_equipment({"x": 1}))
    sent = [r for r in rec.requests
            if r.method == "POST" and r.url.path.endswith("/SiconService/Equipment")]
    assert sent, "write was not sent even though allow_writes=True"
