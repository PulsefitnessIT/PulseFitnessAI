import { FAULT_TYPES, ONSETS, USABLE, SAFE } from './wizardConfig';
import { StepTitle, ReviewRow } from './WizardPrimitives';

export function StepReview({ selectedIds, machineData, equipById, staff }) {
  return (
    <div className="space-y-3" data-testid="mod-step-review">
      <StepTitle eyebrow="Review" title={`Review & submit ${selectedIds.length > 1 ? `· ${selectedIds.length} tickets` : ''}`} subtitle={selectedIds.length > 1 ? 'Each machine below becomes its own ticket with its own SLA.' : undefined} />

      <div className="rounded-xl border p-4 mb-1" style={{ background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }}>
        <ReviewRow label="Reporter" value={staff ? [staff.name, staff.email, staff.phone].filter(Boolean).join(' · ') : '—'} />
      </div>

      {selectedIds.map((id, idx) => {
        const eq = equipById(id);
        const md = machineData[id] || {};
        return (
          <div key={id} className="rounded-xl border p-4 space-y-2" style={{ background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }} data-testid={`mod-review-machine-${id}`}>
            {selectedIds.length > 1 && (
              <div className="text-[10px] font-extrabold uppercase tracking-wider text-[var(--color-brand-cyan)]">Ticket {idx + 1}</div>
            )}
            <ReviewRow label="Machine" value={`${eq?.name || eq?.serial_number}${eq?.location ? ` · ${eq.location}` : ''}`} />
            <ReviewRow label="Fault type" value={FAULT_TYPES.find((t) => t.id === md.fault_type)?.label} />
            <ReviewRow label="Onset" value={ONSETS.find((t) => t.id === md.onset)?.label} />
            <ReviewRow label="Usable" value={USABLE.find((t) => t.id === md.usable)?.label} />
            <ReviewRow label="Safe in service" value={SAFE.find((t) => t.id === md.safe_in_service)?.label} />
            <ReviewRow label="Photos/videos" value={(md.attachment_urls || []).length ? `${(md.attachment_urls || []).length} attached` : 'None'} />
            <ReviewRow label="Description" value={md.description} multiline />
            {(md.steps_taken || '').trim() && (
              <ReviewRow label="Steps taken to fix" value={md.steps_taken} multiline />
            )}
          </div>
        );
      })}
    </div>
  );
}
