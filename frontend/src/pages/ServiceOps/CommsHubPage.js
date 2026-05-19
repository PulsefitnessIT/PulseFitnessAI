/**
 * CommsHubPage — iter 215dv (Phase 7b).
 *
 * Operator console at /service-ops/comms.
 *
 * Two tabs:
 *   • Templates — edit case_logged / engineer_en_route / case_completed /
 *     supplier_po with `{{var}}` placeholders, reset to default
 *   • Activity — recent send log with status pills (sent / failed)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Mail, History, Save, RotateCcw, RefreshCw, Loader2,
  CheckCircle2, AlertTriangle,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import ServiceOpsShell from './ServiceOpsShell';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const TABS = [
  { id: 'templates', label: 'Templates', icon: Mail },
  { id: 'activity', label: 'Activity', icon: History },
];

const PLACEHOLDER_HINT = {
  case_logged: 'Vars: customer_name · reference · site_name · title · priority_label',
  engineer_en_route: 'Vars: customer_name · reference · site_name · engineer_name · scheduled_label',
  case_completed: 'Vars: customer_name · reference · title · site_name · summary',
  supplier_po: 'Vars: po_reference · supplier · line_count · total · lines_text · notes · org_name',
};

export default function CommsHubPage() {
  const [tab, setTab] = useState('templates');
  return (
    <ServiceOpsShell
      icon={Mail}
      title="Customer comms hub"
      subtitle={
        <>Branded email templates for case status updates and supplier purchase orders. Use <code>{'{{var}}'}</code> placeholders — the merge engine pulls case &amp; PO data automatically.</>
      }
      active="comms"
      pageTestId="comms-page"
    >
      <nav className="svc-tabs">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`svc-tab ${active ? 'svc-tab--active' : ''}`}
              data-testid={`comms-tab-${t.id}`}
            >
              <Icon size={13} /> {t.label}
            </button>
          );
        })}
      </nav>

      {tab === 'templates' ? <TemplatesTab /> : <ActivityTab />}
    </ServiceOpsShell>
  );
}

function TemplatesTab() {
  const [rows, setRows] = useState([]);
  const [active, setActive] = useState(null);
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/comms/templates`, auth());
      setRows(r.data.templates || []);
      if (!active && r.data.templates?.length) setActive(r.data.templates[0].key);
    } catch (e) { notify.error('Failed to load templates', e?.response?.data?.detail || e.message); }
  }, [active]);
  useEffect(() => { load(); }, [load]);

  const current = useMemo(() => rows.find((r) => r.key === active), [rows, active]);
  useEffect(() => {
    if (current) setDraft({ subject: current.subject, body_html: current.body_html, audience: current.audience });
  }, [current]);

  const save = async () => {
    if (!current || !draft) return;
    setBusy('save');
    try {
      const r = await axios.put(`${API}/svc/comms/templates/${current.key}`, draft, auth());
      setRows(rows.map((row) => row.key === current.key ? r.data : row));
      notify.success('Template saved');
    } catch (e) { notify.error('Save failed', e?.response?.data?.detail || e.message); }
    finally { setBusy(''); }
  };

  const reset = async () => {
    if (!current) return;
    setBusy('reset');
    try {
      const r = await axios.post(`${API}/svc/comms/templates/${current.key}/reset`, {}, auth());
      setRows(rows.map((row) => row.key === current.key ? r.data : row));
      notify.success('Reset to default');
    } catch (e) { notify.error('Reset failed', e?.response?.data?.detail || e.message); }
    finally { setBusy(''); }
  };

  return (
    <div className="grid grid-cols-12 gap-4" data-testid="comms-templates-tab">
      <aside className="col-span-12 lg:col-span-3 svc-card-base overflow-hidden">
        <ul>
          {rows.map((r) => (
            <li key={r.key}>
              <button
                type="button"
                onClick={() => setActive(r.key)}
                className={`w-full text-left px-3 py-2.5 text-sm border-b transition-colors ${active === r.key ? 'font-extrabold' : ''}`}
                style={{
                  borderColor: 'var(--svc-border)',
                  background: active === r.key ? 'var(--svc-accent-soft)' : 'transparent',
                  color: active === r.key ? 'var(--svc-accent)' : 'var(--svc-text)',
                }}
                data-testid={`comms-template-pick-${r.key}`}
              >
                <div>{r.key}</div>
                <div className="text-[10px] svc-muted uppercase tracking-wider">{r.audience}{r.is_default ? ' · default' : ''}</div>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="col-span-12 lg:col-span-9 svc-section" data-testid="comms-template-editor">
        <div className="svc-section-body space-y-4">
        {!current ? (
          <p className="text-xs svc-muted italic">Select a template on the left.</p>
        ) : (
          <>
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div>
                <p className="svc-label">Template</p>
                <p className="font-extrabold text-base" style={{ color: 'var(--svc-text)' }}>{current.key}</p>
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={reset} disabled={busy === 'reset'} className="svc-btn svc-btn-secondary svc-btn-sm" data-testid="comms-template-reset">
                  <RotateCcw size={11} /> {busy === 'reset' ? '…' : 'Reset to default'}
                </button>
                <button type="button" onClick={save} disabled={busy === 'save'} className="svc-btn svc-btn-primary svc-btn-sm" data-testid="comms-template-save">
                  <Save size={11} /> {busy === 'save' ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>

            <p className="text-[11px] svc-muted">{PLACEHOLDER_HINT[current.key] || 'Use {{var}} placeholders'}</p>

            <label className="block">
              <span className="svc-label">Audience</span>
              <select value={draft?.audience || 'customer'} onChange={(e) => setDraft({ ...draft, audience: e.target.value })} className="svc-select" data-testid="comms-template-audience">
                <option value="customer">customer</option>
                <option value="supplier">supplier</option>
                <option value="engineer">engineer</option>
              </select>
            </label>

            <label className="block">
              <span className="svc-label">Subject</span>
              <input value={draft?.subject || ''} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} className="svc-input" data-testid="comms-template-subject" />
            </label>

            <label className="block">
              <span className="svc-label">HTML body</span>
              <textarea value={draft?.body_html || ''} onChange={(e) => setDraft({ ...draft, body_html: e.target.value })} rows={12} className="svc-textarea" data-testid="comms-template-body" />
            </label>

            <details className="svc-card-base p-3">
              <summary className="text-xs font-bold cursor-pointer" style={{ color: 'var(--svc-text)' }}>Preview (sample data)</summary>
              <div className="mt-3 text-sm" data-testid="comms-template-preview"
                dangerouslySetInnerHTML={{ __html: previewBody(current.key, draft?.body_html || '') }}
              />
            </details>
          </>
        )}
        </div>
      </section>
    </div>
  );
}

function ActivityTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/comms/log`, { ...auth(), params: { limit: 100 } });
      setRows(r.data.events || []);
    } catch (e) { notify.error('Could not load comms log', e?.response?.data?.detail || e.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-3" data-testid="comms-activity-tab">
      <div className="flex justify-end">
        <button type="button" onClick={load} className="svc-btn svc-btn-secondary svc-btn-sm" data-testid="comms-activity-refresh">
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>
      <div className="svc-table-wrap">
        <table className="svc-table">
          <thead><tr><th>When</th><th>Kind</th><th>Template</th><th>To</th><th>Subject</th><th>Status</th></tr></thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="6"><div className="svc-empty"><Loader2 size={14} className="animate-spin" /> Loading…</div></td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan="6"><div className="svc-empty"><Mail size={20} /><div>No comms sent yet.</div></div></td></tr>
            ) : rows.map((r) => (
              <tr key={r.id} data-testid={`comms-log-row-${r.id}`}>
                <td className="text-[11px] tabular-nums svc-muted">{new Date(r.at).toLocaleString()}</td>
                <td className="text-[11px]"><span className="svc-pill">{r.kind}</span></td>
                <td className="text-[11px] svc-muted">{r.template_key}</td>
                <td className="text-[11px]">{r.to}</td>
                <td className="text-[11px] truncate" style={{ maxWidth: '20rem' }}>{r.subject}</td>
                <td>
                  {r.ok ? (
                    <span className="svc-pill svc-pill--good" data-testid={`comms-log-status-${r.id}`}>
                      <CheckCircle2 size={10} /> sent
                    </span>
                  ) : (
                    <span className="svc-pill svc-pill--danger" title={r.error} data-testid={`comms-log-status-${r.id}`}>
                      <AlertTriangle size={10} /> {r.error?.includes('api_key') ? 'no API key' : 'failed'}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Lightweight client-side template preview ──────────────────────
function previewBody(key, html) {
  const sample = {
    customer_name: 'Sam Tester',
    reference: 'SVC-00123',
    site_name: 'PureGym Holborn',
    title: 'Treadmill belt replacement',
    priority_label: 'P2 — High',
    engineer_name: 'Jordan Lee',
    scheduled_label: '14:30 today',
    summary: 'Replaced belt and reset deck. Tested at 12 km/h.',
    po_reference: 'PO-00001',
    supplier: 'Life Fitness Spares',
    line_count: 2,
    total: '624.00',
    lines_text: 'BELT-95TI    qty   1 @ £  300.00  Treadmill belt 95Ti',
    notes: 'Please ship next-day.',
    org_name: 'GymAxis Demo',
  };
  return (html || '').replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, (_, name) => sample[name] ?? `{{${name}}}`);
}
