import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '@/components/ui/dialog';
import { CheckCircle } from 'lucide-react';

/**
 * The "complete check sheet" modal. Handles three modes:
 *   1. Single-machine group → just shows the SN summary.
 *   2. Multi-machine group → multi-select with "Select all / Clear".
 *      Submits one completion record per ticked machine.
 *   3. Custom template → no machines, just the items.
 *
 * All state lives in the parent (`PulseCheckSheetsTab`) so this stays a
 * presentational component with explicit props.
 */
const CompleteSheetDialog = ({
  open,
  onOpenChange,
  activeSheet,
  selectedSerials,
  setSelectedSerials,
  checkedItems,
  setCheckedItems,
  completionDate,
  setCompletionDate,
  completionNotes,
  setCompletionNotes,
  onSubmit,
}) => {
  if (!activeSheet) return null;
  const machines = activeSheet.machines || [];
  const items = activeSheet.items || [];

  const toggleMachine = (key, checked) => {
    setSelectedSerials(prev =>
      checked ? [...prev, key] : prev.filter(k => k !== key)
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white border-zinc-200 text-zinc-900 max-w-lg max-h-[85vh] overflow-y-auto dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800">
        <DialogHeader><DialogTitle>{activeSheet.equipment_type}</DialogTitle></DialogHeader>
        <div className="space-y-4">
          {machines.length > 1 && (
            <div className="space-y-2" data-testid="pulse-sheet-multi">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <Label className="text-zinc-700 text-sm dark:text-zinc-300">
                  Machines ({selectedSerials.length}/{machines.length})
                </Label>
                <div className="flex gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => setSelectedSerials(machines.map(m => m.serial_number || m.name))}
                    className="text-blue-600 hover:underline dark:text-blue-400"
                    data-testid="pulse-sheet-select-all"
                  >Select all</button>
                  <span className="text-zinc-300 dark:text-zinc-700">·</span>
                  <button
                    type="button"
                    onClick={() => setSelectedSerials([])}
                    className="text-zinc-500 hover:underline dark:text-zinc-400"
                    data-testid="pulse-sheet-clear-all"
                  >Clear</button>
                </div>
              </div>
              <div className="max-h-48 overflow-y-auto rounded-md border border-zinc-200 dark:border-zinc-800 divide-y divide-zinc-100 dark:divide-zinc-800">
                {machines.map((m, i) => {
                  const key = m.serial_number || m.name;
                  const ticked = selectedSerials.includes(key);
                  return (
                    <label
                      key={i}
                      className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/50 select-none"
                      data-testid={`pulse-sheet-machine-${i}`}
                    >
                      <input
                        type="checkbox"
                        checked={ticked}
                        onChange={(e) => toggleMachine(key, e.target.checked)}
                        className="w-4 h-4 accent-blue-600 cursor-pointer shrink-0"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-zinc-900 truncate dark:text-zinc-100">{m.name}</p>
                        {m.serial_number && (
                          <p className="text-[10px] font-mono text-zinc-500 dark:text-zinc-400 truncate">
                            S/N {m.serial_number}
                          </p>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
              <p className="text-[11px] text-zinc-400">
                Tick the machines you've checked. One completion record will be saved per ticked machine.
              </p>
            </div>
          )}

          {machines.length === 1 && (
            <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-3 dark:bg-zinc-900 dark:border-zinc-800">
              <p className="text-xs text-zinc-400 uppercase">Machine</p>
              <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{machines[0].name}</p>
              {machines[0].serial_number && (
                <p className="text-xs text-zinc-400">SN: {machines[0].serial_number}</p>
              )}
            </div>
          )}

          <div>
            <Label className="text-zinc-700 text-sm">Date</Label>
            <Input
              type="date"
              value={completionDate}
              onChange={e => setCompletionDate(e.target.value)}
              className="bg-white border-zinc-200 text-zinc-900 mt-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
            />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between text-xs text-zinc-500">
              <span>Check Items</span>
              <span>
                {Object.values(checkedItems).filter(Boolean).length}/{items.length}
              </span>
            </div>
            {items.map((item, idx) => (
              <label
                key={idx}
                className="flex items-center gap-3 p-3 bg-zinc-50 border border-zinc-200 rounded-lg cursor-pointer hover:border-blue-300 transition-colors dark:bg-zinc-900 dark:border-zinc-800"
                data-testid={`pulse-check-item-${idx}`}
              >
                <input
                  type="checkbox"
                  checked={!!checkedItems[item]}
                  onChange={() => setCheckedItems(p => ({ ...p, [item]: !p[item] }))}
                  className="w-4 h-4 accent-blue-600"
                />
                <span className={`text-sm flex-1 ${checkedItems[item] ? 'text-zinc-900 dark:text-zinc-100' : 'text-zinc-500'}`}>
                  {item}
                </span>
                {checkedItems[item] && <CheckCircle size={14} className="text-emerald-500" />}
              </label>
            ))}
          </div>

          <div>
            <Label className="text-zinc-700 text-sm">Notes (optional)</Label>
            <Textarea
              value={completionNotes}
              onChange={e => setCompletionNotes(e.target.value)}
              rows={2}
              placeholder="Any issues noticed..."
              className="bg-white border-zinc-200 text-zinc-900 mt-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
            />
          </div>

          <Button
            onClick={onSubmit}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white"
            data-testid="pulse-submit-sheet"
          >Submit Completed Sheet</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default CompleteSheetDialog;
