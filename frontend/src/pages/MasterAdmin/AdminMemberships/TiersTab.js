import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Crown, Check, X } from 'lucide-react';
import { SectionCard, Pill } from './shared';

const TiersTab = ({ tierMatrix, onSave }) => {
 const [draft, setDraft] = useState(null);
 useEffect(() => { if (tierMatrix) setDraft(JSON.parse(JSON.stringify(tierMatrix.matrix))); }, [tierMatrix]);

 if (!tierMatrix || !draft) return null;

 const keys = Array.from(new Set([...Object.keys(draft.lite || {}), ...Object.keys(draft.pro || {})]));

 return (
 <div className="space-y-4" data-testid="memberships-admin-tiers">
 <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
 <SectionCard title="Lite tier">
 <p className="text-3xl font-semibold text-zinc-900">{tierMatrix.counts.lite}</p>
 <p className="text-xs text-zinc-500">organisations on Lite</p>
 </SectionCard>
 <SectionCard title="Pro tier">
 <div className="flex items-center gap-2">
 <Crown className="text-amber-500" size={24} />
 <p className="text-3xl font-semibold text-zinc-900">{tierMatrix.counts.pro}</p>
 </div>
 <p className="text-xs text-zinc-500">organisations on Pro</p>
 </SectionCard>
 </div>

 <SectionCard
 title="Feature matrix — Lite vs Pro"
 action={
 <Button size="sm" className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)]" onClick={() => onSave(draft)} data-testid="save-tier-matrix">
 Save matrix
 </Button>
 }
 >
 <div className="overflow-x-auto">
 <table className="w-full text-sm">
 <thead>
 <tr className="text-[11px] uppercase tracking-wider text-zinc-400 border-b border-zinc-100">
 <th className="text-left px-3 py-2 font-semibold">Feature</th>
 <th className="px-3 py-2 font-semibold">Lite</th>
 <th className="px-3 py-2 font-semibold">Pro</th>
 </tr>
 </thead>
 <tbody>
 {keys.map((k) => (
 <tr key={k} className="border-b border-zinc-50">
 <td className="px-3 py-2 text-zinc-700 font-mono text-xs">{k.replace(/_/g, ' ')}</td>
 <td className="px-3 py-2 text-center">
 <Switch
 checked={!!draft.lite?.[k]}
 onCheckedChange={(v) => setDraft({ ...draft, lite: { ...draft.lite, [k]: v } })}
 data-testid={`tier-lite-${k}`}
 />
 </td>
 <td className="px-3 py-2 text-center">
 <Switch
 checked={!!draft.pro?.[k]}
 onCheckedChange={(v) => setDraft({ ...draft, pro: { ...draft.pro, [k]: v } })}
 data-testid={`tier-pro-${k}`}
 />
 </td>
 </tr>
 ))}
 </tbody>
 </table>
 </div>
 </SectionCard>

 <SectionCard title="Pro-tier organisations">
 {tierMatrix.pro_orgs.length === 0 ? (
 <p className="text-sm text-zinc-400">No organisations on Pro yet — drive upgrades from the Organisations tab.</p>
 ) : (
 <div className="flex flex-wrap gap-2">
 {tierMatrix.pro_orgs.map((o) => (
 <Pill key={o.id} tone="violet"><Crown size={10} className="mr-1" /> {o.name}</Pill>
 ))}
 </div>
 )}
 </SectionCard>
 </div>
 );
};

export default TiersTab;
