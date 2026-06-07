/**
 * CRMForecast — iter 215de.
 *
 * Per-rep forecast roll-up: pipeline / best_case / commit / closed_won
 * vs quota for the active period (month or quarter). Admins can edit
 * quotas inline; reps see read-only + their own row.
 *
 * Backend: GET /api/crm/forecast?period_type=&period_key=
 *          PUT /api/crm/forecast/quotas
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { formatMoneySync } from '@/utils/localization';
import { toast } from 'sonner';
import { TrendingUp, Target, Save, Megaphone, X, Camera, Award, AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import RepTrackRecord from './RepTrackRecord';
import ForecastLeaderboard from './ForecastLeaderboard';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

function fmtMoney(n) {
  const v = Number(n) || 0;
  return formatMoneySync(v, { maximumFractionDigits: 0 });
}

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function currentQuarter() {
  const d = new Date();
  const q = Math.floor(d.getMonth() / 3) + 1;
  return `${d.getFullYear()}-Q${q}`;
}

function periodOptions(periodType) {
  const out = [];
  const now = new Date();
  if (periodType === 'month') {
    for (let i = -3; i <= 3; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
      out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
    }
  } else {
    const baseYear = now.getFullYear();
    const baseQ = Math.floor(now.getMonth() / 3) + 1;
    for (let i = -2; i <= 2; i++) {
      let q = baseQ + i;
      let y = baseYear;
      while (q < 1) { q += 4; y -= 1; }
      while (q > 4) { q -= 4; y += 1; }
      out.push(`${y}-Q${q}`);
    }
  }
  return out;
}

function AttainmentBar({ pct }) {
  if (pct == null) return <span className="opacity-50 text-xs">—</span>;
  const clamped = Math.max(0, Math.min(150, pct));
  const colour = pct >= 100 ? 'var(--color-success-green, #10b981)' : pct >= 70 ? 'var(--color-warning, #f59e0b)' : 'var(--color-danger-red, #ef4444)';
  return (
    <div className="flex items-center gap-2 min-w-[8rem]">
      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'var(--theme-border, #e5e7eb)' }}>
        <div style={{ width: `${(clamped / 150) * 100}%`, background: colour, height: '100%' }} />
      </div>
      <span className="text-xs font-semibold tabular-nums" style={{ color: colour }}>{Math.round(pct)}%</span>
    </div>
  );
}

function QuotaCell({ row, periodType, periodKey, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(row.quota || 0);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setVal(row.quota || 0); }, [row.quota]);

  const save = async () => {
    setSaving(true);
    try {
      await axios.put(
        `${API}/crm/forecast/quotas`,
        { user_id: row.user_id, period_type: periodType, period_key: periodKey, target_value: Number(val) || 0 },
        auth(),
      );
      toast.success('Quota saved');
      setEditing(false);
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="text-left text-sm font-semibold tabular-nums hover:underline"
        data-testid={`quota-edit-${row.user_id}`}
      >
        {fmtMoney(row.quota)}
      </button>
    );
  }
  return (
    <div className="flex items-center gap-1">
      <input
        type="number"
        value={val}
        onChange={(e) => setVal(e.target.value)}
        autoFocus
        className="w-24 px-2 py-1 rounded border text-sm bg-transparent"
        style={{ borderColor: 'var(--theme-border)' }}
        data-testid={`quota-input-${row.user_id}`}
      />
      <button onClick={save} disabled={saving} className="p-1 rounded text-white" style={{ background: 'var(--color-brand-blue, #1d4ed8)' }} aria-label="Save quota" data-testid={`quota-save-${row.user_id}`}>
        <Save size={12} />
      </button>
    </div>
  );
}

function CommitCallCell({ row, periodType, periodKey, onSaved }) {
  const [open, setOpen] = useState(false);
  const [val, setVal] = useState(row.manager_call || 0);
  const [notes, setNotes] = useState(row.manager_call_notes || '');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setVal(row.manager_call || 0);
    setNotes(row.manager_call_notes || '');
  }, [row.manager_call, row.manager_call_notes]);

  const save = async () => {
    setSaving(true);
    try {
      await axios.put(
        `${API}/crm/forecast/team/call`,
        { user_id: row.user_id, period_type: periodType, period_key: periodKey,
          manager_call_value: Number(val) || 0, notes },
        auth(),
      );
      toast.success('Commit call saved');
      setOpen(false);
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const clear = async () => {
    if (!window.confirm('Clear the manager call for this rep?')) return;
    try {
      await axios.delete(
        `${API}/crm/forecast/team/call?user_id=${encodeURIComponent(row.user_id)}&period_type=${periodType}&period_key=${encodeURIComponent(periodKey)}`,
        auth(),
      );
      toast.success('Cleared');
      onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Clear failed'); }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-left text-sm font-semibold tabular-nums hover:underline inline-flex items-center gap-1"
        style={{ color: row.manager_call > 0 ? 'var(--color-accent-magenta, #d946ef)' : 'var(--theme-text-muted, #6b7280)' }}
        data-testid={`call-edit-${row.user_id}`}
        title={row.manager_call_notes || ''}
      >
        <Megaphone size={11} />
        {row.manager_call > 0 ? fmtMoney(row.manager_call) : 'Set call'}
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-1 min-w-[14rem]">
      <input
        type="number"
        value={val}
        onChange={(e) => setVal(e.target.value)}
        autoFocus
        placeholder="Manager call £"
        className="w-full px-2 py-1 rounded border text-sm bg-transparent"
        style={{ borderColor: 'var(--theme-border)' }}
        data-testid={`call-input-${row.user_id}`}
      />
      <input
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Notes (optional)"
        className="w-full px-2 py-1 rounded border text-xs bg-transparent"
        style={{ borderColor: 'var(--theme-border)' }}
        data-testid={`call-notes-${row.user_id}`}
      />
      <div className="flex gap-1">
        <button onClick={save} disabled={saving} className="px-2 py-1 rounded text-white text-xs font-bold inline-flex items-center gap-1" style={{ background: 'var(--color-brand-blue, #1d4ed8)' }} data-testid={`call-save-${row.user_id}`}>
          <Save size={11} /> {saving ? 'Saving…' : 'Call it'}
        </button>
        {row.manager_call > 0 ? (
          <button onClick={clear} className="px-2 py-1 rounded border text-xs" style={{ borderColor: 'var(--theme-border)' }} data-testid={`call-clear-${row.user_id}`}>
            Clear
          </button>
        ) : null}
        <button onClick={() => setOpen(false)} className="ml-auto p-1 rounded hover:bg-black/5" aria-label="Close" data-testid={`call-cancel-${row.user_id}`}>
          <X size={12} />
        </button>
      </div>
    </div>
  );
}

function AccuracyView({ periodType, periodKey }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [taking, setTaking] = useState(false);
  const [expanded, setExpanded] = useState(null); // user_id of the row whose track record is open

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/crm/forecast/accuracy?period_type=${periodType}&period_key=${periodKey}`, auth());
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load accuracy');
    } finally { setLoading(false); }
  }, [periodType, periodKey]);

  useEffect(() => { load(); }, [load]);

  const takeSnapshot = async () => {
    setTaking(true);
    try {
      const r = await axios.post(`${API}/crm/forecast/snapshots`, { period_type: periodType, period_key: periodKey }, auth());
      toast.success(`Snapshot taken — ${r.data.count} reps frozen`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Snapshot failed');
    } finally { setTaking(false); }
  };

  if (loading) return <p className="text-sm opacity-60" data-testid="accuracy-loading">Loading accuracy report…</p>;

  const rows = data?.rows || [];
  const totals = data?.totals || {};
  const snapshotTaken = !!data?.snapshot_taken;

  return (
    <div className="space-y-5" data-testid="forecast-accuracy">
      <div className="rounded-xl border p-4 flex flex-wrap items-center gap-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
        <Camera size={18} style={{ color: 'var(--color-brand-blue, #1d4ed8)' }} />
        <div className="flex-1 min-w-[16rem]">
          <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>
            {snapshotTaken ? `Snapshot frozen for ${periodKey}` : `No snapshot taken yet for ${periodKey}`}
          </p>
          <p className="text-xs opacity-70">
            Snapshots freeze each rep's pipeline / commit / manager-call so the platform can score forecast accuracy retroactively against actual closed-won.
          </p>
        </div>
        <button
          onClick={takeSnapshot}
          disabled={taking}
          className="px-3 py-2 rounded-lg text-sm font-bold text-white inline-flex items-center gap-1.5"
          style={{ background: 'var(--color-brand-blue, #1d4ed8)' }}
          data-testid="forecast-take-snapshot"
        >
          <Camera size={13} /> {taking ? 'Saving…' : (snapshotTaken ? 'Re-take snapshot' : 'Take snapshot')}
        </button>
      </div>

      {!snapshotTaken ? null : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="accuracy-totals">
            {[
              { label: 'Manager call', value: totals.manager_call },
              { label: 'Commit (snap)', value: totals.commit },
              { label: 'Actual won', value: totals.actual },
              { label: 'Quota', value: totals.quota },
              {
                label: 'Call accuracy',
                value: null,
                pct: totals.call_accuracy_pct,
              },
            ].map((tile) => (
              <div key={tile.label} className="rounded-xl border p-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
                <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">{tile.label}</p>
                {tile.value != null ? (
                  <p className="text-lg font-extrabold tabular-nums mt-1" style={{ color: 'var(--theme-text)' }}>{fmtMoney(tile.value)}</p>
                ) : (
                  <p className="text-lg font-extrabold tabular-nums mt-1" style={{ color: 'var(--color-brand-blue, #1d4ed8)' }}>
                    {tile.pct != null ? `${tile.pct}%` : '—'}
                  </p>
                )}
              </div>
            ))}
          </div>

          <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }} data-testid="accuracy-table">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead style={{ background: 'var(--theme-surface)' }}>
                  <tr className="text-left text-[11px] uppercase tracking-wider opacity-70">
                    <th className="px-3 py-2">Rep</th>
                    <th className="px-3 py-2 text-right">Manager call</th>
                    <th className="px-3 py-2 text-right">Commit (snap)</th>
                    <th className="px-3 py-2 text-right">Actual won</th>
                    <th className="px-3 py-2 text-right">Δ</th>
                    <th className="px-3 py-2">Call accuracy</th>
                    <th className="px-3 py-2">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td colSpan="7" className="px-3 py-6 text-center opacity-60">No rep snapshots in this period.</td></tr>
                  ) : null}
                  {rows.map((r) => {
                    const verdict = r.verdict;
                    const verdictMeta = verdict === 'over'
                      ? { label: 'Sandbagger', icon: Award, colour: 'var(--color-warning, #f59e0b)' }
                      : verdict === 'under'
                      ? { label: 'Missed', icon: AlertTriangle, colour: 'var(--color-danger-red, #ef4444)' }
                      : { label: 'On call', icon: Target, colour: 'var(--color-success-green, #10b981)' };
                    const VIcon = verdictMeta.icon;
                    const isOpen = expanded === r.user_id;
                    const ChevronIcon = isOpen ? ChevronDown : ChevronRight;
                    return (
                      <React.Fragment key={r.user_id}>
                        <tr className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`accuracy-row-${r.user_id}`}>
                          <td className="px-3 py-2 font-semibold" style={{ color: 'var(--theme-text)' }}>
                            <button
                              className="inline-flex items-center gap-1 hover:underline"
                              onClick={() => setExpanded(isOpen ? null : r.user_id)}
                              data-testid={`accuracy-expand-${r.user_id}`}
                            >
                              <ChevronIcon size={12} />
                              {r.owner_name}
                            </button>
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(r.manager_call)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(r.commit_at_snapshot)}</td>
                          <td className="px-3 py-2 text-right tabular-nums" style={{ color: 'var(--color-success-green, #10b981)', fontWeight: 700 }}>{fmtMoney(r.actual_closed_won)}</td>
                          <td className="px-3 py-2 text-right tabular-nums" style={{ color: r.delta >= 0 ? 'var(--color-success-green, #10b981)' : 'var(--color-danger-red, #ef4444)' }}>
                            {r.delta >= 0 ? '+' : ''}{fmtMoney(r.delta)}
                          </td>
                          <td className="px-3 py-2"><AttainmentBar pct={r.call_accuracy_pct} /></td>
                          <td className="px-3 py-2">
                            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-bold" style={{ background: `${verdictMeta.colour}22`, color: verdictMeta.colour }}>
                              <VIcon size={11} /> {verdictMeta.label}
                            </span>
                          </td>
                        </tr>
                        {isOpen ? (
                          <tr style={{ background: 'var(--theme-surface, #f9fafb)' }}>
                            <td colSpan="7" className="px-4 py-4">
                              <RepTrackRecord userId={r.user_id} periods={4} compact />
                            </td>
                          </tr>
                        ) : null}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function CRMForecast() {
  const [periodType, setPeriodType] = useState('quarter');
  const [periodKey, setPeriodKey] = useState(currentQuarter());
  const [view, setView] = useState('all'); // 'all' | 'team' | 'accuracy'
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setPeriodKey(periodType === 'month' ? currentMonth() : currentQuarter());
  }, [periodType]);

  const load = useCallback(async () => {
    if (view === 'accuracy') { setLoading(false); return; } // AccuracyView fetches its own data
    setLoading(true);
    try {
      const path = view === 'team' ? '/crm/forecast/team' : '/crm/forecast';
      const r = await axios.get(`${API}${path}?period_type=${periodType}&period_key=${periodKey}`, auth());
      setData(r.data);
    } catch (e) {
      if (e?.response?.status === 403) {
        toast.error('Manager review is admin/manager only — switching back.');
        setView('all');
      } else {
        toast.error(e?.response?.data?.detail || 'Failed to load forecast');
      }
    } finally { setLoading(false); }
  }, [periodType, periodKey, view]);

  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => data?.rows || [], [data]);
  const totals = data?.totals;
  const periods = useMemo(() => periodOptions(periodType), [periodType]);
  const isTeamView = view === 'team';
  const isAccuracyView = view === 'accuracy';

  return (
    <div className="max-w-6xl mx-auto px-4 py-3 space-y-3" data-testid="crm-forecast-page">
      {/* Iter 216h243 — H1 + description removed (platform-wide
          sub-header sweep). The Forecast tab pill above already
          identifies this page. */}
      <header className="flex flex-wrap items-center justify-end gap-2">
        <div className="flex flex-wrap gap-2">
          <div className="inline-flex rounded-lg border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }} data-testid="forecast-view-toggle">
            <button
              onClick={() => setView('all')}
              className="px-3 py-2 text-xs font-bold"
              style={{
                background: view === 'all' ? 'var(--color-brand-blue, #1d4ed8)' : 'transparent',
                color: view === 'all' ? 'white' : 'var(--theme-text-muted, #6b7280)',
              }}
              data-testid="forecast-view-all"
            >All reps</button>
            <button
              onClick={() => setView('team')}
              className="px-3 py-2 text-xs font-bold"
              style={{
                background: view === 'team' ? 'var(--color-brand-blue, #1d4ed8)' : 'transparent',
                color: view === 'team' ? 'white' : 'var(--theme-text-muted, #6b7280)',
              }}
              data-testid="forecast-view-team"
            >My team</button>
            <button
              onClick={() => setView('accuracy')}
              className="px-3 py-2 text-xs font-bold"
              style={{
                background: view === 'accuracy' ? 'var(--color-brand-blue, #1d4ed8)' : 'transparent',
                color: view === 'accuracy' ? 'white' : 'var(--theme-text-muted, #6b7280)',
              }}
              data-testid="forecast-view-accuracy"
            >Accuracy</button>
          </div>
          <select value={periodType} onChange={(e) => setPeriodType(e.target.value)} className="px-3 py-2 rounded-lg border text-sm bg-transparent" style={{ borderColor: 'var(--theme-border)' }} data-testid="forecast-period-type">
            <option value="month">Monthly</option>
            <option value="quarter">Quarterly</option>
          </select>
          <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)} className="px-3 py-2 rounded-lg border text-sm bg-transparent" style={{ borderColor: 'var(--theme-border)' }} data-testid="forecast-period-key">
            {periods.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </header>

      {isAccuracyView ? (
        <AccuracyView periodType={periodType} periodKey={periodKey} />
      ) : loading ? (
        <p className="text-sm opacity-60" data-testid="forecast-loading">Loading forecast…</p>
      ) : (
        <>
          <div className={`grid grid-cols-2 ${isTeamView ? 'md:grid-cols-6' : 'md:grid-cols-5'} gap-3`} data-testid="forecast-totals">
            {[
              { label: 'Pipeline', value: totals?.pipeline, icon: TrendingUp },
              { label: 'Best case', value: totals?.best_case, icon: TrendingUp },
              { label: 'Commit', value: totals?.commit, icon: Target },
              ...(isTeamView ? [{ label: 'Manager call', value: totals?.manager_call, icon: Megaphone }] : []),
              { label: 'Closed won', value: totals?.closed_won, icon: Target },
              { label: 'Quota', value: totals?.quota, icon: Target },
            ].map((tile) => (
              <div key={tile.label} className="rounded-xl border p-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
                <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">{tile.label}</p>
                <p className="text-lg font-extrabold tabular-nums mt-1" style={{ color: 'var(--theme-text)' }}>{fmtMoney(tile.value)}</p>
              </div>
            ))}
          </div>
          {totals?.attainment_pct != null ? (
            <div className="rounded-xl border p-4 flex items-center gap-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="forecast-org-attainment">
              <p className="text-sm font-bold opacity-80">{isTeamView ? 'Team attainment' : 'Org attainment'}</p>
              <div className="flex-1"><AttainmentBar pct={totals.attainment_pct} /></div>
            </div>
          ) : null}

          {/* Iter 215di — Top callers leaderboard, contextually visible
              alongside the forecast table. Hidden on Accuracy view (where
              the Accuracy table itself is the ranking). */}
          <ForecastLeaderboard periods={4} limit={10} />

          <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }} data-testid="forecast-table">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead style={{ background: 'var(--theme-surface)' }}>
                  <tr className="text-left text-[11px] uppercase tracking-wider opacity-70">
                    <th className="px-3 py-2">Rep</th>
                    <th className="px-3 py-2 text-right">Pipeline</th>
                    <th className="px-3 py-2 text-right">Best case</th>
                    <th className="px-3 py-2 text-right">Commit</th>
                    {isTeamView ? <th className="px-3 py-2">Manager call</th> : null}
                    <th className="px-3 py-2 text-right">Closed won</th>
                    <th className="px-3 py-2 text-right">Quota</th>
                    <th className="px-3 py-2">Attainment</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td colSpan={isTeamView ? 8 : 7} className="px-3 py-6 text-center opacity-60">
                      {isTeamView ? "No reps in your team have deals or quotas this period." : 'No reps with deals or quotas this period.'}
                    </td></tr>
                  ) : null}
                  {rows.map((r) => (
                    <tr key={r.user_id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`forecast-row-${r.user_id}`}>
                      <td className="px-3 py-2 font-semibold" style={{ color: 'var(--theme-text)' }}>{r.owner_name}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(r.pipeline)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(r.best_case)}</td>
                      <td className="px-3 py-2 text-right tabular-nums" style={{ color: 'var(--color-brand-blue, #1d4ed8)', fontWeight: 700 }}>{fmtMoney(r.commit)}</td>
                      {isTeamView ? (
                        <td className="px-3 py-2">
                          <CommitCallCell row={r} periodType={periodType} periodKey={periodKey} onSaved={load} />
                        </td>
                      ) : null}
                      <td className="px-3 py-2 text-right tabular-nums" style={{ color: 'var(--color-success-green, #10b981)', fontWeight: 700 }}>{fmtMoney(r.closed_won)}</td>
                      <td className="px-3 py-2 text-right">
                        <QuotaCell row={r} periodType={periodType} periodKey={periodKey} onSaved={load} />
                      </td>
                      <td className="px-3 py-2"><AttainmentBar pct={r.attainment_pct} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
