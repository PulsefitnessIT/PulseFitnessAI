/**
 * CRM Phase 3 panels (Iter 216h226).
 *
 * - CrossModuleTimeline: unified timeline (CRM + Service + Operations + Invoices).
 * - EnrichFromWebsiteButton: triggers website meta scrape to fill company metadata.
 * - AINextActionCard: AI next-best-action card for an opportunity.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Sparkles, Globe, FileText, Phone, Mail, Calendar, CheckCircle, Activity,
  AlertCircle, Wrench, Receipt, RefreshCw, ChevronRight,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

const MODULE_META = {
  crm:        { color: 'var(--color-info-ios)',       label: 'CRM' },
  service:    { color: 'var(--color-accent-amber)',   label: 'Service' },
  operations: { color: 'var(--color-accent-magenta)', label: 'Operations' },
  billing:    { color: 'var(--color-success-alt)',    label: 'Billing' },
};
const TYPE_ICONS = {
  note: FileText, call: Phone, email: Mail, meeting: Calendar, task: CheckCircle,
  system: Activity, ai_suggestion: Sparkles, case: Wrench, fault: AlertCircle,
  engineer_visit: Wrench, invoice: Receipt,
};

export function CrossModuleTimeline({ companyId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('all');

  const load = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/crm/companies/${companyId}/timeline?limit=80`, auth());
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load timeline');
    } finally { setLoading(false); }
  }, [companyId]);

  useEffect(() => { load(); }, [load]);

  const rows = (data?.rows || []).filter(r => filter === 'all' || r.module === filter);
  const modules = data?.modules_present || [];

  return (
    <div data-testid="crm-cross-module-timeline">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <button onClick={() => setFilter('all')} className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${filter === 'all' ? 'text-white' : ''}`}
          style={filter === 'all' ? { background: 'var(--color-brand-blue)', borderColor: 'var(--color-brand-blue)' } : { borderColor: 'var(--theme-border)' }}>
          All
        </button>
        {modules.map(m => (
          <button key={m} onClick={() => setFilter(m)} className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${filter === m ? 'text-white' : ''}`}
            style={filter === m ? { background: MODULE_META[m]?.color || 'var(--color-brand-blue)', borderColor: 'transparent' } : { borderColor: 'var(--theme-border)' }}>
            {MODULE_META[m]?.label || m}
          </button>
        ))}
        <button onClick={load} disabled={loading} className="ml-auto h-7 w-7 rounded-full border border-[color:var(--theme-border)] flex items-center justify-center" aria-label="Refresh" type="button">
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>
      {loading && !data ? (
        <p className="text-sm text-[color:var(--theme-text-muted)] py-6 text-center">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-[color:var(--theme-text-muted)] py-6 text-center">No activity from any module yet.</p>
      ) : (
        <div className="space-y-0">
          {rows.map((r, i) => {
            const Icon = TYPE_ICONS[r.type] || Activity;
            const colour = MODULE_META[r.module]?.color || 'var(--color-text-faint-alt)';
            const time = r.created_at ? new Date(r.created_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
            return (
              <div key={`${r.ref_id || ''}-${i}`} className="flex gap-3 relative">
                {i < rows.length - 1 && <div className="absolute left-3.5 top-8 w-px h-full" style={{ background: 'var(--theme-border)' }} />}
                <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10" style={{ background: `${colour}20` }}>
                  <Icon size={12} style={{ color: colour }} />
                </div>
                <div className="flex-1 pb-4 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded" style={{ background: `${colour}15`, color: colour }}>
                      {MODULE_META[r.module]?.label || r.module}
                    </span>
                    <p className="text-sm font-semibold truncate" style={{ color: 'var(--theme-text)' }}>{r.title}</p>
                    {time && <span className="text-[10px] shrink-0" style={{ color: 'var(--theme-text-muted)' }}>{time}</span>}
                  </div>
                  {r.body && <p className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{r.body}</p>}
                  {r.owner && <p className="text-[10px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>by {r.owner}</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function EnrichFromWebsiteButton({ companyId, onEnriched }) {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/crm/companies/${companyId}/enrich-from-website`, {}, auth());
      const filled = r.data.enriched || [];
      if (filled.length === 0) toast.message('Website fetched — nothing new to fill (all fields already populated).');
      else toast.success(`Enriched: ${filled.join(', ')}`);
      onEnriched?.(r.data.values || {});
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Enrichment failed');
    } finally { setBusy(false); }
  };
  return (
    <button onClick={run} disabled={busy} className="px-3 py-1.5 text-xs font-medium rounded-md border inline-flex items-center gap-1.5"
      style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
      data-testid="enrich-from-website-btn" type="button">
      <Globe size={12} className={busy ? 'animate-spin' : ''} /> {busy ? 'Enriching…' : 'Enrich from website'}
    </button>
  );
}

const URGENCY_TONE = {
  high:   { bg: 'rgba(239,68,68,0.10)',  fg: 'var(--color-danger)',  label: 'HIGH' },
  medium: { bg: 'rgba(245,158,11,0.10)', fg: 'var(--color-warning)', label: 'MED' },
  low:    { bg: 'rgba(34,197,94,0.10)',  fg: 'var(--color-success)', label: 'LOW' },
};

export function AINextActionCard({ opportunityId, onActOnSuggestion }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(async () => {
    if (!opportunityId) return;
    setLoading(true);
    setError(null);
    try {
      const r = await axios.post(`${API}/crm/opportunities/${opportunityId}/ai/next-action`, {}, auth());
      setData(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'AI service unavailable');
    } finally { setLoading(false); }
  }, [opportunityId]);

  const urgency = URGENCY_TONE[data?.urgency] || URGENCY_TONE.medium;

  return (
    <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="ai-next-action-card">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Sparkles size={14} style={{ color: 'var(--color-brand-blue)' }} />
          <h3 className="text-sm font-extrabold" style={{ color: 'var(--theme-text)' }}>AI · Next best action</h3>
        </div>
        <button onClick={run} disabled={loading} className="text-[11px] font-bold px-2.5 py-1 rounded-full inline-flex items-center gap-1.5"
          style={{ background: 'var(--color-brand-blue)', color: 'white' }} data-testid="ai-next-action-run" type="button">
          {loading ? <RefreshCw size={11} className="animate-spin" /> : <Sparkles size={11} />} {data ? 'Re-run' : 'Suggest'}
        </button>
      </div>
      {error ? (
        <p className="text-xs text-red-500">{error}</p>
      ) : !data ? (
        <p className="text-xs text-[color:var(--theme-text-muted)]">Press “Suggest” to ask the AI what to do next on this deal.</p>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-base font-extrabold" style={{ color: 'var(--theme-text)' }}>{data.action}</span>
            {data.target_role && <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded" style={{ background: 'var(--theme-border)', color: 'var(--theme-text)' }}>{data.target_role}</span>}
            <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ml-auto" style={{ background: urgency.bg, color: urgency.fg }}>{urgency.label}</span>
            <span className="text-[10px] uppercase tracking-wider text-[color:var(--theme-text-muted)]">{data.confidence} confidence</span>
          </div>
          <p className="text-xs" style={{ color: 'var(--theme-text)' }}>{data.reasoning}</p>
          {data.suggested_subject || data.suggested_body ? (
            <div className="rounded-lg border border-dashed border-[color:var(--theme-border)] p-3 space-y-1">
              {data.suggested_subject && <p className="text-[11px] font-bold" style={{ color: 'var(--theme-text)' }}>Subject: {data.suggested_subject}</p>}
              {data.suggested_body && <p className="text-xs whitespace-pre-wrap" style={{ color: 'var(--theme-text-muted)' }}>{data.suggested_body}</p>}
              {onActOnSuggestion && (
                <button onClick={() => onActOnSuggestion(data)} className="text-[11px] font-bold inline-flex items-center gap-1" style={{ color: 'var(--color-brand-blue)' }} type="button">
                  Use this draft <ChevronRight size={11} />
                </button>
              )}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
