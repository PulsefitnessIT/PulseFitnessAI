/**
 * Public — MOD Engineer Appointment Booking form (token-gated, no auth).
 *
 * Digital version of the paper "Appointment Booking" sheet Pulse Fitness
 * sends the MOD site contact to book an engineer onto a base. The MOD
 * contact confirms their details plus the visiting engineer's and vehicle
 * details for site access, then submits.
 */
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Loader2, ShieldCheck, CheckCircle2, Save, Send, Car, User, CalendarClock, Building2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const FIELD = 'w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#19398D]/40 focus:border-[#19398D]';
const LABEL = 'block text-xs font-semibold text-zinc-500 mb-1';

function Section({ icon: Icon, title, children }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 sm:p-5">
      <p className="text-sm font-bold text-zinc-900 flex items-center gap-2 mb-3"><Icon size={16} className="text-[#19398D]" /> {title}</p>
      <div className="grid sm:grid-cols-2 gap-3">{children}</div>
    </div>
  );
}
function Field({ label, k, form, set, type = 'text', full = false, placeholder = '' }) {
  return (
    <div className={full ? 'sm:col-span-2' : ''}>
      <label className={LABEL}>{label}</label>
      <input type={type} value={form[k] || ''} placeholder={placeholder}
        onChange={(e) => set(k, e.target.value)} className={FIELD} data-testid={`booking-${k}`} />
    </div>
  );
}

export default function MODVisitBookingForm() {
  const { token } = useParams();
  const [ctx, setCtx] = useState(null);
  const [form, setForm] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/public/mod-booking/${token}`);
      setCtx(r.data);
      setForm(r.data.form || {});
      if (r.data.status === 'submitted') setDone(true);
    } catch (e) { setError(e?.response?.data?.detail || 'This booking form could not be found.'); }
    finally { setLoading(false); }
  }, [token]);
  useEffect(() => { load(); }, [load]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const saveDraft = async () => {
    setSaving(true); setError('');
    try { await axios.put(`${API}/public/mod-booking/${token}`, { form }); }
    catch (e) { setError(e?.response?.data?.detail || 'Could not save your draft — please try again.'); }
    finally { setSaving(false); }
  };

  const submit = async () => {
    setSubmitting(true); setError('');
    try {
      const r = await axios.post(`${API}/public/mod-booking/${token}/submit`, { form });
      setForm(r.data.form || form);
      setDone(true);
    } catch (e) { setError(e?.response?.data?.detail || 'Could not submit — please check the required fields.'); }
    finally { setSubmitting(false); }
  };

  if (loading) return <div className="min-h-screen grid place-items-center bg-zinc-50"><Loader2 className="animate-spin text-[#19398D]" size={28} /></div>;
  if (error && !ctx) return <div className="min-h-screen grid place-items-center bg-zinc-50 p-6"><div className="max-w-md text-center"><p className="text-lg font-bold text-zinc-900">Booking form unavailable</p><p className="text-sm text-zinc-500 mt-2">{error}</p></div></div>;

  return (
    <div className="min-h-screen bg-zinc-50" data-testid="mod-booking-page">
      <div className="bg-[#19398D] text-white">
        <div className="max-w-2xl mx-auto px-5 py-8 text-center">
          <p className="text-[11px] uppercase tracking-[2px] text-[#9fc2ff] mb-1">Pulse Fitness · Ministry of Defence</p>
          <h1 className="text-2xl font-black tracking-tight">Engineer Appointment Booking</h1>
          {ctx?.site_name && <p className="text-sm text-white/80 mt-1">{ctx.site_name}{ctx.visit_scheduled_date ? ` · proposed ${ctx.visit_scheduled_date}` : ''}</p>}
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-5 py-6">
        {done ? (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-8 text-center" data-testid="booking-done">
            <CheckCircle2 size={40} className="text-emerald-500 mx-auto mb-3" />
            <p className="text-lg font-black text-emerald-900">Booking submitted</p>
            <p className="text-sm text-emerald-800/80 mt-1">Thank you — the Pulse Fitness MOD Service team has been notified and will confirm the engineer's visit.</p>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-zinc-600 bg-white rounded-xl border border-zinc-200 p-4">
              Please complete this form so we can book our engineer onto site. Vehicle and visitor details are needed for base access. Your progress saves as you go.
            </p>

            <Section icon={Building2} title="Requested by — Pulse Fitness Service">
              <Field label="Name" k="requested_by_name" form={form} set={set} />
              <Field label="Email" k="requested_by_email" form={form} set={set} type="email" />
            </Section>

            <Section icon={User} title="MOD Contact">
              <Field label="Name *" k="mod_contact_name" form={form} set={set} />
              <Field label="Email address *" k="mod_contact_email" form={form} set={set} type="email" />
              <Field label="Phone number" k="mod_contact_phone" form={form} set={set} full />
            </Section>

            <Section icon={CalendarClock} title="Visit Details">
              <Field label="Start date" k="visit_start_date" form={form} set={set} type="date" />
              <Field label="Predicted start time" k="visit_start_time" form={form} set={set} type="time" />
              <Field label="End date" k="visit_end_date" form={form} set={set} type="date" />
              <Field label="Predicted end time" k="visit_end_time" form={form} set={set} type="time" />
            </Section>

            <Section icon={User} title="Engineer / Visitor Details">
              <Field label="Name" k="engineer_name" form={form} set={set} />
              <Field label="Date of birth" k="engineer_dob" form={form} set={set} type="date" />
              <Field label="Phone" k="engineer_phone" form={form} set={set} full />
            </Section>

            <Section icon={Car} title="Vehicle Details">
              <Field label="Vehicle registration" k="veh_reg" form={form} set={set} />
              <Field label="Make" k="veh_make" form={form} set={set} />
              <Field label="Model" k="veh_model" form={form} set={set} />
              <Field label="Colour" k="veh_colour" form={form} set={set} />
            </Section>

            {error && <p className="text-sm text-rose-600 font-medium" data-testid="booking-error">{error}</p>}

            <div className="flex items-center justify-end gap-2 pt-1">
              <button onClick={saveDraft} disabled={saving} className="inline-flex items-center gap-1.5 text-sm font-semibold px-4 py-2.5 rounded-lg border border-zinc-300 bg-white hover:bg-zinc-50 disabled:opacity-50" data-testid="booking-save-draft">
                {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Save draft
              </button>
              <button onClick={submit} disabled={submitting} className="inline-flex items-center gap-1.5 text-sm font-bold px-5 py-2.5 rounded-lg bg-[#19398D] text-white hover:opacity-90 disabled:opacity-50" data-testid="booking-submit">
                {submitting ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />} Submit booking
              </button>
            </div>
            <p className="text-[11px] text-zinc-400 text-center flex items-center justify-center gap-1"><ShieldCheck size={12} /> Secure MOD appointment booking · Pulse Fitness AI</p>
          </div>
        )}
      </div>
    </div>
  );
}
