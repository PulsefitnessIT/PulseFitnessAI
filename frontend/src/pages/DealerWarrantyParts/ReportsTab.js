import { useEffect, useState } from 'react';
import { Download, Sparkles, FileSpreadsheet } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { input } from './shared';

const REPORTS = [
  { id: 'allocations', label: 'Allocations report' },
  { id: 'stock', label: 'Dealer stock report' },
  { id: 'usage', label: 'Parts usage report' },
  { id: 'failures', label: 'Failures by part & country' },
];

export default function ReportsTab() {
  const [dealers, setDealers] = useState([]);
  const [dealerId, setDealerId] = useState('');
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { dpApi.listDealers().then((d) => setDealers(d.dealers || [])); }, []);

  const download = async (report) => {
    try { await dpApi.downloadReport(report); notify.success('Report downloaded'); }
    catch { notify.error('Download failed'); }
  };

  const genSummary = async () => {
    if (!dealerId) { notify.error('Select a dealer'); return; }
    setLoading(true); setSummary(null);
    try {
      const r = await dpApi.aiDealerSummary(dealerId);
      if (!r.available) { notify.error(r.error || 'AI unavailable'); return; }
      setSummary(r);
    } catch (e) { notify.error(e?.response?.data?.detail || 'AI failed'); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-6" data-testid="dp-reports-tab">
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2"><FileSpreadsheet size={15} /> Export reports (CSV)</h3>
        <div className="grid sm:grid-cols-2 gap-3">
          {REPORTS.map((r) => (
            <button key={r.id} data-testid={`dp-report-${r.id}`} onClick={() => download(r.id)}
              className="flex items-center justify-between rounded-lg border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 hover:border-[var(--gx-brand-from)]/40 hover:bg-slate-50 transition-all">
              {r.label} <Download size={15} className="text-[var(--gx-brand-from)]" />
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><Sparkles size={15} /> AI dealer summary</h3>
        <div className="flex items-center gap-2 mb-4">
          <select data-testid="dp-summary-dealer" className={`${input} max-w-xs`} value={dealerId} onChange={(e) => setDealerId(e.target.value)}>
            <option value="">Select dealer…</option>
            {dealers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <button data-testid="dp-gen-summary-btn" onClick={genSummary} disabled={loading || !dealerId}
            className="inline-flex items-center gap-1.5 bg-gradient-to-r from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg disabled:opacity-50">
            <Sparkles size={15} /> {loading ? 'Writing…' : 'Generate summary'}
          </button>
        </div>
        {summary && (
          <div className="space-y-3" data-testid="dp-summary-result">
            <p className="text-xs text-slate-400">AI-generated — review before sharing.</p>
            <p className="text-sm text-slate-700">{summary.summary}</p>
            {(summary.highlights || []).length > 0 && (
              <ul className="list-disc pl-5 text-sm text-slate-600 space-y-1">
                {summary.highlights.map((h, i) => <li key={i}>{h}</li>)}
              </ul>
            )}
            {summary.dealer_note && (
              <div className="rounded-lg bg-[var(--gx-brand-from)]/5 border border-[var(--gx-brand-from)]/20 p-3">
                <div className="text-[10px] uppercase tracking-wide font-semibold text-slate-400 mb-1">Draft dealer note</div>
                <p className="text-sm text-slate-700">{summary.dealer_note}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
