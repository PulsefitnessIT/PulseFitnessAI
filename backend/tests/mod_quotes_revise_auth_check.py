"""Ad-hoc check: revising a published group with a pending authorisation supersedes it (queue + customer can re-authorise). Cleans up its own group."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from mod_quotes_ui_setup import login, publish_flow, MQ, API, ROWS, CUSTOMER  # noqa: E402
from mod_quotes_test_helpers import run, delete_groups  # noqa: E402

m = login("modsales.manager@pulsedemo.test", "ModSales123!")
c = login("modsite.officer@army.mod.test", "ModSite123!", "mod")
g = m.post(f"{MQ}/groups", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A", "B"], "notes": "TEST_rev"}).json()
gid = g["id"]
try:
    publish_flow(m, gid, g["quotes"])
    qa = next(q["id"] for q in g["quotes"] if q["mod_quote_type"] == "A")
    print("auth1", c.post(f"{API}/mod/site/quotes/{qa}/authorise", data={"authorising_officer": "TEST_x", "authorisation_date": "2026-01-10"}).status_code)
    a1 = [a for a in m.get(f"{MQ}/authorisations").json()["items"] if a["group_id"] == gid]
    print("auths before revise", [(a["status"], a["quote_number"]) for a in a1])
    r = m.put(f"{MQ}/groups/{gid}", json={"customer": CUSTOMER, "rows": ROWS, "options": ["A", "B"]})
    print("revise", r.status_code)
    a2 = [a for a in m.get(f"{MQ}/authorisations").json()["items"] if a["group_id"] == gid]
    print("auths after revise (all)", [(a["status"], a["quote_number"]) for a in a2])
    sub = [a for a in m.get(f"{MQ}/authorisations", params={"status": "submitted"}).json()["items"] if a["group_id"] == gid]
    print("submitted queue for group after revise:", len(sub))
    g2 = r.json()
    publish_flow(m, gid, g2["quotes"])
    cg = [x for x in c.get(f"{API}/mod/site/quotes").json()["groups"] if x["id"] == gid][0]
    print("customer group status", cg["status"], "rev quotes", [q["quote_number"] + ":" + q["status"] for q in cg["quotes"]], "auth", (cg.get("authorisation") or {}).get("status"))
    qa2 = next(q["id"] for q in g2["quotes"] if q["mod_quote_type"] == "A")
    print("auth2", c.post(f"{API}/mod/site/quotes/{qa2}/authorise", data={"authorising_officer": "TEST_x", "authorisation_date": "2026-01-10"}).status_code)
    print("old quote authorise", c.post(f"{API}/mod/site/quotes/{qa}/authorise", data={"authorising_officer": "TEST_x", "authorisation_date": "2026-01-10"}).status_code)
finally:
    run(delete_groups([gid]))
    print("cleaned", gid)
