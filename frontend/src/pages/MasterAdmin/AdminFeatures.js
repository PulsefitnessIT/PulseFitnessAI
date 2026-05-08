import React from 'react';
import { Card } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';

const FEATURES = [
  { key: 'ai_audits', label: 'AI Audits', group: 'Operations Portal' },
  { key: 'qr_scanning', label: 'QR Scanning', group: 'Operations Portal' },
  { key: 'multi_site', label: 'Multi-Site', group: 'Operations Portal' },
  { key: 'api_access', label: 'API Access', group: 'General' },
  { key: 'white_label', label: 'White Label', group: 'General' },
  { key: 'crm_pipeline', label: 'Pipeline', group: 'CRM Modules' },
  { key: 'crm_quotes', label: 'Quotes / CPQ', group: 'CRM Modules' },
  { key: 'crm_tenders', label: 'Tender Engine', group: 'CRM Modules' },
  { key: 'crm_ai_tools', label: 'AI Tools', group: 'CRM Modules' },
  { key: 'crm_workflows', label: 'Workflows', group: 'CRM Modules' },
  { key: 'crm_documents', label: 'Documents', group: 'CRM Modules' },
];

const groups = [...new Set(FEATURES.map(f => f.group))];

const AdminFeatures = ({ organizations, onUpdateFeatures }) => (
  <div className="space-y-4">
    <p className="text-sm text-zinc-500">Enable or disable features per organization. Toggle switches to control module access.</p>
    {groups.map(group => {
      const groupFeats = FEATURES.filter(f => f.group === group);
      return (
        <div key={group}>
          <p className="text-xs font-bold uppercase tracking-wider text-zinc-400 mb-2">{group}</p>
          <Card className="bg-white border-zinc-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[720px]" data-testid={`features-table-${group.toLowerCase().replace(/\s/g, '-')}`}>
              <thead>
                <tr className="border-b border-zinc-100 bg-zinc-50">
                  <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Organisation</th>
                  {groupFeats.map(f => (
                    <th key={f.key} className="text-center p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">{f.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {organizations.map(org => {
                  const feat = org.features || {};
                  return (
                    <tr key={org.id} className="border-b border-zinc-50 hover:bg-zinc-50">
                      <td className="p-3 font-medium text-zinc-900">{org.name}</td>
                      {groupFeats.map(f => (
                        <td key={f.key} className="p-3 text-center">
                          <Switch
                            checked={feat[f.key] !== false}
                            onCheckedChange={(val) => onUpdateFeatures(org.id, { ...feat, [f.key]: val })}
                            data-testid={`feature-${f.key}-${org.id}`}
                          />
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          </Card>
        </div>
      );
    })}
  </div>
);

export default AdminFeatures;
