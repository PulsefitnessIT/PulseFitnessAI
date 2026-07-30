/**
 * PUBLIC (no-auth) MOD equipment self-capture form.
 * A site fills in its own equipment at /mod-capture/:token. Nothing is
 * imported until Pulse Fitness reviews & confirms the submission.
 */
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Plus, Trash2, Loader2, Send, Save, CheckCircle2, ShieldCheck, AlertCircle, Dumbbell,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const StatusBanner = ({ status, notes }) => {
  if (status === 'submitted') {
    return (
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex items-start gap-3" data-testid="capture-status-submitted">
        <CheckCircle2 className="text-emerald-600 mt-0.5" size={18} />
        <div>
          <p className="font-bold text-emerald-800 text-sm">Submitted to Pulse Fitness</p>
          <p className="text-xs text-emerald-700 mt-0.5">Thank you. Your equipment list is with Pulse Fitness for review — nothing is added to the platform until they confirm it. You'll be contacted if anything needs changing.</p>
        </div>
      </div>
    );
  }
  if (status === 'changes_requested' && notes) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 flex items-start gap-3" data-testid="capture-status-changes">
        <AlertCircle className="text-amber-600 mt-0.5" size={18} />
        <div>
          <p className="font-bold text-amber-800 text-sm">Changes requested by Pulse Fitness</p>
          <p className="text-xs text-amber-700 mt-0.5">{notes}</p>
        </div>
      </div>
    );
  }
  return null;
};

export default function MODEquipmentCaptureForm() {
  const { token } = useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [meta, setMeta] = useState(null);      // { site_name, status, fields, review_notes }
  const [rows, setRows] = useState([]);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/public/mod-capture/${token}`);
      setMeta(data);
      setRows(data.rows?.length ? data.rows : [{}]);
    } catch (e) {
      setError(e?.response?.data?.detail || 'This capture link is invalid or has expired.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const editable = meta && (meta.status === 'open' || meta.status === 'changes_requested');

  const setCell = (i, key, val) => setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)));
  const addRow = () => setRows((rs) => [...rs, {}]);
  const removeRow = (i) => setRows((rs) => (rs.length > 1 ? rs.filter((_, idx) => idx !== i) : rs));

  const save = async (silent = false) => {
    setSaving(true);
    try {
      const clean = rows.filter((r) => Object.values(r).some((v) => (v ?? '').toString().trim()));
      const { data } = await axios.put(`${API}/public/mod-capture/${token}`, { rows: clean });
      setMeta(data);
      if (!silent) toast.success('Draft saved');
      return true;
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not save');
      return false;
    } finally {
      setSaving(false);
    }
  };

  const submit = async () => {
    const named = rows.filter((r) => (r.name || '').trim());
    if (!named.length) { toast.error('Add at least one machine with a name'); return; }
    setSubmitting(true);
    try {
      if (!(await save(true))) return;
      const { data } = await axios.post(`${API}/public/mod-capture/${token}/submit`);
      toast.success(data.message || 'Submitted for review');
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not submit');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="min-h-screen grid place-items-center text-zinc-500"><Loader2 className="animate-spin" /></div>;
  }
  if (error) {
    return (
      <div className="min-h-screen grid place-items-center p-6" data-testid="capture-error">
        <div className="text-center max-w-sm">
          <AlertCircle className="mx-auto text-zinc-400 mb-3" size={32} />
          <p className="text-zinc-700 font-semibold">{error}</p>
        </div>
      </div>
    );
  }

  const fields = meta.fields || [];

  return (
    <div className="min-h-screen bg-zinc-50" data-testid="mod-capture-form">
      <div className="bg-[#19398D] text-white">
        <div className="max-w-5xl mx-auto px-5 py-6">
          <div className="flex items-center gap-2 text-white/80 text-xs font-semibold uppercase tracking-wider">
            <ShieldCheck size={14} /> Pulse Fitness · MOD equipment capture
          </div>
          <h1 className="text-2xl font-extrabold mt-1">{meta.site_name}</h1>
          <p className="text-white/80 text-sm mt-1 max-w-2xl">
            List every piece of gym equipment at your site. Add one row per machine. When you're done, submit it —
            Pulse Fitness will review and confirm before anything goes live.
          </p>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-5 py-6 space-y-4">
        <StatusBanner status={meta.status} notes={meta.review_notes} />

        {rows.map((row, i) => (
          <div key={i} className="bg-white rounded-xl border border-zinc-200 p-4" data-testid={`capture-row-${i}`}>
            <div className="flex items-center justify-between mb-3">
              <span className="inline-flex items-center gap-2 text-sm font-bold text-zinc-700">
                <Dumbbell size={15} className="text-[#19398D]" /> Machine {i + 1}
              </span>
              {editable && (
                <button onClick={() => removeRow(i)} className="text-zinc-400 hover:text-red-500 p-1" aria-label="Remove machine" data-testid={`capture-remove-${i}`}>
                  <Trash2 size={15} />
                </button>
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {fields.map((f) => (
                <label key={f.key} className="block">
                  <span className="text-[11px] font-semibold text-zinc-500 flex items-center gap-1">
                    {f.label}{f.required && <span className="text-red-500">*</span>}
                  </span>
                  {f.options ? (
                    <select
                      disabled={!editable}
                      value={row[f.key] || ''}
                      onChange={(e) => setCell(i, f.key, e.target.value)}
                      data-testid={`capture-input-${f.key}-${i}`}
                      className="mt-1 w-full px-2.5 py-1.5 rounded-lg border border-zinc-200 text-sm bg-white focus:outline-none focus:border-[#19398D] disabled:bg-zinc-100"
                    >
                      <option value="">—</option>
                      {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input
                      type="text"
                      disabled={!editable}
                      value={row[f.key] || ''}
                      placeholder={f.example || ''}
                      onChange={(e) => setCell(i, f.key, e.target.value)}
                      data-testid={`capture-input-${f.key}-${i}`}
                      className="mt-1 w-full px-2.5 py-1.5 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-[#19398D] disabled:bg-zinc-100"
                    />
                  )}
                </label>
              ))}
            </div>
          </div>
        ))}

        {editable && (
          <>
            <button onClick={addRow} data-testid="capture-add-row"
              className="w-full py-3 rounded-xl border-2 border-dashed border-zinc-300 text-zinc-500 hover:border-[#19398D] hover:text-[#19398D] font-semibold text-sm inline-flex items-center justify-center gap-2 transition-colors">
              <Plus size={16} /> Add another machine
            </button>

            <div className="sticky bottom-0 bg-zinc-50/90 backdrop-blur py-3 flex flex-wrap items-center justify-end gap-2 border-t border-zinc-200">
              <button onClick={() => save(false)} disabled={saving} data-testid="capture-save"
                className="px-4 py-2.5 rounded-lg border border-zinc-300 text-zinc-700 font-semibold text-sm inline-flex items-center gap-2 disabled:opacity-50">
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save draft
              </button>
              <button onClick={submit} disabled={submitting} data-testid="capture-submit"
                className="px-5 py-2.5 rounded-lg bg-[#19398D] text-white font-bold text-sm inline-flex items-center gap-2 disabled:opacity-50">
                {submitting ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Submit for review
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
