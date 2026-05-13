/**
 * FindEngineerPanel — iter 216h80.
 *
 * Customer-facing widget that surfaces VERIFIED + STRATEGIC Partner
 * Engineers within reach of the gym's postcode. Lives on the Service
 * Desk Cases tab next to the Engineer Roster (h78).
 *
 * Hard scope:
 *   • GymAxis customers only (backend enforces — Pulse orgs get 403).
 *   • Engineers we surface: status=approved AND
 *     level IN ['verified_partner', 'strategic_partner'].
 *   • We NEVER expose engineer email/phone; instead the customer can
 *     "Request contact" which creates a partner_contact_requests row
 *     the engineer sees on their dashboard.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Search, MapPin, Star, ShieldCheck, BadgeCheck, Loader2, MessageSquare,
  ChevronRight, Send, CheckCircle2, Sparkles,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';

function auth() {
  const t = localStorage.getItem('token');
  return { headers: t ? { Authorization: `Bearer ${t}` } : {} };
}

const LEVEL_LABEL = {
  verified_partner:  { label: 'Verified',  Icon: BadgeCheck, color: '#0ea5e9' },
  strategic_partner: { label: 'Strategic', Icon: ShieldCheck, color: '#7c3aed' },
};
const TIER_BADGE = {
  top_tier:           { cls: 'bg-emerald-100 text-emerald-800', label: 'Top-tier' },
  strong:             { cls: 'bg-sky-100 text-sky-800',         label: 'Strong' },
  solid:              { cls: 'bg-amber-100 text-amber-800',     label: 'Solid' },
  needs_improvement:  { cls: 'bg-rose-100 text-rose-800',       label: 'Building track record' },
  insufficient_data:  { cls: 'bg-zinc-100 text-zinc-600',       label: 'New partner' },
};

export default function FindEngineerPanel({ defaultPostcode = '' }) {
  const [postcode, setPostcode] = useState(defaultPostcode);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [forbidden, setForbidden] = useState(false);
  const [contactBusy, setContactBusy] = useState(null);
  const [contactedIds, setContactedIds] = useState(new Set());

  const search = useCallback(async (pc) => {
    const trimmed = (pc || '').trim();
    if (!trimmed) {
      notify.error('Enter a postcode to find engineers near you');
      return;
    }
    setBusy(true);
    try {
      const r = await axios.get(`${API}/partners/find-engineers`, {
        ...auth(), params: { postcode: trimmed },
      });
      setResult(r.data);
      setForbidden(false);
    } catch (e) {
      if (e?.response?.status === 403) {
        setForbidden(true);
        setResult(null);
      } else {
        notifyApiError(notify, e, 'Search failed');
      }
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    // Auto-load on first mount if we have a default postcode.
    if (defaultPostcode) search(defaultPostcode);
  }, [defaultPostcode, search]);

  const requestContact = async (eng) => {
    setContactBusy(eng.id);
    try {
      const note = window.prompt(
        `Send a short message to ${eng.full_name}? (Optional — they'll see it on their dashboard.)`,
        '',
      );
      if (note === null) { setContactBusy(null); return; }
      await axios.post(`${API}/partners/find-engineers/${eng.id}/request-contact`,
        { note }, auth());
      setContactedIds((s) => new Set(s).add(eng.id));
      notify.success(`Request sent to ${eng.full_name} — they'll reach out via GymAxis.`);
    } catch (e) {
      notifyApiError(notify, e, 'Request failed');
    } finally {
      setContactBusy(null);
    }
  };

  if (forbidden) return null; // Pulse customers see nothing — silent.

  const engineers = result?.engineers || [];
  const inAreaCount = result?.in_area_count || 0;
  const nationwideCount = engineers.length - inAreaCount;

  return (
    <div className="svc-section" data-testid="find-engineer-panel">
      <div className="svc-section-head">
        <div className="flex items-center gap-1.5 text-xs font-bold svc-muted">
          <Search size={13} /> Find an engineer
          <span className="ml-1 px-1.5 py-0.5 rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-200 text-[9px] font-bold uppercase tracking-wider">
            Verified partners
          </span>
        </div>
      </div>

      <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 p-3 my-2 flex items-center gap-2 flex-wrap">
        <MapPin size={13} className="svc-muted shrink-0" />
        <input
          type="text" autoComplete="postal-code"
          value={postcode} onChange={(e) => setPostcode(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === 'Enter' && search(postcode)}
          placeholder="e.g. SW1A 1AA"
          className="svc-input flex-1 min-w-[160px]"
          data-testid="find-engineer-postcode"
        />
        <button onClick={() => search(postcode)} disabled={busy} className="svc-btn-sm svc-btn-primary"
          data-testid="find-engineer-search">
          {busy ? <Loader2 size={11} className="animate-spin" /> : <Search size={11} />}
          Search
        </button>
      </div>

      {result && (
        <>
          {engineers.length === 0 ? (
            <p className="text-xs svc-muted py-3" data-testid="find-engineer-empty">
              No verified Partner Engineers found near <strong>{result.postcode}</strong> yet — the network's still growing. Add an ad-hoc contractor via the Engineer Roster above, or check back as more engineers join.
            </p>
          ) : (
            <>
              {inAreaCount > 0 && (
                <p className="text-[11px] svc-muted mb-2 inline-flex items-center gap-1">
                  <Sparkles size={10} /> {inAreaCount} in your area · {nationwideCount > 0 ? `${nationwideCount} more cover a wide radius` : ''}
                </p>
              )}
              <ul className="space-y-2" data-testid="find-engineer-results">
                {engineers.map((eng) => {
                  const lvl = LEVEL_LABEL[eng.level] || LEVEL_LABEL.verified_partner;
                  const LvlIcon = lvl.Icon;
                  const tier = TIER_BADGE[eng.tier] || TIER_BADGE.insufficient_data;
                  const contacted = contactedIds.has(eng.id);
                  return (
                    <li key={eng.id} className="rounded-lg border border-zinc-200 dark:border-zinc-800 px-3 py-2 bg-white dark:bg-zinc-900"
                      data-testid={`find-engineer-row-${eng.id}`}>
                      <div className="flex items-start justify-between gap-2 flex-wrap">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="text-sm font-bold truncate">{eng.full_name}</span>
                            <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider"
                              style={{ background: lvl.color + '20', color: lvl.color }}>
                              <LvlIcon size={9} /> {lvl.label}
                            </span>
                            <span className={'px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ' + tier.cls}>
                              {tier.label}
                            </span>
                            {eng.in_area
                              ? <span className="text-[9px] font-bold uppercase text-emerald-600">In your area</span>
                              : <span className="text-[9px] svc-muted">Wide-radius</span>}
                          </div>
                          <div className="text-[11px] svc-muted mt-0.5 truncate">
                            {eng.company_name ? eng.company_name + ' · ' : ''}
                            {eng.service_postcode_area} · {eng.travel_radius_km}km radius
                            {eng.jobs_completed_90d ? ` · ${eng.jobs_completed_90d} jobs in 90d` : ''}
                            {eng.rating ? <> · <Star size={9} className="inline fill-amber-400 text-amber-400" /> {eng.rating}</> : ''}
                          </div>
                          {(eng.brands_supported?.length || eng.skills?.length) && (
                            <div className="flex flex-wrap gap-1 mt-1.5">
                              {(eng.brands_supported || []).slice(0, 4).map((b) => (
                                <span key={b} className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 svc-muted">{b}</span>
                              ))}
                              {(eng.skills || []).slice(0, 3).map((s) => (
                                <span key={s} className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 svc-muted">{s}</span>
                              ))}
                            </div>
                          )}
                        </div>
                        {contacted ? (
                          <span className="text-[10px] font-bold text-emerald-600 inline-flex items-center gap-1 px-2 py-1 rounded"
                            data-testid={`find-engineer-contacted-${eng.id}`}>
                            <CheckCircle2 size={10} /> Request sent
                          </span>
                        ) : (
                          <button onClick={() => requestContact(eng)} disabled={contactBusy === eng.id}
                            className="svc-btn-sm svc-btn-primary"
                            data-testid={`find-engineer-contact-${eng.id}`}>
                            {contactBusy === eng.id ? <Loader2 size={10} className="animate-spin" /> : <MessageSquare size={10} />}
                            Request contact
                          </button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  );
}
