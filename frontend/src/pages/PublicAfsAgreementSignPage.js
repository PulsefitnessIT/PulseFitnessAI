/**
 * PublicAfsAgreementSignPage — no-login review + e-signature of the exact
 * maintenance agreement issued by Pulse Fitness (/as/:token).
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useParams } from 'react-router-dom';
import { CheckCircle2, XCircle, Loader2, ShieldCheck, FileText } from 'lucide-react';
import { SignaturePad } from './PublicAfsQuoteAcceptPage';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const gbp = (n) => `£${Number(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmt = (s) => s ? new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
const PAY = { monthly: 'Monthly by Direct Debit', annual: 'Annually in advance', quarterly: 'Quarterly in advance', lump_sum: 'Lump sum in advance' };

const Card = ({ title, children, testid }) => (
  <section className="bg-white rounded-2xl border border-slate-200 p-5" data-testid={testid}>
    {title && <h2 className="text-sm font-bold text-slate-900 mb-3">{title}</h2>}
    {children}
  </section>
);
const Row = ({ k, v }) => <div className="flex justify-between gap-4 text-sm py-1 border-b border-slate-100"><span className="text-slate-500">{k}</span><span className="text-slate-900 text-right">{v || '—'}</span></div>;

function Message({ ok, title, text, testid }) {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <div className="bg-white rounded-2xl border border-slate-200 p-8 max-w-md text-center shadow-sm" data-testid={testid}>
        {ok ? <CheckCircle2 size={40} className="mx-auto mb-3 text-emerald-500" /> : <XCircle size={32} className="mx-auto mb-3 text-rose-500" />}
        <p className="text-lg font-extrabold text-slate-900 mb-1">{title}</p>
        <p className="text-sm text-slate-500">{text}</p>
      </div>
    </div>
  );
}

export default function PublicAfsAgreementSignPage() {
  const { token } = useParams();
  const [ag, setAg] = useState(null);
  const [err, setErr] = useState(null);
  const [form, setForm] = useState({ signatory_name: '', position: '', email: '', authority_confirmed: false, consent_confirmed: false });
  const [sig, setSig] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState('');

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/public/afs/agreement/${token}`);
      setAg(r.data);
      setForm(f => ({ ...f, signatory_name: f.signatory_name || r.data.signatory_name || '' }));
      if (r.data.status === 'signed') setDone('signed');
      if (r.data.status === 'declined') setDone('declined');
    } catch (e) { setErr(e?.response?.data?.detail || 'This agreement link is not valid.'); }
  }, [token]);
  useEffect(() => { load(); }, [load]);

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
  const canSign = form.signatory_name.trim().length > 1 && /\S+@\S+\.\S+/.test(form.email) && form.authority_confirmed && form.consent_confirmed && sig;

  const submit = async () => {
    if (!canSign || busy) return;
    setBusy(true);
    try {
      await axios.post(`${API}/public/afs/agreement/${token}/sign`, { ...form, signature_data_url: sig, document_hash: ag.document_hash });
      setDone('signed');
    } catch (e) { setErr(e?.response?.data?.detail || 'Signing failed — please try again.'); }
    finally { setBusy(false); }
  };
  const decline = async () => {
    if (form.signatory_name.trim().length < 2 || busy) return;
    setBusy(true);
    try { await axios.post(`${API}/public/afs/agreement/${token}/decline`, { name: form.signatory_name, reason }); setDone('declined'); }
    catch (e) { setErr(e?.response?.data?.detail || 'Could not record your response.'); }
    finally { setBusy(false); }
  };

  if (err && !ag) return <Message title="Agreement unavailable" text={err} testid="as-error" />;
  if (!ag) return <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-500"><Loader2 className="animate-spin mr-2" size={20} /> Loading agreement…</div>;
  if (done === 'signed') return <Message ok title="Agreement signed" text={`Thank you. Agreement ${ag.agreement_number} has been signed and Pulse Fitness has been notified. You will receive a confirmation email once your contract is active.`} testid="as-signed-confirmation" />;
  if (done === 'declined') return <Message title="Response recorded" text={`Agreement ${ag.agreement_number} has been declined. Pulse Fitness will be in touch.`} testid="as-declined-confirmation" />;

  return (
    <div className="min-h-screen bg-slate-50" data-testid="as-page">
      <div className="text-white" style={{ background: 'linear-gradient(135deg,#0073A4 0%,#1763B5 60%,#00B5D8 100%)' }}>
        <div className="max-w-3xl mx-auto px-5 py-8">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] opacity-80">Pulse Fitness · Maintenance Agreement</p>
          <h1 className="text-3xl font-extrabold mt-1" data-testid="as-agreement-number">{ag.agreement_number}</h1>
          <p className="text-sm opacity-90 mt-2">{ag.agreement_type} · link valid until {fmt(ag.expires_at)}</p>
        </div>
      </div>
      <main className="max-w-3xl mx-auto px-5 py-6 pb-24 space-y-5">
        <Card title="Agreement summary" testid="as-summary">
          <Row k="Supplier" v={ag.supplier} /><Row k="Customer" v={ag.customer} /><Row k="Site(s)" v={(ag.sites || []).join(', ')} />
          <Row k="Package" v={(ag.package || '').toUpperCase()} /><Row k="Start date" v={fmt(ag.start_date)} /><Row k="Expiry date" v={fmt(ag.end_date)} />
          <Row k="Annual value (ex VAT)" v={gbp(ag.annual_value)} /><Row k="VAT" v={ag.vat_pct != null ? `${(ag.vat_pct * 100).toFixed(0)}% in addition` : '—'} />
          <Row k="Billing" v={PAY[ag.billing_frequency] || ag.billing_frequency} /><Row k="Service visits" v={`${ag.visits_per_year} per year`} />
          <Row k="Terms & Conditions" v={ag.terms_version ? `Version ${ag.terms_version}` : '—'} />
          <button onClick={() => window.open(`${API}/public/afs/agreement/${token}/pdf`, '_blank')} data-testid="as-pdf"
            className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-blue-700 hover:text-blue-900">
            <FileText size={15} /> Read / download the full agreement (PDF)
          </button>
        </Card>
        <Card title="Equipment covered" testid="as-equipment">
          {(ag.equipment || []).map((e, i) => (
            <div key={i} className="text-sm py-1.5 border-b border-slate-100"><b>{e.quantity} × {e.machine}</b>
              <span className="text-slate-500"> · {(e.serial_numbers || []).join(', ') || 'serials confirmed at first service'}</span></div>
          ))}
        </Card>
        {err && <p className="text-sm text-rose-600" data-testid="as-inline-error">{err}</p>}
        {!declining ? (
          <Card title="Sign this agreement" testid="as-sign-section">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-3">
              <input className="text-sm border border-slate-200 rounded-lg px-3 py-2" placeholder="Full name *" value={form.signatory_name} onChange={set('signatory_name')} data-testid="as-name" />
              <input className="text-sm border border-slate-200 rounded-lg px-3 py-2" placeholder="Position" value={form.position} onChange={set('position')} data-testid="as-position" />
              <input className="text-sm border border-slate-200 rounded-lg px-3 py-2" placeholder="Email *" value={form.email} onChange={set('email')} data-testid="as-email" />
            </div>
            <SignaturePad onChange={setSig} />
            <p className="text-[11px] text-slate-500 mt-2" data-testid="as-date">Date of signature: {fmt(new Date().toISOString())} (recorded automatically)</p>
            <label className="text-xs flex gap-2 mt-3 text-slate-600"><input type="checkbox" checked={form.authority_confirmed} onChange={set('authority_confirmed')} data-testid="as-authority" /> I confirm I am authorised to sign this agreement on behalf of the customer.</label>
            <label className="text-xs flex gap-2 mt-2 text-slate-600"><input type="checkbox" checked={form.consent_confirmed} onChange={set('consent_confirmed')} data-testid="as-consent" /> I have read the agreement and the Terms &amp; Conditions and agree to sign electronically.</label>
            <div className="flex gap-2 mt-4">
              <button onClick={submit} disabled={!canSign || busy} data-testid="as-sign-btn"
                className="flex-1 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-white text-sm font-bold shadow disabled:opacity-50" style={{ background: 'linear-gradient(135deg,#0073A4,#1763B5)' }}>
                {busy ? <Loader2 className="animate-spin" size={16} /> : <CheckCircle2 size={16} />} Sign agreement
              </button>
              <button onClick={() => setDeclining(true)} data-testid="as-decline-btn" className="px-4 py-3 rounded-xl bg-white border border-slate-200 text-slate-700 text-sm font-bold">Decline</button>
            </div>
            <p className="text-[10px] text-slate-400 mt-3 flex items-center gap-1.5"><ShieldCheck size={11} /> Your signature is bound to document version {ag.document_version}.</p>
          </Card>
        ) : (
          <Card title="Decline this agreement" testid="as-decline-section">
            <input className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 mb-2" placeholder="Your name *" value={form.signatory_name} onChange={set('signatory_name')} data-testid="as-decline-name" />
            <textarea className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2" rows={3} placeholder="Reason (optional)" value={reason} onChange={e => setReason(e.target.value)} data-testid="as-decline-reason" />
            <div className="flex gap-2 mt-3">
              <button onClick={decline} disabled={busy || form.signatory_name.trim().length < 2} data-testid="as-decline-confirm" className="flex-1 px-5 py-3 rounded-xl bg-rose-600 text-white text-sm font-bold disabled:opacity-50">Confirm decline</button>
              <button onClick={() => setDeclining(false)} data-testid="as-decline-cancel" className="px-4 py-3 rounded-xl bg-white border border-slate-200 text-sm font-bold">Go back</button>
            </div>
          </Card>
        )}
      </main>
    </div>
  );
}
