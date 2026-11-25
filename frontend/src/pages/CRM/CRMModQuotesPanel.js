import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { ExternalLink } from 'lucide-react';

const TYPE = { A: 'Type A', B: 'Type B', AB: 'Type A/B Mix' };
const gbp = (v) => `£${Number(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmt = (d) => (d ? new Date(d).toLocaleDateString('en-GB') : '—');

export default function CRMModQuotesPanel({ companyId, API, headers, c }) {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState('');
  const hRef = useRef(headers);
  hRef.current = headers;
  useEffect(() => {
    const h = hRef.current;
    axios.get(`${API}/mod-ops/quotes/crm/company/${companyId}`, { headers: typeof h === 'function' ? h() : h })
      .then((r) => setRows(r.data.quotes)).catch((e) => setErr(e.response?.data?.detail || 'Could not load MOD quotations'));
  }, [API, companyId]);
  if (err) return <div className="text-sm p-4" style={{ color: c.textMuted }} data-testid="crm-mod-quotes-error">{err}</div>;
  if (!rows) return <div className="text-sm p-4" style={{ color: c.textMuted }}>Loading…</div>;
  return (
    <div className="rounded-xl overflow-x-auto" style={{ border: `1px solid ${c.border}` }} data-testid="crm-mod-quotes">
      <div className="px-4 py-3 text-xs" style={{ color: c.textMuted }}>MOD quotations are created and managed in MOD Operations → Quotations. This is a read-only view.</div>
      <table className="w-full text-sm">
        <thead><tr className="text-left text-xs" style={{ color: c.textMuted }}>
          <th className="p-2">Reference</th><th className="p-2">Site</th><th className="p-2">Type</th><th className="p-2 text-right">Net</th><th className="p-2 text-right">Gross</th>
          <th className="p-2">Created</th><th className="p-2">Published</th><th className="p-2">Status</th><th className="p-2">Customer</th><th className="p-2" />
        </tr></thead>
        <tbody>
          {rows.map((q) => (
            <tr key={q.id} className="border-t" style={{ borderColor: c.border, color: c.text }} data-testid={`crm-mod-quote-${q.id}`}>
              <td className="p-2 font-semibold">{q.sage_quote_number ? `${q.sage_quote_number} (Sage)` : q.quote_number}{q.sage_quote_number && <div className="text-xs font-normal" style={{ color: c.textMuted }}>{q.quote_number}</div>}<div className="text-xs font-normal" style={{ color: c.textMuted }}>v{q.version} · by {q.created_by_name}</div></td>
              <td className="p-2">{q.mod_site_name}</td>
              <td className="p-2">{TYPE[q.mod_quote_type]}{q.selected ? ' ✓ selected' : ''}</td>
              <td className="p-2 text-right">{gbp(q.subtotal)}</td><td className="p-2 text-right">{gbp(q.total)}</td>
              <td className="p-2">{fmt(q.created_at)}</td><td className="p-2">{fmt(q.published_at)}</td>
              <td className="p-2">{(q.status || '').replace(/_/g, ' ')}{q.handover_id ? ' · handed to Operations' : ''}</td>
              <td className="p-2 text-xs">{q.customer_downloads ? `${q.customer_downloads} download(s)` : '—'}</td>
              <td className="p-2"><a href={`/bfpo?view=quotations&quote_group=${q.mod_group_id}`} className="inline-flex items-center gap-1 text-xs font-semibold" style={{ color: 'var(--color-brand-cyan)' }} data-testid={`crm-mod-quote-open-${q.id}`}><ExternalLink size={12} /> View in MOD Operations</a></td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={10} className="p-6 text-center text-sm" style={{ color: c.textMuted }}>No MOD quotations for this customer.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
