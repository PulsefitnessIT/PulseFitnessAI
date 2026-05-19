import { useSeo } from '@/utils/seo';
import MarketingShell from '../Marketing/MarketingShell';
import { ShieldCheck, AlertTriangle } from 'lucide-react';

/**
 * DpiaPage — platform-level Data Protection Impact Assessment summary
 * (iter 215c2). UK GDPR Art. 35 doesn't strictly require us as the
 * processor to publish a DPIA, but B2B procurement teams routinely
 * request one and it's a high-trust signal for prospects.
 */
const DpiaPage = () => {
  useSeo({
    title: 'Data Protection Impact Assessment | GymAxis AI',
    description: 'Summary DPIA for the GymAxis AI platform — UK GDPR Art. 35 risk assessment of personal-data processing across CRM, memberships, marketing and operations modules.',
    canonical: 'https://www.gymaxisai.com/legal/dpia',
  });

  return (
    <MarketingShell>
      <main className="gx-marketing min-h-screen pt-24 pb-16" data-testid="dpia-page">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] font-bold text-slate-500 mb-3">
            <ShieldCheck className="w-4 h-4 text-[var(--gx-brand-from)]" /> Legal · Compliance
          </div>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tighter text-slate-900 mb-4">
            Platform <span className="gx-gradient-text">DPIA Summary</span>
          </h1>
          <p className="text-base text-slate-600 mb-8">
            <strong>Last reviewed:</strong> 15 February 2026 · <strong>Next review:</strong> 15 August 2026 (6-monthly cycle)
          </p>

          <article className="prose prose-slate max-w-none text-sm leading-relaxed">
            <h2 className="text-xl font-bold text-slate-900 mt-4 mb-3">Purpose of this assessment</h2>
            <p>This Data Protection Impact Assessment (DPIA) summarises the risks associated with personal-data processing inside the GymAxis AI platform. It is published as a transparency artefact for prospects, customers, and the ICO if requested.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">1. Description of processing</h2>
            <p><strong>What:</strong> the GymAxis AI multi-tenant SaaS platform delivers gym CRM, member management, class booking, marketing campaigns, and operational record-keeping.</p>
            <p><strong>Why:</strong> to enable fitness operators to run their business — sell memberships, schedule classes, manage staff, market to leads, and track equipment compliance.</p>
            <p><strong>How:</strong> data is collected via web/mobile UI, public APIs, and CSV import. It is stored in MongoDB Atlas, processed by FastAPI services hosted in the EU, and accessed by authenticated operators of the relevant tenant.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">2. Necessity &amp; proportionality</h2>
            <p>Processing is justified under <strong>Art. 6(1)(b)</strong> (contract performance — gym member services) for transactional data, and <strong>Art. 6(1)(a)</strong> (consent) for any marketing communication. Special-category data is not processed by default.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">3. Identified risks &amp; mitigations</h2>

            <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="dpia-risk-table">
              <thead className="bg-slate-50">
                <tr>
                  <th className="text-left p-2 font-semibold">Risk</th>
                  <th className="text-left p-2 font-semibold">Likelihood</th>
                  <th className="text-left p-2 font-semibold">Impact</th>
                  <th className="text-left p-2 font-semibold">Mitigation</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-t border-slate-200">
                  <td className="p-2">Cross-tenant data leakage</td>
                  <td className="p-2">Low</td>
                  <td className="p-2">High</td>
                  <td className="p-2">Every query gated on <code>organization_id</code>; automated tests cover tenancy boundaries.</td>
                </tr>
                <tr className="border-t border-slate-200">
                  <td className="p-2">Operator account compromise (phishing / credential stuffing)</td>
                  <td className="p-2">Medium</td>
                  <td className="p-2">High</td>
                  <td className="p-2">Strong password policy, optional MFA, brute-force lockout, JWT revocation, 12h refresh.</td>
                </tr>
                <tr className="border-t border-slate-200">
                  <td className="p-2">Sub-processor breach (Stripe, Resend, etc.)</td>
                  <td className="p-2">Low</td>
                  <td className="p-2">Medium</td>
                  <td className="p-2">All sub-processors are SOC 2 / ISO 27001 certified; UK IDTA in place for US transfers.</td>
                </tr>
                <tr className="border-t border-slate-200">
                  <td className="p-2">Insider threat (GymAxis staff)</td>
                  <td className="p-2">Very low</td>
                  <td className="p-2">High</td>
                  <td className="p-2">Least-privilege IAM, tamper-evident audit log, mandatory annual training.</td>
                </tr>
                <tr className="border-t border-slate-200">
                  <td className="p-2">Data-subject rights non-compliance (delayed export / erasure)</td>
                  <td className="p-2">Low</td>
                  <td className="p-2">Medium</td>
                  <td className="p-2">Self-serve GDPR endpoints for both operators and members; SLA &lt; 30 days.</td>
                </tr>
                <tr className="border-t border-slate-200">
                  <td className="p-2">Loss of availability (outage)</td>
                  <td className="p-2">Low</td>
                  <td className="p-2">Medium</td>
                  <td className="p-2">External uptime monitoring of <code>/api/health/deep</code>; daily backups with documented restore.</td>
                </tr>
                <tr className="border-t border-slate-200">
                  <td className="p-2">Long-term data retention beyond purpose</td>
                  <td className="p-2">Medium</td>
                  <td className="p-2">Low</td>
                  <td className="p-2">Configurable per-org retention policy; automatic anonymisation of deleted member records.</td>
                </tr>
                <tr className="border-t border-slate-200">
                  <td className="p-2">AI feature data leakage to third-party LLMs</td>
                  <td className="p-2">Low</td>
                  <td className="p-2">Medium</td>
                  <td className="p-2">PII redaction before LLM calls; opt-in per feature; zero-retention agreements with model providers.</td>
                </tr>
              </tbody>
            </table>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">4. Outstanding actions</h2>
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-amber-900">Open items at next review</p>
                  <ul className="text-sm text-amber-900 mt-1 list-disc pl-5 space-y-1">
                    <li>Independent penetration test of the platform.</li>
                    <li>Establish an external uptime alerting policy with on-call rota.</li>
                    <li>Schedule the first annual sub-processor risk review.</li>
                  </ul>
                </div>
              </div>
            </div>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">5. Approval</h2>
            <p>Reviewed by the GymAxis AI Data Protection Officer. Customers and prospects may request the full internal DPIA package by emailing <a href="mailto:dpo@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">dpo@gymaxisai.com</a>.</p>
          </article>
        </div>
      </main>
    </MarketingShell>
  );
};

export default DpiaPage;
