/**
 * EngineerFaultReportPage — Iter 275.
 *
 * Public, no-login page reached by scanning the QR sticker an engineer
 * attaches to a customer's machine (`/r/:equipmentId`). The customer
 * (who is NOT on the Operations portal) describes a fault; submitting
 * creates a case STRAIGHT in their engineer's job queue.
 *
 * Mirrors the operations QRScanPage UX but is engineer-branded (the
 * engineer's company name) and routes to `svc_cases`.
 */
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import {
  Wrench, Loader2, AlertTriangle, CheckCircle2, Camera, ShieldAlert,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

const SEVERITIES = [
  { value: 'low', label: 'Minor — still usable', cls: 'border-emerald-300 bg-emerald-50 text-emerald-800' },
  { value: 'medium', label: 'Faulty — not working right', cls: 'border-amber-300 bg-amber-50 text-amber-800' },
  { value: 'critical', label: 'Unsafe / broken — do not use', cls: 'border-rose-300 bg-rose-50 text-rose-800' },
];

export default function EngineerFaultReportPage() {
  const { equipmentId } = useParams();
  const [info, setInfo] = useState(null);
  const [loadErr, setLoadErr] = useState('');
  const [loading, setLoading] = useState(true);

  const [description, setDescription] = useState('');
  const [severity, setSeverity] = useState('medium');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [photo, setPhoto] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [formErr, setFormErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setLoadErr('');
    try {
      const r = await axios.get(`${API}/public/r/${equipmentId}`);
      setInfo(r.data);
    } catch (e) {
      setLoadErr(e?.response?.data?.detail || 'This machine could not be found.');
    } finally {
      setLoading(false);
    }
  }, [equipmentId]);

  useEffect(() => { load(); }, [load]);

  const submit = async (e) => {
    e?.preventDefault();
    setFormErr('');
    if (!description.trim()) { setFormErr('Please describe the fault.'); return; }
    if (!name.trim()) { setFormErr('Please tell us your name.'); return; }
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append('description', description.trim());
      fd.append('severity', severity);
      fd.append('reporter_name', name.trim());
      fd.append('reporter_phone', phone.trim());
      fd.append('reporter_email', email.trim());
      if (photo) fd.append('photo', photo);
      const r = await axios.post(`${API}/public/r/${equipmentId}/report-fault`, fd);
      setResult(r.data);
    } catch (e) {
      setFormErr(e?.response?.data?.detail || 'Could not submit. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const brand = info?.brand_name || 'Service Engineer';

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-400">
        <Loader2 size={18} className="animate-spin mr-2" /> Loading…
      </div>
    );
  }

  if (loadErr) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4" data-testid="qr-report-not-found">
        <div className="max-w-sm w-full bg-white rounded-2xl border border-slate-200 p-6 text-center">
          <AlertTriangle size={28} className="mx-auto text-amber-500 mb-3" />
          <p className="text-sm font-bold text-slate-900">Machine not found</p>
          <p className="text-xs text-slate-500 mt-1">{loadErr}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 pb-16" data-testid="engineer-fault-report-page">
      {/* Branded header */}
      <div className="bg-slate-900 text-white">
        <div className="max-w-md mx-auto px-5 py-5">
          <div className="flex items-center gap-2 text-orange-400 text-[11px] font-bold uppercase tracking-[0.2em]">
            <Wrench size={13} /> {brand}
          </div>
          <h1 className="text-xl font-extrabold mt-1" data-testid="qr-report-brand">{brand}</h1>
          <p className="text-slate-300 text-xs mt-0.5">Report a fault on this machine</p>
        </div>
      </div>

      <div className="max-w-md mx-auto px-5 -mt-3">
        {/* Machine card */}
        <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm" data-testid="qr-report-machine">
          <div className="flex items-start gap-3">
            <div className="w-11 h-11 rounded-xl bg-orange-50 flex items-center justify-center flex-shrink-0">
              <Wrench size={18} className="text-orange-600" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-bold text-slate-900 truncate">{info?.name || 'Machine'}</p>
              <p className="text-[11px] text-slate-500">
                {[info?.manufacturer, info?.model].filter(Boolean).join(' ')}
                {info?.serial_number ? ` · SN ${info.serial_number}` : ''}
              </p>
              {info?.location && <p className="text-[11px] text-slate-400 mt-0.5">{info.location}</p>}
            </div>
          </div>
        </div>

        {result ? (
          <div className="bg-white rounded-2xl border border-emerald-200 p-6 mt-4 text-center" data-testid="qr-report-success">
            <CheckCircle2 size={34} className="mx-auto text-emerald-500 mb-2" />
            <p className="text-sm font-bold text-slate-900">Thanks — fault reported</p>
            <p className="text-xs text-slate-500 mt-1">{result.message}</p>
            <p className="mt-3 inline-block px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 text-xs font-mono font-bold" data-testid="qr-report-reference">
              {result.reference}
            </p>
            {result.ai_triage?.diagnosis && (
              <div className="mt-4 text-left rounded-xl border border-slate-200 bg-slate-50 p-3" data-testid="qr-report-triage">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Quick assessment</p>
                <p className="text-xs text-slate-700 mt-1">{result.ai_triage.diagnosis}</p>
                {result.ai_triage.safety_note && (
                  <p className="text-[11px] text-rose-700 mt-1 flex items-start gap-1">
                    <ShieldAlert size={12} className="mt-0.5 flex-shrink-0" /> {result.ai_triage.safety_note}
                  </p>
                )}
              </div>
            )}
          </div>
        ) : (
          <form onSubmit={submit} className="mt-4 space-y-3" noValidate data-testid="qr-report-form">
            <Field label="What's wrong?" required>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="e.g. Belt slipping under load, console won't power on…"
                className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-orange-500 resize-none"
                data-testid="qr-report-description"
              />
            </Field>

            <Field label="How bad is it?">
              <div className="space-y-2">
                {SEVERITIES.map((s) => (
                  <button
                    key={s.value}
                    type="button"
                    onClick={() => setSeverity(s.value)}
                    className={`w-full text-left px-3 py-2.5 rounded-xl border text-sm font-semibold transition-colors ${
                      severity === s.value ? s.cls : 'border-slate-200 bg-white text-slate-600'
                    }`}
                    data-testid={`qr-report-severity-${s.value}`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </Field>

            <Field label="Your name" required>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={120}
                placeholder="So your engineer knows who to call"
                className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                data-testid="qr-report-name"
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Phone">
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  maxLength={40}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                  data-testid="qr-report-phone"
                />
              </Field>
              <Field label="Email">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  maxLength={160}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                  data-testid="qr-report-email"
                />
              </Field>
            </div>

            <label className="flex items-center gap-2 px-3 py-2.5 rounded-xl border border-dashed border-slate-300 bg-white text-sm text-slate-600 cursor-pointer" data-testid="qr-report-photo-label">
              <Camera size={16} className="text-slate-400" />
              {photo ? photo.name : 'Add a photo (optional)'}
              <input
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={(e) => setPhoto(e.target.files?.[0] || null)}
                data-testid="qr-report-photo"
              />
            </label>

            {formErr && (
              <p className="text-xs text-rose-600 font-semibold flex items-center gap-1" data-testid="qr-report-error">
                <AlertTriangle size={12} /> {formErr}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-orange-600 text-white text-sm font-bold disabled:opacity-50 hover:bg-orange-700"
              data-testid="qr-report-submit"
            >
              {submitting ? <><Loader2 size={15} className="animate-spin" /> Sending…</> : 'Send to my engineer'}
            </button>
            <p className="text-[10px] text-slate-400 text-center">
              Goes straight to {brand}. No account needed.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}

function Field({ label, required, children }) {
  return (
    <div>
      <label className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-1 flex items-center gap-1">
        {label}{required && <span className="text-rose-600">*</span>}
      </label>
      {children}
    </div>
  );
}
