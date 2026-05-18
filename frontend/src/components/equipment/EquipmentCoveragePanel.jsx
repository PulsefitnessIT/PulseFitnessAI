/**
 * EquipmentCoveragePanel — Phase 2 of Ops↔CRM↔ServiceDesk link.
 *
 * Iter 216h198 — Lee's ask: "we don't have anywhere where we can
 * manage the warranty/contracts on the machine on site". This panel
 * lives at the top of the Operations Equipment Detail modal and shows
 * the active CRM aftersales contract (tier, end date, coverage type)
 * plus a click-through to the contract in CRM. Engineers can now tell
 * at a glance whether a fix is in-warranty before they pick up tools.
 *
 * Data shape comes from `GET /api/equipment/{id}/coverage` — the same
 * endpoint backs both Operations + Service Desk so the three modules
 * never disagree.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { ShieldCheck, ShieldX, Clock, ExternalLink, Loader2 } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';

const TIER_LABELS = {
  warranty: 'Manufacturer warranty',
  bronze: 'Bronze',
  silver: 'Silver',
  gold: 'Gold',
  platinum: 'Platinum',
  bespoke: 'Bespoke',
};

const COVERAGE_TYPE_LABELS = {
  full: 'Full coverage (parts + labour)',
  parts_only: 'Parts only',
  labour_only: 'Labour only',
  inspection: 'Inspection only',
};

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return iso.split('-').reverse().join('/');
  } catch {
    return iso;
  }
}

export default function EquipmentCoveragePanel({ equipmentId, onOpenInCRM }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!equipmentId) return;
    const token = localStorage.getItem('token');
    setLoading(true);
    axios
      .get(`${API}/equipment/${equipmentId}/coverage`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [equipmentId]);

  if (loading) {
    return (
      <div className="rounded-lg border border-[var(--theme-border)] bg-[var(--theme-surface)] p-3 flex items-center gap-2 text-xs"
        data-testid="equipment-coverage-loading"
        style={{ color: 'var(--theme-text-muted)' }}>
        <Loader2 size={12} className="animate-spin" /> Checking contract coverage…
      </div>
    );
  }

  if (!data) return null;

  const best = data.crm_coverage?.best;
  const hasCrmCoverage = !!data.crm_coverage?.has_coverage;
  const warrantyOnly = !hasCrmCoverage && data.warranty_active;
  const noCoverage = !hasCrmCoverage && !data.warranty_active;

  // Visual variants — green for covered, amber for expiring < 90d,
  // red for uncovered.
  const expiringSoon = !!best?.expiring_soon;
  const variant = hasCrmCoverage
    ? expiringSoon ? 'amber' : 'green'
    : warrantyOnly ? 'green' : 'red';

  const styles = {
    green: { bg: 'rgba(34, 197, 94, 0.10)', border: 'rgba(34, 197, 94, 0.30)', icon: 'var(--color-success-alt)' },
    amber: { bg: 'rgba(245, 158, 11, 0.10)', border: 'rgba(245, 158, 11, 0.30)', icon: 'var(--color-warning)' },
    red:   { bg: 'rgba(239, 68, 68, 0.10)',  border: 'rgba(239, 68, 68, 0.30)',  icon: 'var(--color-danger-alt)' },
  }[variant];

  return (
    <div
      className="rounded-lg border p-3 mb-3"
      style={{ background: styles.bg, borderColor: styles.border }}
      data-testid="equipment-coverage-panel"
    >
      <div className="flex items-start gap-3">
        <div className="shrink-0 mt-0.5" style={{ color: styles.icon }}>
          {noCoverage ? <ShieldX size={20} /> : <ShieldCheck size={20} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>
              {hasCrmCoverage && (
                <>Covered · <span style={{ color: styles.icon }}>{TIER_LABELS[best.tier] || best.tier?.toUpperCase()}</span></>
              )}
              {!hasCrmCoverage && warrantyOnly && (
                <>In manufacturer warranty</>
              )}
              {noCoverage && <>No active coverage</>}
            </h4>
            {expiringSoon && best && (
              <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded"
                style={{ background: 'rgba(245, 158, 11, 0.20)', color: 'var(--color-warning)' }}
                data-testid="coverage-expiring-badge">
                <Clock size={9} className="inline mr-0.5" /> Expiring {best.days_until_expiry}d
              </span>
            )}
          </div>
          {/* Active CRM contract row */}
          {hasCrmCoverage && best && (
            <div className="mt-1 text-xs space-y-0.5" style={{ color: 'var(--theme-text-muted)' }}>
              <div>
                <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>
                  {best.contract_title || best.contract_number || 'Aftersales contract'}
                </span>
                {best.contract_number && <span className="opacity-70"> · {best.contract_number}</span>}
              </div>
              <div data-testid="coverage-type-label">
                {COVERAGE_TYPE_LABELS[best.coverage_type] || best.coverage_type}
                {' · '}cover until <span className="font-mono">{fmtDate(best.end_date)}</span>
              </div>
              {best.exclusions && (
                <div className="text-[10px] italic">Exclusions: {best.exclusions}</div>
              )}
              {data.crm_coverage.all_contracts.length > 1 && (
                <div className="text-[10px] opacity-70">
                  +{data.crm_coverage.all_contracts.length - 1} more active contract{data.crm_coverage.all_contracts.length > 2 ? 's' : ''} on this equipment
                </div>
              )}
            </div>
          )}
          {/* Manufacturer warranty fallback */}
          {!hasCrmCoverage && warrantyOnly && (
            <p className="mt-1 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
              Manufacturer warranty expires <span className="font-mono">{fmtDate(data.warranty_expiry)}</span>
              {' '}({data.warranty_days_remaining}d remaining). No aftersales contract on file.
            </p>
          )}
          {/* No coverage at all */}
          {noCoverage && (
            <p className="mt-1 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
              This equipment isn't covered by a manufacturer warranty or an active aftersales contract.
              {' '}<span style={{ color: 'var(--color-danger-alt)' }} className="font-semibold">
                Any callouts will be billable.
              </span>
            </p>
          )}
        </div>
        {hasCrmCoverage && best?.contract_id && (
          <button
            type="button"
            onClick={() => {
              if (onOpenInCRM) return onOpenInCRM(best.contract_id);
              window.open(`/crm/contracts/${best.contract_id}`, '_blank');
            }}
            className="text-[11px] font-semibold flex items-center gap-1 px-2 py-1 rounded shrink-0"
            style={{ color: 'var(--color-info-ios)', border: '1px solid var(--color-info-ios)' }}
            data-testid="coverage-open-in-crm"
          >
            View in CRM <ExternalLink size={10} />
          </button>
        )}
      </div>
    </div>
  );
}
