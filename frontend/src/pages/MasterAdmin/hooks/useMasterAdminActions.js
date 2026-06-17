import { useCallback } from 'react';
import axios from 'axios';

import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
/**
 * All organisation/user/account-type mutations performed from the Master Admin console.
 * Each mutation wraps the axios call, toasts success/failure, and triggers reload callbacks.
 *
 * Iter 234 — every catch block now uses notifyApiError so the toast surfaces
 * the HTTP status + server `detail` instead of a useless "Failed to ...".
 */
const useMasterAdminActions = ({ API, headers, loadData, loadSectionData }) => {
  const updateOrgStatus = useCallback(async (orgId, status) => {
    try {
      await axios.put(`${API}/master-admin/organizations/${orgId}/status`, { status }, { headers });
      notify.success(`Organisation status updated to ${status}`);
      loadData();
    } catch (err) { notifyApiError(notify, err, 'Failed to update status'); }
  }, [API, headers, loadData]);

  const updateOrgTier = useCallback(async (orgId, tier) => {
    try {
      await axios.put(`${API}/master-admin/organizations/${orgId}/subscription`, { tier }, { headers });
      notify.success(`Subscription updated to ${tier}`);
      loadData();
    } catch (err) { notifyApiError(notify, err, 'Failed to update subscription'); }
  }, [API, headers, loadData]);

  const updateOrgFeatures = useCallback(async (orgId, payload, opts = {}) => {
    try {
      // Accept either a flat features map (legacy) or {features:{}} / {modules:{}}.
      const isModulePayload = payload && (payload.modules || payload.features);
      const body = isModulePayload ? payload : { features: payload };
      await axios.put(`${API}/master-admin/organizations/${orgId}/features`, body, { headers });
      if (!opts.silent) {
        notify.success(
          'Features updated — changes take effect on users\' next login or page reload',
          { duration: 7000 },
        );
      }
      loadData();
    } catch (err) { notifyApiError(notify, err, 'Failed to update features'); }
  }, [API, headers, loadData]);

  const toggleTestFlag = useCallback(async (orgId, isTest) => {
    try {
      await axios.put(`${API}/master-admin/organizations/${orgId}/test-flag`, { is_test: isTest }, { headers });
      notify.success(isTest ? 'Marked as test account' : 'Marked as live account');
      loadData();
    } catch (err) { notifyApiError(notify, err, 'Failed to update test flag'); }
  }, [API, headers, loadData]);

  const updateAccountType = useCallback(async (orgId, accountType) => {
    const typeLabel = accountType === 'lite' ? 'Pulse Lite' : accountType === 'pulse_pro' ? 'Pulse Pro' : 'Full';
    try {
      await axios.put(`${API}/master-admin/organizations/${orgId}/account-type`, { account_type: accountType }, { headers });
      notify.success(
        `Account type changed to ${typeLabel} — users will see the new branding on next login`,
        { duration: 7000 },
      );
      await loadSectionData('pulse');
      loadData();
    } catch (err) { notifyApiError(notify, err, 'Failed to update account type'); }
  }, [API, headers, loadData, loadSectionData]);

  const disableUser = useCallback(async (userId, disabled) => {
    try {
      await axios.put(`${API}/master-admin/users/${userId}/disable`, { disabled }, { headers });
      notify.success(disabled ? 'User disabled' : 'User enabled');
      loadData();
    } catch (err) { notifyApiError(notify, err, disabled ? 'Failed to disable user' : 'Failed to enable user'); }
  }, [API, headers, loadData]);

  const archiveUser = useCallback(async (userId, archived) => {
    try {
      await axios.put(`${API}/master-admin/users/${userId}/archive`, { archived }, { headers });
      notify.success(archived ? 'User archived' : 'User unarchived');
      loadData();
    } catch (err) { notifyApiError(notify, err, 'Failed to archive user'); }
  }, [API, headers, loadData]);

  const unlockUser = useCallback(async (userId) => {
    try {
      const res = await axios.post(`${API}/master-admin/users/${userId}/unlock`, {}, { headers });
      notify.success(`Login unlocked${res.data?.email ? ` for ${res.data.email}` : ''}`);
      loadData();
    } catch (err) { notifyApiError(notify, err, 'Failed to unlock login'); }
  }, [API, headers, loadData]);

  const hardDeleteUser = useCallback(async (userId, confirmEmail) => {
    try {
      const res = await axios.delete(`${API}/master-admin/users/${userId}`, {
        headers, data: { confirm_email: confirmEmail },
      });
      const cascade = res.data?.cascade || {};
      const total = Object.values(cascade).reduce((a, b) => a + b, 0);
      notify.success(
        `User permanently deleted${total ? ` — ${total} related records removed` : ''}`,
        { duration: 7000 },
      );
      loadData();
      return true;
    } catch (err) {
      notifyApiError(notify, err, 'Failed to delete user');
      return false;
    }
  }, [API, headers, loadData]);

  const editUser = useCallback(async (userId, updates) => {
    try {
      await axios.put(`${API}/master-admin/users/${userId}/edit`, updates, { headers });
      notify.success('User updated');
      loadData();
    } catch (err) { notifyApiError(notify, err, 'Failed to update user'); }
  }, [API, headers, loadData]);

  const resetPassword = useCallback(async (userId) => {
    try {
      const res = await axios.put(`${API}/master-admin/users/${userId}/reset-password`, {}, { headers });
      const tempPw = res.data?.temp_password;
      if (tempPw && navigator.clipboard) {
        try { await navigator.clipboard.writeText(tempPw); } catch { /* noop */ }
      }
      // Iter 215bi — toast auto-dismisses after 12s (was ttl:0 / persistent
      // which blocked the side drawer when admins clicked it). Temp password
      // is auto-copied to clipboard and also surfaced in the reveal-password
      // panel via the org's primary_contact_initial_password field, so even
      // after the toast goes the admin can grab it again from the drawer.
      notify.success(
        'Password reset · copied to clipboard',
        tempPw ? `Temp password: ${tempPw}` : 'Temporary password issued.',
        { ttl: 12000 },
      );
      loadData();
    } catch (err) { notifyApiError(notify, err, 'Failed to reset password'); }
  }, [API, headers, loadData]);

  const impersonateUser = useCallback(async (userId, setImpersonateDialog) => {
    try {
      const res = await axios.post(`${API}/master-admin/impersonate/${userId}`, {}, { headers });
      setImpersonateDialog(res.data);
    } catch (err) { notifyApiError(notify, err, 'Failed to impersonate user'); }
  }, [API, headers]);

  const createOrganization = useCallback(async (orgForm) => {
    try {
      const res = await axios.post(`${API}/master-admin/organizations`, orgForm, { headers });
      const data = res.data || {};
      // Iter 216h26 — the backend now mints a 72 h invite link for the
      // primary contact alongside the legacy plaintext password.
      // Surface it so the operator can ship the link straight away
      // without the reveal-password handover step.
      if (data.invite_url) {
        notify.success(`Organisation created. Invite link: ${data.invite_url}`);
      } else {
        notify.success('Organisation created');
      }
      loadData();
      return data;
    } catch (err) {
      notifyApiError(notify, err, 'Failed to create organisation');
      throw err;
    }
  }, [API, headers, loadData]);

  const addUserToOrganization = useCallback(async (orgId, userForm) => {
    try {
      const res = await axios.post(`${API}/master-admin/organizations/${orgId}/users`, userForm, { headers });
      try { window.dispatchEvent(new CustomEvent('gymaxis:user-invited')); } catch (_) {}
      // Refresh the list BEFORE we tell the user — guarantees the org
      // panel renders the new user the moment they look for it.
      await loadData();
      notify.success('User added');
      // Iter 215ev — return the response body so the caller can access
      // invite_url when password was omitted (invite-link flow).
      return res.data;
    } catch (err) {
      // If the backend says the user already exists, the most useful
      // thing is to refresh the list (because the previous attempt
      // probably succeeded but the UI lagged) and tell the user.
      if (err?.response?.status === 409) {
        try { await loadData(); } catch (_) { /* refresh best-effort */ }
        notify.error(
          'Already added',
          'This email is already a user. The list has been refreshed — they should now appear under the org.',
        );
        return null;
      }
      notifyApiError(notify, err, 'Failed to add user');
      return null;
    }
  }, [API, headers, loadData]);

  /** Iter 215ev — issue a 72h invite link for an existing user. */
  const issueInviteLink = useCallback(async (userId) => {
    try {
      const res = await axios.post(`${API}/master-admin/users/${userId}/invite-link`, {}, { headers });
      notify.success('Invite link generated');
      return res.data;
    } catch (err) {
      notifyApiError(notify, err, 'Failed to generate invite link');
      return null;
    }
  }, [API, headers]);

  const sendEmailPreview = useCallback(async (orgId, toEmail, kind = 'comment') => {
    try {
      const r = await axios.post(
        `${API}/master-admin/organizations/${orgId}/test-email`,
        { to: toEmail || undefined, kind },
        { headers },
      );
      const { platform_name, sent_to, kind: k } = r.data || {};
      const kindLabel = {
        comment: '2-way conversation',
        engineer_callout: 'engineer callout',
        supplier_welcome: 'supplier welcome',
      }[k] || 'branded';
      notify.success(
        `${platform_name || 'Branded'} ${kindLabel} preview sent to ${sent_to}`,
        { duration: 7000 },
      );
      return r.data;
    } catch (err) {
      notifyApiError(notify, err, 'Failed to send preview email');
      return null;
    }
  }, [API, headers]);

  return {
    updateOrgStatus, updateOrgTier, updateOrgFeatures,
    toggleTestFlag, updateAccountType,
    disableUser, archiveUser, unlockUser, hardDeleteUser, editUser, resetPassword, impersonateUser,
    createOrganization, addUserToOrganization, issueInviteLink, sendEmailPreview,
  };
};

export default useMasterAdminActions;
