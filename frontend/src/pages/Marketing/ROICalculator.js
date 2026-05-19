/**
 * ROI Calculator — Iter 216ba.
 *
 * Self-serve "what would I save by switching to GymAxis?" widget for
 * the /pricing page. 4 inputs (sites, current spend, hours/week wasted,
 * member count), 3 outputs (annual savings, payback months, time
 * reclaimed). Pure client-side; no API calls.
 */
import { useMemo, useState } from 'react';
import { TrendingUp, Clock, PoundSterling, Calculator, ArrowRight } from 'lucide-react';
import { openTrial } from './TrialSignupModal';

// Industry-baseline assumptions surfaced under each input as
// "How we got there" tooltips so the buyer trusts the math.
const ASSUMPTIONS = {
  hourlyValue: 22,                          // £22/h fully-loaded UK ops manager rate
  efficiencyGain: 0.65,                     // GymAxis recovers 65% of admin time
  retentionLift: 0.06,                      // 6% lower churn after switching
  avgRevenuePerMember: 38,                  // £38/mo average for UK gym member
};

export default function ROICalculator() {
  const [sites, setSites] = useState(1);
  const [currentSpend, setCurrentSpend] = useState(220);   // £/mo across all current tools
  const [hoursWasted, setHoursWasted] = useState(8);       // h/week on tool-juggling/admin
  const [members, setMembers] = useState(400);

  const { gymaxisCost, toolSavings, timeSavings, retentionLift, totalAnnual, paybackMonths } = useMemo(() => {
    const gymaxisCost = 150 + Math.max(0, sites - 1) * 50;
    const toolSavings = Math.max(0, currentSpend - gymaxisCost);
    const hoursReclaimedPerWeek = hoursWasted * ASSUMPTIONS.efficiencyGain;
    const timeSavings = hoursReclaimedPerWeek * 4.33 * ASSUMPTIONS.hourlyValue;       // £/mo
    const retentionLift = members * ASSUMPTIONS.retentionLift * ASSUMPTIONS.avgRevenuePerMember;
    const monthlyTotal = toolSavings + timeSavings + retentionLift;
    const totalAnnual = monthlyTotal * 12;
    const paybackMonths = monthlyTotal > 0 ? Math.max(0.5, gymaxisCost / monthlyTotal) : null;
    return { gymaxisCost, toolSavings, timeSavings, retentionLift, totalAnnual, paybackMonths };
  }, [sites, currentSpend, hoursWasted, members]);

  return (
    <section className="py-12 sm:py-16 bg-white border-y border-slate-200/60 dark:bg-zinc-900" data-testid="gx-roi-calculator">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-2xl mx-auto mb-10">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
            <Calculator size={11} className="text-[var(--gx-brand-from)]" /> Show me the math
          </span>
          <h2 className="mt-3 text-3xl sm:text-4xl font-black tracking-tighter text-slate-900 dark:text-zinc-100">
            How much will GymAxis save you?
          </h2>
          <p className="mt-3 text-base text-slate-600">
            4 sliders, no email, no signup. Tell us where you are today — see what year-one looks like with GymAxis.
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-8 items-stretch">
          {/* Inputs */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/30 p-6 space-y-6 dark:border-zinc-800" data-testid="gx-roi-inputs">
            <Slider
              label="Sites" value={sites} setValue={setSites} min={1} max={20} step={1}
              suffix={sites === 1 ? 'site' : 'sites'}
              hint="Each location you operate."
              testId="gx-roi-sites"
            />
            <Slider
              label="Current monthly spend on software" value={currentSpend} setValue={setCurrentSpend} min={0} max={1000} step={10}
              prefix="£" suffix="/mo"
              hint="Sum of MindBody / Glofox / Mailchimp / RotaCloud / spreadsheets / asset trackers."
              testId="gx-roi-spend"
            />
            <Slider
              label="Hours wasted per week on admin" value={hoursWasted} setValue={setHoursWasted} min={0} max={40} step={1}
              suffix={hoursWasted === 1 ? 'hour' : 'hours'}
              hint="Copy-paste between tools, manual reports, chasing late payers."
              testId="gx-roi-hours"
            />
            <Slider
              label="Members across all sites" value={members} setValue={setMembers} min={50} max={5000} step={50}
              hint="Used to estimate retention lift (6% lower churn typical for switchers)."
              testId="gx-roi-members"
            />
          </div>

          {/* Output */}
          <div className="rounded-2xl bg-gradient-to-br from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] p-1 shadow-[0_24px_60px_-20px_rgba(91,91,245,0.55)]">
            <div className="rounded-[15px] bg-white p-6 sm:p-8 h-full flex flex-col dark:bg-zinc-900" data-testid="gx-roi-output">
              <p className="text-[11px] uppercase tracking-[0.18em] font-bold text-slate-500">Year-one projection</p>
              <p className="mt-2 text-5xl sm:text-6xl font-black tracking-tighter gx-gradient-text" data-testid="gx-roi-annual-total">
                £{Math.round(totalAnnual).toLocaleString('en-GB')}
              </p>
              <p className="mt-1 text-sm text-slate-500">total benefit over 12 months</p>

              <div className="mt-6 space-y-3 border-t border-slate-100 pt-5 dark:border-zinc-800">
                <Line icon={PoundSterling}  label="Tool consolidation savings"  value={toolSavings * 12}  testId="gx-roi-tool-savings" />
                <Line icon={Clock}          label="Time reclaimed (admin recovery)" value={timeSavings * 12} testId="gx-roi-time-savings" />
                <Line icon={TrendingUp}     label="Retention lift (6% lower churn)" value={retentionLift * 12} testId="gx-roi-retention" />
              </div>

              <div className="mt-5 flex items-center justify-between rounded-xl bg-slate-50 p-3 text-xs dark:bg-zinc-900">
                <span className="text-slate-600">GymAxis Pro · {sites} {sites === 1 ? 'site' : 'sites'}</span>
                <span className="font-bold text-slate-900 dark:text-zinc-100">£{gymaxisCost}/mo</span>
              </div>

              {paybackMonths !== null && (
                <p className="mt-3 text-sm text-slate-700" data-testid="gx-roi-payback">
                  Payback period: <span className="font-bold">{paybackMonths < 1 ? '<1' : paybackMonths.toFixed(1)} {paybackMonths < 1.5 ? 'month' : 'months'}</span>
                </p>
              )}

              <button type="button" onClick={openTrial}
                className="gx-cta mt-6 w-full inline-flex items-center justify-center gap-1.5 rounded-full px-5 py-3 text-sm font-bold"
                data-testid="gx-roi-cta">
                Start Free Trial <ArrowRight size={14} />
              </button>
              <p className="mt-2 text-[11px] text-center text-slate-500">3-day trial · all modules · no credit card</p>
            </div>
          </div>
        </div>

        <p className="mt-6 text-center text-[11px] text-slate-400">
          Estimates use industry-baseline assumptions: £22/h fully-loaded ops time, 65% admin-time recovery, 6% churn reduction, £38/mo ARPU. Adjust the sliders to your reality.
        </p>
      </div>
    </section>
  );
}

function Slider({ label, value, setValue, min, max, step, prefix, suffix, hint, testId }) {
  return (
    <div data-testid={testId}>
      <div className="flex items-baseline justify-between mb-1.5">
        <label className="text-sm font-bold text-slate-900 dark:text-zinc-100">{label}</label>
        <span className="text-base font-black tracking-tight text-slate-900 tabular-nums dark:text-zinc-100">
          {prefix}{value.toLocaleString('en-GB')}{suffix && ` ${suffix}`}
        </span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => setValue(parseFloat(e.target.value))}
        className="w-full h-2 rounded-full bg-slate-200 appearance-none cursor-pointer accent-[var(--gx-brand-to)]"
        data-testid={`${testId}-input`}
      />
      <p className="mt-1 text-[11px] text-slate-500">{hint}</p>
    </div>
  );
}

function Line({ icon: Icon, label, value, testId }) {
  return (
    <div className="flex items-center gap-3" data-testid={testId}>
      <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center text-slate-700 shrink-0 dark:bg-zinc-800">
        <Icon size={14} />
      </div>
      <span className="text-sm text-slate-700 flex-1">{label}</span>
      <span className="text-sm font-bold text-slate-900 tabular-nums dark:text-zinc-100">£{Math.round(value).toLocaleString('en-GB')}</span>
    </div>
  );
}
