# MODService: ESP engineer (Jimmy preview copy) login + job scope, and .ai-free served HTML
import os
import re
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
EMAIL = "jimmy.connors.preview@example.test"
PASSWORD = "PreviewJimmy#2026"
AI_RE = re.compile(r'(pulsefitness|gymaxis)\.ai', re.I)


@pytest.fixture(scope="module")
def jimmy():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD, "portal": "mod"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Jimmy login failed {r.status_code} {r.text[:200]}")
    return r.json()


# Served HTML
def test_root_html_clean():
    r = requests.get(f"{BASE_URL}/", timeout=60)
    assert r.status_code == 200
    assert not AI_RE.search(r.text), AI_RE.findall(r.text)
    assert "<title>Pulse Fitness MOD Service</title>" in r.text


# Auth
def test_login_mod_portal(jimmy):
    assert isinstance(jimmy.get("token") or jimmy.get("access_token"), str)
    assert jimmy["user"]["is_external_engineer"] is True
    assert not AI_RE.search(str(jimmy))


def test_login_wrong_password():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": "wrong-pass", "portal": "mod"}, timeout=30)
    assert r.status_code in (400, 401)


# Engineer jobs scope
def test_open_jobs_exact(jimmy):
    tok = jimmy.get("token") or jimmy.get("access_token")
    r = requests.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "open"},
                     headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    jobs = data if isinstance(data, list) else (data.get("jobs") or data.get("items") or [])
    txt = str(jobs)
    refs = sorted(set(re.findall(r'(GIB-T\d|CYP-T\d)', txt)))
    print("refs", refs, "count", len(jobs))
    assert refs == ["GIB-T1", "GIB-T2"]
    assert len(jobs) == 2
    assert not AI_RE.search(r.text)


def test_jobs_unauth():
    r = requests.get(f"{BASE_URL}/api/svc/engineer/jobs", params={"when": "open"}, timeout=30)
    assert r.status_code in (401, 403)
