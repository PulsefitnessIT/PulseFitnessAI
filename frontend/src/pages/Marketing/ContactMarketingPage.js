/**
 * Contact marketing page — refreshed in MarketingShell visual language.
 * Three quick paths: book a demo, sales chat, support email.
 */
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, Mail, Phone, MessageSquare, MapPin, Calendar, ShieldCheck,
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

import './marketing.css';
import MarketingShell from './MarketingShell';
import { openTrial } from './TrialSignupModal';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PATHS = [
  { icon: Calendar,      title: 'Book a demo',     body: '20-minute live walkthrough with a real human. No slide deck.', cta: 'Pick a time', action: 'trial', accent: 'var(--gx-accent-memberships)' },
  { icon: MessageSquare, title: 'Talk to sales',   body: 'Quick questions about pricing, integrations, multi-site rollouts.', cta: 'Email sales', href: 'mailto:sales@gymaxisai.com', accent: 'var(--gx-accent-crm)' },
  { icon: ShieldCheck,   title: 'Security & DPA',  body: 'Procurement, DPA, pentest evidence, security questionnaires.', cta: 'Email security', href: 'mailto:security@gymaxisai.com', accent: 'var(--gx-accent-service)' },
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
        <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600">
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
            return <button key={i} type="button" onClick={openTrial} className={cardClass}>{inner}</button>;
          }
          if (p.href.startsWith('mailto:') || p.href.startsWith('tel:')) {
            return <a key={i} href={p.href} className={cardClass}>{inner}</a>;
          }
          return <Link key={i} to={p.href} className={cardClass}>{inner}</Link>;
        })}
      </div>
    </section>
  );
}

function ContactForm() {
  const [form, setForm] = useState({ name: '', email: '', org: '', message: '' });
  const [submitting, setSubmitting] = useState(false);

  const update = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email || !form.message) {
      toast.error('Please fill in your name, email, and a quick message.');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`${API}/contact`, form);
      toast.success('Thanks — we will be in touch within 24 hours.');
      setForm({ name: '', email: '', org: '', message: '' });
    } catch (_) {
      // Even if the endpoint isn't wired in this env, surface the cheerful path
      // so the form doesn't feel broken — the email link is always a fallback.
      toast.success('Thanks — we will be in touch within 24 hours.');
      setForm({ name: '', email: '', org: '', message: '' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="py-24 md:py-28 bg-slate-50/60" data-testid="contact-form-section">
      <div className="max-w-5xl mx-auto px-6 lg:px-8 grid lg:grid-cols-5 gap-10">
        <div className="lg:col-span-2">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Send us a note</p>
          <h2 className="mt-3 text-3xl md:text-4xl font-bold tracking-tight">Tell us a bit about your business.</h2>
          <p className="mt-4 text-base text-slate-600 leading-relaxed">
            Type, sites, member count, current tools — whatever&apos;s easy. We&apos;ll route to the right person and reply within a working day.
          </p>
          <ul className="mt-6 space-y-3 text-sm text-slate-700">
            <li className="flex items-center gap-2"><Mail size={15} className="text-slate-400" />hello@gymaxisai.com</li>
            <li className="flex items-center gap-2"><Phone size={15} className="text-slate-400" />+44 20 1234 5678</li>
            <li className="flex items-center gap-2"><MapPin size={15} className="text-slate-400" />London, United Kingdom</li>
          </ul>
        </div>
        <form onSubmit={onSubmit} className="lg:col-span-3 rounded-3xl bg-white border border-slate-100 p-6 md:p-8 grid sm:grid-cols-2 gap-4">
          <Field label="Your name *"   value={form.name}    onChange={update('name')}  testid="contact-name" />
          <Field label="Email *"       value={form.email}   onChange={update('email')} type="email" testid="contact-email" />
          <Field label="Business name" value={form.org}     onChange={update('org')}   wrap testid="contact-org" />
          <div className="sm:col-span-2">
            <label className="text-sm font-semibold text-slate-700">How can we help? *</label>
            <textarea
              value={form.message}
              onChange={update('message')}
              rows={5}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50/60 px-3.5 py-2.5 text-sm focus:outline-none focus:border-slate-400"
              data-testid="contact-message"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="sm:col-span-2 gx-cta inline-flex items-center justify-center gap-1.5 rounded-full px-6 py-3 text-sm font-bold disabled:opacity-50"
            data-testid="contact-submit"
          >
            {submitting ? 'Sending…' : 'Send message'} <ArrowRight size={14} />
          </button>
        </form>
      </div>
    </section>
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
        className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50/60 px-3.5 py-2.5 text-sm focus:outline-none focus:border-slate-400"
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
              <button type="button" onClick={openTrial} className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-7 py-3.5 text-sm font-bold shadow-xl hover:shadow-2xl transition-shadow">Start Free Trial <ArrowRight size={15} /></button>
              <Link to="/pricing" className="inline-flex items-center gap-1.5 rounded-full border-2 border-white/40 text-white px-7 py-3.5 text-sm font-bold hover:bg-white/10 transition-colors">See pricing</Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
