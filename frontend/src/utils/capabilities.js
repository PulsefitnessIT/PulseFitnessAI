/**
 * capabilities.js — Iter 243.
 *
 * SINGLE source of truth for "who can do what" in the UI.
 *
 * Why: three production bugs (iter 237 site switcher, iter 241 blank
 * Reports/Suppliers/Gym Layout tabs, iter 243 fault-template manager)
 * shared one root cause — features hand-listed roles ("owner || manager")
 * and forgot pulse_master_admin. New features must check a NAMED
 * capability here instead of re-deriving role lists inline.
 *
 * Usage:
 *   import { can } from '@/utils/capabilities';
 *   if (can(user, 'manage_operations')) { ... }
 *   // pages with a demo-role override (e.g. ?role= on /pulse):
 *   can(user, 'manage_operations', { role: userRole })
 */

export const isPulseAdmin = (user) =>
  !!(user?.is_pulse_admin || user?.role === 'pulse_master_admin');

/** Owners, managers, Pulse Fitness master admins and Pulse master admins. */
const managerial = (user, role) =>
  role === 'owner' || role === 'manager' || !!user?.is_master_admin || isPulseAdmin(user);

/**
 * The generic SHARED site login (MOD site-code login, or role "site_staff").
 * It is used by many people so it must NOT expose figures/credentials.
 */
const isRestrictedShared = (user, role) =>
  !!user?.is_shared_site_login || role === 'site_staff';

/** Visible to everyone EXCEPT the restricted shared site login. */
const notShared = (user, role) => !isRestrictedShared(user, role);

const RULES = {
  // Operations module: full tab set (Reports / Suppliers / Gym Layout /
  // Staffing), site switcher, dismissable nudges.
  manage_operations: managerial,
  switch_sites: managerial,
  dismiss_nudges: managerial,
  // Pulse Fitness ops dashboard surfaces.
  view_suppliers: managerial,
  view_capex: managerial,
  // Settings → fault templates (org-scoped create/delete/promote).
  manage_fault_templates: managerial,
  // Reports/figures + Staffing (credentials) — hidden from the shared site login
  // so posted-in personnel using the generic login can't see the owner's data.
  view_reports: notShared,
  view_staffing: notShared,
  // Only a site owner (or master admin) may hand the owner role to someone else.
  transfer_ownership: (user, role) => role === 'owner' || !!user?.is_master_admin,
  // Service Desk hub (/service-desk): flagged desk agents, Pulse Fitness master
  // admins and Pulse master admins (Pulse runs the service operation).
  view_service_desk: (user) =>
    !!(user?.is_service_desk || user?.is_master_admin) || isPulseAdmin(user),
  // Inventory & Distribution module (/inventory): its own additive capability,
  // but Service Desk agents keep access so nobody working today is locked out.
  view_inventory: (user) =>
    !!(user?.is_inventory || user?.is_service_desk || user?.is_master_admin) || isPulseAdmin(user),
};

/**
 * @param {object} user      auth user
 * @param {string} capability  a key of RULES
 * @param {object} [opts]    { role } — effective-role override for pages
 *                           that support admin demo roles.
 */
export const can = (user, capability, { role } = {}) => {
  const rule = RULES[capability];
  if (!rule) {
    // Unknown capability = programming error; fail closed but loudly.
    console.warn(`[capabilities] unknown capability: ${capability}`);
    return false;
  }
  return !!rule(user, role || user?.role || 'staff');
};

/** Every declared capability key — consumed by the Access Matrix page. */
export const listCapabilities = () => Object.keys(RULES);

/** Human labels for the Access Matrix grid (Iter 246). */
export const CAPABILITY_LABELS = {
  manage_operations: 'Operations module — full tab set',
  switch_sites: 'Switch between sites',
  dismiss_nudges: 'Dismiss dashboard nudges',
  view_suppliers: 'View suppliers',
  view_capex: 'View CAPEX planner',
  manage_fault_templates: 'Manage fault templates',
  view_reports: 'View Reports / figures',
  view_staffing: 'Open the Staffing tab',
  transfer_ownership: 'Transfer site ownership',
  view_service_desk: 'Open the Service Desk hub',
  view_inventory: 'Open the Inventory & Distribution module',
};
