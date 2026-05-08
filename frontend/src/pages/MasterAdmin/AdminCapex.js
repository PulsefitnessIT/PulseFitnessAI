import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { RefreshCw } from 'lucide-react';

const AdminCapex = ({ capexThresholds, setCapexThresholds, capexOverview, onSave, onRefresh }) => (
  <div className="space-y-6" data-testid="capex-config-section">
    {/* Thresholds */}
    <Card className="bg-white border-zinc-200 p-6">
      <h3 className="font-semibold text-zinc-900 text-lg mb-4">Scoring Thresholds</h3>
      <p className="text-zinc-500 text-sm mb-6">Configure the weighted scoring model and status cutoff points.</p>
      {capexThresholds ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            {[
              { key: 'age_weight', label: 'Age Weight' },
              { key: 'fault_count_weight', label: 'Fault Count Weight' },
              { key: 'fault_frequency_weight', label: 'Frequency Weight' },
              { key: 'severity_weight', label: 'Severity Weight' },
              { key: 'warranty_weight', label: 'Warranty Weight' },
            ].map(w => (
              <div key={w.key}>
                <label className="text-xs text-zinc-500 mb-1 block">{w.label}</label>
                <Input
                  type="number"
                  value={capexThresholds[w.key] || 0}
                  onChange={e => setCapexThresholds(prev => ({ ...prev, [w.key]: Number(e.target.value) }))}
                  className="h-10 bg-zinc-50"
                  data-testid={`capex-threshold-${w.key}`}
                />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            {[
              { key: 'replace_now_min', label: 'Replace Now (min score)', color: 'text-zinc-900' },
              { key: 'replace_soon_min', label: 'Replace Soon (min score)', color: 'text-red-600' },
              { key: 'at_risk_min', label: 'At Risk (min score)', color: 'text-orange-600' },
              { key: 'monitor_min', label: 'Monitor (min score)', color: 'text-yellow-600' },
            ].map(t => (
              <div key={t.key}>
                <label className={`text-xs mb-1 block ${t.color}`}>{t.label}</label>
                <Input
                  type="number"
                  value={capexThresholds[t.key] || 0}
                  onChange={e => setCapexThresholds(prev => ({ ...prev, [t.key]: Number(e.target.value) }))}
                  className="h-10 bg-zinc-50"
                  data-testid={`capex-threshold-${t.key}`}
                />
              </div>
            ))}
          </div>
          <Button onClick={onSave} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" data-testid="capex-save-thresholds">Save Thresholds</Button>
        </>
      ) : (
        <Button onClick={onRefresh} variant="outline">Load Thresholds</Button>
      )}
    </Card>

    {/* Cross-Org Overview */}
    <Card className="bg-white border-zinc-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-zinc-900 text-lg">Cross-Organisation Overview</h3>
        <Button size="sm" variant="outline" onClick={onRefresh} data-testid="capex-refresh-overview"><RefreshCw size={14} className="mr-1" /> Refresh</Button>
      </div>
      {capexOverview ? (
        <div className="space-y-2">
          {capexOverview.map(org => (
            <div key={org.org_id} className="flex items-center justify-between p-3 rounded-lg bg-zinc-50">
              <div>
                <p className="font-medium text-zinc-900 text-sm">{org.org_name}</p>
                <p className="text-xs text-zinc-400">{org.equipment_count} machines · {org.total_faults} faults</p>
              </div>
            </div>
          ))}
          {capexOverview.length === 0 && <p className="text-zinc-400 text-sm text-center py-8">No organisations found</p>}
        </div>
      ) : (
        <Button onClick={onRefresh} variant="outline">Load Overview</Button>
      )}
    </Card>
  </div>
);

export default AdminCapex;
