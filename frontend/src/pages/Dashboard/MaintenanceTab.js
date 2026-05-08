import React, { useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Clock } from 'lucide-react';
import CheckSheetsTab from '../CheckSheetsTab';

const FREQUENCY_FILTERS = ['all', 'daily', 'weekly', 'monthly', 'quarterly'];

const FREQUENCY_BADGE = {
 daily: 'bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)]',
 weekly: 'bg-purple-500/20 text-purple-400',
 monthly: 'bg-yellow-500/20 text-yellow-400',
 quarterly: 'bg-green-500/20 text-green-400',
};

const MaintenanceTab = ({ maintenanceTasks, taskFrequencyFilter, setTaskFrequencyFilter, t }) => {
 const filteredTasks = useMemo(
 () => maintenanceTasks.filter(task => taskFrequencyFilter === 'all' || task.frequency === taskFrequencyFilter),
 [maintenanceTasks, taskFrequencyFilter]
 );

 return (
 <div className="space-y-8">
 <CheckSheetsTab />
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6">
 <div className="flex items-center justify-between mb-4">
 <h2 className="text-2xl font-semibold text-white">{t('dashboard.scheduled_tasks')}</h2>
 </div>
 <div className="flex gap-2 mb-4 flex-wrap" data-testid="task-frequency-filters">
 {FREQUENCY_FILTERS.map(freq => {
 const active = taskFrequencyFilter === freq;
 return (
 <Button
 key={freq}
 size="sm"
 variant="outline"
 className={active ? 'bg-[var(--color-brand-blue)] text-white border-transparent' : 'border-[var(--theme-border)] text-[var(--color-text-muted)] hover:text-white'}
 style={active ? { color: 'var(--color-white)' } : undefined}
 onClick={() => setTaskFrequencyFilter(freq)}
 data-testid={`task-filter-${freq}`}
 >
 {freq.charAt(0).toUpperCase() + freq.slice(1)}
 </Button>
 );
 })}
 </div>
 <div className="space-y-4">
 {filteredTasks.map(task => (
 <div
 key={task.id}
 className="flex items-center justify-between p-4 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg"
 data-testid={`task-${task.id}`}
 >
 <div className="flex items-center space-x-4">
 <Clock className="text-[var(--color-brand-blue)]" size={24} />
 <div>
 <p className="text-white font-semibold">{task.title}</p>
 <p className="text-[var(--color-text-muted)] text-sm">{task.equipment}</p>
 </div>
 </div>
 <Badge className={FREQUENCY_BADGE[task.frequency] || 'bg-gray-500/20 text-gray-400'}>
 {task.frequency}
 </Badge>
 </div>
 ))}
 {filteredTasks.length === 0 && (
 <p className="text-[var(--color-text-muted)] text-center py-6">{t('dashboard.no_tasks_found')}</p>
 )}
 </div>
 </Card>
 </div>
 );
};

export default MaintenanceTab;
