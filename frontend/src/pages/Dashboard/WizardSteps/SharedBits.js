import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { CheckCircle2, ArrowRight, Loader2 } from 'lucide-react';

/** Small reusable building blocks shared across all 4 onboarding stages. */

export const StageIntro = ({ title, blurb, badge, alreadyDone }) => (
  <div>
    <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)] border-transparent mb-2">{badge}</Badge>
    <h3 className="text-xl font-semibold flex items-center gap-2">
      {title}
      {alreadyDone && <CheckCircle2 size={18} className="text-emerald-400" />}
    </h3>
    <p className="text-sm text-[var(--color-text-muted)] mt-1">{blurb}</p>
    {alreadyDone && (
      <p className="text-xs text-emerald-300 mt-1">✓ You&apos;ve already completed this stage — adding more is optional.</p>
    )}
  </div>
);

export const StageFooter = ({ onSave, onSkip, saving, saveLabel, skipLabel, saveTestId }) => (
  <div className="flex items-center justify-between pt-4 border-t border-[var(--theme-border)]">
    <Button type="button" variant="ghost" onClick={onSkip} className="text-[var(--color-text-muted)] hover:text-white" data-testid="skip-stage-btn">
      {skipLabel}
    </Button>
    {onSave && (
      <Button type="button" onClick={onSave} disabled={saving} className="bg-[var(--color-brand-blue)] text-white" data-testid={saveTestId}>
        {saving ? <><Loader2 size={14} className="mr-2 animate-spin" /> Saving...</> : <>{saveLabel} <ArrowRight size={14} className="ml-2" /></>}
      </Button>
    )}
  </div>
);

export const Field = ({ label, required, children }) => (
  <div>
    <Label className="text-[11px] text-[var(--color-text-muted)] mb-1 block">
      {label} {required && <span className="text-red-400">*</span>}
    </Label>
    {children}
  </div>
);

export const SummaryStat = ({ icon: Icon, value, label, testid }) => (
  <div className="bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg p-3" data-testid={testid}>
    <Icon size={16} className="text-[var(--color-brand-blue)] mx-auto mb-1" />
    <div className="text-2xl font-bold text-white">{value}</div>
    <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider">{label}</div>
  </div>
);
