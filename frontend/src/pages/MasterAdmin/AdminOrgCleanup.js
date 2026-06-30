/**
 * Org Cleanup — consolidate duplicate / stray organisations safely.
 *
 *  • Pin ONE org as the operator company (the Pulse portal quick-button target).
 *  • Merge & delete stray orgs — child data is reassigned to the keep org first,
 *    then the stray is hard-deleted. System orgs (own a master admin) and the
 *    pinned operator are protected. Typed confirmation + dry-run preview.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  Building2, Loader2, ShieldCheck, Star, Trash2, AlertTriangle,
  RefreshCw, Crown, Lock,
} from 'lucide-react';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

export default function AdminOrgCleanup() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const auth = { headers: { Authorization: `Bearer ${token}` } };

  const [q, setQ] = useState('Pulse Fitness');
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [keepId, setKeepId] = useState('');
  const [deleteIds, setDeleteIds] = useState([]);
  const [preview, setPreview] = useState(null);
  const [confirmText, setConfirmText] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/api/master-admin/org-cleanup/candidates?q=${encodeURIComponent(q)}`, auth);
      setOrgs(r.data.organizations || []);
      const op = (r.data.organizations || []).find(o => o.is_operator_company);
      if (op && !keepId) setKeepId(op.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load organisations');
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  useEffect(() => { load(); }, [load]);

  const setOperator = async (org) => {
    setBusy(true);
    try {
      await axios.post(`${API}/api/master-admin/org-cleanup/set-operator/${org.id}`, {}, auth);
      toast.success(`'${org.name}' pinned as the operator company`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to pin operator');
    } finally { setBusy(false); }
  };

  const toggleDelete = (id) => {
    setPreview(null); setConfirmText('');
    setDeleteIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const runMerge = async (dryRun) => {
    if (!keepId) { toast.error('Pick the org to KEEP'); return; }
    if (deleteIds.length === 0) { toast.error('Select at least one org to delete'); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/api/master-admin/org-cleanup/merge-delete`,
        { keep_org_id: keepId, delete_org_ids: deleteIds, dry_run: dryRun }, auth);
      if (dryRun) {
        setPreview(r.data);
      } else {
        toast.success(`Deleted ${r.data.deleted.length} org(s) and reassigned their data`);
        setPreview(null); setConfirmText(''); setDeleteIds([]);
        await load();
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Operation failed');
    } finally { setBusy(false); }
  };

  const keepOrg = orgs.find(o => o.id === keepId);
  const canDelete = confirmText.trim().toUpperCase() === 'DELETE' && deleteIds.length > 0 && keepId;

  return (
    <div className="space-y-6" data-testid="org-cleanup-panel">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Building2 className="w-5 h-5 text-sky-500" /> Organisation Cleanup
          </h2>
          <p className="text-sm text-zinc-500 mt-1">
            Pin your operator company and safely merge &amp; delete duplicate orgs. Child data is
            reassigned to the kept org first; system &amp; pinned orgs are protected.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            data-testid="org-cleanup-search"
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Filter by name…"
            className="px-3 py-2 rounded-lg border border-zinc-300 text-sm bg-white"
          />
          <button onClick={load} disabled={busy}
            data-testid="org-cleanup-refresh"
            className="px-3 py-2 rounded-lg border border-zinc-300 text-sm flex items-center gap-1 hover:bg-zinc-50">
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-zinc-400">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-zinc-200">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-zinc-500 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-3">Organisation</th>
                <th className="text-left px-4 py-3">Owner</th>
                <th className="text-left px-4 py-3">Data</th>
                <th className="text-center px-4 py-3">Keep</th>
                <th className="text-center px-4 py-3">Operator</th>
                <th className="text-center px-4 py-3">Delete</th>
              </tr>
            </thead>
            <tbody>
              {orgs.map((o) => {
                const counts = Object.entries(o.counts || {});
                const isKeep = keepId === o.id;
                const isDel = deleteIds.includes(o.id);
                return (
                  <tr key={o.id} data-testid={`org-row-${o.id}`}
                    className={`border-t border-zinc-100 ${isDel ? 'bg-red-50' : isKeep ? 'bg-emerald-50' : ''}`}>
                    <td className="px-4 py-3">
                      <div className="font-medium flex items-center gap-2">
                        {o.name}
                        {o.is_operator_company && (
                          <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
                            <Crown className="w-3 h-3" /> Operator
                          </span>
                        )}
                        {o.is_system_org && (
                          <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-violet-100 text-violet-700">
                            <ShieldCheck className="w-3 h-3" /> System
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-zinc-400">{o.account_type || '—'} · {o.id}</div>
                    </td>
                    <td className="px-4 py-3 text-zinc-600">{o.owner_email || '—'}</td>
                    <td className="px-4 py-3 text-xs text-zinc-500">
                      {counts.length === 0 ? <span className="text-zinc-300">empty</span>
                        : counts.map(([k, v]) => <span key={k} className="inline-block mr-2">{k}: <b>{v}</b></span>)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <input type="radio" name="keep" checked={isKeep}
                        data-testid={`keep-radio-${o.id}`}
                        onChange={() => { setKeepId(o.id); setDeleteIds(prev => prev.filter(x => x !== o.id)); setPreview(null); }} />
                    </td>
                    <td className="px-4 py-3 text-center">
                      {o.is_operator_company ? (
                        <Star className="w-4 h-4 text-amber-500 fill-amber-400 mx-auto" />
                      ) : (
                        <button onClick={() => setOperator(o)} disabled={busy}
                          data-testid={`set-operator-${o.id}`}
                          className="text-xs px-2 py-1 rounded border border-amber-300 text-amber-700 hover:bg-amber-50">
                          Pin
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {o.protected || isKeep ? (
                        <Lock className="w-4 h-4 text-zinc-300 mx-auto" title={o.protected ? 'Protected system org' : 'This is the keep org'} />
                      ) : (
                        <input type="checkbox" checked={isDel}
                          data-testid={`delete-check-${o.id}`}
                          onChange={() => toggleDelete(o.id)} />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Action bar */}
      {deleteIds.length > 0 && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 space-y-3" data-testid="merge-action-bar">
          <div className="flex items-start gap-2 text-sm text-red-800">
            <AlertTriangle className="w-5 h-5 shrink-0" />
            <div>
              You are about to reassign all data from <b>{deleteIds.length}</b> org(s) into{' '}
              <b>{keepOrg?.name || '—'}</b> and permanently delete them. This is logged &amp; the deleted
              org snapshot is archived to <code>org_cleanup_audit</code>.
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button onClick={() => runMerge(true)} disabled={busy}
              data-testid="dry-run-btn"
              className="px-3 py-2 rounded-lg border border-zinc-300 text-sm hover:bg-white">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Preview (dry run)'}
            </button>
            <input
              value={confirmText} onChange={(e) => setConfirmText(e.target.value)}
              placeholder='Type DELETE to confirm'
              data-testid="confirm-delete-input"
              className="px-3 py-2 rounded-lg border border-red-300 text-sm bg-white"
            />
            <button onClick={() => runMerge(false)} disabled={busy || !canDelete}
              data-testid="confirm-merge-delete-btn"
              className={`px-3 py-2 rounded-lg text-sm text-white flex items-center gap-1 ${canDelete ? 'bg-red-600 hover:bg-red-700' : 'bg-red-300 cursor-not-allowed'}`}>
              <Trash2 className="w-4 h-4" /> Merge &amp; Delete
            </button>
          </div>

          {preview && (
            <div className="text-xs bg-white rounded-lg border border-zinc-200 p-3" data-testid="dry-run-result">
              <div className="font-medium mb-1">Dry-run — records that would be reassigned to {preview.keep_org_name}:</div>
              {preview.results.map((r) => (
                <div key={r.org_id} className="mb-1">
                  <b>{r.org_name}</b>: {Object.keys(r.reassigned).length === 0 ? 'no child data'
                    : Object.entries(r.reassigned).map(([k, v]) => `${k}=${v}`).join(', ')}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
