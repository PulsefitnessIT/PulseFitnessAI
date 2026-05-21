/**
 * TenderCoveragePanel.js (iter 216h279)
 *
 * Rep-by-rep £ summary of tenders + pipeline that fall inside their
 * mapped territories. Reads /api/crm/territories/coverage-report,
 * which already aggregates against the same `territory_id` field
 * the auto-assign engine writes — so this stays in lockstep with
 * whatever the map currently shows.
 *
 * Shown above the tender list on the CRM Tenders page when any
 * territory is configured. Hides itself silently when no rows come
 * back (i.e. customer hasn't enabled the Map yet) so it never
 * shouts at an unconfigured tenant.
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Map as MapIcon, TrendingUp, UserCog, Hammer, ChevronDown, ChevronRight } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

const ROLE_LABELS = { sales_manager: 'Sales Manager', engineer: 'Engineer', both: 'Manager + Engineer' };
const ROLE_ICONS = { sales_manager: UserCog, engineer: Hammer, both: UserCog };

const fmt = (n) => new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 0 }).format(n || 0);

export default function TenderCoveragePanel() {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(true);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/crm/territories/coverage-report`, auth());
        if (!cancel) setData(r.data);
      } catch { /* coverage report is optional — fail quietly */ }
    })();
    return () => { cancel = true; };
  }, []);

  const rows = data?.rows || [];
  const totals = data?.totals || { tenders: 0, value: 0 };
  const totalRegions = useMemo(() => rows.reduce((acc, r) => acc + (r.region_count || 0), 0), [rows]);

  if (!rows.length) return null;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white mb-3 overflow-hidden" data-testid="tender-coverage-panel">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-zinc-50/60 text-left"
        data-testid="tender-coverage-toggle"
      >
        <MapIcon size={15} className="text-zinc-500" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-zinc-900">Territory Coverage</p>
          <p className="text-[11px] text-zinc-500">
            {rows.length} {rows.length === 1 ? 'rep' : 'reps'} covering {totalRegions} regions · {totals.tenders} tenders · {fmt(totals.value)} in flight
          </p>
        </div>
        {open ? <ChevronDown size={14} className="text-zinc-400" /> : <ChevronRight size={14} className="text-zinc-400" />}
      </button>
      {open && (
        <div className="border-t border-zinc-100 divide-y divide-zinc-100" data-testid="tender-coverage-rows">
          {rows.map((r) => {
            const Icon = ROLE_ICONS[r.role] || UserCog;
            const isExpanded = expanded === r.user_id;
            return (
              <div key={r.user_id} data-testid={`tender-coverage-row-${r.user_id}`}>
                <button
                  type="button"
                  onClick={() => setExpanded(isExpanded ? null : r.user_id)}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-zinc-50/60"
                >
                  <span className="w-3 h-3 rounded-full border border-zinc-300" style={{ backgroundColor: r.colour_hex }} />
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] font-semibold text-zinc-900 truncate">{r.full_name}</p>
                    <p className="text-[10px] text-zinc-500 inline-flex items-center gap-1">
                      <Icon size={10} /> {ROLE_LABELS[r.role]} · {r.region_count} {r.region_count === 1 ? 'region' : 'regions'}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-[13px] font-bold text-zinc-900 inline-flex items-center gap-1">
                      <TrendingUp size={11} className="text-emerald-600" /> {fmt(r.tender_value)}
                    </p>
                    <p className="text-[10px] text-zinc-500">{r.tender_count} tenders · pipeline {fmt(r.pipeline_value)}</p>
                  </div>
                  {isExpanded ? <ChevronDown size={12} className="text-zinc-400" /> : <ChevronRight size={12} className="text-zinc-400" />}
                </button>
                {isExpanded && (
                  <div className="px-12 pb-2.5 flex flex-wrap gap-1.5">
                    {r.regions.map((reg) => (
                      <span
                        key={reg.id}
                        className="text-[10px] font-semibold px-1.5 py-0.5 rounded border bg-white"
                        style={{ borderColor: r.colour_hex, color: r.colour_hex }}
                        data-testid={`tender-coverage-region-${reg.id}`}
                      >
                        {reg.region_type === 'postcode_area' ? `${reg.region_code} ·` : ''} {reg.name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
