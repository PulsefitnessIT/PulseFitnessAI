/**
 * moduleHome.js (Iter 220ea·42)
 *
 * Resolves which module surface a trial / standard operator should land on,
 * based on the module they signed up to trial. Trials now let prospects
 * pick exactly which modules to use (module selector on signup), and only
 * those are entitled — so a Memberships-only prospect must land on
 * /memberships, never the Operations dashboard.
 *
 * Returns a path string for a bolt-on module home, or `null` when the
 * caller should use its own default (the Operations /dashboard). Master
 * admins, partner engineers and pulse (lite/pro) accounts are handled by
 * the caller BEFORE this helper, so it only needs to disambiguate the
 * "full" trial bucket.
 */
export const MODULE_HOME = {
  memberships: '/memberships',
  crm: '/crm',
  marketing: '/marketing',
  operations: '/dashboard',
};

const BOLT_ONS = ['memberships', 'crm', 'marketing'];

export function moduleHomePath(user) {
  if (!user) return null;
  const pm = (user.primary_module || '').toLowerCase();
  // Explicit landing module declared at signup wins (unless it's
  // operations, which is the default /dashboard anyway).
  if (BOLT_ONS.includes(pm)) return MODULE_HOME[pm];

  // No explicit bolt-on primary — but if exactly ONE module is enabled and
  // it's a bolt-on, the operator clearly came for that one. Land there.
  const access = user.module_access || {};
  const enabled = ['operations', ...BOLT_ONS].filter((k) => access[k]);
  if (enabled.length === 1 && BOLT_ONS.includes(enabled[0])) {
    return MODULE_HOME[enabled[0]];
  }
  return null;
}
