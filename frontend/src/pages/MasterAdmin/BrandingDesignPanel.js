import { useState, lazy, Suspense } from 'react';
import { Palette, LayoutTemplate } from 'lucide-react';

// Merged single source of truth for brand + design tooling — replaces the
// previously separate "Theme settings" and "Design system" nav entries.
// The Design system reference is platform-internal, so the inner tab is
// hidden for delegated Pulse admins via `showDesignSystem`.
const ThemeSettingsPanel = lazy(() => import('./ThemeSettingsPanel'));
const DesignSystemPage = lazy(() => import('./DesignSystemPage'));

export default function BrandingDesignPanel({ initialTab = 'theme', showDesignSystem = true }) {
  const tabs = [
    { id: 'theme', label: 'Theme & branding', icon: Palette },
    ...(showDesignSystem ? [{ id: 'design', label: 'Design system', icon: LayoutTemplate }] : []),
  ];
  const [tab, setTab] = useState(() => (initialTab === 'design' && showDesignSystem ? 'design' : 'theme'));
  const showDesign = tab === 'design' && showDesignSystem;
  return (
    <div data-testid="branding-design-panel">
      <div className="subtab-bar mb-6 flex-wrap" data-testid="branding-design-tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`subtab-pill ${tab === t.id ? 'is-active' : ''}`}
            data-testid={`branding-design-tab-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <Suspense fallback={null}>
        {showDesign ? <DesignSystemPage /> : <ThemeSettingsPanel />}
      </Suspense>
    </div>
  );
}
