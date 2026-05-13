/**
 * Master Admin — Partner Engineer Network (iter 216h75, Phase 1).
 *
 * Two stacked panels:
 *   1. Applications & status board — list, approve, reject, suspend,
 *      change level.
 *   2. Commission queue — approve accrued rows, queue them into a
 *      payout, mark the payout paid, and export the CSV for BACS.
 *
 * All write actions are audited server-side via `partner_audit_log`.
 * No data is ever soft-deleted — rejections live as ledger / partner
 * rows with explicit status changes.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Loader2, CheckCircle2, X, ShieldCheck, PoundSterling, Users,
  Download, ChevronRight, BadgeCheck,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL;

const LEVELS = [
  { id: 'engineer_partner',  label: 'Engineer Partner' },
  { id: 'verified_partner',  label: 'Verified Partner' },
  { id: 'strategic_partner', label: 'Strategic Partner' },
  { id: 'customer_added',    label: 'Customer-added' },
];

export default function AdminPartners() {
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [partners, setPartners] = useState([]);
  const [queue, setQueue] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null); // partner_id or ledger_id mid-action

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pRes, qRes, sRes] = await Promise.all([
        axios.get(`${API}/api/master-admin/partners`, { headers }),
        axios.get(`${API}/api/master-admin/partners/commission/queue`, { headers }),
        axios.get(`${API}/api/master-admin/partners/reports/summary`, { headers }),
      ]);
      setPartners(pRes.data?.partners || []);
      setQueue(qRes.data?.queue || []);
      setSummary(sRes.data || null);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load partners');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const approve = async (p) => {
    setBusy(p.id);
    try {
      await axios.post(`${API}/api/master-admin/partners/${p.id}/approve`, { level: p.level }, { headers });
      notify.success(`${p.full_name} approved`);
      await load();
    } catch (e) { notifyApiError(notify, e, 'Approve failed'); }
    finally { setBusy(null); }
  };

  const reject = async (p) => {
    const reason = window.prompt('Reason for rejection (optional):', '');
    if (reason === null) return;
    setBusy(p.id);
    try {
      await axios.post(`${API}/api/master-admin/partners/${p.id}/reject`, { reason }, { headers });
      notify.success(`${p.full_name} rejected`);
      await load();
    } catch (e) { notifyApiError(notify, e, 'Reject failed'); }
    finally { setBusy(null); }
  };

  const suspend = async (p) => {
    if (!window.confirm(`Suspend ${p.full_name}? Their commission accruals will pause.`)) return;
    setBusy(p.id);
    try {
      await axios.post(`${API}/api/master-admin/partners/${p.id}/suspend`, {}, { headers });
      notify.success(`${p.full_name} suspended`);
      await load();
    } catch (e) { notifyApiError(notify, e, 'Suspend failed'); }
    finally { setBusy(null); }
  };

  const setLevel = async (p, level) => {
    setBusy(p.id);
    try {
      await axios.post(`${API}/api/master-admin/partners/${p.id}/level`, { level }, { headers });
      notify.success(`Level set to ${level}`);
      await load();
    } catch (e) { notifyApiError(notify, e, 'Level change failed'); }
    finally { setBusy(null); }
  };

  const approveLedger = async (row) => {
    setBusy(row.id);
    try {
      await axios.post(`${API}/api/master-admin/partners/commission/${row.id}/approve`, {}, { headers });
      notify.success('Commission row approved');
      await load();
    } catch (e) { notifyApiError(notify, e, 'Approve failed'); }
    finally { setBusy(null); }
  };

  const rejectLedger = async (row) => {
    const reason = window.prompt('Reason for rejecting this commission row:', '');
    if (!reason) return;
    setBusy(row.id);
    try {
      await axios.post(`${API}/api/master-admin/partners/commission/${row.id}/reject`, { reason }, { headers });
      notify.success('Commission row rejected');
      await load();
    } catch (e) { notifyApiError(notify, e, 'Reject failed'); }
    finally { setBusy(null); }
  };

  const queuePayout = async (partner_id) => {
    setBusy(`payout-${partner_id}`);
    try {
      const r = await axios.post(`${API}/api/master-admin/partners/payouts/queue`, { partner_id, method: 'manual_csv' }, { headers });
      notify.success(`Payout queued: £${r.data?.total_gbp?.toFixed(2)} (${r.data?.ledger_count} rows)`);
      // Trigger immediate CSV download
      window.open(`${API}/api/master-admin/partners/payouts/${r.data.payout_id}/csv`, '_blank');
      await load();
    } catch (e) { notifyApiError(notify, e, 'Queue payout failed'); }
    finally { setBusy(null); }
  };

  if (loading) return <div className="p-6 text-sm text-zinc-500 inline-flex items-center gap-2"><Loader2 className="animate-spin" size={14} /> Loading partners…</div>;

  // Group ledger queue by partner to make the "queue + export CSV" UX one-click.
  const queueByPartner = queue.reduce((acc, r) => {
    (acc[r.partner_id] ||= { name: r.partner_name, email: r.partner_email, rows: [], total: 0 });
    acc[r.partner_id].rows.push(r);
    acc[r.partner_id].total += r.amount_gbp;
    return acc;
  }, {});

  return (
    <div className="space-y-5" data-testid="admin-partners">
      {/* Summary chips */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Partners" value={summary.partners.total} testId="admin-partners-stat-total" />
          <Stat label="Active referrals" value={summary.referrals.active} testId="admin-partners-stat-refs" />
          <Stat label="Accrued" value={`£${(summary.commission.accrued_gbp || 0).toFixed(2)}`} testId="admin-partners-stat-accrued" />
          <Stat label="Paid lifetime" value={`£${(summary.commission.paid_gbp || 0).toFixed(2)}`} testId="admin-partners-stat-paid" />
        </div>
      )}

      {/* Applications */}
      <Section title="Partner applications" icon={Users} testId="admin-partners-applications">
        {partners.length === 0 ? (
          <p className="text-xs text-zinc-500">No partner applications yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-zinc-500 border-b border-zinc-200 dark:border-zinc-800">
                  <th className="text-left py-2 pr-3">Engineer</th>
                  <th className="text-left py-2 pr-3">Status</th>
                  <th className="text-left py-2 pr-3">Level</th>
                  <th className="text-left py-2 pr-3">Code</th>
                  <th className="text-right py-2 pr-3">Active refs</th>
                  <th className="text-right py-2 pl-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {partners.map((p) => (
                  <tr key={p.id} className="border-b border-zinc-100 dark:border-zinc-900" data-testid={`admin-partner-row-${p.id}`}>
                    <td className="py-2 pr-3">
                      <div className="font-bold text-zinc-900 dark:text-zinc-100">{p.full_name}</div>
                      <div className="text-[11px] text-zinc-500">{p.email}{p.company_name ? ` · ${p.company_name}` : ''}</div>
                    </td>
                    <td className="py-2 pr-3 text-xs"><StatusPill status={p.status} /></td>
                    <td className="py-2 pr-3">
                      <select value={p.level} onChange={(e) => setLevel(p, e.target.value)} disabled={busy === p.id}
                        className="text-xs border border-zinc-200 dark:border-zinc-800 rounded px-1.5 py-1 bg-transparent"
                        data-testid={`admin-partner-level-${p.id}`}>
                        {LEVELS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
                      </select>
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">{p.referral_code}</td>
                    <td className="py-2 pr-3 text-right text-xs">{p.active_referral_count || 0}</td>
                    <td className="py-2 pl-2 text-right">
                      <div className="inline-flex gap-1">
                        {p.status !== 'approved' && (
                          <button onClick={() => approve(p)} disabled={busy === p.id}
                            className="px-2 py-1 text-[10px] font-bold uppercase rounded bg-emerald-600 hover:bg-emerald-700 text-white inline-flex items-center gap-1 disabled:opacity-50"
                            data-testid={`admin-partner-approve-${p.id}`}>
                            <CheckCircle2 size={10} /> Approve
                          </button>
                        )}
                        {p.status !== 'rejected' && (
                          <button onClick={() => reject(p)} disabled={busy === p.id}
                            className="px-2 py-1 text-[10px] font-bold uppercase rounded border border-rose-300 dark:border-rose-700 text-rose-700 dark:text-rose-300 inline-flex items-center gap-1 disabled:opacity-50"
                            data-testid={`admin-partner-reject-${p.id}`}>
                            <X size={10} /> Reject
                          </button>
                        )}
                        {p.status === 'approved' && (
                          <button onClick={() => suspend(p)} disabled={busy === p.id}
                            className="px-2 py-1 text-[10px] font-bold uppercase rounded border border-zinc-300 dark:border-zinc-700 inline-flex items-center gap-1 disabled:opacity-50"
                            data-testid={`admin-partner-suspend-${p.id}`}>
                            Suspend
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* Commission queue */}
      <Section title="Commission queue (awaiting approval)" icon={PoundSterling} testId="admin-partners-commission-queue">
        {queue.length === 0 ? (
          <p className="text-xs text-zinc-500">No accrued commission awaiting approval.</p>
        ) : (
          <div className="space-y-3">
            {Object.entries(queueByPartner).map(([pid, group]) => (
              <div key={pid} className="rounded-lg border border-zinc-200 dark:border-zinc-800 p-3" data-testid={`admin-queue-partner-${pid}`}>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div>
                    <div className="text-sm font-bold">{group.name || '(no name)'}</div>
                    <div className="text-[11px] text-zinc-500">{group.email} · £{group.total.toFixed(2)} pending</div>
                  </div>
                  <button onClick={() => queuePayout(pid)} disabled={busy === `payout-${pid}`}
                    className="px-3 py-1.5 text-xs font-bold rounded-md bg-zinc-900 dark:bg-white dark:text-zinc-900 text-white inline-flex items-center gap-1.5 disabled:opacity-50"
                    data-testid={`admin-queue-payout-${pid}`}>
                    <Download size={11} /> Queue payout + CSV
                  </button>
                </div>
                <table className="w-full text-xs">
                  <tbody>
                    {group.rows.map((row) => (
                      <tr key={row.id} className="border-t border-zinc-100 dark:border-zinc-900" data-testid={`admin-ledger-row-${row.id}`}>
                        <td className="py-1.5 pr-2 text-zinc-500">{new Date(row.created_at).toLocaleDateString()}</td>
                        <td className="py-1.5 pr-2 font-bold">{row.kind === 'signup_reward' ? 'Signup' : 'Recurring'}</td>
                        <td className="py-1.5 pr-2 font-mono">£{row.amount_gbp.toFixed(2)}</td>
                        <td className="py-1.5 text-right">
                          <button onClick={() => approveLedger(row)} disabled={busy === row.id}
                            className="px-1.5 py-0.5 text-[10px] font-bold uppercase rounded bg-emerald-600 text-white inline-flex items-center gap-1 mr-1 disabled:opacity-50"
                            data-testid={`admin-approve-ledger-${row.id}`}>
                            Approve
                          </button>
                          <button onClick={() => rejectLedger(row)} disabled={busy === row.id}
                            className="px-1.5 py-0.5 text-[10px] font-bold uppercase rounded border border-rose-300 text-rose-700 disabled:opacity-50"
                            data-testid={`admin-reject-ledger-${row.id}`}>
                            Reject
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

function Section({ title, icon: Icon, children, testId }) {
  return (
    <section className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4" data-testid={testId}>
      <div className="flex items-center gap-2 mb-3">
        {Icon && <Icon size={14} className="text-purple-500" />}
        <h3 className="text-sm font-extrabold uppercase tracking-wider">{title}</h3>
      </div>
      {children}
    </section>
  );
}

function Stat({ label, value, testId }) {
  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-3" data-testid={testId}>
      <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">{label}</div>
      <div className="text-xl font-black mt-1">{value}</div>
    </div>
  );
}

function StatusPill({ status }) {
  const map = {
    draft:     'bg-zinc-200 text-zinc-700',
    pending:   'bg-amber-100 text-amber-800',
    approved:  'bg-emerald-100 text-emerald-800',
    rejected:  'bg-rose-100 text-rose-800',
    suspended: 'bg-zinc-300 text-zinc-800',
  };
  return <span className={'px-2 py-0.5 rounded-full font-bold uppercase tracking-wider text-[9px] ' + (map[status] || 'bg-zinc-100')}>{status}</span>;
}
