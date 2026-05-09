import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ClipboardCheck, CheckCircle } from 'lucide-react';
import { getTasksForType } from './constants';

/**
 * One row per equipment-type group. Shows the machines as chips (green if
 * the daily check has been recorded today), the first 3 task names as a
 * teaser, and a "Start Check" / "Check Again" button.
 */
const EquipmentGroupCard = ({ group, completedTodayNames, onStart }) => {
  const tasks = getTasksForType(group.equipment_type);
  const done = group.machines.every(
    m => completedTodayNames.has(`${group.equipment_type} - ${m.serial_number || m.name}`)
  );
  const cardClass = done
    ? 'border-emerald-300'
    : 'border-zinc-200 hover:border-blue-300 dark:border-zinc-800';

  return (
    <Card
      className={`bg-white shadow-sm p-5 transition-colors ${cardClass}`}
      data-testid={`pulse-equip-group-${group.equipment_type}`}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-semibold text-zinc-900 dark:text-zinc-100">
              {group.equipment_type}
            </h3>
            <Badge className="bg-zinc-100 text-zinc-500 text-xs dark:bg-zinc-800">
              {group.machines.length} machine{group.machines.length > 1 ? 's' : ''}
            </Badge>
            {done && (
              <Badge className="bg-emerald-50 text-emerald-700 text-xs">
                <CheckCircle size={10} className="mr-1" />Done
              </Badge>
            )}
          </div>
          <div className="flex flex-wrap gap-1 mb-1">
            {group.machines.map(m => {
              const sn = m.serial_number || m.name;
              const isChecked = completedTodayNames.has(`${group.equipment_type} - ${sn}`);
              const chipClass = isChecked
                ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                : 'bg-zinc-50 border-zinc-200 text-zinc-500 dark:bg-zinc-900 dark:border-zinc-800';
              return (
                <span key={m.id} className={`text-xs px-2 py-0.5 rounded border ${chipClass}`}>
                  {isChecked && <CheckCircle size={9} className="inline mr-0.5" />}{sn}
                </span>
              );
            })}
          </div>
          <p className="text-xs text-zinc-400">
            {tasks.slice(0, 3).join(' · ')}
            {tasks.length > 3 ? ` +${tasks.length - 3} more` : ''}
          </p>
        </div>
        <Button
          onClick={() => onStart(group)}
          className={done
            ? 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200'
            : 'bg-blue-600 hover:bg-blue-700 text-white'}
          data-testid={`pulse-start-${group.equipment_type}`}
        >
          <ClipboardCheck size={15} className="mr-1.5" />
          {done ? 'Check Again' : 'Start Check'}
        </Button>
      </div>
    </Card>
  );
};

export default EquipmentGroupCard;
