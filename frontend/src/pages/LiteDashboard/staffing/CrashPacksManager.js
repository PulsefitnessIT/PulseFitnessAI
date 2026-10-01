/**
 * CrashPacksManager — Operations > Staffing > Vehicles > Crash Packs.
 * Lists submitted crash packs and opens a clean, printable A4 incident report
 * assembling every captured field + photos. Managers can also edit the
 * per-organisation insurance/broker details shown to drivers.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2, ShieldAlert, Printer, X, Settings, Car, FileDown, MapPin } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const jwt = () => (typeof window !== 'undefined' ? localStorage.getItem('token') : '');
const fmt = (s) => (s ? new Date(s).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—');
const img = (fid) => `${API}/vehicle-checks/photo/${fid}?auth=${jwt()}`;

async function downloadPdf(id, headers, label) {
  const r = await axios.get(`${API}/crash-packs/${id}/pdf`, { headers, responseType: 'blob' });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement('a');
  a.href = url; a.download = `${label || 'Crash Pack'}.pdf`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export default function CrashPacksManager({ headers }) {
  const [packs, setPacks] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [settings, setSettings] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/crash-packs`, { headers }).then((r) => setPacks(r.data.packs || [])).catch(() => setPacks([]));
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  if (!packs) return <div className="p-6"><Loader2 className="animate-spin" style={{ color: 'var(--color-brand-cyan)' }} /></div>;

  return (
    <div className="space-y-3" data-testid="manager-crash-packs-view">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-bold" style={{ color: 'var(--theme-text)' }}>Crash Packs</h3>
        <button onClick={() => setSettings(true)} data-testid="crash-insurance-settings-btn"
          className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5 border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}><Settings size={13} /> Insurance details</button>
      </div>
      {packs.length === 0 ? (
        <div className="rounded-xl border p-10 text-center" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="crash-packs-empty">
          <ShieldAlert size={28} className="mx-auto mb-2 opacity-40" /><p className="text-sm font-semibold">No crash packs submitted</p>
          <p className="text-xs mt-1">When a driver reports a crash from their Staff Portal, it appears here to review and print.</p>
        </div>
      ) : (
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
          <table className="w-full text-sm">
            <thead><tr style={{ background: 'var(--theme-bg)' }}>
              {['Driver', 'Vehicle', 'Submitted', ''].map((h) => <th key={h} className="text-left px-4 py-2.5 text-[11px] font-bold uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)' }}>{h}</th>)}
            </tr></thead>
            <tbody>
              {packs.map((p) => (
                <tr key={p.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`crash-pack-row-${p.id}`}>
                  <td className="px-4 py-3 font-semibold" style={{ color: 'var(--theme-text)' }}>{p.reporter_name}</td>
                  <td className="px-4 py-3" style={{ color: 'var(--theme-text)' }}><span className="font-mono font-bold uppercase">{p.reg_no}</span> <span style={{ color: 'var(--theme-text-muted)' }}>{p.make_model}</span></td>
                  <td className="px-4 py-3" style={{ color: 'var(--theme-text-muted)' }}>{fmt(p.submitted_at)}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button onClick={() => downloadPdf(p.id, headers, `Crash Pack - ${p.reporter_name} - ${p.reg_no}`)} data-testid={`crash-pack-pdf-${p.id}`} className="text-xs font-semibold px-2.5 py-1.5 rounded-lg border mr-2" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} title="Download PDF"><FileDown size={13} className="inline" /> PDF</button>
                    <button onClick={() => setOpenId(p.id)} data-testid={`crash-pack-open-${p.id}`} className="text-xs font-bold px-3 py-1.5 rounded-lg" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>View / Print</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {openId && <ReportModal id={openId} headers={headers} onClose={() => setOpenId(null)} />}
      {settings && <InsuranceModal headers={headers} onClose={() => setSettings(false)} />}
    </div>
  );
}

function ReportModal({ id, headers, onClose }) {
  const [d, setD] = useState(null);
  useEffect(() => { axios.get(`${API}/crash-packs/${id}`, { headers }).then((r) => setD(r.data)).catch(() => setD({ error: true })); }, [id, headers]);
  const pack = d?.pack; const ins = d?.insurance || {};
  const data = pack?.data || {}; const photos = pack?.photos || {};
  const yd = data.your_details || {}; const ac = data.accident || {}; const po = data.police || {};
  const allPhotos = [['Your vehicle', photos.vehicle_damage], ['Scene', photos.scene], ['Other vehicle(s)', photos.other_vehicle], ['Sketch', photos.sketch]];

  return (
    <div className="fixed inset-0 z-[200] overflow-y-auto bg-black/60 print:bg-white print:static" data-testid="crash-report-modal">
      <div className="min-h-full flex items-start justify-center p-4 print:p-0">
        <div className="bg-white w-full max-w-4xl rounded-xl shadow-2xl print:shadow-none print:rounded-none" id="crash-report-print">
          <div className="flex items-center justify-between px-6 py-3 border-b border-slate-200 print:hidden">
            <span className="font-bold text-slate-900">Fleet Incident Report</span>
            <div className="flex gap-2">
              <button onClick={() => downloadPdf(id, headers, 'Crash Pack Report')} data-testid="download-crash-pdf-btn" className="inline-flex items-center gap-1.5 text-sm font-bold px-4 py-2 rounded-lg border border-slate-300 text-slate-700"><FileDown size={15} /> PDF</button>
              <button onClick={() => window.print()} data-testid="print-crash-report-btn" className="inline-flex items-center gap-1.5 text-sm font-bold px-4 py-2 rounded-lg bg-cyan-500 text-white"><Printer size={15} /> Print</button>
              <button onClick={onClose} className="text-slate-400 hover:text-slate-700"><X size={20} /></button>
            </div>
          </div>
          {!d ? <div className="p-16 flex justify-center"><Loader2 className="animate-spin text-cyan-500" /></div> : (
            <div className="p-8 text-slate-900 text-sm leading-relaxed">
              <div className="flex items-center justify-between border-b-2 border-slate-900 pb-3 mb-4">
                <div><h1 className="text-xl font-extrabold">Pulse Fitness — Fleet Incident Report</h1><p className="text-xs text-slate-500">Confidential · Incident #{(pack.id || '').slice(0, 8).toUpperCase()}</p></div>
                <div className="text-right text-xs"><div><strong>Policy</strong> {ins.qbe_policy_number}</div><div>{fmt(pack.submitted_at)}</div></div>
              </div>

              <Section title="A · Driver & vehicle">
                <Grid rows={[['Driver', pack.reporter_name], ['Mobile', yd.mobile], ['Address', yd.address], ['Date of birth', yd.date_of_birth], ['UK residency', yd.length_residency], ['Passed test', yd.date_passed_test], ['Registration', yd.reg_number || pack.reg_no], ['Make / model', yd.make_model || pack.make_model], ['Mileage', yd.mileage], ['Use', yd.use], ['Accidents (5y)', yd.accidents_5yr], ['Convictions (5y)', yd.convictions_5yr], ['Disqualifications (11y)', yd.disqualifications_11yr], ['DVLA medical', yd.medical_dvla]]} />
                {yd.vehicle_damage && <p className="mt-2"><strong>Damage to own vehicle:</strong> {yd.vehicle_damage}</p>}
              </Section>

              <Section title="B · Incident">
                <Grid rows={[['Date', ac.date], ['Time', ac.time], ['Location', ac.location]]} />
                {ac.gps && (
                  <div className="mt-2 flex items-center gap-2 text-sm" data-testid="report-gps">
                    <MapPin size={15} className="text-cyan-600" />
                    <span className="font-mono">{ac.gps.lat?.toFixed(5)}, {ac.gps.lng?.toFixed(5)}</span>
                    <span className="text-slate-400 text-xs">(±{ac.gps.accuracy}m)</span>
                    <a href={`https://maps.google.com/?q=${ac.gps.lat},${ac.gps.lng}`} target="_blank" rel="noreferrer" className="text-cyan-600 font-semibold underline print:hidden">View on map</a>
                  </div>
                )}
                <p className="mt-2 whitespace-pre-wrap">{ac.detail || '—'}</p>
                {ac.sketch_note && <p className="mt-1 text-slate-600"><strong>Sketch note:</strong> {ac.sketch_note}</p>}
              </Section>

              <Section title="C · Photos & sketch">
                {allPhotos.every(([, a]) => !(a || []).length) ? <p className="text-slate-500">No photos attached.</p> : allPhotos.map(([lab, a]) => (a || []).length ? (
                  <div key={lab} className="mb-3" style={{ breakInside: 'avoid' }}>
                    <div className="text-xs font-bold uppercase text-slate-500 mb-1">{lab}</div>
                    <div className="grid grid-cols-3 gap-2">{a.map((fid) => <img key={fid} alt={lab} src={img(fid)} className="w-full h-32 object-cover rounded border border-slate-200" />)}</div>
                  </div>
                ) : null)}
              </Section>

              <Section title="D · Other drivers & witnesses">
                {(data.third_parties || []).length === 0 ? <p className="text-slate-500">No other drivers recorded.</p> : (data.third_parties || []).map((t, i) => (
                  <div key={i} className="mb-2 pb-2 border-b border-slate-100"><strong>Driver {i + 1}:</strong> {[t.name, t.phone, t.vehicle, t.reg, t.insurer, t.passengers && `${t.passengers} passengers`, t.damage, t.injuries].filter(Boolean).join(' · ') || '—'}</div>
                ))}
                {(data.witnesses || []).length > 0 && <div className="mt-2"><strong>Witnesses:</strong> {(data.witnesses || []).map((w) => [w.name, w.phone, w.note].filter(Boolean).join(' ')).join('; ')}</div>}
              </Section>

              <Section title="E · Police">
                {po.attended === 'yes' ? <Grid rows={[['Attended', 'Yes'], ['Crime ref', po.crime_ref], ['Officer', po.officer_name], ['Collar no.', po.collar_number], ['Station', po.station]]} /> : <p className="text-slate-500">Police did not attend.</p>}
              </Section>

              <Section title="F · Insurance / claims">
                <Grid rows={[['QBE 24h claim line', ins.qbe_claim_line], ['Policy number', ins.qbe_policy_number], ['Broker', `${ins.broker_name || ''} ${ins.broker_phone || ''}`]]} />
              </Section>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const Section = ({ title, children }) => (
  <div className="mb-5" style={{ breakInside: 'avoid' }}>
    <h2 className="text-sm font-extrabold uppercase tracking-wide bg-slate-100 px-2 py-1 rounded mb-2">{title}</h2>
    {children}
  </div>
);
const Grid = ({ rows }) => (
  <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1">
    {rows.filter(([, v]) => v).map(([k, v]) => <div key={k}><span className="text-[11px] uppercase text-slate-400 font-semibold block">{k}</span><span>{String(v)}</span></div>)}
  </div>
);

function InsuranceModal({ headers, onClose }) {
  const [f, setF] = useState(null); const [busy, setBusy] = useState(false);
  useEffect(() => { axios.get(`${API}/crash-packs/insurance-settings`, { headers }).then((r) => setF(r.data.insurance)).catch(() => setF({})); }, [headers]);
  const save = async () => { setBusy(true); try { await axios.put(`${API}/crash-packs/insurance-settings`, f, { headers }); onClose(); } finally { setBusy(false); } };
  const fields = [['qbe_claim_line', 'QBE 24h claim line'], ['qbe_claim_note', 'Claim line note'], ['qbe_policy_number', 'QBE policy number'], ['broker_name', 'Broker name'], ['broker_phone', 'Broker phone'], ['broker_note', 'Broker note']];
  return (
    <div className="fixed inset-0 z-[210] bg-black/60 flex items-center justify-center p-4" data-testid="crash-insurance-modal">
      <div className="bg-white rounded-2xl w-full max-w-md p-5 shadow-2xl">
        <div className="flex items-center justify-between mb-3"><h3 className="font-extrabold text-slate-900">Insurance details</h3><button onClick={onClose} className="text-slate-400"><X size={18} /></button></div>
        {!f ? <Loader2 className="animate-spin text-cyan-500" /> : (
          <div className="space-y-2.5">
            {fields.map(([k, l]) => (
              <label className="block" key={k}><span className="text-[11px] font-semibold uppercase text-slate-500">{l}</span>
                <input className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" value={f[k] || ''} onChange={(e) => setF((p) => ({ ...p, [k]: e.target.value }))} data-testid={`crash-ins-${k}`} /></label>
            ))}
            <div className="flex justify-end gap-2 pt-2">
              <button onClick={onClose} className="px-3 py-1.5 text-sm font-semibold text-slate-500">Cancel</button>
              <button onClick={save} disabled={busy} data-testid="crash-ins-save" className="px-4 py-1.5 text-sm font-bold rounded-lg bg-cyan-500 text-white disabled:opacity-50">{busy ? 'Saving…' : 'Save'}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
