"""
Iter 216h176 — Engineer mobile tuning regression test.

Verifies:
  1. Service worker bumps CACHE_NAME (forces clients to re-install
     with the new whitelist).
  2. Service worker whitelists the engineer endpoints so they survive
     offline.
  3. The SW pre-cache warmer module exists and exports `warmEngineerCache`.
  4. EngineerQueue.js virtualises its list (uses react-window's <List>).
  5. EngineerQueue.js wires the warmer to fire after a successful load.
  6. `react-window` is listed in package.json so production builds
     don't silently break on missing dep.
"""
import json
import os


FE = '/app/frontend'


def test_sw_cache_name_bumped():
    body = open(os.path.join(FE, 'public/sw.js')).read()
    assert "CACHE_NAME = 'gymaxis-v13'" in body, (
        "SW cache name must be bumped so clients re-install with the new "
        "engineer endpoint whitelist"
    )
    assert "API_CACHE  = 'gymaxis-api-v13'" in body


def test_sw_whitelists_engineer_endpoints():
    body = open(os.path.join(FE, 'public/sw.js')).read()
    for path in (
        '/api/svc/engineer/queue',
        '/api/svc/engineer/diary',
        '/api/svc/engineer/notifications',
        '/api/svc/engineer/inbox',
        '/api/svc/cases',
        '/api/svc/dispatcher/diary',
    ):
        assert f"'{path}'" in body, f"SW missing engineer offline pattern: {path}"


def test_sw_cache_quota_bumped():
    body = open(os.path.join(FE, 'public/sw.js')).read()
    assert 'API_MAX_ENTRIES = 200' in body, (
        "SW cache must hold the engineer's active week — bump to 200"
    )


def test_warmer_module_exists():
    path = os.path.join(FE, 'src/utils/swEngineerWarmer.js')
    assert os.path.exists(path)
    body = open(path).read()
    assert 'export function warmEngineerCache' in body
    # Should warm the diary 7 days ahead.
    assert 'inDays(7)' in body
    # Throttled so we don't hammer the network on every 30s auto-refresh.
    assert 'gymaxis_engineer_warm_at' in body


def test_engineer_queue_uses_react_window():
    body = open(os.path.join(FE, 'src/pages/ServiceOps/Engineer/EngineerQueue.js')).read()
    assert "from 'react-window'" in body, "EngineerQueue must import react-window"
    assert '<List' in body, "EngineerQueue must render react-window's <List>"
    # The cutover keeps a non-virtualised path for ≤30 jobs.
    assert 'filtered.length <= 30' in body, (
        "EngineerQueue must keep a non-virtualised fallback for very short queues"
    )


def test_engineer_queue_warms_cache_on_load():
    body = open(os.path.join(FE, 'src/pages/ServiceOps/Engineer/EngineerQueue.js')).read()
    assert "from '@/utils/swEngineerWarmer'" in body
    assert 'warmEngineerCache()' in body, (
        "EngineerQueue must fire the SW warmer after a successful queue load"
    )


def test_react_window_pinned_in_package_json():
    pkg = json.load(open(os.path.join(FE, 'package.json')))
    deps = pkg.get('dependencies') or {}
    assert 'react-window' in deps, "react-window must be a direct dep"
