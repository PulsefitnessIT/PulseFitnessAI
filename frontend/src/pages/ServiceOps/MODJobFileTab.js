import { useEffect, useState } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { AlertTriangle, Camera, ClipboardList, FileText, Handshake, Loader2, MessageSquare, Receipt, Wrench } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });
const when = (s) => (s ? new Date(s).toLocaleString() : '—');
const label = (s) => (s || '—').replace(/_/g, ' ');

function Section({ icon: Icon, title, testid, children }) {
  return (
    <section className="svc-section" data-testid={testid}>
      <h4 className="flex items-center gap-1.5 text-sm font-bold mb-2"><Icon size={14} /> {title}</h4>
      {children}
    </section>
  );
}

function Row({ k, v, testid }) {
  return (
    <div className="flex gap-3 text-xs py-0.5" data-testid={testid}>
      <span className="w-32 shrink-0 svc-muted">{k}</span><span className="min-w-0 break-words">{v || '—'}</span>
    </div>
  );
}

const openPdf = async (caseId, path) => {
  try {
    const r = await fetch(`${API}/svc/cases/${caseId}/${path}`, auth());
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
    window.open(URL.createObjectURL(await r.blob()), '_blank');
  } catch (e) { notify.error('Could not open document', e.message); }
};

export function ProviderReadOnlyBanner({ caseId, provider, onDone }) {
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const takeOver = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/cases/${caseId}/take-over`, {}, auth());
      notify.success('Job taken over — you now have full control');
      onDone?.();
    } catch (e) { notify.error('Take over failed', e?.response?.data?.detail || e.message); }
    setBusy(false);
  };
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg p-2.5 text-xs" style={{ background: '#fff7ed', color: '#9a3412' }} data-testid="drawer-provider-readonly">
      <AlertTriangle size={14} />
      <span className="flex-1 min-w-[12rem]">
        With <b>{provider?.supplier_name || 'an outside provider'}</b> ({label(provider?.current_status)}). Read-only on the desk.
      </span>
      <button type="button" className="svc-btn svc-btn--sm" onClick={() => setConfirm(true)} disabled={busy} data-testid="drawer-take-over-btn">
        {busy ? <Loader2 size={12} className="animate-spin" /> : <Handshake size={12} />} Take over
      </button>
      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent data-testid="take-over-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Take this job over?</AlertDialogTitle>
            <AlertDialogDescription>
              {provider?.supplier_name || 'The provider'} will be marked as no longer handling it and Pulse gets full control on the desk.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="take-over-cancel">Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={takeOver} data-testid="take-over-confirm">Take over</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function ProviderSection({ provider }) {
  const cases = provider?.cases || [];
  return (
    <Section icon={Handshake} title="Outside provider" testid="jobfile-provider">
      {cases.length === 0 ? <p className="text-xs svc-muted">Handled by Pulse in-house.</p> : cases.map(sc => (
        <div key={sc.id} className="mb-2" data-testid={`jobfile-provider-${sc.id}`}>
          <Row k="Provider" v={`${sc.supplier_name || '—'} · ${sc.supplier_email || ''}`} />
          <Row k="Status" v={label(sc.current_status)} testid="jobfile-provider-status" />
          {(sc.status_history || []).map((h, i) => (
            <Row key={i} k={when(h.updated_at)} v={[label(h.status), h.engineer_name && `Engineer: ${h.engineer_name}`,
              h.estimated_arrival && `ETA: ${h.estimated_arrival}`, h.parts_required && `Parts: ${h.parts_required}`, h.notes].filter(Boolean).join(' · ')} />
          ))}
        </div>
      ))}
      {provider?.taken_over_at ? <Row k="Taken over" v={when(provider.taken_over_at)} testid="jobfile-taken-over" /> : null}
      {(provider?.messages || []).length > 0 && (
        <div className="mt-2 space-y-1" data-testid="jobfile-messages">
          <p className="text-xs font-semibold flex items-center gap-1"><MessageSquare size={12} /> Messages</p>
          {provider.messages.map(m => (
            <div key={m.id} className="text-xs rounded p-2" style={{ background: 'var(--svc-surface-2, #f4f4f5)' }}>
              <b>{m.author_name}</b> <span className="svc-muted">{when(m.created_at)}</span>
              <div>{m.message}</div>
              {(m.attachments || []).map((a, i) => <a key={i} href={a.url} target="_blank" rel="noreferrer" className="underline mr-2">{a.filename || 'attachment'}</a>)}
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

function CommercialSection({ c }) {
  const quotes = c?.quotes || [];
  const pos = c?.purchase_orders || [];
  return (
    <Section icon={Receipt} title="Quotes & purchase orders" testid="jobfile-commercial">
      <Row k="Customer PO" v={c?.customer_po_number} testid="jobfile-customer-po" />
      {quotes.length === 0 ? <Row k="Quotes" v="None raised" testid="jobfile-quotes-empty" /> : quotes.map(q => (
        <Row key={q.id} k={q.reference || q.quote_number || 'Quote'} v={`${label(q.status)} · ${q.currency_symbol || '£'}${Number(q.total || q.gross || 0).toFixed(2)}`} testid={`jobfile-quote-${q.id}`} />
      ))}
      {pos.length === 0 ? <Row k="Purchase orders" v="None raised" testid="jobfile-pos-empty" /> : pos.map(p => (
        <Row key={p.id} k={p.reference} v={`${label(p.status)} · ${p.supplier || ''} · £${Number(p.total || 0).toFixed(2)}`} testid={`jobfile-po-${p.id}`} />
      ))}
    </Section>
  );
}

export default function MODJobFileTab({ caseId }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    axios.get(`${API}/svc/cases/${caseId}/job-file`, auth()).then(r => setData(r.data))
      .catch(e => notify.error('Could not load job file', e?.response?.data?.detail || e.message));
  }, [caseId]);
  if (!data) return <div className="flex items-center gap-2 text-sm svc-muted"><Loader2 size={14} className="animate-spin" /> Loading job file…</div>;
  const { logged: l, work: w, documents: d } = data;
  return (
    <div className="space-y-4" data-testid="jobfile-tab">
      <Section icon={ClipboardList} title="What was logged" testid="jobfile-logged">
        <Row k="MOD ref" v={l.ticket_ref} testid="jobfile-ref" />
        <Row k="Reported" v={`${when(l.reported_at)}${l.reporter_name ? ` by ${l.reporter_name}` : ''}`} />
        <Row k="Site" v={[l.customer_name, l.site_address].filter(Boolean).join(' · ')} />
        <Row k="Machine" v={[l.asset_name, l.asset_serial && `S/N ${l.asset_serial}`].filter(Boolean).join(' · ')} />
        <Row k="Fault" v={l.fault_description || l.description} testid="jobfile-fault" />
        {l.photos?.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2" data-testid="jobfile-photos">
            {l.photos.map((p, i) => (
              <a key={i} href={p.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs underline"><Camera size={12} /> Photo {i + 1}</a>
            ))}
          </div>
        )}
      </Section>
      <ProviderSection provider={data.provider} />
      <Section icon={Wrench} title="Engineer work" testid="jobfile-work">
        <Row k="Status" v={label(w.status)} testid="jobfile-work-status" />
        <Row k="Engineer" v={w.assigned_engineer_name} />
        <Row k="Visits" v={w.visits?.length ? w.visits.map(v => when(v.start_at)).join(', ') : 'None booked'} />
        <Row k="Time on site" v={w.time_minutes ? `${w.time_minutes} min` : '—'} />
        <Row k="Completion note" v={w.resolution_note} />
        <Row k="Closed" v={w.closed_at && when(w.closed_at)} />
      </Section>
      <Section icon={FileText} title="Reports & certificates" testid="jobfile-documents">
        <div className="flex flex-wrap gap-2">
          <button type="button" className="svc-btn svc-btn--sm" disabled={!d.service_report_available} onClick={() => openPdf(caseId, 'service-report.pdf')} data-testid="jobfile-service-report-btn">
            <FileText size={12} /> Service report{d.service_report_available ? '' : ' (after sign-off)'}
          </button>
          {d.calibration_certificate_available && (
            <button type="button" className="svc-btn svc-btn--sm" onClick={() => openPdf(caseId, 'calibration/certificate.pdf')} data-testid="jobfile-cert-btn">
              <FileText size={12} /> Calibration certificate
            </button>
          )}
          <span className="text-xs svc-muted self-center">{d.per_machine_reports} machine report(s)</span>
        </div>
      </Section>
      <CommercialSection c={data.commercial} />
    </div>
  );
}
