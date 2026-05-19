import { ArrowLeft } from 'lucide-react';

const PrivacyPolicyPage = () => (
  <div className="min-h-screen bg-white">
    <div className="max-w-3xl mx-auto px-6 py-16">
      <a href="/" className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-900 mb-8">
        <ArrowLeft size={16} /> Back to home
      </a>
      <h1 className="text-3xl font-bold text-zinc-900 mb-2">Privacy Policy</h1>
      <p className="text-sm text-zinc-500 mb-8">Last updated: April 2026 · Version 1.0</p>

      <div className="prose prose-zinc max-w-none space-y-6 text-sm leading-relaxed text-zinc-700">
        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">1. Who We Are</h2>
          <p>GymAxis AI ("we", "our", "us") operates the GymAxis AI platform and the Pulse Fitness Self-Service Portal. We are the data controller for the personal data processed through our services.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">2. Data We Collect</h2>
          <p>We collect and process the following personal data:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li><strong>Account data:</strong> Name, email address, company name, role</li>
            <li><strong>Equipment data:</strong> Serial numbers, locations, fault reports, maintenance records</li>
            <li><strong>Usage data:</strong> Login times, feature usage, IP addresses</li>
            <li><strong>Uploaded content:</strong> Invoice PDFs, spec sheets, fault photos/videos</li>
            <li><strong>Communication data:</strong> Support messages, fault descriptions</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">3. Legal Basis for Processing</h2>
          <p>We process your data under the following legal bases (GDPR Art. 6):</p>
          <ul className="list-disc pl-6 space-y-1">
            <li><strong>Contract performance:</strong> To provide the gym maintenance platform services you have subscribed to</li>
            <li><strong>Legitimate interest:</strong> To improve our services, ensure security, and prevent fraud</li>
            <li><strong>Consent:</strong> For marketing communications and optional AI-powered features</li>
            <li><strong>Legal obligation:</strong> To maintain audit trails and comply with regulations</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">4. How We Use Your Data</h2>
          <ul className="list-disc pl-6 space-y-1">
            <li>Provide and maintain the equipment management platform</li>
            <li>Process fault reports and generate AI-powered triage assessments</li>
            <li>Generate ERP-compatible CSV exports for your finance systems</li>
            <li>Match spec sheets to equipment using AI analysis</li>
            <li>Send service notifications and maintenance reminders</li>
            <li>Maintain security audit trails</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">5. Data Sharing</h2>
          <p>We do not sell your personal data. We share data only with:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li><strong>AI providers:</strong> Equipment descriptions and fault text are sent to OpenAI for triage analysis (no personal identifiers included)</li>
            <li><strong>Cloud storage:</strong> Uploaded files are stored securely in cloud storage</li>
            <li><strong>Payment processors:</strong> Stripe processes payment data under their own privacy policy</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">6. Your Rights (GDPR)</h2>
          <p>Under GDPR, you have the right to:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li><strong>Access:</strong> Request a copy of all data we hold about you (available in Settings &gt; Privacy)</li>
            <li><strong>Rectification:</strong> Correct inaccurate personal data</li>
            <li><strong>Erasure:</strong> Request deletion of your account and associated data</li>
            <li><strong>Portability:</strong> Export your data in a machine-readable format (JSON)</li>
            <li><strong>Restriction:</strong> Request we limit processing of your data</li>
            <li><strong>Object:</strong> Object to processing based on legitimate interest</li>
          </ul>
          <p className="mt-2">To exercise these rights, use the self-service options in your account settings or contact us at privacy@gymaxisai.com.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">7. Data Retention</h2>
          <ul className="list-disc pl-6 space-y-1">
            <li>Account data is retained while your account is active</li>
            <li>After account deletion, personal data is anonymised within 30 days</li>
            <li>Audit logs are retained for 12 months, then archived</li>
            <li>Password reset tokens are purged after 24 hours</li>
            <li>Uploaded files are retained for the duration of your subscription</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">8. Security</h2>
          <p>We implement industry-standard security measures including:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li>Bcrypt password hashing</li>
            <li>JWT token authentication with 24-hour expiry</li>
            <li>Rate limiting and brute-force protection</li>
            <li>Security headers (HSTS, CSP, X-Frame-Options)</li>
            <li>Input sanitisation to prevent XSS attacks</li>
            <li>HTTPS encryption in transit</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">9. Cookies</h2>
          <p>We use only essential cookies required for authentication (JWT token stored in localStorage). We do not use tracking cookies or third-party analytics cookies.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">10. Contact</h2>
          <p>For privacy-related enquiries, contact our Data Protection Officer at <strong>privacy@gymaxisai.com</strong>.</p>
        </section>
      </div>
    </div>
  </div>
);

export default PrivacyPolicyPage;
