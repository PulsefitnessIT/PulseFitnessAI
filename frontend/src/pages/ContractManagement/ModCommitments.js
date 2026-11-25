import { useEffect, useState } from 'react';
import axios from 'axios';
import { Shield, ExternalLink } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/crm/workspace/mod-commitments`;
const TYPE = { A: 'Type A — annual', B: 'Type B — one-off', AB: 'Mixed A/B' };
const gbp = (v) => (v == null ? '—' : `£${Number(v).toLocaleString('en-GB', { minimumFractionDigits: 2 })}`);

/** Read-only list of accepted MOD quotations; MOD Operations remains the authoritative record. */
export default function ModCommitments() {
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const tok = localStorage.getItem('crm_token') || localStorage.getItem('token');
    axios.get(API, { headers: tok ? { Authorization: `Bearer ${tok}` } : {}, withCredentials: true })
      .then((r) => setItems(r.data.items)).catch(() => setItems([]));
  }, []);
  if (!items || !items.length) return null;
  return (
    <div className="rounded-xl border p-4 mb-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="cm-mod-commitments">
      <button type="button" className="w-full flex items-center justify-between text-left" onClick={() => setOpen(!open)} aria-expanded={open} data-testid="cm-mod-commitments-toggle">
        <span className="font-semibold text-sm inline-flex items-center gap-2"><Shield size={15} /> MOD contract commitments ({items.length}) · read-only</span>
        <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{open ? 'Hide' : 'Show'}</span>
      </button>
      {open && (
        <div className="overflow-x-auto mt-3">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] uppercase" style={{ color: 'var(--theme-text-muted)' }}>
              <th className="p-2">MOD site</th><th className="p-2">Cover</th><th className="p-2">Quotation</th><th className="p-2">Annual</th><th className="p-2">One-off</th><th className="p-2">Start</th><th className="p-2">Status</th><th className="p-2" /></tr></thead>
            <tbody>{items.map((h) => (
              <tr key={h.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`cm-mod-commitment-${h.id}`}>
                <td className="p-2 font-medium">{h.mod_site_name}</td><td className="p-2">{TYPE[h.quote_type] || h.quote_type}</td>
                <td className="p-2">{h.source_quote_number}</td><td className="p-2">{gbp(h.annual_type_a_value)}</td><td className="p-2">{gbp(h.one_off_type_b_value)}</td>
                <td className="p-2">{h.start_date ? new Date(h.start_date).toLocaleDateString('en-GB') : '—'}</td>
                <td className="p-2">{h.status === 'setup_complete' ? 'Set up' : 'Awaiting set-up'}</td>
                <td className="p-2"><a className="text-xs inline-flex items-center gap-1" href={`/bfpo?view=quotations&quote_group=${h.group_id}`} data-testid="cm-mod-commitment-open">MOD Operations <ExternalLink size={12} /></a></td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
