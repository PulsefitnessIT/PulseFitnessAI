/**
 * SiteSwitcher — header dropdown for multi-site Pulse Pro tenants
 * (Iter 216i).
 *
 * Behaviour:
 *   • Shown only when the org has ≥2 sites.
 *   • Lists every site + an "All sites" pseudo-entry that flips the
 *     dashboard into the multi-site overview (consumed by the parent
 *     via `onAllSites`).
 *   • Active site is sourced from the auth context (`activeSite`) and
 *     written back via `setActiveSite`. Persisted in localStorage by the
 *     parent so the choice survives reloads.
 *   • Pure presentational — no API calls; the sites list is whatever
 *     the auth context already loaded.
 */
import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, MapPin, Star, Globe2, Check } from 'lucide-react';
import { useAuth } from '@/App';

const SiteSwitcher = ({ onAllSites, onPickSite, allSitesActive = false }) => {
  const { sites, activeSite, setActiveSite } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Hide the switcher entirely for single-site tenants — there's nothing
  // to switch to. The parent header still renders the company name.
  if (!sites || sites.length < 2) return null;

  const label = allSitesActive
    ? 'All sites'
    : (activeSite?.name || 'Pick a site');

  /**
   * Iter 216bk — picking a specific site after the org was in "All sites"
   * mode used to leave `allSitesActive=true` on the parent, so the
   * dashboard stayed on the estate-wide overview and the click looked
   * dead. The new `onPickSite` callback lets the parent flip it back
   * to false. We still call `setActiveSite` (which the auth context
   * persists to localStorage) so the choice survives a reload.
   */
  const handlePickSite = (site) => {
    setActiveSite(site);
    if (onPickSite) onPickSite(site);
    setOpen(false);
  };

  return (
    <div ref={ref} className="relative" data-testid="site-switcher">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors"
        style={{
          background: 'var(--theme-surface)',
          borderColor: 'var(--theme-border)',
          color: 'var(--theme-text)',
        }}
        data-testid="site-switcher-trigger"
      >
        {allSitesActive ? <Globe2 size={13} /> : <MapPin size={13} className="text-[var(--color-brand-blue)]" />}
        <span className="max-w-[180px] truncate">{label}</span>
        <ChevronDown size={12} className="opacity-60" />
      </button>
      {open && (
        <div
          /* Iter 216bk — dropdown is now viewport-safe. On mobile (<640px)
             we anchor to the left edge of the trigger so the menu opens
             rightward and never clips off the left. On sm+ we keep the
             original right-aligned behaviour. Width caps at the viewport
             minus a 16px gutter so portrait phones never overflow. */
          className="absolute left-0 sm:left-auto sm:right-0 mt-2 rounded-lg shadow-xl z-30 overflow-hidden"
          style={{
            background: 'var(--theme-surface)',
            border: '1px solid var(--theme-border)',
            width: 'min(18rem, calc(100vw - 2rem))',
          }}
          data-testid="site-switcher-menu"
        >
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider font-bold" style={{ color: 'var(--theme-text-muted)' }}>
            Switch site
          </div>
          {/* All-sites pseudo-entry — only relevant when the parent supplies a handler */}
          {onAllSites ? (
            <button
              type="button"
              onClick={() => { onAllSites(); setOpen(false); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-[var(--theme-hover-bg)]"
              style={{ color: 'var(--theme-text)' }}
              data-testid="site-switcher-all"
            >
              <Globe2 size={14} className="text-[var(--color-brand-blue)]" />
              <span className="flex-1 font-semibold">All sites</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-[rgb(var(--rgb-brand-blue)/0.12)] text-[var(--color-brand-blue)] font-bold">overview</span>
              {allSitesActive ? <Check size={14} className="text-emerald-500" /> : null}
            </button>
          ) : null}
          <div className="border-t" style={{ borderColor: 'var(--theme-border-soft)' }} />
          <ul className="max-h-72 overflow-y-auto" data-testid="site-switcher-list">
            {sites.map((s) => {
              const active = !allSitesActive && activeSite?.id === s.id;
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => handlePickSite(s)}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-[var(--theme-hover-bg)]"
                    style={{ color: 'var(--theme-text)' }}
                    data-testid={`site-switcher-item-${s.id}`}
                  >
                    {s.is_head_office
                      ? <Star size={13} className="text-amber-500 shrink-0" />
                      : <MapPin size={13} className="text-[var(--theme-text-muted)] shrink-0" />}
                    <span className="flex-1 truncate">{s.name}</span>
                    {s.equipment_count != null
                      ? <span className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{s.equipment_count} eq</span>
                      : null}
                    {active ? <Check size={14} className="text-emerald-500" /> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
};

export default SiteSwitcher;
