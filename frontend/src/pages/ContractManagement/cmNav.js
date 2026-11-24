/**
 * Contract Management workspace — navigation + section mapping over the
 * EXISTING CRM / Aftersales components (same CRMContext, auth and records).
 */
import { ListChecks, Building2, Zap, Shield, RefreshCw, CalendarClock, Receipt, BarChart3, Settings } from 'lucide-react';

export const CM_NAV_ITEMS = [
  { id: 'action-centre', label: 'Action Centre', icon: ListChecks, perm: 'workspace.contract_management' },
  { id: 'customers', label: 'Customers', icon: Building2, perm: 'contracts.read' },
  { id: 'build-quote', label: 'Build Quote', icon: Zap, perm: 'quotes.maintenance' },
  { id: 'contracts', label: 'Contracts & Agreements', icon: Shield, perm: 'contracts.read' },
  { id: 'renewals', label: 'Renewals', icon: RefreshCw, perm: 'renewals.review' },
  { id: 'service-planner', label: 'Service Planner', icon: CalendarClock, perm: 'service.read' },
  { id: 'finance', label: 'Finance & Invoices', icon: Receipt, perm: 'billing.prepare' },
  { id: 'reports', label: 'Reports', icon: BarChart3, perm: 'workspace.contract_management' },
  { id: 'settings', label: 'Settings', icon: Settings, perm: 'workspace.contract_management' },
];

export const CM_SECTION_SUBTABS = {
  'action-centre': ['dashboard'],
  'build-quote': ['autoquote', 'onboarding', 'equipment', 'supportability'],
  contracts: ['contracts', 'agreements'],
  renewals: ['renewals'],
  'service-planner': ['service'],
  finance: ['finance'],
  reports: ['reports', 'ai'],
};

export const CM_DEFAULT_SECTION = 'action-centre';

export function sectionForSubTab(subTab) {
  if (subTab === 'pricing') return 'settings';
  return Object.keys(CM_SECTION_SUBTABS).find((k) => CM_SECTION_SUBTABS[k].includes(subTab)) || CM_DEFAULT_SECTION;
}

export function cmPermissions(crmUser, platformUser) {
  return (crmUser && crmUser.crm_permissions) || (platformUser && platformUser.crm_permissions) || [];
}

export function visibleCmNav(perms) {
  return CM_NAV_ITEMS.filter((it) => perms.includes(it.perm));
}

// CRM entity → Contract Management section for global search / deep links.
export const CM_ENTITY_SECTION = { company: 'customers', contact: 'customers', contract: 'contracts', quote: 'build-quote' };
