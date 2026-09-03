import { FAULT_TYPES } from './wizardConfig';
import { StepTitle } from './WizardPrimitives';

export function StepFaultType({ selected, onPick, machineName, machineIndex, machineTotal, error }) {
  return (
    <div data-testid="mod-step-fault-type">
      <StepTitle
        eyebrow={machineTotal > 1 ? `Machine ${machineIndex + 1} of ${machineTotal}` : 'Step 2'}
        title="What's wrong?"
        subtitle={machineName ? `With ${machineName}` : undefined}
      />
      {error && <div className="mb-2 text-[11px] font-bold text-red-500" data-testid="mod-fault-type-error">Pick a fault type to continue.</div>}
      <div className={`grid grid-cols-2 gap-2.5 ${error ? 'rounded-xl ring-1 ring-red-500/50 p-1 -m-1' : ''}`} role="radiogroup" aria-label="Fault type">
        {FAULT_TYPES.map((t) => {
          const picked = t.id === selected;
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              type="button"
              role="radio"
              aria-checked={picked}
              onClick={() => onPick(t.id)}
              className={`rounded-xl border p-4 flex flex-col items-center gap-2 transition-all ${picked ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.12)]' : 'hover:border-[var(--color-brand-cyan)]'}`}
              style={picked ? {} : { background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }}
              data-testid={`mod-fault-type-${t.id}`}
            >
              <Icon size={26} className={picked ? 'text-[var(--color-brand-cyan)]' : ''} style={picked ? {} : { color: 'var(--theme-text-muted)' }} />
              <div className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{t.label}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
