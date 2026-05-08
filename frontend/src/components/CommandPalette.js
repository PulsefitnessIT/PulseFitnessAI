/**
 * Global ⌘K command palette.
 *
 * Toggles on Cmd-K / Ctrl-K from anywhere in the authenticated app. Fuzzy
 * search jumps straight to any Master Admin section, sub-tab, member-portal
 * action, or commonly-needed shortcut. Built on `cmdk` (already installed)
 * so we get keyboard navigation, fuzzy matching and accessibility for free.
 */
import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Command } from 'cmdk';
import {
  Search, ArrowRight, Building2, CreditCard, Users, BarChart3, Receipt,
  ShieldAlert, ShieldCheck, Megaphone, Tag, LifeBuoy, Settings, Wrench,
  Sparkles, FileText, Banknote, Mail, ListChecks, LayoutDashboard,
  Smartphone, Calendar, PoundSterling, Lock, KeyRound, Headphones,
} from 'lucide-react';
import { useAuth } from '@/App';

/* ─────────────────── Command registry ─────────────────── */

/**
 * Each command is a fuzzy-searchable jump target.
 *  - `value`: hidden alias string crammed with synonyms so e.g. "money"
 *    finds "Pricing" + "Org Billing" + "Payments" without the user having
 *    to know our internal vocab.
 */
const buildCommands = ({ navigate, user, setSection }) => {
  const isAdmin = !!(user?.is_master_admin || user?.is_pulse_admin);
  const cmds = [];

  // ── Navigation ──
  cmds.push(
    { id: 'nav-dashboard', label: 'Dashboard',   group: 'Navigate', icon: LayoutDashboard,
      value: 'dashboard home main',  run: () => navigate('/dashboard') },
    { id: 'nav-memberships', label: 'Memberships console', group: 'Navigate', icon: Users,
      value: 'memberships members classes bookings plans',
      run: () => navigate('/memberships') },
    { id: 'nav-pricing-public', label: 'Public pricing page', group: 'Navigate', icon: Tag,
      value: 'pricing public homepage modules', run: () => navigate('/pricing') },
    { id: 'nav-trust', label: 'Trust & security', group: 'Navigate', icon: ShieldCheck,
      value: 'trust security uptime gdpr soc2 compliance',
      run: () => navigate('/trust') },
  );

  if (isAdmin) {
    cmds.push(
      { id: 'nav-master-admin', label: 'Master Admin', group: 'Navigate', icon: Settings,
        value: 'master admin platform', run: () => navigate('/master-admin') },
    );
  }

  // ── Master-admin sections (only if user has access) ──
  if (isAdmin) {
    const adminSections = [
      { id: 'overview',       label: 'Overview',        icon: LayoutDashboard, value: 'overview kpi dashboard stats home' },
      { id: 'tasks',          label: 'Setup tasks',     icon: ListChecks,       value: 'tasks setup checklist onboard' },
      { id: 'onboarding',     label: 'Onboarding hub',  icon: Building2,        value: 'onboarding new customer site provision' },
      { id: 'analytics',      label: 'Global analytics',icon: BarChart3,        value: 'analytics platform metrics' },
      { id: 'pricing',        label: 'Pricing',         icon: Tag,              value: 'pricing plans modules bundle prices money' },
      { id: 'org-billing',    label: 'Org billing',     icon: Receipt,          value: 'billing invoices payments bacs ledger money' },
      { id: 'payments',       label: 'Payments',        icon: CreditCard,       value: 'payments revenue subscriptions stripe money' },
      { id: 'stripe-connect', label: 'Stripe Connect',  icon: Banknote,         value: 'stripe connect oauth fee money' },
      { id: 'financial-ops',  label: 'Financial Ops',   icon: PoundSterling,    value: 'financial ops reserves cost centres money' },
      { id: 'capex-config',   label: 'CAPEX config',    icon: BarChart3,        value: 'capex thresholds config money' },
      { id: 'login-events',   label: 'Login events',    icon: ShieldAlert,      value: 'login events security audit brute force' },
      { id: 'trust',          label: 'Trust & Reliability', icon: ShieldCheck,  value: 'trust reliability events security' },
      { id: 'marketing-suite',label: 'Marketing suite', icon: Megaphone,        value: 'marketing campaigns email comms' },
      { id: 'trials',         label: 'Trial management',icon: ListChecks,       value: 'trials free conversion' },
      { id: 'ask-support',    label: 'Ask Support Desk',icon: Sparkles,         value: 'support ai escalation tickets' },
      { id: 'support',        label: 'Support tools',   icon: Headphones,       value: 'support tools customer help' },
      { id: 'emails',         label: 'Email log',       icon: Mail,             value: 'emails outbound audit log' },
      { id: 'orbit4',         label: 'Orbit 4',         icon: Wrench,           value: 'orbit4 integration sync' },
      { id: 'sicon-integration', label: 'Sicon Service',icon: Wrench,           value: 'sicon service integration' },
      { id: 'roles',          label: 'Roles & access',  icon: Users,            value: 'roles access permissions service desk' },
    ];
    for (const s of adminSections) {
      cmds.push({
        id: `admin-${s.id}`, label: s.label, group: 'Master Admin',
        icon: s.icon, value: `${s.label.toLowerCase()} ${s.value}`,
        run: () => {
          // If we're already on /master-admin, switch section without remount;
          // otherwise navigate with a query param the page consumes on mount.
          if (window.location.pathname.startsWith('/master-admin')) {
            setSection?.(s.id);
          } else {
            navigate(`/master-admin?section=${s.id}`);
          }
        },
      });
    }
  }

  // ── Common quick actions ──
  cmds.push(
    { id: 'act-logout', label: 'Log out', group: 'Account', icon: KeyRound,
      value: 'logout sign out exit',
      run: () => { localStorage.removeItem('token'); navigate('/login'); } },
    { id: 'act-mobile-builder', label: 'Mobile App Builder', group: 'Quick action',
      icon: Smartphone, value: 'mobile app builder cards layout',
      run: () => navigate('/memberships?tab=mobile-app') },
    { id: 'act-classes', label: 'Class booking schedule', group: 'Quick action',
      icon: Calendar, value: 'classes timetable bookings schedule',
      run: () => navigate('/memberships?tab=classes') },
    { id: 'act-help', label: 'Help centre', group: 'Help', icon: LifeBuoy,
      value: 'help centre docs guides faq', run: () => navigate('/help') },
  );

  return cmds;
};


/* ─────────────────── Public hook ─────────────────── */
/**
 * `useCommandPalette` returns the [open, setOpen] tuple but ALSO wires the
 * Cmd-K / Ctrl-K listener once at the top of the app. Mount the palette
 * itself via <CommandPalette /> below.
 */
export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e) => {
      if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  return [open, setOpen];
}


/* ─────────────────── Public component ─────────────────── */

export default function CommandPalette({ open, setOpen, setSection }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const commands = useMemo(
    () => buildCommands({ navigate, user, setSection }),
    [navigate, user, setSection],
  );

  const runAndClose = useCallback((cmd) => {
    setOpen(false);
    // Defer to avoid React state thrash during the dismiss animation.
    setTimeout(() => cmd.run(), 30);
  }, [setOpen]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] px-4 bg-black/50 backdrop-blur-sm"
      onClick={() => setOpen(false)}
      data-testid="command-palette-overlay"
    >
      <div
        className="w-full max-w-[640px] rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
        data-testid="command-palette"
      >
        <Command label="Command palette" loop>
          <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-100 dark:border-zinc-800">
            <Search size={16} className="text-zinc-400" />
            <Command.Input
              autoFocus
              placeholder="Type to search — modules, settings, actions…"
              className="flex-1 bg-transparent outline-none text-sm text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400"
              data-testid="command-palette-input"
            />
            <kbd className="hidden sm:inline-block text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-500 border border-zinc-200 dark:border-zinc-700">ESC</kbd>
          </div>
          <Command.List className="max-h-[60vh] overflow-y-auto p-2" data-testid="command-palette-list">
            <Command.Empty className="px-4 py-8 text-center text-sm text-zinc-400">
              No matches. Try a different keyword.
            </Command.Empty>
            {Object.entries(groupBy(commands, (c) => c.group)).map(([group, items]) => (
              <Command.Group key={group} heading={group} className="text-[10px] font-bold uppercase tracking-wider text-zinc-400 px-3 pt-3 pb-1">
                {items.map((cmd) => {
                  const Icon = cmd.icon;
                  return (
                    <Command.Item
                      key={cmd.id}
                      value={`${cmd.label} ${cmd.value || ''}`}
                      onSelect={() => runAndClose(cmd)}
                      className="flex items-center gap-3 px-3 py-2 rounded-md text-sm text-zinc-700 dark:text-zinc-200 cursor-pointer aria-selected:bg-[rgb(var(--rgb-brand-cyan)/0.1)] aria-selected:text-[var(--color-teal-deep)] dark:aria-selected:text-[var(--color-brand-cyan)]"
                      data-testid={`command-palette-item-${cmd.id}`}
                    >
                      <Icon size={14} className="text-zinc-400 group-aria-selected:text-[var(--color-brand-cyan)]" />
                      <span className="flex-1">{cmd.label}</span>
                      <ArrowRight size={12} className="text-zinc-300 dark:text-zinc-600" />
                    </Command.Item>
                  );
                })}
              </Command.Group>
            ))}
          </Command.List>
          <div className="flex items-center justify-between px-4 py-2 border-t border-zinc-100 dark:border-zinc-800 text-[11px] text-zinc-400">
            <div>↑↓ navigate · ↵ run · ESC close</div>
            <div>
              <kbd className="text-[10px] font-mono px-1 rounded bg-zinc-100 dark:bg-zinc-800">⌘K</kbd>
              <span className="ml-1">to toggle</span>
            </div>
          </div>
        </Command>
      </div>
    </div>
  );
}


function groupBy(arr, fn) {
  const out = {};
  for (const x of arr) {
    const k = fn(x);
    (out[k] = out[k] || []).push(x);
  }
  return out;
}
