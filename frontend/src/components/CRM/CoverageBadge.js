/**
 * CoverageBadge.js (iter 216h278)
 *
 * Renders a compact "Covered by: Jane (SM), Tom (Eng)" pill that
 * sits next to any record (tender row, company card, opportunity
 * detail). Looks up coverage via /api/crm/territories/coverage-for
 * and silently hides when no territory is configured — coverage is
 * an optional feature so we never want this to show as a "loading"
 * blocker on customers who haven't enabled it.
 *
 * Lookups are memoised in a module-level cache keyed by
 * `${companyId}|${postcode}|${county}` so the same tender list
 * doesn't fire 20 identical requests when scrolled.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { ShieldCheck } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

const cache = new Map();

const ROLE_SHORT = { sales_manager: 'SM', engineer: 'Eng', both: 'SM/Eng' };

export default function CoverageBadge({ companyId, postcode, county, compact = false, testId }) {
  const [data, setData] = useState(null);
  const key = `${companyId || ''}|${postcode || ''}|${county || ''}`;

  useEffect(() => {
    if (!companyId && !postcode && !county) return;
    if (cache.has(key)) { setData(cache.get(key)); return; }
    let cancel = false;
    (async () => {
      try {
        const params = new URLSearchParams();
        if (companyId) params.set('company_id', companyId);
        if (postcode) params.set('postcode', postcode);
        if (county) params.set('county', county);
        const r = await axios.get(`${API}/crm/territories/coverage-for?${params}`, auth());
        if (cancel) return;
        cache.set(key, r.data);
        setData(r.data);
      } catch { /* coverage is optional — fail quiet */ }
    })();
    return () => { cancel = true; };
  }, [key, companyId, postcode, county]);

  if (!data || !data.covered || !data.reps?.length) return null;

  const top = data.reps.slice(0, compact ? 1 : 3);
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold border bg-white"
      style={{ borderColor: 'var(--theme-border, #E2E8F0)', color: 'var(--theme-text-muted, #475569)' }}
      title={`Covered by: ${data.reps.map((r) => `${r.full_name} (${ROLE_SHORT[r.role] || ''})`).join(', ')}`}
      data-testid={testId || 'coverage-badge'}
    >
      <ShieldCheck size={10} />
      <span className="hidden sm:inline">Cover:</span>
      {top.map((r) => (
        <span key={r.user_id} className="inline-flex items-center gap-0.5">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: r.colour_hex }} />
          <span>{(r.full_name || '').split(' ')[0] || '?'}</span>
        </span>
      ))}
      {data.reps.length > top.length && (
        <span className="text-zinc-400">+{data.reps.length - top.length}</span>
      )}
    </span>
  );
}
