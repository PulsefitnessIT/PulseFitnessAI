/**
 * ComplianceAdmin — Iter 220di.
 *
 * Operator-side editor for the org-level **PTW templates** + **COSHH
 * register** seeded by Iter 220de. Both surfaces ship with sensible
 * lazy-seeded defaults (Hot Work, Electrical, Height for PTW; WD-40,
 * IPA, treadmill silicone for COSHH), so engineers can use them on
 * day one. This page lets owners + managers refine them — adding
 * site-specific templates, swapping in their own SDS URLs, soft-
 * deleting items they don't use.
 *
 * One page, two tabs, because:
 *   * They sit under the same Compliance domain.
 *   * Same audience (operator with the safety responsibility hat on).
 *   * Sharing a single embedded surface keeps the Insights footer
 *     nav from sprouting two new entries.
 *
 * Backend API surface (already shipped):
 *   GET / POST / DELETE  /api/svc/compliance/ptw/templates
 *   GET / POST / DELETE  /api/svc/compliance/coshh
 *
 * Owner / Manager / Master Admin only (server-side enforced).
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  ShieldCheck, FlaskConical, Plus, Trash2, Loader2, X, AlertTriangle,
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });

export default function ComplianceAdmin() {
  const [tab, setTab] = useState('ptw'); // 'ptw' | 'coshh'

  return (
    <div className="p-6 max-w-6xl space-y-5" data-testid="compliance-admin">
      <header>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <ShieldCheck size={22} className="text-blue-600" /> Compliance register
        </h1>
        <p className="text-sm text-slate-500 max-w-2xl">
          Permit-to-Work templates and COSHH chemicals used by every
          engineer on every visit. Defaults are seeded the first time
          you load — edit, add or retire to match your contracts (MOD,
          NHS, national chains).
        </p>
      </header>

      <div className="flex items-center gap-1 border-b border-slate-200" data-testid="compliance-admin-tabs">
        <TabButton
          active={tab === 'ptw'}
          onClick={() => setTab('ptw')}
          icon={ShieldCheck}
          label="Permit to Work"
          testId="compliance-admin-tab-ptw"
        />
        <TabButton
          active={tab === 'coshh'}
          onClick={() => setTab('coshh')}
          icon={FlaskConical}
          label="COSHH register"
          testId="compliance-admin-tab-coshh"
        />
      </div>

      {tab === 'ptw' ? <PtwAdmin /> : <CoshhAdmin />}
    </div>
  );
}

function TabButton({ active, onClick, icon: Icon, label, testId }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={`inline-flex items-center gap-2 px-4 py-2 -mb-px border-b-2 text-sm font-bold transition-colors ${
        active
          ? 'border-blue-600 text-blue-700'
          : 'border-transparent text-slate-500 hover:text-slate-700'
      }`}
    >
      <Icon size={14} /> {label}
    </button>
  );
}

// ═══ PTW templates ═══════════════════════════════════════════════

function PtwAdmin() {
  const [rows, setRows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState(emptyPtwDraft());
  const [confirmDelete, setConfirmDelete] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/compliance/ptw/templates`, auth());
      setRows(r.data?.items || []);
      setCategories(r.data?.categories || []);
    } catch (e) {
      toast.error('Could not load PTW templates', { description: e?.response?.data?.detail || e.message });
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const addDraftHazard = () => setDraft({ ...draft, hazards: [...draft.hazards, ''] });
  const addDraftControl = () => setDraft({ ...draft, controls: [...draft.controls, ''] });
  const setDraftHazard = (i, v) => setDraft({ ...draft, hazards: draft.hazards.map((x, j) => j === i ? v : x) });
  const setDraftControl = (i, v) => setDraft({ ...draft, controls: draft.controls.map((x, j) => j === i ? v : x) });
  const removeDraftHazard = (i) => setDraft({ ...draft, hazards: draft.hazards.filter((_, j) => j !== i) });
  const removeDraftControl = (i) => setDraft({ ...draft, controls: draft.controls.filter((_, j) => j !== i) });

  const submit = async () => {
    if (!draft.name.trim()) {
      toast.error('Name required');
      return;
    }
    if (!draft.hazard_category) {
      toast.error('Pick a hazard category');
      return;
    }
    setSaving(true);
    try {
      const body = {
        name: draft.name.trim(),
        hazard_category: draft.hazard_category,
        validity_hours: Number(draft.validity_hours) || 8,
        hazards: draft.hazards.map((s) => s.trim()).filter(Boolean),
        controls: draft.controls.map((s) => s.trim()).filter(Boolean),
        active: true,
      };
      await axios.post(`${API}/svc/compliance/ptw/templates`, body, auth());
      toast.success('Template added');
      setDraft(emptyPtwDraft());
      await load();
    } catch (e) {
      toast.error('Save failed', { description: e?.response?.data?.detail || e.message });
    } finally { setSaving(false); }
  };

  const doDelete = async (row) => {
    setSaving(true);
    try {
      await axios.delete(`${API}/svc/compliance/ptw/templates/${row.id}`, auth());
      toast.success('Template removed');
      setConfirmDelete(null);
      await load();
    } catch (e) {
      toast.error('Delete failed', { description: e?.response?.data?.detail || e.message });
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-5" data-testid="ptw-admin">
      <section className="rounded-2xl border border-slate-200 bg-white p-4">
        <p className="text-sm font-bold text-slate-900 mb-2">Add a template</p>
        <div className="grid sm:grid-cols-3 gap-2">
          <input
            type="text"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="Template name (e.g. Confined Space)"
            className="px-3 py-2 rounded-lg border border-slate-200 text-sm"
            data-testid="ptw-draft-name"
          />
          <select
            value={draft.hazard_category}
            onChange={(e) => setDraft({ ...draft, hazard_category: e.target.value })}
            className="px-3 py-2 rounded-lg border border-slate-200 text-sm"
            data-testid="ptw-draft-category"
          >
            <option value="">Hazard category…</option>
            {categories.map((c) => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
          </select>
          <input
            type="number"
            min={1}
            max={72}
            value={draft.validity_hours}
            onChange={(e) => setDraft({ ...draft, validity_hours: e.target.value })}
            placeholder="Validity (hours)"
            className="px-3 py-2 rounded-lg border border-slate-200 text-sm"
            data-testid="ptw-draft-validity"
          />
        </div>
        <div className="grid sm:grid-cols-2 gap-3 mt-3">
          <DraftListEditor
            label="Hazards"
            items={draft.hazards}
            setItem={setDraftHazard}
            addItem={addDraftHazard}
            removeItem={removeDraftHazard}
            testIdPrefix="ptw-draft-hazard"
          />
          <DraftListEditor
            label="Controls"
            items={draft.controls}
            setItem={setDraftControl}
            addItem={addDraftControl}
            removeItem={removeDraftControl}
            testIdPrefix="ptw-draft-control"
          />
        </div>
        <div className="mt-3 flex justify-end">
          <button
            type="button"
            onClick={submit}
            disabled={saving}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold disabled:opacity-50"
            data-testid="ptw-draft-submit"
          >
            {saving ? <Loader2 size={14} className="animate-spin inline mr-1" /> : <Plus size={14} className="inline mr-1" />}
            Add template
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white">
        <header className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
          <p className="text-sm font-bold text-slate-900">Templates ({rows.length})</p>
          {loading && <Loader2 size={14} className="animate-spin text-slate-400" />}
        </header>
        {rows.length === 0 ? (
          <div className="p-6 text-sm text-slate-500" data-testid="ptw-empty">No templates yet.</div>
        ) : (
          <ul className="divide-y divide-slate-100" data-testid="ptw-list">
            {rows.map((r) => (
              <li key={r.id} className="p-3 flex items-start gap-3" data-testid={`ptw-row-${r.id}`}>
                <ShieldCheck size={14} className="text-blue-600 mt-1" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-slate-900">{r.name}</p>
                  <p className="text-xs text-slate-500">
                    {(r.hazard_category || '').replace(/_/g, ' ')} · valid {r.validity_hours}h ·{' '}
                    {(r.hazards || []).length} hazards · {(r.controls || []).length} controls
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setConfirmDelete(r)}
                  className="p-1.5 rounded text-rose-600 hover:bg-rose-50"
                  data-testid={`ptw-delete-${r.id}`}
                  aria-label="Delete template"
                >
                  <Trash2 size={13} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {confirmDelete && (
        <ConfirmModal
          title="Remove template?"
          subtitle={confirmDelete.name}
          warning="Existing PTW requests using this template are unaffected; only future requests can no longer pick it."
          onClose={() => setConfirmDelete(null)}
          onConfirm={() => doDelete(confirmDelete)}
          testId="ptw-confirm-delete"
        />
      )}
    </div>
  );
}

function emptyPtwDraft() {
  return { name: '', hazard_category: '', validity_hours: 8, hazards: [''], controls: [''] };
}

function DraftListEditor({ label, items, setItem, addItem, removeItem, testIdPrefix }) {
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500 mb-1">{label}</p>
      <ul className="space-y-1">
        {items.map((v, i) => (
          <li key={i} className="flex items-center gap-1">
            <input
              type="text"
              value={v}
              onChange={(e) => setItem(i, e.target.value)}
              placeholder={`${label.slice(0, -1)} ${i + 1}`}
              className="flex-1 px-2 py-1 rounded border border-slate-200 text-xs"
              data-testid={`${testIdPrefix}-${i}`}
            />
            <button
              type="button"
              onClick={() => removeItem(i)}
              className="p-1 text-slate-400 hover:text-rose-600"
              data-testid={`${testIdPrefix}-remove-${i}`}
              aria-label={`Remove ${label.slice(0, -1)}`}
            >
              <X size={12} />
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={addItem}
        className="mt-1 text-[10px] font-bold uppercase tracking-wide text-blue-600 hover:text-blue-800"
        data-testid={`${testIdPrefix}-add`}
      >
        + Add {label.slice(0, -1).toLowerCase()}
      </button>
    </div>
  );
}

// ═══ COSHH register ══════════════════════════════════════════════

function CoshhAdmin() {
  const [rows, setRows] = useState([]);
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState(emptyCoshhDraft());
  const [confirmDelete, setConfirmDelete] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/compliance/coshh`, auth());
      setRows(r.data?.items || []);
      setClasses(r.data?.hazard_classes || []);
    } catch (e) {
      toast.error('Could not load COSHH register', { description: e?.response?.data?.detail || e.message });
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    if (!draft.name.trim()) {
      toast.error('Name required');
      return;
    }
    if (!draft.hazard_class) {
      toast.error('Pick a hazard class');
      return;
    }
    setSaving(true);
    try {
      await axios.post(`${API}/svc/compliance/coshh`, {
        name: draft.name.trim(),
        supplier: draft.supplier.trim(),
        hazard_class: draft.hazard_class,
        controls: draft.controls.trim(),
        sds_url: draft.sds_url.trim() || null,
        active: true,
      }, auth());
      toast.success('COSHH entry added');
      setDraft(emptyCoshhDraft());
      await load();
    } catch (e) {
      toast.error('Save failed', { description: e?.response?.data?.detail || e.message });
    } finally { setSaving(false); }
  };

  const doDelete = async (row) => {
    setSaving(true);
    try {
      await axios.delete(`${API}/svc/compliance/coshh/${row.id}`, auth());
      toast.success('Entry retired');
      setConfirmDelete(null);
      await load();
    } catch (e) {
      toast.error('Delete failed', { description: e?.response?.data?.detail || e.message });
    } finally { setSaving(false); }
  };

  const activeRows = rows.filter((r) => r.active !== false);

  return (
    <div className="space-y-5" data-testid="coshh-admin">
      <section className="rounded-2xl border border-slate-200 bg-white p-4">
        <p className="text-sm font-bold text-slate-900 mb-2">Add a chemical</p>
        <div className="grid sm:grid-cols-2 gap-2">
          <input
            type="text"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="Name (e.g. Brake cleaner)"
            className="px-3 py-2 rounded-lg border border-slate-200 text-sm"
            data-testid="coshh-draft-name"
          />
          <input
            type="text"
            value={draft.supplier}
            onChange={(e) => setDraft({ ...draft, supplier: e.target.value })}
            placeholder="Supplier"
            className="px-3 py-2 rounded-lg border border-slate-200 text-sm"
            data-testid="coshh-draft-supplier"
          />
          <select
            value={draft.hazard_class}
            onChange={(e) => setDraft({ ...draft, hazard_class: e.target.value })}
            className="px-3 py-2 rounded-lg border border-slate-200 text-sm"
            data-testid="coshh-draft-class"
          >
            <option value="">Hazard class…</option>
            {classes.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <input
            type="url"
            value={draft.sds_url}
            onChange={(e) => setDraft({ ...draft, sds_url: e.target.value })}
            placeholder="SDS URL (optional)"
            className="px-3 py-2 rounded-lg border border-slate-200 text-sm"
            data-testid="coshh-draft-sds"
          />
        </div>
        <textarea
          value={draft.controls}
          onChange={(e) => setDraft({ ...draft, controls: e.target.value })}
          rows={2}
          placeholder="Controls (PPE, ventilation, exposure limits)"
          className="w-full mt-2 px-3 py-2 rounded-lg border border-slate-200 text-sm"
          data-testid="coshh-draft-controls"
        />
        <div className="mt-3 flex justify-end">
          <button
            type="button"
            onClick={submit}
            disabled={saving}
            className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm font-bold disabled:opacity-50"
            data-testid="coshh-draft-submit"
          >
            {saving ? <Loader2 size={14} className="animate-spin inline mr-1" /> : <Plus size={14} className="inline mr-1" />}
            Add chemical
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white">
        <header className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
          <p className="text-sm font-bold text-slate-900">
            Register ({activeRows.length} active / {rows.length} total)
          </p>
          {loading && <Loader2 size={14} className="animate-spin text-slate-400" />}
        </header>
        {rows.length === 0 ? (
          <div className="p-6 text-sm text-slate-500" data-testid="coshh-empty">No entries yet.</div>
        ) : (
          <ul className="divide-y divide-slate-100" data-testid="coshh-list">
            {rows.map((r) => (
              <li
                key={r.id}
                className={`p-3 flex items-start gap-3 ${r.active === false ? 'opacity-50' : ''}`}
                data-testid={`coshh-row-${r.id}`}
              >
                <FlaskConical size={14} className="text-amber-600 mt-1" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-slate-900">
                    {r.name}
                    {r.active === false && (
                      <span className="ml-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">Retired</span>
                    )}
                  </p>
                  <p className="text-xs text-slate-500">
                    {r.hazard_class}
                    {r.supplier ? ` · ${r.supplier}` : ''}
                  </p>
                  {r.controls ? <p className="text-[11px] text-slate-500 leading-snug mt-0.5">{r.controls}</p> : null}
                  {r.sds_url ? (
                    <a
                      href={r.sds_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] text-blue-600 underline"
                      data-testid={`coshh-sds-${r.id}`}
                    >
                      View SDS
                    </a>
                  ) : null}
                </div>
                {r.active !== false && (
                  <button
                    type="button"
                    onClick={() => setConfirmDelete(r)}
                    className="p-1.5 rounded text-rose-600 hover:bg-rose-50"
                    data-testid={`coshh-delete-${r.id}`}
                    aria-label="Retire entry"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {confirmDelete && (
        <ConfirmModal
          title="Retire chemical?"
          subtitle={confirmDelete.name}
          warning="Engineers won't see this in the COSHH picker on new jobs. Past usage records remain unchanged."
          onClose={() => setConfirmDelete(null)}
          onConfirm={() => doDelete(confirmDelete)}
          testId="coshh-confirm-delete"
        />
      )}
    </div>
  );
}

function emptyCoshhDraft() {
  return { name: '', supplier: '', hazard_class: '', controls: '', sds_url: '' };
}

// ═══ shared modal ════════════════════════════════════════════════

function ConfirmModal({ title, subtitle, warning, onClose, onConfirm, testId }) {
  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/60 flex items-end sm:items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      data-testid={testId}
    >
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl p-5">
        <div className="flex items-start gap-2 mb-2">
          <AlertTriangle size={16} className="text-rose-600 mt-0.5" />
          <div>
            <p className="text-sm font-bold text-slate-900">{title}</p>
            <p className="text-xs text-slate-500 truncate">{subtitle}</p>
          </div>
        </div>
        <p className="text-xs text-slate-600 mb-3">{warning}</p>
        <div className="flex items-center justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 text-xs font-bold rounded bg-slate-100 text-slate-700 hover:bg-slate-200" data-testid={`${testId}-cancel`}>
            Cancel
          </button>
          <button onClick={onConfirm} className="px-3 py-1.5 text-xs font-bold rounded bg-rose-600 hover:bg-rose-700 text-white" data-testid={`${testId}-confirm`}>
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
