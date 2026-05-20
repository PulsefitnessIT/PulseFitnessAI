/**
 * ListPanel — Iter 216h44
 *
 * Lightweight list-panel skeleton that bundles the four pieces every
 * CRM / Memberships list view duplicates today:
 *
 *   1. Toolbar  — search input + count chip + secondary actions + primary CTA.
 *   2. Loading  — centred spinner.
 *   3. Empty    — wraps `<EmptyState>` so consumers just pass the same props.
 *   4. Rows     — children, fully owned by the caller (rows are too
 *                 domain-specific to abstract — contact rows look nothing
 *                 like plan cards which look nothing like class tiles).
 *
 * Why this scope?
 *   The rows themselves vary too much to standardise without painting
 *   ourselves into a corner. But the surrounding 30-50 LOC of toolbar +
 *   loading + count-chip + search-input repeats verbatim across
 *   CRMContacts, CRMCompanies, MembershipsConsole (Plans/Classes/Ads),
 *   PromotionsTab, etc. Standardising just that surface kills ~80 LOC
 *   per panel without sacrificing flexibility.
 *
 * Props:
 *   - `title`              (optional) — H2 above the toolbar.
 *   - `subtitle`           (optional) — supportive copy below the title.
 *   - `search`             (optional) — `{ value, onChange, placeholder, testId }`.
 *   - `count`              (optional) — `{ value, label, singular?, plural? }`.
 *   - `secondaryActions`   (optional) — array of `<Button>` / `<ExportCsvButton>` nodes.
 *   - `primaryAction`      (optional) — `{ label, icon, onClick, loading?, disabled?, testId? }`.
 *   - `loading`            (bool) — show spinner instead of children.
 *   - `empty`              (optional) — `{ when, icon, title, hint, primaryAction, testId }`.
 *                                       When `when=true` AND children is empty, renders <EmptyState>.
 *   - `toolbarRight`       (optional) — extra JSX appended to the toolbar (filters / view-switchers).
 *   - `className`          (optional) — wrapper override.
 *   - `bodyClassName`      (optional) — override for the inner body wrapper (default `space-y-2`).
 *                                       Use this for grid layouts like Plans / Promotions cards.
 *   - `data-testid`        (optional).
 *   - `children`           — list rows.
 *
 * Usage:
 *   <ListPanel
 *     search={{ value: search, onChange: setSearch, placeholder: 'Search contacts…', testId: 'contact-search' }}
 *     count={{ value: total, label: 'contact' }}
 *     secondaryActions={[<ExportCsvButton key="csv" module="contacts" testId="contacts-export-csv" />]}
 *     primaryAction={{ label: 'New Contact', icon: Plus, onClick: openCreate, testId: 'create-contact-btn' }}
 *     loading={loading}
 *     empty={{ when: contacts.length === 0, icon: Users, title: 'No contacts yet', primaryAction: { label: 'Add your first contact', onClick: openCreate }, testId: 'crm-contacts-empty' }}
 *     data-testid="crm-contacts-list"
 *   >
 *     {contacts.map(ct => <ContactRow key={ct.id} ct={ct} … />)}
 *   </ListPanel>
 */
import React from 'react';
import { Search, Loader2 } from 'lucide-react';
import Button from './Button';
import EmptyState from './EmptyState';

const ListPanel = ({
  title,
  subtitle,
  search,
  count,
  secondaryActions = [],
  primaryAction,
  loading = false,
  empty,
  toolbarRight,
  className = '',
  bodyClassName = 'space-y-2',
  children,
  ...rest
}) => {
  // The empty state should only render when the caller signals it AND
  // there are no rows. We don't auto-count children because callers
  // sometimes pass conditional render trees that yield non-row content.
  // Iter 216h243 — title + subtitle suppression. The platform-wide
  // audit (user prod review) flagged sub-page H1+description blocks
  // as redundant — the parent tab pill already names the section.
  // Suppressed unconditionally here so every Memberships sub-tab that
  // uses ListPanel collapses its header gap in one place. The
  // `title`/`subtitle` props are kept on the API so callers don't need
  // edits and a future toggle can re-expose them if needed.
  const showTitleBlock = false;
  const showEmpty = empty?.when && !loading;
  const hasToolbar = search || count || secondaryActions.length > 0 || primaryAction || toolbarRight;

  return (
    <div className={`space-y-3 ${className}`} {...rest}>
      {/* Title + subtitle — Iter 216h243: suppressed platform-wide. */}
      {showTitleBlock && (title || subtitle) && (
        <div>
          {title && <h2 className="text-base font-bold tracking-tight" style={{ color: 'var(--theme-text)' }}>{title}</h2>}
          {subtitle && <p className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{subtitle}</p>}
        </div>
      )}

      {/* Toolbar */}
      {hasToolbar && (
        <div className="flex items-center justify-between gap-3 flex-wrap" data-testid={rest['data-testid'] ? `${rest['data-testid']}-toolbar` : undefined}>
          {/* Left side: search */}
          {search ? (
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--theme-text-muted)' }} />
              <input
                value={search.value || ''}
                onChange={(e) => search.onChange?.(e.target.value)}
                placeholder={search.placeholder || 'Search…'}
                className="w-full pl-9 pr-3 py-2 text-sm rounded-md"
                style={{
                  background: 'var(--theme-input-bg, #fff)',
                  border: '1px solid var(--theme-border, #E4E4E7)',
                  color: 'var(--theme-text, #18181B)',
                }}
                data-testid={search.testId}
              />
            </div>
          ) : <div />}

          {/* Right side: count + secondary actions + primary action + custom JSX */}
          <div className="flex items-center gap-2 flex-wrap">
            {count != null && (
              <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
                {count.value} {count.value === 1 ? (count.singular || count.label) : (count.plural || `${count.label || 'item'}${count.label?.endsWith('s') ? '' : 's'}`)}
              </p>
            )}
            {secondaryActions.map((node, i) => (
              <React.Fragment key={node.key || i}>{node}</React.Fragment>
            ))}
            {primaryAction && (
              <Button
                variant="primary"
                size="sm"
                onClick={primaryAction.onClick}
                disabled={primaryAction.disabled}
                loading={primaryAction.loading}
                icon={primaryAction.icon}
                data-testid={primaryAction.testId}
              >
                {primaryAction.label}
              </Button>
            )}
            {toolbarRight}
          </div>
        </div>
      )}

      {/* Body */}
      {loading ? (
        <div className="flex items-center justify-center py-12" data-testid={rest['data-testid'] ? `${rest['data-testid']}-loading` : undefined}>
          <Loader2 size={20} className="animate-spin" style={{ color: 'var(--color-brand-cyan, #00D6E0)' }} />
        </div>
      ) : showEmpty ? (
        <EmptyState
          icon={empty.icon}
          title={empty.title}
          hint={empty.hint}
          primaryAction={empty.primaryAction}
          secondaryAction={empty.secondaryAction}
          testId={empty.testId}
        />
      ) : (
        <div className={bodyClassName}>
          {children}
        </div>
      )}
    </div>
  );
};

export default ListPanel;
