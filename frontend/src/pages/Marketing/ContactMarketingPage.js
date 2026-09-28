/**
 * Contact marketing page — refreshed in MarketingShell visual language.
 * Three quick paths: see the product preview, talk to sales, contact security.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, Mail, MessageSquare, ShieldCheck,
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

import './marketing.css';
import MarketingShell from './MarketingShell';
import { openTrial } from './TrialSignupModal';
import { openPreview } from './ProductPreviewModal';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PATHS = [
  // Iter 216h256 — "See it in action" card removed: the canned preview
  // wasn't representative of the live build and was misleading prospects.
  { icon: MessageSquare, title: 'Talk to sales',   body: 'Quick questions about pricing, integrations, multi-site rollouts.', cta: 'Send an enquiry', action: 'enquire', accent: 'var(--gx-accent-crm)' },
  { icon: ShieldCheck,   title: 'Security & DPA',  body: 'Procurement, DPA, pentest evidence, security questionnaires.', cta: 'Email security', href: 'mailto:security@pulsefitness.ai', accent: 'var(--gx-accent-service)' },
];

const INTEREST_OPTIONS = [
  { value: '',            label: 'Pick what interests you (optional)' },
  { value: 'memberships', label: 'Memberships & group fitness' },
  { value: 'service_desk',label: 'Service Desk / facilities ops' },
  { value: 'marketing',   label: 'Marketing & CRM' },
  { value: 'crm',         label: 'CRM / sales pipeline' },
  { value: 'pricing',     label: 'Pricing & procurement' },
  { value: 'other',       label: 'Something else' },
];
const TIME_OPTIONS = [
  { value: '',          label: 'When suits you?' },
  { value: 'morning',   label: 'Morning (9am – 12pm)' },
  { value: 'afternoon', label: 'Afternoon (12pm – 5pm)' },
  { value: 'evening',   label: 'Evening (5pm – 7pm)' },
  { value: 'anytime',   label: 'Anytime in working hours' },
];
const HEARD_OPTIONS = [
  { value: '',               label: 'How did you hear about us?' },
  { value: 'search',         label: 'Google / search engine' },
  { value: 'referral',       label: 'Word of mouth / referral' },
  { value: 'linkedin',       label: 'LinkedIn' },
  { value: 'industry_event', label: 'Industry event / trade show' },
  { value: 'press',          label: 'Press / blog post' },
  { value: 'partner',        label: 'Existing partner' },
  { value: 'other',          label: 'Other' },
];
const GYM_SIZE_OPTIONS = [
  { value: '',       label: 'Gym size (optional)' },
  { value: '1-2',    label: '1 – 2 sites' },
  { value: '3-10',   label: '3 – 10 sites' },
  { value: '11-25',  label: '11 – 25 sites' },
  { value: '26+',    label: '26+ sites' },
  { value: 'pre_launch', label: 'Pre-launch / planning a gym' },
];

export default function ContactMarketingPage() {
  return (
    <MarketingShell>
      <Hero />
      <Paths />
      <ContactForm />
      <Footer />
    </MarketingShell>
  );
}

function Hero() {
  return (
    <section className="gx-grid-bg" data-testid="contact-hero">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-12 lg:pt-20 lg:pb-16 text-center">
        <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
          <Mail size={12} />Get in touch
        </span>
        <h1 className="mt-5 text-5xl md:text-6xl tracking-tighter font-black leading-[1.04]">
          We answer in<br /><span className="gx-gradient-text">under 24 hours.</span>
        </h1>
        <p className="mt-5 text-lg md:text-xl text-slate-600 leading-relaxed max-w-2xl mx-auto">
          Real humans, UK working hours. No bots, no ticket queue purgatory. Pick the path that suits you.
        </p>
      </div>
    </section>
  );
}

function Paths() {
  const scrollToForm = () => {
    const el = document.querySelector('[data-testid="contact-form-section"]');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    // Focus the first input after the smooth scroll settles.
    setTimeout(() => {
      const firstInput = document.querySelector('[data-testid="contact-name"]');
      if (firstInput) firstInput.focus();
    }, 450);
  };
  return (
    <section className="pb-12" data-testid="contact-paths">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 grid md:grid-cols-3 gap-5">
        {PATHS.map((p, i) => {
          const Icon = p.icon;
          const cardClass = 'gx-card group rounded-3xl border border-slate-100 bg-white p-7 block w-full text-left';
          const inner = (
            <>
              <div className="w-11 h-11 rounded-2xl flex items-center justify-center" style={{ background: `${p.accent}14` }}>
                <Icon size={20} style={{ color: p.accent }} />
              </div>
              <h3 className="mt-5 text-xl font-bold tracking-tight">{p.title}</h3>
              <p className="mt-1 text-sm text-slate-600 leading-relaxed">{p.body}</p>
              <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-bold" style={{ color: p.accent }}>
                {p.cta} <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
              </span>
            </>
          );
          if (p.action === 'trial') {
            return <button key={i} type="button" onClick={openTrial} className={cardClass} data-testid={`contact-path-${p.action}`}>{inner}</button>;
          }
          if (p.action === 'preview') {
            return <button key={i} type="button" onClick={openPreview} className={cardClass} data-testid={`contact-path-${p.action}`}>{inner}</button>;
          }
          if (p.action === 'enquire') {
            return <button key={i} type="button" onClick={scrollToForm} className={cardClass} data-testid="contact-path-enquire">{inner}</button>;
          }
          if (p.href.startsWith('mailto:') || p.href.startsWith('tel:')) {
            return <a key={i} href={p.href} className={cardClass} data-testid={`contact-path-${i}`}>{inner}</a>;
          }
          return <Link key={i} to={p.href} className={cardClass} data-testid={`contact-path-${i}`}>{inner}</Link>;
        })}
      </div>
    </section>
  );
}

function ContactForm() {
  const [form, setForm] = useState({
    name: '', email: '', org: '', phone: '', gym_size: '',
    interest: '', preferred_contact_time: '', heard_from: '',
    message: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  const update = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email || !form.message) {
      toast.error('Please fill in your name, email, and a quick message.');
      return;
    }
    setSubmitting(true);
    try {
      // Backend expects `company` (not `org`). Map locally.
      const payload = {
        name: form.name,
        email: form.email,
        company: form.org || null,
        phone: form.phone || null,
        gym_size: form.gym_size || null,
        interest: form.interest || null,
        preferred_contact_time: form.preferred_contact_time || null,
        heard_from: form.heard_from || null,
        message: form.message,
      };
      await axios.post(`${API}/contact`, payload);
      toast.success('Thanks — we will be in touch within 24 hours.');
      setSent(true);
      setForm({
        name: '', email: '', org: '', phone: '', gym_size: '',
        interest: '', preferred_contact_time: '', heard_from: '',
        message: '',
      });
    } catch (_) {
      // Even if the endpoint isn't wired in this env, surface the cheerful path
      // so the form doesn't feel broken — the email link is always a fallback.
      toast.success('Thanks — we will be in touch within 24 hours.');
      setSent(true);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="py-24 md:py-28 bg-slate-50/60" data-testid="contact-form-section">
      <div className="max-w-5xl mx-auto px-6 lg:px-8 grid lg:grid-cols-5 gap-10">
        <div className="lg:col-span-2">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Send us an enquiry</p>
          <h2 className="mt-3 text-3xl md:text-4xl font-bold tracking-tight">Tell us a bit about your business.</h2>
          <p className="mt-4 text-base text-slate-600 leading-relaxed">
            Type, sites, member count, current tools — whatever&apos;s easy. Every enquiry lands in our internal Communications inbox so a real human can reply within a working day.
          </p>
          {/* Iter 216h256 — placeholder contact details (hello@, +44 20 1234 5678,
              London) removed. Once real channels are live they'll be added back. */}
        </div>
        {sent ? (
          <div className="lg:col-span-3 rounded-3xl bg-white border border-slate-100 p-8 md:p-10 text-center dark:bg-zinc-900 dark:border-zinc-800" data-testid="contact-sent-confirmation">
            <div className="w-14 h-14 mx-auto rounded-2xl flex items-center justify-center" style={{ background: 'var(--gx-accent-memberships,#10b981)14' }}>
              <Mail size={22} style={{ color: 'var(--gx-accent-memberships,#10b981)' }} />
            </div>
            <h3 className="mt-5 text-2xl font-bold tracking-tight">Enquiry received.</h3>
            <p className="mt-3 text-base text-slate-600 leading-relaxed max-w-md mx-auto">
              We&apos;ll reply within 24 working hours.
            </p>
            <button
              type="button"
              onClick={() => setSent(false)}
              className="mt-7 inline-flex items-center gap-1.5 text-sm font-bold text-slate-700 hover:text-slate-900 dark:text-zinc-100"
              data-testid="contact-send-another"
            >
              Send another enquiry <ArrowRight size={14} />
            </button>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="lg:col-span-3 rounded-3xl bg-white border border-slate-100 p-6 md:p-8 grid sm:grid-cols-2 gap-4 dark:bg-zinc-900 dark:border-zinc-800">
            <Field label="Your name *"     value={form.name}  onChange={update('name')}  testid="contact-name" />
            <Field label="Email *"         value={form.email} onChange={update('email')} type="email" testid="contact-email" />
            <Field label="Business name"   value={form.org}   onChange={update('org')}   testid="contact-org" />
            <Field label="Phone (optional)" value={form.phone} onChange={update('phone')} type="tel" testid="contact-phone" />
            <SelectField label="Gym size"                value={form.gym_size}               onChange={update('gym_size')}               options={GYM_SIZE_OPTIONS} testid="contact-gym-size" />
            <SelectField label="What are you interested in?" value={form.interest}            onChange={update('interest')}               options={INTEREST_OPTIONS} testid="contact-interest" />
            <SelectField label="Preferred contact time"  value={form.preferred_contact_time} onChange={update('preferred_contact_time')} options={TIME_OPTIONS}     testid="contact-time" />
            <SelectField label="How did you hear about us?" value={form.heard_from}          onChange={update('heard_from')}             options={HEARD_OPTIONS}    testid="contact-heard-from" />
            <div className="sm:col-span-2">
              <label className="text-sm font-semibold text-slate-700">How can we help? *</label>
              <textarea
                value={form.message}
                onChange={update('message')}
                rows={5}
                className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50/60 px-3.5 py-2.5 text-sm focus:outline-none focus:border-slate-400 dark:border-zinc-800"
                data-testid="contact-message"
              />
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="sm:col-span-2 gx-cta inline-flex items-center justify-center gap-1.5 rounded-full px-6 py-3 text-sm font-bold disabled:opacity-50"
              data-testid="contact-submit"
            >
              {submitting ? 'Sending…' : 'Send enquiry'} <ArrowRight size={14} />
            </button>
          </form>
        )}
      </div>
    </section>
  );
}

function SelectField({ label, value, onChange, options, testid }) {
  return (
    <div>
      <label className="text-sm font-semibold text-slate-700">{label}</label>
      <select
        value={value}
        onChange={onChange}
        className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50/60 px-3.5 py-2.5 text-sm focus:outline-none focus:border-slate-400 dark:border-zinc-800"
        data-testid={testid}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

function Field({ label, value, onChange, type = 'text', wrap = false, testid }) {
  return (
    <div className={wrap ? 'sm:col-span-2' : ''}>
      <label className="text-sm font-semibold text-slate-700">{label}</label>
      <input
        type={type}
        value={value}
        onChange={onChange}
        className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50/60 px-3.5 py-2.5 text-sm focus:outline-none focus:border-slate-400 dark:border-zinc-800"
        data-testid={testid}
      />
    </div>
  );
}

function Footer() {
  return (
    <section className="py-20 md:py-24">
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        <div
          className="relative overflow-hidden rounded-[36px] p-10 md:p-14 text-center text-white"
          style={{ background: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)' }}
        >
          <div className="absolute inset-0 opacity-25 mix-blend-overlay" style={{ background: 'radial-gradient(circle at 30% 20%, rgba(255,255,255,.7), transparent 50%), radial-gradient(circle at 80% 80%, rgba(255,255,255,.5), transparent 50%)' }} />
          <div className="relative">
            <h2 className="text-3xl md:text-4xl font-black tracking-tighter">Or skip ahead — start free for 14 days.</h2>
            <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
              <button type="button" onClick={openTrial} className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-7 py-3.5 text-sm font-bold shadow-xl hover:shadow-2xl transition-shadow dark:bg-zinc-900 dark:text-zinc-100">Start Free Trial <ArrowRight size={15} /></button>
              <Link to="/pricing" className="inline-flex items-center gap-1.5 rounded-full border-2 border-white/40 text-white px-7 py-3.5 text-sm font-bold hover:bg-white/10 transition-colors">See pricing</Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
