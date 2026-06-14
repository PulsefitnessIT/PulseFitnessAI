/**
 * EngineerMachineHistory — Iter 276.
 *
 * Read-only service history for a machine an engineer reached by scanning
 * an Operations-portal QR sticker (`/scan/{id}`) or their own
 * `/r/eq/{id}` sticker. Shows previous jobs, parts fitted and which
 * engineers worked on it. Access is gated server-side (own org / operator
 * engineer / has worked on it) → a 403 renders a friendly lockout.
 */
import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  ArrowLeft, Loader2, Wrench, Lock, AlertTriangle, Package,
  Users, ClipboardList, Calendar, ShieldCheck, Send, CheckCircle2,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const STATUS_TONE = {
  new: 'bg-slate-100 text-slate-600',
  assigned: 'bg-blue-50 text-blue-700',
  en_route: 'bg-indigo-50 text-indigo-700',
  on_site: 'bg-violet-50 text-violet-700',
  completed: 'bg-emerald-50 text-emerald-700',
  closed: 'bg-emerald-50 text-emerald-700',
  cancelled: 'bg-rose-50 text-rose-700',
};

function fmtDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      day: 'numeric', month: 'short', year: 'numeric',
    });
  } catch { return ''; }
}

export default function EngineerMachineHistory() {
  const { equipmentId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState(0);
  const [errMsg, setErrMsg] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setStatus(0);
    setErrMsg('');
    try {
      const r = await axios.get(`${API}/svc/engineer/machine-history/${equipmentId}`, auth());
      setData(r.data);
    } catch (e) {
      setStatus(e?.response?.status || 500);
      setErrMsg(e?.response?.data?.detail || 'Could not load this machine.');
    } finally {
      setLoading(false);
    }
  }, [equipmentId]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-machine-history">
      <div className="bg-white border-b border-slate-100 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center gap-2">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="w-9 h-9 rounded-xl border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-50"
            data-testid="machine-history-back"
            aria-label="Back"
          >
            <ArrowLeft size={16} />
          </button>
          <div className="min-w-0">
            <p className="text-sm font-bold text-slate-900 truncate">Machine history</p>
            <p className="text-[11px] text-slate-400">Scanned from an Operations QR · read-only</p>
          </div>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 py-4">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-slate-400">
            <Loader2 size={16} className="animate-spin mr-2" /> Loading history…
          </div>
        ) : status === 403 ? (
          <div className="bg-white rounded-2xl border border-amber-200 p-6 text-center" data-testid="machine-history-forbidden">
            <Lock size={28} className="mx-auto text-amber-500 mb-3" />
            <p className="text-sm font-bold text-slate-900">No access to this machine</p>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">{errMsg}</p>
            <RequestAccess equipmentId={equipmentId} />
          </div>
        ) : status ? (
          <div className="bg-rose-50 border border-rose-200 rounded-2xl p-4 text-sm text-rose-700 flex items-start gap-2" data-testid="machine-history-error">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" /> {errMsg}
          </div>
        ) : data ? (
          <div className="space-y-4">
            {/* Machine card */}
            <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="machine-history-machine">
              <div className="flex items-start gap-3">
                <div className="w-11 h-11 rounded-xl bg-orange-50 flex items-center justify-center flex-shrink-0">
                  <Wrench size={18} className="text-orange-600" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-base font-bold text-slate-900 truncate">{data.equipment?.name || 'Machine'}</p>
                  <p className="text-[11px] text-slate-500">
                    {[data.equipment?.manufacturer, data.equipment?.model].filter(Boolean).join(' ')}
                    {data.equipment?.serial_number ? ` · SN ${data.equipment.serial_number}` : ''}
                  </p>
                  {data.operator_name && (
                    <p className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-1">
                      <ShieldCheck size={11} /> {data.operator_name}
                      {data.equipment?.location ? ` · ${data.equipment.location}` : ''}
                    </p>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2 mt-4">
                <Stat icon={ClipboardList} label="Jobs" value={data.stats?.total_jobs} />
                <Stat icon={Package} label="Parts fitted" value={data.stats?.total_parts} />
                <Stat icon={Users} label="Engineers" value={data.stats?.engineers} />
              </div>
            </div>

            {/* Engineers who worked on it */}
            {data.engineers?.length > 0 && (
              <Section title="Who's worked on it" icon={Users} testid="machine-history-engineers">
                <div className="space-y-1.5">
                  {data.engineers.map((e) => (
                    <div key={e.name} className="flex items-center justify-between text-sm" data-testid="machine-history-engineer-row">
                      <span className="font-semibold text-slate-800">{e.name}</span>
                      <span className="text-[11px] text-slate-400">
                        {e.jobs} job{e.jobs === 1 ? '' : 's'} · last {fmtDate(e.last)}
                      </span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Parts fitted */}
            {data.parts?.length > 0 && (
              <Section title="Parts fitted" icon={Package} testid="machine-history-parts">
                <div className="space-y-1.5">
                  {data.parts.map((p, i) => (
                    <div key={i} className="flex items-center justify-between text-sm">
                      <span className="text-slate-800 truncate">
                        {p.qty > 1 ? `${p.qty}× ` : ''}{p.part_name}
                        {p.part_sku ? <span className="text-slate-400"> · {p.part_sku}</span> : null}
                      </span>
                      <span className="text-[11px] text-slate-400 shrink-0 ml-2">
                        {p.case_reference} · {fmtDate(p.fitted_at)}
                      </span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Job timeline */}
            <Section title="Service history" icon={ClipboardList} testid="machine-history-jobs">
              {data.jobs?.length === 0 ? (
                <p className="text-sm text-slate-400 py-2">No previous jobs logged on this machine.</p>
              ) : (
                <div className="space-y-2">
                  {data.jobs.map((j) => (
                    <div key={j.id} className="rounded-xl border border-slate-100 p-3" data-testid="machine-history-job-row">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-bold text-slate-900 truncate">{j.title || j.reference}</span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full shrink-0 ${STATUS_TONE[j.status] || 'bg-slate-100 text-slate-600'}`}>
                          {(j.status || '').replace(/_/g, ' ')}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500 mt-0.5 flex items-center gap-1.5 flex-wrap">
                        <span className="font-mono">{j.reference}</span>
                        <Calendar size={10} /> {fmtDate(j.created_at)}
                        {j.engineer ? <span>· {j.engineer}</span> : null}
                      </p>
                      {j.fault && <p className="text-xs text-slate-600 mt-1.5">{j.fault}</p>}
                      {j.parts?.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {j.parts.map((p, i) => (
                            <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                              {p.qty > 1 ? `${p.qty}× ` : ''}{p.part_name}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Stat({ icon: Icon, label, value }) {
  return (
    <div className="rounded-xl bg-slate-50 p-2.5 text-center">
      <Icon size={14} className="mx-auto text-slate-400" />
      <p className="text-lg font-extrabold text-slate-900 mt-0.5">{value ?? 0}</p>
      <p className="text-[10px] text-slate-400 uppercase tracking-wide">{label}</p>
    </div>
  );
}

function Section({ title, icon: Icon, testid, children }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid={testid}>
      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2 flex items-center gap-1.5">
        <Icon size={12} /> {title}
      </p>
      {children}
    </div>
  );
}

function RequestAccess({ equipmentId }) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState('');
  const [err, setErr] = useState('');

  const submit = async () => {
    setBusy(true);
    setErr('');
    try {
      const r = await axios.post(
        `${API}/svc/engineer/machine-history/${equipmentId}/request-access`,
        { message: message.trim() },
        auth(),
      );
      setDone(r.data?.message || 'Request sent.');
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Could not send request.');
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div className="mt-4 flex flex-col items-center gap-1 text-emerald-700" data-testid="request-access-done">
        <CheckCircle2 size={20} />
        <p className="text-xs font-semibold">{done}</p>
      </div>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-bold hover:bg-slate-800"
        data-testid="request-access-btn"
      >
        <Send size={13} /> Request access
      </button>
    );
  }

  return (
    <div className="mt-4 text-left" data-testid="request-access-form">
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={2}
        maxLength={500}
        placeholder="Optional: who you are / why you need access"
        className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 resize-none"
        data-testid="request-access-message"
      />
      {err && <p className="text-[11px] text-rose-600 mt-1">{err}</p>}
      <div className="flex gap-2 mt-2">
        <button
          type="button"
          onClick={submit}
          disabled={busy}
          className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-orange-600 text-white text-xs font-bold disabled:opacity-50 hover:bg-orange-700"
          data-testid="request-access-submit"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Send to operator
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="px-3 py-2 rounded-xl border border-slate-200 text-slate-600 text-xs font-bold"
          data-testid="request-access-cancel"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
