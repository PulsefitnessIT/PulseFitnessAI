/**
 * Account Settings — shared primitives.
 *
 * Iter 216h72 — extracted from the legacy monolithic
 * `AccountSettingsModal.js` (>1600 LOC) so each section can live in
 * its own file without re-implementing the auth header / API base /
 * label primitive. Public surface deliberately small — the modal
 * shell and individual section files are the only consumers.
 */
import { useCallback } from 'react';
import {
  User, ShieldCheck, Sliders, CreditCard, Building2, Users, ListChecks, Truck, Database, FileText,
} from 'lucide-react';

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const SECTIONS = [
  { id: 'profile',      label: 'Profile',         icon: User },
  { id: 'onboarding',   label: 'Onboarding',      icon: ListChecks },
  { id: 'security',     label: 'Security',        icon: ShieldCheck },
  { id: 'preferences',  label: 'Preferences',     icon: Sliders },
  { id: 'billing',      label: 'Plan & Billing',  icon: CreditCard },
  { id: 'organisation', label: 'Organisation',    icon: Building2 },
  { id: 'documents',    label: 'Document Branding', icon: FileText },
  { id: 'suppliers',    label: 'Suppliers',       icon: Truck },
  { id: 'team',         label: 'Team & Roles',    icon: Users },
  { id: 'data-export',  label: 'Data export',     icon: Database },
];

export const useAuthHeaders = () =>
  useCallback(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);

export function FieldRow({ label, children }) {
  return (
    <label className="block">
      <div className="text-[11px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--theme-text-muted)' }}>{label}</div>
      {children}
    </label>
  );
}
