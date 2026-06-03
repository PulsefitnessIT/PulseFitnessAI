/**
 * MemberAppTab — Iter 220n
 *
 * Unifies the member-facing experience under one tab: the mobile App Builder
 * and the Parent portal controls (they naturally belong together).
 */
import { useState } from 'react';
import { Smartphone, ShieldCheck } from 'lucide-react';
import MobileAppBuilderTab from '@/pages/Memberships/MobileAppBuilderTab';
import ParentPortalTab from '@/pages/Memberships/ParentPortalTab';

const SUBTABS = [
  { id: 'builder', label: 'App Builder', icon: Smartphone },
  { id: 'parent-portal', label: 'Parent portal', icon: ShieldCheck },
];

export default function MemberAppTab({ API, headers }) {
  const [sub, setSub] = useState('builder');
  return (
    <div className="space-y-4" data-testid="mbr-member-app">
      <div className="flex flex-wrap gap-2">
        {SUBTABS.map((s) => {
          const Icon = s.icon;
          const active = sub === s.id;
          return (
            <button
              key={s.id}
              onClick={() => setSub(s.id)}
              data-testid={`mbr-member-app-tab-${s.id}`}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-colors"
              style={active
                ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
                : { background: 'var(--theme-surface)', color: 'var(--theme-text-muted)', border: '1px solid var(--theme-border)' }}
            >
              <Icon className="w-3.5 h-3.5" /> {s.label}
            </button>
          );
        })}
      </div>
      {sub === 'builder' && <MobileAppBuilderTab API={API} headers={headers} />}
      {sub === 'parent-portal' && <ParentPortalTab API={API} headers={headers} />}
    </div>
  );
}
