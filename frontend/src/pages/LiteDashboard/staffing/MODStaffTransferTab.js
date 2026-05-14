/**
 * MOD Staff Transfer — Pulse Fitness Staffing Console tab.
 * (Iter 216h113e).
 *
 * Lets a MOD site operator move one of their personnel between sites
 * within the same MOD force (Army↔Army, RAF↔RAF, Navy↔Navy). The
 * backend enforces the force-lock; cross-force transfers are
 * rejected with a 403.
 *
 * UX:
 *   1. Search by name or email (debounced, force-scoped).
 *   2. Click a result → review their current site + role.
 *   3. Pick a destination from a dropdown of same-force sites.
 *   4. Optional transfer reason → confirm.
 *   5. Toast + refresh on success.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Users, Search, ArrowRightLeft, Loader2, MapPin, Shield, X, CheckCircle2,
  Mail, Phone,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function MODStaffTransferTab({ headers }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [force, setForce] = useState(null);

  const [targets, setTargets] = useState([]);
  const [currentSiteName, setCurrentSiteName] = useState('');

  // Modal / selection state
  const [selected, setSelected] = useState(null);          // staff record
  const [destSiteId, setDestSiteId] = useState('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // ── Load destination site list ─────────────────────────────────
  const loadTargets = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/mod/site/transfer-targets`, { headers });
      setTargets(r.data?.sites || []);
      setForce(r.data?.force || null);
      setCurrentSiteName(r.data?.current_site_name || '');
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Could not load destination sites';
      toast.error(typeof msg === 'string' ? msg : 'Could not load destination sites');
    }
  }, [headers]);

  useEffect(() => { loadTargets(); }, [loadTargets]);

  // ── Debounced search ───────────────────────────────────────────
  useEffect(() => {
    const handle = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await axios.get(`${API}/mod/site/staff-search`, {
          headers,
          params: { q: query },
        });
        setResults(r.data?.results || []);
        setForce(r.data?.force || force);
      } catch (e) {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 220);
    return () => clearTimeout(handle);
  }, [query, headers, force]);

  // ── Submit transfer ────────────────────────────────────────────
  const submit = async () => {
    if (!selected) return;
    if (!destSiteId) { toast.error('Pick a destination site'); return; }
    if (destSiteId === selected.current_site_id) {
      toast.error('Destination is the same as current site');
      return;
    }
    setSubmitting(true);
    try {
      const r = await axios.post(
        `${API}/mod/site/staff/transfer`,
        {
          staff_id: selected.id,
          destination_site_id: destSiteId,
          reason: reason.trim() || undefined,
        },
        { headers },
      );
      toast.success(`${r.data?.staff_name || 'Staff'} transferred to ${r.data?.to_site_name}`);
      setSelected(null);
      setDestSiteId('');
      setReason('');
      // Refresh the result list (their site_name will have changed)
      const re = await axios.get(`${API}/mod/site/staff-search`, { headers, params: { q: query } });
      setResults(re.data?.results || []);
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Transfer failed';
      toast.error(typeof msg === 'string' ? msg : 'Transfer failed');
    } finally {
      setSubmitting(false);
    }
  };

  const targetSiteName = useMemo(() => {
    const s = targets.find((t) => t.id === destSiteId);
    return s ? s.name : null;
  }, [destSiteId, targets]);

  return (
    <div className="space-y-5" data-testid="mod-staff-transfer-tab">
      {/* Header */}
      <div className="rounded-2xl border p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)' }}>
        <div className="flex items-start gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: 'rgba(102,204,255,0.10)' }}
          >
            <ArrowRightLeft size={18} style={{ color: '#33B8FF' }} />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-base font-bold" style={{ color: 'var(--theme-text)' }}>Staff transfers</h3>
              {force && (
                <span
                  className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(102,204,255,0.12)', color: '#33B8FF', letterSpacing: '0.16em' }}
                  data-testid="mod-transfer-force-badge"
                >
                  <Shield size={10} className="inline mr-1" />
                  {force} only
                </span>
              )}
            </div>
            <p className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>
              Move a staff member from any {force ? force.toLowerCase() : 'force'} site to
              {currentSiteName ? ` ${currentSiteName}` : ' your site'}, or send one of your
              team to another {force ? force.toLowerCase() : 'force'} site. Cross-force
              transfers are blocked.
            </p>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="rounded-2xl border p-5" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)' }}>
        <label className="block">
          <span className="text-[11px] uppercase font-bold tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>
            Find a staff member
          </span>
          <div className="mt-2 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: '#A2ACAB' }} />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Type a name or email…"
              className="w-full pl-9 pr-9 py-2.5 rounded-lg text-sm border focus:outline-none focus:border-cyan-400 transition-colors"
              style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }}
              data-testid="mod-transfer-search"
              autoComplete="off"
            />
            {searching && (
              <Loader2 size={14} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin" style={{ color: '#A2ACAB' }} />
            )}
          </div>
        </label>

        {/* Results */}
        <div className="mt-4 space-y-2">
          {!searching && results.length === 0 && (
            <div className="text-center py-8 text-sm" style={{ color: 'var(--theme-text-muted)' }} data-testid="mod-transfer-empty">
              {query.trim()
                ? `No staff matching “${query.trim()}” in the ${force || ''} force.`
                : `Start typing to search the ${force || ''} force directory.`}
            </div>
          )}
          {results.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => { setSelected(r); setDestSiteId(''); setReason(''); }}
              className="w-full text-left rounded-xl border bg-white px-4 py-3 hover:border-cyan-400 transition-colors flex items-start gap-3"
              style={{ borderColor: 'var(--theme-border, #E4E4E7)' }}
              data-testid={`mod-transfer-result-${r.id}`}
            >
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-xs font-bold shrink-0" style={{ background: 'rgba(102,204,255,0.10)', color: '#33B8FF' }}>
                {(r.name || '?').split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-sm" style={{ color: 'var(--theme-text)' }}>{r.name}</span>
                  {r.is_own_site && (
                    <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded" style={{ background: '#FEF3C7', color: '#92400E' }}>
                      Your site
                    </span>
                  )}
                </div>
                <div className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                  {r.role || '—'}
                </div>
                <div className="flex items-center gap-3 text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                  <span className="inline-flex items-center gap-1">
                    <MapPin size={11} /> {r.current_site_name}
                  </span>
                  {r.email && (
                    <span className="inline-flex items-center gap-1 hidden sm:inline-flex">
                      <Mail size={11} /> {r.email}
                    </span>
                  )}
                </div>
              </div>
              <ArrowRightLeft size={14} className="shrink-0 mt-1" style={{ color: '#33B8FF' }} />
            </button>
          ))}
        </div>
      </div>

      {/* Transfer modal */}
      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.45)' }}
          data-testid="mod-transfer-modal"
        >
          <div className="rounded-2xl w-full max-w-lg p-6 relative" style={{ background: 'var(--theme-surface)' }}>
            <button
              type="button"
              onClick={() => { setSelected(null); setReason(''); setDestSiteId(''); }}
              className="absolute right-4 top-4 p-1.5 rounded-full"
              style={{ background: 'transparent' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--theme-bg)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
              data-testid="mod-transfer-close"
              aria-label="Close"
            >
              <X size={16} />
            </button>

            <div className="flex items-start gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: 'rgba(102,204,255,0.12)' }}>
                <Users size={18} style={{ color: '#33B8FF' }} />
              </div>
              <div className="flex-1">
                <h4 className="text-base font-bold" style={{ color: 'var(--theme-text)' }}>Transfer {selected.name}</h4>
                <p className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                  Currently at <strong>{selected.current_site_name}</strong>{selected.current_branch ? ` · ${selected.current_branch}` : ''}
                </p>
              </div>
            </div>

            {/* Contact line */}
            {(selected.email || selected.phone) && (
              <div className="mb-4 rounded-lg px-3 py-2 text-xs flex items-center gap-3" style={{ background: '#F8F9FA', color: 'var(--theme-text-muted)' }}>
                {selected.email && <span className="inline-flex items-center gap-1"><Mail size={11} /> {selected.email}</span>}
                {selected.phone && <span className="inline-flex items-center gap-1"><Phone size={11} /> {selected.phone}</span>}
              </div>
            )}

            <label className="block">
              <span className="text-[11px] uppercase font-bold tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>
                Destination site ({force} only)
              </span>
              <select
                value={destSiteId}
                onChange={(e) => setDestSiteId(e.target.value)}
                className="mt-1.5 w-full px-3 py-2.5 rounded-lg text-sm border focus:outline-none focus:border-cyan-400 transition-colors"
                style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }}
                data-testid="mod-transfer-destination"
              >
                <option value="">— Choose a site —</option>
                {targets
                  .filter((t) => t.id !== selected.current_site_id)
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}{t.branch ? ` — ${t.branch}` : ''}
                    </option>
                  ))}
              </select>
            </label>

            <label className="block mt-4">
              <span className="text-[11px] uppercase font-bold tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>
                Reason (optional)
              </span>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
                maxLength={400}
                placeholder="e.g. Reassignment to PT team at Vimy"
                className="mt-1.5 w-full px-3 py-2.5 rounded-lg text-sm border focus:outline-none focus:border-cyan-400 transition-colors resize-none"
                style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }}
                data-testid="mod-transfer-reason"
              />
            </label>

            {targetSiteName && (
              <div className="mt-4 rounded-lg px-3 py-2.5 text-xs flex items-start gap-2" style={{ background: 'rgba(102,204,255,0.08)', border: '1px solid rgba(102,204,255,0.25)' }}>
                <CheckCircle2 size={14} style={{ color: '#33B8FF' }} className="shrink-0 mt-0.5" />
                <span style={{ color: 'var(--theme-text)' }}>
                  <strong>{selected.name}</strong> will be moved from <strong>{selected.current_site_name}</strong> to <strong>{targetSiteName}</strong>. Their fault history stays with them.
                </span>
              </div>
            )}

            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => { setSelected(null); setReason(''); setDestSiteId(''); }}
                className="px-4 py-2 rounded-lg text-sm font-semibold"
                style={{ color: 'var(--theme-text-muted)' }}
                data-testid="mod-transfer-cancel"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={submit}
                disabled={submitting || !destSiteId}
                className="px-4 py-2 rounded-lg text-sm font-bold inline-flex items-center gap-2 disabled:opacity-50"
                style={{ background: '#66CCFF', color: '#212721' }}
                data-testid="mod-transfer-confirm"
              >
                {submitting ? <Loader2 size={14} className="animate-spin" /> : <ArrowRightLeft size={14} />}
                Confirm transfer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
