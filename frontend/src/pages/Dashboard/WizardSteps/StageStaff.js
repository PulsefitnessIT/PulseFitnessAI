import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Plus, Trash2 } from 'lucide-react';
import { StageIntro, StageFooter } from './SharedBits';

export const STAFF_ROLES = [
  { value: 'manager', label: 'Manager', hint: 'Can invite staff, manage equipment & run reports' },
  { value: 'staff',   label: 'Staff',   hint: 'Can log faults, run check sheets & view dashboards' },
];

const StageStaff = ({ invites, addRow, removeRow, updateRow, onSave, onSkip, saving, alreadyDone }) => (
  <div className="space-y-5" data-testid="stage-staff">
    <StageIntro title="Invite your team" blurb="Add your managers and floor staff — they'll receive an email to join your GymAxis Operations Portal."
      badge="Stage 3 / 4" alreadyDone={alreadyDone} />
    <div className="space-y-3">
      {invites.map((s, i) => (
        <div key={i} className="bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg p-4" data-testid={`staff-row-${i}`}>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <Input value={s.full_name} onChange={e => updateRow(i, 'full_name', e.target.value)} placeholder="Full name" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-sm" data-testid={`staff-name-${i}`} />
            <Input type="email" value={s.email} onChange={e => updateRow(i, 'email', e.target.value)} placeholder="email@gym.com *" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-sm" data-testid={`staff-email-${i}`} />
            <Select value={s.role} onValueChange={v => updateRow(i, 'role', v)}>
              <SelectTrigger className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-sm" data-testid={`staff-role-${i}`}><SelectValue /></SelectTrigger>
              <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]">
                {STAFF_ROLES.map(r => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <p className="text-[10px] text-[var(--color-text-muted)] mt-2">
            {STAFF_ROLES.find(r => r.value === s.role)?.hint}
          </p>
          {invites.length > 1 && (
            <button type="button" onClick={() => removeRow(i)} className="mt-1 text-xs text-red-400 flex items-center gap-1" data-testid={`remove-staff-${i}`}>
              <Trash2 size={12} /> Remove
            </button>
          )}
        </div>
      ))}
    </div>
    <Button type="button" variant="outline" size="sm" onClick={addRow} className="border-[var(--theme-border)] text-[var(--color-text-muted)] hover:text-white" data-testid="add-staff-btn">
      <Plus size={14} className="mr-1" /> Invite another teammate
    </Button>
    <StageFooter onSave={onSave} onSkip={onSkip} saving={saving} saveLabel="Send invites" skipLabel="I'll add them later" saveTestId="save-staff-btn" />
  </div>
);

export default StageStaff;
