/**
 * EngineerSupport — Engineer App help & troubleshooting.
 *
 * Replaces the old 404 at /support. Built-in static troubleshooting guides,
 * a short FAQ, and a "Contact Pulse Fitness" block. No backend dependency.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, LifeBuoy, ChevronDown, Mail, Phone, Wrench, ClipboardList,
  Camera, FileText, WifiOff, Bell, ShieldCheck, HelpCircle,
} from 'lucide-react';

const GUIDES = [
  {
    icon: Wrench,
    title: 'Logging a new job',
    steps: [
      'From the home screen tap Quick Actions → New job.',
      'Pick the customer & site (or add a new one), then choose the equipment/asset.',
      'Select the case type (Repair, PPM, etc.) and add a short fault description.',
      'Tap Save — the job appears under Today and in your diary.',
    ],
  },
  {
    icon: ClipboardList,
    title: 'Completing a PPM check sheet',
    steps: [
      'Open the job, then tap the Check sheet tab.',
      'Work through each line — tick Pass/Fail and add readings where prompted.',
      'Any Fail auto-flags a follow-up; add a note so the office has context.',
      'Tap Complete check sheet — it is saved to the job history and the report.',
    ],
  },
  {
    icon: Camera,
    title: 'Adding photos to a job',
    steps: [
      'Inside a job, tap Photos → Add photo.',
      'Take before/after shots — they attach to the job and the service report.',
      'If you are offline the photo is queued and uploads automatically once you reconnect.',
    ],
  },
  {
    icon: FileText,
    title: 'Sending a report or invoice',
    steps: [
      'Finish the work, then tap Send report (or Quick Actions → New invoice).',
      'Check the customer email is correct, add a message if needed.',
      'Tap Send — the customer receives a branded PDF and a copy is stored on the job.',
    ],
  },
  {
    icon: WifiOff,
    title: 'Working offline & syncing',
    steps: [
      'The app keeps working with no signal — jobs, notes and photos are saved on the device.',
      'A sync badge shows how many changes are waiting to upload.',
      'When you regain signal everything syncs automatically; pull down to refresh to force it.',
    ],
  },
  {
    icon: Bell,
    title: 'Not getting job notifications?',
    steps: [
      'Tap Enable push alerts on the home banner and allow notifications when prompted.',
      'On iPhone, add the app to your Home Screen first, then enable push from there.',
      'Check your phone Settings → Notifications and make sure alerts are allowed for the app.',
    ],
  },
  {
    icon: ShieldCheck,
    title: 'Signing in / password help',
    steps: [
      'Change your password any time from Account settings → Security.',
      'Forgotten it? Use "Forgot password" on the login screen to receive a reset link.',
      'Still stuck? Contact the Pulse Fitness office using the details below.',
    ],
  },
];

const FAQ = [
  { q: 'My job list is empty', a: 'New work is assigned by the office. If you expect a job and cannot see it, pull down to refresh, then contact dispatch if it is still missing.' },
  { q: 'A customer or site is missing', a: 'Customers and sites are managed centrally by the Pulse Fitness office and imported for you — ask the office to add or correct a record.' },
  { q: 'I picked the wrong case type', a: 'Open the job and change the case type from the job header before you complete the report.' },
  { q: 'The app feels out of date', a: 'Close and reopen the app, or pull down to refresh. If it persists, sign out and back in.' },
];

const Accordion = ({ icon: Icon, title, children, testid }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden" data-testid={testid}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50"
        data-testid={`${testid}-toggle`}
      >
        {Icon ? (
          <span className="w-9 h-9 rounded-lg bg-cyan-50 flex items-center justify-center flex-shrink-0">
            <Icon size={17} className="text-cyan-700" />
          </span>
        ) : null}
        <span className="flex-1 text-sm font-bold text-slate-900">{title}</span>
        <ChevronDown size={16} className={`text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="px-4 pb-4 pt-1 text-sm text-slate-600">{children}</div>}
    </div>
  );
};

export default function EngineerSupport() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-support-page">
      <header className="sticky top-0 z-10 bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-3">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50"
          aria-label="Back"
          data-testid="engineer-support-back"
        >
          <ArrowLeft size={16} />
        </button>
        <div className="flex items-center gap-2">
          <LifeBuoy size={18} className="text-cyan-700" />
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-700">Pulse Fitness · Engineer</p>
            <h1 className="text-base font-extrabold text-slate-900">Help &amp; Support</h1>
          </div>
        </div>
      </header>

      <div className="max-w-2xl mx-auto p-4 space-y-6">
        <section data-testid="engineer-support-guides">
          <h2 className="text-sm font-bold text-slate-500 uppercase tracking-wide mb-2">Troubleshooting guides</h2>
          <div className="space-y-2">
            {GUIDES.map((g, i) => (
              <Accordion key={g.title} icon={g.icon} title={g.title} testid={`engineer-support-guide-${i}`}>
                <ol className="list-decimal pl-5 space-y-1.5">
                  {g.steps.map((s, j) => <li key={j}>{s}</li>)}
                </ol>
              </Accordion>
            ))}
          </div>
        </section>

        <section data-testid="engineer-support-faq">
          <h2 className="text-sm font-bold text-slate-500 uppercase tracking-wide mb-2">FAQ</h2>
          <div className="space-y-2">
            {FAQ.map((f, i) => (
              <Accordion key={f.q} icon={HelpCircle} title={f.q} testid={`engineer-support-faq-${i}`}>
                <p>{f.a}</p>
              </Accordion>
            ))}
          </div>
        </section>

        <section data-testid="engineer-support-contact">
          <h2 className="text-sm font-bold text-slate-500 uppercase tracking-wide mb-2">Contact Pulse Fitness</h2>
          <div className="rounded-xl border border-slate-200 bg-white divide-y divide-slate-100">
            <a
              href="mailto:service@pulsefitness.com"
              className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50"
              data-testid="engineer-support-email"
            >
              <span className="w-9 h-9 rounded-lg bg-cyan-50 flex items-center justify-center">
                <Mail size={17} className="text-cyan-700" />
              </span>
              <div>
                <p className="text-sm font-bold text-slate-900">Email the office</p>
                <p className="text-xs text-slate-500">service@pulsefitness.com</p>
              </div>
            </a>
            <a
              href="tel:+441260294600"
              className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50"
              data-testid="engineer-support-phone"
            >
              <span className="w-9 h-9 rounded-lg bg-cyan-50 flex items-center justify-center">
                <Phone size={17} className="text-cyan-700" />
              </span>
              <div>
                <p className="text-sm font-bold text-slate-900">Call the office</p>
                <p className="text-xs text-slate-500">+44 (0)1260 294600 · Mon–Fri, 8am–5pm</p>
              </div>
            </a>
          </div>
        </section>

        <p className="text-center text-[11px] text-slate-400 pb-8">Pulse Fitness Engineer · v2</p>
      </div>
    </div>
  );
}
