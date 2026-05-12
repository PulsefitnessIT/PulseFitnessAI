/**
 * ServiceOpsShell — shared Service Operations layout (iter 215dw).
 *
 * Renders the premium gradient hero + module nav strip used on every
 * Service Ops page. Pages plug their own body content as children.
 *
 * Props:
 *  - eyebrow:  top-line label (default "Service Operations")
 *  - icon:     lucide icon component, rendered next to title
 *  - title:    page title (large)
 *  - subtitle: short description
 *  - actions:  ReactNode rendered to the top-right of the hero
 *  - active:   one of "desk" | "scheduler" | "parts" | "billing" |
 *              "reports" | "comms" — drives the active nav pill
 *  - lowStockCount: number on the Parts pill (optional)
 *  - children: page body
 *  - testId:   wrapper data-testid (default "svc-shell")
 *
 * Light & dark mode handled entirely via theme tokens — no hardcoded
 * colours. See _serviceops.css for the full design layer.
 */
import React, { createContext, useContext } from 'react';
import { Link } from 'react-router-dom';
import {
  ClipboardList, Calendar, Package, FileText, BarChart3, Mail,
  Smartphone, Plus, HardHat,
} from 'lucide-react';
import './_serviceops.css';

// Iter 216h53 — when the shell renders inside the merged Service Desk
// page, the outer hero + nav strip is suppressed (the merged page
// already has its own sidebar + tab bar). Consumers wrap with
// <ServiceOpsEmbeddedContext.Provider value={true}> to flip the flag.
export const ServiceOpsEmbeddedContext = createContext(false);

const NAV = [
  { id: 'desk',      to: '/service-ops',           label: 'Desk',      Icon: ClipboardList },
  { id: 'scheduler', to: '/service-ops/scheduler', label: 'Scheduler', Icon: Calendar },
  { id: 'engineers', to: '/service-ops/engineers', label: 'Engineers', Icon: HardHat },
  { id: 'parts',     to: '/service-ops/parts',     label: 'Parts',     Icon: Package, badge: 'lowStockCount' },
  { id: 'billing',   to: '/service-ops/billing',   label: 'Billing',   Icon: FileText },
  { id: 'reports',   to: '/service-ops/reports',   label: 'Reports',   Icon: BarChart3 },
  { id: 'comms',     to: '/service-ops/comms',     label: 'Comms',     Icon: Mail },
];

export default function ServiceOpsShell({
  eyebrow = 'Service Operations',
  icon: Icon,
  title,
  subtitle,
  actions,
  active,
  lowStockCount = 0,
  children,
  testId = 'svc-shell',
  pageTestId,
  narrow = false,
}) {
  const embedded = useContext(ServiceOpsEmbeddedContext);
  // When embedded, render the page body only — the merged Service Desk
  // page provides its own header + nav. Still wrap in a minimal div so
  // .svc-* CSS rules continue to scope correctly.
  if (embedded) {
    return (
      <div className={`svc-shell svc-shell--embedded ${narrow ? 'svc-page-narrow' : ''}`} data-testid={testId}>
        <div className="svc-page svc-page--embedded" data-testid={pageTestId}>
          {actions ? (
            <div className="flex flex-wrap items-center gap-2 justify-end mb-4" data-testid="svc-hero-actions">
              {actions}
            </div>
          ) : null}
          <div className="space-y-5" data-testid="svc-body">{children}</div>
        </div>
      </div>
    );
  }
  return (
    <div className={`svc-shell ${narrow ? 'svc-page-narrow' : ''}`} data-testid={testId}>
      <div className="svc-page" data-testid={pageTestId}>
        {/* ─── Hero ─── */}
        <header className="svc-hero" data-testid="svc-hero">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0">
              <p className="svc-eyebrow">{eyebrow}</p>
              <h1 className="svc-h1">
                {Icon ? <Icon size={22} strokeWidth={2.4} /> : null}
                {title}
              </h1>
              {subtitle ? <p className="svc-subtitle">{subtitle}</p> : null}
            </div>
            {actions ? (
              <div className="flex flex-wrap items-center gap-2 shrink-0" data-testid="svc-hero-actions">
                {actions}
              </div>
            ) : null}
          </div>
        </header>

        {/* ─── Nav strip ─── */}
        <nav className="svc-nav mt-4" aria-label="Service Operations" data-testid="svc-nav">
          {NAV.map(({ id, to, label, Icon: I, badge }) => {
            const isActive = active === id;
            const showBadge = badge === 'lowStockCount' && lowStockCount > 0;
            return (
              <Link
                key={id}
                to={to}
                className={`svc-nav-pill ${isActive ? 'svc-nav-pill--active' : ''}`}
                data-testid={`svc-nav-${id}`}
                aria-current={isActive ? 'page' : undefined}
              >
                <I size={13} />
                {label}
                {showBadge ? (
                  <span className="svc-nav-badge" data-testid="svc-nav-low-stock-badge">
                    {lowStockCount > 99 ? '99+' : lowStockCount}
                  </span>
                ) : null}
              </Link>
            );
          })}
          <Link
            to="/svc/engineer"
            className="svc-nav-pill"
            data-testid="svc-nav-engineer"
            title="Engineer mobile view"
          >
            <Smartphone size={13} /> Engineer
          </Link>
        </nav>

        {/* ─── Body ─── */}
        <div className="mt-5 space-y-5" data-testid="svc-body">
          {children}
        </div>
      </div>
    </div>
  );
}

/** Reusable primary CTA matching the design system. */
export function SvcPrimaryButton({ icon: Icon, children, ...rest }) {
  return (
    <button type="button" className="svc-btn svc-btn-primary" {...rest}>
      {Icon ? <Icon size={13} /> : <Plus size={13} />}
      {children}
    </button>
  );
}

/** Reusable secondary button. */
export function SvcSecondaryButton({ icon: Icon, children, ...rest }) {
  return (
    <button type="button" className="svc-btn svc-btn-secondary" {...rest}>
      {Icon ? <Icon size={13} /> : null}
      {children}
    </button>
  );
}
