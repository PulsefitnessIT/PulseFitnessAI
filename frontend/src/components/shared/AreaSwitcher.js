import React from 'react';
import { useLocation } from 'react-router-dom';
import { LayoutGrid, ChevronDown, Headphones, HardHat, Activity, Check, Boxes, CalendarClock, ShieldCheck } from 'lucide-react';

/**
 * Iter 283 — "Switch area" button.
 *
 * The pill ModuleSwitcher stays reserved for the four consistently-designed
 * modules (Operations / Memberships / CRM / Marketing). The Service Desk and
 * Engineer app have their own distinct shells, so a separate compact
 * "Switch area" dropdown (placed next to Account settings) lets users who can
 * access those surfaces hop between them without breaking the pill bar's
 * visual consistency.
 *
 * Renders only when the user can reach 2+ areas.
 */
function accessibleAreas(user) {
  if (!user) return [];
  const isMaster = user.is_master_admin === true || user.is_pulse_admin === true
    || user.role === 'master_admin' || user.role === 'master';
  const at = user.account_type;
  const mainPath = (at === 'pulse_pro' || at === 'lite') ? '/pulse' : '/dashboard';

  const areas = [];

  // Main app — only for users who actually have operator/module access, so a
  // pure field engineer doesn't get a dead "Main app" link.
  const ma = user.moduleAccess || user.module_access || {};
  const hasAnyModule = ['operations', 'memberships', 'marketing', 'crm'].some((k) => ma && ma[k]);
  const operatorTypes = ['full', 'pulse_pro', 'lite', 'mod_site', 'mod_branch', 'mod_org'];
  const canMain = isMaster || operatorTypes.includes(at) || hasAnyModule || user.role === 'owner';
  if (canMain) areas.push({ id: 'main', label: 'Main app', path: mainPath, icon: Activity });

  const canServiceDesk = isMaster || user.is_service_desk === true || user.role === 'service_desk';
  if (canServiceDesk) areas.push({ id: 'service-desk', label: 'Service Desk', path: '/service-desk', icon: Headphones });

  // Inventory & Distribution — its own module; reachable by users with the
  // inventory right OR Service Desk access (so existing operators keep it).
  const canInventory = isMaster || user.is_inventory === true || canServiceDesk;
  if (canInventory) areas.push({ id: 'inventory', label: 'Inventory & Distribution', path: '/inventory', icon: Boxes });

  const canEngineer = isMaster || user.role === 'engineer' || user.is_engineer === true || !!user.engineer_id;
  if (canEngineer) areas.push({ id: 'engineer', label: 'Engineer app', path: '/svc/engineer', icon: HardHat });

  // MOD Operations — per-user opt-in module (platform admins always qualify).
  const canModOps = isMaster || (user.module_overrides && user.module_overrides.mod_operations === true);
  if (canModOps) areas.push({ id: 'mod-operations', label: 'MOD Operations', path: '/bfpo', icon: ShieldCheck });

  // Staff Portal — anyone with an employee record in the staffing register
  // (resolved server-side into user.has_staff_portal).
  if (user.has_staff_portal === true) {
    areas.push({ id: 'staff-portal', label: 'Staff Portal', path: '/staff-portal', icon: CalendarClock });
  }

  return areas;
}

function currentAreaId(pathname) {
  const p = pathname || '';
  if (p.startsWith('/inventory') || p.startsWith('/service-desk/inventory')) return 'inventory';
  if (p.startsWith('/service-desk')) return 'service-desk';
  if (p.startsWith('/svc/engineer') || p.startsWith('/engineer')) return 'engineer';
  if (p.startsWith('/bfpo')) return 'mod-operations';
  if (p.startsWith('/staff-portal')) return 'staff-portal';
  return 'main';
}

export default function AreaSwitcher({ user, tone = 'header', className = '' }) {
  const location = useLocation();
  const [open, setOpen] = React.useState(false);

  const areas = accessibleAreas(user);
  if (areas.length < 2) return null;

  const active = currentAreaId(location.pathname);
  const dark = tone === 'header';
  const icon = tone === 'icon';
  const openUp = tone === 'sidebar';

  const go = (area) => {
    setOpen(false);
    if (area.id === active) return;
    // Service Desk / Engineer live in separate shells — full navigation is
    // the most reliable way to switch between them.
    window.location.href = area.path;
  };

  let btnClass, btnStyle;
  if (icon) {
    btnClass = 'relative p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50 text-slate-700';
    btnStyle = {};
  } else if (dark) {
    btnClass = 'flex items-center gap-2 px-3 py-2 rounded-lg border hover:opacity-80 transition-colors';
    btnStyle = { borderColor: 'var(--theme-border)', color: 'var(--theme-text)' };
  } else {
    btnClass = 'flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 transition-colors w-full';
    btnStyle = {};
  }

  const menuPos = openUp ? 'left-0 bottom-full mb-2' : 'right-0 top-full mt-2';

  return (
    <div className={`relative ${className}`}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={btnClass}
        style={btnStyle}
        data-testid="area-switcher-btn"
        aria-haspopup="true"
        aria-expanded={open}
        title={icon ? 'Switch area' : undefined}
        aria-label={icon ? 'Switch area' : undefined}
      >
        <LayoutGrid size={icon ? 16 : 15} />
        {!icon && <span className="text-sm font-medium">Switch area</span>}
        {!icon && <ChevronDown size={14} className={`ml-auto transition-transform ${open ? 'rotate-180' : ''}`} />}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className={`absolute ${menuPos} w-52 rounded-lg shadow-xl z-50 overflow-hidden`}
            style={dark
              ? { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }
              : { background: '#fff', border: '1px solid #e2e8f0' }}
            data-testid="area-switcher-menu"
          >
            <p className={`px-4 pt-3 pb-1 text-[10px] uppercase tracking-[0.16em] font-semibold ${dark ? '' : 'text-slate-400'}`}
               style={dark ? { color: 'var(--theme-text-muted)' } : {}}>Switch area</p>
            <div className="py-1">
              {areas.map((a) => {
                const Icon = a.icon;
                const on = a.id === active;
                return (
                  <button
                    key={a.id}
                    onClick={() => go(a)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${dark ? 'hover:opacity-80' : 'hover:bg-slate-50'} ${on ? 'font-semibold' : ''}`}
                    style={dark ? { color: 'var(--theme-text)' } : { color: on ? '#0f172a' : '#475569' }}
                    data-testid={`area-switcher-${a.id}`}
                  >
                    <Icon size={16} /> {a.label}
                    {on && <Check size={14} className="ml-auto text-emerald-500" />}
                  </button>
                );
              })}
            </div>
            {user.is_operator_company === true && (
              <div className="py-1 border-t" style={dark ? { borderColor: 'var(--theme-border)' } : { borderColor: '#e2e8f0' }}>
                <button
                  onClick={() => { setOpen(false); window.location.href = '/launch?choose=1'; }}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${dark ? 'hover:opacity-80' : 'hover:bg-slate-50'}`}
                  style={dark ? { color: 'var(--theme-text-muted)' } : { color: '#475569' }}
                  data-testid="area-switcher-chooser"
                >
                  <LayoutGrid size={16} /> Area Selector…
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
