import { ArrowLeft } from 'lucide-react';

const DirectorsHandout = () => (
  <div className="min-h-screen bg-white">
    {/* Print styles */}
    <style>{`
      @media print {
        .no-print { display: none !important; }
        .print-break { page-break-before: always; }
        body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        .page { max-width: 100% !important; padding: 40px !important; }
      }
      @page { size: A4 portrait; margin: 15mm; }
    `}</style>

    {/* Back button (hidden on print) */}
    <div className="no-print px-6 pt-6">
      <a href="/" className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-900">
        <ArrowLeft size={16} /> Back to home
      </a>
    </div>

    <div className="page max-w-[700px] mx-auto px-8 py-10">

      {/* ─── COVER ─── */}
      <div className="text-center mb-16">
        <div className="inline-flex items-center gap-3 mb-6">
          <div className="w-12 h-12 rounded-xl bg-[var(--color-brand-blue-dark)] flex items-center justify-center">
            <span className="text-white font-bold text-xl">P</span>
          </div>
          <span className="text-2xl font-bold text-[var(--color-brand-blue-dark)] tracking-tight">Pulse Fitness</span>
        </div>
        <h1 className="text-4xl font-bold text-zinc-900 leading-tight mb-4">
          Self-Service Portal<br />
          <span className="text-[var(--color-brand-blue-dark)]">Director's Briefing</span>
        </h1>
        <p className="text-zinc-500 text-base max-w-md mx-auto leading-relaxed">
          A complete overview of the Pulse Fitness Self-Service Portal — features, security, compliance, and roadmap. Built to transform how your customers manage their equipment.
        </p>
        <div className="mt-8 flex items-center justify-center gap-6 text-xs text-zinc-400">
          <span>Confidential</span>
          <span>|</span>
          <span>April 2026</span>
          <span>|</span>
          <span>Powered by GymAxis AI</span>
        </div>
      </div>

      {/* ─── THE OPPORTUNITY ─── */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-zinc-900 border-b-2 border-[var(--color-brand-blue-dark)] pb-2 mb-4">The Opportunity</h2>
        <p className="text-sm text-zinc-700 leading-relaxed mb-4">
          Every gym that buys Pulse Fitness equipment faces the same challenges: tracking warranty status, logging faults efficiently, managing maintenance schedules, and getting equipment data into their ERP systems.
        </p>
        <p className="text-sm text-zinc-700 leading-relaxed mb-4">
          The <strong>Pulse Fitness Self-Service Portal</strong> solves all of these — delivered as a white-label platform that sits under the Pulse brand. It turns every equipment sale into an ongoing digital relationship with the customer.
        </p>
        <div className="bg-[var(--color-brand-blue-dark)]/5 border border-[var(--color-brand-blue-dark)]/20 rounded-lg p-4 mt-4">
          <p className="text-sm font-semibold text-[var(--color-brand-blue-dark)] mb-2">Value to Pulse Fitness:</p>
          <ul className="text-sm text-zinc-700 space-y-1.5">
            <li className="flex gap-2"><span className="text-[var(--color-brand-blue-dark)] font-bold">1.</span> <strong>Recurring revenue</strong> — Pro subscriptions generate monthly income per site</li>
            <li className="flex gap-2"><span className="text-[var(--color-brand-blue-dark)] font-bold">2.</span> <strong>Customer retention</strong> — Portal becomes indispensable for day-to-day operations</li>
            <li className="flex gap-2"><span className="text-[var(--color-brand-blue-dark)] font-bold">3.</span> <strong>Reduced support burden</strong> — AI triage helps customers self-resolve faults</li>
            <li className="flex gap-2"><span className="text-[var(--color-brand-blue-dark)] font-bold">4.</span> <strong>Competitive advantage</strong> — No competitor offers an integrated AI maintenance platform</li>
            <li className="flex gap-2"><span className="text-[var(--color-brand-blue-dark)] font-bold">5.</span> <strong>Data intelligence</strong> — Real-time visibility into installed base, fault patterns, CAPEX cycles</li>
          </ul>
        </div>
      </section>

      {/* ─── TWO TIERS ─── */}
      <section className="mb-12 print-break">
        <h2 className="text-xl font-bold text-zinc-900 border-b-2 border-[var(--color-brand-blue-dark)] pb-2 mb-4">Two Tiers — Lite & Pro</h2>

        <div className="grid grid-cols-2 gap-4 mb-6">
          {/* Lite */}
          <div className="border border-zinc-200 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-lg bg-zinc-100 flex items-center justify-center">
                <span className="text-zinc-600 font-bold text-sm">L</span>
              </div>
              <div>
                <h3 className="font-bold text-zinc-900 text-sm">Pulse Lite</h3>
                <p className="text-[10px] text-zinc-500">Included with equipment purchase</p>
              </div>
            </div>
            <ul className="text-xs text-zinc-700 space-y-1.5">
              <li className="flex gap-1.5"><span className="text-green-600">&#10003;</span> Equipment inventory & tracking</li>
              <li className="flex gap-1.5"><span className="text-green-600">&#10003;</span> Fault logging & status tracking</li>
              <li className="flex gap-1.5"><span className="text-green-600">&#10003;</span> Warranty & SLA visibility</li>
              <li className="flex gap-1.5"><span className="text-green-600">&#10003;</span> Document storage (manuals, invoices)</li>
              <li className="flex gap-1.5"><span className="text-green-600">&#10003;</span> Product spec sheets & images</li>
              <li className="flex gap-1.5"><span className="text-green-600">&#10003;</span> QR code scanning for quick access</li>
              <li className="flex gap-1.5"><span className="text-green-600">&#10003;</span> Light & dark mode</li>
              <li className="flex gap-1.5"><span className="text-green-600">&#10003;</span> Mobile responsive</li>
            </ul>
          </div>

          {/* Pro */}
          <div className="border-2 border-[var(--color-brand-blue-dark)] rounded-lg p-4 bg-[var(--color-brand-blue-dark)]/[0.02]">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-lg bg-[var(--color-brand-blue-dark)] flex items-center justify-center">
                <span className="text-white font-bold text-sm">P</span>
              </div>
              <div>
                <h3 className="font-bold text-[var(--color-brand-blue-dark)] text-sm">Pulse Pro</h3>
                <p className="text-[10px] text-zinc-500">Monthly subscription</p>
              </div>
            </div>
            <ul className="text-xs text-zinc-700 space-y-1.5">
              <li className="flex gap-1.5"><span className="text-[var(--color-brand-blue-dark)]">&#10003;</span> <strong>Everything in Lite, plus:</strong></li>
              <li className="flex gap-1.5"><span className="text-[var(--color-brand-blue-dark)]">&#10003;</span> AI Fault Triage (GPT-5.2 powered)</li>
              <li className="flex gap-1.5"><span className="text-[var(--color-brand-blue-dark)]">&#10003;</span> AI Equipment Diagnosis</li>
              <li className="flex gap-1.5"><span className="text-[var(--color-brand-blue-dark)]">&#10003;</span> Maintenance check sheets & compliance</li>
              <li className="flex gap-1.5"><span className="text-[var(--color-brand-blue-dark)]">&#10003;</span> Operational reports & analytics</li>
              <li className="flex gap-1.5"><span className="text-[var(--color-brand-blue-dark)]">&#10003;</span> Gym floor layout designer</li>
              <li className="flex gap-1.5"><span className="text-[var(--color-brand-blue-dark)]">&#10003;</span> Supplier management</li>
              <li className="flex gap-1.5"><span className="text-[var(--color-brand-blue-dark)]">&#10003;</span> Weekly maintenance digest emails</li>
              <li className="flex gap-1.5"><span className="text-[var(--color-brand-blue-dark)]">&#10003;</span> Document Q&A (AI-powered)</li>
              <li className="flex gap-1.5"><span className="text-[var(--color-brand-blue-dark)]">&#10003;</span> Product tour & guided onboarding</li>
            </ul>
          </div>
        </div>
      </section>

      {/* ─── AI CAPABILITIES ─── */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-zinc-900 border-b-2 border-[var(--color-brand-blue-dark)] pb-2 mb-4">AI-Powered Capabilities</h2>
        <div className="space-y-3">
          <div className="bg-zinc-50 rounded-lg p-4">
            <h3 className="font-semibold text-zinc-900 text-sm mb-1">AI Invoice Parsing & Onboarding</h3>
            <p className="text-xs text-zinc-600">Drag and drop Pulse Fitness invoices (single or bulk — up to 20 at once). GPT-5.2 extracts site names, equipment details, serial numbers, warranty codes, and pricing. Generates Sicon-compatible CSV exports automatically. Adaptive to any supplier format.</p>
          </div>
          <div className="bg-zinc-50 rounded-lg p-4">
            <h3 className="font-semibold text-zinc-900 text-sm mb-1">AI Fault Triage (Pro)</h3>
            <p className="text-xs text-zinc-600">When a customer logs a fault, AI analyses the equipment type, fault description, and historical repair data to provide diagnosis, step-by-step repair instructions, parts likely needed, and estimated downtime — before an engineer is even dispatched.</p>
          </div>
          <div className="bg-zinc-50 rounded-lg p-4">
            <h3 className="font-semibold text-zinc-900 text-sm mb-1">AI Spec Sheet Management</h3>
            <p className="text-xs text-zinc-600">Bulk upload spec sheet PDFs. AI identifies equipment model, type, and key specifications. Automatically extracts the hero product image and matches spec sheets to equipment across all customer sites. Classic, Club Line, and Premium levels are auto-labelled.</p>
          </div>
          <div className="bg-zinc-50 rounded-lg p-4">
            <h3 className="font-semibold text-zinc-900 text-sm mb-1">AI Equipment Diagnosis (Pro)</h3>
            <p className="text-xs text-zinc-600">Deep analysis of specific equipment combining fault history, maintenance records, and technical documentation to provide actionable repair guidance with safety notes and part numbers.</p>
          </div>
        </div>
      </section>

      {/* ─── MASTER ADMIN ─── */}
      <section className="mb-12 print-break">
        <h2 className="text-xl font-bold text-zinc-900 border-b-2 border-[var(--color-brand-blue-dark)] pb-2 mb-4">Master Admin Panel (Pulse Internal)</h2>
        <p className="text-sm text-zinc-700 mb-3">A dedicated control centre for Pulse Fitness staff to manage the entire customer base:</p>
        <div className="grid grid-cols-2 gap-3">
          {[
            ['Customer Management', 'View all sites, equipment counts, fault status, and subscription tiers at a glance'],
            ['Onboard New Sites', 'Wizard-driven onboarding: upload invoice, AI extracts everything, create customer account in minutes'],
            ['Lite → Pro Upgrades', 'One-click upgrade from Lite to Pro. All AI features activate instantly for the customer'],
            ['Spec Sheet Library', 'Upload and manage product spec sheets. AI auto-matches to equipment across all sites'],
            ['CAPEX Intelligence', 'Cross-site replacement scoring — identify which equipment across the installed base needs replacing'],
            ['Activity & Audit', 'Full audit trail of all admin actions, user management, and system activity'],
          ].map(([title, desc]) => (
            <div key={title} className="border border-zinc-200 rounded-lg p-3">
              <h4 className="font-semibold text-zinc-900 text-xs mb-1">{title}</h4>
              <p className="text-[11px] text-zinc-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ─── SECURITY ─── */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-zinc-900 border-b-2 border-[var(--color-brand-blue-dark)] pb-2 mb-4">Security Architecture</h2>
        <p className="text-sm text-zinc-700 mb-3">Enterprise-grade security built in from day one:</p>
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs text-zinc-700">
          {[
            ['Authentication', 'Bcrypt password hashing, JWT tokens with 24h expiry, automatic refresh'],
            ['Brute Force Protection', 'Rate limiting (5 attempts/5min), account lockout after 5 failures (15min cooldown)'],
            ['Password Policy', 'Minimum 8 characters, uppercase, lowercase, number required'],
            ['Security Headers', 'HSTS, X-Frame-Options (DENY), XSS Protection, Content-Type-Options, Referrer-Policy'],
            ['CORS Hardening', 'Restricted origins, methods, and headers — no wildcard access in production'],
            ['Input Sanitisation', 'HTML entity escaping on all user-submitted text prevents XSS attacks'],
            ['Secrets Management', 'Zero hardcoded credentials. All secrets via environment variables, verified by automated scans'],
            ['File Validation', 'PDF compression on upload, file type verification, size limits enforced'],
          ].map(([title, desc]) => (
            <div key={title} className="py-2 border-b border-zinc-100">
              <span className="font-semibold text-zinc-900">{title}:</span> {desc}
            </div>
          ))}
        </div>
      </section>

      {/* ─── COMPLIANCE ─── */}
      <section className="mb-12 print-break">
        <h2 className="text-xl font-bold text-zinc-900 border-b-2 border-[var(--color-brand-blue-dark)] pb-2 mb-4">GDPR Compliance</h2>
        <p className="text-sm text-zinc-700 mb-3">Full compliance with the UK & EU General Data Protection Regulation:</p>
        <div className="space-y-2">
          {[
            ['Privacy Policy (Art. 13/14)', 'Published at /privacy — covers data collection, legal basis, user rights, retention periods, and third-party sharing'],
            ['Terms of Service', 'Published at /terms — covers AI disclaimer, data ownership, acceptable use, governing law (England & Wales)'],
            ['Cookie Consent (Art. 7)', 'GDPR-compliant banner with "Essential Only" and "Accept All" options. No tracking cookies used'],
            ['Right of Access (Art. 15)', 'Users can export all their personal data as a downloadable JSON file from their account settings'],
            ['Right to Erasure (Art. 17)', 'Users can request account deletion — personal data is anonymised, audit trail preserved for legal obligations'],
            ['Consent Management (Art. 7)', 'Versioned consent tracking with timestamps, IP addresses, and user-agent. Re-consent required when terms change'],
            ['Audit Trail', 'Immutable log of all sensitive actions: logins, data exports, consent changes, role changes, deletions'],
            ['Data Retention', 'Automated cleanup: expired tokens (24h), archived audit logs (12 months), stale imports (30 days)'],
            ['Accessibility (WCAG 2.1)', 'Skip-to-content links, keyboard navigation, focus indicators, screen reader support'],
          ].map(([title, desc]) => (
            <div key={title} className="flex gap-3 py-1.5">
              <span className="text-green-600 mt-0.5 shrink-0">&#10003;</span>
              <div className="text-xs"><strong className="text-zinc-900">{title}:</strong> <span className="text-zinc-600">{desc}</span></div>
            </div>
          ))}
        </div>
      </section>

      {/* ─── CODE QUALITY ─── */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-zinc-900 border-b-2 border-[var(--color-brand-blue-dark)] pb-2 mb-4">Code Quality & Reliability</h2>
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-green-700">0</p>
            <p className="text-[10px] text-green-600 font-medium">Lint Errors</p>
          </div>
          <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-green-700">0</p>
            <p className="text-[10px] text-green-600 font-medium">Hardcoded Secrets</p>
          </div>
          <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-green-700">100%</p>
            <p className="text-[10px] text-green-600 font-medium">API Smoke Tests</p>
          </div>
        </div>
        <ul className="text-xs text-zinc-700 space-y-1">
          <li className="flex gap-2"><span className="text-green-600">&#10003;</span> Automated quality gate runs on every commit (Ruff + ESLint + secrets scan)</li>
          <li className="flex gap-2"><span className="text-green-600">&#10003;</span> Python type hints across all core modules</li>
          <li className="flex gap-2"><span className="text-green-600">&#10003;</span> PDF compression on all uploads (30-90% storage savings)</li>
          <li className="flex gap-2"><span className="text-green-600">&#10003;</span> Pre-commit hooks prevent regressions</li>
        </ul>
      </section>

      {/* ─── ERP INTEGRATION ─── */}
      <section className="mb-12 print-break">
        <h2 className="text-xl font-bold text-zinc-900 border-b-2 border-[var(--color-brand-blue-dark)] pb-2 mb-4">ERP & System Integration</h2>
        <div className="space-y-3">
          <div className="border border-zinc-200 rounded-lg p-4">
            <h3 className="font-semibold text-zinc-900 text-sm mb-1">Sicon Service Integration</h3>
            <p className="text-xs text-zinc-600 mb-2">Full 44-column Sicon-compatible CSV export. Equipment data flows directly from invoice upload into Sicon's asset management format. Supports combined and per-invoice exports.</p>
            <p className="text-[10px] text-amber-600 font-medium">Status: Export working. Live API push awaiting Sicon API keys.</p>
          </div>
          <div className="border border-zinc-200 rounded-lg p-4">
            <h3 className="font-semibold text-zinc-900 text-sm mb-1">Sage 200 API</h3>
            <p className="text-xs text-zinc-600 mb-2">Scaffold built for Sage 200 ERP integration — customer sync, invoice reconciliation, and financial data flow.</p>
            <p className="text-[10px] text-amber-600 font-medium">Status: Scaffold complete. Awaiting live Sage 200 API credentials.</p>
          </div>
          <div className="border border-zinc-200 rounded-lg p-4">
            <h3 className="font-semibold text-zinc-900 text-sm mb-1">Orbit 4 API</h3>
            <p className="text-xs text-zinc-600">Active integration for case management and service request routing.</p>
          </div>
        </div>
      </section>

      {/* ─── ROADMAP ─── */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-zinc-900 border-b-2 border-[var(--color-brand-blue-dark)] pb-2 mb-4">Remaining Roadmap</h2>
        <p className="text-sm text-zinc-500 mb-3 italic">Excluding Stripe and email integration</p>
        <div className="space-y-3">
          <div>
            <h3 className="font-semibold text-zinc-900 text-sm mb-2">Near-Term (Awaiting Keys/Access)</h3>
            <ul className="text-xs text-zinc-700 space-y-1.5">
              <li className="flex gap-2"><span className="text-amber-500">&#9679;</span> Sicon Service live API push (two-way sync: push equipment in, pull resolution status back)</li>
              <li className="flex gap-2"><span className="text-amber-500">&#9679;</span> Sage 200 live integration (customer/invoice sync)</li>
            </ul>
          </div>
          <div>
            <h3 className="font-semibold text-zinc-900 text-sm mb-2">Future Enhancements</h3>
            <ul className="text-xs text-zinc-700 space-y-1.5">
              <li className="flex gap-2"><span className="text-zinc-400">&#9679;</span> Revenue forecasting from installed base data</li>
              <li className="flex gap-2"><span className="text-zinc-400">&#9679;</span> Push notifications for fault updates and warranty expiry</li>
              <li className="flex gap-2"><span className="text-zinc-400">&#9679;</span> Homepage demo video</li>
              <li className="flex gap-2"><span className="text-zinc-400">&#9679;</span> Two-factor authentication (2FA)</li>
              <li className="flex gap-2"><span className="text-zinc-400">&#9679;</span> Data encryption at rest</li>
              <li className="flex gap-2"><span className="text-zinc-400">&#9679;</span> Power dialer integration for CRM</li>
            </ul>
          </div>
        </div>
      </section>

      {/* ─── DEVELOPMENT INVESTMENT ─── */}
      <section className="mb-12 print-break">
        <h2 className="text-xl font-bold text-zinc-900 border-b-2 border-[var(--color-brand-blue-dark)] pb-2 mb-4">Development Investment Comparison</h2>
        <p className="text-sm text-zinc-700 mb-4">
          To put the scale of this platform into perspective, below is what a traditional web development agency or senior freelance developer would quote for a build of this scope.
        </p>

        <div className="border border-zinc-200 rounded-lg overflow-hidden mb-4">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-zinc-50 border-b border-zinc-200">
                <th className="text-left px-3 py-2 font-semibold text-zinc-900">Component</th>
                <th className="text-center px-3 py-2 font-semibold text-zinc-900">Timeline</th>
                <th className="text-right px-3 py-2 font-semibold text-zinc-900">Cost Estimate</th>
              </tr>
            </thead>
            <tbody className="text-zinc-700">
              {[
                ['Marketing site + theming + i18n (EN/FR/DE)', '3-4 weeks', '£7,500 - £12,000'],
                ['Auth system + roles + security hardening', '2-3 weeks', '£5,000 - £9,000'],
                ['Equipment management + lifecycle tracking', '3-4 weeks', '£7,500 - £12,000'],
                ['Fault logging + AI triage integration', '2-3 weeks', '£5,000 - £9,000'],
                ['AI invoice parsing + bulk import + Sicon CSV', '3-4 weeks', '£7,500 - £12,000'],
                ['Spec sheet management + AI matching', '2-3 weeks', '£5,000 - £9,000'],
                ['CAPEX analysis + predictive maintenance', '2-3 weeks', '£5,000 - £9,000'],
                ['CRM module (10 pages, pipeline, AI tools)', '4-6 weeks', '£10,000 - £18,000'],
                ['Master Admin + onboarding wizard', '2-3 weeks', '£5,000 - £9,000'],
                ['GDPR compliance + audit trail', '1-2 weeks', '£2,500 - £6,000'],
                ['QR scanning, gym layout, check sheets, reports', '3-4 weeks', '£7,500 - £12,000'],
                ['Testing, QA, deployment, documentation', '2-3 weeks', '£5,000 - £9,000'],
              ].map(([component, time, cost]) => (
                <tr key={component} className="border-b border-zinc-100">
                  <td className="px-3 py-1.5">{component}</td>
                  <td className="px-3 py-1.5 text-center text-zinc-500">{time}</td>
                  <td className="px-3 py-1.5 text-right font-medium">{cost}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-[var(--color-brand-blue-dark)]/5 border border-[var(--color-brand-blue-dark)]/20 rounded-lg p-3 text-center">
            <p className="text-lg font-bold text-[var(--color-brand-blue-dark)]">7-10</p>
            <p className="text-[10px] text-zinc-600 font-medium">Months (Agency)</p>
          </div>
          <div className="bg-[var(--color-brand-blue-dark)]/5 border border-[var(--color-brand-blue-dark)]/20 rounded-lg p-3 text-center">
            <p className="text-lg font-bold text-[var(--color-brand-blue-dark)]">£72k - £126k</p>
            <p className="text-[10px] text-zinc-600 font-medium">Agency Estimate</p>
          </div>
          <div className="bg-[var(--color-brand-blue-dark)]/5 border border-[var(--color-brand-blue-dark)]/20 rounded-lg p-3 text-center">
            <p className="text-lg font-bold text-[var(--color-brand-blue-dark)]">£100k - £150k+</p>
            <p className="text-[10px] text-zinc-600 font-medium">Top London Agency</p>
          </div>
        </div>

        <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-4 text-xs text-zinc-700 space-y-2">
          <p><strong className="text-zinc-900">Freelance senior full-stack developer:</strong> £50,000 - £80,000 over 5-7 months</p>
          <p><strong className="text-zinc-900">Mid-tier UK agency:</strong> £72,000 - £126,000 over 7-10 months</p>
          <p><strong className="text-zinc-900">Top London agency:</strong> £100,000 - £150,000+ over 8-12 months</p>
          <p className="pt-2 text-zinc-500 italic">Estimates based on UK market rates of £500-£800/day for senior full-stack development, including project management, design, development, testing, and deployment. Does not include ongoing maintenance, hosting, or AI API costs.</p>
        </div>
      </section>

      {/* ─── TECH STACK ─── */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-zinc-900 border-b-2 border-[var(--color-brand-blue-dark)] pb-2 mb-4">Technology Stack</h2>
        <div className="grid grid-cols-2 gap-x-8 gap-y-1.5 text-xs text-zinc-700">
          <div><strong className="text-zinc-900">Frontend:</strong> React, Tailwind CSS, Shadcn/UI</div>
          <div><strong className="text-zinc-900">Backend:</strong> Python FastAPI</div>
          <div><strong className="text-zinc-900">Database:</strong> MongoDB</div>
          <div><strong className="text-zinc-900">AI Engine:</strong> OpenAI GPT-5.2</div>
          <div><strong className="text-zinc-900">PDF Processing:</strong> PyMuPDF</div>
          <div><strong className="text-zinc-900">Authentication:</strong> JWT + Bcrypt</div>
          <div><strong className="text-zinc-900">Localisation:</strong> EN / FR / DE</div>
          <div><strong className="text-zinc-900">Theming:</strong> Light & Dark mode</div>
        </div>
      </section>

      {/* ─── CLOSING ─── */}
      <section className="text-center pt-8 border-t-2 border-[var(--color-brand-blue-dark)]">
        <p className="text-base font-semibold text-zinc-900 mb-2">The Pulse Fitness Self-Service Portal isn't just a product feature.</p>
        <p className="text-sm text-zinc-600 max-w-lg mx-auto leading-relaxed">
          It's a strategic platform that deepens customer relationships, generates recurring revenue, reduces support costs through AI, and gives Pulse Fitness an unmatched competitive advantage in the fitness equipment market.
        </p>
        <div className="mt-8 text-xs text-zinc-400">
          <p>Prepared for the Pulse Fitness Board of Directors</p>
          <p className="mt-1">Powered by GymAxis AI &middot; April 2026</p>
        </div>
      </section>

    </div>
  </div>
);

export default DirectorsHandout;
