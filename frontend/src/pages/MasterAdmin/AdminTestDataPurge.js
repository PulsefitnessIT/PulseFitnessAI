/**
 * Test Data Purge — clean up regression fixtures that leaked into the DB.
 *
 * A boot-time seed historically upserted the test user
 * lee.somers@pulsefitness.com and its "— Somers (test)" org (plus demo-seed
 * orgs) into whichever DB the process pointed at, including production. That
 * seed is now hard-gated off in production; this tool removes what already
 * spilled. Dry-run preview first, then confirm.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Trash2, Loader2, AlertTriangle, RefreshCw, Lock, FlaskConical } from 'lucide-react';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

export default function AdminTestDataPurge() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const auth = { headers: { Authorization: `Bearer ${token}` } };

  const [orgs, setOrgs] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [confirmText, setConfirmText] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/api/master-admin/test-data/candidates`, auth);
      setOrgs(r.data.organizations || []);
      setUsers(r.data.users || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load test-data candidates');
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load]);

  const run = async (dryRun) => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/api/master-admin/test-data/purge`, { dry_run: dryRun }, auth);
      if (dryRun) {
        setPreview(r.data);
      } else {
        const delOrgs = r.data.organizations.filter(o => !o.skipped).length;
        const delUsers = r.data.users.filter(u => u.deleted).length;
        toast.success(`Purged ${delOrgs} test org(s) and ${delUsers} test user(s)`);
        setPreview(null); setConfirmText('');
        await load();
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Purge failed');
    } finally { setBusy(false); }
  };

  const deletableOrgs = orgs.filter(o => !o.protected);
  const deletableUsers = users.filter(u => !u.is_master_admin);
  const nothingToPurge = deletableOrgs.length === 0 && deletableUsers.length === 0;
  const canDelete = confirmText.trim().toUpperCase() === 'DELETE' && !nothingToPurge;

  return (
    <div className="space-y-6" data-testid="test-data-purge-panel">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-sky-500" /> Purge Test Data
          </h2>
          <p className="text-sm text-zinc-500 mt-1">
            Detects regression fixtures that may have leaked into this database (the
            <code className="mx-1">lee.somers@pulsefitness.com</code> test user, its
            "— Somers (test)" org, and demo-seed orgs). System &amp; pinned operator orgs are protected.
          </p>
        </div>
        <button onClick={load} disabled={busy}
          data-testid="test-data-refresh"
          className="px-3 py-2 rounded-lg border border-zinc-300 text-sm flex items-center gap-1 hover:bg-zinc-50">
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-zinc-400">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : nothingToPurge ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-sm text-emerald-800"
          data-testid="test-data-clean">
          ✓ No test data detected in this database.
        </div>
      ) : (
        <div className="space-y-4">
          <div className="overflow-x-auto rounded-xl border border-zinc-200">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 text-zinc-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-4 py-3">Test record</th>
                  <th className="text-left px-4 py-3">Type</th>
                  <th className="text-left px-4 py-3">Details</th>
                  <th className="text-center px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {orgs.map((o) => (
                  <tr key={o.id} data-testid={`test-org-row-${o.id}`} className="border-t border-zinc-100">
                    <td className="px-4 py-3 font-medium">{o.name}</td>
                    <td className="px-4 py-3 text-zinc-500">Organisation</td>
                    <td className="px-4 py-3 text-xs text-zinc-400">{o.account_type || '—'} · {o.id}</td>
                    <td className="px-4 py-3 text-center">
                      {o.protected
                        ? <span className="inline-flex items-center gap-1 text-xs text-zinc-400"><Lock className="w-3 h-3" /> {o.protected_reason}</span>
                        : <span className="text-xs text-red-600">will delete</span>}
                    </td>
                  </tr>
                ))}
                {users.map((u) => (
                  <tr key={u.id} data-testid={`test-user-row-${u.id}`} className="border-t border-zinc-100">
                    <td className="px-4 py-3 font-medium">{u.email}</td>
                    <td className="px-4 py-3 text-zinc-500">User</td>
                    <td className="px-4 py-3 text-xs text-zinc-400">{u.full_name || '—'}</td>
                    <td className="px-4 py-3 text-center">
                      {u.is_master_admin
                        ? <span className="inline-flex items-center gap-1 text-xs text-zinc-400"><Lock className="w-3 h-3" /> master admin</span>
                        : <span className="text-xs text-red-600">will delete</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="rounded-xl border border-red-200 bg-red-50 p-4 space-y-3" data-testid="purge-action-bar">
            <div className="flex items-start gap-2 text-sm text-red-800">
              <AlertTriangle className="w-5 h-5 shrink-0" />
              <div>
                Permanently deletes <b>{deletableOrgs.length}</b> org(s) (and all their org-scoped data) and{' '}
                <b>{deletableUsers.length}</b> user(s). Snapshots are archived to <code>test_data_purge_audit</code>.
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={() => run(true)} disabled={busy}
                data-testid="purge-dry-run-btn"
                className="px-3 py-2 rounded-lg border border-zinc-300 text-sm hover:bg-white">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Preview (dry run)'}
              </button>
              <input
                value={confirmText} onChange={(e) => setConfirmText(e.target.value)}
                placeholder='Type DELETE to confirm'
                data-testid="purge-confirm-input"
                className="px-3 py-2 rounded-lg border border-red-300 text-sm bg-white"
              />
              <button onClick={() => run(false)} disabled={busy || !canDelete}
                data-testid="purge-confirm-btn"
                className={`px-3 py-2 rounded-lg text-sm text-white flex items-center gap-1 ${canDelete ? 'bg-red-600 hover:bg-red-700' : 'bg-red-300 cursor-not-allowed'}`}>
                <Trash2 className="w-4 h-4" /> Purge Test Data
              </button>
            </div>

            {preview && (
              <div className="text-xs bg-white rounded-lg border border-zinc-200 p-3" data-testid="purge-dry-run-result">
                <div className="font-medium mb-1">Dry-run — records that would be removed:</div>
                {preview.organizations.map((r) => (
                  <div key={r.org_id} className="mb-1">
                    <b>{r.org_name}</b>: {r.skipped ? `skipped (${r.skipped})`
                      : Object.keys(r.removed || {}).length === 0 ? 'no child data'
                      : Object.entries(r.removed).map(([k, v]) => `${k}=${v}`).join(', ')}
                  </div>
                ))}
                {preview.users.map((r) => (
                  <div key={r.user_id} className="mb-1">
                    <b>{r.email}</b>: {r.skipped ? `skipped (${r.skipped})` : r.would_delete ? 'would delete' : 'not found'}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
