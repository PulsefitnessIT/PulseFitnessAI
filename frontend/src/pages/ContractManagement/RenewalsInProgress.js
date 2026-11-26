import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useCRM } from '@/pages/CRM/CRMApp';
import { copyAcceptLink } from '@/pages/CRM/Aftersales/AftersalesApp';

const TONE = {
  approved_not_delivered: 'var(--color-danger)', declined: 'var(--color-danger)', expired: 'var(--color-danger)',
  awaiting_price_approval: 'var(--color-accent-amber)', pending_approval: 'var(--color-accent-amber)',
  delivered: 'var(--color-info-ios)', accepted: 'var(--color-success-alt)',
  awaiting_dispatch: 'var(--color-accent-amber)', email_cancelled: 'var(--color-danger)', issued_manually: 'var(--color-info-ios)',
};

/** Renewals in progress — recoverable accept link + truthful delivery status. */
export default function RenewalsInProgress() {
  const [ask, setAsk] = useState(null);
  const [askText, setAskText] = useState('');
  const { API, headers, c } = useCRM();
  const [rows, setRows] = useState(null);
  const load = useCallback(() => {
    axios.get(`${API}/crm/workspace/renewals`, { headers: headers() })
      .then((r) => setRows(r.data.renewals || [])).catch(() => setRows([]));
  }, [API, headers]);
  useEffect(() => { load(); }, [load]);
  const act = async (id, path, okMsg, body = {}) => {
    try {
      const r = await axios.post(`${API}/crm/workspace/renewals/${id}/${path}`, body, { headers: headers() });
      if (path === 'resend' && !r.data.email_delivered) toast.warning('Email still not delivered — copy the link and send it yourself');
      else toast.success(okMsg);
      load();
    }
    catch (e) { toast.error(e.response?.data?.detail || 'Action failed'); }
  };
  if (!rows || rows.length === 0) return null;
  const submitAsk = async () => { const a = ask; setAsk(null); await act(a.id, a.path, a.ok, { [a.field]: askText.trim() }); setAskText(''); };
  return (
    <div className="rounded-2xl p-4 mb-5" style={{ background: c.surface, border: `1px solid ${c.border}` }} data-testid="cm-renewals-in-progress">
      <h3 className="text-sm font-bold mb-3" style={{ color: c.text }}>Renewals in progress</h3>
      {ask && (
        <div className="rounded-xl p-3 mb-3 border" style={{ borderColor: c.border, background: c.bg || c.surface }} data-testid="cm-renewal-ask" role="dialog" aria-label={ask.title}>
          <p className="text-xs font-semibold mb-1" style={{ color: c.text }}>{ask.title}</p>
          <input autoFocus value={askText} onChange={(e) => setAskText(e.target.value)} placeholder={ask.label} aria-label={ask.label}
            className="w-full text-xs px-2 py-1.5 rounded-md border" style={{ borderColor: c.border, color: c.text, background: 'transparent' }} data-testid="cm-renewal-ask-input" />
          <div className="flex gap-2 mt-2 text-xs">
            <button disabled={askText.trim().length < 5} onClick={submitAsk} className="px-2 py-1 rounded-md border font-semibold disabled:opacity-40" style={{ borderColor: c.border, color: c.text }} data-testid="cm-renewal-ask-confirm">Confirm</button>
            <button onClick={() => { setAsk(null); setAskText(''); }} className="px-2 py-1" style={{ color: c.textMuted }} data-testid="cm-renewal-ask-cancel">Back</button>
          </div>
        </div>
      )}
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
                  {['awaiting_dispatch', 'approved_not_delivered', 'email_cancelled'].includes(r.comms_status) && r.status === 'renewal_approved' && (
                    <button onClick={() => setAsk({ id: r.id, path: 'mark-issued', field: 'evidence', title: 'Record manual issue', label: 'How did the renewal reach the customer?', ok: 'Renewal recorded as issued' })}
                      className="px-2 py-1 rounded-md border mr-1" style={{ borderColor: c.border, color: c.text }} data-testid={`cm-renewal-mark-issued-${r.id}`}>Mark issued</button>
                  )}
                  {r.comms_status === 'awaiting_dispatch' && (
                    <button onClick={() => setAsk({ id: r.id, path: 'cancel-email', field: 'reason', title: 'Cancel customer email', label: 'Why should this email not be sent?', ok: 'Customer email cancelled' })}
                      className="px-2 py-1 rounded-md border mr-1" style={{ borderColor: c.border, color: c.text }} data-testid={`cm-renewal-cancel-email-${r.id}`}>Cancel customer email</button>
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
