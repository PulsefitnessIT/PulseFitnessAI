import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { DownloadCloud, Eye, Loader2 } from 'lucide-react';
import SiconSyncCounts from './SiconSyncCounts';
import SiconDifferencesList from './SiconDifferencesList';

const busy = (run) => run && ['queued', 'running'].includes(run.status);
const PHASE = { equipment: 'Reading equipment, customers and sites', contracts: 'Reading contracts', cases: 'Reading cases', done: 'Finished' };

export default function SiconOnboardingSync({ API, headers }) {
  const [state, setState] = useState(null);
  const [starting, setStarting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const load = useCallback(async () => {
    try { setState((await axios.get(`${API}/sicon/read/onboarding/latest`, { headers })).data); } catch { /* panel shows empty */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- headers is rebuilt each render; token read at call time
  }, [API]);

  useEffect(() => { load(); }, [load]);
  const running = busy(state?.preview) || busy(state?.apply);
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [running, load]);

  const start = async (url, msg) => {
    setStarting(true);
    try { await axios.post(url, {}, { headers }); notify.success(msg); await load(); }
    catch (e) { notifyApiError(notify, e, 'Could not start the Sicon sync'); }
    setStarting(false);
  };

  const preview = state?.preview;
  const applied = state?.apply;
  const appliedThisPreview = applied && applied.preview_run_id === preview?.id;
  const active = busy(applied) ? applied : busy(preview) ? preview : null;
  const shown = appliedThisPreview ? applied : preview;

  return (
    <Card className="p-5 border-zinc-200 dark:border-zinc-800 space-y-4" data-testid="sicon-onboarding-sync-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Sicon Sync — onboarding import</h4>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 max-w-xl">
            Pulls customers, sites, equipment, contracts and cases from Sicon. Preview first — nothing is saved until you confirm.
            Existing Pulse details are never overwritten; differences go to a review list.
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={running || starting} data-testid="sicon-sync-preview-btn"
            onClick={() => start(`${API}/sicon/read/onboarding/preview`, 'Preview started — reading Sicon')}>
            {starting && !preview ? <Loader2 size={14} className="animate-spin mr-1" /> : <Eye size={14} className="mr-1" />}
            {preview ? 'Preview again' : 'Preview Sicon Sync'}
          </Button>
          {preview?.status === 'completed' && !appliedThisPreview && (
            <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white" disabled={running || starting}
              onClick={() => setConfirmOpen(true)} data-testid="sicon-sync-apply-btn">
              <DownloadCloud size={14} className="mr-1" /> Confirm &amp; import
            </Button>
          )}
        </div>
      </div>

      {active && (
        <div className="flex items-center gap-2 rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900 p-3 text-sm text-blue-800 dark:text-blue-200" data-testid="sicon-sync-progress">
          <Loader2 size={14} className="animate-spin" />
          {active.mode === 'apply' ? 'Importing' : 'Previewing'} — {PHASE[active.phase] || 'Starting'}…
        </div>
      )}

      {shown && !busy(shown) && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500" data-testid="sicon-sync-run-meta">
            <Badge className={shown.status === 'completed' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}>
              {shown.mode === 'apply' ? 'Imported' : 'Preview'} · {shown.status}
            </Badge>
            <span>{new Date(shown.finished_at || shown.started_at).toLocaleString()}</span>
            {shown.error && <span className="text-red-600" data-testid="sicon-sync-error">{shown.error}</span>}
          </div>
          <SiconSyncCounts run={shown} />
        </div>
      )}

      {!preview && !active && (
        <p className="text-xs text-zinc-400" data-testid="sicon-sync-empty">No sync run yet. Test the connection, then click "Preview Sicon Sync".</p>
      )}

      <SiconDifferencesList API={API} headers={headers} openCount={state?.open_differences || 0}
        conflictCount={state?.open_conflicts || 0} onChange={load} />

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent data-testid="sicon-sync-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Import from Sicon now?</AlertDialogTitle>
            <AlertDialogDescription>
              New customers, sites, equipment, contracts and cases will be created and matches linked. Empty Pulse fields are filled in;
              anything already filled in stays as it is and differences are listed for review. Sicon itself is not changed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="sicon-sync-confirm-cancel">Cancel</AlertDialogCancel>
            <AlertDialogAction data-testid="sicon-sync-confirm-ok"
              onClick={() => start(`${API}/sicon/read/onboarding/${preview.id}/apply`, 'Import started')}>
              Import
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
