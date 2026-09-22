/**
 * SiconIntegrationPage (Iter 238e)
 *
 * Single tabbed surface for everything Sicon. Replaces the previous
 * stacked layout where Health, Field Mappings (custom panel), and the
 * generic IntegrationAdminPanel were rendered one below the other —
 * which produced a duplicate "Field Mappings" section (one custom, one
 * inside IntegrationAdminPanel) and a confusing scroll.
 *
 * Tabs:
 *   • Overview     — health tiles + percentage bar (no org table)
 *   • Organisations — per-org status table (was buried at the bottom)
 *   • Event Log     — IntegrationAdminPanel logs view
 *   • Configuration — IntegrationAdminPanel config view
 *   • Field Mappings — IntegrationAdminPanel mappings view (single source)
 */
import { useState } from 'react';
import { ArrowLeftRight } from 'lucide-react';
import SiconHealthPanel from './SiconHealthPanel';
import SiconReadinessPanel from './SiconReadinessPanel';
import SiconEquipmentMapper from './SiconEquipmentMapper';
import IntegrationAdminPanel from '../IntegrationAdminPanel';
import SubTabBar from '../../components/shared/SubTabBar';

const TABS = [
  { id: 'readiness',    label: 'Readiness' },
  { id: 'overview',     label: 'Overview' },
  { id: 'organisations', label: 'Organisations' },
  { id: 'equipment',    label: 'Equipment IDs' },
  { id: 'logs',         label: 'Event Log' },
  { id: 'config',       label: 'Configuration' },
  { id: 'mappings',     label: 'Field Mappings' },
];

export default function SiconIntegrationPage() {
  const [tab, setTab] = useState('readiness');

  return (
    <div className="space-y-5" data-testid="sicon-integration-page">
      <SubTabBar
        tabs={TABS}
        active={tab}
        onChange={setTab}
        testId="sicon-tab"
      />

      {tab === 'readiness' && <SiconReadinessPanel />}
      {tab === 'overview' && <SiconHealthPanel view="overview" />}
      {tab === 'organisations' && <SiconHealthPanel view="organisations" />}
      {tab === 'equipment' && <SiconEquipmentMapper />}
      {(tab === 'logs' || tab === 'config' || tab === 'mappings') && (
        <IntegrationAdminPanel
          integrationId="sicon"
          title="Sicon Service"
          icon={ArrowLeftRight}
          color="bg-violet-600"
          initialSection={tab}
          hideHeader
        />
      )}
    </div>
  );
}
