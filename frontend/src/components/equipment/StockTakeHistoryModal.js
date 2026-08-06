/**
 * StockTakeHistoryModal — review saved bulk stock-take reports.
 * Managers open this (any device) to see past audits: who ran it, when, and
 * the found / missing / unexpected breakdown. Missing machines are listed so
 * they can follow up.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { X, Loader2, ClipboardList, ChevronRight, AlertTriangle, Flag, CheckSquare, Square, ListChecks } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });
const fmt = (iso) => { try { return new Date(iso).toLocaleString(); } catch (_e) { return iso || ''; } };

export default function StockTakeHistoryModal({ open, onClose, siteId }) {
  const [view, setView] = useState('history'); // history | followups
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [flagging, setFlagging] = useState(false);
  const [followUps, setFollowUps] = useState([]);
  const [fuLoading, setFuLoading] = useState(false);

  const loadHistory = () => {
    setLoading(true);
    axios.get(`${API}/equipment/stocktakes`, { ...auth(), params: { site_id: siteId || undefined } })
      .then((r) => setRows(r.data?.stocktakes || []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  };
  const loadFollowUps = () => {
    setFuLoading(true);
    axios.get(`${API}/equipment/follow-ups`, { ...auth(), params: { site_id: siteId || undefined, status: 'open' } })
      .then((r) => setFollowUps(r.data?.follow_ups || []))
      .catch(() => setFollowUps([]))
      .finally(() => setFuLoading(false));
  };

  useEffect(() => {
    if (!open) return;
    setDetail(null); setView('history');
    loadHistory();
    loadFollowUps();
  }, [open, siteId]); // eslint-disable-line react-hooks/exhaustive-deps

  const openDetail = async (id) => {
    setDetailLoading(true);
    try { const r = await axios.get(`${API}/equipment/stocktakes/${id}`, auth()); setDetail(r.data); }
    catch (_e) { /* noop */ }
    setDetailLoading(false);
  };

  const flagMissing = async () => {
    if (!detail) return;
    setFlagging(true);
    try {
      await axios.post(`${API}/equipment/stocktakes/${detail.id}/flag-missing`, {}, auth());
      const r = await axios.get(`${API}/equipment/stocktakes/${detail.id}`, auth());
      setDetail(r.data);
      loadFollowUps();
    } catch (_e) { /* noop */ }
    setFlagging(false);
  };

  const resolveFollowUp = async (item) => {
    try {
      await axios.put(`${API}/equipment/stocktakes/${item.stocktake_id}/follow-ups/${item.equipment_id}`,
        { status: 'resolved' }, auth());
      setFollowUps((list) => list.filter((f) => !(f.stocktake_id === item.stocktake_id && f.equipment_id === item.equipment_id)));
    } catch (_e) { /* noop */ }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[90] bg-slate-900/70 flex items-end sm:items-center justify-center" data-testid="stocktake-history-modal" role="dialog" aria-modal="true">
      <div className="w-full max-w-md bg-white rounded-t-3xl sm:rounded-3xl shadow-xl overflow-hidden max-h-[92vh] flex flex-col">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100 shrink-0">
          <ClipboardList size={16} className="text-cyan-600" />
          <p className="text-sm font-bold text-slate-900 flex-1">{detail ? 'Stock-take report' : 'Stock-takes'}</p>
          {detail && <button type="button" onClick={() => setDetail(null)} className="text-xs font-bold text-cyan-600 mr-2" data-testid="stocktake-history-back">Back</button>}
          <button type="button" onClick={onClose} className="w-8 h-8 rounded-full hover:bg-slate-100 flex items-center justify-center text-slate-500" data-testid="stocktake-history-close" aria-label="Close"><X size={16} /></button>
        </div>

        {!detail && (
          <div className="flex px-4 pt-3 gap-2 shrink-0">
            <button type="button" onClick={() => setView('history')} className={`text-xs font-bold px-3 py-1.5 rounded-full ${view === 'history' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'}`} data-testid="stocktake-tab-history">History</button>
            <button type="button" onClick={() => setView('followups')} className={`text-xs font-bold px-3 py-1.5 rounded-full inline-flex items-center gap-1.5 ${view === 'followups' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'}`} data-testid="stocktake-tab-followups">
              <ListChecks size={13} /> Follow-ups{followUps.length ? ` (${followUps.length})` : ''}
            </button>
          </div>
        )}

        <div className="p-4 overflow-y-auto">
          {detail ? (
            <div className="space-y-3">
              <p className="text-xs text-slate-500">{detail.location} · {fmt(detail.created_at)} · by {detail.started_by || 'staff'}</p>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-2 rounded-xl bg-green-50 border border-green-100"><p className="text-lg font-bold text-green-700">{detail.found_count}</p><p className="text-[10px] uppercase text-green-700/70">Found</p></div>
                <div className="p-2 rounded-xl bg-red-50 border border-red-100"><p className="text-lg font-bold text-red-700">{detail.missing_count}</p><p className="text-[10px] uppercase text-red-700/70">Missing</p></div>
                <div className="p-2 rounded-xl bg-amber-50 border border-amber-100"><p className="text-lg font-bold text-amber-700">{detail.unexpected_count}</p><p className="text-[10px] uppercase text-amber-700/70">Unexpected</p></div>
              </div>
              {detail.missing?.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-[10px] font-bold uppercase tracking-wide text-red-600 flex items-center gap-1"><AlertTriangle size={11} /> Missing</p>
                    <button type="button" onClick={flagMissing} disabled={flagging || detail.follow_up_flagged} className="text-[11px] font-bold inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-amber-500 text-white disabled:opacity-50" data-testid="stocktake-flag-missing">
                      {flagging ? <Loader2 size={11} className="animate-spin" /> : <Flag size={11} />} {detail.follow_up_flagged ? 'Flagged for follow-up' : 'Flag for follow-up'}
                    </button>
                  </div>
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    {detail.missing.map((e) => <div key={e.id} className="text-xs text-slate-700">{e.name || e.serial_number} <span className="text-slate-400">· {e.serial_number}{e.location ? ` · ${e.location}` : ''}</span></div>)}
                  </div>
                </div>
              )}
            </div>
          ) : view === 'followups' ? (
            fuLoading ? (
              <div className="py-10 text-center text-slate-400"><Loader2 size={20} className="animate-spin inline" /></div>
            ) : followUps.length === 0 ? (
              <p className="py-10 text-center text-sm text-slate-400" data-testid="stocktake-followups-empty">No open follow-ups. Flag a stock-take's missing machines to create tasks.</p>
            ) : (
              <div className="space-y-2" data-testid="stocktake-followups-list">
                {followUps.map((f) => (
                  <div key={`${f.stocktake_id}-${f.equipment_id}`} className="flex items-start gap-2 px-3 py-2 rounded-xl border border-slate-200" data-testid={`followup-item-${f.equipment_id}`}>
                    <button type="button" onClick={() => resolveFollowUp(f)} className="mt-0.5 text-slate-400 hover:text-green-600" title="Mark resolved" data-testid={`followup-resolve-${f.equipment_id}`}>
                      <Square size={16} />
                    </button>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-bold text-slate-900 truncate">{f.name}</p>
                      <p className="text-[11px] text-slate-500">{f.serial_number}{f.location ? ` · ${f.location}` : ''} · from {f.stocktake_location} · {fmt(f.stocktake_at)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : loading ? (
            <div className="py-10 text-center text-slate-400"><Loader2 size={20} className="animate-spin inline" /></div>
          ) : rows.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-400" data-testid="stocktake-history-empty">No stock-takes yet.</p>
          ) : (
            <div className="space-y-2" data-testid="stocktake-history-list">
              {rows.map((s) => (
                <button key={s.id} type="button" onClick={() => openDetail(s.id)} disabled={detailLoading} className="w-full text-left px-3 py-2.5 rounded-xl border border-slate-200 hover:bg-slate-50 flex items-center gap-2" data-testid={`stocktake-history-row-${s.id}`}>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-slate-900 truncate">{s.location}</p>
                    <p className="text-[11px] text-slate-500">{fmt(s.created_at)} · {s.started_by || 'staff'}</p>
                  </div>
                  <span className="text-xs font-bold text-green-600">{s.found_count}/{s.expected_count}</span>
                  {s.missing_count > 0 && <span className="text-xs font-bold text-red-600">{s.missing_count} missing</span>}
                  <ChevronRight size={14} className="text-slate-400" />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
