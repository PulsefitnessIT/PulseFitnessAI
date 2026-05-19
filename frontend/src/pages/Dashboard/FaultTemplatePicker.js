import { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Zap, Users, User } from 'lucide-react';

/**
 * Inline template picker shown at the top of the fault-log form.
 * - Loads templates on mount (org-wide + personal merged).
 * - Applying a template pre-fills the parent form + increments usage.
 */
const FaultTemplatePicker = ({ API, onApply }) => {
  const [templates, setTemplates] = useState([]);
  const [selected, setSelected] = useState('');

  const loadTemplates = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/fault-templates`, { headers: { Authorization: `Bearer ${token}` } });
      setTemplates(res.data.templates || []);
    } catch {
      setTemplates([]);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  useEffect(() => { loadTemplates();   }, []);

  const topSuggestions = useMemo(() => templates.slice(0, 3), [templates]);

  const applyTemplate = async (tpl) => {
    onApply({
      machine_type: tpl.machine_type || '',
      issue_description: tpl.issue_description || '',
      severity: tpl.severity || 'operational_minor',
      supplier: tpl.supplier || '',
      steps_taken: tpl.steps_taken || '',
      fault_code: tpl.fault_code || null,
    });
    try {
      const token = localStorage.getItem('token');
      axios.post(`${API}/fault-templates/${tpl.id}/used`, {}, { headers: { Authorization: `Bearer ${token}` } });
    } catch { /* best-effort */ }
  };

  const handleDropdownChange = (e) => {
    const id = e.target.value;
    setSelected(id);
    if (!id) return;
    const tpl = templates.find(t => t.id === id);
    if (tpl) applyTemplate(tpl);
  };

  if (templates.length === 0) return null;

  return (
    <div
      className="rounded-md border px-3 py-2.5 mb-3"
      style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface-2, rgba(0,85,255,0.04))' }}
      data-testid="fault-template-picker"
    >
      <div className="flex items-center gap-2 mb-2">
        <Zap size={14} className="text-[var(--color-brand-blue)]" />
        <Label className="text-xs font-medium" style={{ color: 'var(--theme-text)' }}>
          Quick-log from template
        </Label>
      </div>

      {/* Most-used suggestion chips */}
      {topSuggestions.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2" data-testid="template-suggestions">
          {topSuggestions.map(tpl => (
            <Button
              key={tpl.id}
              size="sm"
              variant="outline"
              onClick={() => applyTemplate(tpl)}
              className="h-7 text-xs gap-1"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid={`template-chip-${tpl.id}`}
            >
              {tpl.scope === 'org' ? <Users size={11} /> : <User size={11} />}
              {tpl.name}
              {tpl.usage_count > 0 && (
                <Badge className="ml-1 text-[10px] px-1 py-0 bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)] border-transparent">
                  {tpl.usage_count}×
                </Badge>
              )}
            </Button>
          ))}
        </div>
      )}

      <select
        value={selected}
        onChange={handleDropdownChange}
        className="w-full rounded-md border px-2 py-1.5 text-xs"
        style={{
          background: 'var(--theme-surface)',
          color: 'var(--theme-text)',
          borderColor: 'var(--theme-border)',
        }}
        data-testid="template-dropdown"
      >
        <option value="">— or pick another template —</option>
        {templates.map(t => (
          <option key={t.id} value={t.id}>
            [{t.scope === 'org' ? 'Site' : 'Me'}] {t.name} — {t.machine_type}
            {t.fault_code ? ` · ${t.fault_code}` : ''}
          </option>
        ))}
      </select>
    </div>
  );
};

export default FaultTemplatePicker;
