/**
 * EquipmentTransfersInbox (Iter 337) — gym Operations side.
 *
 * Surfaces equipment that an engineer wants to hand over to this gym's
 * Operations portal, plus a discovery row for equipment an engineer
 * already holds on file for this gym. The gym admin approves before
 * anything moves; transferred assets keep their QR codes and history.
 * Self-hides when there's nothing to action.
 */
import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import { ArrowRightLeft, CheckCircle2, X, Loader2, PackagePlus } from 'lucide-react';

export default function EquipmentTransfersInbox({ onImported }) {
  const [pending, setPending] = useState([]);
  const [available, setAvailable] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([
        api.get('/operations/equipment-transfers', { params: { status: 'pending' } }),
        api.get('/operations/equipment-transfers/available'),
      ]);
      setPending((p.data?.transfers || []).filter((t) => t.awaiting === 'gym'));
      setAvailable(a.data?.available || []);
    } catch (_e) {
      /* non-blocking */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const approve = async (t) => {
    setBusyId(t.id);
    try {
      const r = await api.post(`/operations/equipment-transfers/${t.id}/approve`);
      notify.success(`${r.data.moved_count} machine(s) imported into your Operations portal.`);
      await load();
      onImported?.();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not approve transfer');
    } finally {
      setBusyId(null);
    }
  };

  const decline = async (t) => {
    setBusyId(t.id);
    try {
      await api.post(`/operations/equipment-transfers/${t.id}/decline`);
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not decline transfer');
    } finally {
      setBusyId(null);
    }
  };

  const requestPull = async (a) => {
    setBusyId(a.source_customer_id);
    try {
      await api.post('/operations/equipment-transfers/request', {
        source_org_id: a.source_org_id,
        source_customer_id: a.source_customer_id,
      });
      notify.success('Import requested — your engineer will approve the handover.');
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not request import');
    } finally {
      setBusyId(null);
    }
  };

  if (loading || (pending.length === 0 && available.length === 0)) return null;

  return (
    <div className="mb-6 rounded-2xl border border-orange-200 bg-orange-50/60 p-5" data-testid="eq-transfers-inbox">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-8 h-8 rounded-xl bg-orange-500 text-white flex items-center justify-center"><ArrowRightLeft size={16} /></span>
        <h3 className="font-bold text-slate-900">Equipment from your engineer</h3>
      </div>

      {pending.map((t) => (
        <div key={t.id} className="rounded-xl border border-slate-200 bg-white p-4 mb-2 flex flex-wrap items-center justify-between gap-3" data-testid={`eq-transfer-pending-${t.id}`}>
          <div className="min-w-0">
            <p className="text-sm font-bold text-slate-900">{t.equipment_count} machine{t.equipment_count === 1 ? '' : 's'} ready to import</p>
            <p className="text-xs text-slate-500 mt-0.5">From {t.engineer_name || 'your engineer'}{t.engineer_company ? ` · ${t.engineer_company}` : ''} · QR codes & service history included</p>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => decline(t)} disabled={busyId === t.id} className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-slate-300 text-slate-600 text-xs font-bold hover:bg-slate-50" data-testid={`eq-transfer-decline-${t.id}`}>
              <X size={13} /> Decline
            </button>
            <button type="button" onClick={() => approve(t)} disabled={busyId === t.id} className="inline-flex items-center gap-1 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold disabled:opacity-50" data-testid={`eq-transfer-approve-${t.id}`}>
              {busyId === t.id ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />} Approve & import
            </button>
          </div>
        </div>
      ))}

      {available.map((a) => (
        <div key={a.source_customer_id} className="rounded-xl border border-slate-200 bg-white p-4 mb-2 flex flex-wrap items-center justify-between gap-3" data-testid={`eq-transfer-available-${a.source_customer_id}`}>
          <div className="min-w-0">
            <p className="text-sm font-bold text-slate-900">{a.equipment_count} machine{a.equipment_count === 1 ? '' : 's'} on file with {a.engineer_org_name}</p>
            <p className="text-xs text-slate-500 mt-0.5">Request to import these into your Operations portal.</p>
          </div>
          <button type="button" onClick={() => requestPull(a)} disabled={busyId === a.source_customer_id} className="inline-flex items-center gap-1 px-4 py-2 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-xs font-bold disabled:opacity-50" data-testid={`eq-transfer-request-${a.source_customer_id}`}>
            {busyId === a.source_customer_id ? <Loader2 size={13} className="animate-spin" /> : <PackagePlus size={13} />} Request import
          </button>
        </div>
      ))}
    </div>
  );
}
