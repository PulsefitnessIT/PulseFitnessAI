"""Dealer Warranty Parts Phase 3 — usage / stores-dashboard / RMA."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    # fallback to frontend .env
    with open('/app/frontend/.env') as f:
        for ln in f:
            if ln.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = ln.split('=', 1)[1].strip().rstrip('/')

EMAIL = 'owner@isodemo.com'
PASSWORD = 'IsoDemo123!'


@pytest.fixture(scope='session')
def token():
    r = requests.post(f'{BASE_URL}/api/auth/login', json={'email': EMAIL, 'password': PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()['token']


@pytest.fixture(scope='session')
def h(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture(scope='session')
def dealers(h):
    r = requests.get(f'{BASE_URL}/api/dealer-parts/dealers', headers=h)
    assert r.status_code == 200, r.text
    return r.json().get('dealers') or []


def _find_dealer(dealers, name_contains):
    for d in dealers:
        if name_contains.lower() in (d.get('name') or '').lower():
            return d
    return None


# ── USAGE ──
class TestUsage:
    def test_log_usage_decrements_stock_and_writes_movement(self, h, dealers):
        dealer = _find_dealer(dealers, 'Fitline')
        assert dealer, 'Fitline Deutschland dealer not seeded'
        # find its store & BELT-260G stock
        stores = requests.get(f'{BASE_URL}/api/dealer-parts/stores', headers=h,
                              params={'dealer_id': dealer['id']}).json().get('stores') or []
        assert stores, 'no stores'
        target_store, before_qty = None, None
        for s in stores:
            stock = requests.get(f'{BASE_URL}/api/dealer-parts/stores/{s["id"]}/stock', headers=h).json().get('stock') or []
            for row in stock:
                if row.get('part_sku') == 'BELT-260G' and (row.get('qty_on_hand') or 0) > 0:
                    target_store, before_qty = s, row['qty_on_hand']
                    break
            if target_store:
                break
        assert target_store, 'BELT-260G with stock not found on Fitline'

        # log usage
        payload = {
            'dealer_id': dealer['id'], 'store_id': target_store['id'],
            'part_sku': 'BELT-260G', 'quantity': 1, 'machine_model': 'TEST_TREAD-9',
            'serial_number': 'TEST_SN1', 'failure_reason': 'wear_and_tear', 'warranty': True,
            'notes': 'TEST_usage_phase3',
        }
        r = requests.post(f'{BASE_URL}/api/dealer-parts/usage', headers=h, json=payload)
        assert r.status_code == 200, r.text
        usage = r.json()
        assert usage['part_sku'] == 'BELT-260G'
        assert usage['dealer_id'] == dealer['id']
        assert 'id' in usage

        # verify stock decremented + last_used set
        stock2 = requests.get(f'{BASE_URL}/api/dealer-parts/stores/{target_store["id"]}/stock', headers=h).json().get('stock') or []
        row2 = next((r for r in stock2 if r['part_sku'] == 'BELT-260G'), None)
        assert row2 and row2['qty_on_hand'] == before_qty - 1
        assert row2.get('last_used'), 'last_used not set'

        # verify movement written
        mv = requests.get(f'{BASE_URL}/api/dealer-parts/movements', headers=h,
                         params={'dealer_id': dealer['id']}).json().get('movements') or []
        used = [m for m in mv if m.get('movement_type') == 'part_used' and m.get('part_sku') == 'BELT-260G']
        assert used, 'no part_used movement written'

        # list usage filterable
        lst = requests.get(f'{BASE_URL}/api/dealer-parts/usage', headers=h,
                          params={'dealer_id': dealer['id'], 'part_sku': 'BELT-260G'}).json()
        assert lst.get('count', 0) >= 1
        assert any(u['id'] == usage['id'] for u in lst.get('usage') or [])

    def test_usage_bad_case_id_does_not_error(self, h, dealers):
        dealer = _find_dealer(dealers, 'Fitline')
        r = requests.post(f'{BASE_URL}/api/dealer-parts/usage', headers=h, json={
            'dealer_id': dealer['id'], 'part_sku': 'TEST-NONESUCH', 'quantity': 1,
            'case_id': 'non-existent-case-xyz', 'failure_reason': 'other', 'warranty': False,
            'notes': 'TEST_phase3_badcase',
        })
        assert r.status_code == 200, r.text

    def test_usage_validation(self, h, dealers):
        dealer = _find_dealer(dealers, 'Fitline')
        r = requests.post(f'{BASE_URL}/api/dealer-parts/usage', headers=h, json={
            'dealer_id': dealer['id'], 'part_sku': '', 'quantity': 0,
        })
        assert r.status_code == 400


# ── STORES DASHBOARD ──
class TestStoresDashboard:
    def test_dashboard_shape(self, h):
        r = requests.get(f'{BASE_URL}/api/dealer-parts/stores-dashboard', headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert 'cards' in d and 'to_pick' in d and 'awaiting_receipt' in d
        assert 'recent_usage' in d and 'low_stock' in d
        for k in ('to_pick', 'awaiting_receipt', 'low_stock', 'open_rma'):
            assert k in d['cards']
        # seeded expectations
        assert any('GulfGym' in (a.get('dealer_name') or '') for a in d['to_pick']), 'GulfGym approved alloc missing from to_pick'
        assert any('IberFit' in (a.get('dealer_name') or '') for a in d['awaiting_receipt']), 'IberFit dispatched missing from awaiting_receipt'


# ── RMA ──
class TestRma:
    created_id = None

    def test_create_rma_auto_reference(self, h, dealers):
        dealer = _find_dealer(dealers, 'Fitline')
        r = requests.post(f'{BASE_URL}/api/dealer-parts/rma', headers=h, json={
            'dealer_id': dealer['id'], 'part_sku': 'BELT-260G',
            'failure_reason': 'manufacturing_defect_suspected', 'notes': 'TEST_rma_phase3',
        })
        assert r.status_code == 200, r.text
        j = r.json()
        assert j['status'] == 'return_requested'
        assert j['rma_reference'].startswith('RMA-')
        TestRma.created_id = j['id']

    def test_list_rma(self, h):
        r = requests.get(f'{BASE_URL}/api/dealer-parts/rma', headers=h)
        assert r.status_code == 200
        assert any(x['id'] == TestRma.created_id for x in r.json().get('rma') or [])

    def test_patch_rma_valid_status(self, h):
        r = requests.patch(f'{BASE_URL}/api/dealer-parts/rma/{TestRma.created_id}', headers=h,
                           json={'status': 'under_inspection'})
        assert r.status_code == 200
        assert r.json()['status'] == 'under_inspection'

    def test_patch_rma_invalid_status(self, h):
        r = requests.patch(f'{BASE_URL}/api/dealer-parts/rma/{TestRma.created_id}', headers=h,
                           json={'status': 'not_a_real_status'})
        assert r.status_code == 400

    def test_create_rma_validation(self, h):
        r = requests.post(f'{BASE_URL}/api/dealer-parts/rma', headers=h, json={'part_sku': 'X'})
        assert r.status_code == 400
