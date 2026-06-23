"""Phase 2 — Comms audience segmentation backend tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/') or 'http://localhost:8001'
ADMIN_EMAIL = 'admin@pulsefitness.com'
ADMIN_PASSWORD = 'C2s9yJ3YAhydB4d34-Bykg'


@pytest.fixture(scope='module')
def headers():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={'email': ADMIN_EMAIL, 'password': ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get('token') or r.json().get('access_token')
    assert tok
    return {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}


@pytest.fixture(scope='module')
def created_ids():
    return []


def test_segments_fields(headers):
    r = requests.get(f"{BASE_URL}/api/comms/segments/fields", headers=headers, timeout=20)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    src_ids = {s['id'] for s in d['sources']}
    assert {'contacts', 'members'} <= src_ids
    assert 'contacts' in d['fields'] and 'members' in d['fields']
    op_ids = {o['id'] for o in d['operators']}
    for op in ('==', '!=', '>=', '<=', '>', '<', 'in'):
        assert op in op_ids
    assert any('d_ago' in s for s in d['date_sentinels'])


def test_segment_preview_contacts(headers):
    body = {'source': 'contacts', 'rules': {'op': 'and', 'conditions': [{'field': 'lifecycle', 'op': '==', 'value': 'lead'}]}}
    r = requests.post(f"{BASE_URL}/api/comms/segments/preview", json=body, headers=headers, timeout=20)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert 'count' in d and isinstance(d['count'], int)
    assert 'sample' in d and isinstance(d['sample'], list)


def test_segment_preview_members(headers):
    body = {'source': 'members', 'rules': {'op': 'and', 'conditions': []}}
    r = requests.post(f"{BASE_URL}/api/comms/segments/preview", json=body, headers=headers, timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert 'count' in d and isinstance(d['count'], int)


def test_segment_create_list_get(headers, created_ids):
    payload = {
        'name': 'TEST_lapsed_premium',
        'source': 'members',
        'type': 'dynamic',
        'rules': {'op': 'and', 'conditions': [{'field': 'status', 'op': '==', 'value': 'lapsed'}]},
    }
    r = requests.post(f"{BASE_URL}/api/comms/segments", json=payload, headers=headers, timeout=20)
    assert r.status_code == 200, r.text[:200]
    seg = r.json()['segment']
    assert seg['id'] and seg['name'] == 'TEST_lapsed_premium'
    assert seg['source'] == 'members'
    assert seg['type'] == 'dynamic'
    assert 'member_count' in seg
    assert 'sample' in seg
    sid = seg['id']
    created_ids.append(sid)

    # List
    r = requests.get(f"{BASE_URL}/api/comms/segments", headers=headers, timeout=20)
    assert r.status_code == 200
    ids = [s['id'] for s in r.json()['segments']]
    assert sid in ids

    # Get single
    r = requests.get(f"{BASE_URL}/api/comms/segments/{sid}", headers=headers, timeout=20)
    assert r.status_code == 200
    assert r.json()['segment']['id'] == sid


def test_segment_update_reevaluates(headers, created_ids):
    assert created_ids
    sid = created_ids[0]
    upd = {'name': 'TEST_lapsed_renamed', 'rules': {'op': 'or', 'conditions': [{'field': 'status', 'op': '==', 'value': 'active'}]}}
    r = requests.put(f"{BASE_URL}/api/comms/segments/{sid}", json=upd, headers=headers, timeout=20)
    assert r.status_code == 200
    seg = r.json()['segment']
    assert seg['name'] == 'TEST_lapsed_renamed'
    assert seg['rules']['op'] == 'or'
    # member_count refreshed in update path
    assert 'member_count' in seg


def test_segment_members_endpoint(headers, created_ids):
    sid = created_ids[0]
    r = requests.get(f"{BASE_URL}/api/comms/segments/{sid}/members", headers=headers, timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert 'members' in d and isinstance(d['members'], list)
    assert 'total' in d and isinstance(d['total'], int)


def test_campaign_with_segment_id(headers, created_ids):
    sid = created_ids[0]
    r = requests.post(f"{BASE_URL}/api/comms/campaigns",
                      json={'name': 'TEST_seg_campaign', 'campaign_type': 'regular', 'segment_id': sid},
                      headers=headers, timeout=20)
    assert r.status_code == 200, r.text[:200]
    c = r.json()['campaign']
    assert c['segment_id'] == sid
    # cleanup campaign via archive
    requests.delete(f"{BASE_URL}/api/comms/campaigns/{c['id']}", headers=headers, timeout=20)


def test_segment_delete(headers, created_ids):
    sid = created_ids[0]
    r = requests.delete(f"{BASE_URL}/api/comms/segments/{sid}", headers=headers, timeout=20)
    assert r.status_code == 200
    # 404 after delete
    r = requests.get(f"{BASE_URL}/api/comms/segments/{sid}", headers=headers, timeout=20)
    assert r.status_code == 404


def test_invalid_source(headers):
    r = requests.post(f"{BASE_URL}/api/comms/segments/preview",
                      json={'source': 'bogus', 'rules': {'op': 'and', 'conditions': []}},
                      headers=headers, timeout=20)
    assert r.status_code == 400
