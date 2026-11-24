import AftersalesApp from '@/pages/CRM/Aftersales/AftersalesApp';
import CRMCompanies from '@/pages/CRM/CRMCompanies';
import { useCRM } from '@/pages/CRM/CRMApp';
import { CM_SECTION_SUBTABS, sectionForSubTab } from './cmNav';
import WorkspaceSettings from './WorkspaceSettings';
import RenewalsInProgress from './RenewalsInProgress';

/** Renders one Contract Management section using the existing components. */
export default function ContractManagementSection({ section, subTab, onNavigate }) {
  const { setActiveTab } = useCRM();
  if (section === 'customers') return <CRMCompanies />;
  if (section === 'settings') return <WorkspaceSettings onNavigate={onNavigate} />;
  const sections = CM_SECTION_SUBTABS[section] || CM_SECTION_SUBTABS['action-centre'];
  const initial = subTab && sections.includes(subTab) ? subTab : sections[0];
  return (
    <div data-testid={`cm-section-${section}`}>
      {section === 'renewals' && <RenewalsInProgress />}
      <AftersalesApp
        key={`${section}:${initial}`}
        sections={sections}
        initialTab={initial}
        onLeaveSection={(t) => (onNavigate ? onNavigate(sectionForSubTab(t), t) : setActiveTab(sectionForSubTab(t)))}
      />
    </div>
  );
}
