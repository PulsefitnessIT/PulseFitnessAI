/**
 * ModuleGuard
 * -----------
 *
 * Frontend entitlement gate. Redirects users whose org doesn't have the
 * requested module enabled away from the route, surfacing a polite toast
 * so they understand why. Master admins always pass.
 *
 * Usage:
 *
 *   <Route path="/marketing" element={
 *     <ModuleGuard module="marketing"><MarketingSuite/></ModuleGuard>
 *   } />
 *
 * The backend also enforces this via `require_module()` — the frontend
 * guard is the friendly UX layer, not the security boundary.
 */
import React, { useEffect, useRef } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';

const FRIENDLY = {
  operations:  'Operations Portal',
  memberships: 'Memberships',
  marketing:   'Marketing Suite',
};

export default function ModuleGuard({ module, children, fallback = '/dashboard' }) {
  const { user } = useAuth();
  const warned = useRef(false);

  // Master admin and unloaded user state always pass.
  const isMaster = user?.is_master_admin === true || user?.role === 'master_admin' || user?.role === 'master';
  const moduleAccess = user?.module_access || user?.moduleAccess || {};
  const allowed = isMaster || moduleAccess[module] !== false; // undefined = legacy → allow

  useEffect(() => {
    if (!allowed && !warned.current && user) {
      warned.current = true;
      notify.error(
        `${FRIENDLY[module] || module} not enabled`,
        `Your organisation doesn't have this module turned on. Ask your administrator to enable it.`,
      );
    }
  }, [allowed, module, user]);

  if (!user) return null; // App.js handles login gate; we just defer.
  if (!allowed) return <Navigate to={fallback} replace />;
  return children;
}
