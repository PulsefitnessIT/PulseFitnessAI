/**
 * Iter 216h23 — Cross-organisation physical-sites list.
 *
 * Lives at Master Admin → Organisations → "All sites" sub-tab. Operator
 * feedback: "I still don't know why we need a Sites button when we have
 * Organisations?" The misleading stand-alone "Sites" sidebar entry has
 * been deleted (it actually contained the equipment catalogue, now
 * re-homed under "Catalogue & Library"). Sites belong to Organisations
 * and the only SSoT for site editing remains the Organisation drawer's
 * Sites tab. THIS page is a flat power-view across every org so HQ ops
 * can spot dormant sites without bouncing through the org list.
 *
 * Row click → switches the section to `organizations` and emits
 * `gymaxis:focus-org` so AdminOrganizations can expand the right row +
 * land on its Sites tab. Single source of truth preserved.
 */
import { useEffect, useState, useMemo, useCallback } from 'react';
import axios from 'axios';
import { MapPin, RefreshCw, Search, ExternalLink, Building2, Star } from 'lucide-react';
import Button from '@/components/shared/Button';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const BrandPill = ({ brand }) => {
  const tones = {
    pulse:   { bg: 'rgba(0,85,255,0.08)',     fg: '#1D4ED8', label: 'Pulse' },
    gymaxis: { bg: 'rgba(16,185,129,0.10)',   fg: '#047857', label: 'GymAxis' },
  };
  const t = tones[brand] || tones.gymaxis;
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold" style={{ background: t.bg, color: t.fg }}>
      {t.label}
    </span>
  );
};

const AdminAllSites = ({ isPulseAdmin = false }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [q, setQ] = useState('');
  const [siteType, setSiteType] = useState('all');
  const [orgFilter, setOrgFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const token = localStorage.getItem('token');
      const { data: payload } = await axios.get(`${API}/master-admin/all-sites`, {
        headers: { Authorization: `Bearer ${token}` },
        params: { limit: 1000 },
      });
      setData(payload);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to load sites');
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const sites = data?.sites || [];
  const totals = data?.totals || { sites: 0, head_offices: 0, branches: 0, equipment: 0 };

  const orgs = useMemo(() => {
    const seen = new Map();
    sites.forEach((s) => { if (s.organization_id && !seen.has(s.organization_id)) seen.set(s.organization_id, s.org_name); });
    return Array.from(seen, ([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [sites]);

  const filtered = useMemo(() => sites.filter((s) => {
    if (siteType === 'head_office' && !s.is_head_office) return false;
    if (siteType === 'branch' && s.is_head_office) return false;
    if (orgFilter !== 'all' && s.organization_id !== orgFilter) return false;
    if (q.trim() && !`${s.name} ${s.org_name} ${s.city || ''} ${s.postcode || ''}`.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  }), [sites, siteType, orgFilter, q]);

  const openInOrg = (s) => {
    try {
      // Iter 216h23 — AdminOrganizations already reads ?expand=ORG&view=VIEW
      // from the URL on mount (line ~455). Push those params + flip the
      // section so the right org row expands on the Sites tab.
      const params = new URLSearchParams(window.location.search);
      params.set('section', 'organizations');
      params.set('expand', s.organization_id);
      params.set('view', 'sites');
      window.history.pushState({}, '', `?${params.toString()}`);
      window.dispatchEvent(new CustomEvent('gymaxis:set-section', { detail: { section: 'organizations' } }));
    } catch { /* noop */ }
  };

  return (
    <div className="space-y-5" data-testid="admin-all-sites">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-bold text-zinc-900 tracking-tight">All sites</h2>
          <p className="text-sm text-zinc-500 mt-0.5">
            Flat list of every physical site across {isPulseAdmin ? 'Pulse Fitness' : 'every organisation'}. Click a row to open the parent organisation&apos;s Sites tab.
          </p>
        </div>
        <Button
          variant="secondary" size="sm" icon={RefreshCw}
          onClick={load}
          disabled={loading}
          data-testid="admin-all-sites-refresh"
        >
          Refresh
        </Button>
      </div>

      {/* Totals strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="admin-all-sites-totals">
        {[
          { label: 'Total sites',   value: totals.sites },
          { label: 'Head offices',  value: totals.head_offices },
          { label: 'Branches',      value: totals.branches },
          { label: 'Equipment',     value: totals.equipment },
        ].map((t) => (
          <div key={t.label} className="rounded-lg border bg-white p-3" style={{ borderColor: '#E4E4E7' }}>
            <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">{t.label}</div>
            <div className="text-2xl font-bold text-zinc-900 mt-0.5">{t.value}</div>
          </div>
        ))}
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-white p-3" style={{ borderColor: '#E4E4E7' }}>
        <div className="relative flex-1 min-w-[200px]">
          <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            type="search"
            placeholder="Search by site, org, city, postcode…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="w-full pl-7 pr-2 py-1.5 text-sm rounded-md border bg-white focus:outline-none focus:ring-2 focus:ring-blue-200"
            style={{ borderColor: '#E4E4E7' }}
            data-testid="admin-all-sites-search"
          />
        </div>
        <select
          value={siteType}
          onChange={(e) => setSiteType(e.target.value)}
          className="text-sm rounded-md border px-2 py-1.5 bg-white"
          style={{ borderColor: '#E4E4E7' }}
          data-testid="admin-all-sites-type-filter"
        >
          <option value="all">All site types</option>
          <option value="head_office">Head offices only</option>
          <option value="branch">Branches only</option>
        </select>
        <select
          value={orgFilter}
          onChange={(e) => setOrgFilter(e.target.value)}
          className="text-sm rounded-md border px-2 py-1.5 bg-white max-w-[220px]"
          style={{ borderColor: '#E4E4E7' }}
          data-testid="admin-all-sites-org-filter"
        >
          <option value="all">All organisations</option>
          {orgs.map((o) => (
            <option key={o.id} value={o.id}>{o.name}</option>
          ))}
        </select>
        <span className="text-[11px] text-zinc-500" data-testid="admin-all-sites-result-count">
          Showing {filtered.length} of {sites.length}
        </span>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>
      )}

      {/* Table */}
      <div className="rounded-lg border bg-white overflow-hidden" style={{ borderColor: '#E4E4E7' }}>
        <table className="w-full text-sm" data-testid="admin-all-sites-table">
          <thead className="bg-zinc-50 text-xs uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="text-left py-2 px-3 font-semibold">Site</th>
              <th className="text-left py-2 px-3 font-semibold">Organisation</th>
              <th className="text-left py-2 px-3 font-semibold">Brand</th>
              <th className="text-left py-2 px-3 font-semibold">Location</th>
              <th className="text-right py-2 px-3 font-semibold">Equipment</th>
              <th className="text-right py-2 px-3 font-semibold">Members</th>
              <th className="w-10"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && !loading && (
              <tr><td colSpan={7} className="text-center py-6 text-zinc-500 text-sm">No sites match your filters.</td></tr>
            )}
            {filtered.map((s) => (
              <tr
                key={`${s.organization_id}-${s.id}`}
                className="border-t hover:bg-zinc-50 cursor-pointer"
                style={{ borderColor: '#F4F4F5' }}
                onClick={() => openInOrg(s)}
                data-testid={`admin-all-sites-row-${s.id}`}
              >
                <td className="py-2.5 px-3">
                  <div className="flex items-center gap-2">
                    {s.is_head_office ? (
                      <span title="Head Office" className="inline-flex items-center justify-center w-5 h-5 rounded bg-amber-50 text-amber-600">
                        <Star size={11} />
                      </span>
                    ) : (
                      <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-zinc-50 text-zinc-500">
                        <MapPin size={11} />
                      </span>
                    )}
                    <span className="font-medium text-zinc-900">{s.name}</span>
                    {!s.active && <span className="text-[10px] uppercase tracking-wider font-bold text-zinc-400">Archived</span>}
                  </div>
                </td>
                <td className="py-2.5 px-3 text-zinc-700">
                  <div className="flex items-center gap-1.5">
                    <Building2 size={11} className="text-zinc-400" />
                    <span className="truncate max-w-[200px]">{s.org_name}</span>
                  </div>
                </td>
                <td className="py-2.5 px-3"><BrandPill brand={s.org_brand} /></td>
                <td className="py-2.5 px-3 text-zinc-600 text-xs">
                  {[s.city, s.postcode].filter(Boolean).join(' · ') || '\u2014'}
                </td>
                <td className="py-2.5 px-3 text-right font-medium text-zinc-700">{s.equipment_count}</td>
                <td className="py-2.5 px-3 text-right font-medium text-zinc-700">{s.members_count || 0}</td>
                <td className="py-2.5 px-3 text-zinc-400"><ExternalLink size={12} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[10px] text-zinc-400 italic">
        Site editing remains inside the Organisations drawer (single source of truth). This list is read-only — click any row to land directly on that org&apos;s Sites tab.
      </p>
    </div>
  );
};

export default AdminAllSites;
