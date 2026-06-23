/**
 * Pulse Fitness AI — campaign analytics modal: rates, click map, bot
 * filtering toggle, conversions and an AI "why did this perform?" summary.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { X, Wand2, Loader2, MousePointerClick } from 'lucide-react';

const apiRoot = (API) => (API || process.env.REACT_APP_BACKEND_URL || '').replace(/\/api\/?$/, '');
const card = { background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' };
const muted = { color: 'var(--theme-text-muted)' };
const txt = { color: 'var(--theme-text)' };

function Metric({ label, value, suffix }) {
  return (
    <div className="rounded-xl border p-3" style={card}>
      <p className="text-[11px] font-bold uppercase tracking-wide" style={muted}>{label}</p>
      <p className="text-xl font-extrabold pulse-font-heading" style={txt}>{value}{suffix}</p>
    </div>
  );
}

export default function CampaignAnalytics({ campaign, API, headers, onClose }) {
  const [bots, setBots] = useState('exclude');
  const [data, setData] = useState(null);
  const [ai, setAi] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${apiRoot(API)}/api/comms/campaigns/${campaign.id}/analytics?bots=${bots}`, { headers });
      setData(r.data);
    } catch { toast.error('Failed to load analytics'); }
  }, [API, headers, campaign.id, bots]);
  useEffect(() => { load(); }, [load]);

  const analyse = async () => {
    setAiBusy(true);
    try {
      const r = await axios.post(`${apiRoot(API)}/api/comms/campaigns/${campaign.id}/ai-analyse`, {}, { headers });
      setAi(r.data.analysis);
    } catch (e) { toast.error(e?.response?.data?.detail || 'AI is unavailable right now'); }
    finally { setAiBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[160] bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto border" style={card} onClick={(e) => e.stopPropagation()} data-testid="campaign-analytics-modal">
        <div className="flex items-center justify-between px-6 py-4 border-b sticky top-0" style={{ ...card, borderColor: 'var(--theme-border)' }}>
          <h3 className="font-bold text-lg pulse-font-heading" style={txt}>{campaign.name} — analytics</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-black/5" style={muted}><X size={18} /></button>
        </div>
        <div className="p-6">
          {!data ? <p className="text-sm" style={muted}>Loading…</p> : (
            <>
              <div className="flex items-center justify-end gap-2 mb-3">
                <span className="text-xs font-semibold" style={muted}>Bot filtering</span>
                <select value={bots} onChange={(e) => setBots(e.target.value)} className="px-2 py-1 rounded-lg text-xs border" style={{ ...card, ...txt }} data-testid="analytics-bots">
                  <option value="exclude">Exclude bots ({data.bot_opens})</option>
                  <option value="include">Include bots</option>
                </select>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                <Metric label="Sent" value={data.totals.sent} />
                <Metric label="Open rate" value={data.rates.open_rate} suffix="%" />
                <Metric label="Click rate" value={data.rates.click_rate} suffix="%" />
                <Metric label="Bounce rate" value={data.rates.bounce_rate} suffix="%" />
              </div>

              {data.conversions && (
                <div className="grid grid-cols-3 gap-3 mb-4" data-testid="analytics-conversions">
                  <Metric label="Conversions" value={data.conversions.count} />
                  <Metric label="Conv. rate" value={data.conversions.conversion_rate} suffix="%" />
                  <Metric label="Revenue" value={`£${data.conversions.revenue_gbp}`} />
                </div>
              )}
              {data.conversions && Object.keys(data.conversions.by_type || {}).length > 0 && (
                <div className="flex flex-wrap gap-2 mb-4">
                  {Object.entries(data.conversions.by_type).map(([t, n]) => (
                    <span key={t} className="text-xs font-bold px-2.5 py-1 rounded-full" style={{ background: 'var(--theme-bg)', ...txt }}>{t.replace(/_/g, ' ')}: {n}</span>
                  ))}
                </div>
              )}

              <div className="mb-4">
                <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide mb-2" style={muted}><MousePointerClick size={13} />Click map</p>
                {data.click_map.length === 0 ? <p className="text-sm" style={muted}>No link clicks recorded yet.</p> : (
                  <div className="space-y-1.5">
                    {data.click_map.map((c, i) => (
                      <div key={i} className="flex items-center justify-between gap-2 text-sm px-3 py-2 rounded-lg" style={{ background: 'var(--theme-bg)' }}>
                        <span className="truncate" style={txt}>{c.url}</span><span className="font-bold shrink-0" style={{ color: 'var(--color-brand-cyan)' }}>{c.clicks}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <button onClick={analyse} disabled={aiBusy} className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-bold text-white disabled:opacity-50 mb-3" style={{ backgroundImage: 'linear-gradient(135deg,#7C3AED,#19CDFF)' }} data-testid="analytics-ai-analyse">
                {aiBusy ? <Loader2 size={15} className="animate-spin" /> : <Wand2 size={15} />}Analyse with AI
              </button>
              {ai && (
                <div className="rounded-xl border p-4 text-sm" style={card} data-testid="ai-analysis">
                  <p className="font-semibold mb-2" style={txt}>{ai.summary}</p>
                  {ai.what_worked?.length > 0 && <><p className="text-xs font-bold uppercase tracking-wide mt-2 mb-1" style={muted}>What worked</p><ul className="list-disc pl-5 space-y-0.5" style={muted}>{ai.what_worked.map((x, i) => <li key={i}>{x}</li>)}</ul></>}
                  {ai.what_to_improve?.length > 0 && <><p className="text-xs font-bold uppercase tracking-wide mt-2 mb-1" style={muted}>To improve</p><ul className="list-disc pl-5 space-y-0.5" style={muted}>{ai.what_to_improve.map((x, i) => <li key={i}>{x}</li>)}</ul></>}
                  {ai.recommendations?.length > 0 && <><p className="text-xs font-bold uppercase tracking-wide mt-2 mb-1" style={muted}>Recommendations</p><ul className="list-disc pl-5 space-y-0.5" style={muted}>{ai.recommendations.map((x, i) => <li key={i}>{x}</li>)}</ul></>}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
