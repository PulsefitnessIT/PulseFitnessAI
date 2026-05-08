import React from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Truck, Dumbbell, Users, PartyPopper, CheckCircle, ArrowRight } from 'lucide-react';
import { SummaryStat } from './SharedBits';

const StageLive = ({ status, onFinish, onLogFault }) => {
  const counts = status?.counts || {};
  const totalStaff = (counts.staff_active || 0) + (counts.staff_invited || 0);
  return (
    <div className="text-center py-6" data-testid="stage-live">
      <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br from-emerald-400 to-[var(--color-brand-blue)] mb-4">
        <PartyPopper size={36} className="text-white" />
      </div>
      <h3 className="text-2xl font-semibold mb-1">Your gym is now live 🎉</h3>
      <p className="text-[var(--color-text-muted)] text-sm max-w-md mx-auto mb-6">
        You&apos;re fully onboarded. Time to see GymAxis in action — log your first fault and watch the AI triage engine work.
      </p>

      <div className="grid grid-cols-3 gap-3 max-w-md mx-auto mb-6">
        <SummaryStat icon={Truck}    value={counts.suppliers || 0}      label="Suppliers"  testid="summary-suppliers" />
        <SummaryStat icon={Dumbbell} value={counts.equipment || 0}      label="Machines"   testid="summary-equipment" />
        <SummaryStat icon={Users}    value={totalStaff}                  label="Teammates"  testid="summary-staff" />
      </div>

      <Badge className="bg-emerald-500/20 text-emerald-300 border-transparent mb-5" data-testid="fully-operational-badge">
        <CheckCircle size={11} className="mr-1" /> Fully Operational Gym
      </Badge>

      <div className="flex flex-col sm:flex-row gap-2 justify-center max-w-md mx-auto">
        <Button onClick={onLogFault} className="bg-[var(--color-brand-blue)] text-white flex-1" data-testid="go-live-log-fault-btn">
          Log your first fault <ArrowRight size={14} className="ml-1" />
        </Button>
        <Button onClick={onFinish} variant="outline" className="border-[var(--theme-border)] text-white flex-1" data-testid="go-live-finish-btn">
          Explore dashboard
        </Button>
      </div>
    </div>
  );
};

export default StageLive;
