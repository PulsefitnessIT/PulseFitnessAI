/**
 * DeskExpenses — Iter 278
 *
 * Finance / manager cockpit for the Expenses subsystem, embedded in the
 * Service Desk under Insights → Expenses. Three sub-views:
 *   • Approvals   — submitted queue: approve / reject / needs-details, plus
 *                   reimburse approved claims; team KPI strip.
 *   • Reports     — grouped totals (category/user/job/country…) + CSV export.
 *   • Settings    — country rules engine (VAT / mileage) + categories.
 *
 * Backend: /api/expenses/{dashboard,reports,export.csv,settings/*} + review.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Loader2, CheckCircle2, XCircle, MessageSquare, Banknote, Download,
  Settings as SettingsIcon, ClipboardCheck, BarChart3, Globe, Tag, Plus, Trash2,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { authConfig } from './authConfig';

const CCY = { GBP: '£', USD: '$', EUR: '€', CAD: 'C$', AUD: 'A$' };
const sym = (c) => CCY[c] || (c ? `${c} ` : '£');
const money = (v, c) => `${sym(c)}${Number(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtDate = (iso) => { try { return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }); } catch { return String(iso || '').slice(0, 10); } };

export default function DeskExpenses({ API: APIprop }) {
  const API = APIprop || (process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api');
  const [sub, setSub] = useState('approvals');

  return (
    <div className="space-y-4" data-testid="desk-expenses">
      <div className="flex gap-2">
        {[
          { id: 'approvals', label: 'Approvals', icon: ClipboardCheck },
          { id: 'reports', label: 'Reports', icon: BarChart3 },
          { id: 'settings', label: 'Settings', icon: SettingsIcon },
        ].map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setSub(id)}
            className={`flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-lg ${sub === id ? 'bg-orange-500 text-white' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300'}`}
            data-testid={`desk-exp-tab-${id}`}><Icon size={15} /> {label}</button>
        ))}
      </div>
      {sub === 'approvals' && <Approvals API={API} />}
      {sub === 'reports' && <Reports API={API} />}
      {sub === 'settings' && <SettingsPanel API={API} />}
    </div>
  );
}

// ── Approvals ────────────────────────────────────────────────────────
function Approvals({ API }) {
  const [team, setTeam] = useState(null);
  const [rows, setRows] = useState([]);
  const [tab, setTab] = useState('submitted,needs_details');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [noteFor, setNoteFor] = useState(null);
  const [note, setNote] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, l] = await Promise.all([
        axios.get(`${API}/expenses/dashboard`, authConfig()),
        axios.get(`${API}/expenses?status=${tab}`, authConfig()),
      ]);
      setTeam(d.data?.team || {}); setRows(l.data?.expenses || []);
    } finally { setLoading(false); }
  }, [API, tab]);
  useEffect(() => { load(); }, [load]);

  const act = async (id, action, n = '') => {
    setBusy(id);
    try {
      await axios.post(`${API}/expenses/${id}/review`, { action, note: n }, authConfig());
      setNoteFor(null); setNote(''); await load();
    } catch (e) { window.alert(e?.response?.data?.detail || 'Action failed'); }
    finally { setBusy(''); }
  };
  const reimburse = async (id) => {
    setBusy(id);
    try { await axios.post(`${API}/expenses/${id}/reimburse`, {}, authConfig()); await load(); }
    catch (e) { window.alert(e?.response?.data?.detail || 'Reimburse failed'); }
    finally { setBusy(''); }
  };

  if (loading) return <Loader />;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="desk-exp-team-kpis">
        <KPI label="Awaiting approval" value={team?.awaiting_approval ?? 0} testid="kpi-awaiting" />
        <KPI label="Needs details" value={team?.needs_details ?? 0} testid="kpi-needs" />
        <KPI label="Approved to pay" value={money(team?.awaiting_reimbursement_total)} testid="kpi-topay" />
        <KPI label="Reclaimable VAT" value={money(team?.vat_total)} testid="kpi-vat" />
      </div>

      <div className="flex gap-2">
        {[
          { id: 'submitted,needs_details', label: 'To review' },
          { id: 'approved', label: 'Approved — to pay' },
        ].map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={tab === t.id ? { color: '#ffffff' } : undefined}
            className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition-colors ${tab === t.id ? 'bg-[var(--color-brand-blue)] border-[var(--color-brand-blue)]' : 'bg-[var(--theme-surface-2)] text-[var(--theme-text)] border-[var(--theme-border)] hover:bg-[var(--theme-hover-bg)]'}`}
            data-testid={`desk-exp-queue-${t.id.split(',')[0]}`}>{t.label}</button>
        ))}
      </div>

      {rows.length === 0 ? (
        <p className="text-sm text-zinc-400 py-10 text-center" data-testid="desk-exp-empty">Nothing here right now.</p>
      ) : (
        <div className="space-y-2">
          {rows.map((e) => (
            <Card key={e.id} className="p-3" data-testid={`desk-exp-row-${e.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-bold text-zinc-900 dark:text-zinc-100 truncate">{e.merchant || e.category_name || 'Expense'}</div>
                  <div className="text-[11px] text-zinc-500">{e.user_name} · {e.reference} · {fmtDate(e.transaction_date)}{e.job_reference ? ` · ${e.job_reference}` : ''}{e.expense_type === 'mileage' ? ' · mileage' : ''}</div>
                  {e.duplicate_flag && <div className="text-[11px] text-amber-600 mt-0.5">⚠ possible duplicate</div>}
                </div>
                <div className="text-right shrink-0">
                  <div className="text-sm font-bold text-zinc-900 dark:text-zinc-100">{money(e.gross_amount, e.currency)}</div>
                  <div className="text-[10px] text-zinc-400">{e.tax_label || 'Tax'} {money(e.tax_amount, e.currency)}</div>
                </div>
              </div>

              {noteFor === e.id ? (
                <div className="mt-2 flex gap-2">
                  <input className="flex-1 text-sm border border-zinc-200 dark:border-zinc-700 rounded-lg px-2 py-1.5 bg-white dark:bg-zinc-900" value={note} onChange={(ev) => setNote(ev.target.value)} placeholder="Message to engineer…" data-testid="desk-exp-note-input" />
                  <button onClick={() => act(e.id, 'needs_details', note)} className="text-xs font-semibold px-3 rounded-lg bg-orange-500 text-white" data-testid="desk-exp-note-send">Send</button>
                  <button onClick={() => { setNoteFor(null); setNote(''); }} className="text-xs px-2 text-zinc-400">Cancel</button>
                </div>
              ) : e.status === 'approved' ? (
                <div className="flex gap-2 mt-2 pt-2 border-t border-zinc-100 dark:border-zinc-800">
                  <Action onClick={() => reimburse(e.id)} busy={busy === e.id} icon={Banknote} label="Mark reimbursed" tone="emerald" testid={`desk-exp-reimburse-${e.id}`} />
                </div>
              ) : (
                <div className="flex gap-2 mt-2 pt-2 border-t border-zinc-100 dark:border-zinc-800">
                  <Action onClick={() => act(e.id, 'approve')} busy={busy === e.id} icon={CheckCircle2} label="Approve" tone="emerald" testid={`desk-exp-approve-${e.id}`} />
                  <Action onClick={() => { setNoteFor(e.id); setNote(''); }} icon={MessageSquare} label="Query" tone="amber" testid={`desk-exp-query-${e.id}`} />
                  <Action onClick={() => act(e.id, 'reject')} busy={busy === e.id} icon={XCircle} label="Reject" tone="red" testid={`desk-exp-reject-${e.id}`} />
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Reports ──────────────────────────────────────────────────────────
function Reports({ API }) {
  const [groupBy, setGroupBy] = useState('category');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await axios.get(`${API}/expenses/reports?group_by=${groupBy}`, authConfig()); setData(data); }
    finally { setLoading(false); }
  }, [API, groupBy]);
  useEffect(() => { load(); }, [load]);

  const exportCsv = async () => {
    setExporting(true);
    try {
      const res = await axios.get(`${API}/expenses/export.csv?status=approved`, { ...authConfig(), responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a'); a.href = url; a.download = 'expenses-export.csv'; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { window.alert(e?.response?.data?.detail || 'Export failed (finance access required)'); }
    finally { setExporting(false); }
  };

  const GROUPS = ['category', 'user', 'job', 'customer', 'country', 'status', 'currency'];
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex gap-1.5 flex-wrap">
          {GROUPS.map((g) => (
            <button key={g} onClick={() => setGroupBy(g)}
              className={`text-xs font-semibold px-2.5 py-1 rounded-full capitalize ${groupBy === g ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300'}`}
              data-testid={`desk-exp-group-${g}`}>{g}</button>
          ))}
        </div>
        <button onClick={exportCsv} disabled={exporting} className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-emerald-600 text-white" data-testid="desk-exp-export">
          {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} Export approved (CSV)
        </button>
      </div>

      {loading ? <Loader /> : (
        <Card className="p-0 overflow-hidden" data-testid="desk-exp-report-table">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 dark:bg-zinc-800 text-[11px] uppercase tracking-wide text-zinc-500">
              <tr><th className="text-left px-4 py-2">{groupBy}</th><th className="text-right px-4 py-2">Count</th><th className="text-right px-4 py-2">Tax</th><th className="text-right px-4 py-2">Gross</th></tr>
            </thead>
            <tbody>
              {(data?.rows || []).map((r, i) => (
                <tr key={i} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="px-4 py-2 text-zinc-800 dark:text-zinc-200">{r.label}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{r.count}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-zinc-500">{money(r.tax)}</td>
                  <td className="px-4 py-2 text-right tabular-nums font-semibold">{money(r.gross)}</td>
                </tr>
              ))}
              {(data?.rows || []).length === 0 && <tr><td colSpan={4} className="px-4 py-8 text-center text-zinc-400">No data for this range.</td></tr>}
            </tbody>
            {data?.totals && (
              <tfoot className="bg-zinc-50 dark:bg-zinc-800 font-bold">
                <tr><td className="px-4 py-2">Total</td><td className="px-4 py-2 text-right tabular-nums">{data.totals.count}</td><td className="px-4 py-2 text-right tabular-nums">{money(data.totals.tax)}</td><td className="px-4 py-2 text-right tabular-nums">{money(data.totals.gross)}</td></tr>
              </tfoot>
            )}
          </table>
        </Card>
      )}
    </div>
  );
}

// ── Settings (country rules + categories) ─────────────────────────────
function SettingsPanel({ API }) {
  const [rules, setRules] = useState([]);
  const [cats, setCats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newCat, setNewCat] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, c] = await Promise.all([
        axios.get(`${API}/expenses/settings/country-rules`, authConfig()),
        axios.get(`${API}/expenses/settings/categories`, authConfig()),
      ]);
      setRules(r.data?.country_rules || []); setCats(c.data?.categories || []);
    } finally { setLoading(false); }
  }, [API]);
  useEffect(() => { load(); }, [load]);

  const saveRule = async (rule, patch) => {
    const body = { ...rule, ...patch };
    try { await axios.put(`${API}/expenses/settings/country-rules/${rule.id}`, body, authConfig()); load(); }
    catch (e) { window.alert(e?.response?.data?.detail || 'Save failed'); }
  };
  const addCat = async () => {
    if (!newCat.trim()) return;
    try { await axios.post(`${API}/expenses/settings/categories`, { name: newCat.trim() }, authConfig()); setNewCat(''); load(); }
    catch (e) { window.alert(e?.response?.data?.detail || 'Add failed'); }
  };
  const toggleCat = async (c) => {
    try { await axios.put(`${API}/expenses/settings/categories/${c.id}`, { ...c, active: !c.active }, authConfig()); load(); }
    catch (e) { window.alert(e?.response?.data?.detail || 'Update failed'); }
  };
  const delCat = async (c) => {
    try { await axios.delete(`${API}/expenses/settings/categories/${c.id}`, authConfig()); load(); }
    catch (e) { window.alert(e?.response?.data?.detail || 'Delete failed'); }
  };
  const setDefault = async (rule) => saveRule(rule, { is_default: true });

  if (loading) return <Loader />;
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <Card className="p-4" data-testid="desk-exp-rules">
        <h3 className="flex items-center gap-2 text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-3"><Globe size={16} /> Country rules</h3>
        <div className="space-y-3">
          {rules.map((r) => (
            <div key={r.id} className="border border-zinc-100 dark:border-zinc-800 rounded-lg p-3" data-testid={`desk-exp-rule-${r.country_code}`}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{r.country_name} · {r.currency} {sym(r.currency)}</span>
                {r.is_default ? <span className="text-[10px] font-bold text-emerald-600">DEFAULT</span>
                  : <button onClick={() => setDefault(r)} className="text-[10px] font-semibold text-orange-600" data-testid={`desk-exp-rule-default-${r.country_code}`}>Set default</button>}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <label className="block"><span className="text-zinc-400">{r.tax_label} default %</span>
                  <input type="number" defaultValue={r.default_tax_rate} onBlur={(e) => saveRule(r, { default_tax_rate: parseFloat(e.target.value) || 0 })}
                    className="w-full mt-0.5 border border-zinc-200 dark:border-zinc-700 rounded px-2 py-1 bg-white dark:bg-zinc-900" data-testid={`desk-exp-rule-tax-${r.country_code}`} /></label>
                <label className="block"><span className="text-zinc-400">Approval threshold</span>
                  <input type="number" defaultValue={r.approval_threshold} onBlur={(e) => saveRule(r, { approval_threshold: parseFloat(e.target.value) || 0 })}
                    className="w-full mt-0.5 border border-zinc-200 dark:border-zinc-700 rounded px-2 py-1 bg-white dark:bg-zinc-900" data-testid={`desk-exp-rule-approval-${r.country_code}`} /></label>
              </div>
              <div className="mt-2 text-[11px] text-zinc-500">
                Mileage ({r.mileage_unit}): {(r.mileage_rates || []).map((m) => `${m.label} ${m.rate}`).join(' · ') || '—'}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-4" data-testid="desk-exp-categories">
        <h3 className="flex items-center gap-2 text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-3"><Tag size={16} /> Categories</h3>
        <div className="flex gap-2 mb-3">
          <input value={newCat} onChange={(e) => setNewCat(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addCat()} placeholder="New category" className="flex-1 text-sm border border-zinc-200 dark:border-zinc-700 rounded-lg px-2 py-1.5 bg-white dark:bg-zinc-900" data-testid="desk-exp-cat-input" />
          <button onClick={addCat} className="flex items-center gap-1 text-xs font-semibold px-3 rounded-lg bg-orange-500 text-white" data-testid="desk-exp-cat-add"><Plus size={14} /> Add</button>
        </div>
        <div className="space-y-1 max-h-[420px] overflow-y-auto">
          {cats.map((c) => (
            <div key={c.id} className={`flex items-center justify-between px-2 py-1.5 rounded-lg ${c.active ? '' : 'opacity-40'}`} data-testid={`desk-exp-cat-${c.id}`}>
              <span className="text-sm text-zinc-800 dark:text-zinc-200">{c.name}{c.billable_to_customer ? ' · billable' : ''}{c.receipt_required ? ' · receipt' : ''}</span>
              <div className="flex items-center gap-2">
                <button onClick={() => toggleCat(c)} className="text-[11px] font-semibold text-zinc-500">{c.active ? 'Disable' : 'Enable'}</button>
                <button onClick={() => delCat(c)} className="text-zinc-300 hover:text-red-500"><Trash2 size={13} /></button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ── shared bits ───────────────────────────────────────────────────────
const Loader = () => <div className="flex justify-center py-16 text-zinc-400"><Loader2 className="animate-spin" /></div>;
function KPI({ label, value, testid }) {
  return (
    <Card className="p-3" data-testid={testid}>
      <div className="text-xl font-bold text-zinc-900 dark:text-zinc-100 tabular-nums">{value}</div>
      <div className="text-[11px] text-zinc-500 mt-0.5">{label}</div>
    </Card>
  );
}
function Action({ onClick, busy, icon: Icon, label, tone, testid }) {
  const tones = { emerald: 'text-emerald-600', amber: 'text-amber-600', red: 'text-red-600' };
  return (
    <button onClick={onClick} disabled={busy} className={`flex-1 flex items-center justify-center gap-1.5 text-xs font-semibold py-1.5 ${tones[tone] || 'text-zinc-600'}`} data-testid={testid}>
      {busy ? <Loader2 size={13} className="animate-spin" /> : <Icon size={14} />} {label}
    </button>
  );
}
