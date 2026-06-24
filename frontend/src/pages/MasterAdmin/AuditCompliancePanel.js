import { useState, lazy, Suspense } from 'react';
import { ScrollText, ShieldCheck } from 'lucide-react';

// Merged single source of truth for audit data — replaces the previously
// separate "Audit log" (security timeline) and "Compliance trail" nav
// entries with one screen + an internal toggle.
const AuditLogPanel = lazy(() => import('./AuditLogPanel'));
const AdminAuditLogs = lazy(() => import('./AdminAuditLogs'));

const TABS = [
  { id: 'security', label: 'Security timeline', icon: ShieldCheck },
  { id: 'compliance', label: 'Compliance trail', icon: ScrollText },
];

export default function AuditCompliancePanel({ initialTab = 'security' }) {
  const [tab, setTab] = useState(initialTab === 'compliance' ? 'compliance' : 'security');
  return (
    <div data-testid="audit-compliance-panel">
      <div className="subtab-bar mb-6 flex-wrap" data-testid="audit-compliance-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`subtab-pill ${tab === t.id ? 'is-active' : ''}`}
            data-testid={`audit-compliance-tab-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <Suspense fallback={null}>
        {tab === 'security' ? <AuditLogPanel /> : <AdminAuditLogs />}
      </Suspense>
    </div>
  );
}
