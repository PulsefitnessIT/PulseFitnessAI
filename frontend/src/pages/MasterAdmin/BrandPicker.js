/**
 * Iter 216h17 — Brand context picker pill, lives in the Master Admin
 * top bar. Replaces the ad-hoc `gymaxisOnly` flag scattering across
 * sidebar/panel files.
 *
 * Iter 216h22 — `isPulseAdmin` prop. When the signed-in operator is a
 * delegated Pulse Master Admin (`is_pulse_admin && !is_master_admin`)
 * the picker is FORCED to "Pulse" on mount and rendered as a
 * non-clickable scope pill so Pulse admins can never accidentally
 * peek at GymAxis-only customers. GymAxis Master Admins keep the
 * full toggle.
 */
import React from 'react';
import { ChevronDown, Globe2, Shield } from 'lucide-react';
import { useBrandContext, BRAND_OPTIONS } from './BrandContext';

export const BrandPicker = ({ compact = false, isPulseAdmin = false }) => {
  const { brand, setBrand, brandShort, brandAccent } = useBrandContext();
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);

  // Force the brand to Pulse for Pulse-only admins on first mount and
  // any time they somehow ended up on a different brand (e.g. stale
  // localStorage from a previous GymAxis-master session in the same
  // browser). Idempotent.
  React.useEffect(() => {
    if (isPulseAdmin && brand !== 'pulse') setBrand('pulse');
  }, [isPulseAdmin, brand, setBrand]);

  React.useEffect(() => {
    if (!open) return undefined;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Pulse-only admins see a locked scope pill — no dropdown, no other
  // brand options visible. Hover tooltip explains why.
  if (isPulseAdmin) {
    return (
      <div
        className="inline-flex items-center gap-2 rounded-full border bg-white px-3 py-1.5 text-sm font-medium shadow-sm"
        style={{ borderColor: '#BFDBFE', color: '#1D4ED8', background: '#EFF6FF' }}
        title="Pulse Master Admin scope — your account only sees Pulse Fitness data."
        data-testid="master-admin-brand-picker-locked"
      >
        <Shield size={13} />
        <span className="font-semibold tracking-tight">Pulse Fitness</span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-blue-500">Scope locked</span>
      </div>
    );
  }

  return (
    <div ref={ref} className="relative inline-block" data-testid="master-admin-brand-picker">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="inline-flex items-center gap-2 rounded-full border bg-white px-3 py-1.5 text-sm font-medium shadow-sm hover:bg-zinc-50 transition-colors"
        style={{ borderColor: '#E4E4E7', color: '#0A0A0A' }}
        data-testid="master-admin-brand-picker-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="inline-block w-2 h-2 rounded-full" style={{ background: brandAccent }} aria-hidden />
        {!compact && <Globe2 size={14} className="text-zinc-500" aria-hidden />}
        <span className="font-semibold tracking-tight">{brandShort}</span>
        <ChevronDown size={14} className="text-zinc-400" aria-hidden />
      </button>
      {open && (
        <div
          role="listbox"
          className="absolute right-0 mt-1.5 w-56 rounded-lg border bg-white shadow-lg z-50 overflow-hidden"
          style={{ borderColor: '#E4E4E7' }}
          data-testid="master-admin-brand-picker-menu"
        >
          <div className="px-3 pt-2.5 pb-1 text-[10px] font-bold uppercase tracking-wider text-zinc-500">Brand context</div>
          {BRAND_OPTIONS.map((opt) => {
            const active = opt.id === brand;
            return (
              <button
                key={opt.id}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => { setBrand(opt.id); setOpen(false); }}
                className="w-full text-left px-3 py-2 text-sm flex items-center gap-2.5 hover:bg-zinc-50"
                style={{ background: active ? 'rgba(0,85,255,0.06)' : 'transparent' }}
                data-testid={`master-admin-brand-picker-option-${opt.id}`}
              >
                <span className="inline-block w-2 h-2 rounded-full" style={{ background: opt.accent }} aria-hidden />
                <span className={active ? 'font-semibold text-zinc-900' : 'text-zinc-700'}>{opt.label}</span>
                {active && <span className="ml-auto text-[10px] font-bold uppercase tracking-wider text-[#0055FF]">Active</span>}
              </button>
            );
          })}
          <div className="px-3 pt-2 pb-2.5 text-[10px] leading-snug text-zinc-500 border-t" style={{ borderColor: '#F4F4F5' }}>
            Filters every Master Admin list, dashboard and audit view by brand. Stored locally so it survives reloads.
          </div>
        </div>
      )}
    </div>
  );
};

export default BrandPicker;
