import React from 'react';
import { Users, Building2 } from 'lucide-react';

/**
 * Iter 215c — CRM mode segmented control.
 *
 * Only renders when BOTH leisure and business modes are enabled. If
 * only one mode is on, there's nothing to switch between, so the
 * component returns null and the parent shows a static label instead.
 */
const CRMModeSwitcher = ({ modes, activeMode, onChange, brandAccent = 'var(--color-brand-blue)' }) => {
  const both = modes?.leisure && modes?.business;
  if (!both) return null;

  const Item = ({ id, label, Icon }) => {
    const active = activeMode === id;
    return (
      <button
        type="button"
        onClick={() => onChange(id)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-full transition-colors whitespace-nowrap"
        style={
          active
            ? { background: brandAccent, color: '#fff' }
            : { color: 'var(--theme-text-muted)', background: 'transparent' }
        }
        data-testid={`crm-mode-${id}`}
      >
        <Icon size={12} />
        {label}
      </button>
    );
  };

  return (
    <div
      className="inline-flex items-center gap-0.5 p-0.5 rounded-full"
      style={{
        background: 'var(--theme-surface)',
        border: '1px solid var(--theme-border)',
      }}
      role="tablist"
      aria-label="CRM mode"
      data-testid="crm-mode-switcher"
    >
      <Item id="leisure" label="Members" Icon={Users} />
      <Item id="business" label="Corporate" Icon={Building2} />
    </div>
  );
};

export default CRMModeSwitcher;
