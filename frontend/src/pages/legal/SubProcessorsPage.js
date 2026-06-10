import { Link } from 'react-router-dom';
import { useSeo } from '@/utils/seo';
import MarketingShell from '../Marketing/MarketingShell';
import { Network, FileText, Mail } from 'lucide-react';

/**
 * SubProcessorsPage — Public sub-processor register (Iter 220ba).
 *
 * Mirrors `/app/memory/LEGAL/SUB_PROCESSORS.md`. Lists every third-party
 * processor that may handle Customer Personal Data under our DPA. The
 * notice obligation (30 days' written notice) is published here so
 * enterprise prospects + auditors can review without contacting sales.
 */
const SubProcessorsPage = () => {
  useSeo({
    title: 'Sub-processors | GymAxis AI',
    description: 'Authorised third-party data processors used by GymAxis AI for hosting, communications, payments, AI and observability. 30-day change notice.',
    canonical: 'https://gymaxisai.com/sub-processors',
  });

  return (
    <MarketingShell>
      <main className="gx-marketing min-h-screen pt-24 pb-16" data-testid="sub-processors-page">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] font-bold text-slate-500 mb-3">
            <Network className="w-4 h-4 text-[var(--gx-brand-from)]" /> Legal · Compliance
          </div>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tighter text-slate-900 mb-4">
            Sub-<span className="gx-gradient-text">processors</span>
          </h1>
          <p className="text-base text-slate-600 mb-2">
            <strong>Last updated:</strong> 28 May 2026 · v1.0
          </p>
          <p className="text-base text-slate-600 mb-6">
            This page lists every third-party processor that may handle Customer Personal Data under GymAxis AI's{' '}
            <Link to="/legal/dpa" className="text-[var(--gx-brand-from)] underline">Data Processing Agreement</Link>.
          </p>

          <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 mb-8" data-testid="sub-processors-notice">
            <div className="flex items-start gap-3">
              <FileText className="w-5 h-5 text-amber-700 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-amber-900">30-day change notice</p>
                <p className="text-sm text-amber-800 mt-1">
                  GymAxis will provide customers at least <strong>30 days' notice</strong> before adding, replacing or materially changing a
                  sub-processor. Customers may object in writing; if the objection cannot be resolved within 30 days the customer may terminate
                  the affected workload without penalty. Subscribe at{' '}
                  <a href="mailto:dpo@gymaxisai.com?subject=subscribe%20sub-processor" className="text-amber-900 underline">dpo@gymaxisai.com</a>.
                </p>
              </div>
            </div>
          </div>

          <article className="prose prose-slate max-w-none text-sm leading-relaxed">
            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">1. Infrastructure &amp; hosting</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="subp-infra-table">
                <thead className="bg-slate-50">
                  <tr><th className="text-left p-2 font-semibold">Sub-processor</th><th className="text-left p-2 font-semibold">Purpose</th><th className="text-left p-2 font-semibold">Region</th><th className="text-left p-2 font-semibold">Transfer mechanism</th></tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Emergent Labs</strong></td><td className="p-2">Platform hosting (compute, container orchestration, network ingress)</td><td className="p-2">UK / EU</td><td className="p-2">UK GDPR / EU SCCs (if any non-UK/EEA)</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>MongoDB</strong> <em>(via Emergent-managed cluster)</em></td><td className="p-2">Primary application database</td><td className="p-2">UK / EU</td><td className="p-2">Sub-processor of Emergent Labs</td></tr>
                </tbody>
              </table>
            </div>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">2. Communications</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="subp-comms-table">
                <thead className="bg-slate-50">
                  <tr><th className="text-left p-2 font-semibold">Sub-processor</th><th className="text-left p-2 font-semibold">Purpose</th><th className="text-left p-2 font-semibold">Region</th><th className="text-left p-2 font-semibold">Transfer mechanism</th></tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Resend</strong></td><td className="p-2">Transactional + marketing email delivery</td><td className="p-2">US / EU-Frankfurt</td><td className="p-2">SCCs · UK IDTA</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Twilio</strong> <em>(planned, currently mocked)</em></td><td className="p-2">SMS dispatch</td><td className="p-2">US</td><td className="p-2">SCCs · UK IDTA</td></tr>
                </tbody>
              </table>
            </div>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">3. Payments</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="subp-payments-table">
                <thead className="bg-slate-50">
                  <tr><th className="text-left p-2 font-semibold">Sub-processor</th><th className="text-left p-2 font-semibold">Purpose</th><th className="text-left p-2 font-semibold">Region</th><th className="text-left p-2 font-semibold">Transfer mechanism</th></tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Stripe Payments Europe Ltd / Stripe Inc.</strong></td><td className="p-2">Card processing, subscription billing, Stripe Connect for engineer payouts</td><td className="p-2">UK / Ireland / US</td><td className="p-2">SCCs · UK IDTA · Stripe DPA</td></tr>
                </tbody>
              </table>
            </div>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">4. AI / LLM providers</h2>
            <p>GymAxis uses Large Language Models for the AI Assistant, SEO Autopilot, Tender drafting and CRM insights. Provider selection happens via the Emergent LLM Key proxy.</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="subp-ai-table">
                <thead className="bg-slate-50">
                  <tr><th className="text-left p-2 font-semibold">Sub-processor</th><th className="text-left p-2 font-semibold">Purpose</th><th className="text-left p-2 font-semibold">Region</th><th className="text-left p-2 font-semibold">Transfer mechanism</th></tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>OpenAI</strong></td><td className="p-2">Text (GPT-4o / GPT-5.2), image (GPT Image 1), Whisper STT</td><td className="p-2">US</td><td className="p-2">SCCs · OpenAI DPA · "no training on API data"</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Anthropic</strong></td><td className="p-2">Text (Claude Sonnet 4.5)</td><td className="p-2">US / EU</td><td className="p-2">SCCs · Anthropic DPA</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Google (Gemini)</strong></td><td className="p-2">Text, image (Nano Banana)</td><td className="p-2">US / EU</td><td className="p-2">SCCs · Google DPA</td></tr>
                </tbody>
              </table>
            </div>
            <p className="text-xs text-slate-500 mt-2"><strong>Operator obligation:</strong> Do not paste raw special-category data (health, biometric, criminal) into AI prompts. Use the redact-before-prompt pattern documented in the Help Centre.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">5. Observability &amp; analytics</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="subp-obs-table">
                <thead className="bg-slate-50">
                  <tr><th className="text-left p-2 font-semibold">Sub-processor</th><th className="text-left p-2 font-semibold">Purpose</th><th className="text-left p-2 font-semibold">Region</th><th className="text-left p-2 font-semibold">Transfer mechanism</th></tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Sentry</strong> <em>(enabled when SENTRY_DSN is set)</em></td><td className="p-2">Server + client error tracking (no PII)</td><td className="p-2">US / EU options</td><td className="p-2">SCCs · UK IDTA</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>PostHog</strong> <em>(planned)</em></td><td className="p-2">Product analytics, anonymous event metadata</td><td className="p-2">EU-Frankfurt</td><td className="p-2">SCCs</td></tr>
                </tbody>
              </table>
            </div>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">6. Integrations enabled per-tenant (opt-in, not default)</h2>
            <p>These sub-processors only receive data if the customer <strong>explicitly enables</strong> the integration in their workspace:</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="subp-optin-table">
                <thead className="bg-slate-50">
                  <tr><th className="text-left p-2 font-semibold">Sub-processor</th><th className="text-left p-2 font-semibold">Triggered by</th><th className="text-left p-2 font-semibold">Data categories</th></tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Microsoft (Outlook Calendar)</strong></td><td className="p-2">Tenant connects Microsoft 365 account</td><td className="p-2">Calendar events, meeting attendees</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>DocuSign</strong></td><td className="p-2">Tenant sends a CRM quote for signature</td><td className="p-2">Recipient name + email, document content</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Sage 200</strong></td><td className="p-2">Tenant maps Sage company in <code>/master-admin/integrations</code></td><td className="p-2">Invoice + customer ledger data</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Sicon (Service Manager)</strong></td><td className="p-2">Tenant connects Sicon credentials</td><td className="p-2">Equipment service history</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Google Calendar</strong> <em>(via Emergent Auth)</em></td><td className="p-2">Tenant connects Google account</td><td className="p-2">Calendar events</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Meta (Instagram Graph API)</strong> <em>(planned)</em></td><td className="p-2">Tenant connects IG Business account</td><td className="p-2">Post content + media</td></tr>
                </tbody>
              </table>
            </div>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">7. Audit &amp; legal</h2>
            <p>GymAxis itself acts as <strong>data processor</strong> when handling Customer Personal Data on behalf of a Tenant. Where Tenant Personal Data ends up in our paid sub-processors above, we have a written DPA in place with each. A list of executed DPAs is available on request: <a href="mailto:dpo@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">dpo@gymaxisai.com</a>.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">8. Changes to this list</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="subp-changelog-table">
                <thead className="bg-slate-50">
                  <tr><th className="text-left p-2 font-semibold">Version</th><th className="text-left p-2 font-semibold">Date</th><th className="text-left p-2 font-semibold">Change</th></tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-200"><td className="p-2">1.0</td><td className="p-2">2026-05-28</td><td className="p-2">Initial publication</td></tr>
                </tbody>
              </table>
            </div>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">9. Contact</h2>
            <ul className="list-none space-y-1 text-slate-700">
              <li><Mail className="inline w-4 h-4 mr-1 text-slate-500" /> Data Protection Officer (DPO): <a href="mailto:dpo@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">dpo@gymaxisai.com</a></li>
              <li><Mail className="inline w-4 h-4 mr-1 text-slate-500" /> Security disclosure: <a href="mailto:security@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">security@gymaxisai.com</a></li>
            </ul>
          </article>
        </div>
      </main>
    </MarketingShell>
  );
};

export default SubProcessorsPage;
