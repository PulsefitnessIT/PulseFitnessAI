import React from 'react';
import { useSeo } from '@/utils/seo';
import MarketingShell from '../Marketing/MarketingShell';
import { Shield, Download, FileText } from 'lucide-react';

/**
 * DpaPage — Data Processing Agreement template (iter 215c2).
 *
 * UK GDPR Art. 28 requires a written contract between data controller
 * (the gym operator) and data processor (us) covering specific clauses.
 * This template-style page lets prospects review the standard DPA before
 * signing up; the legal team can later replace this with a downloadable
 * PDF or an e-signature flow.
 */
const DpaPage = () => {
  useSeo({
    title: 'Data Processing Agreement | GymAxis AI',
    description: 'Standard UK GDPR-compliant Data Processing Agreement between GymAxis AI Ltd and our customers (data controllers).',
    canonical: 'https://www.gymaxisai.com/legal/dpa',
  });

  return (
    <MarketingShell>
      <main className="gx-marketing min-h-screen pt-24 pb-16" data-testid="dpa-page">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] font-bold text-slate-500 mb-3">
            <Shield className="w-4 h-4 text-[var(--gx-brand-from)]" /> Legal · Compliance
          </div>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tighter text-slate-900 mb-4">
            Data Processing <span className="gx-gradient-text">Agreement</span>
          </h1>
          <p className="text-base text-slate-600 mb-2">
            <strong>Last updated:</strong> 15 February 2026 · v1.0
          </p>
          <p className="text-base text-slate-600 mb-8">
            This DPA forms part of the GymAxis AI Subscription Terms when one or both parties processes
            personal data subject to the UK GDPR or EU GDPR. Customers (the <em>Data Controller</em>) sign
            the Subscription Terms; this DPA applies automatically.
          </p>

          <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 mb-8" data-testid="dpa-download-box">
            <div className="flex items-start gap-3">
              <FileText className="w-5 h-5 text-slate-700 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-slate-900">Need a counter-signed copy?</p>
                <p className="text-sm text-slate-600 mt-1">
                  Email <a href="mailto:dpa@gymaxisai.com" className="text-[var(--gx-brand-from)] underline">dpa@gymaxisai.com</a> with your company details.
                  We respond within one business day with a PDF of this DPA pre-signed by our DPO.
                </p>
              </div>
            </div>
          </div>

          <article className="prose prose-slate max-w-none text-sm leading-relaxed">
            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">1. Definitions</h2>
            <p>Terms not defined here have the meaning given in the UK GDPR or in the GymAxis AI Subscription Terms.</p>
            <ul className="list-disc pl-6 space-y-1 text-slate-700">
              <li><strong>Customer</strong>: the entity subscribing to GymAxis AI services.</li>
              <li><strong>Personal Data</strong>: data relating to identified or identifiable natural persons processed by us on the Customer's behalf.</li>
              <li><strong>Sub-processor</strong>: a third party we engage to assist with processing (Stripe, Resend, Mongo Atlas, AWS S3, etc.).</li>
              <li><strong>Supervisory Authority</strong>: the UK Information Commissioner's Office (ICO).</li>
            </ul>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">2. Scope &amp; processing details</h2>
            <p><strong>Subject matter:</strong> provision of the GymAxis AI platform.</p>
            <p><strong>Duration:</strong> for the term of the Subscription plus a 30-day grace period for export, then 90 days for backups.</p>
            <p><strong>Nature &amp; purpose:</strong> hosting, storing, processing, and analysing Customer data to deliver gym CRM, memberships, marketing, and operations features.</p>
            <p><strong>Categories of data subjects:</strong> Customer's staff, members, prospects, and contacts.</p>
            <p><strong>Categories of personal data:</strong> contact details (name, email, phone, address), DOB, payment metadata (last-4 only), attendance, communication history, optional emergency contact, optional marketing preferences. We do not process special-category data unless explicitly uploaded by the Customer (e.g. medical waivers).</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">3. Roles</h2>
            <p>Customer is the <strong>Data Controller</strong>. GymAxis AI Ltd is the <strong>Data Processor</strong> for all Customer data, except where we collect data directly from website visitors (cookies, contact form), in which case we are an independent Controller per our Privacy Policy.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">4. Customer instructions</h2>
            <p>We process Personal Data only on documented instructions from the Customer, including transfers to third countries, unless required by UK or EU law. Setting up the platform, configuring features, and using the public API constitute documented instructions.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">5. Confidentiality &amp; staff</h2>
            <p>All GymAxis personnel with access to Personal Data are bound by written confidentiality obligations and have received UK GDPR awareness training.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">6. Security measures (Art. 32)</h2>
            <ul className="list-disc pl-6 space-y-1 text-slate-700">
              <li>Encryption in transit (TLS 1.2+) and at rest (AES-256) for all customer databases.</li>
              <li>Role-based access control with least-privilege principles.</li>
              <li>JWT session tokens, MFA available for all operator accounts.</li>
              <li>Tamper-evident audit log for sensitive operations.</li>
              <li>Annual penetration test by an independent third party.</li>
              <li>Quarterly secrets rotation, monthly dependency vulnerability scans.</li>
              <li>24-hour incident-response SLA; 72-hour breach notification per Art. 33.</li>
              <li>Regular automated backups with documented restore tests.</li>
            </ul>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">7. Sub-processors</h2>
            <p>Our current authorised sub-processors:</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-slate-200 rounded-lg my-4" data-testid="dpa-subprocessors-table">
                <thead className="bg-slate-50">
                  <tr><th className="text-left p-2 font-semibold">Sub-processor</th><th className="text-left p-2 font-semibold">Purpose</th><th className="text-left p-2 font-semibold">Region</th></tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-200"><td className="p-2">MongoDB Atlas</td><td className="p-2">Database hosting</td><td className="p-2">EU (Ireland)</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2">Stripe Payments UK Ltd</td><td className="p-2">Payment processing</td><td className="p-2">UK / EU / US (SCCs)</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2">Resend Inc.</td><td className="p-2">Transactional email delivery</td><td className="p-2">US (UK IDTA)</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2">AWS Inc.</td><td className="p-2">Object storage (uploads, exports)</td><td className="p-2">EU (Ireland)</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2">Anthropic PBC</td><td className="p-2">AI text generation (opt-in features)</td><td className="p-2">US (UK IDTA)</td></tr>
                  <tr className="border-t border-slate-200"><td className="p-2">Sentry / Functional Software Inc.</td><td className="p-2">Error tracking</td><td className="p-2">US (UK IDTA)</td></tr>
                </tbody>
              </table>
            </div>
            <p>We provide 30 days' notice via the in-app status page when adding a new sub-processor. The Customer may object in writing within 14 days.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">8. International transfers</h2>
            <p>Where Personal Data is transferred outside the UK / EEA, we rely on the UK International Data Transfer Addendum (IDTA) to the EU Standard Contractual Clauses or, where adequacy decisions exist, on those.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">9. Data subject rights</h2>
            <p>We provide self-serve endpoints in the operator portal for: access (export), rectification (in-app edits), erasure (close-account button), restriction (suspend processing), portability (CSV export), and objection (notification preferences). Member-side equivalents live at <code>/portal/me/gdpr</code>. We will assist the Customer in responding to data-subject requests at no extra charge.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">10. Personal data breach</h2>
            <p>We notify the Customer without undue delay (and within 72 hours) of any confirmed Personal Data breach, including: nature, categories &amp; approximate volume of records, name &amp; contact of our DPO, likely consequences, and measures taken or proposed.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">11. Audits</h2>
            <p>Once per year (or after a confirmed breach) the Customer may request a written summary of our security posture and most recent third-party penetration test. On-site audits may be arranged with 30 days' notice and at the Customer's reasonable cost.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">12. Termination &amp; deletion</h2>
            <p>Upon termination, we provide the Customer with a 30-day grace period to export data via the operator portal CSV export tools or via API. Thereafter we delete or anonymise all live Customer data. Backups containing Customer data are deleted on a rolling 90-day cycle.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">13. Liability</h2>
            <p>Our liability under this DPA is governed by the limitation-of-liability clause in the Subscription Terms.</p>

            <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3">14. Contact</h2>
            <p><strong>Data Protection Officer (DPO):</strong> dpo@gymaxisai.com<br/>
            <strong>Postal address:</strong> GymAxis AI Ltd, [Registered office address], United Kingdom.</p>
          </article>
        </div>
      </main>
    </MarketingShell>
  );
};

export default DpaPage;
