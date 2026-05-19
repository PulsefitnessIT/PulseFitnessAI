/**
 * PulseUpgradeRequestModal — in-app upgrade intent form.
 *
 * Replaces the mailto: behaviour on the Pulse Pro plan card with a
 * structured form that captures gym name, site count, equipment count,
 * preferred contact method and notes. POSTs to /api/pulse/upgrade-request
 * which persists the record and fans out two emails (Pulse service team
 * + platform owner).
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import {
 X as XIcon, ArrowRight, CheckCircle2, Loader2, Zap,
 Mail, Phone, Building2, MessageSquare,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import Turnstile from '@/components/shared/Turnstile';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const CONTACT_METHODS = [
 { value: 'email', label: 'Email', icon: Mail },
 { value: 'phone', label: 'Phone', icon: Phone },
 { value: 'either', label: 'Either', icon: MessageSquare },
];

export default function PulseUpgradeRequestModal({ open, onClose, seed = {} }) {
 const [form, setForm] = useState({
 full_name: '', email: '', phone: '',
 gym_name: '', site_count: 1, equipment_count: '',
 contact_method: 'email', notes: '',
 });
 const [loading, setLoading] = useState(false);
 const [done, setDone] = useState(false);
 const [captchaToken, setCaptchaToken] = useState('');

 // Seed from props when opened (e.g. pre-fill a logged-in user's name/email)
 useEffect(() => {
 if (!open) return;
 setForm((f) => ({
 ...f,
 full_name: seed.full_name || f.full_name,
 email: seed.email || f.email,
 gym_name: seed.gym_name || f.gym_name,
 }));
 }, [open, seed.full_name, seed.email, seed.gym_name]);

 useEffect(() => {
 if (!open) return undefined;
 const onKey = (e) => e.key === 'Escape' && onClose();
 window.addEventListener('keydown', onKey);
 return () => window.removeEventListener('keydown', onKey);
 }, [open, onClose]);

 useEffect(() => {
 if (!open) return undefined;
 const prev = document.body.style.overflow;
 document.body.style.overflow = 'hidden';
 return () => { document.body.style.overflow = prev; };
 }, [open]);

 useEffect(() => {
 if (!open) {
 // Reset for next open
 setForm({
 full_name: '', email: '', phone: '',
 gym_name: '', site_count: 1, equipment_count: '',
 contact_method: 'email', notes: '',
 });
 setDone(false);
 setCaptchaToken('');
 }
 }, [open]);

 const update = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

 const submit = async (e) => {
 e.preventDefault();
 if (!captchaToken) {
 notify.error('Please complete the anti-bot check');
 return;
 }
 setLoading(true);
 try {
 await axios.post(`${API}/pulse/upgrade-request`, {
 full_name: form.full_name.trim(),
 email: form.email.trim().toLowerCase(),
 phone: form.phone.trim() || undefined,
 gym_name: form.gym_name.trim(),
 site_count: parseInt(form.site_count, 10) || 1,
 equipment_count: form.equipment_count ? parseInt(form.equipment_count, 10) : undefined,
 contact_method: form.contact_method,
 notes: form.notes.trim() || undefined,
 cf_turnstile_response: captchaToken,
 });
 setDone(true);
 setTimeout(() => { onClose(); }, 2200);
 } catch (err) {
 notifyApiError(notify, err, 'Could not send request — please try again.');
 }
 setLoading(false);
 };

 if (!open) return null;

 return (
 <AnimatePresence>
 <motion.div
 initial={{ opacity: 0 }}
 animate={{ opacity: 1 }}
 exit={{ opacity: 0 }}
 className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
 onClick={onClose}
 data-testid="pulse-upgrade-modal-overlay"
 >
 <motion.div
 onClick={(e) => e.stopPropagation()}
 initial={{ opacity: 0, y: 20, scale: 0.98 }}
 animate={{ opacity: 1, y: 0, scale: 1 }}
 transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
 className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl overflow-hidden max-h-[92vh] flex flex-col"
 data-testid="pulse-upgrade-modal"
 >
 {/* Cyan accent header bar */}
 <div className="relative bg-gradient-to-br from-[var(--color-surface-dark-panel-alt)] to-[var(--color-dark-panel-3)] p-6 pb-5 border-b-4 border-[var(--pulse-primary)]">
 <div className="pointer-events-none absolute -top-20 -right-20 w-56 h-56 bg-[rgb(var(--rgb-pulse-primary)/0.25)] blur-[90px] rounded-full" />
 <div className="relative flex items-start justify-between gap-4">
 <div>
 <div className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--pulse-primary)] mb-2">
 <Zap size={11} /> Pulse Pro · Upgrade
 </div>
 <h2 className="text-white text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.01em' }}>
 {done ? 'Request received' : 'Upgrade to Pulse Pro'}
 </h2>
 <p className="text-white/70 text-sm mt-1">
 {done
 ? 'Your Pulse Fitness account manager will be in touch shortly.'
 : 'Tell us about your estate and we\'ll be in touch with tailored pricing.'}
 </p>
 </div>
 <button
 onClick={onClose}
 type="button"
 className="p-1.5 rounded-md text-white/70 hover:text-white hover:bg-white/10 transition shrink-0"
 data-testid="pulse-upgrade-modal-close"
 >
 <XIcon size={18} />
 </button>
 </div>
 </div>

 {done ? (
 <div className="p-8 text-center" data-testid="pulse-upgrade-success">
 <div className="w-16 h-16 mx-auto rounded-full bg-emerald-50 border-2 border-emerald-200 flex items-center justify-center mb-4">
 <CheckCircle2 size={32} className="text-emerald-500" />
 </div>
 <h3 className="text-[var(--color-surface-dark-panel-alt)] font-extrabold text-xl">Thanks, {form.full_name.split(' ')[0]}.</h3>
 <p className="text-[var(--color-text-slate)] text-sm mt-2 max-w-sm mx-auto">
 Your request has been logged and emailed to the Pulse Fitness team. We'll get back to you by{' '}
 <span className="font-semibold text-[var(--color-surface-dark-panel-alt)]">
 {form.contact_method === 'either' ? 'email or phone' : form.contact_method}
 </span>{' '}
 within one working day.
 </p>
 </div>
 ) : (
 <form onSubmit={submit} className="flex-1 overflow-y-auto" data-testid="pulse-upgrade-form">
 <div className="p-6 space-y-4">
 {/* Contact details */}
 <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
 <Field label="Your name" required testId="upgrade-name">
 <input
 type="text" required
 value={form.full_name} onChange={update('full_name')}
 className="w-full h-11 px-3 rounded-lg bg-white border border-slate-200 text-[var(--color-surface-dark-panel-alt)] placeholder:text-slate-400 focus:outline-none focus:border-[var(--pulse-primary)] focus:ring-2 focus:ring-[rgb(var(--rgb-pulse-primary)/0.2)] transition"
 placeholder="Lee Somers"
 />
 </Field>
 <Field label="Work email" required testId="upgrade-email">
 <input
 type="email" required
 value={form.email} onChange={update('email')}
 className="w-full h-11 px-3 rounded-lg bg-white border border-slate-200 text-[var(--color-surface-dark-panel-alt)] placeholder:text-slate-400 focus:outline-none focus:border-[var(--pulse-primary)] focus:ring-2 focus:ring-[rgb(var(--rgb-pulse-primary)/0.2)] transition"
 placeholder="lee@yourgym.com"
 />
 </Field>
 </div>

 <Field label="Gym / organisation name" required testId="upgrade-gym">
 <div className="relative">
 <Building2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
 <input
 type="text" required
 value={form.gym_name} onChange={update('gym_name')}
 className="w-full h-11 pl-9 pr-3 rounded-lg bg-white border border-slate-200 text-[var(--color-surface-dark-panel-alt)] placeholder:text-slate-400 focus:outline-none focus:border-[var(--pulse-primary)] focus:ring-2 focus:ring-[rgb(var(--rgb-pulse-primary)/0.2)] transition"
 placeholder="Acme Fitness"
 />
 </div>
 </Field>

 {/* Estate size */}
 <div className="grid grid-cols-2 gap-3">
 <Field label="Sites" required testId="upgrade-sites">
 <input
 type="number" min={1} max={500} required
 value={form.site_count} onChange={update('site_count')}
 className="w-full h-11 px-3 rounded-lg bg-white border border-slate-200 text-[var(--color-surface-dark-panel-alt)] focus:outline-none focus:border-[var(--pulse-primary)] focus:ring-2 focus:ring-[rgb(var(--rgb-pulse-primary)/0.2)] transition"
 />
 </Field>
 <Field label="Equipment pieces (est.)" testId="upgrade-equipment">
 <input
 type="number" min={0} max={50000}
 value={form.equipment_count} onChange={update('equipment_count')}
 className="w-full h-11 px-3 rounded-lg bg-white border border-slate-200 text-[var(--color-surface-dark-panel-alt)] placeholder:text-slate-400 focus:outline-none focus:border-[var(--pulse-primary)] focus:ring-2 focus:ring-[rgb(var(--rgb-pulse-primary)/0.2)] transition"
 placeholder="e.g. 120"
 />
 </Field>
 </div>

 {/* Phone */}
 <Field label="Phone (optional)" testId="upgrade-phone">
 <div className="relative">
 <Phone size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
 <input
 type="tel"
 value={form.phone} onChange={update('phone')}
 className="w-full h-11 pl-9 pr-3 rounded-lg bg-white border border-slate-200 text-[var(--color-surface-dark-panel-alt)] placeholder:text-slate-400 focus:outline-none focus:border-[var(--pulse-primary)] focus:ring-2 focus:ring-[rgb(var(--rgb-pulse-primary)/0.2)] transition"
 placeholder="+44 7700 900000"
 />
 </div>
 </Field>

 {/* Preferred contact */}
 <div>
 <label className="text-[11px] font-bold text-[var(--color-text-slate)] uppercase tracking-wide mb-2 block">
 How should we get back to you?
 </label>
 <div className="grid grid-cols-3 gap-2" role="radiogroup" data-testid="upgrade-contact-method">
 {CONTACT_METHODS.map((m) => {
 const selected = form.contact_method === m.value;
 const Icon = m.icon;
 return (
 <button
 key={m.value}
 type="button"
 role="radio"
 aria-checked={selected}
 onClick={() => setForm((f) => ({ ...f, contact_method: m.value }))}
 className={`h-11 rounded-lg border-2 text-sm font-bold flex items-center justify-center gap-1.5 transition-all ${
 selected
 ? 'bg-[rgb(var(--rgb-pulse-primary)/0.1)] border-[var(--pulse-primary)] text-[var(--color-surface-dark-panel-alt)]'
 : 'bg-white border-slate-200 text-[var(--color-text-slate)] hover:border-slate-300'
 }`}
 data-testid={`upgrade-contact-${m.value}`}
 >
 <Icon size={13} /> {m.label}
 </button>
 );
 })}
 </div>
 </div>

 {/* Notes */}
 <Field label="Anything else we should know? (optional)" testId="upgrade-notes">
 <textarea
 rows={3}
 value={form.notes} onChange={update('notes')}
 className="w-full px-3 py-2.5 rounded-lg bg-white border border-slate-200 text-[var(--color-surface-dark-panel-alt)] placeholder:text-slate-400 focus:outline-none focus:border-[var(--pulse-primary)] focus:ring-2 focus:ring-[rgb(var(--rgb-pulse-primary)/0.2)] transition resize-none"
 placeholder="Number of engineers, existing suppliers, urgency, anything that helps us tailor the quote…"
 />
 </Field>

 {/* Turnstile captcha */}
 <div className="pt-1">
 <Turnstile
 onToken={setCaptchaToken}
 theme="light"
 testId="pulse-upgrade-turnstile"
 action="pulse_upgrade"
 />
 </div>
 </div>

 {/* Sticky submit bar */}
 <div className="sticky bottom-0 border-t border-slate-100 bg-white p-4">
 <button
 type="submit" disabled={loading}
 className="w-full h-12 rounded-lg font-bold text-sm transition flex items-center justify-center gap-2 disabled:opacity-60"
 style={{
 background: 'linear-gradient(135deg, var(--pulse-primary) 0%, var(--pulse-primary-deep) 100%)',
 color: 'var(--color-surface-darker)',
 letterSpacing: '0.05em',
 boxShadow: '0 6px 20px rgba(25,205,255,0.3)',
 }}
 data-testid="pulse-upgrade-submit"
 >
 {loading ? (
 <><Loader2 size={14} className="animate-spin" /> Sending…</>
 ) : (
 <><span className="uppercase">Send upgrade request</span> <ArrowRight size={14} /></>
 )}
 </button>
 <p className="text-[10px] text-[var(--color-text-slate)] text-center mt-2">
 We'll email both <span className="font-semibold text-[var(--color-surface-dark-panel-alt)]">Pulse Fitness</span> service team and your account manager.
 </p>
 </div>
 </form>
 )}
 </motion.div>
 </motion.div>
 </AnimatePresence>
 );
}


function Field({ label, children, required, testId }) {
 return (
 <div data-testid={testId}>
 <label className="text-[11px] font-bold text-[var(--color-text-slate)] uppercase tracking-wide mb-1.5 block">
 {label}{required && <span className="text-[var(--pulse-primary)] ml-0.5">*</span>}
 </label>
 {children}
 </div>
 );
}
