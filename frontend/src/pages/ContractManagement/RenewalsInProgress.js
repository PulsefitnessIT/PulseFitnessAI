import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useCRM } from '@/pages/CRM/CRMApp';
import { copyAcceptLink } from '@/pages/CRM/Aftersales/AftersalesApp';

const TONE = {
  approved_not_delivered: 'var(--color-danger)', declined: 'var(--color-danger)', expired: 'var(--color-danger)',
  awaiting_price_approval: 'var(--color-accent-amber)', pending_approval: 'var(--color-accent-amber)',
  delivered: 'var(--color-info-ios)', accepted: 'var(--color-success-alt)',
};

/** Renewals in progress — recoverable accept link + truthful delivery status. */
export default function RenewalsInProgress() {
  const { API, headers, c } = useCRM();
  const [rows, setRows] = useState(null);
  const load = useCallback(() => {
    axios.get(`${API}/crm/workspace/renewals`, { headers: headers() })
      .then((r) => setRows(r.data.renewals || [])).catch(() => setRows([]));
  }, [API, headers]);
  useEffect(() => { load(); }, [load]);
  const act = async (id, path, okMsg) => {
    try {
      const r = await axios.post(`${API}/crm/workspace/renewals/${id}/${path}`, {}, { headers: headers() });
      if (path === 'resend' && !r.data.email_delivered) toast.warning('Email still not delivered — copy the link and send it yourself');
      else toast.success(okMsg);
      load();
    }
    catch (e) { toast.error(e.response?.data?.detail || 'Action failed'); }
  };
  if (!rows || rows.length === 0) return null;
  return (
    <div className="rounded-2xl p-4 mb-5" style={{ background: c.surface, border: `1px solid ${c.border}` }} data-testid="cm-renewals-in-progress">
      <h3 className="text-sm font-bold mb-3" style={{ color: c.text }}>Renewals in progress</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead><tr style={{ color: c.textMuted }}><th className="pb-2">Renewal</th><th className="pb-2">New term</th><th className="pb-2">Value</th><th className="pb-2">Status</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t" style={{ borderColor: c.border }} data-testid={`cm-renewal-row-${r.id}`}>
                <td className="py-2 pr-2"><div className="font-semibold" style={{ color: c.text }}>{r.contract_number}</div><div style={{ color: c.textMuted }}>{r.company_name}</div></td>
                <td className="py-2 pr-2" style={{ color: c.text }}>{r.start_date} → {r.end_date}</td>
                <td className="py-2 pr-2" style={{ color: c.text }}>£{Number(r.annual_value || 0).toLocaleString('en-GB', { minimumFractionDigits: 2 })}{r.renewal_uplift_percent ? ` (+${r.renewal_uplift_percent}%)` : ''}</td>
                <td className="py-2 pr-2"><span className="font-semibold" style={{ color: TONE[r.comms_status] || c.text }} data-testid={`cm-renewal-status-${r.id}`}>{r.comms_label}</span>
                  {r.renewal_sent_to && <div style={{ color: c.textMuted }}>{r.renewal_sent_to}</div>}</td>
                <td className="py-2 text-right whitespace-nowrap">
                  {r.renewal_accept_link && ['approved_not_delivered', 'delivered', 'expired'].includes(r.comms_status) && (
                    <button onClick={() => copyAcceptLink(r.renewal_accept_link)}
                      className="px-2 py-1 rounded-md border mr-1" style={{ borderColor: c.border, color: c.text }} data-testid={`cm-renewal-copy-${r.id}`}>Copy link</button>
                  )}
                  {['approved_not_delivered', 'delivered'].includes(r.comms_status) && (
                    <>
                      <button onClick={() => act(r.id, 'resend', 'Renewal email delivered')} className="px-2 py-1 rounded-md border mr-1" style={{ borderColor: c.border, color: c.text }} data-testid={`cm-renewal-resend-${r.id}`}>Resend</button>
                      <button onClick={() => act(r.id, 'declined', 'Marked as declined')} className="px-2 py-1 rounded-md border" style={{ borderColor: c.border, color: c.text }} data-testid={`cm-renewal-declined-${r.id}`}>Declined</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
