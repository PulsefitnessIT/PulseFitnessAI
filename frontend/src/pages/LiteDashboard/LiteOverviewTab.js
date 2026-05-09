import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Wrench, AlertTriangle, CheckCircle, Clock, AlertCircle } from 'lucide-react';
import KpiTile from '../../components/shared/KpiTile';

const LiteOverviewTab = ({
  equipment, openFaults, operational, outOfOrder,
  onLogFault, onViewFault,
  getSeverityStyle, getSeverityLabel
}) => {
  return (
    <div className="space-y-6">
      {/* Iter 216c — `<ActivationMilestonesCard />` moved to OperationsStartTab.
          Once every milestone fires, the Start tab auto-hides and Dashboard
          becomes the first option (Lee, Feb 2026). */}

      {/* Log Fault CTA */}
      <Button onClick={onLogFault} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white px-6 py-3 text-base" data-testid="overview-log-fault-btn">
        <AlertCircle className="mr-2" size={20} /> Log a Fault
      </Button>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile icon={Wrench}        label="Total Machines" value={equipment.length} tone="brand"   testId="lite-kpi-machines" />
        <KpiTile icon={CheckCircle}   label="Operational"    value={operational.length} tone="success" testId="lite-kpi-operational" />
        <KpiTile icon={AlertTriangle} label="With Faults"    value={outOfOrder} tone="danger"          testId="lite-kpi-faults" />
        <KpiTile icon={Clock}         label="Open Faults"    value={openFaults.length} tone="warning"  testId="lite-kpi-open" />
      </div>

      {/* Recent Faults */}
      <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)]">
        <div className="p-4 border-b border-[var(--theme-border)]"><h3 className="font-semibold text-white">Recent Faults</h3></div>
        <div className="divide-y divide-white/5">
          {openFaults.slice(0, 5).map(f => (
            <div key={f.id} className="p-4 flex items-center gap-3 hover:bg-white/[0.02] transition-colors cursor-pointer" onClick={() => onViewFault(f)} data-testid={`lite-recent-fault-${f.id}`}>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-white text-sm">{f.serial_number}</p>
                <p className="text-xs text-[var(--color-text-muted)] truncate">{f.issue_description}</p>
              </div>
              <Badge className={getSeverityStyle(f.severity)}>{getSeverityLabel(f.severity)}</Badge>
              <span className="text-xs text-[var(--color-text-muted)]">{f.created_at ? new Date(f.created_at).toLocaleDateString() : ''}</span>
            </div>
          ))}
          {openFaults.length === 0 && <p className="p-6 text-center text-[var(--color-text-muted)] text-sm">No open faults</p>}
        </div>
      </Card>
    </div>
  );
};

export default LiteOverviewTab;
