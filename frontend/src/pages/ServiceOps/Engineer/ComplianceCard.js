/**
 * ComplianceCard — Iter 220de.
 *
 * Surfaces the field-engineer compliance status for a single case
 * on the ``JobAtAGlance`` header. Three sections:
 *
 *   • Permit to Work (PTW) — request → admin issues → engineer completes.
 *   • LOTO checklist — engineer ticks a generic isolation procedure.
 *   • COSHH usage — engineer logs which org-register chemicals they used.
 *
 * Quiet when nothing needs the engineer's attention. Renders a
 * lightweight expandable card when ANY of the three has outstanding
 * action OR has a captured record (so the engineer can review).
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import {
  ShieldCheck, AlertTriangle, ChevronDown, ChevronUp, Plus,
  Check, Loader2, X, ClipboardCheck, FlaskConical,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

export default function ComplianceCard({ caseId, onChange }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [activeDialog, setActiveDialog] = useState(null); // 'ptw' | 'loto' | 'coshh'

  const load = async () => {
    try {
      const r = await axios.get(
        `${API}/svc/engineer/jobs/${caseId}/compliance-summary`, auth(),
      );
      setSummary(r.data);
    } catch (_e) {
      setSummary(null);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [caseId]);

  if (loading || !summary) return null;
  const ptwActive = summary.ptw?.active;
  const ptwNeeded = summary.ptw?.needs_action;
  const lotoNeeded = summary.loto?.needs_action;
  const lotoDone = (summary.loto?.completed_count || 0) > 0;
  const coshhDone = (summary.coshh?.recorded_count || 0) > 0;

  const hasAction = ptwNeeded || lotoNeeded;
  const hasRecord = ptwActive || lotoDone || coshhDone;
  if (!hasAction && !hasRecord) {
    // Quiet state: show a single "Log compliance" link only.
    return (
      <div className="mx-3 mb-2" data-testid="compliance-card-quiet">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="text-[10px] font-bold uppercase tracking-wide text-slate-500 hover:text-slate-700 inline-flex items-center gap-1"
          data-testid="compliance-open"
        >
          <ShieldCheck size={11} /> Log compliance (PTW / LOTO / COSHH)
        </button>
        {open && (
          <ComplianceDialogs
            caseId={caseId}
            activeDialog={activeDialog}
            setActiveDialog={setActiveDialog}
            onClose={() => { setOpen(false); setActiveDialog(null); }}
            onRecorded={() => { load(); onChange?.(); }}
          />
        )}
      </div>
    );
  }

  const headerCls = hasAction
    ? 'bg-amber-50 border-amber-200 text-amber-900'
    : 'bg-emerald-50 border-emerald-200 text-emerald-900';

  return (
    <div
      className={`mx-3 mb-2 p-2 rounded-lg border ${headerCls}`}
      data-testid="compliance-card"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2"
        data-testid="compliance-toggle"
      >
        {hasAction ? <AlertTriangle size={14} /> : <ShieldCheck size={14} />}
        <p className="text-[10px] font-bold uppercase tracking-wide flex-1 text-left">
          Compliance
        </p>
        <div className="flex items-center gap-1">
          {ptwActive ? (
            <span className="px-1.5 py-0.5 rounded-full bg-white border border-blue-200 text-blue-800 text-[10px] font-bold uppercase tracking-wide" data-testid="compliance-ptw-chip">
              PTW {ptwActive.status}
            </span>
          ) : ptwNeeded ? (
            <span className="px-1.5 py-0.5 rounded-full bg-white border border-rose-200 text-rose-800 text-[10px] font-bold uppercase tracking-wide" data-testid="compliance-ptw-needed">
              PTW needed
            </span>
          ) : null}
          {lotoDone ? (
            <span className="px-1.5 py-0.5 rounded-full bg-white border border-emerald-200 text-emerald-800 text-[10px] font-bold uppercase tracking-wide" data-testid="compliance-loto-done">
              LOTO ✓
            </span>
          ) : lotoNeeded ? (
            <span className="px-1.5 py-0.5 rounded-full bg-white border border-rose-200 text-rose-800 text-[10px] font-bold uppercase tracking-wide" data-testid="compliance-loto-needed">
              LOTO needed
            </span>
          ) : null}
          {coshhDone && (
            <span className="px-1.5 py-0.5 rounded-full bg-white border border-emerald-200 text-emerald-800 text-[10px] font-bold uppercase tracking-wide" data-testid="compliance-coshh-done">
              COSHH ✓
            </span>
          )}
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </div>
      </button>
      {open && (
        <div className="mt-2 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span>Permit to Work</span>
            <button
              type="button"
              onClick={() => setActiveDialog('ptw')}
              className="px-2 py-1 rounded bg-white border border-slate-200 text-[10px] font-bold uppercase tracking-wide hover:bg-slate-50"
              data-testid="compliance-ptw-open"
            >
              {ptwActive ? 'View / complete' : 'Request'}
            </button>
          </div>
          <div className="flex items-center justify-between">
            <span>LOTO checklist</span>
            <button
              type="button"
              onClick={() => setActiveDialog('loto')}
              className="px-2 py-1 rounded bg-white border border-slate-200 text-[10px] font-bold uppercase tracking-wide hover:bg-slate-50"
              data-testid="compliance-loto-open"
            >
              {lotoDone ? 'New' : 'Complete'}
            </button>
          </div>
          <div className="flex items-center justify-between">
            <span>COSHH usage</span>
            <button
              type="button"
              onClick={() => setActiveDialog('coshh')}
              className="px-2 py-1 rounded bg-white border border-slate-200 text-[10px] font-bold uppercase tracking-wide hover:bg-slate-50"
              data-testid="compliance-coshh-open"
            >
              Log
            </button>
          </div>
        </div>
      )}
      <ComplianceDialogs
        caseId={caseId}
        activeDialog={activeDialog}
        setActiveDialog={setActiveDialog}
        onClose={() => setActiveDialog(null)}
        onRecorded={() => { load(); onChange?.(); }}
      />
    </div>
  );
}

// ─── Dialogs ─────────────────────────────────────────────────────

function ComplianceDialogs({ caseId, activeDialog, setActiveDialog, onClose, onRecorded }) {
  if (!activeDialog) return null;
  const Body = activeDialog === 'ptw'
    ? PtwDialog
    : activeDialog === 'loto' ? LotoDialog : CoshhDialog;
  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/60 flex items-end sm:items-center justify-center"
      data-testid={`compliance-dialog-${activeDialog}`}
      onClick={(e) => { if (e.target === e.currentTarget) setActiveDialog(null); }}
    >
      <div className="w-full max-w-md bg-white rounded-t-3xl sm:rounded-3xl shadow-xl overflow-hidden">
        <Body caseId={caseId} onClose={onClose} onRecorded={onRecorded} />
      </div>
    </div>
  );
}

// ─── PTW dialog ──────────────────────────────────────────────────

function PtwDialog({ caseId, onClose, onRecorded }) {
  const [templates, setTemplates] = useState([]);
  const [requests, setRequests] = useState([]);
  const [tplId, setTplId] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [t, r] = await Promise.all([
          axios.get(`${API}/svc/compliance/ptw/templates`, auth()),
          axios.get(`${API}/svc/engineer/jobs/${caseId}/ptw-requests`, auth()),
        ]);
        const items = t.data?.items || [];
        setTemplates(items);
        setTplId(items[0]?.id || '');
        setRequests(r.data?.items || []);
      } catch (_e) { /* noop */ }
    })();
  }, [caseId]);

  const request = async () => {
    setBusy(true);
    try {
      await axios.post(
        `${API}/svc/engineer/jobs/${caseId}/ptw-requests`,
        { template_id: tplId, notes },
        auth(),
      );
      notify.success('PTW requested', 'Admin will review and issue.');
      onRecorded();
      onClose();
    } catch (e) {
      notify.error('Could not request', e?.response?.data?.detail || e?.message);
    } finally { setBusy(false); }
  };
  const complete = async (id) => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/engineer/ptw-requests/${id}/complete`, {}, auth());
      notify.success('PTW completed');
      onRecorded();
      onClose();
    } catch (e) {
      notify.error('Could not complete', e?.response?.data?.detail || e?.message);
    } finally { setBusy(false); }
  };

  return (
    <div className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <ShieldCheck size={16} className="text-blue-600" />
        <p className="text-sm font-bold flex-1">Permit to Work</p>
        <button onClick={onClose} className="text-slate-500" data-testid="ptw-dialog-close"><X size={14} /></button>
      </div>
      {requests.length > 0 && (
        <div className="mb-3" data-testid="ptw-existing">
          <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-1">
            Existing
          </p>
          <ul className="space-y-1">
            {requests.map((r) => (
              <li key={r.id} className="text-xs border border-slate-200 rounded p-2 flex items-center gap-2" data-testid={`ptw-row-${r.id}`}>
                <span className="flex-1">
                  <span className="font-bold">{r.template_name}</span>
                  <span className="ml-1 text-slate-500">· {r.status}</span>
                  {r.valid_until ? <span className="text-slate-400 ml-1">until {new Date(r.valid_until).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span> : null}
                </span>
                {r.status === 'issued' && (
                  <button
                    onClick={() => complete(r.id)}
                    disabled={busy}
                    className="px-2 py-0.5 rounded bg-emerald-600 text-white text-[10px] font-bold uppercase"
                    data-testid={`ptw-complete-${r.id}`}
                  >
                    Complete
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="space-y-2">
        <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Template</label>
        <select
          value={tplId}
          onChange={(e) => setTplId(e.target.value)}
          className="w-full text-sm px-2 py-2 rounded border border-slate-200"
          data-testid="ptw-template-select"
        >
          {templates.length === 0 && <option value="">No templates available</option>}
          {templates.map((t) => (
            <option key={t.id} value={t.id}>{t.name} · {t.hazard_category}</option>
          ))}
        </select>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notes (optional)"
          rows={2}
          className="w-full text-sm px-2 py-1 rounded border border-slate-200"
          data-testid="ptw-notes"
        />
        <button
          onClick={request}
          disabled={!tplId || busy}
          className="w-full px-3 py-2 rounded bg-blue-600 text-white text-xs font-bold uppercase disabled:opacity-50"
          data-testid="ptw-request-submit"
        >
          {busy ? <Loader2 size={12} className="animate-spin inline" /> : <><Plus size={12} className="inline -mt-0.5" /> Request permit</>}
        </button>
      </div>
    </div>
  );
}

// ─── LOTO dialog ─────────────────────────────────────────────────

function LotoDialog({ caseId, onClose, onRecorded }) {
  const [steps, setSteps] = useState([]);
  const [ticked, setTicked] = useState(new Set());
  const [energy, setEnergy] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/svc/engineer/jobs/${caseId}/loto`, auth());
        setSteps(r.data?.steps || []);
      } catch (_e) { /* noop */ }
    })();
  }, [caseId]);

  const toggle = (id) => {
    const next = new Set(ticked);
    if (next.has(id)) next.delete(id); else next.add(id);
    setTicked(next);
  };
  const submit = async () => {
    setBusy(true);
    try {
      await axios.post(
        `${API}/svc/engineer/jobs/${caseId}/loto`,
        {
          ticked_step_ids: Array.from(ticked),
          energy_sources: energy.split(',').map((s) => s.trim()).filter(Boolean),
          notes,
        },
        auth(),
      );
      notify.success('LOTO checklist complete');
      onRecorded();
      onClose();
    } catch (e) {
      notify.error('Could not submit', e?.response?.data?.detail || e?.message);
    } finally { setBusy(false); }
  };

  return (
    <div className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <ClipboardCheck size={16} className="text-blue-600" />
        <p className="text-sm font-bold flex-1">Lockout / Tagout</p>
        <button onClick={onClose} className="text-slate-500" data-testid="loto-dialog-close"><X size={14} /></button>
      </div>
      <ul className="space-y-1 mb-3" data-testid="loto-steps">
        {steps.map((s) => (
          <li key={s.id}>
            <label className="flex items-start gap-2 text-xs cursor-pointer" data-testid={`loto-step-${s.id}`}>
              <input
                type="checkbox"
                checked={ticked.has(s.id)}
                onChange={() => toggle(s.id)}
                className="mt-0.5"
              />
              <span>
                {s.label}
                {s.required ? <span className="text-rose-600 ml-1">*</span> : null}
              </span>
            </label>
          </li>
        ))}
      </ul>
      <input
        type="text"
        value={energy}
        onChange={(e) => setEnergy(e.target.value)}
        placeholder="Energy sources (comma-separated)"
        className="w-full text-sm px-2 py-1 rounded border border-slate-200 mb-2"
        data-testid="loto-energy"
      />
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Notes (optional)"
        rows={2}
        className="w-full text-sm px-2 py-1 rounded border border-slate-200 mb-2"
        data-testid="loto-notes"
      />
      <button
        onClick={submit}
        disabled={busy}
        className="w-full px-3 py-2 rounded bg-emerald-600 text-white text-xs font-bold uppercase disabled:opacity-50"
        data-testid="loto-submit"
      >
        {busy ? <Loader2 size={12} className="animate-spin inline" /> : <><Check size={12} className="inline -mt-0.5" /> Submit checklist</>}
      </button>
    </div>
  );
}

// ─── COSHH dialog ────────────────────────────────────────────────

function CoshhDialog({ caseId, onClose, onRecorded }) {
  const [entries, setEntries] = useState([]);
  const [picked, setPicked] = useState(new Set());
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/svc/engineer/coshh/active`, auth());
        setEntries(r.data?.items || []);
      } catch (_e) { /* noop */ }
    })();
  }, []);

  const toggle = (id) => {
    const next = new Set(picked);
    if (next.has(id)) next.delete(id); else next.add(id);
    setPicked(next);
  };
  const submit = async () => {
    if (picked.size === 0) {
      notify.error('Pick at least one', 'Tick the chemicals you used on this visit.');
      return;
    }
    setBusy(true);
    try {
      await axios.post(
        `${API}/svc/engineer/jobs/${caseId}/coshh-used`,
        { entry_ids: Array.from(picked), notes },
        auth(),
      );
      notify.success('COSHH usage logged');
      onRecorded();
      onClose();
    } catch (e) {
      notify.error('Could not log', e?.response?.data?.detail || e?.message);
    } finally { setBusy(false); }
  };

  return (
    <div className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <FlaskConical size={16} className="text-amber-600" />
        <p className="text-sm font-bold flex-1">COSHH usage</p>
        <button onClick={onClose} className="text-slate-500" data-testid="coshh-dialog-close"><X size={14} /></button>
      </div>
      {entries.length === 0 ? (
        <p className="text-xs text-slate-500" data-testid="coshh-empty">No COSHH entries yet. Ask the operator to seed the register.</p>
      ) : (
        <ul className="space-y-1 mb-3 max-h-64 overflow-y-auto" data-testid="coshh-list">
          {entries.map((e) => (
            <li key={e.id}>
              <label className="flex items-start gap-2 text-xs cursor-pointer" data-testid={`coshh-item-${e.id}`}>
                <input
                  type="checkbox"
                  checked={picked.has(e.id)}
                  onChange={() => toggle(e.id)}
                  className="mt-0.5"
                />
                <span className="flex-1">
                  <span className="font-bold">{e.name}</span>
                  <span className="ml-1 text-slate-500">· {e.hazard_class}</span>
                  {e.controls ? <p className="text-[10px] text-slate-500 leading-snug">{e.controls}</p> : null}
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Notes (optional)"
        rows={2}
        className="w-full text-sm px-2 py-1 rounded border border-slate-200 mb-2"
        data-testid="coshh-notes"
      />
      <button
        onClick={submit}
        disabled={busy || entries.length === 0}
        className="w-full px-3 py-2 rounded bg-amber-600 text-white text-xs font-bold uppercase disabled:opacity-50"
        data-testid="coshh-submit"
      >
        {busy ? <Loader2 size={12} className="animate-spin inline" /> : <><Check size={12} className="inline -mt-0.5" /> Log usage</>}
      </button>
    </div>
  );
}
