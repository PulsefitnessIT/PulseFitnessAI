import { BarChart3, Star, Cog, Radar, ShieldAlert, FileBarChart, FileText } from 'lucide-react';
import { SubTabHub } from './SubTabHub';
import MostUsedAnalysisTab from './MostUsedAnalysisTab';
import MostUsedTab from './MostUsedTab';
import MachinePartsTab from './MachinePartsTab';
import FailureIntelTab from './FailureIntelTab';
import AlertsTab from './AlertsTab';
import DataIntelligenceTab from './DataIntelligenceTab';
import ReportsTab from './ReportsTab';

const ITEMS = [
  { id: 'mua', label: 'Most-Used Analysis', icon: BarChart3, C: MostUsedAnalysisTab },
  { id: 'intel', label: 'Intelligence & Reports', icon: Radar, C: DataIntelligenceTab },
  { id: 'machine', label: 'Parts by Machine', icon: Cog, C: MachinePartsTab },
  { id: 'mostused', label: 'Most-Used Parts (manual)', icon: Star, C: MostUsedTab },
  { id: 'failure', label: 'Failure Intelligence', icon: ShieldAlert, C: FailureIntelTab },
  { id: 'alerts', label: 'Monitoring & Alerts', icon: FileBarChart, C: AlertsTab },
  { id: 'reports', label: 'Dealer Reports', icon: FileText, C: ReportsTab },
];

export default function AnalyticsTab() {
  return <SubTabHub items={ITEMS} storageKey="analytics" />;
}
