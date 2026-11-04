/**
 * engineerGuard (iter 274)
 *
 * Independent partner engineers now have their own personal org, which gives
 * them an org context for the Engineer App — but they must NOT be able to
 * reach gym-operator modules (Operations/Pulse/CRM/Memberships/Marketing).
 * Their home is the Engineer App (/partner-engineer + /svc/engineer).
 *
 * Master/pulse admins are explicitly excluded so a misc `is_partner_engineer`
 * flag can never lock an admin out of their console.
 */
export const isIndependentEngineer = (u) =>
  !!u
  && !u.is_master_admin
  && !u.is_pulse_admin
  && (
    u.is_partner_engineer === true
    || u.account_type === 'partner_engineer'
    || u.role === 'engineer_partner'
  );

// External Service Provider engineers (MOD estate providers) — Engineer App only.
export const isExternalEngineer = (u) =>
  !!u && !u.is_master_admin && !u.is_pulse_admin && u.is_external_engineer === true;

export const isLockedEngineer = (u) => isIndependentEngineer(u) || isExternalEngineer(u);

export const lockedEngineerHome = (u) => (isExternalEngineer(u) ? '/svc/engineer' : '/partner-engineer');
