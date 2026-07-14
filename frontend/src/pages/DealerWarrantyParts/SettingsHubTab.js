import { Settings, UploadCloud, Layers, GitCompare, HelpCircle } from 'lucide-react';
import { SubTabHub } from './SubTabHub';
import SettingsTab from './SettingsTab';
import DataImportsTab from './DataImportsTab';
import BomTab from './BomTab';
import MatchReviewTab from './MatchReviewTab';
import UnmatchedReviewTab from './UnmatchedReviewTab';

const ITEMS = [
  { id: 'general', label: 'General', icon: Settings, C: SettingsTab },
  { id: 'imports', label: 'Data Imports', icon: UploadCloud, C: DataImportsTab },
  { id: 'bom', label: 'BOM Management', icon: Layers, C: BomTab },
  { id: 'match', label: 'Match Review', icon: GitCompare, C: MatchReviewTab },
  { id: 'unmatched', label: 'Unmatched Review', icon: HelpCircle, C: UnmatchedReviewTab },
];

export default function SettingsHubTab() {
  return <SubTabHub items={ITEMS} storageKey="settings" />;
}
