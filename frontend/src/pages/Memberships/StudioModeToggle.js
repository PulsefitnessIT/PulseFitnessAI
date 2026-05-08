/**
 * StudioModeToggle — small pill in the Memberships header that switches
 * between "Full" and "Studio" layouts.
 *
 * Iter 215p. Shown only to owners / managers. When switched ON for the
 * first time, the UI flips to the simplified 5-tab layout AND surfaces
 * the Studio Quickstart on the Start tab.
 */
import React, { useCallback } from 'react';
import { Sparkles } from 'lucide-react';
import { notify } from '@/components/notifications';

export default function StudioModeToggle({ studioMode, toggle, saving, loading }) {
  const onClick = useCallback(async () => {
    const r = await toggle(!studioMode);
    if (!r.ok) notify.error('Studio Mode', r.error || 'Failed to toggle.');
    else notify.success(
      studioMode ? 'Full layout restored' : 'Studio Mode on',
      studioMode ? 'All tabs are back.' : 'Simplified layout for 1-3 person teams.',
    );
  }, [studioMode, toggle]);

  if (loading) return null;

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={saving}
      className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-full border text-xs font-bold uppercase tracking-wider transition-colors ${
        studioMode
          ? 'bg-[var(--color-brand-cyan)] text-[var(--color-ink)] border-transparent'
          : 'border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)] hover:text-[color:var(--theme-text)]'
      } disabled:opacity-50`}      title={studioMode ? 'Switch back to full layout' : 'Simplify for a small studio'}
      data-testid="studio-mode-toggle"
    >
      <Sparkles size={12} />
      {studioMode ? 'Studio Mode' : 'Studio Mode off'}
    </button>
  );
}
