import { useMemo, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Clock, Plus, Trash2, X, Loader2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import CheckSheetsTab from '../CheckSheetsTab';

const FREQUENCY_FILTERS = ['all', 'daily', 'weekly', 'monthly', 'quarterly', 'yearly'];
const FREQUENCY_OPTIONS = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly'];

const FREQUENCY_BADGE = {
  daily: 'bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)]',
  weekly: 'bg-purple-500/20 text-purple-400',
  monthly: 'bg-yellow-500/20 text-yellow-400',
  quarterly: 'bg-green-500/20 text-green-400',
  yearly: 'bg-rose-500/20 text-rose-400',
};

const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

const MaintenanceTab = ({ maintenanceTasks, taskFrequencyFilter, setTaskFrequencyFilter, API, onTasksChanged, t }) => {
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [form, setForm] = useState({ title: '', equipment: '', frequency: 'daily' });

  const filteredTasks = useMemo(
    () => maintenanceTasks.filter(task => taskFrequencyFilter === 'all' || task.frequency === taskFrequencyFilter),
    [maintenanceTasks, taskFrequencyFilter]
  );

  const equipmentSuggestions = useMemo(
    () => Array.from(new Set(maintenanceTasks.map(x => x.equipment).filter(Boolean))),
    [maintenanceTasks]
  );

  const addTask = async () => {
    if (!form.title.trim()) return notify.error('Enter a task name');
    setSaving(true);
    try {
      await axios.post(`${API}/maintenance/tasks`, {
        title: form.title.trim(), equipment: form.equipment.trim() || 'General', frequency: form.frequency,
      }, { headers });
      notify.success('Maintenance task added');
      setForm({ title: '', equipment: '', frequency: 'daily' });
      setShowAdd(false);
      onTasksChanged?.();
    } catch (e) { notify.error(e?.response?.data?.detail || 'Could not add task'); }
    finally { setSaving(false); }
  };

  const changeFrequency = async (task, frequency) => {
    if (frequency === task.frequency) return;
    setBusyId(task.id);
    try {
      await axios.patch(`${API}/maintenance/tasks/${task.id}`, { frequency }, { headers });
      onTasksChanged?.();
    } catch (e) { notify.error(e?.response?.data?.detail || 'Could not update frequency'); }
    finally { setBusyId(null); }
  };

  const deleteTask = async (task) => {
    if (!window.confirm(`Remove "${task.title}"?`)) return;
    setBusyId(task.id);
    try {
      await axios.delete(`${API}/maintenance/tasks/${task.id}`, { headers });
      notify.success('Task removed');
      onTasksChanged?.();
    } catch (e) { notify.error(e?.response?.data?.detail || 'Could not remove task'); }
    finally { setBusyId(null); }
  };

  return (
    <div className="space-y-8">
      <CheckSheetsTab />
      <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h2 className="text-2xl font-semibold text-white">{t('dashboard.scheduled_tasks')}</h2>
          <Button
            size="sm"
            className="bg-[var(--color-brand-blue)] text-white hover:opacity-90"
            style={{ color: 'var(--color-white)' }}
            onClick={() => setShowAdd(v => !v)}
            data-testid="add-maintenance-task-btn"
          >
            <Plus size={16} className="mr-1" /> Add Task
          </Button>
        </div>

        {showAdd && (
          <div className="mb-5 p-4 rounded-lg border border-[var(--theme-border)] bg-[var(--theme-surface-hover,rgba(255,255,255,0.03))]" data-testid="add-maintenance-task-form">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-white font-semibold text-sm">New scheduled maintenance task</h3>
              <button onClick={() => setShowAdd(false)} className="text-[var(--color-text-muted)] hover:text-white" data-testid="add-task-close"><X size={16} /></button>
            </div>
            <div className="grid sm:grid-cols-3 gap-3">
              <div className="sm:col-span-1">
                <label className="block text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Task name</label>
                <input
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="e.g. Lubricate belt"
                  className="w-full rounded-lg bg-[var(--theme-surface)] border border-[var(--theme-border)] px-3 py-2 text-sm text-white placeholder:text-[var(--color-text-muted)]"
                  data-testid="add-task-title"
                />
              </div>
              <div className="sm:col-span-1">
                <label className="block text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Equipment / area</label>
                <input
                  value={form.equipment}
                  onChange={(e) => setForm({ ...form, equipment: e.target.value })}
                  placeholder="e.g. Treadmills"
                  list="maint-equipment-suggestions"
                  className="w-full rounded-lg bg-[var(--theme-surface)] border border-[var(--theme-border)] px-3 py-2 text-sm text-white placeholder:text-[var(--color-text-muted)]"
                  data-testid="add-task-equipment"
                />
                <datalist id="maint-equipment-suggestions">
                  {equipmentSuggestions.map(s => <option key={s} value={s} />)}
                </datalist>
              </div>
              <div className="sm:col-span-1">
                <label className="block text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Frequency</label>
                <select
                  value={form.frequency}
                  onChange={(e) => setForm({ ...form, frequency: e.target.value })}
                  className="w-full rounded-lg bg-[var(--theme-surface)] border border-[var(--theme-border)] px-3 py-2 text-sm text-white"
                  data-testid="add-task-frequency"
                >
                  {FREQUENCY_OPTIONS.map(f => <option key={f} value={f}>{cap(f)}</option>)}
                </select>
              </div>
            </div>
            <div className="flex justify-end mt-3">
              <Button size="sm" onClick={addTask} disabled={saving} className="bg-[var(--color-brand-blue)] text-white hover:opacity-90" style={{ color: 'var(--color-white)' }} data-testid="add-task-save">
                {saving ? <Loader2 size={15} className="animate-spin mr-1" /> : <Plus size={15} className="mr-1" />} Add task
              </Button>
            </div>
          </div>
        )}

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
                {cap(freq)}
              </Button>
            );
          })}
        </div>
        <div className="space-y-4">
          {filteredTasks.map(task => (
            <div
              key={task.id}
              className="flex items-center justify-between p-4 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg gap-3"
              data-testid={`task-${task.id}`}
            >
              <div className="flex items-center space-x-4 min-w-0">
                <Clock className="text-[var(--color-brand-blue)] shrink-0" size={24} />
                <div className="min-w-0">
                  <p className="text-white font-semibold truncate">{task.title}{task.is_custom && <span className="ml-2 text-[10px] text-[var(--color-text-muted)] align-middle">custom</span>}</p>
                  <p className="text-[var(--color-text-muted)] text-sm truncate">{task.equipment}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Badge className={`${FREQUENCY_BADGE[task.frequency] || 'bg-gray-500/20 text-gray-400'} hidden sm:inline-flex`}>
                  {task.frequency}
                </Badge>
                <select
                  value={task.frequency}
                  disabled={busyId === task.id}
                  onChange={(e) => changeFrequency(task, e.target.value)}
                  className="rounded-lg bg-[var(--theme-surface)] border border-[var(--theme-border)] px-2 py-1.5 text-sm text-white disabled:opacity-50"
                  data-testid={`task-frequency-select-${task.id}`}
                  aria-label={`Frequency for ${task.title}`}
                >
                  {FREQUENCY_OPTIONS.map(f => <option key={f} value={f}>{cap(f)}</option>)}
                </select>
                {task.is_custom && (
                  <button
                    onClick={() => deleteTask(task)}
                    disabled={busyId === task.id}
                    className="text-[var(--color-text-muted)] hover:text-rose-400 p-1.5 disabled:opacity-50"
                    data-testid={`task-delete-${task.id}`}
                    aria-label={`Delete ${task.title}`}
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
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
