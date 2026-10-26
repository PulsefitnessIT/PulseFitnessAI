import React, { useState } from 'react';
import { Search, X } from 'lucide-react';

// Searchable multi-select of every MOD site an engineer can be allocated to.
export const EngineerSitePicker = ({ sites, value = [], onChange, testid }) => {
  const [q, setQ] = useState('');
  const term = q.trim().toLowerCase();
  const shown = sites.filter((s) => !term || `${s.name} ${s.country || ''}`.toLowerCase().includes(term));
  const byId = Object.fromEntries(sites.map((s) => [s.id, s]));
  const toggle = (id, on) => onChange(on ? [...value, id] : value.filter((x) => x !== id));

  return (
    <div className="rounded-lg bg-cyan-50/40 border border-cyan-100 p-3 space-y-2" data-testid={testid}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Sites covered ({value.length})</span>
        {value.length > 0 && <button type="button" onClick={() => onChange([])} className="text-[11px] text-slate-500 hover:text-red-600" data-testid={`${testid}-clear`}>Clear</button>}
      </div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5" data-testid={`${testid}-selected`}>
          {value.map((id) => (
            <span key={id} className="inline-flex items-center gap-1 text-[12px] px-2 py-0.5 rounded-full bg-white border border-cyan-200 text-cyan-800">
              {byId[id]?.name || id}
              <button type="button" onClick={() => toggle(id, false)} className="text-cyan-500 hover:text-red-600" data-testid={`${testid}-remove-${id}`}><X size={11} /></button>
            </span>
          ))}
        </div>
      )}
      <div className="relative">
        <Search size={13} className="absolute left-2.5 top-2.5 text-slate-400" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search sites or country"
          className="w-full h-8 rounded-md border border-slate-200 bg-white pl-8 pr-2 text-[13px] focus:outline-none focus:ring-2 focus:ring-cyan-400" data-testid={`${testid}-search`} />
      </div>
      <div className="max-h-44 overflow-auto rounded-lg border border-slate-200 bg-white p-2 space-y-1">
        {sites.length === 0 && <p className="text-[11px] text-slate-400" data-testid={`${testid}-empty`}>No MOD sites set up yet — add them under MOD onboarding.</p>}
        {sites.length > 0 && shown.length === 0 && <p className="text-[11px] text-slate-400">No sites match.</p>}
        {shown.map((s) => (
          <label key={s.id} className="flex items-center gap-2 text-[13px] text-slate-700 cursor-pointer">
            <input type="checkbox" checked={value.includes(s.id)} className="accent-cyan-500" onChange={(ev) => toggle(s.id, ev.target.checked)} data-testid={`${testid}-site-${s.id}`} />
            <span className="flex-1 truncate">{s.name}</span>
            {s.country && <span className="text-[10px] text-slate-400">{s.country}</span>}
          </label>
        ))}
      </div>
    </div>
  );
};
