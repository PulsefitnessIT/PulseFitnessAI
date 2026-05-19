import { useState } from 'react';
import { SubTabBar } from './SidebarConfig';
import AdminDashboardTab from '../Dashboard/AdminAnalytics/AdminDashboardTab';
import AdminEquipmentTab from '../Dashboard/AdminAnalytics/AdminEquipmentTab';
import AdminFaultsTab from '../Dashboard/AdminAnalytics/AdminFaultsTab';
import AdminCheckSheetsTab from '../Dashboard/AdminAnalytics/AdminCheckSheetsTab';
import AdminAIDiagnosisTab from '../Dashboard/AdminAnalytics/AdminAIDiagnosisTab';

/** Global Analytics — a simple SubTabBar over the five cross-gym analytics dashboards. */
const AnalyticsSection = () => {
  const [tab, setTab] = useState('dashboard');
  const tabs = [
    { id: 'dashboard',   label: 'Dashboard' },
    { id: 'equipment',   label: 'Equipment Trends' },
    { id: 'faults',      label: 'Fault Hotspots' },
    { id: 'checksheets', label: 'Check Sheets' },
    { id: 'ai',          label: 'AI Diagnosis' },
  ];
  return (
    <div>
      <SubTabBar tabs={tabs} active={tab} onChange={setTab} />
      {tab === 'dashboard'   && <AdminDashboardTab />}
      {tab === 'equipment'   && <AdminEquipmentTab />}
      {tab === 'faults'      && <AdminFaultsTab />}
      {tab === 'checksheets' && <AdminCheckSheetsTab />}
      {tab === 'ai'          && <AdminAIDiagnosisTab />}
    </div>
  );
};

export default AnalyticsSection;
