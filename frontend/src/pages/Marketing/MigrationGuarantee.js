/**
 * Migration Guarantee badge — Iter 216ba.
 *
 * Compact reusable callout used on /pricing and /compare pages.
 * Reduces switching friction by promising free migration + a refund
 * window if it doesn't go smoothly.
 */
import { ShieldCheck, ArrowRight, Clock, Database, BadgeCheck } from 'lucide-react';
import { openTrial } from './TrialSignupModal';

export default function MigrationGuarantee() {
  return (
    <section className="py-12 sm:py-16" data-testid="gx-migration-guarantee">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="rounded-3xl border border-emerald-200 bg-gradient-to-br from-emerald-50 via-white to-white p-6 sm:p-10">
          <div className="grid lg:grid-cols-3 gap-8 items-center">
            <div className="lg:col-span-2">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-emerald-700">
                <ShieldCheck size={11} /> Switching guarantee
              </span>
              <h2 className="mt-3 text-3xl sm:text-4xl font-black tracking-tighter text-slate-900">
                Switch in 14 days — or your money back.
              </h2>
              <p className="mt-3 text-base text-slate-600 max-w-2xl">
                We'll import your members, classes and contacts from MindBody, Glofox, ClubReady, RotaCloud, Mailchimp or your spreadsheets — free of charge. If you're not fully migrated within 14 days, we'll refund your first month and you keep the data.
              </p>
              <div className="mt-5 grid sm:grid-cols-3 gap-3">
                <Pill icon={Database} text="Free data import" />
                <Pill icon={Clock} text="14-day promise" />
                <Pill icon={BadgeCheck} text="No long-term contract" />
              </div>
            </div>
            <div className="text-center lg:text-right">
              <button type="button" onClick={openTrial}
                className="inline-flex items-center gap-1.5 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm px-6 py-3"
                data-testid="gx-migration-cta">
                Start switching <ArrowRight size={14} />
              </button>
              <p className="mt-2 text-[11px] text-slate-500">Real humans · UK working hours · no scripted reps</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Pill({ icon: Icon, text }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-xl bg-white border border-emerald-200/60 px-3 py-2 text-xs font-semibold text-emerald-800">
      <Icon size={13} className="text-emerald-600" /> {text}
    </div>
  );
}
