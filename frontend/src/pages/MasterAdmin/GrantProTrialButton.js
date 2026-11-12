import { useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Gift, Loader2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Master Admin: give a Lite organisation that asked for it one more free Pulse Pro trial.
export default function GrantProTrialButton({ org }) {
  const [busy, setBusy] = useState(false);
  const [granted, setGranted] = useState(!!org.pro_trial_granted);
  if ((org.account_type || '').toLowerCase() !== 'lite') return null;
  const used = !!org.pro_trial_used_at || Object.values(org.module_trials || {}).some((t) => t?.started_at);

  const grant = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/master-admin/organizations/${org.id}/grant-pro-trial`, {},
        { headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });
      setGranted(true);
      notify.success('Free trial allocated', `${org.name} can start a new 3-day Pulse Pro trial from Account settings.`);
    } catch (e) { notifyApiError(notify, e, 'Could not allocate the trial'); }
    setBusy(false);
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 rounded-md border border-zinc-200 p-3" data-testid={`org-pro-trial-${org.id}`}>
      <div className="flex-1 min-w-[12rem] text-xs text-zinc-600">
        <p className="font-semibold text-zinc-800">Free Pulse Pro trial</p>
        <p data-testid={`org-pro-trial-status-${org.id}`}>
          {granted ? 'Allocated — waiting for the organisation to start it.' : used ? 'Already used.' : 'Not used yet — available to the owner.'}
        </p>
      </div>
      {used && !granted && (
        <Button size="sm" variant="outline" onClick={grant} disabled={busy} data-testid={`org-grant-pro-trial-${org.id}`}>
          {busy ? <Loader2 size={13} className="animate-spin mr-1" /> : <Gift size={13} className="mr-1" />} Allocate another trial
        </Button>
      )}
    </div>
  );
}
