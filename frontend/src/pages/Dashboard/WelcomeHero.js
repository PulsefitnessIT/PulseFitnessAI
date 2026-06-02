import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Sparkles, ArrowRight, X, CheckCircle2 } from 'lucide-react';

/**
 * Welcome hero banner shown on the GymAxis Service Portal dashboard for users
 * who haven't completed all 4 onboarding stages and haven't dismissed the banner.
 * Deliberately unobtrusive but clearly actionable — opens GamifiedOnboarding.
 */
const WelcomeHero = ({ gymName, status, onStart, onDismiss }) => {
 if (!status) return null;
 const percent = status.percent || 0;
 const completedCount = status.completed_count || 0;
 const totalCount = status.total_count || 4;

 return (
 <Card
 className="relative overflow-hidden bg-gradient-to-br from-[rgb(var(--rgb-brand-blue)/0.08)] via-[var(--theme-surface)] to-[rgb(var(--rgb-brand-blue)/0.03)] border-[rgb(var(--rgb-brand-blue)/0.25)] p-6 mb-6"
 data-testid="welcome-hero-card"
 >
 {/* Dismiss button */}
 <button
 type="button"
 onClick={onDismiss}
 className="absolute top-3 right-3 text-[var(--color-text-muted)] hover:text-[var(--theme-text)] transition-colors"
 aria-label="Dismiss"
 data-testid="welcome-hero-dismiss"
 >
 <X size={16} />
 </button>

 <div className="flex flex-col md:flex-row md:items-center gap-5">
 <div className="flex items-start gap-3 flex-1 min-w-0">
 <div className="w-11 h-11 rounded-lg bg-[rgb(var(--rgb-brand-blue)/0.2)] flex items-center justify-center flex-shrink-0">
 <Sparkles size={22} className="text-[var(--color-brand-blue)]" />
 </div>
 <div className="min-w-0">
 <h3 className="text-lg font-semibold text-white tracking-tight">
 Welcome to GymAxis, {gymName} <span className="inline-block">👋</span>
 </h3>
 <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
 Let&apos;s get your gym fully set up — takes about 5 minutes.
 </p>

 {/* Inline checklist */}
 <div className="flex flex-wrap gap-2 mt-3" data-testid="welcome-hero-checklist">
 {[
 { id: 'suppliers', label: 'Suppliers' },
 { id: 'equipment', label: 'Equipment' },
 { id: 'staff', label: 'Team' },
 { id: 'live', label: 'Go Live' },
 ].map(s => {
 const done = status.stages?.[s.id];
 return (
 <span
 key={s.id}
 className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] ${
 done ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300' : 'bg-[var(--theme-bg)] text-[var(--color-text-muted)] border border-[var(--theme-border)]'
 }`}
 data-testid={`welcome-check-${s.id}`}
 >
 {done ? <CheckCircle2 size={11} /> : <span className="w-2 h-2 rounded-full border border-[var(--theme-border)] inline-block" />}
 {s.label}
 </span>
 );
 })}
 </div>

 {/* Progress */}
 <div className="mt-3 max-w-md">
 <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mb-1">
 <span>Setup progress</span>
 <span className="text-[var(--theme-text)] font-medium">{percent}% · {completedCount} of {totalCount}</span>
 </div>
 <div className="h-1.5 rounded-full bg-[var(--theme-border)] overflow-hidden">
 <div
 className="h-full rounded-full bg-gradient-to-r from-[var(--color-brand-blue)] to-[var(--color-accent-violet)] transition-all duration-700"
 style={{ width: `${percent}%` }}
 data-testid="welcome-hero-progress"
 />
 </div>
 </div>
 </div>
 </div>

 <Button onClick={onStart} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white flex-shrink-0" data-testid="welcome-hero-start-btn">
 {percent > 0 ? 'Resume setup' : 'Start setup'} <ArrowRight size={14} className="ml-1" />
 </Button>
 </div>
 </Card>
 );
};

export default WelcomeHero;
