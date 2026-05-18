/**
 * CoverageBanner — iter 216h205.
 *
 * Single, shared visual for "what coverage applies to this fault/case?"
 * Used in two surfaces:
 *
 *   1. Operations fault-log dialog — fed from
 *      `GET /api/equipment/{id}/coverage.crm_coverage` (iter h198).
 *   2. Service Desk case-detail drawer — fed from the case's
 *      `source_meta.coverage_*` fields (iter h199).
 *
 * Both surfaces resolve to the SAME data shape via the
 * `utils/coverage.py` resolver on the backend so the badges agree.
 *
 * Variants:
 *   • covered_contract (green)  — under aftersales contract
 *   • covered_warranty (sky)    — manufacturer warranty in date
 *   • expiring_soon  (amber)    — contract ends <90 days
 *   • uncovered      (red)      — chargeable to customer
 */
import React from 'react';
import { ShieldCheck, ShieldAlert, ShieldOff, Clock } from 'lucide-react';

function _formatDDMMYYYY(iso) {
  if (!iso) return '';
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  return `${m[3]}/${m[2]}/${m[1]}`;
}

const TIER_LABEL = {
  platinum: 'Platinum',
  gold: 'Gold',
  silver: 'Silver',
  bronze: 'Bronze',
};

export default function CoverageBanner({
  coverage,
  loading = false,
  testid = 'coverage-banner',
  compact = false,
}) {
  if (loading) {
    return (
      <div
        data-testid={`${testid}-loading`}
        className="flex items-center gap-2 p-2 rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] text-[11px] text-[color:var(--theme-text-muted)] animate-pulse"
      >
        <Clock size={12} /> Checking warranty & contract cover…
      </div>
    );
  }
  if (!coverage) return null;

  // Normalise both data shapes (h198 equipment endpoint vs h199 case
  // source_meta) into a single `state` object so the banner doesn't
  // have to know where it came from.
  const state = _normalise(coverage);
  if (!state) return null;

  const palette = _palette(state.status);
  const Icon = palette.Icon;

  return (
    <div
      data-testid={testid}
      data-coverage-status={state.status}
      className={`rounded-lg border ${palette.frame} px-3 py-2 flex items-start gap-2.5`}
    >
      <Icon size={16} className={`${palette.icon} mt-0.5 shrink-0`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center flex-wrap gap-1.5">
          <span data-testid={`${testid}-title`} className={`text-[12px] font-extrabold ${palette.title}`}>
            {palette.title_text}
          </span>
          {state.contract_tier && (
            <span
              data-testid={`${testid}-tier`}
              className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${palette.pill}`}
            >
              {TIER_LABEL[state.contract_tier] || state.contract_tier}
            </span>
          )}
          {state.expiring_soon && (
            <span
              data-testid={`${testid}-expiring-soon`}
              className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 inline-flex items-center gap-1"
            >
              <Clock size={9} /> Expiring soon
            </span>
          )}
        </div>
        {!compact && (
          <div className="text-[11px] text-[color:var(--theme-text-muted)] mt-0.5 leading-snug">
            {state.contract_number && (
              <span data-testid={`${testid}-number`}>{state.contract_number} · </span>
            )}
            {state.contract_end_date && (
              <span data-testid={`${testid}-end-date`}>
                {state.expiring_soon ? 'Expires ' : 'Valid until '}
                {_formatDDMMYYYY(state.contract_end_date)}
              </span>
            )}
            {state.warranty_expiry && state.status === 'covered_warranty' && (
              <span data-testid={`${testid}-warranty-expiry`}>
                Warranty until {_formatDDMMYYYY(state.warranty_expiry)}
              </span>
            )}
            {state.status === 'uncovered' && (
              <span>No warranty or aftersales contract — work will be billed to the customer.</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function _normalise(c) {
  // Shape 1: equipment coverage endpoint
  //   { crm_coverage: { has_coverage, best: { tier, contract_number, end_date, expiring_soon } },
  //     warranty_active, warranty_expiry, covered, type }
  if ('crm_coverage' in c) {
    const cc = c.crm_coverage || {};
    if (cc.has_coverage && cc.best) {
      return {
        status: cc.best.expiring_soon ? 'expiring_soon' : 'covered_contract',
        contract_tier: cc.best.tier,
        contract_number: cc.best.contract_number,
        contract_end_date: cc.best.end_date,
        expiring_soon: cc.best.expiring_soon,
        warranty_expiry: c.warranty_expiry,
      };
    }
    if (c.warranty_active) {
      return {
        status: 'covered_warranty',
        warranty_expiry: c.warranty_expiry,
      };
    }
    return { status: 'uncovered' };
  }
  // Shape 2: case source_meta (iter h199)
  //   { coverage_status, contract_tier, contract_number, contract_end_date,
  //     contract_expiring_soon, warranty_active, warranty_expiry }
  if (c.coverage_status) {
    if (c.coverage_status === 'covered_contract') {
      return {
        status: c.contract_expiring_soon ? 'expiring_soon' : 'covered_contract',
        contract_tier: c.contract_tier,
        contract_number: c.contract_number,
        contract_end_date: c.contract_end_date,
        expiring_soon: c.contract_expiring_soon,
      };
    }
    if (c.coverage_status === 'covered_warranty' || c.warranty_active) {
      return {
        status: 'covered_warranty',
        warranty_expiry: c.warranty_expiry,
      };
    }
    return { status: 'uncovered' };
  }
  return null;
}

function _palette(status) {
  switch (status) {
    case 'covered_contract':
      return {
        Icon: ShieldCheck,
        frame: 'border-emerald-500/40 bg-emerald-500/10',
        icon: 'text-emerald-300',
        title: 'text-emerald-200',
        title_text: 'Under aftersales contract',
        pill: 'bg-emerald-500/25 text-emerald-200',
      };
    case 'expiring_soon':
      return {
        Icon: ShieldAlert,
        frame: 'border-amber-400/40 bg-amber-500/10',
        icon: 'text-amber-300',
        title: 'text-amber-200',
        title_text: 'Contract expiring soon',
        pill: 'bg-amber-500/25 text-amber-200',
      };
    case 'covered_warranty':
      return {
        Icon: ShieldCheck,
        frame: 'border-sky-500/40 bg-sky-500/10',
        icon: 'text-sky-300',
        title: 'text-sky-200',
        title_text: 'Manufacturer warranty active',
        pill: 'bg-sky-500/25 text-sky-200',
      };
    default:
      return {
        Icon: ShieldOff,
        frame: 'border-red-500/40 bg-red-500/10',
        icon: 'text-red-300',
        title: 'text-red-200',
        title_text: 'No active coverage',
        pill: 'bg-red-500/25 text-red-200',
      };
  }
}
