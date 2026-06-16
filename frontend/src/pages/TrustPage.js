/**
 * Public Trust & Security page — /trust.
 *
 * Visible to anyone (signed in or not). Bundles the security posture
 * artefacts a 50k+/year customer asks about *before* booking a demo:
 * uptime status, security control coverage, GDPR/SOC posture, sub-
 * processor list. Most of these are static today; backend hooks are
 * marked with TODO comments where we'd plug in real status feeds.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import {
  ShieldCheck, Lock, KeyRound, Activity, Database,
  CheckCircle2, ArrowRight, AlertCircle, Clock,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;


export default function TrustPage() {
  const [healthy, setHealthy] = useState(true);
  const [checkedAt, setCheckedAt] = useState(null);

  // Live uptime ping — backend `/api/health` returns {status:"ok"}.
  // If it 5xx's, the badge flips. No auth needed.
  useEffect(() => {
    let alive = true;
    const ping = async () => {
      try {
        const r = await axios.get(`${API}/health`, { timeout: 5000 });
        if (alive) {
          setHealthy(r.data?.status === 'ok');
          setCheckedAt(new Date());
        }
      } catch {
        if (alive) {
          setHealthy(false);
          setCheckedAt(new Date());
        }
      }
    };
    ping();
    const id = setInterval(ping, 60_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <div className="bg-[var(--color-surface-darker)] text-white min-h-screen" data-testid="trust-page">
      {/* ── Hero ── */}
      <header className="border-b border-white/5">
        <div className="max-w-6xl mx-auto px-6 py-20 sm:py-28">
          <div className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.25em] text-white/60 mb-5">
            <ShieldCheck size={14} className="text-[var(--color-brand-cyan)]" /> Trust & security
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.02em' }}>
            Built for the <span className="text-[var(--color-brand-cyan)]">UK gym estate</span>.<br />
            Hardened for procurement.
          </h1>
          <p className="mt-6 text-lg text-white/70 max-w-2xl leading-relaxed">
            Every customer's data is encrypted, audited, and ring-fenced.
            Below is the stack of controls, posture and proof-points your
            security team will ask for. No marketing fluff.
          </p>

          <div className="mt-10 inline-flex items-center gap-3 px-4 py-2.5 rounded-full border border-white/10 bg-white/[0.03]" data-testid="trust-uptime-badge">
            <span className={`w-2.5 h-2.5 rounded-full ${healthy ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}`} />
            <span className="text-sm font-semibold">
              {healthy ? 'All systems operational' : 'Investigating an incident'}
            </span>
            <span className="text-xs text-white/50">
              {checkedAt ? `· checked ${checkedAt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}` : ''}
            </span>
          </div>
        </div>
      </header>

      {/* ── Pillars ── */}
      <section className="border-b border-white/5">
        <div className="max-w-6xl mx-auto px-6 py-16 sm:py-20">
          <h2 className="text-xs uppercase tracking-[0.2em] text-[var(--color-brand-cyan)] mb-10">Our security pillars</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {PILLARS.map((p) => (
              <div key={p.title}
                   className="rounded-2xl border border-white/10 bg-white/[0.025] p-6 hover:border-[rgb(var(--rgb-brand-cyan)/0.4)] transition-colors"
                   data-testid={`trust-pillar-${p.id}`}>
                <p.icon size={20} className="text-[var(--color-brand-cyan)]" />
                <h3 className="mt-4 text-lg font-bold">{p.title}</h3>
                <p className="mt-2 text-sm text-white/60 leading-relaxed">{p.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Controls table ── */}
      <section className="border-b border-white/5">
        <div className="max-w-6xl mx-auto px-6 py-16 sm:py-20">
          <h2 className="text-xs uppercase tracking-[0.2em] text-[var(--color-brand-cyan)] mb-3">Controls coverage</h2>
          <p className="text-white/60 text-sm mb-8 max-w-2xl">
            What your security team will tick off in a typical procurement
            questionnaire. Colour-coded by current implementation status.
          </p>
          <div className="rounded-xl border border-white/10 overflow-hidden">
            {CONTROLS.map((c, idx) => (
              <div key={c.name}
                   className={`flex items-center gap-4 p-4 sm:p-5 ${idx > 0 ? 'border-t border-white/5' : ''}`}
                   data-testid={`trust-control-${c.id}`}>
                <span className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  c.status === 'live' ? 'bg-emerald-500/15 text-emerald-400'
                    : c.status === 'soon' ? 'bg-amber-500/15 text-amber-400'
                    : 'bg-zinc-500/15 text-zinc-400'
                }`}>
                  {c.status === 'live' ? <CheckCircle2 size={18} /> :
                   c.status === 'soon' ? <Clock size={18} /> : <AlertCircle size={18} />}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-bold text-white">{c.name}</div>
                  <div className="text-xs text-white/55 mt-0.5">{c.detail}</div>
                </div>
                <div className="text-[10px] uppercase tracking-wider font-bold flex-shrink-0"
                     style={{
                       color: c.status === 'live' ? 'var(--color-success-light)' :
                              c.status === 'soon' ? 'var(--color-warning-alt)' : 'var(--color-text-muted)',
                     }}>
                  {c.status === 'live' ? 'Live' : c.status === 'soon' ? 'Roadmap' : 'On request'}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Compliance posture ── */}
      <section className="border-b border-white/5">
        <div className="max-w-6xl mx-auto px-6 py-16 sm:py-20">
          <h2 className="text-xs uppercase tracking-[0.2em] text-[var(--color-brand-cyan)] mb-8">Compliance & legal</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <ComplianceCard
              title="UK GDPR"
              status="Compliant"
              tone="ok"
              testid="trust-compliance-gdpr"
              points={[
                'Personal data minimisation by design',
                'Right-to-erasure implemented (per-org)',
                'Data Processing Agreement available on request',
              ]}
            />
            <ComplianceCard
              title="SOC 2 Type II"
              status="In progress"
              tone="soon"
              testid="trust-compliance-soc2"
              points={[
                'Internal controls documented',
                'External audit Q3 2026',
                'Trust Services Criteria mapped',
              ]}
            />
            <ComplianceCard
              title="ISO 27001"
              status="Roadmap"
              tone="soon"
              testid="trust-compliance-iso"
              points={[
                'Risk assessment complete',
                'ISMS framework drafted',
                'Cert audit FY27',
              ]}
            />
          </div>
        </div>
      </section>

      {/* ── Sub-processors ── */}
      <section className="border-b border-white/5">
        <div className="max-w-6xl mx-auto px-6 py-16 sm:py-20">
          <h2 className="text-xs uppercase tracking-[0.2em] text-[var(--color-brand-cyan)] mb-3">Sub-processors</h2>
          <p className="text-white/60 text-sm mb-8 max-w-2xl">
            Third parties that may process customer data on our behalf, with
            their hosting region. We notify customers 30 days before adding
            any new sub-processor.
          </p>
          <div className="overflow-x-auto rounded-xl border border-white/10">
            <table className="w-full text-sm" data-testid="trust-subprocessors-table">
              <thead className="bg-white/[0.025] text-[10px] uppercase tracking-wider text-white/50">
                <tr>
                  <th className="text-left px-4 py-3">Service</th>
                  <th className="text-left px-4 py-3">Purpose</th>
                  <th className="text-left px-4 py-3">Region</th>
                </tr>
              </thead>
              <tbody>
                {SUBPROCESSORS.map((s) => (
                  <tr key={s.name} className="border-t border-white/5">
                    <td className="px-4 py-3 font-bold text-white">{s.name}</td>
                    <td className="px-4 py-3 text-white/70">{s.purpose}</td>
                    <td className="px-4 py-3 text-white/55">{s.region}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ── Contact ── */}
      <section>
        <div className="max-w-6xl mx-auto px-6 py-16 sm:py-20">
          <div className="rounded-2xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.1)] via-transparent to-transparent p-8 sm:p-12">
            <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
              Need a security questionnaire, DPA, or pen-test report?
            </h2>
            <p className="mt-3 text-white/70 max-w-xl">
              Email security@pulsefitness.ai — we usually respond within one
              UK working day. Existing customers can also raise a request
              from the Master Admin → Security tab.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <a href="mailto:security@pulsefitness.ai"
                 className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] text-sm font-bold uppercase tracking-wider"
                 data-testid="trust-contact-email-btn">
                Contact security <ArrowRight size={14} />
              </a>
              <Link to="/privacy"
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md border border-white/20 text-sm font-bold uppercase tracking-wider hover:bg-white/5"
                    data-testid="trust-privacy-link">
                Privacy policy
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}


/* ─────────────────── Bits ─────────────────── */

function ComplianceCard({ title, status, tone, points, testid }) {
  const toneCls = tone === 'ok'
    ? 'border-emerald-500/40 bg-emerald-500/5'
    : 'border-amber-500/40 bg-amber-500/5';
  return (
    <div className={`rounded-2xl border ${toneCls} p-6`} data-testid={testid}>
      <div className="flex items-start justify-between gap-3">
        <div className="text-lg font-extrabold">{title}</div>
        <span className={`text-[10px] uppercase tracking-wider font-bold ${
          tone === 'ok' ? 'text-emerald-400' : 'text-amber-400'
        }`}>{status}</span>
      </div>
      <ul className="mt-4 space-y-2">
        {points.map((p) => (
          <li key={p} className="flex items-start gap-2 text-sm text-white/75">
            <CheckCircle2 size={14} className="text-[var(--color-brand-cyan)] mt-0.5 shrink-0" />
            <span>{p}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}


/* ─────────────────── Static content ─────────────────── */

const PILLARS = [
  { id: 'encryption', icon: Lock,         title: 'Encryption everywhere',
    desc: 'TLS 1.3 in transit, AES-256 at rest. Backups encrypted with rotated keys held in a separate region.' },
  { id: 'isolation',  icon: Database,     title: 'Tenant isolation',
    desc: 'Every collection scoped by organisation id. Defense-in-depth at the API + database + audit layers.' },
  { id: 'access',     icon: KeyRound,     title: 'Least privilege',
    desc: 'Role-based access, MFA for admins, brute-force lockouts and full audit trail of every elevated action.' },
  { id: 'observability', icon: Activity,  title: 'Observability',
    desc: 'Sentry SDK on backend + frontend. Failed-login + integration drift triggers a trust event in real time.' },
];

const CONTROLS = [
  { id: 'tls13',     name: 'TLS 1.3',                       detail: 'All traffic encrypted in transit. HSTS preload.', status: 'live' },
  { id: 'aes256',    name: 'AES-256 at rest',               detail: 'MongoDB Atlas + S3 storage encryption.', status: 'live' },
  { id: 'mfa',       name: 'Multi-factor authentication',   detail: 'TOTP enforced for all master admin accounts.', status: 'live' },
  { id: 'audit',     name: 'Immutable audit log',           detail: 'Every login, billing change, and config edit recorded.', status: 'live' },
  { id: 'lockout',   name: 'Brute-force lockout',           detail: '5-attempt lockout, sliding window, trust-event escalation.', status: 'live' },
  { id: 'csp',       name: 'Strict CSP + security headers', detail: 'No `unsafe-eval`, frame-ancestors none, X-Content-Type-Options.', status: 'live' },
  { id: 'rl',        name: 'Per-route rate limiting',       detail: 'Sliding-window limits on auth + write paths.', status: 'live' },
  { id: 'sentry',    name: 'Real-time error monitoring',    detail: 'Sentry instrumentation across backend + frontend.', status: 'live' },
  { id: 'pii',       name: 'PII minimisation',              detail: 'Customer data scoped, retention policies enforced.', status: 'live' },
  { id: 'dpa',       name: 'Data Processing Agreement',     detail: 'GDPR-aligned DPA template available on request.', status: 'live' },
  { id: 'pentest',   name: 'Annual penetration test',       detail: 'Third-party offensive security review.', status: 'soon' },
  { id: 'soc2',      name: 'SOC 2 Type II report',          detail: 'Audit window opens Q3 2026.', status: 'soon' },
];

const SUBPROCESSORS = [
  { name: 'MongoDB Atlas', purpose: 'Primary database', region: 'EU (eu-west)' },
  { name: 'AWS S3',        purpose: 'Object storage (uploads, exports)', region: 'EU (eu-west)' },
  { name: 'Stripe',        purpose: 'Payment processing', region: 'UK / EU' },
  { name: 'Resend',        purpose: 'Transactional email', region: 'EU' },
  { name: 'Sentry',        purpose: 'Error monitoring', region: 'EU' },
  { name: 'Anthropic / Google / OpenAI', purpose: 'LLM inference (opt-in)', region: 'EU / US' },
];
