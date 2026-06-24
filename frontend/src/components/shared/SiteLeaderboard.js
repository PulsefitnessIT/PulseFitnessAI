/**
 * Cross-site comparison leaderboard — shown ONLY on the "All Sites"
 * aggregate view. Compares Active Members, MRR, Open Deals, Campaigns
 * (30d) and Open Faults per site, with the Head Office flagged (star).
 * Each row drills into that site (switches the active site).
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Star, MapPin, Users, PoundSterling, Briefcase, Megaphone, Wrench } from 'lucide-react';
import { useAuth } from '@/App';

const COLS = [
  { key: 'active_members', label: 'Active Members', icon: Users },
  { key: 'mrr_gbp', label: 'MRR', icon: PoundSterling, money: true },
  { key: 'open_deals', label: 'Open Deals', icon: Briefcase },
  { key: 'campaigns_30d', label: 'Campaigns (30d)', icon: Megaphone },
  { key: 'open_faults', label: 'Open Faults', icon: Wrench },
];

export default function SiteLeaderboard() {
  const { API, allSitesMode, sites, setActiveSite } = useAuth();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!allSitesMode) return;
    let alive = true;
    (async () => {
      try {
        setLoading(true);
        const { data } = await axios.get(`${API}/sites/leaderboard`);
        if (alive) setRows(data.sites || []);
      } catch {
        if (alive) setRows([]);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [allSitesMode, API]);

  // Only render on the aggregate view for multi-site orgs.
  if (!allSitesMode || !sites || sites.length < 2) return null;

  const drillIn = (siteId) => {
    const site = (sites || []).find((s) => s.id === siteId);
    if (site) setActiveSite(site);
  };

  const fmt = (c, v) => (c.money ? `£${Number(v || 0).toLocaleString()}` : Number(v || 0).toLocaleString());

  return (
    <div
      className="rounded-xl overflow-hidden mb-6"
      style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}
      data-testid="site-leaderboard"
    >
      <div className="px-5 py-4 flex items-center gap-2" style={{ borderBottom: '1px solid var(--theme-border-soft)' }}>
        <MapPin size={16} className="text-[var(--color-brand-blue)]" />
        <h3 className="text-base font-bold" style={{ color: 'var(--theme-text)' }}>Site comparison</h3>
        <span className="text-xs ml-2" style={{ color: 'var(--theme-text-muted)' }}>across all your sites</span>
      </div>

      {loading ? (
        <div className="p-6 text-sm" style={{ color: 'var(--theme-text-muted)' }} data-testid="site-leaderboard-loading">Loading site metrics…</div>
      ) : rows.length === 0 ? (
        <div className="p-6 text-sm" style={{ color: 'var(--theme-text-muted)' }}>No site data yet.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="site-leaderboard-table">
            <thead>
              <tr style={{ color: 'var(--theme-text-muted)' }}>
                <th className="text-left font-semibold px-5 py-2.5">Site</th>
                {COLS.map((c) => (
                  <th key={c.key} className="text-right font-semibold px-4 py-2.5 whitespace-nowrap">
                    <span className="inline-flex items-center gap-1 justify-end"><c.icon size={13} />{c.label}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.site_id}
                  onClick={() => drillIn(r.site_id)}
                  className="cursor-pointer transition-colors hover:bg-[var(--theme-hover-bg)]"
                  style={{ borderTop: '1px solid var(--theme-border-soft)', color: 'var(--theme-text)' }}
                  data-testid={`site-leaderboard-row-${r.site_id}`}
                >
                  <td className="px-5 py-3 font-semibold">
                    <span className="inline-flex items-center gap-1.5">
                      {r.is_head_office ? <Star size={14} className="text-amber-500" /> : <MapPin size={14} className="text-[var(--theme-text-muted)]" />}
                      {r.name}
                    </span>
                  </td>
                  {COLS.map((c) => (
                    <td key={c.key} className="text-right px-4 py-3 tabular-nums">{fmt(c, r[c.key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
