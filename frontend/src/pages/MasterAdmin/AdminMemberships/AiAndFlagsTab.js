import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Sparkles, Flame, AlertTriangle, Info, FlaskConical } from 'lucide-react';
import { SectionCard, Pill, severityTone } from './shared';

const AiAndFlagsTab = ({ aiInsights, onLoadAiInsights, featureFlags, onSaveFlags, onDrillOrg }) => {
 const [draft, setDraft] = useState(null);
 useEffect(() => { if (featureFlags) setDraft({ ...featureFlags.flags }); }, [featureFlags]);
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
 useEffect(() => { if (!aiInsights) onLoadAiInsights?.();   }, []);

 const insights = aiInsights?.insights || [];
 const betaKeys = draft ? Object.keys(draft).filter((k) => k.startsWith('beta_')) : [];
 const coreKeys = draft ? Object.keys(draft).filter((k) => !k.startsWith('beta_')) : [];

 const iconFor = (sev) => {
 if (sev === 'high') return <Flame size={14} className="text-red-600" />;
 if (sev === 'medium') return <AlertTriangle size={14} className="text-amber-600" />;
 return <Info size={14} className="text-blue-600" />;
 };

 return (
 <div className="space-y-4" data-testid="memberships-admin-ai-flags">
 <SectionCard
 title="AI-prioritised insights"
 action={
 <Button size="sm" variant="outline" className="h-8 text-xs" onClick={onLoadAiInsights} data-testid="refresh-ai-insights">
 <Sparkles size={12} className="mr-1" /> Refresh
 </Button>
 }
 >
 {!aiInsights ? (
 <p className="text-sm text-zinc-400 py-4">Generating insights…</p>
 ) : insights.length === 0 ? (
 <p className="text-sm text-zinc-400 py-4">No insights yet — check back after more activity.</p>
 ) : (
 <div className="space-y-2">
 {insights.map((ins, i) => (
 <button
 key={i}
 onClick={() => ins.org_id && onDrillOrg?.(ins.org_id)}
 className="w-full text-left p-3 border border-zinc-200 rounded-md hover:border-zinc-300 hover:bg-zinc-50/50 transition-colors"
 data-testid={`ai-insight-${i}`}
 >
 <div className="flex items-start justify-between gap-3">
 <div className="flex items-start gap-2 min-w-0">
 {iconFor(ins.severity)}
 <div className="min-w-0">
 <div className="flex items-center gap-2">
 <p className="text-sm font-medium text-zinc-900">{ins.title}</p>
 <Pill tone={severityTone(ins.severity)}>{ins.severity}</Pill>
 </div>
 <p className="text-xs text-zinc-600 mt-1">{ins.detail}</p>
 {ins.action && (
 <p className="text-[11px] text-zinc-500 mt-1.5"><span className="font-semibold text-zinc-700">Suggested action: </span>{ins.action}</p>
 )}
 </div>
 </div>
 </div>
 </button>
 ))}
 </div>
 )}
 {aiInsights?.generated_at && (
 <p className="text-[11px] text-zinc-400 mt-3">Generated {new Date(aiInsights.generated_at).toLocaleString()}</p>
 )}
 </SectionCard>

 {draft && (
 <SectionCard
 title="Global feature flags"
 action={
 <Button size="sm" className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)]" onClick={() => onSaveFlags(draft)} data-testid="save-flags">
 Save flags
 </Button>
 }
 >
 <div className="space-y-1">
 <p className="text-[11px] uppercase tracking-wider text-zinc-400 font-semibold mb-2">Core features</p>
 {coreKeys.map((k) => (
 <div key={k} className="flex items-center justify-between py-2 border-b border-zinc-50 last:border-b-0">
 <div>
 <p className="text-sm text-zinc-800 font-mono text-xs">{k.replace(/_/g, ' ')}</p>
 </div>
 <Switch checked={!!draft[k]} onCheckedChange={(v) => setDraft({ ...draft, [k]: v })} data-testid={`flag-${k}`} />
 </div>
 ))}
 </div>

 {betaKeys.length > 0 && (
 <div className="mt-5 pt-5 border-t border-zinc-100">
 <p className="text-[11px] uppercase tracking-wider text-zinc-400 font-semibold mb-2 flex items-center gap-1">
 <FlaskConical size={11} /> Beta features — rollout gates
 </p>
 {betaKeys.map((k) => (
 <div key={k} className="flex items-center justify-between py-2 border-b border-zinc-50 last:border-b-0">
 <div>
 <p className="text-sm text-zinc-800 font-mono text-xs">{k.replace(/_/g, ' ')}</p>
 </div>
 <Switch checked={!!draft[k]} onCheckedChange={(v) => setDraft({ ...draft, [k]: v })} data-testid={`flag-${k}`} />
 </div>
 ))}
 </div>
 )}

 {featureFlags?.updated_at && (
 <p className="text-[11px] text-zinc-400 mt-3">Last updated {new Date(featureFlags.updated_at).toLocaleString()} by {featureFlags.updated_by || 'system'}</p>
 )}
 </SectionCard>
 )}
 </div>
 );
};

export default AiAndFlagsTab;
