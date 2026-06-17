/**
 * IntegrationsSiconConnect — /admin/integrations/sicon
 *
 * Iter 216h135. Master-admin Connect panel for the Sicon Service
 * Manager (Sage 200 add-on). Lets the platform owner paste Sicon
 * credentials, run a live Ping test, and toggle integration ON.
 *
 * Backed by existing endpoints (see /app/backend/routes/sicon.py):
 *   GET  /api/sicon/config              — masked config + status flags
 *   PUT  /api/sicon/config              — encrypts creds at rest
 *   POST /api/sicon/test-connection     — pings using stored creds
 *
 * Designed so that the moment Sicon credentials land we go live with
 * **zero code changes** — outbox workers already monitor `sicon_config
 * .enabled=true` and start pushing the moment it flips.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Cable, Save, FlaskConical, Loader2, CheckCircle2,
  AlertTriangle, ZapOff, Zap, EyeOff, KeyRound, Globe, Building2,
  RotateCw, Cog,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const EMPTY = {
  base_url: '',
  username: '',
  password: '',
  company_id: 0,
  enabled: false,
  auto_sync_faults: true,
  auto_sync_status: true,
};

export default function IntegrationsSiconConnect() {
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [original, setOriginal] = useState(EMPTY);
  const [meta, setMeta] = useState(null);     // server-returned masked config
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/sicon/config`, auth());
      setMeta(r.data);
      const seed = {
        base_url: r.data.base_url || '',
        username: r.data.username || '',     // server returns ••••••••
        password: '',                         // never echoes back
        company_id: r.data.company_id || 0,
        enabled: !!r.data.enabled,
        auto_sync_faults: !!r.data.auto_sync_faults,
        auto_sync_status: !!r.data.auto_sync_status,
      };
      setForm(seed);
      setOriginal(seed);
    } catch (e) {
      notify.error('Could not load Sicon config');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const dirty = JSON.stringify(form) !== JSON.stringify(original);

  const save = useCallback(async () => {
    setSaving(true);
    try {
      const payload = { ...form };
      // The backend treats `••••••••` as "don't overwrite username".
      // We blank-out password if the user didn't type one, so it stays.
      if (!payload.password) delete payload.password;
      await axios.put(`${API}/sicon/config`, payload, auth());
      notify.success('Sicon configuration saved');
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Save failed');
    } finally {
      setSaving(false);
    }
  }, [form, load]);

  const test = useCallback(async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await axios.post(`${API}/sicon/test-connection`, {}, auth());
      setTestResult(r.data);
      if (r.data.connected) notify.success('Sicon Ping OK');
      else notify.error(r.data.error || 'Sicon Ping failed');
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Ping failed';
      setTestResult({ connected: false, error: msg });
      notify.error(msg);
    } finally {
      setTesting(false);
    }
  }, []);

  if (loading) {
    return <FullscreenLoader />;
  }

  const live = !!meta?.enabled && (meta?.connection_status === 'connected');

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900" data-testid="sicon-connect-page">
      <header className="sticky top-0 z-10 bg-white/95 backdrop-blur border-b border-slate-200">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/admin/integrations')}
            className="p-2 rounded-full hover:bg-slate-100"
            aria-label="Back"
            data-testid="sicon-connect-back"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="flex-1">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
              Admin · Integrations
            </p>
            <h1 className="text-lg font-extrabold flex items-center gap-2">
              <Cable size={18} /> Sicon Service Manager
            </h1>
          </div>
          <StatusPip configured={meta?.configured} live={live} />
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6 space-y-5">
        {/* What is Sicon explainer */}
        <ExplainerCard configured={meta?.configured} live={live} />

        {/* Credentials form */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="sicon-creds-form">
          <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-3">
            Credentials
          </p>

          <Field label="Base URL" icon={Globe} testid="sicon-base-url"
                  value={form.base_url} onChange={v => setForm(f => ({ ...f, base_url: v }))}
                  placeholder="https://sicon.your-host.com" />

          <Field label="Username" icon={KeyRound} testid="sicon-username"
                  value={form.username} onChange={v => setForm(f => ({ ...f, username: v }))}
                  placeholder="api-user@pulsefitness"
                  hint={form.username === '••••••••' ? 'A username is saved — type a new one to replace.' : ''} />

          <Field label="Password" icon={EyeOff} testid="sicon-password" type="password"
                  value={form.password} onChange={v => setForm(f => ({ ...f, password: v }))}
                  placeholder={meta?.has_password ? '••••••••  (leave blank to keep)' : 'Sicon API password'} />

          <Field label="Sage 200 Company ID" icon={Building2} testid="sicon-company-id" type="number"
                  value={form.company_id} onChange={v => setForm(f => ({ ...f, company_id: Number(v) || 0 }))}
                  placeholder="0" hint="Multi-company Sage 200 installs only. Leave 0 for single-company." />

          <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-2">
            <Toggle label="Integration enabled" testid="sicon-enabled"
                     value={form.enabled} onChange={v => setForm(f => ({ ...f, enabled: v }))} />
            <Toggle label="Auto-push new faults" testid="sicon-auto-push-faults"
                     value={form.auto_sync_faults} onChange={v => setForm(f => ({ ...f, auto_sync_faults: v }))} />
            <Toggle label="Auto-pull status updates" testid="sicon-auto-pull-status"
                     value={form.auto_sync_status} onChange={v => setForm(f => ({ ...f, auto_sync_status: v }))} />
          </div>

          <div className="mt-5 flex gap-2 flex-wrap">
            <button
              type="button"
              disabled={saving || !dirty}
              onClick={save}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold disabled:opacity-50"
              data-testid="sicon-save-btn"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              {saving ? 'Saving…' : 'Save configuration'}
            </button>
            <button
              type="button"
              disabled={testing || !meta?.configured}
              onClick={test}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white border border-slate-200 text-slate-700 text-sm font-bold hover:bg-slate-50 disabled:opacity-50"
              data-testid="sicon-test-btn"
              title={!meta?.configured ? 'Save credentials first' : 'Calls Sicon /SMConnectivity/Ping with the saved creds'}
            >
              {testing ? <Loader2 size={14} className="animate-spin" /> : <FlaskConical size={14} />}
              {testing ? 'Testing…' : 'Test connection'}
            </button>
            <button
              type="button"
              onClick={load}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white border border-slate-200 text-slate-700 text-sm font-bold hover:bg-slate-50"
              data-testid="sicon-reload-btn"
            >
              <RotateCw size={14} /> Reload
            </button>
          </div>

          {testResult && (
            <div
              className={`mt-3 rounded-lg p-3 text-xs flex items-start gap-2 border ${
                testResult.connected
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                  : 'bg-rose-50 border-rose-200 text-rose-900'
              }`}
              data-testid="sicon-test-result"
            >
              {testResult.connected
                ? <CheckCircle2 size={14} className="mt-0.5 text-emerald-600" />
                : <AlertTriangle size={14} className="mt-0.5 text-rose-600" />}
              <div>
                <p className="font-bold">
                  {testResult.connected
                    ? 'Sicon API reachable'
                    : 'Connection failed'}
                </p>
                {testResult.error && (
                  <pre className="whitespace-pre-wrap break-all text-[11px] mt-1">{testResult.error}</pre>
                )}
                {testResult.connected && (
                  <p className="text-[11px] mt-0.5">/api/SMConnectivity/Ping returned 200 OK.</p>
                )}
              </div>
            </div>
          )}
        </section>

        {/* Status panel */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="sicon-status-card">
          <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">
            Status
          </p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <Row label="Configured" value={meta?.configured ? 'Yes' : 'No'} />
            <Row label="Enabled"    value={meta?.enabled ? 'Yes' : 'No'} />
            <Row label="Connection" value={meta?.connection_status || '—'} />
            <Row label="Last tested" value={meta?.last_test_at ? new Date(meta.last_test_at).toLocaleString() : '—'} />
            <Row label="Last sync"   value={meta?.last_sync_at ? new Date(meta.last_sync_at).toLocaleString() : '—'} />
            <Row label="Last poll"   value={meta?.last_poll_at ? new Date(meta.last_poll_at).toLocaleString() : '—'} />
          </dl>
        </section>

        {/* What happens next */}
        <section className="rounded-2xl border border-blue-200 bg-blue-50 p-5" data-testid="sicon-next-steps">
          <p className="text-[11px] font-bold uppercase tracking-wide text-blue-700 mb-2">When credentials land</p>
          <ol className="text-xs text-blue-900 list-decimal list-inside space-y-1">
            <li>Paste credentials above and click <b>Save</b> — they are encrypted at rest with Fernet (derived from JWT_SECRET).</li>
            <li>Click <b>Test connection</b> — hits <code>/api/SMConnectivity/Ping</code>.</li>
            <li>Flip <b>Integration enabled</b> ON — the outbox worker starts flushing pending cases/notes/appointments immediately.</li>
            <li>Visit <a className="underline font-bold" href="/admin/integrations">/admin/integrations</a> for live outbox health.</li>
          </ol>
        </section>
      </main>
    </div>
  );
}

// ─────────────────────────── small bits ──────────────────────────────

function FullscreenLoader() {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-400">
      <Loader2 className="animate-spin mr-2" size={18} />
      Loading Sicon settings…
    </div>
  );
}

const StatusPip = ({ configured, live }) => {
  if (live) {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 text-[11px] font-bold" data-testid="sicon-status-pip-live">
        <Zap size={11} /> Live
      </span>
    );
  }
  if (configured) {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-100 text-amber-800 text-[11px] font-bold" data-testid="sicon-status-pip-configured">
        <Cog size={11} /> Configured · disabled
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-[11px] font-bold" data-testid="sicon-status-pip-dryrun">
      <ZapOff size={11} /> Dry-run · awaiting credentials
    </span>
  );
};

const ExplainerCard = ({ configured, live }) => (
  <section
    className="rounded-2xl p-5 text-white shadow-md"
    style={{ background: live
      ? 'linear-gradient(135deg, #047857 0%, #0d9488 60%, #1d4ed8 100%)'
      : 'linear-gradient(135deg, #1d4ed8 0%, #6366f1 60%, #8b5cf6 100%)' }}
    data-testid="sicon-explainer"
  >
    <p className="text-[10px] uppercase tracking-[0.18em] font-bold opacity-90">
      Sicon Service Manager · Sage 200 add-on
    </p>
    <h2 className="text-xl font-extrabold mt-1">
      {live
        ? 'Live link to your accounts ERP'
        : configured
          ? 'Almost there — turn the integration ON'
          : "We're ready when your Sicon API key is"}
    </h2>
    <p className="text-sm opacity-95 mt-1 max-w-2xl">
      All outbound payloads (cases, tracking notes, appointments, time
      bookings, part movements, contracts) already queue to
      <code className="mx-1 bg-white/10 px-1 rounded">svc_sicon_outbox</code>
      and pull-down updates are scheduled — they go live the moment you
      save valid credentials and flip the toggle.
    </p>
  </section>
);

const Field = ({ label, value, onChange, icon: Icon, placeholder, type = 'text', testid, hint }) => (
  <div className="mb-3">
    <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-1 flex items-center gap-1.5">
      {Icon ? <Icon size={11} /> : null}
      {label}
    </label>
    <input
      type={type}
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
      data-testid={testid}
      autoComplete="off"
      spellCheck={false}
    />
    {hint && <p className="text-[11px] text-slate-500 mt-1">{hint}</p>}
  </div>
);

const Toggle = ({ label, value, onChange, testid }) => (
  <label
    className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-bold cursor-pointer select-none transition-colors ${
      value
        ? 'bg-blue-50 border-blue-200 text-blue-800'
        : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'
    }`}
    data-testid={testid}
  >
    <input
      type="checkbox"
      checked={!!value}
      onChange={e => onChange(e.target.checked)}
      className="sr-only"
    />
    <span className={`w-3.5 h-3.5 rounded-sm border flex items-center justify-center ${
      value ? 'bg-blue-600 border-blue-600' : 'border-slate-300'
    }`}>
      {value && <CheckCircle2 size={10} className="text-white" />}
    </span>
    {label}
  </label>
);

const Row = ({ label, value }) => (
  <>
    <dt className="text-slate-500">{label}</dt>
    <dd className="font-semibold text-slate-900 tabular-nums">{value}</dd>
  </>
);
