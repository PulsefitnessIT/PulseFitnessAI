import { useState } from 'react';
import { useAuth } from '@/App';
import { useCRM } from '@/pages/CRM/CRMApp';
import AftersalesApp from '@/pages/CRM/Aftersales/AftersalesApp';
import { cmPermissions } from './cmNav';
import WorkspaceRolesPanel from './WorkspaceRolesPanel';

const DEFAULT_AREA_KEY = 'pf_launcher_default_area';

function Card({ title, children, c, testId }) {
  return (
    <section className="rounded-2xl p-5 mb-5" style={{ background: c.surface, border: `1px solid ${c.border}` }} data-testid={testId}>
      <h2 className="text-base font-bold pulse-font-heading mb-3" style={{ color: c.text }}>{title}</h2>
      {children}
    </section>
  );
}

function DefaultAreaToggle({ c }) {
  const read = () => { try { return localStorage.getItem(DEFAULT_AREA_KEY) === 'contract_management'; } catch { return false; } };
  const [on, setOn] = useState(read);
  const toggle = (v) => {
    try {
      if (v) localStorage.setItem(DEFAULT_AREA_KEY, 'contract_management');
      else if (read()) localStorage.removeItem(DEFAULT_AREA_KEY);
    } catch { /* quota */ }
    setOn(v);
  };
  return (
    <label className="flex items-center gap-3 cursor-pointer select-none w-fit" data-testid="cm-default-area-toggle">
      <input type="checkbox" checked={on} onChange={(e) => toggle(e.target.checked)}
        className="h-4 w-4 rounded" style={{ accentColor: 'var(--color-brand-cyan)' }} data-testid="cm-default-area-checkbox" />
      <span className="text-sm" style={{ color: c.text }}>Open Contract Management straight after sign-in on this device</span>
    </label>
  );
}

/** Coordinator preferences for everyone; restricted configuration for admins. */
export default function WorkspaceSettings() {
  const { user, c } = useCRM();
  const mainAuth = useAuth();
  const perms = cmPermissions(user, mainAuth?.user);
  const roleLabel = user?.crm_workspace_role_label || mainAuth?.user?.crm_workspace_role_label || 'Contract Management user';
  return (
    <div data-testid="cm-section-settings">
      <Card title="Your workspace" c={c} testId="cm-settings-preferences">
        <p className="text-sm mb-4" style={{ color: c.textMuted }}>
          Signed in as <span style={{ color: c.text, fontWeight: 600 }} data-testid="cm-settings-role">{roleLabel}</span>.
          Contract Management uses the same customers, sites, equipment and contracts as CRM.
        </p>
        <DefaultAreaToggle c={c} />
      </Card>
      {perms.includes('permissions.admin') && (
        <Card title="Workspace roles" c={c} testId="cm-settings-roles">
          <WorkspaceRolesPanel />
        </Card>
      )}
      {perms.includes('pricing.manage') && (
        <Card title="Pricing & rules" c={c} testId="cm-settings-pricing">
          <AftersalesApp sections={['pricing']} initialTab="pricing" />
        </Card>
      )}
    </div>
  );
}
