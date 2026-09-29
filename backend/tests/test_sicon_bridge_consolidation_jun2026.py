"""Verifies the legacy Orbit4→Sicon bridge write path is consolidated onto the
single proven SiconClient + svc_sicon_outbox subsystem: the rogue direct-POST
(forward_to_sicon → {base}/api/service/cases, unguarded by SICON_ALLOW_WRITES)
is retired and no longer callable, and the bridge defers to the outbox.
"""
from tests.conftest import drive_async
from routes.integrations import forward_to_sicon, _forward_and_log_sicon


def test_forward_to_sicon_is_retired():
    async def run():
        try:
            await forward_to_sicon({"x": 1}, {"enabled": True, "base_url": "http://should-not-be-hit"})
            return "no-error"
        except RuntimeError as e:
            return str(e)
    msg = drive_async(run())
    assert "deprecated" in msg.lower()  # rogue path raises instead of POSTing


def test_bridge_defers_to_outbox_even_when_legacy_config_enabled():
    async def run():
        br = {"orbit4_ticket_id": "T-123"}
        # Even with the old enabled+base_url config that used to trigger a POST,
        # we must NOT forward — just record + defer to the proven subsystem.
        await _forward_and_log_sicon({"orbit4_ticket_id": "T-123"},
                                     {"enabled": True, "base_url": "http://legacy"}, br)
        return br
    br = drive_async(run())
    assert br["status"] == "queued_outbox"
    assert br.get("sicon_case_id") is None
    assert "error" not in br
