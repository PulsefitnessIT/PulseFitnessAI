import React from 'react';
import { PULSE_LOGO, ROLE_LABEL, PRIORITY } from '../ui';
import { MapPin, Globe2, ClipboardList, ArrowRight, PartyPopper } from 'lucide-react';

export default function WelcomeKit({ data, onStart, onViewJobs }) {
  const terrs = data.territories || [];
  const sites = data.sites || [];
  const jobs = data.open_jobs || { count: 0, items: [] };
  const firstName = (data.full_name || '').trim().split(' ')[0] || 'there';

  return (
    <div className="fixed inset-0 z-[70] bg-[#F8F9FA] overflow-y-auto" data-testid="bfpo-welcome" style={{ fontFamily: "'Proxima Nova', 'Inter', system-ui, sans-serif" }}>
      <div className="on-dark text-white" style={{ backgroundColor: '#000000' }}>
        <div className="max-w-3xl mx-auto px-4 h-20 flex items-center">
          <img src={PULSE_LOGO} alt="Pulse Fitness" className="h-10 rounded-md object-cover" style={{ objectPosition: 'center', aspectRatio: '3.8/1', clipPath: 'inset(12% 3% 12% 3% round 6px)' }} />
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-8 pb-28">
        <div className="flex items-center gap-2 text-cyan-700 font-semibold text-sm mb-1">
          <PartyPopper className="w-4 h-4" /> Welcome to the team
        </div>
        <h1 className="text-3xl font-bold text-slate-900">Hi {firstName}, you're all set.</h1>
        <p className="text-slate-500 mt-1">{ROLE_LABEL[data.role] || 'MOD / BFPO Engineer'} · here's your patch and what's waiting for you.</p>

        <div className="grid sm:grid-cols-2 gap-4 mt-6">
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5" data-testid="welcome-territories">
            <div className="flex items-center gap-2 text-slate-900 font-semibold mb-3"><Globe2 className="w-4 h-4 text-cyan-600" /> Your territories</div>
            {terrs.length === 0 ? <p className="text-sm text-slate-400">No territories assigned yet — your lead will sort this.</p> : (
              <div className="flex flex-wrap gap-1.5">
                {terrs.map((t) => (
                  <span key={t.id} className="px-3 py-1.5 rounded-full text-xs font-semibold bg-cyan-50 text-cyan-700 border border-cyan-200">{t.name}</span>
                ))}
              </div>
            )}
          </div>

          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5" data-testid="welcome-sites">
            <div className="flex items-center gap-2 text-slate-900 font-semibold mb-3"><MapPin className="w-4 h-4 text-cyan-600" /> Your sites <span className="text-slate-400 font-normal">({sites.length})</span></div>
            {sites.length === 0 ? <p className="text-sm text-slate-400">No sites in scope yet.</p> : (
              <ul className="space-y-1.5 max-h-40 overflow-y-auto">
                {sites.map((s) => (
                  <li key={s.id} className="text-sm text-slate-700 flex items-center justify-between gap-2">
                    <span className="truncate">{s.name}</span>
                    <span className="text-xs text-slate-400 whitespace-nowrap">{s.country || s.territory_name || ''}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5 mt-4" data-testid="welcome-jobs">
          <div className="flex items-center gap-2 text-slate-900 font-semibold mb-3"><ClipboardList className="w-4 h-4 text-cyan-600" /> Open jobs waiting <span className="text-slate-400 font-normal">({jobs.count})</span></div>
          {jobs.count === 0 ? <p className="text-sm text-slate-400">Nothing open right now — you're all caught up.</p> : (
            <div className="space-y-2">
              {jobs.items.map((j) => {
                const cfg = PRIORITY[j.priority] || PRIORITY.p3;
                return (
                  <div key={j.id} className="flex items-center gap-3 border border-slate-100 rounded-xl px-3 py-2" data-testid={`welcome-job-${j.id}`}>
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${cfg.cls}`}>{cfg.label}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-800 truncate">{j.title}</p>
                      <p className="text-xs text-slate-400 truncate">{j.reference} · {j.site_name}</p>
                    </div>
                  </div>
                );
              })}
              {jobs.count > jobs.items.length && <p className="text-xs text-slate-400 pt-1">+ {jobs.count - jobs.items.length} more</p>}
            </div>
          )}
        </div>
      </div>

      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 p-4">
        <div className="max-w-3xl mx-auto flex gap-3">
          <button onClick={onStart} className="flex-1 inline-flex items-center justify-center gap-2 font-semibold rounded-xl px-4 py-3 text-sm border border-slate-300 bg-white hover:bg-slate-50 text-slate-700" data-testid="welcome-start">
            Explore the portal
          </button>
          <button onClick={onViewJobs} className="flex-1 inline-flex items-center justify-center gap-2 font-semibold rounded-xl px-4 py-3 text-sm bg-cyan-600 hover:bg-cyan-700 text-white" data-testid="welcome-view-jobs">
            View my jobs <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
