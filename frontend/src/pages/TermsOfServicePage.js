import React from 'react';
import { ArrowLeft } from 'lucide-react';

const TermsOfServicePage = () => (
  <div className="min-h-screen bg-white">
    <div className="max-w-3xl mx-auto px-6 py-16">
      <a href="/" className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-900 mb-8">
        <ArrowLeft size={16} /> Back to home
      </a>
      <h1 className="text-3xl font-bold text-zinc-900 mb-2">Terms of Service</h1>
      <p className="text-sm text-zinc-500 mb-8">Last updated: April 2026 · Version 1.0</p>

      <div className="prose prose-zinc max-w-none space-y-6 text-sm leading-relaxed text-zinc-700">
        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">1. Acceptance of Terms</h2>
          <p>By accessing or using GymAxis AI and the Pulse Fitness Self-Service Portal ("the Service"), you agree to be bound by these Terms of Service. If you are using the Service on behalf of an organisation, you represent that you have authority to bind that organisation.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">2. Description of Service</h2>
          <p>GymAxis AI provides a gym equipment maintenance management platform including:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li>Equipment inventory and lifecycle tracking</li>
            <li>Fault reporting with AI-powered triage</li>
            <li>Maintenance scheduling and check sheet management</li>
            <li>Document management (invoices, spec sheets, manuals)</li>
            <li>CAPEX analysis and replacement planning</li>
            <li>ERP integration (Sicon Service compatible exports)</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">3. User Accounts</h2>
          <ul className="list-disc pl-6 space-y-1">
            <li>You must provide accurate and complete registration information</li>
            <li>You are responsible for maintaining the security of your account credentials</li>
            <li>You must notify us immediately of any unauthorised use of your account</li>
            <li>Passwords must meet minimum strength requirements (8+ characters, mixed case, numbers)</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">4. Acceptable Use</h2>
          <p>You agree not to:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li>Use the Service for any unlawful purpose</li>
            <li>Upload malicious content, viruses, or harmful files</li>
            <li>Attempt to access other users' data without authorisation</li>
            <li>Reverse engineer, decompile, or attempt to extract source code</li>
            <li>Use automated tools to scrape or overload the Service</li>
            <li>Share your account credentials with unauthorised persons</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">5. AI Features Disclaimer</h2>
          <p>The AI-powered features (fault triage, equipment diagnosis, document analysis) are provided as decision-support tools. They do not replace professional engineering assessment. You acknowledge that:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li>AI recommendations are advisory and may not always be accurate</li>
            <li>Safety-critical decisions must be made by qualified personnel</li>
            <li>We are not liable for actions taken based solely on AI recommendations</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">6. Data Ownership</h2>
          <ul className="list-disc pl-6 space-y-1">
            <li>You retain ownership of all data you upload to the Service</li>
            <li>We do not claim ownership of your equipment data, fault reports, or uploaded documents</li>
            <li>You grant us a licence to process your data solely for providing the Service</li>
            <li>You may export or delete your data at any time (see Privacy Policy)</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">7. Service Availability</h2>
          <p>We aim for 99.9% uptime but do not guarantee uninterrupted service. Scheduled maintenance windows will be communicated in advance where possible.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">8. Subscription & Payment</h2>
          <ul className="list-disc pl-6 space-y-1">
            <li>Pulse Fitness Lite: Included as part of equipment purchase</li>
            <li>Pulse Fitness Pro: Monthly subscription, billed via Stripe</li>
            <li>GymAxis AI Full: Enterprise pricing, contact sales</li>
            <li>Refunds are handled per our published <a href="/refunds" className="text-blue-600 underline">Refund &amp; cancellation policy</a></li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">9. Limitation of Liability</h2>
          <p>To the maximum extent permitted by law, GymAxis AI shall not be liable for any indirect, incidental, special, or consequential damages arising from your use of the Service.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">10. Changes to Terms</h2>
          <p>We may update these terms from time to time. Material changes will be notified via email or in-app notification. Continued use after changes constitutes acceptance.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">11. Governing Law</h2>
          <p>These Terms shall be governed by the laws of England and Wales. Any disputes shall be subject to the exclusive jurisdiction of the English courts.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">12. Contact</h2>
          <p>For questions about these Terms, contact us at <strong>legal@gymaxisai.com</strong>.</p>
        </section>
      </div>
    </div>
  </div>
);

export default TermsOfServicePage;
