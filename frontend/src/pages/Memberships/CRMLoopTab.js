/**
 * Pulse Fitness Memberships → CRM Loop (Phase 6).
 *
 * Closes the loop between Memberships behaviour and Marketing/CRM
 * outbound. Operator sees:
 *   • Live counts of signals + auto-sends in the last N days
 *   • Toggleable rules with cooldown editor
 *   • Recent signals + recent sends timeline
 *   • One-tap "Scan now" (forces a detector pass for this org)
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Activity, Send, RefreshCw, Loader2, ToggleLeft, ToggleRight,
  ChevronDown, AlertTriangle, Sparkles, Heart, UserMinus,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const KIND_META = {
  missed_class:    { labelKey: 'crml_kind_missed_class',    label: 'Missed class',     icon: UserMinus,     tone: 'amber'   },
  inactive_30d:    { labelKey: 'crml_kind_inactive_30d',    label: 'Inactive 30d',     icon: AlertTriangle, tone: 'red'     },
  low_attendance:  { labelKey: 'crml_kind_low_attendance',  label: 'Low attendance',   icon: Activity,      tone: 'sky'     },
  high_engagement: { labelKey: 'crml_kind_high_engagement', label: 'High engagement',  icon: Sparkles,      tone: 'emerald' },
};


export default function CRMLoopTab({ API, headers }) {
  const { t } = useTranslation();
  const [view, setView] = useState('dashboard');
  return (
    <div data-testid="mbr-crmloop-tab">
      <div className="flex gap-2 overflow-x-auto -mx-1 px-1 pb-2 mb-4">
        {[
          { id: 'dashboard', label: t('memberships_console.crml_dashboard', 'Dashboard') },
          { id: 'rules',     label: t('memberships_console.crml_rules', 'Rules') },
          { id: 'signals',   label: t('memberships_console.crml_signals', 'Signals') },
          { id: 'sends',     label: t('memberships_console.crml_sends', 'Sends') },
        ].map((tab) => (
          <button key={tab.id} onClick={() => setView(tab.id)}
            className={`flex-shrink-0 px-3 py-2 rounded-md text-xs font-extrabold border transition ${
              view === tab.id
                ? 'bg-violet-500 text-white border-violet-500'
                : 'bg-transparent border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]'
            }`}
            data-testid={`mbr-crmloop-tab-${tab.id}`}>
            {tab.label}
          </button>
        ))}
      </div>

      {view === 'dashboard' && <DashboardView API={API} headers={headers} />}
      {view === 'rules'     && <RulesView     API={API} headers={headers} />}
      {view === 'signals'   && <SignalsView   API={API} headers={headers} />}
      {view === 'sends'     && <SendsView     API={API} headers={headers} />}
    </div>
  );
}


function DashboardView({ API, headers }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);

  const load = () => {
    setLoading(true);
    axios.get(`${API}/memberships/crm-loop/dashboard?days=30`, { headers })
      .then((r) => setData(r.data))
      .catch(() => notify.error(t('memberships_console.crml_dash_fail', 'Failed to load CRM dashboard')))
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  useEffect(() => { load();   }, []);

  const scan = async () => {
    setScanning(true);
    try {
      const r = await axios.post(`${API}/memberships/crm-loop/scan`, {}, { headers });
      notify.success(t('memberships_console.crml_scanned', 'Scanned {{members}} members · fired {{signals}} signals', { members: r.data.members_scanned, signals: r.data.signals_fired }));
      load();
    } catch (e) {
      notifyApiError(notify, e, t('memberships_console.crml_scan_fail', 'Scan failed'));
    }
    setScanning(false);
  };

  if (loading) return <Spinner />;
  if (!data) return null;
  const lastRun = data.last_run;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {Object.entries(data.by_kind).map(([kind, stats]) => (
          <KindStat key={kind} kind={kind} stats={stats} />
        ))}
      </div>

      <div className="rounded-xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-4 flex items-start gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <p className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)]">{t('memberships_console.crml_last_cycle', 'Last cycle')}</p>
          {lastRun ? (
            <p className="text-sm mt-0.5">
              {new Date(lastRun.started_at).toLocaleString()} — {t('memberships_console.crml_last_cycle_stats', 'scanned {{scanned}}, fired {{fired}} across {{orgs}} studio(s)', { scanned: lastRun.members_scanned, fired: lastRun.signals_fired, orgs: lastRun.orgs })}
            </p>
          ) : (
            <p className="text-sm text-[color:var(--theme-text-muted)] mt-0.5">{t('memberships_console.crml_no_cycle', 'No automated cycle has run yet — try Scan now.')}</p>
          )}
        </div>
        <button onClick={scan} disabled={scanning}
          className="px-3 py-2 rounded-md font-extrabold text-xs flex items-center gap-1.5 disabled:opacity-50"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid="mbr-crmloop-scan">
          {scanning ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          {t('memberships_console.crml_scan_now', 'Scan now')}
        </button>
      </div>
    </div>
  );
}


function KindStat({ kind, stats }) {
  const { t } = useTranslation();
  const meta = KIND_META[kind] || { label: kind, icon: Activity, tone: 'zinc' };
  const Icon = meta.icon;
  const tones = {
    amber:   'border-amber-500/30 bg-amber-500/5 text-amber-500',
    red:     'border-red-500/30 bg-red-500/5 text-red-400',
    sky:     'border-sky-500/30 bg-sky-500/5 text-sky-500',
    emerald: 'border-emerald-500/30 bg-emerald-500/5 text-emerald-500',
    zinc:    'border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]',
  };
  return (
    <div className={`rounded-lg border p-3 ${tones[meta.tone]}`} data-testid={`mbr-crmloop-stat-${kind}`}>
      <p className="text-[9px] uppercase tracking-wider font-bold flex items-center gap-1">
        <Icon size={9} /> {meta.labelKey ? t(`memberships_console.${meta.labelKey}`, meta.label) : meta.label}
      </p>
      <p className="text-xl font-extrabold mt-0.5">{stats.signals}</p>
      <p className="text-[10px] text-[color:var(--theme-text-muted)] mt-0.5">
        {t('memberships_console.crml_n_sent', '{{n}} sent', { n: stats.sends })}
        {stats.last_sent_at && ` · ${new Date(stats.last_sent_at).toLocaleDateString()}`}
      </p>
    </div>
  );
}


function RulesView({ API, headers }) {
  const { t } = useTranslation();
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  const load = () => {
    setLoading(true);
    axios.get(`${API}/memberships/crm-loop/rules`, { headers })
      .then((r) => setRules(r.data.rules || []))
      .catch(() => notify.error(t('memberships_console.crml_rules_fail', 'Rules failed')))
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  useEffect(() => { load();   }, []);

  const update = async (kind, patch) => {
    setBusy(kind);
    try {
      const r = await axios.put(`${API}/memberships/crm-loop/rules/${kind}`, patch, { headers });
      setRules((prev) => prev.map((p) => p.kind === kind ? r.data.rule : p));
      notify.success(t('memberships_console.crml_saved', 'Saved'));
    } catch (e) {
      notifyApiError(notify, e, t('memberships_console.crml_failed', 'Failed'));
    }
    setBusy(null);
  };

  if (loading) return <Spinner />;
  return (
    <div className="space-y-3">
      {rules.map((r) => {
        const meta = KIND_META[r.kind] || {};
        const Icon = meta.icon || Activity;
        const Tog = r.enabled ? ToggleRight : ToggleLeft;
        return (
          <div key={r.kind}
            className="rounded-xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-4"
            data-testid={`mbr-crmloop-rule-${r.kind}`}>
            <div className="flex items-start gap-3 flex-wrap">
              <div className={`flex-shrink-0 w-10 h-10 rounded-md grid place-items-center ${
                meta.tone === 'amber' ? 'bg-amber-500/15 text-amber-500'
                : meta.tone === 'red' ? 'bg-red-500/15 text-red-400'
                : meta.tone === 'sky' ? 'bg-sky-500/15 text-sky-500'
                : 'bg-emerald-500/15 text-emerald-500'
              }`}>
                <Icon size={14} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-extrabold">{r.label}</p>
                <p className="text-[11px] text-[color:var(--theme-text-muted)] mt-0.5 leading-relaxed">{r.description}</p>
              </div>
              <button onClick={() => update(r.kind, { enabled: !r.enabled })}
                disabled={busy === r.kind}
                className={`p-1.5 rounded transition ${r.enabled ? 'text-emerald-500' : 'text-zinc-500'}`}
                title={r.enabled ? t('memberships_console.crml_disable_rule', 'Disable rule') : t('memberships_console.crml_enable_rule', 'Enable rule')}
                data-testid={`mbr-crmloop-rule-toggle-${r.kind}`}>
                <Tog size={28} />
              </button>
            </div>
            <div className="mt-3 flex items-center gap-2 flex-wrap text-[11px]">
              <span className="text-[color:var(--theme-text-muted)] uppercase tracking-wider font-bold text-[9px]">{t('memberships_console.crml_cooldown', 'Cooldown')}</span>
              <CooldownEditor value={r.cooldown_hours}
                onChange={(v) => update(r.kind, { cooldown_hours: v })} />
              <span className="text-[color:var(--theme-text-muted)]">{t('memberships_console.crml_between_sends', 'between sends to the same member')}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}


function CooldownEditor({ value, onChange }) {
  const presets = [24, 72, 168, 30 * 24];
  const [open, setOpen] = useState(false);
  const fmt = (h) => h >= 24 ? `${Math.round(h / 24)}d` : `${h}h`;
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)}
        className="px-2 py-1 rounded border border-[color:var(--theme-border)] flex items-center gap-1 font-bold"
        data-testid="mbr-crmloop-cooldown-btn">
        {fmt(value)} <ChevronDown size={9} />
      </button>
      {open && (
        <div className="absolute z-10 top-full left-0 mt-1 rounded-md border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] py-1 shadow-lg">
          {presets.map((p) => (
            <button key={p} onClick={() => { setOpen(false); onChange(p); }}
              className={`block w-full text-left px-3 py-1 hover:bg-zinc-500/10 ${p === value ? 'text-violet-500 font-bold' : ''}`}>
              {fmt(p)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}


function SignalsView({ API, headers }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  useEffect(() => {
    setLoading(true);
    const url = `${API}/memberships/crm-loop/signals?days=30${filter ? `&kind=${filter}` : ''}`;
    axios.get(url, { headers })
      .then((r) => setData(r.data))
      .catch(() => notify.error(t('memberships_console.crml_signals_fail', 'Signals failed')))
      .finally(() => setLoading(false));
  }, [API, headers, filter, t]);

  return (
    <div>
      <div className="flex gap-1 mb-3 overflow-x-auto pb-1 -mx-1 px-1">
        <FilterPill active={!filter} onClick={() => setFilter('')}>{t('memberships_console.crml_all', 'All')}</FilterPill>
        {Object.keys(KIND_META).map((k) => (
          <FilterPill key={k} active={filter === k} onClick={() => setFilter(k)}>
            {t(`memberships_console.${KIND_META[k].labelKey}`, KIND_META[k].label)}
          </FilterPill>
        ))}
      </div>
      {loading ? <Spinner /> : data?.count === 0 ? (
        <Empty title={t('memberships_console.crml_no_signals', 'No signals yet')} hint={t('memberships_console.crml_no_signals_hint', 'The detector will catch signals on its next 5-min cycle, or hit Scan now on the dashboard.')} />
      ) : (
        <div className="space-y-1.5">
          {data.signals.map((s) => <SignalRow key={s.id} s={s} />)}
        </div>
      )}
    </div>
  );
}


function SignalRow({ s }) {
  const { t } = useTranslation();
  const meta = KIND_META[s.kind] || {};
  const Icon = meta.icon || Activity;
  return (
    <div className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-2.5 flex items-center gap-2"
      data-testid={`mbr-crmloop-signal-${s.id}`}>
      <Icon size={12} className={`flex-shrink-0 ${
        meta.tone === 'amber' ? 'text-amber-500'
        : meta.tone === 'red' ? 'text-red-400'
        : meta.tone === 'sky' ? 'text-sky-500'
        : 'text-emerald-500'
      }`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-bold truncate">{s.member_name}</p>
        <p className="text-[10px] text-[color:var(--theme-text-muted)]">
          {meta.labelKey ? t(`memberships_console.${meta.labelKey}`, meta.label) : meta.label} · {new Date(s.detected_at).toLocaleString()}
        </p>
      </div>
      {s.fired ? (
        <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-500">{t('memberships_console.crml_sent', 'Sent')}</span>
      ) : (
        <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-zinc-500/15 text-[color:var(--theme-text-muted)]">{t('memberships_console.crml_held', 'Held')}</span>
      )}
    </div>
  );
}


function SendsView({ API, headers }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    axios.get(`${API}/memberships/crm-loop/sends?days=30`, { headers })
      .then((r) => setData(r.data))
      .catch(() => notify.error(t('memberships_console.crml_sends_fail', 'Sends failed')))
      .finally(() => setLoading(false));
  }, [API, headers, t]);

  if (loading) return <Spinner />;
  if (!data?.count) return <Empty title={t('memberships_console.crml_no_sends', 'No sends yet')} hint={t('memberships_console.crml_no_sends_hint', 'Once a signal fires + cooldown clears, the matching email is dispatched and shown here.')} />;
  return (
    <div className="space-y-1.5">
      {data.sends.map((s) => {
        const meta = KIND_META[s.kind] || {};
        const Icon = meta.icon || Send;
        return (
          <div key={s.id}
            className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-2.5 flex items-center gap-2"
            data-testid={`mbr-crmloop-send-${s.id}`}>
            <Icon size={12} className={`flex-shrink-0 ${
              meta.tone === 'amber' ? 'text-amber-500'
              : meta.tone === 'red' ? 'text-red-400'
              : meta.tone === 'sky' ? 'text-sky-500'
              : 'text-emerald-500'
            }`} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold truncate">{s.member_name}</p>
              <p className="text-[10px] text-[color:var(--theme-text-muted)]">
                {meta.labelKey ? t(`memberships_console.${meta.labelKey}`, meta.label) : meta.label} · {new Date(s.sent_at).toLocaleString()}
                {s.error && ` · ${t('memberships_console.crml_error', 'error')}: ${s.error}`}
              </p>
            </div>
            {s.ok ? (
              <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-500">{t('memberships_console.crml_ok', 'OK')}</span>
            ) : (
              <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-red-500/15 text-red-400">{t('memberships_console.crml_failed_badge', 'Failed')}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}


/* ─────── shared ─────── */


function FilterPill({ active, onClick, children }) {
  return (
    <button onClick={onClick}
      className={`flex-shrink-0 px-2.5 py-1 rounded-md text-[11px] font-bold border whitespace-nowrap ${
        active
          ? 'bg-violet-500 text-white border-violet-500'
          : 'bg-transparent border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]'
      }`}>
      {children}
    </button>
  );
}


function Spinner() {
  return (
    <div className="flex items-center justify-center py-10 text-[color:var(--theme-text-muted)] text-sm gap-2">
      <Loader2 size={14} className="animate-spin" /> Loading…
    </div>
  );
}


function Empty({ title, hint }) {
  return (
    <div className="rounded-xl border border-dashed border-[color:var(--theme-border)] p-10 text-center">
      <Heart size={28} className="mx-auto text-[color:var(--theme-text-muted)] mb-3" />
      <p className="text-sm font-bold">{title}</p>
      {hint && <p className="text-xs text-[color:var(--theme-text-muted)] mt-1 max-w-sm mx-auto">{hint}</p>}
    </div>
  );
}
