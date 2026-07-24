/**
 * Phase S6 — AI Workforce Automation tab.
 *
 * Combines three manager-facing capabilities behind a single tab:
 *   • Rota Builder    — generate weekly suggestions via Claude/heuristic
 *                       and apply (bulk insert)
 *   • Absence Risk    — heuristic per-staff risk leaderboard
 *   • Sage Payroll    — date-range CSV download in Sage 50 format
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  Sparkles, Wand2, Loader2, Download, CheckCircle2, RefreshCw, ShieldAlert, FileSpreadsheet,
} from 'lucide-react';
import { useLocalization, formatMoneySync } from '@/utils/localization';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SUB_TABS = [
  { id: 'rota',     labelKey: 'staffing.ai_tab_rota',    labelDefault: 'Rota Builder',  icon: Wand2 },
  { id: 'absence',  labelKey: 'staffing.ai_tab_absence', labelDefault: 'Absence Risk',  icon: ShieldAlert },
  { id: 'sage',     labelKey: 'staffing.ai_tab_sage',    labelDefault: 'Sage Payroll',  icon: FileSpreadsheet },
];

// ───────────────────────── Rota Builder ──────────────────────────

function nextMonday(iso) {
  const d = iso ? new Date(iso) : new Date();
  d.setHours(0, 0, 0, 0);
  const day = d.getDay() || 7;            // Sun=7
  d.setDate(d.getDate() + (8 - day));     // jump to next Mon
  return d.toISOString().slice(0, 10);
}

function RotaBuilderPanel({ headers }) {
  const { t } = useTranslation();
  const [weekStart, setWeekStart] = useState(() => nextMonday(null));
  const [maxHours, setMaxHours]   = useState(40);
  const [notes, setNotes]         = useState('');
  const [busy, setBusy]           = useState(false);
  const [applied, setApplied]     = useState(false);
  const [err, setErr]             = useState('');
  const [result, setResult]       = useState(null);
  const [overwrite, setOverwrite] = useState(true);

  const generate = async () => {
    setBusy(true); setErr(''); setResult(null); setApplied(false);
    try {
      const { data } = await axios.post(
        `${API}/staffing/ai/rota/suggest`,
        { week_start: weekStart, max_hours_per_staff_week: maxHours, notes: notes || null },
        { headers, timeout: 120000 },
      );
      setResult(data);
    } catch (e) {
      setErr(e.response?.data?.detail || e.message || t('staffing.ai_rota_gen_failed', 'Failed to generate rota'));
    }
    setBusy(false);
  };

  const apply = async () => {
    if (!result?.suggestions?.length) return;
    const warn = overwrite ? ' ' + t('staffing.ai_rota_replace_warn', 'This will REPLACE all shifts in that week.') : '';
    if (!window.confirm(`${t('staffing.ai_rota_apply_confirm', 'Apply')} ${result.suggestions.length} ${t('staffing.ai_rota_shifts_to', 'shifts to')} ${weekStart}?${warn}`)) return;
    setBusy(true); setErr('');
    try {
      const { data } = await axios.post(
        `${API}/staffing/ai/rota/apply`,
        { week_start: weekStart, shifts: result.suggestions, overwrite_existing: overwrite },
        { headers },
      );
      setApplied(true);
      window.alert(`${t('staffing.ai_rota_created', 'Created')} ${data.created} ${t('staffing.ai_rota_shifts', 'shifts')}.`);
    } catch (e) {
      setErr(e.response?.data?.detail || e.message || t('staffing.ai_rota_apply_failed', 'Apply failed'));
    }
    setBusy(false);
  };

  return (
    <div className="space-y-4" data-testid="rota-builder-panel">
      <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
        <div className="flex items-center gap-2 mb-3">
          <Wand2 size={14} style={{ color: 'var(--color-brand-cyan)' }} />
          <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.ai_rota_builder', 'Rota Builder · Claude Sonnet 4.5')}</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2 mb-2">
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_week_starting', 'Week starting (Mon)')}</label>
            <input type="date" value={weekStart} onChange={(e) => setWeekStart(e.target.value)}
              className="w-full h-9 rounded-md bg-transparent border px-2 text-sm mt-1"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="rota-week-start" />
          </div>
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_max_hours', 'Max hours / staff')}</label>
            <input type="number" min="0" step="1" value={maxHours} onChange={(e) => setMaxHours(parseFloat(e.target.value) || 0)}
              className="w-full h-9 rounded-md bg-transparent border px-2 text-sm mt-1"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="rota-max-hours" />
          </div>
          <div className="md:col-span-2">
            <label className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_notes', 'Notes for AI')}</label>
            <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder={t('staffing.ai_notes_ph', 'e.g. opening early Monday, double-cover Saturday morning')}
              className="w-full h-9 rounded-md bg-transparent border px-2 text-sm mt-1"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="rota-notes" />
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button type="button" onClick={generate} disabled={busy}
            className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-60"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }}
            data-testid="rota-generate-btn">
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            {busy ? t('staffing.ai_generating', 'Generating…') : t('staffing.ai_generate_rota', 'Generate rota')}
          </button>
          {result && (
            <>
              <label className="text-xs inline-flex items-center gap-1.5" style={{ color: 'var(--theme-text-muted)' }} data-testid="rota-overwrite-toggle">
                <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
                {t('staffing.ai_overwrite_existing', 'Overwrite existing shifts that week')}
              </label>
              <button type="button" onClick={apply} disabled={busy || applied || !result.suggestions?.length}
                className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5 border disabled:opacity-60"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="rota-apply-btn">
                {applied ? <CheckCircle2 size={12} /> : <RefreshCw size={12} />}
                {applied ? t('staffing.ai_applied', 'Applied') : `${t('staffing.ai_rota_apply_confirm', 'Apply')} ${result.suggestions.length} ${t('staffing.ai_rota_shifts', 'shifts')}`}
              </button>
            </>
          )}
        </div>
        {err && <p className="text-xs mt-2" style={{ color: '#EF4444' }} data-testid="rota-error">{err}</p>}
      </div>

      {result && (
        <div className="space-y-3" data-testid="rota-result">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Stat label={t('staffing.ai_engine', 'Engine')}        value={result.engine === 'claude-sonnet-4-5' ? t('staffing.ai_engine_claude', 'AI · Claude') : t('staffing.ai_engine_heuristic', 'Heuristic')} testId="rota-engine" />
            <Stat label={t('staffing.ai_shifts_planned', 'Shifts planned')} value={result.suggestions?.length || 0}                                      testId="rota-shift-count" />
            <Stat label={t('staffing.ai_people_covered', 'People covered')} value={Object.keys(result.hours_per_staff || {}).length}                     testId="rota-people-count" />
            <Stat label={t('staffing.ai_total_cost', 'Total cost')}     value={formatMoneySync(result.cost_total || 0)}                            testId="rota-total-cost" />
          </div>
          <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
            <table className="w-full text-xs">
              <thead>
                <tr style={{ background: 'var(--theme-surface-2)' }}>
                  <th className="text-left p-2 font-bold" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_col_date', 'Date')}</th>
                  <th className="text-left p-2 font-bold" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_col_staff', 'Staff')}</th>
                  <th className="text-left p-2 font-bold" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_col_role', 'Role')}</th>
                  <th className="text-left p-2 font-bold" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_col_hours', 'Hours')}</th>
                  <th className="text-left p-2 font-bold" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_col_reason', 'Reason')}</th>
                </tr>
              </thead>
              <tbody>
                {result.suggestions.map((s, i) => {
                  const hours = (() => {
                    const [sh, sm] = s.start_time.split(':').map(Number);
                    const [eh, em] = s.end_time.split(':').map(Number);
                    return Math.max(0, ((eh * 60 + em) - (sh * 60 + sm)) / 60);
                  })();
                  const staffEntry = (result.cost_per_staff || []).find((c) => c.staff_id === s.staff_id);
                  return (
                    <tr key={i} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`rota-row-${i}`}>
                      <td className="p-2 whitespace-nowrap" style={{ color: 'var(--theme-text)' }}>{s.date}</td>
                      <td className="p-2 font-bold" style={{ color: 'var(--theme-text)' }}>{staffEntry?.name || s.staff_id.slice(0, 8)}</td>
                      <td className="p-2 uppercase tracking-wide text-[10px]" style={{ color: 'var(--color-brand-cyan)' }}>{s.role}</td>
                      <td className="p-2 whitespace-nowrap" style={{ color: 'var(--theme-text-muted)' }}>{s.start_time}–{s.end_time} ({hours.toFixed(1)}h)</td>
                      <td className="p-2" style={{ color: 'var(--theme-text-muted)' }}>{s.reason}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, testId }) {
  return (
    <div className="rounded-xl border p-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid={testId}>
      <p className="text-[10px] uppercase tracking-wider font-bold" style={{ color: 'var(--theme-text-muted)' }}>{label}</p>
      <p className="text-base font-bold pulse-font-heading mt-1" style={{ color: 'var(--theme-text)' }}>{value}</p>
    </div>
  );
}

// ───────────────────────── Absence Risk ──────────────────────────

function AbsenceRiskPanel({ headers }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [horizon, setHorizon] = useState(14);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/staffing/ai/absence-risk`, { headers, params: { horizon_days: horizon } });
      setData(data);
    } catch { /* noop */ }
    setLoading(false);
  }, [headers, horizon]);
  useEffect(() => { load(); }, [load]);

  const tint = (band) => band === 'high' ? '#EF4444' : (band === 'medium' ? '#F59E0B' : '#10B981');

  return (
    <div className="space-y-3" data-testid="absence-risk-panel">
      <div className="flex items-center gap-3 flex-wrap">
        <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.ai_absence_title', 'Absence Prediction · Heuristic')}</p>
        <div className="ml-auto flex items-center gap-2">
          <label className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_horizon', 'Horizon')}</label>
          <select value={horizon} onChange={(e) => setHorizon(parseInt(e.target.value, 10))}
            className="h-8 rounded-md bg-transparent border px-2 text-xs"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="absence-horizon">
            <option value={7}>{t('staffing.ai_next_7', 'Next 7 days')}</option>
            <option value={14}>{t('staffing.ai_next_14', 'Next 14 days')}</option>
            <option value={30}>{t('staffing.ai_next_30', 'Next 30 days')}</option>
          </select>
        </div>
      </div>
      {loading && <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_loading', 'Loading…')}</p>}
      {!loading && data && (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Stat label={t('staffing.ai_high_risk', 'High risk')}   value={data.summary.high}   testId="absence-high" />
            <Stat label={t('staffing.ai_medium_risk', 'Medium risk')} value={data.summary.medium} testId="absence-medium" />
            <Stat label={t('staffing.ai_low_risk', 'Low risk')}    value={data.summary.low}    testId="absence-low" />
          </div>
          <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
            {data.rows.length === 0 ? (
              <p className="p-4 text-xs text-center" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_no_active_staff', 'No active staff yet.')}</p>
            ) : data.rows.map((r) => (
              <div key={r.staff_id} className="border-b p-3 flex items-start gap-3" style={{ borderColor: 'var(--theme-border)' }} data-testid={`absence-row-${r.staff_id}`}>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{r.full_name}</p>
                  <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{r.primary_role}</p>
                  <ul className="text-[11px] mt-1 list-disc pl-4 space-y-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                    {r.reasons.map((rs, i) => <li key={i}>{rs}</li>)}
                  </ul>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-2xl font-bold tabular-nums" style={{ color: tint(r.band) }} data-testid={`absence-score-${r.staff_id}`}>{r.score}</p>
                  <p className="text-[10px] uppercase font-bold tracking-wider" style={{ color: tint(r.band) }}>{r.band}</p>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ───────────────────────── Sage Payroll ──────────────────────────

function SagePayrollPanel({ headers }) {
  const { t } = useTranslation();
  const [from, setFrom] = useState(() => { const d = new Date(); d.setDate(1); return d.toISOString().slice(0, 10); });
  const [to, setTo]     = useState(() => new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);

  const download = async () => {
    setBusy(true);
    try {
      const token = headers.Authorization?.split(' ')[1];
      const r = await fetch(`${API}/staffing/ai/payroll/sage.csv?date_from=${from}&date_to=${to}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) {
        const txt = await r.text();
        throw new Error(txt || t('staffing.ai_download_failed', 'Download failed'));
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `sage-payroll-${from}-to-${to}.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      window.alert(e.message || t('staffing.ai_download_failed', 'Download failed'));
    }
    setBusy(false);
  };

  return (
    <div className="space-y-3" data-testid="sage-payroll-panel">
      <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
        <div className="flex items-center gap-2 mb-3">
          <FileSpreadsheet size={14} style={{ color: 'var(--color-brand-cyan)' }} />
          <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.ai_sage_title', 'Sage 50 Payroll · Hours and Rates import')}</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-3">
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_from', 'From')}</label>
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)}
              className="w-full h-9 rounded-md bg-transparent border px-2 text-sm mt-1"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="sage-from" />
          </div>
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ai_to', 'To')}</label>
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)}
              className="w-full h-9 rounded-md bg-transparent border px-2 text-sm mt-1"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="sage-to" />
          </div>
          <div className="flex items-end">
            <button type="button" onClick={download} disabled={busy}
              className="h-9 w-full rounded-full px-4 text-xs font-bold inline-flex items-center justify-center gap-1.5 disabled:opacity-60"
              style={{ background: 'var(--color-brand-cyan)', color: '#001219' }}
              data-testid="sage-download-btn">
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
              {t('staffing.ai_download_csv', 'Download CSV')}
            </button>
          </div>
        </div>
        <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
          {t('staffing.ai_sage_note', 'Columns: Reference · Surname · Forenames · NI Number · Payment Number · Hours · Rate · Amount. Aggregates non-cancelled shifts; pulls NI number from Phase S5 HR profile.')}
        </p>
      </div>
    </div>
  );
}

// ───────────────────────── Hub ───────────────────────────────────

export default function AIWorkforceTab({ headers }) {
  const { t } = useTranslation();
  useLocalization();  // warm currency cache
  const [sub, setSub] = useState(() => localStorage.getItem('staffing.ai.sub') || 'rota');
  useEffect(() => { localStorage.setItem('staffing.ai.sub', sub); }, [sub]);
  return (
    <div className="space-y-3" data-testid="ai-workforce-tab">
      <div className="inline-flex rounded-full border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
        {SUB_TABS.map((st) => {
          const Icon = st.icon;
          const on = sub === st.id;
          return (
            <button key={st.id} type="button" onClick={() => setSub(st.id)}
              className="h-9 px-4 text-xs font-bold inline-flex items-center gap-1.5"
              style={{
                background: on ? 'var(--color-brand-cyan)' : 'transparent',
                color: on ? '#001219' : 'var(--theme-text-muted)',
                borderLeft: st.id !== SUB_TABS[0].id ? '1px solid var(--theme-border)' : 'none',
              }}
              data-testid={`ai-sub-${st.id}`}>
              <Icon size={12} /> {t(st.labelKey, st.labelDefault)}
            </button>
          );
        })}
      </div>
      {sub === 'rota'    && <RotaBuilderPanel headers={headers} />}
      {sub === 'absence' && <AbsenceRiskPanel headers={headers} />}
      {sub === 'sage'    && <SagePayrollPanel headers={headers} />}
    </div>
  );
}
