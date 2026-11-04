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

/**
 * First granted bolt-on module path for a user (CRM → Memberships → Marketing),
 * or null. Used as a safe landing for a non-operator staffer who has no
 * Operations access — send them straight into a module they DO have rather
 * than the Operations dashboard or the (Pulse-Fitness-only) area selector.
 */
export function firstGrantedModulePath(user) {
  const ma = (user && (user.module_access || user.moduleAccess)) || {};
  const key = BOLT_ONS.find((k) => ma[k]);
  return key ? MODULE_HOME[key] : null;
}

/**
 * Single source of truth for a user's post-login home path — used by
 * LoginPage.routeAfterLogin, LoginRedirectPage, and the /dashboard + /crm
 * access guards. Keeping them in lock-step stops a user being bounced to the
 * wrong home when any of these re-render during the login handshake.
 *
 * Only OPERATOR-COMPANY staff (Pulse Fitness Ltd — `org_is_operator`) get the
 * area selector (/launch), so they can hop between the Staff Portal and any
 * modules they're granted. Every OTHER company lands directly on its normal
 * home (Operations dashboard, or its first granted module if Operations isn't
 * granted) exactly as before — they have no Staff Portal and no selector.
 * The module-access security guards apply to everyone regardless.
 */
export function resolveHomePath(user) {
  const u = user || {};
  if (u.must_change_password) return '/change-password';
  // External Service Provider engineers only ever use the Engineer App.
  if (u.is_external_engineer && !u.is_master_admin && !u.is_pulse_admin) return '/svc/engineer';
  // MOD / BFPO Engineer Portal — engineers, leads and MOD service staff sign
  // in through the standard MOD service login and land directly in /bfpo.
  if (['engineer', 'lead', 'staff'].includes(u.bfpo_role)) return '/bfpo';
  if (u.role === 'dealer_user') return '/dealer-portal';
  if (u.role === 'logistics') return '/logistics';
  if (u.is_master_admin || u.is_pulse_admin) return '/master-admin';
  if (u.is_partner_engineer || u.account_type === 'partner_engineer' || u.role === 'engineer_partner') return '/partner-engineer';
  // Pulse Fitness Ltd (the platform operator company) staff → area selector.
  if (u.is_operator_company === true) return '/launch';
  // Any staff member (has a Staff Portal) signs in through the main login and
  // is sent to the area chooser, where they pick their Staff Portal or any
  // module they can access. If the portal is their only area, LauncherPage
  // forwards them straight there.
  if (u.has_staff_portal === true) return '/launch';
  if (u.is_service_desk) return u.service_ops_setup_complete === false ? '/service-desk/setup' : '/service-desk';
  if (['lite', 'pulse_pro', 'mod_site', 'mod_branch', 'mod_org'].includes(u.account_type)) return '/pulse';
  // Other companies: no Operations access → first granted module; otherwise
  // the Operations dashboard (their historical home). `/launch` is only a
  // last resort for a zero-access account (LauncherPage shows a no-access
  // card) and never surfaces the selector for a non-operator company.
  const ma = u.module_access || {};
  if (ma.operations === false) return moduleHomePath(u) || firstGrantedModulePath(u) || '/launch';
  return moduleHomePath(u) || '/dashboard';
}

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
