import { Link } from 'react-router-dom';
import { useSeo } from '@/utils/seo';
import MarketingShell from '../Marketing/MarketingShell';
import { Activity, FileText, Mail } from 'lucide-react';

/**
 * SlaPage — Service Level Agreement (Iter 220ba).
 *
 * Mirrors the structure of `/app/memory/LEGAL/SLA.md` so the legal team
 * and any prospect can confirm uptime targets, service-credit schedule,
 * support-response SLAs, and incident-comms commitments before signing
 * an order form. Template — final wording lives in the signed Order Form.
 */
const SlaPage = () => {
  useSeo({
    title: 'Service Level Agreement | GymAxis AI',
    description: 'Uptime targets, service credits, support response times, backup commitments and incident communications for GymAxis AI customers.',
    canonical: 'https://gymaxisai.com/sla',
  });

  return (
    <MarketingShell>
      <main className="gx-marketing min-h-screen pt-24 pb-16" data-testid="sla-page">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] font-bold text-slate-500 mb-3">
            <Activity className="w-4 h-4 text-[var(--gx-brand-from)]" /> Legal · Operations
          </div>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tighter text-slate-900 mb-4">
            Service Level <span className="gx-gradient-text">Agreement</span>
          </h1>
          <p className="text-base text-slate-600 mb-2">
            <strong>Last updated:</strong> 28 May 2026 · v1.0
          </p>
          <p className="text-base text-slate-600 mb-8">
            This SLA forms part of the GymAxis AI <Link to="/terms" className="text-[var(--gx-brand-from)] underline">Terms of Service</Link> and applies
            to all paid plans unless a signed Order Form modifies it. The single-pod preview environment used by free trials is <strong>not</strong>{' '}
            covered — production deployments only.
          </p>

          <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 mb-8" data-testid="sla-billing-box">
            <div className="flex items-start gap-3">
              <FileText className="w-5 h-5 text-slate-700 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-900">Need a counter-signed copy?</p>
                <p className="text-sm text-slate-600 mt-1">
                  Email <a href="mailto:billing@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">billing@gymaxisai.com</a> with
                  your company details and plan tier. We respond within one business day with a PDF of this SLA pre-signed by our COO.
                </p>
              </div>
            </div>
          </div>

          <article className="prose prose-slate max-w-none text-sm leading-relaxed">
            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">1. Definitions</h2>
            <ul className="list-disc pl-6 space-y-1 text-slate-700">
              <li><strong>Service</strong>: the GymAxis AI web application — Master Admin, CRM, Memberships, Service Desk, Engineer App, and the public marketing site.</li>
              <li><strong>Uptime</strong>: the percentage of minutes in a calendar month during which the Service responds to a <code>GET /api/health</code> request with HTTP 200 within 5 seconds.</li>
              <li><strong>Excluded Time</strong>: scheduled maintenance announced at least 48 hours in advance; downtime caused by Customer-side issues (Customer's network, credentials, third-party integrations they connect themselves); Force Majeure as defined in the Terms of Service.</li>
              <li><strong>Incident</strong>: a continuous period of more than 5 minutes during which the Service is below the Uptime threshold.</li>
            </ul>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">2. Uptime commitments</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="sla-uptime-table">
                <thead className="bg-slate-50">
                  <tr><th className="text-left p-2 font-semibold">Plan tier</th><th className="text-left p-2 font-semibold">Monthly Uptime target</th><th className="text-left p-2 font-semibold">Measurement window</th></tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Starter</strong></td><td className="p-2">99.0%</td><td className="p-2">Calendar month</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Growth</strong></td><td className="p-2">99.5%</td><td className="p-2">Calendar month</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>Enterprise</strong></td><td className="p-2">99.9%</td><td className="p-2">Calendar month — OOH support included</td></tr>
                </tbody>
              </table>
            </div>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">3. Service credits</h2>
            <p>If we miss the Uptime target in a calendar month, the Customer is entitled to a service credit against the next monthly invoice, calculated against the affected workload's monthly fee:</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="sla-credits-table">
                <thead className="bg-slate-50">
                  <tr><th className="text-left p-2 font-semibold">Monthly Uptime measured</th><th className="text-left p-2 font-semibold">Starter</th><th className="text-left p-2 font-semibold">Growth</th><th className="text-left p-2 font-semibold">Enterprise</th></tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-200"><td className="p-2">≥ Target</td><td className="p-2">—</td><td className="p-2">—</td><td className="p-2">—</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2">Below target, ≥ 95.0%</td><td className="p-2">10%</td><td className="p-2">15%</td><td className="p-2">20%</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2">≥ 90.0%, &lt; 95.0%</td><td className="p-2">25%</td><td className="p-2">30%</td><td className="p-2">35%</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2">&lt; 90.0%</td><td className="p-2">50%</td><td className="p-2">50%</td><td className="p-2">75%</td></tr>
                </tbody>
              </table>
            </div>
            <ul className="list-disc pl-6 space-y-1 text-slate-700">
              <li>Service credits are the Customer's <strong>sole and exclusive remedy</strong> for failure to meet the Uptime target.</li>
              <li>Maximum credit in any calendar month: <strong>100%</strong> of that month's affected workload fee.</li>
              <li>Credits do not accumulate beyond the month earned and have no cash value.</li>
              <li>Customer must submit a credit request within <strong>30 days</strong> of the end of the affected month, in writing to <a href="mailto:billing@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">billing@gymaxisai.com</a>, with reasonable supporting evidence (timestamps, screenshots, request IDs).</li>
            </ul>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">4. Support response times</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="sla-support-table">
                <thead className="bg-slate-50">
                  <tr><th className="text-left p-2 font-semibold">Severity</th><th className="text-left p-2 font-semibold">Definition</th><th className="text-left p-2 font-semibold">Initial ack</th><th className="text-left p-2 font-semibold">Update cadence</th></tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>P0 — Critical</strong></td><td className="p-2">Service unavailable, data leak, or live payment failure for the Customer's tenant</td><td className="p-2">≤ 30 min (24×7 for Enterprise; UK business hours otherwise)</td><td className="p-2">Every 60 min until resolved</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>P1 — Major</strong></td><td className="p-2">Major feature unusable, no workaround</td><td className="p-2">≤ 2 hr (UK business hours)</td><td className="p-2">Every 4 hr</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>P2 — Minor</strong></td><td className="p-2">Feature degraded, workaround available</td><td className="p-2">≤ 1 business day</td><td className="p-2">Daily</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2"><strong>P3 — Cosmetic</strong></td><td className="p-2">Non-blocking</td><td className="p-2">Next sprint</td><td className="p-2">On request</td></tr>
                </tbody>
              </table>
            </div>
            <p>Support channels: <a href="mailto:support@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">support@gymaxisai.com</a> (all tiers) · Slack Connect (Growth + Enterprise) · Phone (Enterprise only, OOH for P0 only).</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">5. Scheduled maintenance</h2>
            <ul className="list-disc pl-6 space-y-1 text-slate-700">
              <li>GymAxis publishes maintenance windows on the status page at least <strong>48 hours</strong> in advance.</li>
              <li>Routine maintenance is targeted at <strong>02:00–05:00 UK time</strong>, max <strong>once per calendar month</strong>, max <strong>4 hours</strong> per window.</li>
              <li>Emergency maintenance (e.g. a critical security patch) may be performed with shorter notice; this time IS counted toward Excluded Time.</li>
            </ul>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">6. Backup &amp; restore commitments</h2>
            <ul className="list-disc pl-6 space-y-1 text-slate-700">
              <li><strong>RPO (Recovery Point Objective):</strong> ≤ 1 hour for Growth + Enterprise; ≤ 24 hours for Starter.</li>
              <li><strong>RTO (Recovery Time Objective):</strong> ≤ 4 hours during UK business hours, ≤ 12 hours OOH (Enterprise: 24×7 4-hour RTO).</li>
              <li>Backups are retained for <strong>30 days</strong> rolling.</li>
              <li>A restore drill is conducted at least <strong>annually</strong>; Enterprise customers may request to observe.</li>
            </ul>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">7. Incident communication</h2>
            <p>Customers will be notified of any incident affecting their tenant via:</p>
            <ol className="list-decimal pl-6 space-y-1 text-slate-700">
              <li><strong>Status page</strong> within 15 minutes of detection.</li>
              <li><strong>Email</strong> to the primary technical contact for P0/P1 incidents.</li>
              <li><strong>Post-mortem</strong> published within 5 working days for any P0, or any P1 lasting &gt; 4 hours.</li>
            </ol>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">8. Security incident notification</h2>
            <p>A confirmed personal-data breach affecting Customer Personal Data triggers the breach-notification obligations defined in our <Link to="/legal/dpa" className="text-[var(--gx-brand-from)] underline">Data Processing Agreement</Link>. We will notify the Customer without undue delay and within <strong>72 hours</strong> of becoming aware (UK ICO clock).</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">9. Modifications</h2>
            <p>GymAxis may modify this SLA with <strong>60 days' written notice</strong>. If the modification is materially adverse, the Customer may terminate the affected workload at the end of the notice period without penalty.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">10. Contact</h2>
            <ul className="list-none space-y-1 text-slate-700">
              <li><Mail className="inline w-4 h-4 mr-1 text-slate-500" /> Service credits: <a href="mailto:billing@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">billing@gymaxisai.com</a></li>
              <li><Mail className="inline w-4 h-4 mr-1 text-slate-500" /> Support: <a href="mailto:support@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">support@gymaxisai.com</a></li>
              <li><Mail className="inline w-4 h-4 mr-1 text-slate-500" /> Security: <a href="mailto:security@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">security@gymaxisai.com</a></li>
              <li><Mail className="inline w-4 h-4 mr-1 text-slate-500" /> DPO: <a href="mailto:dpo@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">dpo@gymaxisai.com</a></li>
            </ul>
          </article>
        </div>
      </main>
    </MarketingShell>
  );
};

export default SlaPage;
