import React from 'react';
import { LayoutDashboard, Wrench, AlertTriangle, FileText, Plus, BarChart3, Brain, Users, Calendar, Dumbbell } from 'lucide-react';

const MobileBottomNav = ({ activeTab, setActiveTab, onReportFault, variant = 'gymaxis', isPro = false }) => {
  const pulseItems = [
    { id: 'overview', icon: LayoutDashboard, label: 'Home' },
    { id: 'equipment', icon: Wrench, label: 'Equipment' },
    { id: 'faults', icon: AlertTriangle, label: 'Faults' },
    { id: 'documents', icon: FileText, label: 'Docs' },
    ...(isPro ? [{ id: 'reports', icon: BarChart3, label: 'Reports' }] : []),
  ];

  const gymaxisItems = [
    { id: 'overview', icon: LayoutDashboard, label: 'Home' },
    { id: 'equipment', icon: Wrench, label: 'Equipment' },
    { id: 'issues', icon: AlertTriangle, label: 'Faults' },
    { id: 'reports', icon: BarChart3, label: 'Reports' },
    { id: 'diagnosis', icon: Brain, label: 'AI' },
  ];

  const membershipsItems = [
    { id: 'dashboard', icon: LayoutDashboard, label: 'Home' },
    { id: 'members',   icon: Users,           label: 'Members' },
    { id: 'timetable', icon: Calendar,        label: 'Timetable' },
    { id: 'classes',   icon: Dumbbell,        label: 'Classes' },
    { id: 'analytics', icon: BarChart3,       label: 'Analytics' },
  ];

  let items = gymaxisItems;
  let accentColor = 'var(--color-brand-blue)';
  if (variant === 'pulse') { items = pulseItems; accentColor = 'var(--color-brand-cyan-hover)'; }
  if (variant === 'memberships') { items = membershipsItems; accentColor = 'var(--color-brand-cyan)'; }

  const showFab = variant !== 'memberships'; // Memberships has no "Report Fault" shortcut

  return (
    <div className="md:hidden fixed bottom-0 left-0 right-0 z-40" data-testid="mobile-bottom-nav">
      <div
        className="flex items-center justify-around px-1 pt-1 pb-safe-bottom border-t backdrop-blur-xl"
        style={{
          background: 'var(--theme-surface)',
          borderColor: 'var(--theme-border)',
          paddingBottom: 'max(0.5rem, env(safe-area-inset-bottom))',
        }}
      >
        {items.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab && setActiveTab(item.id)}
              className="flex flex-col items-center gap-0.5 py-1.5 px-2 min-w-[52px] transition-colors"
              style={{ color: isActive ? accentColor : 'var(--theme-text-muted)' }}
              data-testid={`mobile-nav-${item.id}`}
            >
              <item.icon size={20} strokeWidth={isActive ? 2.2 : 1.5} />
              <span className="text-[10px] font-medium leading-tight">{item.label}</span>
            </button>
          );
        })}
        {showFab && (
          <button
            onClick={onReportFault}
            className="flex flex-col items-center gap-0.5 py-1.5 px-2 min-w-[52px]"
            style={{ color: accentColor }}
            data-testid="mobile-nav-report-fault"
          >
            <div
              className="w-10 h-10 rounded-full flex items-center justify-center -mt-5 shadow-lg"
              style={{ background: accentColor }}
            >
              <Plus size={22} className="text-white" strokeWidth={2.5} />
            </div>
            <span className="text-[10px] font-medium leading-tight -mt-0.5">Report</span>
          </button>
        )}
      </div>
    </div>
  );
};

export default MobileBottomNav;
