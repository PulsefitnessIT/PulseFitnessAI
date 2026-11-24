"""Edge checks against TEST_p3ui seeded data (public URL)."""
import os

import requests

from utils.auth import create_token

API = os.environ["PUB"] + "/api"
AFS = f"{API}/crm/v2/aftersales"
CID, O1 = "e32a7b96-fdc4-4243-b91e-8f88394f00ea", "b0e0032a-9c7c-57ab-bd18-1d9f8450dfe8"
O2 = "ca1a4845-6b68-55d6-affc-49106f8b5d09"


def h(uid):
    t = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token(uid)}"}).json()["token"]
    return {"Authorization": f"Bearer {t}"}


co, fin, asm = h("cm-test-coord"), h("cm-test-fin"), h("cm-test-asm")
checks = [
    ("bad date", requests.post(f"{AFS}/contracts/{CID}/obligations/{O2}/book", headers=co, json={"scheduled_date": "03/12/2026"}), 400),
    ("completed visit", requests.post(f"{AFS}/contracts/{CID}/obligations/{O1}/book", headers=co, json={"scheduled_date": "2027-01-01"}), 400),
    ("finance book", requests.post(f"{AFS}/contracts/{CID}/obligations/{O2}/book", headers=fin, json={"scheduled_date": "2027-01-01"}), 403),
    ("unknown engineer", requests.post(f"{AFS}/contracts/{CID}/obligations/{O2}/book", headers=co, json={"scheduled_date": "2027-09-01", "engineer_id": "nope"}), 400),
    ("unknown obligation", requests.post(f"{AFS}/contracts/{CID}/obligations/xx/book", headers=co, json={"scheduled_date": "2027-09-01"}), 404),
    ("bad review action", requests.post(f"{AFS}/contracts/{CID}/obligations/{O2}/review", headers=asm, json={"action": "zap"}), 400),
    ("exclude no note", requests.post(f"{AFS}/contracts/{CID}/obligations/{O2}/review", headers=asm, json={"action": "exclude"}), 400),
    ("reconciliation", requests.get(f"{AFS}/contracts/{CID}/service-reconciliation", headers=co), 200),
    ("engineers", requests.get(f"{AFS}/service-planner/engineers", headers=fin), 200),
    ("no auth planner", requests.get(f"{AFS}/service-planner"), 401),
]
for name, r, exp in checks:
    print(("PASS" if r.status_code == exp else "FAIL"), name, r.status_code, r.text[:140])
# booking lock released after failed engineer lookup?
r = requests.post(f"{AFS}/contracts/{CID}/obligations/{O2}/book", headers=co, json={"scheduled_date": "2027-09-01"})
print("rebook after failure", r.status_code, r.text[:120])
