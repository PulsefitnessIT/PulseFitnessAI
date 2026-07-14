import { useState } from 'react';

export function SubTabHub({ items, storageKey }) {
  const [active, setActive] = useState(items[0]?.id);
  const Active = items.find((i) => i.id === active)?.C;
  return (
    <div className="space-y-5" data-testid={`dp-hub-${storageKey}`}>
      <div className="flex flex-wrap gap-1.5 border-b border-slate-200 pb-3">
        {items.map((it) => {
          const Icon = it.icon;
          return (
            <button key={it.id} data-testid={`dp-subtab-${it.id}`} onClick={() => setActive(it.id)}
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-colors ${active === it.id ? 'bg-[var(--gx-brand-from)] text-white' : 'text-slate-500 hover:bg-slate-100'}`}>
              {Icon && <Icon size={14} />} {it.label}
            </button>
          );
        })}
      </div>
      {Active ? <Active /> : null}
    </div>
  );
}
