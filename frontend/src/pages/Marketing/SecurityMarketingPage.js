/**
 * Security marketing page — refreshed in MarketingShell visual language.
 * This is the ONE place pentest / SOC 2 / responsible disclosure language lives.
 */
import { Link } from 'react-router-dom';
import {
  ShieldCheck, Lock, KeyRound, FileSearch, Bug, Server, Activity, ArrowRight,
  CheckCircle2, FileText, Mail, Download, FileType2,
} from 'lucide-react';

import './marketing.css';
import MarketingShell from './MarketingShell';
import { openTrial } from './TrialSignupModal';

const PILLARS = [
  { icon: KeyRound,    title: 'Authentication & sessions', body: 'Rotated JWT secret with cryptographic strength, HttpOnly cookies, password reset rate-limits, and brute-force protection on every auth endpoint.' },
  { icon: Lock,        title: 'Encryption everywhere',     body: 'TLS 1.3 in transit, AES-256 at rest. Fernet field-level encryption for integration secrets. Stripe handles PCI scope; we never see raw card numbers.' },
  { icon: ShieldCheck, title: 'IDOR-tested endpoints',     body: 'Every operator endpoint filters by the caller\'s organisation_id before any read or write. Cross-tenant access returns 404 (never 403) so attackers can\'t enumerate IDs by status code. Regression-tested on every deploy.' },
  { icon: FileSearch,  title: 'Tamper-evident audit log',  body: 'Append-only master-admin audit trail with CSV export, dedicated impersonation + export event streams, and hash-chain verification — evidence-grade for SOC 2 and pentests.' },
  { icon: Server,      title: 'Hardened infrastructure',   body: 'Strict CSP, security headers, SSRF allow-list with IMDS + DNS-rebind guards, AV scanning on uploads (ClamAV + static-signature), and dependency CVE auditing on every release.' },
  { icon: Bug,         title: 'Responsible disclosure',    body: 'Published security.txt with a canonical contact, expiry date and 90-day safe-harbour. Researchers welcome; we acknowledge within 24 hours.' },
];

const HARDENING = [
  'Pen-test ready — 7 hardening waves landed (auth, AI guardrails, web scrubbers, SSRF, AV, audit hygiene, sandbox tenant).',
  'AI prompt-injection guardrails on every LLM round-trip (OWASP LLM01–10) — per-tenant token budgets, jailbreak detection, output sanitisation.',
  'JWT_SECRET rotated to a 64-hex cryptographically random value. Role-tiered access TTLs; MFA enforceable on every master-admin route.',
  'Rate-limits on every auth + money endpoint (login, register, top-up, auto-pay, public demo-request).',
  'Stripe webhook hard-requires STRIPE_WEBHOOK_SECRET in production; idempotency keys on every event.',
  'Global 500 handler — never leaks raw exception details to the client. /api/health returns "ok" only (no version / build / commit info).',
  'CORS pinned per-environment; "*" disallowed in production. HSTS preload-ready.',
  '/.well-known/security.txt published with a 12-month expiry and rolling refresh.',
  'GDPR Art. 17 erasure workflow with 30-day cooling-off; gdpr_erased rows excluded from operator lists + AI RAG contexts.',
];

const POSTURE_LINKS = [
  { label: 'Data Processing Agreement (DPA)', to: '/legal/dpa', kind: 'internal' },
  { label: 'Sub-processors register', to: '/sub-processors', kind: 'internal' },
  { label: 'Service Level Agreement (SLA)', to: '/sla', kind: 'internal' },
  { label: 'Privacy Policy', to: '/privacy', kind: 'internal' },
  { label: 'Terms of Service', to: '/terms', kind: 'internal' },
  { label: 'security.txt (RFC 9116)', to: '/.well-known/security.txt', kind: 'external' },
];

export default function SecurityPage() {
  return (
    <MarketingShell>
      <Hero />
      <Pillars />
      <Hardening />
      <Posture />
      <Disclosure />
      <Cta />
    </MarketingShell>
  );
}

function Hero() {
  return (
    <section className="gx-grid-bg" data-testid="sec-hero">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-20 lg:pt-20 lg:pb-28 grid lg:grid-cols-12 gap-12 items-center">
        <div className="lg:col-span-7">
          <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
            <ShieldCheck size={12} />Trust & Security
          </span>
          <h1 className="mt-5 text-5xl md:text-6xl tracking-tighter font-black leading-[1.04]">
            Built for operators<br /><span className="gx-gradient-text">who can&apos;t afford a breach.</span>
          </h1>
          <p className="mt-6 text-lg md:text-xl text-slate-600 leading-relaxed max-w-2xl">
            GymAxis runs your members&apos; payment data, your staff personal information, and your operational decisions. Here is how we protect them.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <a href="/.well-known/security.txt" target="_blank" rel="noreferrer" className="gx-cta inline-flex items-center gap-1.5 rounded-full px-6 py-3 text-sm font-bold">
              View security.txt <ArrowRight size={15} />
            </a>
            <Link to="/contact" className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-6 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 dark:bg-zinc-900">
              Request pentest evidence
            </Link>
          </div>
        </div>
        <div className="lg:col-span-5">
          <div className="aspect-square max-w-md mx-auto rounded-[36px] gx-glass p-8 flex flex-col">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-white" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
              <ShieldCheck size={26} />
            </div>
            <p className="mt-5 text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Latest hardening pass</p>
            <p className="mt-1 text-2xl font-bold tracking-tight">May 2026</p>
            <div className="mt-auto space-y-2">
              {[
                ['Open critical CVEs', '0'],
                ['Auth rate-limits', 'Active'],
                ['Audit log', 'Tamper-evident'],
                ['security.txt', 'Published'],
              ].map(([l, r]) => (
                <div key={l} className="flex items-center justify-between rounded-xl bg-white/80 border border-slate-100 px-3 py-2 text-sm dark:border-zinc-800">
                  <span className="font-semibold text-slate-700">{l}</span>
                  <span className="font-bold text-emerald-600">{r}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Pillars() {
  return (
    <section className="py-24 md:py-32 bg-white dark:bg-zinc-900" data-testid="sec-pillars">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Our defence</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">Six pillars. Continually verified.</h2>
        </div>
        <div className="mt-12 grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {PILLARS.map((p, i) => {
            const Icon = p.icon;
            return (
              <div key={i} className="gx-card rounded-3xl border border-slate-100 bg-slate-50/40 p-7 dark:border-zinc-800">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center text-white" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
                  <Icon size={18} />
                </div>
                <h3 className="mt-5 text-lg font-bold tracking-tight">{p.title}</h3>
                <p className="mt-1 text-sm text-slate-600 leading-relaxed">{p.body}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function Hardening() {
  return (
    <section className="py-24 md:py-32 bg-slate-50/60">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 grid lg:grid-cols-2 gap-12">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Latest hardening</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">What we shipped this quarter.</h2>
          <p className="mt-4 text-base md:text-lg text-slate-600 leading-relaxed">
            Security is a release item, not a marketing tagline. Every quarter we publish what we hardened, what we audited, and what changed.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-2" data-testid="security-hardening-actions">
            <Link
              to="/security/details"
              className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-4 py-2 text-sm font-bold text-white hover:bg-slate-700 transition dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
              data-testid="security-hardening-read"
            >
              <FileText size={14} /> Read full document
            </Link>
            <a
              href={`${process.env.REACT_APP_BACKEND_URL}/api/security/document.pdf`}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 hover:border-slate-400 transition dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200"
              data-testid="security-hardening-pdf"
            >
              <Download size={14} /> PDF
            </a>
            <a
              href={`${process.env.REACT_APP_BACKEND_URL}/api/security/document.txt`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 hover:border-slate-400 transition dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200"
              data-testid="security-hardening-txt"
            >
              <FileType2 size={14} /> Plain text
            </a>
          </div>
        </div>
        <ul className="rounded-3xl bg-white border border-slate-100 p-6 md:p-8 space-y-3 dark:bg-zinc-900 dark:border-zinc-800">
          {HARDENING.map((h, i) => (
            <li key={i} className="flex items-start gap-3">
              <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-emerald-500" />
              <span className="text-sm text-slate-700 leading-relaxed">{h}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Posture() {
  return (
    <section className="py-20 md:py-24 bg-white dark:bg-zinc-900" data-testid="sec-posture">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Trust posture</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">Read the contracts, not the pitch.</h2>
          <p className="mt-4 text-base md:text-lg text-slate-600 leading-relaxed">
            Every commitment on this page is written down. Procurement and security teams can review the legal posture before talking to us.
          </p>
        </div>
        <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {POSTURE_LINKS.map((p) => p.kind === 'external' ? (
            <a
              key={p.to}
              href={p.to}
              target="_blank"
              rel="noreferrer"
              className="group flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50/40 px-5 py-4 hover:border-slate-300 hover:bg-slate-50 transition-colors dark:border-zinc-800 dark:bg-zinc-900"
              data-testid={`sec-posture-link-${p.to.replace(/[^a-z0-9]/gi, '-').toLowerCase()}`}
            >
              <span className="text-sm font-semibold text-slate-800 dark:text-zinc-100">{p.label}</span>
              <ArrowRight size={14} className="text-slate-400 group-hover:text-slate-700 transition-colors" />
            </a>
          ) : (
            <Link
              key={p.to}
              to={p.to}
              className="group flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50/40 px-5 py-4 hover:border-slate-300 hover:bg-slate-50 transition-colors dark:border-zinc-800 dark:bg-zinc-900"
              data-testid={`sec-posture-link-${p.to.replace(/[^a-z0-9]/gi, '-').toLowerCase()}`}
            >
              <span className="text-sm font-semibold text-slate-800 dark:text-zinc-100">{p.label}</span>
              <ArrowRight size={14} className="text-slate-400 group-hover:text-slate-700 transition-colors" />
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

function Disclosure() {
  return (
    <section className="py-24 md:py-28 bg-white dark:bg-zinc-900">
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        <div className="rounded-[28px] border border-slate-200 bg-slate-50/40 p-8 md:p-12 grid md:grid-cols-3 gap-8 items-center dark:border-zinc-800">
          <div className="md:col-span-2">
            <p className="text-xs uppercase tracking-[0.2em] font-bold" style={{ color: 'var(--gx-brand-from)' }}>
              <Activity size={13} className="inline mr-1" />Responsible disclosure
            </p>
            <h2 className="mt-3 text-3xl md:text-4xl font-bold tracking-tight">Found something?</h2>
            <p className="mt-3 text-base md:text-lg text-slate-600 leading-relaxed">
              Email us. We acknowledge within 24 hours and patch within the SLA on our security.txt. Researchers acting in good faith are covered by our safe-harbour clause.
            </p>
          </div>
          <div className="space-y-3">
            <a href="mailto:security@gymaxisai.com" className="gx-cta w-full inline-flex items-center justify-center gap-1.5 rounded-full px-5 py-3 text-sm font-bold">
              <Mail size={14} />security@gymaxisai.com
            </a>
            <a href="/.well-known/security.txt" target="_blank" rel="noreferrer" className="w-full inline-flex items-center justify-center gap-1.5 rounded-full border border-slate-300 px-5 py-3 text-sm font-bold text-slate-700 hover:bg-white dark:bg-zinc-900">
              security.txt
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

function Cta() {
  return (
    <section className="py-24 md:py-28">
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        <div
          className="relative overflow-hidden rounded-[36px] p-10 md:p-14 text-center text-white"
          style={{ background: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)' }}
        >
          <div className="absolute inset-0 opacity-25 mix-blend-overlay" style={{ background: 'radial-gradient(circle at 30% 20%, rgba(255,255,255,.7), transparent 50%), radial-gradient(circle at 80% 80%, rgba(255,255,255,.5), transparent 50%)' }} />
          <div className="relative">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-black tracking-tighter leading-[1.06]">Run a fitness business that takes security seriously.</h2>
            <p className="mt-4 text-base md:text-lg text-white/90 max-w-xl mx-auto">14-day free trial. Pentest-evidence pack available on request for enterprise plans.</p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <button type="button" onClick={openTrial} className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-7 py-3.5 text-sm font-bold shadow-xl hover:shadow-2xl transition-shadow dark:bg-zinc-900 dark:text-zinc-100">Start Free Trial <ArrowRight size={15} /></button>
              <Link to="/contact" className="inline-flex items-center gap-1.5 rounded-full border-2 border-white/40 text-white px-7 py-3.5 text-sm font-bold hover:bg-white/10 transition-colors">Talk to sales <ArrowRight size={15} /></Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
