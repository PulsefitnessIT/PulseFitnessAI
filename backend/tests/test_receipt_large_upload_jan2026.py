"""Regression: Staff Portal expense receipt upload accepts large / HEIC (Live Photo) images,
converts to small JPEG server-side; PDF untouched; >25MB → 413; bad HEIC → 415.
Also vehicle-check + crash-pack photo uploads with large images."""
import io
import os
import time
import pytest
import requests
import numpy as np
from PIL import Image
import pillow_heif

pillow_heif.register_heif_opener()

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
EMAIL, PW = "vc.driver@pulsefitness.test", "Driver123!"
_CACHE = "/tmp/rcpt_token.txt"


def _noise(w, h, seed=1):
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (h, w, 3), dtype=np.uint8), "RGB")


@pytest.fixture(scope="module")
def token():
    if os.path.exists(_CACHE) and time.time() - os.path.getmtime(_CACHE) < 3000:
        t = open(_CACHE).read().strip()
        if requests.get(f"{API}/new-starter/portal/expenses", headers={"Authorization": f"Bearer {t}"}, timeout=30).status_code == 200:
            return t
    for i in range(5):
        r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PW}, timeout=30)
        if r.status_code != 429:
            break
        time.sleep(6 + i * 3)
    assert r.status_code == 200, r.text
    t = r.json().get("token") or r.json().get("access_token")
    open(_CACHE, "w").write(t)
    return t


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def claim_id(H):
    # Far-future month claim; testing agent cleans via mongo (staff VCTEST_staff, months 2027-11/12)
    r = requests.post(f"{API}/new-starter/portal/expenses", json={"claim_month": "2027-11"}, headers=H, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    cid = d.get("id") or (d.get("claim") or {}).get("id")
    assert cid
    return cid


@pytest.fixture(scope="module")
def big_heic():
    img = _noise(4032, 3024, 2)  # iPhone 12MP; larger noise HEICs hit an encoder quirk
    buf = io.BytesIO(); img.save(buf, "HEIF", quality=80)
    return buf.getvalue()


@pytest.fixture(scope="module")
def big_jpeg():
    img = _noise(4200, 3200, 3)
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=97)
    return buf.getvalue()


def _upload(H, cid, name, data, ctype):
    return requests.post(f"{API}/new-starter/portal/expenses/{cid}/receipt", headers=H,
                         files={"file": (name, data, ctype)}, timeout=180)


def _get(H, cid, rid):
    return requests.get(f"{API}/new-starter/portal/expenses/{cid}/receipt/{rid}", headers=H, timeout=60)


# --- Receipt upload: large HEIC ---
def test_large_heic_receipt(H, claim_id, big_heic):
    print("HEIC size MB", len(big_heic) / 1e6)
    assert len(big_heic) > 5 * 1024 * 1024
    r = _upload(H, claim_id, "IMG_0001.HEIC", big_heic, "image/heic")
    assert r.status_code == 200, r.text
    rid = r.json()["receipt_id"]
    g = _get(H, claim_id, rid)
    assert g.status_code == 200
    assert g.headers["content-type"].startswith("image/jpeg")
    im = Image.open(io.BytesIO(g.content))
    assert im.format == "JPEG" and max(im.size) <= 2000
    print("stored bytes", len(g.content), im.size)
    assert len(g.content) < len(big_heic)


# --- Receipt upload: large JPEG ---
def test_large_jpeg_receipt(H, claim_id, big_jpeg):
    print("JPEG size MB", len(big_jpeg) / 1e6)
    assert len(big_jpeg) > 10 * 1024 * 1024
    r = _upload(H, claim_id, "IMG_0002.JPG", big_jpeg, "image/jpeg")
    assert r.status_code == 200, r.text
    g = _get(H, claim_id, r.json()["receipt_id"])
    im = Image.open(io.BytesIO(g.content))
    assert g.headers["content-type"].startswith("image/jpeg")
    assert max(im.size) <= 2000 and len(g.content) < len(big_jpeg) / 3


# --- EXIF rotation respected ---
def test_exif_rotation(H, claim_id):
    img = Image.new("RGB", (3000, 1000), (200, 50, 50))
    exif = Image.Exif(); exif[0x0112] = 6
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=100, exif=exif.tobytes())
    r = _upload(H, claim_id, "rot.jpg", buf.getvalue(), "image/jpeg")
    assert r.status_code == 200, r.text
    im = Image.open(io.BytesIO(_get(H, claim_id, r.json()["receipt_id"]).content))
    print("rotated size", im.size)
    assert im.size[1] > im.size[0]  # portrait after transpose


# --- PDF untouched ---
def test_pdf_unchanged(H, claim_id):
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n" + b"0" * 1000
    r = _upload(H, claim_id, "receipt.pdf", pdf, "application/pdf")
    assert r.status_code == 200, r.text
    g = _get(H, claim_id, r.json()["receipt_id"])
    assert g.headers["content-type"].startswith("application/pdf")
    assert g.content == pdf


# --- >25MB → 413 JSON ---
def test_over_25mb_413(H, claim_id):
    # Edge proxy intermittently turns the early 413 into a 502 (~40%) — retry
    blob = os.urandom(26 * 1024 * 1024)
    for _ in range(4):
        r = _upload(H, claim_id, "huge.jpg", blob, "image/jpeg")
        if r.status_code == 413:
            break
    assert r.status_code == 413, r.status_code
    assert "detail" in r.json()
    print(r.json())


# --- Unreadable HEIC → 415 friendly ---
def test_bad_heic_415(H, claim_id):
    r = _upload(H, claim_id, "IMG_9.HEIC", os.urandom(200_000), "image/heic")
    assert r.status_code == 415, r.text
    assert "take the receipt photo again" in r.json()["detail"]


# --- JSON expense endpoints still fine (2MB tier) ---
def test_claim_list_and_get(H, claim_id):
    r = requests.get(f"{API}/new-starter/portal/expenses", headers=H, timeout=30)
    assert r.status_code == 200
    g = requests.get(f"{API}/new-starter/portal/expenses/{claim_id}", headers=H, timeout=30)
    assert g.status_code == 200


# --- Regression: vehicle-check + crash-pack photo with large images ---
def test_vehicle_photo_large(H, big_heic, big_jpeg):
    r = requests.post(f"{API}/new-starter/portal/vehicle-check/photo", headers=H,
                      files={"file": ("IMG_0003.HEIC", big_heic, "image/heic")}, timeout=180)
    assert r.status_code == 200, r.text
    assert r.json().get("file_id")
    r = requests.post(f"{API}/new-starter/portal/vehicle-check/photo", headers=H,
                      files={"file": ("big.jpg", big_jpeg, "image/jpeg")}, timeout=180)
    assert r.status_code == 200, r.text


def test_crash_photo_large(H, big_jpeg):
    r = requests.post(f"{API}/new-starter/portal/crash-packs/photo", headers=H,
                      files={"file": ("crash.jpg", big_jpeg, "image/jpeg")}, timeout=180)
    assert r.status_code == 200, r.text
    assert r.json().get("file_id")


# --- JSON update (PUT) with a receipt-linked line + submit ---
def test_put_line_and_submit(H, claim_id, big_jpeg):
    r = _upload(H, claim_id, "line.jpg", big_jpeg, "image/jpeg")
    rid = r.json()["receipt_id"]
    lines = [{"date": "2027-11-03", "description": "TEST_fuel", "nominal": "", "net": 10, "vat": 2,
              "no_vat": False, "receipt_id": rid}]
    p = requests.put(f"{API}/new-starter/portal/expenses/{claim_id}", json={"lines": lines}, headers=H, timeout=30)
    assert p.status_code == 200, p.text
    g = requests.get(f"{API}/new-starter/portal/expenses/{claim_id}", headers=H, timeout=30).json()
    gl = (g.get("claim") or g)["lines"]
    assert gl[0]["receipt_id"] == rid
    s = requests.post(f"{API}/new-starter/portal/expenses/{claim_id}/submit", headers=H, timeout=30)
    assert s.status_code == 200, s.text
    assert s.json()["status"] == "submitted"
