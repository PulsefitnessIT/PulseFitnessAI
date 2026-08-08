import { StepTitle } from './WizardPrimitives';

export function StepReporter({ staff, selected, onPick, onAddNew }) {
  return (
    <div data-testid="mod-step-reporter">
      <StepTitle eyebrow="Reporter" title="Who is reporting this?" subtitle="So our engineer can contact you and resolve faster." />
      <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-3 py-2 mb-3 text-[12px] text-amber-700 dark:text-amber-200 flex items-start gap-2" data-testid="mod-reporter-required-note">
        <span className="font-bold">Required:</span>
        <span>Select (or add) the staff member logging this fault — our service provider will contact them directly. This can't be skipped.</span>
      </div>
      <button
        onClick={onAddNew}
        className="w-full rounded-xl border border-dashed border-[rgb(var(--rgb-brand-cyan)/0.5)] px-3 py-3 text-[var(--color-brand-cyan)] hover:bg-[rgb(var(--rgb-brand-cyan)/0.06)] text-sm font-bold mb-3"
        data-testid="mod-reporter-add-new"
      >+ Add new contact</button>

      {staff.length === 0 ? (
        <div className="text-center py-6 text-sm" style={{ color: 'var(--theme-text-muted)' }}>No staff yet — add one above.</div>
      ) : (
        <div className="space-y-2 max-h-[45vh] overflow-y-auto" role="radiogroup" aria-label="Reporter">
          {staff.map((s) => {
            const picked = s.id === selected?.id;
            return (
              <button
                key={s.id}
                type="button"
                role="radio"
                aria-checked={picked}
                onClick={() => onPick(s)}
                className={`w-full text-left rounded-xl border p-3 transition-all ${picked ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.12)]' : 'hover:border-[var(--color-brand-cyan)]'}`}
                style={picked ? {} : { background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }}
                data-testid={`mod-reporter-${s.id}`}
              >
                <div className="font-bold text-sm" style={{ color: 'var(--theme-text)' }}>{s.name} {s.role && <span className="font-normal" style={{ color: 'var(--theme-text-muted)' }}>· {s.role}</span>}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.email} · {s.phone}</div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
