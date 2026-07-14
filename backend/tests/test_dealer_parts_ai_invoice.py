"""Backend tests: Dealer Parts AI invoice parsing + RBAC."""
import io
import os
import time
import requests
import pytest

def _read_env_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""

BASE = _read_env_backend_url().rstrip("/")
API = f"{BASE}/api"

STAFF = ("owner@isodemo.com", "IsoDemo123!")
DEALER = ("portal2@fitline.test", "DealerDemo123!")


def _login(email, password, retries=3):
    last = None
    for i in range(retries):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            return data.get("token") or data.get("access_token")
        last = r
        if r.status_code == 429:
            time.sleep(40)
            continue
        time.sleep(2)
    raise RuntimeError(f"login failed for {email}: {last.status_code} {last.text[:200]}")


@pytest.fixture(scope="module")
def staff_token():
    return _login(*STAFF)


@pytest.fixture(scope="module")
def dealer_token():
    time.sleep(35)  # avoid rate limit clash with staff login
    return _login(*DEALER)


INVOICE_TXT = (
    "PULSE FITNESS INVOICE PO-TEST-001\n"
    "Currency: GBP\n"
    "Qty, Model, Description, Unit Value\n"
    "3, 305H-ZZY, Treadmill, 12500\n"
    "1, UNKNOWN-XYZ-999, Some mystery machine, 1000\n"
    "Order Total: 38500\n"
)


def test_ai_parse_invoice_staff_matches_305H_ZZY(staff_token):
    files = {"file": ("invoice.csv", io.BytesIO(INVOICE_TXT.encode()), "text/csv")}
    headers = {"Authorization": f"Bearer {staff_token}"}
    r = requests.post(f"{API}/dealer-parts/data/ai-parse-invoice", files=files, headers=headers, timeout=90)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    data = r.json()
    print("AI parse response:", data)
    # If LLM unavailable, allow graceful failure
    if not data.get("available"):
        pytest.skip(f"LLM returned unavailable: {data.get('error')}")
    assert data.get("order_value"), "order_value should be populated"
    lines = data.get("lines") or []
    assert lines, "lines array should not be empty"
    zzy = [l for l in lines if "305H-ZZY" in (l.get("input_ref") or "").upper() or (l.get("top_level_ref") or "").upper() == "305H-ZZY"]
    assert zzy, f"expected a 305H-ZZY line, got: {lines}"
    z = zzy[0]
    assert z.get("matched") is True, f"305H-ZZY line should be matched: {z}"
    assert z.get("match_method") == "exact_ref", f"expected exact_ref, got {z.get('match_method')}"
    assert (z.get("top_level_ref") or "").upper() == "305H-ZZY"
    assert data.get("matched_count", 0) >= 1
    # unknown should be unmatched
    unknown = [l for l in lines if "UNKNOWN" in (l.get("input_ref") or "").upper()]
    if unknown:
        assert unknown[0].get("matched") is False


def test_ai_parse_invoice_dealer_forbidden(dealer_token):
    files = {"file": ("invoice.csv", io.BytesIO(INVOICE_TXT.encode()), "text/csv")}
    headers = {"Authorization": f"Bearer {dealer_token}"}
    r = requests.post(f"{API}/dealer-parts/data/ai-parse-invoice", files=files, headers=headers, timeout=30)
    assert r.status_code == 403, f"expected 403 for dealer, got {r.status_code}: {r.text[:200]}"
