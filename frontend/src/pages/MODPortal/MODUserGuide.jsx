import { useState } from 'react';
import {
  Printer, ShieldCheck, LogIn, LayoutDashboard, Dumbbell, AlertTriangle,
  ClipboardList, FileText, Truck, CalendarClock, ShieldAlert, WifiOff,
  Users, LifeBuoy, ChevronRight, CheckCircle2, MapPin,
} from 'lucide-react';

/**
 * Pulse Fitness · MOD Service — portal user guide.
 * Viewable in-app (no download needed) and printable / saveable as a PDF
 * via the browser print dialog. Branded to Pulse (cyan #19CDFF on dark).
 */

const SECTIONS = [
  {
    id: 'getting-started', icon: LogIn, title: 'Getting started',
    body: [
      { h: 'Signing in', p: 'Open the MOD Service portal at /MODService and sign in with the email and password issued to your site. Every screen is marked with its protective marking (for example OFFICIAL‑SENSITIVE) — handle and share information in line with that marking.' },
      { h: 'Finding your way around', p: 'The tabs along the top take you to each area: Dashboard, Equipment, Faults, Reports, Documents and more. Your site preferences (such as collapsed equipment zones) are remembered on your device.' },
      { h: 'Who can do what', p: 'Everyone can log faults and incidents. Managers and site owners can additionally close incidents and manage settings. If a button is missing, your account role may not have access to that action.' },
    ],
  },
  {
    id: 'dashboard', icon: LayoutDashboard, title: 'The Dashboard',
    body: [
      { h: 'Your site at a glance', p: 'The Dashboard shows headline numbers — open faults, equipment counts and any items needing attention — so you can see the health of your site the moment you log in.' },
      { h: 'Jump straight to a problem', p: 'Cards and figures are shortcuts: selecting an open‑faults figure takes you to the Faults tab already filtered, so you spend less time searching.' },
    ],
  },
  {
    id: 'equipment', icon: Dumbbell, title: 'Equipment',
    body: [
      { h: 'Organised by zone and location', p: 'Machines are grouped by zone and location (for example “Main Gym › Cardio”). Each group can be collapsed to keep long lists tidy, and a red badge shows how many machines in a zone currently have a fault.' },
      { h: 'Filter and summarise quickly', p: 'Zone filter chips above the list let you show just one area. Summary cards give you the count and condition of machines per zone at a glance.' },
      { h: 'Editing a machine’s location', p: 'Open a machine and edit its location inline — start typing to reuse an existing location or type a new one. This keeps your floor plan accurate as kit moves around.' },
      { h: 'Moving kit in bulk', p: 'Use Bulk Move to relocate several machines at once — within a zone, across zones, or even to another site. If you make a mistake, an Undo prompt appears immediately so you can reverse the move.' },
      { h: 'QR codes', p: 'Each machine can carry a QR code so anyone on the floor can scan it and go straight to reporting a fault on that exact asset.' },
    ],
  },
  {
    id: 'report-fault', icon: AlertTriangle, title: 'Reporting a fault',
    body: [
      { h: 'The guided fault form', p: 'From the Faults tab choose “Report a fault”. A short, step‑by‑step form walks you through it — you can’t get lost or miss a required detail.' },
      { h: 'What you’ll be asked', p: '1) Pick the machine. 2) Tell us what’s wrong — choose the fault type, say whether it’s safe to use and still usable, and add a short description (at least 30 characters). 3) Optionally record “Any steps taken to fix?” so the engineer isn’t repeating what you’ve already tried. 4) Add photos or a short video — a thumbnail preview confirms each one attached. 5) Choose who is reporting it. 6) Review everything on one screen and submit.' },
      { h: 'What happens after you submit', p: 'You get a ticket reference (for example MOD‑2026‑XXXXX). The fault is automatically sent to the Pulse MOD Service desk and to the machine’s servicing supplier — you never have to look up or type an email address.' },
    ],
  },
  {
    id: 'track-fault', icon: ClipboardList, title: 'Tracking a fault',
    body: [
      { h: 'The fault card', p: 'Every fault shows its priority, status and who it was sent to (for example “Sent to Inda Fitness”). Urgent, unsafe faults are highlighted so they’re easy to spot.' },
      { h: 'Engineer booking chip', p: 'A small chip on each fault shows the engineer‑visit progress: amber “Sent” means the booking form has gone to the supplier and is awaiting completion; green “Completed” means the supplier has confirmed the engineer and vehicle details.' },
      { h: 'Supplier communication', p: 'A two‑way message thread is set up automatically against the supplier the fault was sent to — no need to add an email. Anything you post is delivered to them, and their replies appear back here.' },
      { h: 'Report to DIO', p: 'If a fault needs escalating, choose “Report to DIO”. A simple pop‑up lets you add a short note and confirm the DIO email address — if none is on file you can enter one and it’s saved for next time.' },
    ],
  },
  {
    id: 'supplier-card', icon: Truck, title: 'What the supplier sees',
    body: [
      { h: 'Their own job card', p: 'The supplier receives a branded email with a link to their job card — no login required. From there they can update the status, add notes and message your site directly.' },
      { h: 'Engineer Appointment Booking', p: 'The job card includes the Engineer Appointment Booking form. It is the supplier who completes the engineer and vehicle details needed for base access — not your site. Once they submit it, your fault’s booking chip turns green “Completed”.' },
      { h: 'Automatic reminders', p: 'If the booking form isn’t completed within 24 hours, the supplier is reminded automatically so nothing stalls.' },
    ],
  },
  {
    id: 'reports', icon: ShieldAlert, title: 'Reports & safety',
    body: [
      { h: 'ASER', p: 'The Activity Safety Events Register lives on the Reports tab for recording and reviewing safety events.' },
      { h: 'Reporting an incident', p: 'On the Reports tab choose “Report Incident” (next to ASER). Record what happened, who was involved, the injury severity and any RIDDOR considerations. The record is saved securely and a PDF copy is filed to Documents automatically.' },
      { h: 'The Incident Register', p: 'The “Incident Register” on the Reports tab lists every incident logged at your site. Expand any entry to see the full detail, view its PDF, or re‑save it to Documents. This means incidents are always retrievable later — not just at the moment they’re logged.' },
      { h: 'Closing an incident', p: 'Managers and owners can close an incident straight from the register: record the root cause, contributing factors and the corrective action taken (plus a RIDDOR reference if relevant). The record flips to “Closed”, is fully audited, and its filed PDF is refreshed.' },
    ],
  },
  {
    id: 'documents', icon: FileText, title: 'Documents',
    body: [
      { h: 'Your site’s filing cabinet', p: 'The Documents tab holds your site’s files. Incident PDFs are filed here automatically under an “Incidents” category, giving you a permanent, shareable record for audit and compliance.' },
    ],
  },
  {
    id: 'offline', icon: WifiOff, title: 'Working offline',
    body: [
      { h: 'No signal, no problem', p: 'The portal works as an app on your device. If connectivity drops on base you can still capture faults; they sync automatically once you’re back online, so nothing is lost.' },
    ],
  },
  {
    id: 'help', icon: LifeBuoy, title: 'Getting help',
    body: [
      { h: 'Support', p: 'For anything you can’t resolve on‑screen, contact the Pulse MOD Service desk. Quote your ticket or incident reference so we can help you quickly.' },
    ],
  },
];

function Cover({ onPrint }) {
  return (
    <div className="rounded-2xl overflow-hidden border" style={{ borderColor: 'var(--theme-border)' }}>
      <div className="p-8 sm:p-10" style={{ background: 'linear-gradient(135deg, #1B1D1D 0%, #0b1220 100%)', borderBottom: '4px solid #19CDFF' }}>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.3em] text-[#19CDFF]">Pulse Fitness · MOD Service</div>
            <h1 className="font-extrabold mt-3 text-3xl sm:text-4xl leading-tight" style={{ color: '#ffffff' }}>Portal User Guide</h1>
            <p className="text-zinc-300 mt-3 max-w-xl text-sm sm:text-base">
              Everything you need to run equipment, faults, engineer visits and safety records on your base — explained step by step.
            </p>
            <div className="mt-4 inline-flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-zinc-400">
              <ShieldCheck size={13} className="text-[#19CDFF]" /> Handle in line with your site’s protective marking
            </div>
          </div>
          <button
            onClick={onPrint}
            className="no-print shrink-0 inline-flex items-center gap-2 rounded-lg bg-[#19CDFF] hover:bg-[#66CCFF] text-[#04121a] font-extrabold px-5 py-3 text-sm transition-colors"
            data-testid="mod-guide-download"
          >
            <Printer size={16} /> Download / Print
          </button>
        </div>
      </div>
    </div>
  );
}

export default function MODUserGuide() {
  const [active, setActive] = useState(SECTIONS[0].id);
  const print = () => window.print();
  const go = (id) => {
    setActive(id);
    const el = document.getElementById(`guide-${id}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6 mod-guide" data-testid="mod-user-guide">
      <style>{`
        .mod-guide h1 { color: #ffffff !important; }
        @media print {
          .no-print { display: none !important; }
          .mod-guide { max-width: 100% !important; }
          .mod-guide, .mod-guide * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
          .mod-guide .guide-section { break-inside: avoid; }
          body { background: #fff !important; }
        }
      `}</style>

      <Cover onPrint={print} />

      <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-6">
        {/* Contents */}
        <nav className="no-print lg:sticky lg:top-4 self-start rounded-xl border p-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="mod-guide-toc">
          <div className="text-[10px] font-extrabold uppercase tracking-wider mb-2" style={{ color: 'var(--theme-text-muted)' }}>Contents</div>
          <ul className="space-y-1">
            {SECTIONS.map((s, i) => {
              const Icon = s.icon;
              const on = active === s.id;
              return (
                <li key={s.id}>
                  <button
                    onClick={() => go(s.id)}
                    className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-left text-[13px] font-semibold transition-colors ${on ? 'text-[#04121a]' : ''}`}
                    style={on ? { background: '#19CDFF' } : { color: 'var(--theme-text)' }}
                    data-testid={`mod-guide-toc-${s.id}`}
                  >
                    <Icon size={14} className={on ? '' : 'text-[#19CDFF]'} />
                    <span className="flex-1 truncate">{i + 1}. {s.title}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Sections */}
        <div className="space-y-5">
          {SECTIONS.map((s, i) => {
            const Icon = s.icon;
            return (
              <section
                key={s.id}
                id={`guide-${s.id}`}
                className="guide-section rounded-xl border p-5 sm:p-6 scroll-mt-4"
                style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}
                data-testid={`mod-guide-section-${s.id}`}
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="grid place-items-center w-9 h-9 rounded-lg" style={{ background: 'rgba(25,205,255,0.14)' }}>
                    <Icon size={18} className="text-[#19CDFF]" />
                  </div>
                  <h2 className="text-lg font-extrabold" style={{ color: 'var(--theme-text)' }}>
                    <span className="text-[#19CDFF]">{i + 1}.</span> {s.title}
                  </h2>
                </div>
                <div className="space-y-4">
                  {s.body.map((b, j) => (
                    <div key={j}>
                      <div className="flex items-center gap-2 text-sm font-bold mb-1" style={{ color: 'var(--theme-text)' }}>
                        <ChevronRight size={14} className="text-[#19CDFF]" /> {b.h}
                      </div>
                      <p className="text-sm leading-relaxed pl-6" style={{ color: 'var(--theme-text-muted)' }}>{b.p}</p>
                    </div>
                  ))}
                </div>
              </section>
            );
          })}

          <div className="rounded-xl border p-5 flex items-center gap-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface-2)' }}>
            <CheckCircle2 size={18} className="text-emerald-400 shrink-0" />
            <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>
              That’s everything. Keep this guide handy — you can reopen it any time from the <strong style={{ color: 'var(--theme-text)' }}>User Guide</strong> tab, or download a copy with the button at the top.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
