/**
 * BackfillsPanel — Iter 216bn.
 *
 * One-click maintenance backfills surfaced in Master Admin → Tools.
 * Each backfill ships with a dry-run-first pattern: click "Preview"
 * to see what would change, then "Apply" to write. Built to scale
 * — adding a new backfill is one config block.
 */
import { useState } from 'react';
import axios from 'axios';
import { RefreshCcw, FileText, Wrench, Loader2, CheckCircle2, ListChecks } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

const BACKFILLS = [
  {
    id: 'pulse-supplier',
    title: 'Pulse Fitness supplier',
    icon: Wrench,
    description: 'Set every piece of equipment in every Pulse Fitness Lite / Pro organisation\'s supplier to "Pulse Fitness" with the official service email (service.dept@pulsefitness.com).',
    path: '/master-admin/equipment/backfill-pulse-supplier',
    countKey: 'equipment_to_update',
    appliedKey: 'equipment_updated',
  },
  {
    id: 'spec-sheets',
    title: 'Spec sheets → equipment',
    icon: FileText,
    description: 'Re-run the spec-sheet auto-match across all equipment so rows added before this feature pick up matching catalogue entries (model, manufacturer, photo).',
    path: '/master-admin/equipment/backfill-spec-sheets',
    countKey: 'matched',
    appliedKey: 'matched',
    consideredKey: 'considered',
  },
  {
    id: 'short-display',
    title: 'Short equipment-row display (iter 216h13)',
    icon: ListChecks,
    description: 'Rewrite legacy invoice-imported equipment so `name` is the short subtype noun (Treadmill / StepMill / Upright Cycle) and `model` is the short stock code (260G, 200H-AAF). Full marketing line preserved in `description`. Run this once after deploy to clean up Carshalton + any other long-row imports.',
    path: '/master-admin/equipment/backfill-short-display',
    countKey: 'equipment_to_update',
    appliedKey: 'equipment_updated',
    consideredKey: 'total_candidates',
  },
];

const BackfillCard = ({ cfg }) => {
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);

  const run = async (dry_run) => {
    setRunning(true);
    try {
      const r = await axios.post(`${API}${cfg.path}?dry_run=${dry_run}`, {}, { headers: auth() });
      if (dry_run) {
        setPreview(r.data);
        notify.info('Preview ready');
      } else {
        setResult(r.data);
        notify.success(`Backfill complete · ${r.data?.[cfg.appliedKey] || 0} rows updated`);
      }
    } catch (e) {
      notifyApiError(notify, e, `Failed to ${dry_run ? 'preview' : 'run'} backfill`);
    }
    setRunning(false);
  };

  return (
    <Card className="bg-[var(--theme-surface)] border-white/10 p-4 space-y-3" data-testid={`backfill-${cfg.id}`}>
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400 shrink-0">
          <cfg.icon size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white">{cfg.title}</p>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">{cfg.description}</p>
        </div>
      </div>

      {preview && (
        <div className="px-3 py-2 rounded-md bg-blue-500/5 border border-blue-500/20 text-xs text-blue-300 flex items-center gap-2 flex-wrap" data-testid={`backfill-${cfg.id}-preview`}>
          <span className="font-semibold">Preview:</span>
          {cfg.consideredKey ? <Badge className="bg-zinc-500/10 text-zinc-300 border-zinc-500/30 text-[10px]">considered: {preview[cfg.consideredKey] ?? '—'}</Badge> : null}
          <Badge className="bg-amber-500/10 text-amber-300 border-amber-500/30 text-[10px]">would update: {preview[cfg.countKey] ?? 0}</Badge>
          {preview.orgs != null ? <Badge className="bg-zinc-500/10 text-zinc-300 border-zinc-500/30 text-[10px]">orgs: {preview.orgs}</Badge> : null}
        </div>
      )}

      {result && (
        <div className="px-3 py-2 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-300 flex items-center gap-2 flex-wrap" data-testid={`backfill-${cfg.id}-result`}>
          <CheckCircle2 size={12} />
          <span className="font-semibold">Done.</span>
          <span>{result[cfg.appliedKey] ?? 0} rows updated</span>
          {result.orgs != null ? <span>· across {result.orgs} orgs</span> : null}
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        <Button size="sm" variant="ghost" disabled={running} onClick={() => run(true)} className="text-xs text-[var(--color-text-muted)] hover:text-white" data-testid={`backfill-${cfg.id}-preview-btn`}>
          {running ? <Loader2 size={12} className="animate-spin mr-1.5" /> : <RefreshCcw size={12} className="mr-1.5" />}
          Preview
        </Button>
        <Button size="sm" disabled={running} onClick={() => {
          if (!window.confirm(`Apply "${cfg.title}" to production data? This will write to the database immediately.`)) return;
          run(false);
        }} className="bg-blue-600 hover:bg-blue-700 text-white text-xs" data-testid={`backfill-${cfg.id}-apply-btn`}>
          {running ? <Loader2 size={12} className="animate-spin mr-1.5" /> : null}
          Apply
        </Button>
      </div>
    </Card>
  );
};

const BackfillsPanel = () => (
  <div className="space-y-4" data-testid="backfills-panel">
    <div>
      <h2 className="text-xl font-semibold text-white flex items-center gap-2">
        <RefreshCcw size={18} className="text-blue-400" /> Data Backfills
      </h2>
      <p className="text-xs text-[var(--color-text-muted)] mt-1 max-w-2xl">
        One-click maintenance jobs. Always preview before applying. New backfills are added by the engineering team as new auto-attach features ship — running them is what propagates the new defaults to existing data.
      </p>
    </div>

    <div className="grid gap-4 md:grid-cols-2">
      {BACKFILLS.map(cfg => (
        <BackfillCard key={cfg.id} cfg={cfg} />
      ))}
    </div>
  </div>
);

export default BackfillsPanel;
