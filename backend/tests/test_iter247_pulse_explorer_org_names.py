"""Iter 247 — Pulse data explorer: organisation names instead of raw ids.

`GET /api/master-admin/pulse-explorer/collections/{name}` now enriches
every doc carrying an `organization_id` with `organization_name`, and
the frontend renders the name in an "organisation" column (raw uuid
stays in the hover tooltip).
"""

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

PULSE_ADMIN = ("pulse.admin.test@pulsefitness.com", "PulseAdmin123!")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"{email}: {r.text}"
    return s


def test_pulse_explorer_docs_carry_organization_name():
    s = _login(*PULSE_ADMIN)
    # find a collection with rows that have an org link
    r = s.get(f"{BASE_URL}/api/master-admin/pulse-explorer/collections", timeout=30)
    assert r.status_code == 200, r.text
    candidates = [c["name"] for c in r.json()["collections"]
                  if c["count"] > 0 and c["name"] != "organizations"]
    assert candidates, "need at least one populated org-linked collection"

    checked = 0
    for name in candidates[:3]:
        r = s.get(f"{BASE_URL}/api/master-admin/pulse-explorer/collections/{name}",
                  params={"page": 1, "page_size": 25}, timeout=30)
        assert r.status_code == 200, r.text
        for d in r.json()["docs"]:
            if d.get("organization_id"):
                assert "organization_name" in d, (
                    f"{name} doc with organization_id missing organization_name: "
                    f"{list(d.keys())}"
                )
                assert isinstance(d["organization_name"], str)
                checked += 1
    assert checked > 0, "no org-linked docs found to verify enrichment"


def test_pulse_explorer_org_name_matches_real_org():
    s = _login(*PULSE_ADMIN)
    r = s.get(f"{BASE_URL}/api/master-admin/pulse-explorer/collections/sites",
              params={"page": 1, "page_size": 25}, timeout=30)
    assert r.status_code == 200, r.text
    docs = [d for d in r.json()["docs"] if d.get("organization_id") and d.get("organization_name")]
    if not docs:  # fall back to equipment if no sites in scope
        r = s.get(f"{BASE_URL}/api/master-admin/pulse-explorer/collections/equipment",
                  params={"page": 1, "page_size": 25}, timeout=30)
        docs = [d for d in r.json()["docs"] if d.get("organization_id") and d.get("organization_name")]
    assert docs, "expected at least one enriched doc in sites/equipment"
    sample = docs[0]
    # the name must belong to the org with that id (organisations collection)
    r = s.get(f"{BASE_URL}/api/master-admin/pulse-explorer/collections/organizations",
              params={"q": sample["organization_id"], "page_size": 5}, timeout=30)
    orgs = r.json()["docs"]
    match = [o for o in orgs if o.get("id") == sample["organization_id"]]
    assert match and match[0].get("name") == sample["organization_name"]


def test_frontend_renders_org_names():
    src = open("/app/frontend/src/pages/MasterAdmin/PulseDbExplorerPanel.js", encoding="utf-8").read()
    assert "organization_name" in src
    assert "'organisation'" in src, "organization_id column must be re-labelled"
    assert "cellTitle" in src, "raw id must stay available in the tooltip"
