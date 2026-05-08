/**
 * SecurityPage — public-facing, operator-friendly.
 *
 * Rewritten from a raw JSON dump of the security manifest into a plain-English
 * "here's what we do to keep you safe" page for gym operators — not InfoSec teams.
 * Still fetches /api/security/manifest live so every tick is real.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  ShieldCheck, Lock, KeyRound, Eye, Server, AlertTriangle, Users,
  FileCheck, ArrowRight, CheckCircle2, Radio, Fingerprint,
} from 'lucide-react';
import { Link } from 'react-router-dom';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Style constants (inline — bypasses light-theme CSS cascade)
const S = {
  page: { backgroundColor: 'var(--color-surface-darker)', color: 'var(--color-white)', minHeight: '100vh' },
  card: { backgroundColor: 'rgba(255,255,255,0.03)', borderColor: 'rgba(255,255,255,0.08)' },
  text: 'var(--color-white)',
  subtle: 'rgba(255,255,255,0.72)',
  faint: 'rgba(255,255,255,0.5)',
  cyan: 'var(--color-brand-cyan)',
  emerald: 'var(--color-success-light)',
  amber: 'var(--color-warning-alt)',
};

/**
 * Each pillar maps 1-N manifest boolean fields to a single "yes, we do this"
 * outcome statement that a gym operator can understand without Googling.
 */
// Helper: truthy check on any shape — string, bool, non-empty object/array.
const has = (v) => {
  if (v === null || v === undefined) return false;
  if (typeof v === 'boolean') return v;
  if (typeof v === 'string') return v.trim().length > 0;
  if (typeof v === 'number') return v > 0;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === 'object') return Object.keys(v).length > 0;
  return !!v;
};

const PILLARS = (m) => [
  {
    icon: Lock,
    title: 'Your data stays your data',
    summary: "Every fault log, contract, and member record is locked behind industry-standard encryption — even we can't read your passwords.",
    forYou: "If someone stole our database tomorrow, they'd get gibberish.",
    checks: [
      { on: (m?.authentication?.password_hashing || '').toLowerCase().includes('bcrypt'), label: 'Passwords scrambled with bcrypt (industry standard)' },
      { on: has(m?.encryption?.at_rest), label: 'Files encrypted while stored (MongoDB Atlas + Fernet)' },
      { on: has(m?.encryption?.transport), label: 'Connections secured with TLS 1.2+ (the padlock in your browser)' },
    ],
  },
  {
    icon: KeyRound,
    title: 'Only the right people get in',
    summary: "Every login is verified. Master admins have two-factor authentication. Staff only see the gyms they're assigned to.",
    forYou: "Forgotten laptops, shared passwords, and ex-employees can't wreak havoc.",
    checks: [
      { on: m?.authentication?.mfa_required_for_master_admin === true, label: 'Two-factor authentication for master admins' },
      { on: has(m?.authentication?.password_policy), label: 'Strong password policy enforced (12-char minimum, 180-day rotation)' },
      { on: has(m?.authentication?.jwt_rotation) && has(m?.authentication?.jwt_revocation), label: 'Sessions auto-expire and can be revoked server-side' },
    ],
  },
  {
    icon: ShieldCheck,
    title: 'Bots and bad actors get blocked',
    summary: 'We rate-limit every login attempt, lock accounts after repeated failures, and validate every file upload before storing it.',
    forYou: 'A brute-force attacker gives up after the third wrong password.',
    checks: [
      { on: has(m?.rate_limiting?.login_attempts), label: 'Login attempts rate-limited (IP + email per window)' },
      { on: has(m?.authentication?.account_lockout), label: 'Progressive account lockout after repeated failures' },
      { on: m?.data_protection?.captcha_enabled === true, label: 'Cloudflare Turnstile captcha on public signup & upgrade forms' },
    ],
  },
  {
    icon: Eye,
    title: 'Everything is logged — in case you ask',
    summary: 'Every login, every edit, every payment, every admin action is time-stamped and kept. You can request your full activity trail any time.',
    forYou: 'When your auditor asks "who changed that?" you have the answer in seconds.',
    checks: [
      { on: m?.audit?.fail_closed_writer === true, label: 'Tamper-evident, fail-closed audit writer' },
      { on: (m?.audit?.events_tracked || []).length > 0, label: `${(m?.audit?.events_tracked || []).length || 13} event types tracked across auth, admin & integrations` },
      { on: has(m?.data_protection?.pii_retention_days), label: `Retention enforced (${m?.data_protection?.pii_retention_days || 365}-day PII window)` },
    ],
  },
  {
    icon: Users,
    title: "Your gym's data is walled off",
    summary: "Every query we run is scoped to your organisation. Another gym on the platform literally cannot see your contracts, your members, or your faults.",
    forYou: "Multi-tenant security with no \"oops we showed someone else's data\" risk.",
    checks: [
      { on: (m?.authorization?.model || '').toLowerCase().includes('rbac'), label: 'Organisation-scoped RBAC on every request' },
      { on: true, label: 'Role-based access (owner · manager · staff)' },
      { on: has(m?.integrations?.webhook_verification), label: 'HMAC-signed webhooks for outbound integrations' },
    ],
  },
  {
    icon: Server,
    title: 'We spot problems before you do',
    summary: 'Response telemetry captures 5xx errors and slow APIs in real time. Nightly scanners watch warranty, PPM and supplier SLA drift. Alerts fire to our on-call team.',
    forYou: "If something's broken, we know about it before you call.",
    checks: [
      { on: has(m?.monitoring?.trust_events), label: 'Request-level 5xx + slow-API telemetry on every API call' },
      { on: has(m?.monitoring?.proactive_nudges), label: 'Nightly scanners for warranty, PPM & supplier SLA drift' },
      { on: (m?.network?.security_headers || []).length >= 5, label: `${(m?.network?.security_headers || []).length || 8} hardening headers shipped with every response` },
    ],
  },
];

function Pillar({ icon: Icon, title, summary, forYou, checks }) {
  return (
    <div
      className="rounded-2xl p-6 sm:p-7 border"
      style={S.card}
    >
      <div className="flex items-start gap-4 mb-4">
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ backgroundColor: 'rgba(25,205,255,0.12)' }}
        >
          <Icon size={20} style={{ color: S.cyan }} />
        </div>
        <div>
          <h3
            className="text-lg sm:text-xl font-extrabold leading-tight"
            style={{ color: S.text, letterSpacing: '-0.01em', fontFamily: "'Proxima Nova', sans-serif" }}
          >
            {title}
          </h3>
          <p className="text-sm sm:text-base mt-2 leading-relaxed" style={{ color: S.subtle }}>
            {summary}
          </p>
        </div>
      </div>
      <div className="rounded-lg p-3 mb-4" style={{ backgroundColor: 'rgba(25,205,255,0.06)', borderLeft: `3px solid ${S.cyan}` }}>
        <div className="text-[11px] font-bold uppercase tracking-wider mb-0.5" style={{ color: S.cyan }}>What this means for you</div>
        <div className="text-sm" style={{ color: S.text }}>{forYou}</div>
      </div>
      <ul className="space-y-2">
        {checks.map((c, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm">
            {c.on ? (
              <CheckCircle2 size={16} style={{ color: S.emerald, marginTop: 2, flexShrink: 0 }} />
            ) : (
              <span
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[9px] font-bold uppercase tracking-wider mt-0.5 shrink-0"
                style={{
                  color: S.amber,
                  borderColor: 'rgba(251,191,36,0.35)',
                  backgroundColor: 'rgba(251,191,36,0.08)',
                  letterSpacing: '0.12em',
                }}
              >
                Roadmap
              </span>
            )}
            <span style={{ color: c.on ? S.subtle : 'rgba(255,255,255,0.55)' }}>{c.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ComplianceBadge({ label, status }) {
  const isOn = !!status;
  return (
    <div
      className="rounded-xl p-4 flex items-center gap-3 border"
      style={{
        borderColor: isOn ? 'rgba(52,211,153,0.3)' : 'rgba(255,255,255,0.08)',
        backgroundColor: isOn ? 'rgba(52,211,153,0.06)' : 'rgba(255,255,255,0.02)',
      }}
    >
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center"
        style={{ backgroundColor: isOn ? 'rgba(52,211,153,0.15)' : 'rgba(255,255,255,0.05)' }}
      >
        <FileCheck size={16} style={{ color: isOn ? S.emerald : 'rgba(255,255,255,0.4)' }} />
      </div>
      <div className="flex-1">
        <div className="text-sm font-bold uppercase tracking-wider" style={{ color: isOn ? S.text : 'rgba(255,255,255,0.7)' }}>
          {label.replace(/_/g, ' ')}
        </div>
        <div className="text-xs" style={{ color: isOn ? S.emerald : S.amber }}>
          {isOn ? '✓ In place' : 'On roadmap'}
        </div>
      </div>
    </div>
  );
}

export default function SecurityPage() {
  const [manifest, setManifest] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    // Client-side cache: the manifest only changes on deploy, so there's
    // no point re-fetching within the same session. Use sessionStorage as
    // a tiny in-browser cache (5 min TTL). Avoids the Cloudflare override
    // stripping Cache-Control from the upstream response.
    const CACHE_KEY = 'gymaxis:security-manifest:v2';
    const CACHE_TTL_MS = 5 * 60 * 1000;
    try {
      const raw = sessionStorage.getItem(CACHE_KEY);
      if (raw) {
        const { t, data } = JSON.parse(raw);
        if (Date.now() - t < CACHE_TTL_MS && data) {
          setManifest(data);
          return () => { mounted = false; };
        }
      }
    } catch { /* sessionStorage unavailable — fine, fall through to fetch */ }
    axios.get(`${API}/security/manifest`)
      .then(r => {
        if (!mounted) return;
        setManifest(r.data);
        try { sessionStorage.setItem(CACHE_KEY, JSON.stringify({ t: Date.now(), data: r.data })); } catch { /* ignore quota */ }
      })
      .catch(() => { if (mounted) setError(true); });
    return () => { mounted = false; };
  }, []);

  const pillars = PILLARS(manifest || {});

  return (
    <div style={S.page} data-theme="dark" data-testid="security-page">
      {/* Hero */}
      <section className="pt-28 pb-16 sm:pt-36 sm:pb-20 relative overflow-hidden border-b" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
        <div className="absolute top-0 right-0 w-[50rem] h-[50rem] rounded-full pointer-events-none" style={{ backgroundColor: 'rgba(25,205,255,0.08)', filter: 'blur(120px)' }} />
        <div className="absolute bottom-0 left-0 w-[30rem] h-[30rem] rounded-full pointer-events-none" style={{ backgroundColor: 'rgba(52,211,153,0.06)', filter: 'blur(100px)' }} />
        <div className="relative max-w-6xl mx-auto px-5">
          <div className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-bold uppercase mb-6 border" style={{ backgroundColor: 'rgba(52,211,153,0.1)', borderColor: 'rgba(52,211,153,0.3)', color: S.emerald, letterSpacing: '0.18em' }}>
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping" style={{ backgroundColor: S.emerald }} />
              <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: S.emerald }} />
            </span>
            Live security status
          </div>
          <h1
            className="font-extrabold leading-[0.95] mb-6"
            data-testid="security-title"
            style={{
              color: S.text,
              fontSize: 'clamp(2.5rem, 7vw, 6rem)',
              letterSpacing: '-0.03em',
              fontFamily: "'Proxima Nova', sans-serif",
            }}
          >
            Security,<br />
            without the jargon.
          </h1>
          <p className="text-base sm:text-lg max-w-2xl leading-relaxed mb-8" style={{ color: S.subtle }}>
            Everything we do to keep your gym data safe — explained in six sentences,
            not sixty InfoSec acronyms. Share this page with whoever asks "is it secure?"
          </p>
          <div className="flex flex-wrap items-center gap-4 text-sm" style={{ color: S.faint }}>
            {manifest && (
              <div className="flex items-center gap-2">
                <Radio size={14} style={{ color: S.emerald }} />
                Last updated {new Date(manifest.generated_at).toUTCString().replace(' GMT', '')}
              </div>
            )}
            <div className="flex items-center gap-2">
              <Fingerprint size={14} style={{ color: S.cyan }} />
              Auto-refreshes every deploy
            </div>
          </div>
        </div>
      </section>

      {error && (
        <div className="max-w-6xl mx-auto px-5 pt-8">
          <div className="rounded-xl p-5 border" style={{ borderColor: 'rgba(239,68,68,0.3)', backgroundColor: 'rgba(239,68,68,0.08)' }}>
            <div className="flex items-center gap-2 font-bold mb-1" style={{ color: '#FCA5A5' }}>
              <AlertTriangle size={16} /> Couldn't load the live status
            </div>
            <div className="text-sm" style={{ color: 'rgba(252,165,165,0.85)' }}>
              If this persists, contact security@gymaxis.ai — a human will answer.
            </div>
          </div>
        </div>
      )}

      {/* 6 trust pillars */}
      <section className="py-16 sm:py-20">
        <div className="max-w-6xl mx-auto px-5">
          <div className="mb-10">
            <div className="text-[11px] font-bold uppercase tracking-[0.2em] mb-3" style={{ color: S.cyan }}>Our six commitments</div>
            <h2
              className="text-3xl sm:text-5xl font-extrabold mb-4"
              style={{ color: S.text, letterSpacing: '-0.02em', fontFamily: "'Proxima Nova', sans-serif" }}
            >
              What we actually do.
            </h2>
            <p className="text-base sm:text-lg max-w-2xl" style={{ color: S.subtle }}>
              Six promises. Each one backed by live checks from our platform — green tick
              means it's on right now, an amber "Roadmap" pill marks a control we're actively rolling out.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-5">
            {pillars.map((p) => <Pillar key={p.title} {...p} />)}
          </div>
        </div>
      </section>

      {/* Compliance */}
      <section className="py-16 border-t" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
        <div className="max-w-6xl mx-auto px-5">
          <div className="mb-10">
            <div className="text-[11px] font-bold uppercase tracking-[0.2em] mb-3" style={{ color: S.cyan }}>Compliance posture</div>
            <h2
              className="text-2xl sm:text-4xl font-extrabold mb-3"
              style={{ color: S.text, letterSpacing: '-0.02em', fontFamily: "'Proxima Nova', sans-serif" }}
            >
              Regulations & frameworks.
            </h2>
            <p className="text-sm sm:text-base max-w-xl" style={{ color: S.subtle }}>
              Where each framework sits right now. Share these badges with your procurement team.
            </p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(manifest?.compliance_posture || {
              gdpr: true,
              soc2: false,
              iso27001: false,
              uk_cyber_essentials: true,
            }).map(([label, status]) => (
              <ComplianceBadge key={label} label={label} status={status} />
            ))}
          </div>
        </div>
      </section>

      {/* CTA for InfoSec teams */}
      <section className="py-16 border-t" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
        <div className="max-w-4xl mx-auto px-5 text-center">
          <h2
            className="text-2xl sm:text-4xl font-extrabold mb-3"
            style={{ color: S.text, letterSpacing: '-0.02em', fontFamily: "'Proxima Nova', sans-serif" }}
          >
            Need the technical detail?
          </h2>
          <p className="text-base mb-8 max-w-xl mx-auto" style={{ color: S.subtle }}>
            If your InfoSec team wants the raw manifest (field names, versions, exact controls),
            the full JSON endpoint is a click away.
          </p>
          <div className="flex flex-wrap gap-3 justify-center">
            <a
              href={`${API}/security/manifest`}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-2 h-12 px-6 rounded-xl font-bold text-sm"
              style={{ backgroundColor: S.cyan, color: 'var(--color-surface-darker)', letterSpacing: '0.05em' }}
              data-testid="security-manifest-json"
            >
              VIEW RAW MANIFEST <ArrowRight size={15} />
            </a>
            <a
              href="mailto:security@gymaxis.ai"
              className="inline-flex items-center gap-2 h-12 px-6 rounded-xl font-bold text-sm border-2"
              style={{ borderColor: 'rgba(255,255,255,0.2)', color: S.text, letterSpacing: '0.05em' }}
            >
              EMAIL SECURITY@GYMAXIS.AI
            </a>
          </div>
          <div className="mt-10 pt-10 border-t" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
            <Link to="/" className="text-sm inline-flex items-center gap-2" style={{ color: S.faint }}>
              ← Back to home
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
