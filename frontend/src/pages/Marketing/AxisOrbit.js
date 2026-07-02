/**
 * Pulse Fitness AXIS orbit hero — central animated visual.
 *
 * Iter 220bc — collapsed 6 → 4 modules + interactive feature constellation.
 *
 * 4 module nodes orbit a glowing center (the GA monogram) at constant
 * angular velocity. Hover any node and:
 *   • The orbit ring pauses (existing CSS).
 *   • The hovered node lifts + accents.
 *   • Its sub-features fan out as small pill-icons around it (a mini
 *     mind-map), staggered for a smooth reveal.
 *   • The other 3 nodes dim so the focus stays on the hovered branch.
 *
 * The rest of the visual language (concentric rings, glow,
 * counter-rotating labels) is unchanged so the homepage looks the
 * same — just more useful on hover.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  Wrench, Users, Calendar, Megaphone, HardHat,
  Wallet, AlertTriangle, ListChecks, UserCog,
  Building2, GitBranch, LineChart,
  CalendarClock, Receipt, Smartphone, BookOpen,
  Image as ImageIcon, MailPlus, Heart,
  MapPin, Camera, PoundSterling,
} from 'lucide-react';

import PulseFitnessMark from './PulseFitnessMark';

// Iter 220bc — Single source of truth lives in MarketingHome.MODULES,
// but the orbit needs a slightly different shape (per-feature icons +
// labels only, no body copy). Mirroring the structure here keeps the
// orbit self-contained for any consumer of this component.
const ORBIT_MODULES = (t) => [
  {
    id: 'service',
    icon: Wrench,
    color: 'var(--gx-accent-service)',
    to: '/platform/service',
    label: t('mkt.mod_service', 'Operations'),
    features: [
      { icon: AlertTriangle, label: t('mkt.f_fault', 'Fault Logging') },
      { icon: ListChecks,    label: t('mkt.f_checks', 'Check Sheets') },
      { icon: Wallet,        label: t('mkt.f_capex', 'CAPEX') },
      { icon: UserCog,       label: t('mkt.f_staffing', 'Staffing') },
      { icon: LineChart,     label: t('mkt.f_reporting', 'Reporting') },
    ],
  },
  {
    id: 'crm',
    icon: Users,
    color: 'var(--gx-accent-crm)',
    to: '/platform/crm',
    label: t('mkt.mod_crm', 'CRM'),
    features: [
      { icon: Building2,  label: t('mkt.f_companies', 'Companies') },
      { icon: GitBranch,  label: t('mkt.f_pipeline', 'Pipeline') },
      { icon: LineChart,  label: t('mkt.f_forecast', 'Forecast') },
      { icon: Users,      label: t('mkt.f_contacts', 'Contacts') },
    ],
  },
  {
    id: 'memberships',
    icon: Calendar,
    color: 'var(--gx-accent-memberships)',
    to: '/platform/memberships',
    label: t('mkt.mod_memberships', 'Memberships'),
    features: [
      { icon: CalendarClock, label: t('mkt.f_timetable', 'Timetable') },
      { icon: Receipt,       label: t('mkt.f_invoicing', 'Invoicing') },
      { icon: Smartphone,    label: t('mkt.f_customapp', 'Custom App') },
      { icon: BookOpen,      label: t('mkt.f_bookings', 'Bookings') },
    ],
  },
  {
    id: 'marketing',
    icon: Megaphone,
    color: 'var(--gx-accent-marketing)',
    to: '/platform/marketing',
    label: t('mkt.mod_marketing', 'Marketing'),
    features: [
      { icon: MailPlus,  label: t('mkt.f_campaigns', 'Campaigns') },
      { icon: ImageIcon, label: t('mkt.f_poster', 'Poster Maker') },
      { icon: Heart,     label: t('mkt.f_jam', 'Member Jam') },
      { icon: Megaphone, label: t('mkt.f_social', 'Social') },
    ],
  },
  // Iter 220bd — Engineers as 5th orbital node. The partner-engineer
  // network gets equal billing alongside the four core SaaS modules.
  {
    id: 'engineers',
    icon: HardHat,
    color: 'var(--gx-accent-engineers)',
    to: '/partners/engineers',
    label: t('mkt.mod_engineers', 'Engineers'),
    features: [
      { icon: MapPin,        label: t('mkt.f_routing', 'Job Routing') },
      { icon: Smartphone,    label: t('mkt.f_mobile', 'Mobile App') },
      { icon: Camera,        label: t('mkt.f_phototriage', 'AI Photo Triage') },
      { icon: PoundSterling, label: t('mkt.f_earnings', 'Earnings') },
    ],
  },
];

export default function AxisOrbit() {
  const { t } = useTranslation();
  const orbitModules = ORBIT_MODULES(t);
  // Track which node is hovered so we can dim the others. Pure UI state.
  const [activeId, setActiveId] = useState(null);

  return (
    <div className="relative w-full max-w-[640px] aspect-square mx-auto" data-testid="gx-axis-orbit">
      {/* Decorative concentric rings */}
      <div className="absolute inset-[8%] rounded-full border border-slate-200/70" />
      <div className="absolute inset-[20%] rounded-full border border-slate-200/50" />
      <div className="absolute inset-[34%] rounded-full border border-slate-200/30" />

      {/* Rotating ring with the 4 module nodes */}
      <div className="absolute inset-0 gx-orbit-ring">
        {orbitModules.map((m, i) => {
          // Iter 220bc — Place 4 nodes at the cardinal compass points
          // (top, right, bottom, left). Start at -π/2 so the first
          // node sits at 12 o'clock — natural reading entry point.
          const angle = -Math.PI / 2 + (i / orbitModules.length) * 2 * Math.PI;
          // Push nodes onto the outer concentric ring (~46% from center)
          const x = 50 + 46 * Math.cos(angle);
          const y = 50 + 46 * Math.sin(angle);
          const isActive = activeId === m.id;
          const dimmed = activeId !== null && !isActive;
          return (
            <div
              key={m.id}
              className="absolute -translate-x-1/2 -translate-y-1/2"
              style={{ left: `${x}%`, top: `${y}%`, zIndex: isActive ? 20 : 10 }}
              onMouseEnter={() => setActiveId(m.id)}
              onMouseLeave={() => setActiveId(null)}
              onFocus={() => setActiveId(m.id)}
              onBlur={() => setActiveId(null)}
            >
              {/* Counter-spin so label stays upright */}
              <div className="gx-orbit-counter">
                <ModuleNode
                  to={m.to}
                  icon={m.icon}
                  color={m.color}
                  label={m.label}
                  isActive={isActive}
                  dimmed={dimmed}
                  testId={`gx-orbit-${m.id}`}
                />
                {isActive && (
                  <FeatureConstellation features={m.features} color={m.color} />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Center node — the AXIS itself, branded with the GA monogram */}
      <div className="absolute inset-1/2 -translate-x-1/2 -translate-y-1/2 w-[30%] aspect-square">
        <div className="relative w-full h-full">
          <div
            className="absolute inset-0 rounded-full opacity-40 blur-2xl"
            style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}
          />
          <div
            className="relative w-full h-full rounded-full bg-white flex items-center justify-center gx-glow dark:bg-zinc-900"
            style={{ boxShadow: '0 18px 50px -12px rgba(25, 205, 255, .35), 0 0 0 1px rgba(15, 23, 42, .04)' }}
            data-testid="gx-orbit-center"
          >
            <PulseFitnessMark className="w-[68%] h-[68%]" />
          </div>
        </div>
      </div>
    </div>
  );
}

function ModuleNode({ to, icon: Icon, color, label, isActive, dimmed, testId }) {
  return (
    <Link
      to={to}
      className="group flex flex-col items-center gx-orbit-node-link"
      data-testid={testId}
      aria-label={label}
      style={{ opacity: dimmed ? 0.35 : 1, transition: 'opacity .25s ease' }}
    >
      <div
        className={`gx-orbit-node w-20 h-20 sm:w-24 sm:h-24 rounded-3xl bg-white border border-slate-200 flex items-center justify-center transition-all duration-300 dark:bg-zinc-900 dark:border-zinc-800 ${isActive ? 'gx-orbit-node-active' : ''}`}
        style={{
          boxShadow: isActive
            ? `0 18px 40px -10px ${color}, 0 0 0 1px rgba(15, 23, 42, .04)`
            : `0 6px 24px -6px ${color}55, 0 0 0 1px rgba(15, 23, 42, .04)`,
          ['--gx-node-accent']: color,
          transform: isActive ? 'translateY(-4px) scale(1.05)' : 'translateY(0)',
        }}
      >
        <Icon
          size={30}
          strokeWidth={1.6}
          style={{ color }}
          className="transition-transform duration-300 group-hover:scale-110"
        />
      </div>
      <p className="mt-2 text-xs sm:text-sm font-bold text-slate-700 text-center whitespace-nowrap">{label}</p>
    </Link>
  );
}

/**
 * FeatureConstellation — fans the module's sub-features out in an arc
 * around the parent node, with a staggered reveal so each pill pops in
 * sequence (60ms apart). Pure CSS — no JS animation loop.
 *
 * Geometry: features sit on a 88px radius from the node centre, on an
 * arc that opens outward from the orbit centre (rotated to face away
 * from the GA logo). That keeps them away from the rotating ring and
 * the center monogram.
 */
function FeatureConstellation({ features, color }) {
  // Iter 220bc.1 — Wider arc + bigger radius so the pills fan out into
  // the empty diagonals between adjacent module cards (per the user's
  // sketch — pills should bleed into the gaps between Operations ↔
  // Marketing and Operations ↔ CRM, not just hug the node).
  const radius = 132; // px from node centre (was 92)
  // Arc widens to 240° — pills wrap around like a halo, leaving the
  // 120° "outward" sliver clear so the node icon stays readable.
  const total = features.length;
  const arc = (Math.PI / 180) * 240;
  const startAngle = -Math.PI / 2 - arc / 2;
  return (
    <div
      className="absolute left-1/2 top-1/2 pointer-events-none"
      style={{ width: 0, height: 0, zIndex: 30 }}
      data-testid="gx-orbit-features"
    >
      {features.map((f, i) => {
        const step = total === 1 ? 0 : i / (total - 1);
        const angle = startAngle + step * arc;
        const x = radius * Math.cos(angle);
        const y = radius * Math.sin(angle);
        const FIcon = f.icon;
        return (
          <div
            key={f.label}
            className="absolute gx-orbit-feature-pop pointer-events-auto"
            style={{
              left: `${x}px`,
              top: `${y}px`,
              transform: 'translate(-50%, -50%)',
              animationDelay: `${i * 60}ms`,
            }}
            data-testid={`gx-orbit-feature-${f.label.toLowerCase().replace(/\s+/g, '-')}`}
          >
            <div
              className="rounded-full bg-white shadow-lg border px-2.5 py-1.5 inline-flex items-center gap-1.5 whitespace-nowrap dark:bg-zinc-900 dark:border-zinc-800"
              style={{
                borderColor: color,
                boxShadow: `0 8px 24px -6px ${color}66`,
              }}
            >
              <FIcon size={12} style={{ color }} />
              <span className="text-[11px] font-bold text-slate-800 dark:text-zinc-100">{f.label}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
