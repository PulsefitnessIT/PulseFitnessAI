/**
 * GymAxis AXIS orbit hero — central animated visual.
 *
 * 6 module nodes orbit a glowing center (the GA monogram) at constant
 * angular velocity. Pause-on-hover gives users time to read/click;
 * counter-rotation on the inner content keeps icons + labels upright.
 * Pure CSS animation — GPU-friendly, no JS RAF loop.
 */
import { Link } from 'react-router-dom';
import {
  Wrench, Users, Calendar, Megaphone, UserCog, BarChart3,
} from 'lucide-react';

import GymAxisMark from './GymAxisMark';

const ORBIT_MODULES = [
  { id: 'service',     icon: Wrench,    color: 'var(--gx-accent-service)',     to: '/platform/service',     label: 'Operations' },
  { id: 'crm',         icon: Users,     color: 'var(--gx-accent-crm)',         to: '/platform/crm',         label: 'CRM' },
  { id: 'memberships', icon: Calendar,  color: 'var(--gx-accent-memberships)', to: '/platform/memberships', label: 'Memberships' },
  { id: 'marketing',   icon: Megaphone, color: 'var(--gx-accent-marketing)',   to: '/platform/marketing',   label: 'Marketing' },
  { id: 'staffing',    icon: UserCog,   color: 'var(--gx-accent-staffing)',    to: '/platform/staffing',    label: 'Staffing' },
  { id: 'reporting',   icon: BarChart3, color: 'var(--gx-accent-reporting)',   to: '/platform/reporting',   label: 'Reporting' },
];

export default function AxisOrbit() {
  return (
    <div className="relative w-full max-w-[640px] aspect-square mx-auto" data-testid="gx-axis-orbit">
      {/* Decorative concentric rings */}
      <div className="absolute inset-[8%] rounded-full border border-slate-200/70" />
      <div className="absolute inset-[20%] rounded-full border border-slate-200/50" />
      <div className="absolute inset-[34%] rounded-full border border-slate-200/30" />

      {/* Rotating ring with the 6 module nodes */}
      <div className="absolute inset-0 gx-orbit-ring">
        {ORBIT_MODULES.map((m, i) => {
          const angle = (i / ORBIT_MODULES.length) * 2 * Math.PI;
          // Push nodes onto the outer concentric ring (~46% from center)
          const x = 50 + 46 * Math.cos(angle);
          const y = 50 + 46 * Math.sin(angle);
          return (
            <Link
              key={m.id}
              to={m.to}
              className="absolute -translate-x-1/2 -translate-y-1/2 group"
              style={{ left: `${x}%`, top: `${y}%` }}
              data-testid={`gx-orbit-${m.id}`}
              aria-label={m.label}
            >
              {/* Counter-spin to keep label upright */}
              <div className="gx-orbit-counter flex flex-col items-center">
                <ModuleNode icon={m.icon} color={m.color} label={m.label} />
              </div>
            </Link>
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
            className="relative w-full h-full rounded-full bg-white flex items-center justify-center gx-glow"
            style={{ boxShadow: '0 18px 50px -12px rgba(37, 99, 235, .35), 0 0 0 1px rgba(15, 23, 42, .04)' }}
            data-testid="gx-orbit-center"
          >
            <GymAxisMark className="w-[68%] h-[68%]" />
          </div>
        </div>
      </div>
    </div>
  );
}

function ModuleNode({ icon: Icon, color, label }) {
  return (
    <div className="relative">
      <div
        className="gx-orbit-node w-20 h-20 sm:w-24 sm:h-24 rounded-3xl bg-white border border-slate-200 flex items-center justify-center transition-all duration-300 group-hover:-translate-y-1"
        style={{
          boxShadow: `0 6px 24px -6px ${color}55, 0 0 0 1px rgba(15, 23, 42, .04)`,
          ['--gx-node-accent']: color,
        }}
      >
        <Icon size={30} strokeWidth={1.6} style={{ color }} className="transition-transform duration-300 group-hover:scale-110" />
      </div>
      <p className="mt-2 text-xs sm:text-sm font-bold text-slate-700 text-center whitespace-nowrap">{label}</p>
    </div>
  );
}
