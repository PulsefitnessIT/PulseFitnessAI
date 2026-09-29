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
        self.contract_ping_status = 404  # §26 — plugin unavailable by default

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
        # ── Proven v1 case-relationship chain (§11-16) ──
        if "/SiconService/Case/" in path and path.endswith("/Equipment"):
            return httpx.Response(200, json={"records": [{"siconEquipmentId": 1}]})
        if "/SiconService/Case/" in path and path.endswith("/Appointment"):
            return httpx.Response(200, json={"records": [{"siconAppointmentId": 77}]})
        if "/SiconService/Case/" in path and "/TrackingNote" in path:
            return httpx.Response(200, json={"records": [{"siconTrackingNoteId": 5}]})
        if "/SiconService/Appointment/" in path and path.endswith("/Resource"):
            return httpx.Response(200, json={"records": [{"siconResourceId": 3}]})
        if "/SiconService/Appointment/" in path and path.endswith("/TimeBooking"):
            return httpx.Response(200, json={"records": [{"siconTimeBookingId": 8}]})
        if "/SiconService/Appointment/" in path:
            aid = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"siconAppointmentId": int(aid)})
        # ── Contract Management plugin probe (§26) ──
        if path.endswith("/SiconContract/Ping"):
            return httpx.Response(self.contract_ping_status,
                                  json={"ok": self.contract_ping_status == 200})
        if path.endswith("/SiconContract/Contract"):
            return httpx.Response(200, json={"records": [{"siconContractId": 1}]})
        if "/SiconContract/Contract/" in path:
            return httpx.Response(200, json={"siconContractId": int(path.rsplit("/", 1)[-1])})
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


# ── §11-16 proven v1 case-relationship read routes ────────────────
def test_case_relationship_routes_are_v1():
    rec = _Recorder()
    c = _client()
    with mock_sicon(rec):
        drive_async(c.svc_get_case_equipment(123))
        drive_async(c.svc_get_case_appointments(123))
        drive_async(c.svc_get_case_tracking_notes(123))
        drive_async(c.svc_get_tracking_note_one(123, 9))
        drive_async(c.svc_get_appointment_one(55))
        drive_async(c.svc_get_appointment_resources(55))
        drive_async(c.svc_get_appointment_timebookings(55))
    paths = [r.url.path for r in rec.requests if "/SiconService/" in r.url.path]
    assert "/api/v1/SiconService/Case/123/Equipment" in paths
    assert "/api/v1/SiconService/Case/123/Appointment" in paths
    assert "/api/v1/SiconService/Case/123/TrackingNote" in paths
    assert "/api/v1/SiconService/Case/123/TrackingNote/9" in paths
    assert "/api/v1/SiconService/Appointment/55" in paths
    assert "/api/v1/SiconService/Appointment/55/Resource" in paths
    assert "/api/v1/SiconService/Appointment/55/TimeBooking" in paths
    # Every relationship read is company-scoped and never a legacy /api/Service/* route
    rel = [r for r in rec.requests if "/SiconService/Case/" in r.url.path
           or "/SiconService/Appointment/" in r.url.path]
    assert all(b"companyId=2" in r.url.query for r in rel)
    assert not any(r.url.path.startswith("/api/Service") for r in rec.requests)


# ── §26 Contract Management plugin capability probe ───────────────
def test_contract_probe_unavailable_on_404():
    rec = _Recorder()
    rec.contract_ping_status = 404
    with mock_sicon(rec):
        avail = drive_async(_client().svc_contract_available())
    assert avail is False
    ping = [r for r in rec.requests if r.url.path.endswith("/SiconContract/Ping")]
    assert ping, "contract ping was not attempted"


def test_contract_probe_available_and_reads_on_200():
    rec = _Recorder()
    rec.contract_ping_status = 200
    with mock_sicon(rec):
        assert drive_async(_client().svc_contract_available()) is True
        many = drive_async(_client().svc_get_contracts())
        one = drive_async(_client().svc_get_contract_one(1))
    assert many["records"][0]["siconContractId"] == 1
    assert one["siconContractId"] == 1


def test_contract_uses_contract_base_url():
    rec = _Recorder()
    rec.contract_ping_status = 200
    c = SiconClient("https://sicon.test", "svc", "pw", company_id=2,
                    allow_writes=False, page_size=50,
                    contract_base_url="https://contract.test")
    with mock_sicon(rec):
        drive_async(c.svc_contract_available())
    ping = [r for r in rec.requests if r.url.path.endswith("/SiconContract/Ping")][0]
    assert str(ping.url).startswith("https://contract.test"), str(ping.url)


def test_contract_reads_are_not_write_guarded():
    # Contract GETs are read-only and must work with writes disabled.
    rec = _Recorder()
    rec.contract_ping_status = 200
    with mock_sicon(rec):
        out = drive_async(_client(allow_writes=False).svc_get_contracts())
    assert out["records"][0]["siconContractId"] == 1

