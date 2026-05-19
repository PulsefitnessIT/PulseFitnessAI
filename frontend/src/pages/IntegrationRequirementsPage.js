import { Button } from '@/components/ui/button';
import { ArrowLeft, Printer, Circle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const IntegrationRequirementsPage = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-white">
      {/* Header Bar (hidden on print) */}
      <div className="print:hidden sticky top-0 bg-white border-b border-gray-200 z-10">
        <div className="max-w-3xl mx-auto px-6 py-3 flex items-center justify-between">
          <Button variant="ghost" onClick={() => navigate(-1)} className="text-gray-600">
            <ArrowLeft size={16} className="mr-2" /> Back
          </Button>
          <Button variant="outline" onClick={() => window.print()} className="text-gray-600">
            <Printer size={16} className="mr-2" /> Print / Save PDF
          </Button>
        </div>
      </div>

      {/* Document */}
      <div className="max-w-3xl mx-auto px-8 py-12 print:px-12 print:py-8">

        {/* Title */}
        <div className="text-center mb-10 pb-6 border-b-2 border-gray-900">
          <p className="text-sm uppercase tracking-[0.3em] text-gray-400 mb-3">Integration Requirements</p>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Orbit 4 → Sicon Service Bridge</h1>
          <p className="text-base text-gray-500 mt-2">What we need from Pulse Fitness to make this happen</p>
          <div className="flex items-center justify-center gap-4 mt-4 text-sm text-gray-400">
            <span>Prepared by: GymAxis AI</span>
            <span>|</span>
            <span>April 2026</span>
          </div>
        </div>

        {/* What We're Building */}
        <div className="mb-10">
          <h2 className="text-xl font-bold text-gray-900 mb-3 pb-2 border-b border-gray-200">What We're Building</h2>
          <p className="text-sm text-gray-600 leading-relaxed mb-4">
            A background service that <strong>automatically</strong> takes faults logged by gym operators in Orbit 4 and creates service cases in Sicon — without anyone needing to manually copy information between the two systems.
          </p>
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-5">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-sm">
              <div className="text-center p-3 bg-white border border-gray-200 rounded-lg flex-1 w-full">
                <p className="font-semibold text-gray-900">Orbit 4</p>
                <p className="text-gray-500 text-xs mt-1">Gym staff logs a fault</p>
              </div>
              <div className="text-gray-400 text-xl sm:rotate-0 rotate-90">→</div>
              <div className="text-center p-3 bg-gray-900 text-white rounded-lg flex-1 w-full">
                <p className="font-semibold">GymAxis AI</p>
                <p className="text-gray-300 text-xs mt-1">Automatic bridge</p>
              </div>
              <div className="text-gray-400 text-xl sm:rotate-0 rotate-90">→</div>
              <div className="text-center p-3 bg-white border border-gray-200 rounded-lg flex-1 w-full">
                <p className="font-semibold text-gray-900">Sicon Service</p>
                <p className="text-gray-500 text-xs mt-1">Case created automatically</p>
              </div>
            </div>
          </div>
        </div>

        {/* What We Need from Pulse Fitness */}
        <div className="mb-10">
          <h2 className="text-xl font-bold text-gray-900 mb-3 pb-2 border-b border-gray-200">What We Need from Pulse Fitness</h2>

          <div className="space-y-6 mt-4">
            {/* Item 1 */}
            <RequirementItem
              number={1}
              title="Orbit 4 API Token"
              who="Pulse Fitness (or whoever manages the Orbit 4 account)"
              how={[
                'Log in to Orbit 4 at app.orbit4.org',
                'Go to your Profile menu',
                'Click "API Tokens"',
                'Click "Generate API Token"',
                'Copy the token and send it to us securely',
              ]}
              why="This allows our system to listen for new faults and read asset/ticket information from Orbit 4."
              notes="This token gives read/write access. We will only use it to read tickets and push status updates back."
            />

            {/* Item 2 */}
            <RequirementItem
              number={2}
              title="Orbit 4 Webhook Setup"
              who="Pulse Fitness (or whoever manages the Orbit 4 account)"
              how={[
                'Log in to Orbit 4 at app.orbit4.org',
                'Go to your Profile menu',
                'Click "Webhooks"',
                'Click "Create Webhook"',
                'Enter the URL we provide (e.g. https://yourdomain.com/api/webhooks/orbit4)',
                'Subscribe to these events: ticket.created, ticket.updated, ticket.closed',
                'Save — a secret key will be generated',
                'Send us that secret key securely',
              ]}
              why="This is how Orbit 4 tells our system that a new fault has been logged. Without it, we'd have to constantly poll for new faults."
              notes="We will provide the exact webhook URL once the system is ready."
            />

            {/* Item 3 */}
            <RequirementItem
              number={3}
              title="Sicon Service API Credentials"
              who="Pulse Fitness IT / whoever manages Sicon"
              how={[
                'Provide the Sicon Service API base URL',
                'Provide API credentials (username, password, or API key)',
                'Confirm which Sicon fields map to: fault description, asset serial number, priority, gym location',
              ]}
              why="This allows our system to create service cases in Sicon automatically."
              notes="If Pulse Fitness already uses Sicon's API for other integrations, the same credentials can likely be reused."
            />

            {/* Item 4 */}
            <RequirementItem
              number={4}
              title="Field Mapping Confirmation"
              who="Someone at Pulse Fitness who knows both Orbit 4 and Sicon"
              how={[
                'Review a simple mapping table we provide (Orbit 4 field → Sicon field)',
                'Confirm or adjust the mappings',
                'Tell us about any Sicon-specific fields that need default values (e.g. priority, category, assigned team)',
              ]}
              why="Orbit 4 and Sicon use different field names. We need to know what goes where."
              notes="This is a 15-minute conversation or a one-page spreadsheet. We'll prepare the first draft."
            />

            {/* Item 5 */}
            <RequirementItem
              number={5}
              title="Pulse Fitness Domain for Webhook URL"
              who="Pulse Fitness IT"
              how={[
                'Set up a subdomain, e.g. api.pulsefitness.com',
                'Point it to our server via a reverse proxy or DNS CNAME (we will provide the target)',
                'This ensures Orbit 4 sees a Pulse Fitness URL, not a third-party URL',
              ]}
              why="When Orbit 4 sends fault data, it sends it to a webhook URL. That URL should belong to Pulse Fitness so their customers and Orbit 4 only ever see Pulse Fitness branding."
              notes="If this isn't possible immediately, we can start with our internal URL and switch later. The integration will work either way — this is purely about what Orbit 4 sees."
            />

            {/* Item 6 */}
            <RequirementItem
              number={6}
              title="Orbit 4 Test Account (Optional but Helpful)"
              who="Orbit 4 / Pulse Fitness"
              how={[
                'A sandbox or test environment in Orbit 4 where we can create test faults',
                'Alternatively, a test gym operator account we can use for development',
              ]}
              why="So we can test the full flow without creating real service cases."
              notes="If a test environment isn't available, we can build using the API documentation and test with a single real fault as a trial."
            />
          </div>
        </div>

        {/* What Changes for Gym Operators */}
        <div className="mb-10">
          <h2 className="text-xl font-bold text-gray-900 mb-3 pb-2 border-b border-gray-200">What Changes for Gym Operators?</h2>
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-5">
            <p className="text-sm text-emerald-800 font-semibold mb-2">Nothing.</p>
            <p className="text-sm text-emerald-700">
              Gym operators continue logging faults in Orbit 4 exactly as they do today. They won't know or need to know that the fault is being forwarded to Sicon. There is no new software, no new login, and no training required.
            </p>
          </div>
        </div>

        {/* What Does Orbit 4 See? */}
        <div className="mb-10">
          <h2 className="text-xl font-bold text-gray-900 mb-3 pb-2 border-b border-gray-200">What Does Orbit 4 See?</h2>
          <div className="bg-violet-50 border border-violet-200 rounded-lg p-5">
            <p className="text-sm text-violet-800 font-semibold mb-2">Pulse Fitness — not GymAxis AI.</p>
            <p className="text-sm text-violet-700 mb-3">
              The integration is fully white-labelled. Everything Orbit 4 sees identifies as Pulse Fitness:
            </p>
            <ul className="space-y-2 text-sm text-violet-700">
              <li className="flex items-start gap-2">
                <span className="font-semibold text-violet-800 flex-shrink-0">Webhook URL:</span>
                <span>Points to a Pulse Fitness domain (e.g. <code className="bg-violet-100 px-1 rounded text-xs">api.pulsefitness.com/webhooks</code>)</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="font-semibold text-violet-800 flex-shrink-0">API Identity:</span>
                <span>All calls identify as <code className="bg-violet-100 px-1 rounded text-xs">PulseFitness-ServiceBridge/1.0</code></span>
              </li>
              <li className="flex items-start gap-2">
                <span className="font-semibold text-violet-800 flex-shrink-0">Responses:</span>
                <span>Webhook acknowledgements reference "Pulse Fitness"</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="font-semibold text-violet-800 flex-shrink-0">GymAxis AI:</span>
                <span>Is never mentioned, referenced, or visible to Orbit 4 or their customers</span>
              </li>
            </ul>
          </div>
        </div>

        {/* What Changes for Pulse Fitness Staff */}
        <div className="mb-10">
          <h2 className="text-xl font-bold text-gray-900 mb-3 pb-2 border-b border-gray-200">What Changes for Pulse Fitness Staff?</h2>
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-5">
            <p className="text-sm text-blue-800 font-semibold mb-2">They stop manually copying faults from Orbit 4 into Sicon.</p>
            <p className="text-sm text-blue-700">
              Service cases appear in Sicon automatically. Staff can focus on resolving faults instead of admin work. All fault data, asset information, and gym details are carried across accurately.
            </p>
          </div>
        </div>

        {/* Timeline */}
        <div className="mb-10">
          <h2 className="text-xl font-bold text-gray-900 mb-3 pb-2 border-b border-gray-200">Estimated Timeline</h2>
          <div className="space-y-3">
            {[
              ['Week 1', 'Receive credentials and confirm field mappings'],
              ['Week 2–3', 'Build the integration and test with sample data'],
              ['Week 4', 'Live test with a small number of real faults'],
              ['Week 5', 'Full go-live — all Orbit 4 faults auto-forwarded to Sicon'],
            ].map(([when, what], i) => (
              <div key={i} className="flex items-start gap-3">
                <div className="w-20 flex-shrink-0 text-right">
                  <span className="text-sm font-semibold text-gray-900">{when}</span>
                </div>
                <div className="w-2 h-2 rounded-full bg-gray-900 mt-1.5 flex-shrink-0" />
                <p className="text-sm text-gray-600">{what}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Checklist Summary */}
        <div className="mb-10">
          <h2 className="text-xl font-bold text-gray-900 mb-3 pb-2 border-b border-gray-200">Summary Checklist</h2>
          <div className="space-y-2">
            {[
              'Orbit 4 API token',
              'Orbit 4 webhook created and secret key shared',
              'Sicon Service API credentials',
              'Field mapping confirmed',
              'Pulse Fitness domain for webhook URL (e.g. api.pulsefitness.com)',
              'Test environment access (optional)',
            ].map((item, i) => (
              <div key={i} className="flex items-center gap-3 p-2.5 rounded-lg border border-gray-100">
                <Circle size={18} className="text-gray-300 flex-shrink-0" />
                <span className="text-sm text-gray-700">{item}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-3 italic">Tick items off as they're provided. Once all items are received, we can begin the build immediately.</p>
        </div>

        {/* Contact */}
        <div className="mt-12 pt-8 border-t-2 border-gray-900 text-center">
          <h3 className="text-lg font-semibold text-gray-900 mb-1">Questions?</h3>
          <p className="text-sm text-gray-500">Contact GymAxis AI — we're happy to walk through any of these steps.</p>
          <p className="text-sm text-gray-400 mt-4">[Your Name] · [Your Email] · [Your Phone]</p>
        </div>

        <p className="mt-8 text-xs text-gray-400 text-center italic">
          This document is provided to support the GymAxis AI × Pulse Fitness partnership proposal.
        </p>
      </div>
    </div>
  );
};

const RequirementItem = ({ number, title, who, how, why, notes }) => (
  <div className="border border-gray-200 rounded-lg overflow-hidden print:break-inside-avoid">
    <div className="bg-gray-50 px-5 py-3 border-b border-gray-200 flex items-center gap-3">
      <div className="w-7 h-7 rounded-full bg-gray-900 text-white flex items-center justify-center text-sm font-semibold flex-shrink-0">{number}</div>
      <h3 className="font-semibold text-gray-900">{title}</h3>
    </div>
    <div className="p-5 space-y-3 text-sm">
      <div>
        <p className="text-gray-500 font-medium mb-1">Who provides this?</p>
        <p className="text-gray-700">{who}</p>
      </div>
      <div>
        <p className="text-gray-500 font-medium mb-1">How to get it:</p>
        <ol className="list-decimal pl-5 space-y-1 text-gray-700">
          {how.map((step, i) => <li key={i}>{step}</li>)}
        </ol>
      </div>
      <div>
        <p className="text-gray-500 font-medium mb-1">Why we need it:</p>
        <p className="text-gray-700">{why}</p>
      </div>
      {notes && (
        <div className="bg-amber-50 border border-amber-200 rounded px-3 py-2">
          <p className="text-amber-800 text-xs"><strong>Note:</strong> {notes}</p>
        </div>
      )}
    </div>
  </div>
);

export default IntegrationRequirementsPage;
