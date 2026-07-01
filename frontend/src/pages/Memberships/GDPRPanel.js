/**
 * GDPRPanel — Data Subject Rights (operator owner/manager).
 *
 * Search a member or CRM contact, then either export everything held
 * about them (Subject Access Request, downloaded as JSON) or erase them
 * (Right to be Forgotten — anonymises PII + flags gdpr_erased). Backed by
 * /api/gdpr/*. Erasure is irreversible and logged.
 */
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import {
  ShieldCheck, Search, Download, Trash2, Loader2, User, Building2, AlertTriangle, History, Clock, Flag,
} from 'lucide-react';

export default function GDPRPanel() {
  const [q, setQ] = useState('');
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState('');
  const [confirm, setConfirm] = useState(null);
  const [erasures, setErasures] = useState([]);

  const loadLog = () => api.get('/gdpr/erasures').then(({ data }) => setErasures(data.erasures || [])).catch(() => {});
  useEffect(() => { loadLog(); }, []);

  const search = async (e) => {
    e?.preventDefault();
    if (q.trim().length < 2) return;
    setSearching(true);
    try {
      const { data } = await api.get('/gdpr/search', { params: { q: q.trim() } });
      setResults(data.results || []);
    } catch (err) { notify.error('Search failed.'); }
    setSearching(false);
  };

  const doExport = async (r) => {
    setBusy(`exp-${r.id}`);
    try {
      const { data } = await api.get(`/gdpr/subject/${r.kind}/${r.id}/export`);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `gdpr-export-${r.kind}-${r.id}.json`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      notify.success('Data export downloaded.');
    } catch (err) { notify.error(err.response?.data?.detail || 'Export failed.'); }
    setBusy('');
  };

  const doErase = async (r) => {
    setBusy(`era-${r.id}`);
    try {
      await api.post(`/gdpr/subject/${r.kind}/${r.id}/erase`);
      notify.success(`${r.name} has been erased.`);
      setConfirm(null);
      setResults((rs) => rs.map((x) => (x.id === r.id && x.kind === r.kind ? { ...x, erased: true, name: 'Erased User', email: null } : x)));
      loadLog();
    } catch (err) { notify.error(err.response?.data?.detail || 'Erase failed.'); }
    setBusy('');
  };

  return (
    <div className="space-y-5" data-testid="gdpr-panel">
      <div className="flex items-center gap-2">
        <ShieldCheck size={18} style={{ color: 'var(--color-brand-blue,#1d4ed8)' }} />
        <div>
          <h2 className="text-lg font-extrabold" style={{ color: 'var(--theme-text)' }}>Privacy &amp; GDPR</h2>
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Honour subject access (export) and erasure requests for any member or contact.</p>
        </div>
      </div>

      <form onSubmit={search} className="flex gap-2" data-testid="gdpr-search-form">
        <div className="flex-1 relative">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--theme-text-muted)' }} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or email…" data-testid="gdpr-search-input"
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }} />
        </div>
        <button type="submit" disabled={searching || q.trim().length < 2} data-testid="gdpr-search-btn"
          className="px-4 py-2 rounded-lg text-sm font-bold text-white disabled:opacity-50" style={{ background: 'var(--color-brand-blue,#1d4ed8)' }}>
          {searching ? <Loader2 size={15} className="animate-spin" /> : 'Search'}
        </button>
      </form>

      {results !== null && (
        results.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }} data-testid="gdpr-no-results">No people matched “{q}”.</p>
        ) : (
          <ul className="space-y-2" data-testid="gdpr-results">
            {results.map((r) => (
              <li key={`${r.kind}-${r.id}`} className="rounded-xl border p-3 flex items-center gap-3 flex-wrap" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid={`gdpr-result-${r.id}`}>
                {r.kind === 'member' ? <User size={16} style={{ color: 'var(--color-brand-blue,#1d4ed8)' }} /> : <Building2 size={16} style={{ color: 'var(--color-brand-cyan,#0891b2)' }} />}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold" style={{ color: 'var(--theme-text)' }}>{r.name}</span>
                    <span className="text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded" style={{ background: 'var(--theme-surface-2,#f1f5f9)', color: 'var(--theme-text-muted)' }}>{r.kind}</span>
                    {r.erased && <span className="text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(239,68,68,0.14)', color: '#b91c1c' }}>Erased</span>}
                  </div>
                  <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{r.email || '—'}</p>
                </div>
                {!r.erased && (
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={() => doExport(r)} disabled={busy === `exp-${r.id}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50"
                      style={{ border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`gdpr-export-${r.id}`}>
                      {busy === `exp-${r.id}` ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />} Export
                    </button>
                    <button type="button" onClick={() => setConfirm(r)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white"
                      style={{ background: '#dc2626' }} data-testid={`gdpr-erase-${r.id}`}>
                      <Trash2 size={12} /> Erase
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )
      )}

      {/* Retention review */}
      <RetentionReview />

      {/* Erasure log */}
      {erasures.length > 0 && (
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: 'var(--theme-text-muted)' }}><History size={12} /> Erasure log</h3>
          <ul className="space-y-1" data-testid="gdpr-erasure-log">
            {erasures.slice(0, 10).map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-2 text-xs rounded-lg px-3 py-2" style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
                <span style={{ color: 'var(--theme-text)' }}>{e.original_name} <span style={{ color: 'var(--theme-text-muted)' }}>({e.subject_kind})</span></span>
                <span style={{ color: 'var(--theme-text-muted)' }}>{new Date(e.erased_at).toLocaleDateString('en-GB')} · {e.erased_by}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Confirm erase */}
      {confirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)' }} data-testid="gdpr-confirm">
          <div className="rounded-2xl p-5 max-w-sm w-full" style={{ background: 'var(--theme-surface)' }}>
            <div className="flex items-center gap-2 mb-2"><AlertTriangle size={18} style={{ color: '#dc2626' }} /><h3 className="font-bold" style={{ color: 'var(--theme-text)' }}>Erase {confirm.name}?</h3></div>
            <p className="text-sm mb-4" style={{ color: 'var(--theme-text-muted)' }}>This anonymises their personal data and cannot be undone. Financial records are retained for legal compliance.</p>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setConfirm(null)} className="px-3 py-1.5 rounded-lg text-sm font-semibold" style={{ border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }} data-testid="gdpr-confirm-cancel">Cancel</button>
              <button type="button" onClick={() => doErase(confirm)} disabled={busy === `era-${confirm.id}`} className="px-3 py-1.5 rounded-lg text-sm font-bold text-white disabled:opacity-50" style={{ background: '#dc2626' }} data-testid="gdpr-confirm-erase">
                {busy === `era-${confirm.id}` ? <Loader2 size={14} className="animate-spin" /> : 'Erase permanently'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RetentionReview() {
  const [months, setMonths] = useState(24);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const preview = async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get('/gdpr/retention/preview', { params: { months } });
      setData(d);
    } catch (err) { notify.error('Could not load inactive members.'); }
    setLoading(false);
  };

  const flagAll = async (flag) => {
    const ids = (data?.members || []).filter((m) => (flag ? !m.flagged : m.flagged)).map((m) => m.id);
    if (ids.length === 0) { notify.info(flag ? 'Nothing new to flag.' : 'Nothing flagged to clear.'); return; }
    setBusy(true);
    try {
      await api.post(`/gdpr/retention/${flag ? 'flag' : 'unflag'}`, { member_ids: ids });
      notify.success(flag ? `${ids.length} member${ids.length > 1 ? 's' : ''} flagged for review.` : 'Review flags cleared.');
      setData((prev) => prev && { ...prev, members: prev.members.map((m) => ({ ...m, flagged: flag })) });
    } catch (err) { notify.error('Action failed.'); }
    setBusy(false);
  };

  const fmt = (iso) => { try { return new Date(iso).toLocaleDateString('en-GB'); } catch { return '—'; } };

  return (
    <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="gdpr-retention">
      <div className="flex items-center gap-2 mb-1">
        <Clock size={15} style={{ color: 'var(--color-brand-cyan,#0891b2)' }} />
        <h3 className="text-sm font-extrabold" style={{ color: 'var(--theme-text)' }}>Retention review</h3>
      </div>
      <p className="text-xs mb-3" style={{ color: 'var(--theme-text-muted)' }}>
        Find members with no activity past your retention window (based on last sign-in or sign-up date) so you can review and erase them. Nothing is changed automatically.
      </p>
      <div className="flex items-end gap-2 flex-wrap mb-3">
        <label className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
          <span className="block mb-1 font-bold uppercase tracking-wider">Inactive for (months)</span>
          <input type="number" min={1} max={120} value={months} onChange={(e) => setMonths(Math.max(1, Math.min(120, Number(e.target.value) || 1)))}
            className="w-24 px-3 py-2 text-sm rounded-lg" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="gdpr-retention-months" />
        </label>
        <button type="button" onClick={preview} disabled={loading} data-testid="gdpr-retention-preview-btn"
          className="px-4 py-2 rounded-lg text-sm font-bold text-white disabled:opacity-50" style={{ background: 'var(--color-brand-blue,#1d4ed8)' }}>
          {loading ? <Loader2 size={15} className="animate-spin" /> : 'Preview inactive'}
        </button>
      </div>

      {data && (
        data.total_inactive === 0 ? (
          <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }} data-testid="gdpr-retention-none">No members are inactive past {data.window_months} months. 🎉</p>
        ) : (
          <div data-testid="gdpr-retention-results">
            <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
              <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>
                {data.total_inactive} inactive member{data.total_inactive > 1 ? 's' : ''} <span className="font-normal" style={{ color: 'var(--theme-text-muted)' }}>(showing {data.members.length})</span>
              </p>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => flagAll(true)} disabled={busy} data-testid="gdpr-retention-flag-all"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white disabled:opacity-50" style={{ background: '#d97706' }}>
                  <Flag size={12} /> Flag all for review
                </button>
                <button type="button" onClick={() => flagAll(false)} disabled={busy} data-testid="gdpr-retention-unflag-all"
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50" style={{ border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}>
                  Clear flags
                </button>
              </div>
            </div>
            <ul className="space-y-1 max-h-72 overflow-y-auto">
              {data.members.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-2 text-xs rounded-lg px-3 py-2" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }} data-testid={`gdpr-retention-member-${m.id}`}>
                  <span className="min-w-0 flex-1 truncate" style={{ color: 'var(--theme-text)' }}>
                    {m.name} <span style={{ color: 'var(--theme-text-muted)' }}>· {m.email || '—'}</span>
                  </span>
                  {m.flagged && <span className="text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(217,119,6,0.16)', color: '#b45309' }}>Flagged</span>}
                  <span className="shrink-0" style={{ color: 'var(--theme-text-muted)' }}>last active {fmt(m.last_active)}</span>
                </li>
              ))}
            </ul>
            <p className="text-[11px] mt-2" style={{ color: 'var(--theme-text-muted)' }}>To erase a flagged member, search their name above and use Erase.</p>
          </div>
        )
      )}
    </div>
  );
}
