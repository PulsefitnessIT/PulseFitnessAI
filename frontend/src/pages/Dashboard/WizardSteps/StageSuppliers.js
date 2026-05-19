import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Plus, Trash2, Check } from 'lucide-react';
import { StageIntro, StageFooter, Field } from './SharedBits';

/**
 * Iter 216o-7 — Multi-select supplier categories.
 *
 * Pulse Fitness, Precor, Technogym etc. typically supply both Cardio
 * AND Strength (and often Functional too). The earlier single-select
 * dropdown forced operators to pick just one which mis-routed faults.
 *
 * Expanded the catalogue to cover the realistic full estate of supplier
 * specialisations:
 *   Cardio · Strength · Functional · Free Weights · Plate Loaded ·
 *   Group Cycling · Stretching · Recovery / Wellness · Flooring ·
 *   Audio / AV · Lockers · HVAC · Plumbing · Electrical · Cleaning ·
 *   Other
 *
 * Storage shape: `supplier_types: string[]` on the row. The first item
 * is also written to `supplier_type` for backwards-compat with any
 * legacy code that reads the singular field.
 */

const SUPPLIER_TYPES = [
  { value: 'cardio',         label: 'Cardio' },
  { value: 'strength',       label: 'Strength' },
  { value: 'functional',     label: 'Functional' },
  { value: 'free_weights',   label: 'Free Weights' },
  { value: 'plate_loaded',   label: 'Plate Loaded' },
  { value: 'group_cycling',  label: 'Group Cycling' },
  { value: 'stretching',     label: 'Stretching' },
  { value: 'recovery',       label: 'Recovery / Wellness' },
  { value: 'flooring',       label: 'Flooring' },
  { value: 'av',             label: 'Audio / AV' },
  { value: 'lockers',        label: 'Lockers' },
  { value: 'hvac',           label: 'HVAC' },
  { value: 'plumbing',       label: 'Plumbing' },
  { value: 'electrical',     label: 'Electrical' },
  { value: 'cleaning',       label: 'Cleaning' },
  { value: 'other',          label: 'Other' },
];

const TypeChips = ({ selected, onToggle, rowIndex }) => {
  const sel = Array.isArray(selected) ? selected : (selected ? [selected] : []);
  return (
    <div className="flex flex-wrap gap-1.5" data-testid={`supplier-type-chips-${rowIndex}`}>
      {SUPPLIER_TYPES.map((t) => {
        const isOn = sel.includes(t.value);
        return (
          <button
            key={t.value}
            type="button"
            onClick={() => onToggle(t.value)}
            data-testid={`supplier-type-${rowIndex}-${t.value}`}
            data-active={isOn}
            className={`text-xs px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1
              ${isOn
                ? 'bg-[var(--color-brand-blue)] border-[var(--color-brand-blue)] text-white'
                : 'border-[var(--theme-border)] text-[var(--color-text-muted)] hover:border-[var(--color-brand-blue)] hover:text-[var(--theme-text)]'}`}
          >
            {isOn ? <Check size={11} /> : null}
            {t.label}
          </button>
        );
      })}
    </div>
  );
};

const StageSuppliers = ({ suppliers, addRow, removeRow, updateRow, onSave, onSkip, saving, alreadyDone }) => {
  const toggleType = (i, value) => {
    const current = suppliers[i].supplier_types
      || (suppliers[i].supplier_type ? [suppliers[i].supplier_type] : []);
    const next = current.includes(value)
      ? current.filter((t) => t !== value)
      : [...current, value];
    updateRow(i, 'supplier_types', next);
    // Keep singular in sync for backward compat.
    updateRow(i, 'supplier_type', next[0] || '');
  };

  return (
    <div className="space-y-5" data-testid="stage-suppliers">
      <StageIntro
        title="Add your service suppliers"
        blurb="We'll auto-route faults to them when your team logs an issue — no more chasing emails."
        badge="Stage 1 / 4"
        alreadyDone={alreadyDone}
      />
      <div className="space-y-3">
        {suppliers.map((s, i) => (
          <div
            key={i}
            className="bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg p-4"
            data-testid={`supplier-row-${i}`}
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Company Name" required>
                <Input
                  value={s.company_name}
                  onChange={(e) => updateRow(i, 'company_name', e.target.value)}
                  placeholder="e.g. Precor UK Ltd"
                  className="bg-[var(--theme-surface)] border-[var(--theme-border)]"
                  data-testid={`supplier-name-${i}`}
                />
              </Field>
              <Field label="Service Desk Email" required>
                <Input
                  type="email"
                  value={s.contact_email}
                  onChange={(e) => updateRow(i, 'contact_email', e.target.value)}
                  placeholder="service@precor.co.uk"
                  className="bg-[var(--theme-surface)] border-[var(--theme-border)]"
                  data-testid={`supplier-email-${i}`}
                />
              </Field>
              <Field label="Phone">
                <Input
                  value={s.phone}
                  onChange={(e) => updateRow(i, 'phone', e.target.value)}
                  placeholder="+44 20 ..."
                  className="bg-[var(--theme-surface)] border-[var(--theme-border)]"
                  data-testid={`supplier-phone-${i}`}
                />
              </Field>
              <Field label="Contact Person">
                <Input
                  value={s.contact_person}
                  onChange={(e) => updateRow(i, 'contact_person', e.target.value)}
                  placeholder="e.g. Sarah Patel"
                  className="bg-[var(--theme-surface)] border-[var(--theme-border)]"
                  data-testid={`supplier-contact-${i}`}
                />
              </Field>
            </div>

            <div className="mt-3">
              <Field label="Categories supplied (select all that apply)">
                <TypeChips
                  selected={s.supplier_types || (s.supplier_type ? [s.supplier_type] : [])}
                  onToggle={(v) => toggleType(i, v)}
                  rowIndex={i}
                />
              </Field>
            </div>

            {suppliers.length > 1 && (
              <button
                type="button"
                onClick={() => removeRow(i)}
                className="mt-3 text-xs text-red-500 hover:text-red-400 flex items-center gap-1"
                data-testid={`remove-supplier-${i}`}
              >
                <Trash2 size={12} /> Remove
              </button>
            )}
          </div>
        ))}
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={addRow}
        className="border-[var(--theme-border)] text-[var(--color-text-muted)] hover:text-white"
        data-testid="add-supplier-btn"
      >
        <Plus size={14} className="mr-1" /> Add another supplier
      </Button>
      <StageFooter
        onSave={onSave}
        onSkip={onSkip}
        saving={saving}
        saveLabel="Save suppliers"
        skipLabel="Skip for now"
        saveTestId="save-suppliers-btn"
      />
    </div>
  );
};

export default StageSuppliers;
