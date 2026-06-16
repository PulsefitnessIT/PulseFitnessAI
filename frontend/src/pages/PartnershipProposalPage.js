import { useRef } from 'react';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Printer } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const PartnershipProposalPage = () => {
  const navigate = useNavigate();
  const contentRef = useRef(null);

  const handlePrint = () => window.print();

  return (
    <div className="min-h-screen bg-white">
      {/* Header Bar (hidden on print) */}
      <div className="print:hidden sticky top-0 bg-white border-b border-gray-200 z-10">
        <div className="max-w-4xl mx-auto px-6 py-3 flex items-center justify-between">
          <Button variant="ghost" onClick={() => navigate(-1)} className="text-gray-600">
            <ArrowLeft size={16} className="mr-2" /> Back
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => navigate('/integration-requirements')} className="text-gray-600">
              Integration Requirements
            </Button>
            <Button variant="outline" onClick={handlePrint} className="text-gray-600">
              <Printer size={16} className="mr-2" /> Print / Save PDF
            </Button>
          </div>
        </div>
      </div>

      {/* Document */}
      <div ref={contentRef} className="max-w-4xl mx-auto px-8 py-12 print:px-12 print:py-8">
        {/* Title Block */}
        <div className="text-center mb-12 pb-8 border-b-2 border-gray-900">
          <p className="text-sm uppercase tracking-[0.3em] text-gray-400 mb-4">Partnership Proposal</p>
          <h1 className="text-4xl font-bold text-gray-900 mb-2">Pulse Fitness AI <span className="text-gray-400 font-light mx-3">×</span> Pulse Fitness</h1>
          <p className="text-lg text-gray-500 mt-3">Self-Service Portal — Commercial Partnership</p>
          <div className="flex items-center justify-center gap-6 mt-6 text-sm text-gray-400">
            <span>Prepared by: Pulse Fitness AI</span>
            <span>|</span>
            <span>April 2026</span>
            <span>|</span>
            <span className="text-amber-600 font-medium">Draft — For Discussion</span>
          </div>
        </div>

        {/* 1. Executive Summary */}
        <Section num="1" title="Executive Summary">
          <p>Pulse Fitness AI has developed a white-label <strong>Self-Service Maintenance Portal</strong> purpose-built for gym equipment management. This proposal outlines a commercial partnership with Pulse Fitness to deploy the portal across Pulse Fitness's customer base in two tiers:</p>
          <ul className="list-disc pl-6 mt-3 space-y-1">
            <li><strong>Pulse Self-Service (Lite)</strong> — Bundled free with Pulse Fitness equipment</li>
            <li><strong>Pulse Self-Service Pro</strong> — Premium subscription sold jointly</li>
          </ul>
          <p className="mt-3">Pulse Fitness AI retains full ownership of the Pulse Fitness AI platform and all underlying intellectual property. Pulse Fitness receives an exclusive licence to distribute the Self-Service Portal under the Pulse Fitness brand.</p>
        </Section>

        {/* 2. Product Tiers */}
        <Section num="2" title="Product Tiers">
          <h4 className="font-semibold text-gray-900 mb-3">Pulse Self-Service — Lite (Standard)</h4>
          <p className="text-sm text-gray-500 mb-3">Included at no additional cost for all Pulse Fitness equipment customers.</p>
          <FeatureTable features={[
            ['Equipment asset register', true],
            ['Fault reporting & tracking', true],
            ['Document library (manuals, certificates)', true],
            ['Dashboard overview & KPIs', true],
            ['Email notifications', true],
            ['Multi-user access', true],
            ['White-label Pulse Fitness branding', true],
          ]} />

          <h4 className="font-semibold text-gray-900 mb-3 mt-8">Pulse Self-Service — Pro</h4>
          <p className="text-sm text-gray-500 mb-3">Premium subscription unlocking advanced maintenance intelligence.</p>
          <FeatureTable features={[
            ['Everything in Lite', true],
            ['AI-powered fault diagnosis (text & photo)', true],
            ['Automated check sheets (daily/weekly/monthly)', true],
            ['Operational & compliance reports', true],
            ['Gym layout designer (floor plans)', true],
            ['Weekly maintenance digest emails', true],
            ['3-tier team management (Owner / Manager / Staff)', true],
            ['Priority support', true],
          ]} />
        </Section>

        {/* 3. Commercial Terms */}
        <Section num="3" title="Proposed Commercial Terms">
          <h4 className="font-semibold text-gray-900 mb-3">3.1 Lite Portal — Licence Fee</h4>
          <p className="mb-3">Pulse Fitness pays a per-site monthly licence fee for each gym using the Lite portal.</p>
          <table className="w-full text-sm border-collapse mb-4">
            <tbody>
              <Row label="Licence model" value="Per-site, per-month" />
              <Row label="Suggested price to Pulse Fitness" value="£3 – £5 per gym site / month" />
              <Row label="Pulse Fitness customer price" value="Bundled free with equipment (value-add)" />
              <Row label="Minimum commitment" value="12-month rolling agreement" />
              <Row label="Volume discount" value="Negotiable at 200+ sites" />
            </tbody>
          </table>
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm text-gray-600 mb-6">
            <strong>Example:</strong> 500 Pulse Fitness gym clients × £4/month = <strong className="text-gray-900">£24,000/year</strong> to Pulse Fitness AI. Pulse Fitness benefits from increased customer retention, reduced support calls, and a competitive differentiator — at no cost to their end customer.
          </div>

          <h4 className="font-semibold text-gray-900 mb-3">3.2 Pro Portal — Revenue Share</h4>
          <p className="mb-3">Pro subscriptions are sold jointly. Pulse Fitness AI receives a recurring commission on all Pro revenue.</p>
          <table className="w-full text-sm border-collapse mb-4">
            <tbody>
              <Row label="Suggested end-customer price" value="£49 – £99 per gym site / month" />
              <Row label="Pulse Fitness AI commission" value="25% of gross monthly revenue" />
              <Row label="Billing & collection" value="Managed by Pulse Fitness" />
              <Row label="Commission payment" value="Monthly, within 30 days of collection" />
              <Row label="Minimum term per subscriber" value="3-month initial commitment" />
            </tbody>
          </table>
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm text-gray-600 mb-6">
            <strong>Example:</strong> 100 gyms upgrade to Pro at £79/month = £94,800/year gross. Pulse Fitness AI commission (25%) = <strong className="text-gray-900">£23,700/year</strong>. Combined with Lite licence = <strong className="text-gray-900">£47,700/year total</strong>.
          </div>

          <h4 className="font-semibold text-gray-900 mb-3">3.3 Scaling Projections</h4>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b-2 border-gray-900">
                <th className="text-left py-2 font-semibold text-gray-900">Year</th>
                <th className="text-left py-2 font-semibold text-gray-900">Lite Sites</th>
                <th className="text-left py-2 font-semibold text-gray-900">Pro Sites</th>
                <th className="text-right py-2 font-semibold text-gray-900">Pulse Fitness AI Annual Revenue</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-gray-100">
                <td className="py-2 text-gray-700">Year 1</td>
                <td className="py-2 text-gray-700">300</td>
                <td className="py-2 text-gray-500">45 (15%)</td>
                <td className="py-2 text-right font-semibold text-gray-900">£25,092</td>
              </tr>
              <tr className="border-b border-gray-100">
                <td className="py-2 text-gray-700">Year 2</td>
                <td className="py-2 text-gray-700">600</td>
                <td className="py-2 text-gray-500">120 (20%)</td>
                <td className="py-2 text-right font-semibold text-gray-900">£57,312</td>
              </tr>
              <tr className="border-b border-gray-100">
                <td className="py-2 text-gray-700">Year 3</td>
                <td className="py-2 text-gray-700">1,000</td>
                <td className="py-2 text-gray-500">250 (25%)</td>
                <td className="py-2 text-right font-semibold text-gray-900">£107,400</td>
              </tr>
            </tbody>
          </table>
          <p className="text-xs text-gray-400 mt-2 italic">Assumes £4/month Lite licence, £79/month Pro price, 25% commission.</p>
        </Section>

        {/* 4. IP */}
        <Section num="4" title="Intellectual Property & Ownership">
          <table className="w-full text-sm border-collapse mb-4">
            <tbody>
              <Row label="Pulse Fitness AI platform (full product)" value="100% Pulse Fitness AI" />
              <Row label="Self-Service Portal codebase" value="100% Pulse Fitness AI" />
              <Row label="Pulse Fitness brand assets (logo, name)" value="100% Pulse Fitness" />
              <Row label="Customer data (gym operators)" value="Owned by end customer" />
              <Row label="AI models & training data" value="100% Pulse Fitness AI" />
            </tbody>
          </table>
          <ul className="list-disc pl-6 space-y-2 text-sm text-gray-600">
            <li>Pulse Fitness AI grants Pulse Fitness a <strong>non-exclusive, non-transferable licence</strong> to distribute the Self-Service Portal under the Pulse Fitness brand.</li>
            <li>Pulse Fitness <strong>may not</strong> sublicense, reverse-engineer, or independently fork the portal.</li>
            <li>Pulse Fitness AI retains the right to sell the same portal technology to other equipment manufacturers under different branding.</li>
          </ul>
        </Section>

        {/* 5. Development */}
        <Section num="5" title="Development & Investment">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="font-semibold text-gray-900 mb-2">Pulse Fitness AI Responsibilities</h4>
              <ul className="list-disc pl-5 space-y-1 text-sm text-gray-600">
                <li>Ongoing platform maintenance and bug fixes</li>
                <li>Infrastructure and hosting management</li>
                <li>AI model improvements and updates</li>
                <li>Security patches and compliance</li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-gray-900 mb-2">Pulse Fitness Responsibilities</h4>
              <ul className="list-disc pl-5 space-y-1 text-sm text-gray-600">
                <li>Fund development of new Pro features (quoted per feature)</li>
                <li>Customer onboarding, training, and first-line support</li>
                <li>Sales and marketing of Pro subscriptions</li>
                <li>Payment collection and customer billing</li>
              </ul>
            </div>
          </div>
          <div className="mt-4">
            <h4 className="font-semibold text-gray-900 mb-2">Shared</h4>
            <ul className="list-disc pl-5 space-y-1 text-sm text-gray-600">
              <li>Product roadmap input (quarterly review meetings)</li>
              <li>Customer feedback loop and feature prioritisation</li>
              <li>Joint marketing materials and case studies</li>
            </ul>
          </div>
        </Section>

        {/* 6. SLA */}
        <Section num="6" title="Service Level Agreement">
          <table className="w-full text-sm border-collapse">
            <tbody>
              <Row label="Platform uptime" value="99.5% monthly" />
              <Row label="Critical bug response" value="Within 4 business hours" />
              <Row label="Feature requests" value="Scoped within 5 business days" />
              <Row label="Data backups" value="Daily automated, 30-day retention" />
              <Row label="Security" value="SSL encryption, SOC 2 aligned practices" />
            </tbody>
          </table>
        </Section>

        {/* 7. Integration Services */}
        <Section num="7" title="Integration Services — Orbit 4 to Sicon Bridge">
          <p className="mb-4">As an additional capability, Pulse Fitness AI will provide a <strong>middleware integration layer</strong> that automatically bridges Orbit 4 (used by gym operators to log faults) with Sicon Service (Pulse Fitness's internal service management system).</p>

          <h4 className="font-semibold text-gray-900 mb-3">The Problem</h4>
          <p className="mb-4">Today, when a gym operator logs a fault in Orbit 4, Pulse Fitness staff must manually read the fault details in Orbit 4 and re-enter them into Sicon Service to create a service case. This is time-consuming, error-prone, and introduces delays in response times.</p>

          <h4 className="font-semibold text-gray-900 mb-3">The Solution</h4>
          <p className="mb-4">Pulse Fitness AI will sit between Orbit 4 and Sicon as an invisible middleware layer. When a fault is logged in Orbit 4, it is <strong>automatically</strong> forwarded to Sicon Service — no manual intervention required.</p>

          <div className="bg-gray-50 border border-gray-200 rounded-lg p-5 mb-6">
            <div className="flex flex-col md:flex-row items-center justify-between gap-4 text-sm">
              <div className="text-center p-3 bg-white border border-gray-200 rounded-lg flex-1">
                <p className="font-semibold text-gray-900">Orbit 4</p>
                <p className="text-gray-500 text-xs mt-1">Gym staff logs fault</p>
                <p className="text-gray-400 text-xs">(No change to their workflow)</p>
              </div>
              <div className="text-gray-400 text-2xl">→</div>
              <div className="text-center p-3 bg-gray-900 text-white rounded-lg flex-1">
                <p className="font-semibold">Pulse Fitness AI</p>
                <p className="text-gray-300 text-xs mt-1">Receives, transforms & forwards</p>
                <p className="text-gray-400 text-xs">(Invisible middleware)</p>
              </div>
              <div className="text-gray-400 text-2xl">→</div>
              <div className="text-center p-3 bg-white border border-gray-200 rounded-lg flex-1">
                <p className="font-semibold text-gray-900">Sicon Service</p>
                <p className="text-gray-500 text-xs mt-1">Service case auto-created</p>
                <p className="text-gray-400 text-xs">(No manual entry needed)</p>
              </div>
            </div>
          </div>

          <h4 className="font-semibold text-gray-900 mb-3">How It Works</h4>
          <ol className="list-decimal pl-6 space-y-2 mb-4">
            <li>Gym staff logs a fault in Orbit 4 — <strong>exactly as they do today</strong></li>
            <li>Orbit 4 fires a webhook (<code className="text-xs bg-gray-100 px-1 rounded">ticket.created</code>) to the Pulse Fitness AI server</li>
            <li>Pulse Fitness AI receives the fault data (asset, description, serial number, priority)</li>
            <li>Pulse Fitness AI transforms and maps the data to Sicon Service's required format</li>
            <li>A service case is <strong>automatically created</strong> in Sicon — no staff action needed</li>
            <li>When Sicon resolves the case, the status is pushed back to Orbit 4</li>
          </ol>

          <h4 className="font-semibold text-gray-900 mb-3">Benefits</h4>
          <table className="w-full text-sm border-collapse mb-4">
            <tbody>
              <Row label="Staff time saved" value="Eliminates manual fault re-entry from Orbit 4 to Sicon" />
              <Row label="Faster response" value="Service cases created instantly, not when staff find time" />
              <Row label="Zero errors" value="No typos, missed details, or forgotten faults" />
              <Row label="Zero training" value="Gym operators continue using Orbit 4 — nothing changes for them" />
              <Row label="Full audit trail" value="Every fault is tracked end-to-end across both systems" />
            </tbody>
          </table>

          <h4 className="font-semibold text-gray-900 mb-3">What's Required</h4>
          <p>A separate requirements document is provided outlining the specific access and credentials needed from Pulse Fitness and Orbit 4 to enable this integration.</p>
        </Section>

        {/* 8. Term */}
        <Section num="8" title="Term & Termination">
          <table className="w-full text-sm border-collapse">
            <tbody>
              <Row label="Initial term" value="12 months from launch date" />
              <Row label="Renewal" value="Auto-renews annually unless 90 days' written notice" />
              <Row label="Termination for cause" value="30 days' written notice for material breach" />
              <Row label="Post-termination" value="Read-only data export access for 90 days" />
              <Row label="Non-compete" value="24 months post-termination" />
            </tbody>
          </table>
        </Section>

        {/* 9. Next Steps */}
        <Section num="9" title="Next Steps">
          <div className="space-y-3">
            {[
              ['Review & Discussion', 'Pulse Fitness to review this proposal and provide feedback'],
              ['Commercial Negotiation', 'Agree final pricing, commission rates, and volume thresholds'],
              ['Integration Scoping', 'Orbit 4 and Sicon access provided for middleware build'],
              ['Legal Review', 'Both parties to engage solicitors for formal agreement'],
              ['Pilot Programme', '90-day pilot with 20–50 Pulse Fitness gym clients'],
              ['Full Rollout', 'Scale to full customer base with agreed support structure'],
            ].map(([title, desc], i) => (
              <div key={i} className="flex items-start gap-4">
                <div className="w-8 h-8 rounded-full bg-gray-900 text-white flex items-center justify-center text-sm font-semibold flex-shrink-0">{i + 1}</div>
                <div>
                  <p className="font-semibold text-gray-900">{title}</p>
                  <p className="text-sm text-gray-500">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </Section>

        {/* Contact */}
        <div className="mt-12 pt-8 border-t-2 border-gray-900 text-center">
          <h3 className="text-lg font-semibold text-gray-900 mb-1">Contact</h3>
          <p className="text-sm text-gray-500">Pulse Fitness AI</p>
          <p className="text-sm text-gray-400 mt-4">[Your Name] · [Your Email] · [Your Phone]</p>
        </div>

        {/* Disclaimer */}
        <p className="mt-12 text-xs text-gray-400 text-center italic">
          This document is a draft proposal for discussion purposes only and does not constitute a binding agreement. Final terms to be agreed in a formal commercial contract reviewed by both parties' legal representatives.
        </p>
      </div>
    </div>
  );
};

const Section = ({ num, title, children }) => (
  <div className="mb-10 print:break-inside-avoid">
    <h3 className="text-xl font-bold text-gray-900 mb-4 pb-2 border-b border-gray-200">
      <span className="text-gray-400 mr-2">{num}.</span>{title}
    </h3>
    <div className="text-sm text-gray-600 leading-relaxed">{children}</div>
  </div>
);

const Row = ({ label, value }) => (
  <tr className="border-b border-gray-100">
    <td className="py-2.5 pr-4 text-gray-500 w-1/2">{label}</td>
    <td className="py-2.5 text-gray-900 font-medium">{value}</td>
  </tr>
);

const FeatureTable = ({ features }) => (
  <table className="w-full text-sm border-collapse">
    <tbody>
      {features.map(([feature, included], i) => (
        <tr key={i} className="border-b border-gray-100">
          <td className="py-2 text-gray-700">{feature}</td>
          <td className="py-2 text-right text-emerald-600 font-medium w-20">{included ? 'Yes' : '—'}</td>
        </tr>
      ))}
    </tbody>
  </table>
);

export default PartnershipProposalPage;
