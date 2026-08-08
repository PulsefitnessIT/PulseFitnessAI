import { ONSETS, USABLE, SAFE } from './wizardConfig';
import { StepTitle, RadioGroup } from './WizardPrimitives';

export function StepGuided({ data, patch, machineName }) {
  return (
    <div className="space-y-5" data-testid="mod-step-guided">
      <StepTitle eyebrow="Fault details" title="Tell us more" subtitle={machineName ? `${machineName} · ≥ 40 characters so the engineer can prep` : '≥ 40 characters so the engineer can prep before arrival'} />
      <label className="block">
        <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Description *</span>
        <textarea
          value={data.description}
          onChange={(e) => patch('description', e.target.value)}
          rows={4}
          placeholder="e.g. belt slipping when incline > 5% under heavy user. Started making a clicking noise yesterday."
          className="mt-1 w-full rounded-lg border px-3 py-2.5 text-sm focus:outline-none focus:border-[var(--color-brand-cyan)]"
          style={{ background: 'var(--theme-surface-2)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
          data-testid="mod-field-description"
        />
        <div className="flex items-center justify-between mt-1 gap-3">
          <div className={`text-[10px] font-bold ${data.description.length >= 40 ? 'text-emerald-500 dark:text-emerald-400' : ''}`} style={data.description.length >= 40 ? {} : { color: 'var(--theme-text-muted)' }}>
            {data.description.length} / 40 minimum
          </div>
          <div className="text-[10px] text-amber-600 dark:text-amber-300/90 font-semibold" data-testid="mod-field-classification-hint">
            ◆ OFFICIAL-SENSITIVE ceiling — do NOT include NSN, operation names, callsigns, personal data or anything above OFFICIAL-SENSITIVE.
          </div>
        </div>
      </label>

      <RadioGroup label="When did it start? *" options={ONSETS} value={data.onset} onChange={(v) => patch('onset', v)} testidPrefix="mod-field-onset" />
      <RadioGroup label="Is it usable? *" options={USABLE} value={data.usable} onChange={(v) => patch('usable', v)} testidPrefix="mod-field-usable" withHelp />
      <RadioGroup label="Is it safe to leave in service? *" options={SAFE} value={data.safe_in_service} onChange={(v) => patch('safe_in_service', v)} testidPrefix="mod-field-safe" alert={data.safe_in_service === 'no'} />
      {data.safe_in_service === 'no' && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-600 dark:text-red-200 font-medium">
          ⚠ This machine will be auto-isolated and flagged URGENT. The on-call engineer will be paged.
        </div>
      )}
    </div>
  );
}
