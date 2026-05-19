/* Master Admin — Trial Management */
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/App';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import {
  Clock, CheckCircle2, AlertTriangle, Lock, Zap,
  Calendar, Users, Loader2, RefreshCw, TrendingUp
} from 'lucide-react';

const STATUS_META = {
  active: { label: 'Active', classes: 'bg-emerald-100 text-emerald-700' },
  expiring_soon: { label: 'Expiring soon', classes: 'bg-amber-100 text-amber-700' },
  expired: { label: 'Expired', classes: 'bg-red-100 text-red-700' },
  suspended: { label: 'Suspended', classes: 'bg-zinc-800 text-white' },
  converted: { label: 'Converted', classes: 'bg-blue-100 text-blue-700' },
};

export default function AdminTrials() {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [trials, setTrials] = useState([]);
  const [summary, setSummary] = useState({ total: 0, by_status: {}, converted_30d: 0 });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [extendTarget, setExtendTarget] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [listRes, sumRes] = await Promise.all([
        axios.get(`${API}/master-admin/trials`, { headers }),
        axios.get(`${API}/master-admin/trials/summary`, { headers }),
      ]);
      setTrials(listRes.data.trials || []);
      setSummary(sumRes.data || { total: 0, by_status: {}, converted_30d: 0 });
    } catch (e) {
      notify.error('Failed to load trials');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const filtered = filter === 'all' ? trials : trials.filter(t => t.trial_status === filter);

  const startCheckout = async (org) => {
    try {
      const res = await axios.post(`${API}/master-admin/trials/${org.id}/convert`,
        { tier: org.tier, origin_url: window.location.origin },
        { headers });
      if (res.data?.checkout_url) {
        navigator.clipboard.writeText(res.data.checkout_url);
        notify.success('Checkout link copied to clipboard. Share with the customer.');
        window.open(res.data.checkout_url, '_blank');
      }
    } catch (e) {
      notifyApiError(notify, e, 'Checkout creation failed');
    }
  };

  const markConverted = async (orgId) => {
    if (!window.confirm('Mark this trial as converted? (Use only if Stripe payment didn\'t fire the webhook.)')) return;
    try {
      await axios.post(`${API}/master-admin/trials/${orgId}/mark-converted`, {}, { headers });
      notify.success('Marked as converted');
      load();
    } catch (e) {
      notify.error('Failed');
    }
  };

  if (loading) return <div className="flex justify-center py-20"><Loader2 className="animate-spin text-zinc-400" /></div>;

  return (
    <div className="space-y-5" data-testid="admin-trials">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold text-zinc-900">Trial Management</h2>
          <p className="text-sm text-zinc-500 mt-1">Track active trials, extend deadlines, and convert customers to paid subscriptions.</p>
        </div>
        <Button variant="outline" size="sm" onClick={load}><RefreshCw size={12} className="mr-1" /> Refresh</Button>
      </div>

      {/* Summary tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <SummaryTile icon={Clock} label="Active" value={summary.by_status?.active || 0} tone="emerald" testid="tile-active" />
        <SummaryTile icon={AlertTriangle} label="Expiring soon" value={summary.by_status?.expiring_soon || 0} tone="amber" testid="tile-expiring" />
        <SummaryTile icon={Lock} label="Expired" value={summary.by_status?.expired || 0} tone="red" testid="tile-expired" />
        <SummaryTile icon={CheckCircle2} label="Converted (30d)" value={summary.converted_30d || 0} tone="blue" testid="tile-converted-30d" />
        <SummaryTile icon={TrendingUp} label="Total" value={summary.total || 0} tone="zinc" testid="tile-total-trials" />
      </div>

      {/* Filter pills */}
      <div className="flex gap-1 flex-wrap">
        {['all', 'active', 'expiring_soon', 'expired', 'suspended', 'converted'].map(s => (
          <button key={s} onClick={() => setFilter(s)}
            data-testid={`trial-filter-${s}`}
            className={`px-3 py-1 rounded-md text-xs font-medium capitalize transition-colors ${filter === s ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200'}`}>
            {s.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* List */}
      {filtered.length === 0 ? (
        <Card className="p-10 text-center border-zinc-200">
          <Clock size={28} className="text-zinc-300 mx-auto mb-2" />
          <p className="text-sm text-zinc-500">No trials {filter !== 'all' && `in "${filter.replace('_', ' ')}"`}.</p>
        </Card>
      ) : (
        <div className="grid gap-3">
          {filtered.map(t => (
            <TrialRow key={t.id} trial={t} onExtend={() => setExtendTarget(t)} onCheckout={() => startCheckout(t)} onMarkConverted={() => markConverted(t.id)} />
          ))}
        </div>
      )}

      {extendTarget && (
        <ExtendDialog API={API} headers={headers} trial={extendTarget}
          onClose={() => setExtendTarget(null)}
          onExtended={() => { setExtendTarget(null); load(); }} />
      )}
    </div>
  );
}

function TrialRow({ trial, onExtend, onCheckout, onMarkConverted }) {
  const meta = STATUS_META[trial.trial_status] || STATUS_META.active;
  const total = trial.trial_duration_days + (trial.extended_by_days || 0);
  const used = total - trial.days_left;
  const pct = Math.max(0, Math.min(100, Math.round((used / Math.max(1, total)) * 100)));
  const progressColor = trial.trial_status === 'expired' || trial.trial_status === 'suspended' ? 'bg-red-500' : trial.trial_status === 'expiring_soon' ? 'bg-amber-500' : 'bg-emerald-500';

  return (
    <Card className="p-5 border-slate-200 rounded-2xl shadow-[0_1px_2px_rgba(15,23,42,0.04)] hover:shadow-[0_8px_24px_-8px_rgba(15,23,42,0.10)] transition-shadow" data-testid={`trial-row-${trial.id}`}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-zinc-900 truncate">{trial.name}</h3>
            <Badge className={meta.classes}>{meta.label}</Badge>
            <Badge className="bg-blue-100 text-blue-700 capitalize">{trial.tier}</Badge>
          </div>
          <p className="text-xs text-zinc-500 mt-1 flex items-center gap-3 flex-wrap">
            <span><Users size={10} className="inline mr-1" />{trial.user_count} users</span>
            {trial.primary_contact?.email && <span>{trial.primary_contact.email}</span>}
            {trial.extended_by_days > 0 && <span className="text-amber-600">• Extended +{trial.extended_by_days}d</span>}
          </p>

          <div className="mt-3">
            <div className="flex justify-between text-[11px] text-zinc-500 mb-1">
              <span>{used} days used</span>
              <span className="font-medium text-zinc-700">{trial.days_left} days left</span>
            </div>
            <div className="w-full h-1.5 bg-zinc-100 rounded-full overflow-hidden">
              <div className={`h-full ${progressColor}`} style={{ width: `${pct}%` }} />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap justify-end">
          {trial.trial_status !== 'converted' && (
            <>
              <Button size="sm" variant="outline" onClick={onExtend} data-testid={`btn-extend-${trial.id}`}>
                <Calendar size={12} className="mr-1" /> Extend
              </Button>
              <Button size="sm" onClick={onCheckout} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid={`btn-convert-${trial.id}`}>
                <Zap size={12} className="mr-1" /> Convert
              </Button>
              <Button size="sm" variant="outline" onClick={onMarkConverted} title="Manually mark as converted (Stripe didn't fire webhook)" data-testid={`btn-mark-converted-${trial.id}`}>
                <CheckCircle2 size={12} />
              </Button>
            </>
          )}
        </div>
      </div>
    </Card>
  );
}

function ExtendDialog({ API, headers, trial, onClose, onExtended }) {
  const [days, setDays] = useState(7);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/master-admin/trials/${trial.id}/extend`,
        { days, reason },
        { headers });
      notify.success(`Extended by ${days} days`);
      onExtended();
    } catch (e) {
      notifyApiError(notify, e, 'Extension failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent data-testid="extend-trial-dialog">
        <DialogHeader><DialogTitle>Extend trial — {trial.name}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label className="text-xs uppercase tracking-wider">Additional days (1–30)</Label>
            <Input type="number" min={1} max={30} value={days} onChange={e => setDays(Number(e.target.value))} data-testid="extend-days" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider">Reason (for audit log)</Label>
            <Input value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. Customer requested more time to evaluate" data-testid="extend-reason" />
          </div>
          <div className="bg-blue-50 border border-blue-200 rounded-md p-2 text-xs text-blue-800">
            Currently {trial.days_left} days left. New end date will push forward by {days} days. Reminder emails will re-arm.
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={busy} className="bg-blue-600 hover:bg-blue-700" data-testid="btn-confirm-extend">
            {busy ? <Loader2 size={12} className="animate-spin mr-1" /> : <Calendar size={12} className="mr-1" />}
            Extend trial
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SummaryTile({ icon: Icon, label, value, tone, testid }) {
  const tones = {
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-700',
    amber: 'bg-amber-50 border-amber-200 text-amber-700',
    red: 'bg-red-50 border-red-200 text-red-700',
    blue: 'bg-blue-50 border-blue-200 text-blue-700',
    zinc: 'bg-zinc-50 border-zinc-200 text-zinc-700',
  };
  return (
    <div className={`border rounded-lg p-3 ${tones[tone]}`} data-testid={testid}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest font-semibold opacity-80">{label}</span>
        <Icon size={13} className="opacity-60" />
      </div>
      <p className="mt-1 text-2xl font-bold tabular-nums">{value}</p>
    </div>
  );
}
