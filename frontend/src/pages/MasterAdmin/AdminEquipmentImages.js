/**
 * Master Admin — Equipment Image Backfill (P3)
 *
 * Observability surface + manual trigger for the AI-powered equipment image
 * fallback pipeline (`utils/equipment_image_cron.py`).
 *
 * The pipeline runs every Monday 03:00 UTC, scans equipment with no
 * user-uploaded photo and no auto image, queries the manufacturer's website
 * for an OG:image, and verifies the match with GPT-4o vision before saving
 * to `equipment.auto_image_url`.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
 ImageIcon, RefreshCw, CheckCircle2, AlertTriangle, Sparkles,
 Loader2, Calendar, History,
} from 'lucide-react';

import { Card } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { useInlineBanner } from '@/components/notifications';

const fmtPct = (num, den) => (den ? `${Math.round((num / den) * 100)}%` : '—');
const fmtDate = (iso) => {
 if (!iso) return '—';
 try { return new Date(iso).toLocaleString(); } catch { return iso; }
};

const StatTile = ({ label, value, accent, testid }) => (
 <Card className="p-5 rounded-xl border-zinc-200" data-testid={testid}>
 <p className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold">{label}</p>
 <p className={`text-2xl font-bold mt-1 ${accent || 'text-zinc-900'}`}>{value}</p>
 </Card>
);

const AdminEquipmentImages = ({ API }) => {
 const [status, setStatus] = useState(null);
 const [loading, setLoading] = useState(true);
 const [running, setRunning] = useState(false);
 const [limit, setLimit] = useState(25);
 const { banner, show, clear } = useInlineBanner();

 const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

 const load = async () => {
 setLoading(true);
 try {
 const { data } = await axios.get(`${API}/master-admin/equipment-images/status`, { headers });
 setStatus(data);
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t load backfill status', detail: err.response?.data?.detail });
 }
 setLoading(false);
 };

 useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

 const runNow = async () => {
 setRunning(true);
 clear();
 try {
 const { data } = await axios.post(
 `${API}/master-admin/equipment-images/backfill-now`,
 { limit },
 { headers },
 );
 show({
 tone: data.matched > 0 ? 'success' : 'warning',
 title: `Backfill complete — ${data.matched} matched / ${data.processed} scanned`,
 detail: data.skipped_no_manufacturer
 ? `${data.skipped_no_manufacturer} skipped (unrecognised manufacturer).`
 : undefined,
 });
 load();
 } catch (err) {
 show({ tone: 'error', title: 'Backfill failed', detail: err.response?.data?.detail });
 }
 setRunning(false);
 };

 if (loading) {
 return (
 <div className="flex items-center justify-center py-16 text-zinc-400" data-testid="equipment-images-loading">
 <Loader2 className="animate-spin mr-2" size={16} /> Loading backfill status…
 </div>
 );
 }

 const t = status?.totals || {};
 const coveragePct = fmtPct((t.with_user_photo || 0) + (t.with_auto_image || 0), t.total_equipment || 0);

 return (
 <div className="space-y-6" data-testid="admin-equipment-images">
 {banner}

 {/* Summary tiles */}
 <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
 <StatTile label="Total equipment" value={t.total_equipment ?? 0} testid="eq-img-total" />
 <StatTile label="With user photo" value={t.with_user_photo ?? 0} accent="text-emerald-700" testid="eq-img-user" />
 <StatTile label="With AI image" value={t.with_auto_image ?? 0} accent="text-blue-700" testid="eq-img-auto" />
 <StatTile label="Vision-verified" value={t.auto_verified_by_vision ?? 0} accent="text-purple-700" testid="eq-img-verified" />
 <StatTile
 label="Missing image"
 value={t.missing_image ?? 0}
 accent={t.missing_image ? 'text-amber-700' : 'text-emerald-700'}
 testid="eq-img-missing"
 />
 </div>

 {/* Coverage banner */}
 <Card className={`p-4 rounded-xl border ${(t.missing_image || 0) === 0 ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'}`}>
 <div className="flex items-start gap-3">
 {(t.missing_image || 0) === 0
 ? <CheckCircle2 className="text-emerald-600 shrink-0 mt-0.5" size={18} />
 : <AlertTriangle className="text-amber-600 shrink-0 mt-0.5" size={18} />}
 <div className="flex-1 min-w-0">
 <p className="text-sm font-semibold text-zinc-900">
 Image coverage: {coveragePct}
 </p>
 <p className="text-xs text-zinc-600 mt-0.5">
 {t.missing_image
 ? `${t.missing_image} pieces of equipment have no image yet. The weekly cron will attempt to lookup manufacturer photos for any with a recognised brand.`
 : 'Every piece of equipment has either a user-uploaded photo or an AI-matched manufacturer image. Nice.'}
 </p>
 </div>
 </div>
 </Card>

 {/* Schedule + manual trigger */}
 <Card className="p-5 rounded-xl border-zinc-200" data-testid="eq-img-schedule">
 <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
 <div className="flex items-start gap-3">
 <Calendar className="text-zinc-400 shrink-0 mt-0.5" size={16} />
 <div>
 <p className="text-sm font-semibold text-zinc-900">Weekly cron — {status?.schedule || 'Mondays 03:00 UTC'}</p>
 <p className="text-xs text-zinc-500 mt-0.5">
 Next run: <span className="font-mono">{fmtDate(status?.next_run_at)}</span> · Last run: <span className="font-mono">{fmtDate(status?.last_run?.at)}</span>
 </p>
 </div>
 </div>
 <div className="flex items-center gap-2">
 <input
 type="number"
 min={1}
 max={200}
 value={limit}
 onChange={(e) => setLimit(Math.min(200, Math.max(1, parseInt(e.target.value || '0', 10) || 25)))}
 className="w-20 px-2 py-1.5 text-sm border border-zinc-200 rounded-md font-mono"
 data-testid="eq-img-limit-input"
 />
 <Button
 size="sm"
 disabled={running}
 onClick={runNow}
 className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
 data-testid="eq-img-run-now-btn"
 >
 {running
 ? <><Loader2 size={13} className="mr-1.5 animate-spin" /> Running…</>
 : <><Sparkles size={13} className="mr-1.5" /> Run backfill now</>}
 </Button>
 </div>
 </div>
 <p className="text-[11px] text-zinc-400 mt-2">
 Manual runs ignore the Monday window so you can backfill on demand. Set the limit (1-200) to control how many items get checked in this run.
 </p>
 </Card>

 {/* Recent runs */}
 <Card className="p-5 rounded-xl border-zinc-200">
 <div className="flex items-center gap-2 mb-3">
 <History className="text-zinc-400" size={14} />
 <h2 className="text-sm font-semibold text-zinc-900">Recent runs</h2>
 <Button size="sm" variant="ghost" onClick={load} className="ml-auto text-xs h-7" data-testid="eq-img-refresh">
 <RefreshCw size={12} className="mr-1" /> Refresh
 </Button>
 </div>
 {(status?.recent_runs || []).length === 0 ? (
 <p className="text-xs text-zinc-400 italic">No backfill runs recorded yet — fire one with "Run backfill now" or wait for Monday's cron.</p>
 ) : (
 <div className="overflow-x-auto">
 <table className="w-full text-sm" data-testid="eq-img-runs-table">
 <thead className="text-[10px] uppercase tracking-wider text-zinc-400 border-b border-zinc-100">
 <tr>
 <th className="text-left py-2 font-medium">When</th>
 <th className="text-left py-2 font-medium">Trigger</th>
 <th className="text-right py-2 font-medium">Scanned</th>
 <th className="text-right py-2 font-medium">Matched</th>
 <th className="text-right py-2 font-medium">Skipped</th>
 <th className="text-right py-2 font-medium">Failures</th>
 </tr>
 </thead>
 <tbody>
 {status.recent_runs.map((run, i) => (
 <tr key={i} className="border-b border-zinc-50 last:border-b-0" data-testid={`eq-img-run-row-${i}`}>
 <td className="py-2 text-zinc-700 font-mono text-xs">{fmtDate(run.at)}</td>
 <td className="py-2">
 <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${
 run.trigger === 'manual' ? 'bg-blue-50 text-blue-700' : 'bg-zinc-100 text-zinc-600'
 }`}>
 {run.trigger || 'weekly'}
 </span>
 </td>
 <td className="py-2 text-right tabular-nums">{run.processed ?? 0}</td>
 <td className="py-2 text-right tabular-nums text-emerald-700 font-medium">{run.matched ?? 0}</td>
 <td className="py-2 text-right tabular-nums text-zinc-500">{run.skipped_no_manufacturer ?? 0}</td>
 <td className="py-2 text-right tabular-nums text-amber-700">{run.failures ?? 0}</td>
 </tr>
 ))}
 </tbody>
 </table>
 </div>
 )}
 </Card>

 {/* How it works footer */}
 <div className="text-[11px] text-zinc-500 leading-relaxed flex items-start gap-2">
 <ImageIcon size={12} className="mt-0.5 shrink-0 text-zinc-400" />
 <p>
 <strong>How the pipeline works:</strong> for any equipment with no user photo and a recognised manufacturer, we search the manufacturer's website for the product page,
 extract its OG:image, and run a 2-stage GPT-4o verification (text title + vision pixel check, confidence ≥0.6).
 Only verified matches are saved to <span className="font-mono">auto_image_url</span>; unverified candidates are dropped.
 Equipment with an unrecognised brand is skipped — add the brand to the manufacturer-domain map to enable lookups.
 </p>
 </div>
 </div>
 );
};

export default AdminEquipmentImages;
