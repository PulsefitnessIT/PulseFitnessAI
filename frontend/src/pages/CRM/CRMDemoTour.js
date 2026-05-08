import React, { useState } from 'react';
import { Users, Building2, GitBranch, Sparkles, Inbox, Zap, FileText, LayoutDashboard, ArrowRight, ArrowLeft, X, CheckCircle, Rocket } from 'lucide-react';

const TOUR_STEPS = [
  {
    icon: Rocket, title: 'Welcome to GymAxis CRM',
    desc: 'Your all-in-one platform for managing contacts, deals, and growing your business. Let us show you around.',
    tip: 'This quick tour takes about 60 seconds.',
    navTo: null,
  },
  {
    icon: LayoutDashboard, title: 'Dashboard',
    desc: 'Your command centre. See pipeline value, deal stages, win rates, and recent activity at a glance.',
    tip: 'The dashboard updates in real-time as you add contacts and deals.',
    navTo: 'dashboard',
  },
  {
    icon: Users, title: 'Contacts',
    desc: 'Add and manage your contacts. Track every interaction, tag them by stage, and import from CSV.',
    tip: 'Start by adding your first contact — even just a name and email.',
    navTo: 'contacts',
  },
  {
    icon: Building2, title: 'Companies',
    desc: 'Group contacts under companies. Track company size, industry, and link deals to the right account.',
    tip: 'Contacts can be linked to companies for better organisation.',
    navTo: 'companies',
  },
  {
    icon: GitBranch, title: 'Pipeline',
    desc: 'Drag deals between stages. Customise your pipeline to match your sales process.',
    tip: 'Create your first deal and drag it through the stages as it progresses.',
    navTo: 'pipeline',
  },
  {
    icon: Inbox, title: 'Inbox',
    desc: 'Manage conversations with your contacts. Reply to emails and keep a full communication history.',
    tip: 'All contact interactions are logged automatically.',
    navTo: 'inbox',
  },
  {
    icon: Zap, title: 'Workflows',
    desc: 'Automate repetitive tasks. Set triggers for follow-ups, notifications, and deal stage changes.',
    tip: 'Available on Professional and Enterprise plans.',
    navTo: 'workflows',
  },
  {
    icon: FileText, title: 'Quotes & Proposals',
    desc: 'Create professional quotes, add line items, and send directly to your contacts.',
    tip: 'Quotes auto-calculate totals and can include Stripe payment links.',
    navTo: 'quotes',
  },
  {
    icon: Sparkles, title: 'AI Tools',
    desc: 'Get AI-powered contact scoring, deal predictions, email drafts, and duplicate detection.',
    tip: 'AI learns from your data to give better suggestions over time.',
    navTo: 'ai-tools',
  },
  {
    icon: CheckCircle, title: "You're all set!",
    desc: 'Start by adding your first contact or importing from a CSV. Your CRM is ready to help you close more deals.',
    tip: 'You can replay this tour anytime from Settings.',
    navTo: null,
  },
];

export default function CRMDemoTour({ onClose, onNavigate }) {
  const [step, setStep] = useState(0);
  const current = TOUR_STEPS[step];
  const Icon = current.icon;
  const isLast = step === TOUR_STEPS.length - 1;
  const isFirst = step === 0;

  const next = () => {
    if (isLast) { onClose(); return; }
    const nextStep = TOUR_STEPS[step + 1];
    if (nextStep.navTo && onNavigate) onNavigate(nextStep.navTo);
    setStep(step + 1);
  };

  const prev = () => {
    if (isFirst) return;
    const prevStep = TOUR_STEPS[step - 1];
    if (prevStep.navTo && onNavigate) onNavigate(prevStep.navTo);
    setStep(step - 1);
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center" data-testid="crm-demo-tour">
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Tour card */}
      <div className="relative w-full sm:max-w-md mx-auto bg-[var(--color-neutral-900)] border border-[var(--color-surface-dark-3)] rounded-t-2xl sm:rounded-2xl shadow-2xl overflow-hidden" data-testid="tour-card">
        {/* Progress bar */}
        <div className="flex gap-1 px-4 pt-4">
          {TOUR_STEPS.map((_, i) => (
            <div key={i} className="flex-1 h-1 rounded-full transition-all duration-300" style={{ background: i <= step ? 'var(--color-info-ios)' : 'var(--color-surface-dark-3)' }} />
          ))}
        </div>

        {/* Close */}
        <button onClick={onClose} className="absolute top-4 right-4 text-[var(--color-neutral-600)] hover:text-white transition-colors" data-testid="tour-close">
          <X size={18} />
        </button>

        {/* Content */}
        <div className="px-6 pt-6 pb-4">
          <div className="w-14 h-14 rounded-2xl bg-[rgb(var(--rgb-info-ios)/0.1)] flex items-center justify-center mb-4">
            <Icon size={28} className="text-[var(--color-info-ios)]" />
          </div>
          <h3 className="text-xl font-semibold text-white mb-2" style={{ fontFamily: 'Outfit, sans-serif' }}>
            {current.title}
          </h3>
          <p className="text-[var(--color-neutral-400)] text-sm leading-relaxed mb-3">
            {current.desc}
          </p>
          <div className="bg-[rgb(var(--rgb-info-ios)/0.05)] border border-[rgb(var(--rgb-info-ios)/0.2)] rounded-lg px-3 py-2">
            <p className="text-[var(--color-info-ios)] text-xs font-medium">{current.tip}</p>
          </div>
        </div>

        {/* Navigation */}
        <div className="px-6 pb-6 flex items-center justify-between">
          <div className="text-xs text-[var(--color-neutral-600)]">{step + 1} of {TOUR_STEPS.length}</div>
          <div className="flex gap-2">
            {!isFirst && (
              <button onClick={prev} className="px-4 py-2 text-sm font-medium text-[var(--color-neutral-400)] hover:text-white transition-colors flex items-center gap-1" data-testid="tour-prev">
                <ArrowLeft size={14} /> Back
              </button>
            )}
            <button onClick={next} className="px-5 py-2 bg-[var(--color-info-ios)] hover:bg-[var(--color-brand-blue-deep)] text-white text-sm font-medium rounded-lg flex items-center gap-1.5 transition-all" data-testid="tour-next">
              {isLast ? 'Get Started' : 'Next'} {!isLast && <ArrowRight size={14} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
