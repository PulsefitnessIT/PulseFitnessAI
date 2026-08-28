import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  MapPin, CheckCircle, XCircle, RefreshCw, Plus, Wrench, Gauge, AlertTriangle,
  ClipboardCheck, PenTool, ChevronRight, ChevronLeft, Loader2, Radio, Save,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('crm_token') || ''}` });

const STEPS = [
  { id: 'asset_check', label: 'Asset Check', icon: ClipboardCheck },
  { id: 'service', label: 'Service', icon: Wrench },
  { id: 'calibration', label: 'Calibration', icon: Gauge },
  { id: 'faults', label: 'Faults', icon: AlertTriangle },
  { id: 'review', label: 'Review', icon: ClipboardCheck },
  { id: 'sign', label: 'Sign & Complete', icon: PenTool },
];

const RESULT_COLOR = { pass: '#16a34a', review: '#d97706', fail: '#dc2626', incomplete: '#94a3b8' };

const BigButton = ({ onClick, children, color = '#1d4ed8', icon: Icon, testId, disabled, variant }) => (
  <button data-testid={testId} onClick={onClick} disabled={disabled}
    className="flex items-center justify-center gap-2 rounded-2xl px-5 py-4 text-base font-semibold transition-transform active:scale-95 disabled:opacity-40 w-full"
    style={variant === 'outline'
      ? { border: `2px solid ${color}`, color, background: 'transparent' }
      : { background: color, color: '#fff' }}>
    {Icon && <Icon size={20} />}{children}
  </button>
);

// ── Numeric keypad for calibration entry (§15/§16) ──────────────────
function NumPad({ value, onChange, onDone }) {
  const press = (k) => {
    if (k === 'del') return onChange(value.slice(0, -1));
    if (k === '.' && value.includes('.')) return;
    onChange((value + k).slice(0, 6));
  };
  const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '.', '0', 'del'];
  return (
    <div className="grid grid-cols-3 gap-2 mt-3" data-testid="calib-numpad">
      {keys.map(k => (
        <button key={k} onClick={() => press(k)} data-testid={`numpad-${k}`}
          className="rounded-xl py-4 text-xl font-bold bg-slate-100 active:bg-slate-200">
          {k === 'del' ? '⌫' : k}</button>
      ))}
      <button onClick={onDone} data-testid="numpad-done"
        className="col-span-3 rounded-xl py-3 text-base font-semibold bg-blue-600 text-white">Done</button>
    </div>
  );
}

export default function BlueLightVisitWizard() {
  const { visitId } = useParams();
  const nav = useNavigate();
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [activeAsset, setActiveAsset] = useState(null); // for audit/service/calibration modal
  const [mode, setMode] = useState(null); // 'audit' | 'service' | 'calibration' | 'fault' | 'addAsset'
  const [toast, setToast] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/crm/v2/visits/${visitId}`, { headers: authHeaders() });
      setState(r.data);
    } catch (e) { setToast({ err: e.response?.data?.detail || 'Could not load the visit' }); }
    finally { setLoading(false); }
  }, [visitId]);

  useEffect(() => { load(); }, [load]);

  const post = async (path, body) => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/crm/v2/visits/${visitId}${path}`, body, { headers: authHeaders() });
      if (r.data.visit || r.data.progress) setState(r.data);
      else await load();
      return r.data;
    } catch (e) { setToast({ err: e.response?.data?.detail || 'Something went wrong' }); return null; }
    finally { setBusy(false); }
  };

  const lookupAsset = async ({ serial, model, name }) => {
    try {
      const params = new URLSearchParams();
      if (serial) params.set('serial', serial);
      if (model) params.set('model', model);
      if (name) params.set('name', name);
      const r = await axios.get(`${API}/crm/v2/visits/${visitId}/assets/lookup?${params.toString()}`, { headers: authHeaders() });
      return r.data.matches || [];
    } catch { return []; }
  };

  if (loading) return <div className="min-h-screen grid place-items-center bg-slate-50"><Loader2 className="animate-spin text-blue-600" /></div>;
  if (!state) return <div className="min-h-screen grid place-items-center bg-slate-50 text-slate-500">Visit not found.</div>;

  const { pack, assets, progress, completion_blockers, can_complete, contract, visit, calibrations } = state;
  const notStarted = !visit.started_at && visit.status !== 'in_progress' && visit.status !== 'completed';
  const treadmills = assets.filter(a => a.is_treadmill && a.audit && a.audit !== 'not_found');
  const presentAssets = assets.filter(a => ['present', 'update', 'replaced', 'add'].includes(a.audit));

  // ── START SCREEN (§6) ──
  if (notStarted) {
    return (
      <div className="min-h-screen bg-slate-50 pb-10">
        <div className="bg-blue-700 text-white px-5 pt-8 pb-6">
          <div className="flex items-center gap-2 text-blue-200 text-sm"><Radio size={16} /> Blue Light Service</div>
          <h1 className="text-2xl font-bold mt-1" data-testid="visit-station-name">{pack.station_name}</h1>
          <p className="text-blue-100 text-sm mt-1">{pack.station?.address}, {pack.station?.city} {pack.station?.postcode}</p>
        </div>
        <div className="p-5 space-y-4">
          <div className="rounded-2xl bg-white shadow p-4 grid grid-cols-3 text-center">
            <div><div className="text-2xl font-bold">{pack.expected_asset_count}</div><div className="text-xs text-slate-500">Machines</div></div>
            <div><div className="text-2xl font-bold text-blue-600">{pack.treadmill_count}</div><div className="text-xs text-slate-500">Treadmills</div></div>
            <div><div className="text-2xl font-bold">{contract.contract_number || '—'}</div><div className="text-xs text-slate-500">Contract</div></div>
          </div>
          <div className="rounded-2xl bg-white shadow p-4 text-sm text-slate-600 space-y-1">
            <div><b>Contact:</b> {pack.station?.contact_name} · {pack.station?.telephone}</div>
            {pack.station?.access_instructions && <div><b>Access:</b> {pack.station.access_instructions}</div>}
            {pack.station?.parking_info && <div><b>Parking:</b> {pack.station.parking_info}</div>}
          </div>
          <label className="flex items-start gap-3 rounded-2xl bg-white shadow p-4 text-sm">
            <input type="checkbox" id="confirm-site" data-testid="confirm-on-site" className="mt-1 w-5 h-5" />
            <span>I confirm I am at the correct station: <b>{pack.station_name}</b></span>
          </label>
          <BigButton testId="start-visit-btn" icon={MapPin} disabled={busy} color="#1d4ed8"
            onClick={async () => {
              const ok = document.getElementById('confirm-site')?.checked;
              if (!ok) { setToast({ err: 'Please tick the box to confirm you are at the correct station.' }); return; }
              await post('/start', { confirmed_on_site: true });
            }}>Start Station Service</BigButton>
        </div>
        {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
      </div>
    );
  }

  if (visit.status === 'completed') {
    return (
      <div className="min-h-screen bg-slate-50 grid place-items-center p-6">
        <div className="rounded-2xl bg-white shadow p-8 text-center max-w-sm" data-testid="visit-completed">
          <CheckCircle size={56} className="mx-auto text-green-600" />
          <h2 className="text-xl font-bold mt-3">Visit Completed</h2>
          <p className="text-slate-600 mt-1">{pack.station_name}</p>
          <p className="text-sm text-slate-500 mt-2">Next service due: <b>{visit.next_service_due}</b></p>
          <p className="text-xs text-slate-400 mt-1">Certificate: {visit.certificate_status?.replace(/_/g, ' ')}</p>
          {visit.certificate_id && (
            <button data-testid="download-cert-btn" onClick={() => {
              axios.get(`${API}/crm/v2/certificates/${visit.certificate_id}/download`, { headers: authHeaders(), responseType: 'blob' })
                .then(res => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' })); a.download = 'certificate.pdf'; a.click(); URL.revokeObjectURL(a.href); })
                .catch(() => {});
            }} className="mt-3 text-sm underline text-blue-600">Download certificate</button>
          )}
          <BigButton testId="back-to-matrix" color="#1d4ed8" onClick={() => nav('/crm?tab=contracts')}>Back to contracts</BigButton>
        </div>
      </div>
    );
  }

  const curStep = STEPS[step].id;

  return (
    <div className="min-h-screen bg-slate-50 pb-28">
      {/* Header + progress */}
      <div className="bg-blue-700 text-white px-5 pt-6 pb-4 sticky top-0 z-20">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-blue-200 text-xs flex items-center gap-1"><Radio size={13} /> Blue Light Service</div>
            <h1 className="text-lg font-bold" data-testid="wizard-station-name">{pack.station_name}</h1>
          </div>
          <div className="text-right text-xs text-blue-100">
            <div data-testid="wizard-asset-progress">{progress.accounted} / {progress.expected_assets} assets</div>
            <div>{progress.treadmills_calibrated}/{progress.treadmills_required} treadmills</div>
          </div>
        </div>
        <div className="flex gap-1 mt-3 overflow-x-auto no-scrollbar">
          {STEPS.map((s, i) => (
            <button key={s.id} onClick={() => setStep(i)} data-testid={`step-tab-${s.id}`}
              className="flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold whitespace-nowrap"
              style={{ background: i === step ? '#fff' : 'rgba(255,255,255,0.15)', color: i === step ? '#1d4ed8' : '#dbeafe' }}>
              <s.icon size={12} />{i + 1}. {s.label}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 space-y-3">
        {curStep === 'asset_check' && (
          <AssetList assets={assets} title="Confirm every asset" emptyDone={progress.assets_remaining === 0}
            onPick={(a) => { setActiveAsset(a); setMode('audit'); }}
            badge={(a) => a.audit ? { text: AUDIT_LABEL[a.audit], color: a.audit === 'not_found' ? '#dc2626' : '#16a34a' } : { text: 'Pending', color: '#94a3b8' }}
            footer={<BigButton testId="add-asset-btn" variant="outline" color="#1d4ed8" icon={Plus}
              onClick={() => { setActiveAsset(null); setMode('addAsset'); }}>Add machine not on list</BigButton>} />
        )}
        {curStep === 'service' && (
          <AssetList assets={presentAssets} title="Service each machine" emptyDone={progress.serviced === progress.to_service}
            onPick={(a) => { setActiveAsset(a); setMode('service'); }}
            badge={(a) => a.service_outcome ? { text: SERVICE_LABEL[a.service_outcome] || 'Done', color: '#16a34a' } : { text: 'To service', color: '#94a3b8' }} />
        )}
        {curStep === 'calibration' && (
          <div className="space-y-3">
            <StepTitle>{progress.treadmills_calibrated}/{progress.treadmills_required} treadmills calibrated</StepTitle>
            {treadmills.length === 0 && <Empty>No treadmills requiring calibration at this station.</Empty>}
            {treadmills.map(t => {
              const cal = calibrations[t.asset_key];
              return (
                <button key={t.asset_key} data-testid={`calib-asset-${t.asset_key}`}
                  onClick={() => { setActiveAsset(t); setMode('calibration'); }}
                  className="w-full text-left rounded-2xl bg-white shadow p-4 flex items-center justify-between">
                  <div>
                    <div className="font-semibold">{t.asset_name}</div>
                    <div className="text-xs text-slate-500">Serial: {t.serial_number || '—'}</div>
                  </div>
                  {cal?.overall
                    ? <span className="px-3 py-1 rounded-full text-xs font-bold text-white" style={{ background: RESULT_COLOR[cal.overall] }}>{cal.overall.toUpperCase()}</span>
                    : <span className="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-700">CALIBRATION REQUIRED</span>}
                </button>
              );
            })}
          </div>
        )}
        {curStep === 'faults' && (
          <div className="space-y-3">
            <StepTitle>Faults & actions</StepTitle>
            {(state.faults || []).length === 0 && <Empty>No faults raised yet.</Empty>}
            {(state.faults || []).map(f => (
              <div key={f.id} className="rounded-2xl bg-white shadow p-4" data-testid={`fault-row-${f.id}`}>
                <div className="font-semibold text-sm">{f.reference} · {f.title}</div>
                <div className="text-xs text-slate-500 mt-0.5">Priority {f.priority?.toUpperCase()}{f.out_of_service ? ' · OUT OF SERVICE' : ''}</div>
              </div>
            ))}
            <BigButton testId="raise-fault-btn" variant="outline" color="#dc2626" icon={AlertTriangle}
              onClick={() => { setActiveAsset(null); setMode('fault'); }}>Raise a fault</BigButton>
          </div>
        )}
        {curStep === 'review' && <ReviewPanel state={state} />}
        {curStep === 'sign' && (
          <SignPanel busy={busy} blockers={completion_blockers} canComplete={can_complete}
            onGoTo={(b) => { const idx = STEPS.findIndex(s => s.id === (b.type === 'calibration' ? 'calibration' : b.type === 'service' ? 'service' : 'asset_check')); setStep(idx >= 0 ? idx : 0); }}
            onComplete={async (sig, name, override) => {
              const r = await post('/complete', { signature_data: sig, engineer_name: name, override_reason: override });
              if (r?.success) { setToast({ ok: `Visit complete. Next service ${r.next_service_due}.` }); await load(); }
              else if (r?.blocked) setToast({ err: r.message });
            }}
            onPartial={async (reason) => { const r = await post('/partial', { reason }); if (r?.success) { setToast({ ok: 'Saved as partial visit.' }); nav('/crm?tab=contracts'); } }} />
        )}
      </div>

      {/* Sticky footer nav */}
      <div className="fixed bottom-0 inset-x-0 bg-white border-t p-3 flex gap-2 z-20">
        <button data-testid="wizard-prev" disabled={step === 0} onClick={() => setStep(s => Math.max(0, s - 1))}
          className="flex-1 rounded-xl py-3 font-semibold border disabled:opacity-30 flex items-center justify-center gap-1"><ChevronLeft size={18} />Back</button>
        <button data-testid="wizard-next" disabled={step === STEPS.length - 1} onClick={() => setStep(s => Math.min(STEPS.length - 1, s + 1))}
          className="flex-1 rounded-xl py-3 font-semibold bg-blue-600 text-white disabled:opacity-30 flex items-center justify-center gap-1">Next<ChevronRight size={18} /></button>
      </div>

      {/* Modals */}
      {mode === 'audit' && activeAsset && <AuditSheet asset={activeAsset} busy={busy} onClose={() => setMode(null)}
        onSubmit={async (payload) => { await post(`/assets/${activeAsset.asset_key}/audit`, payload); setMode(null); }} />}
      {mode === 'addAsset' && <AddAssetSheet busy={busy} onClose={() => setMode(null)}
        onLookup={lookupAsset}
        onRequestTransfer={async (assetId, reason) => {
          const r = await post(`/assets/${assetId}/transfer-request`, { reason });
          if (r) { setMode(null); setToast({ ok: 'Transfer requested — the office will review it.' }); }
        }}
        onSubmit={async (na) => { await post(`/assets/new-${Date.now()}/audit`, { action: 'add', new_asset: na }); setMode(null); }} />}
      {mode === 'service' && activeAsset && <ServiceSheet asset={activeAsset} busy={busy} onClose={() => setMode(null)}
        onSubmit={async (payload) => { await post(`/assets/${activeAsset.asset_key}/service`, payload); setMode(null); }}
        onRaiseFault={() => setMode('fault')} />}
      {mode === 'calibration' && activeAsset && <CalibrationSheet asset={activeAsset} config={contract.blue_light} busy={busy}
        existing={calibrations[activeAsset.asset_key]} onClose={() => setMode(null)}
        onSubmit={async (payload) => await post(`/treadmills/${activeAsset.asset_key}/calibration`, payload)} />}
      {mode === 'fault' && <FaultSheet asset={activeAsset} busy={busy} onClose={() => setMode(null)}
        onSubmit={async (payload) => { const r = await post('/faults', payload); if (r?.success) { setToast({ ok: `Fault ${r.fault.reference} raised.` }); setMode(null); await load(); } }} />}

      {toast && <Toast toast={toast} onClose={() => setToast(null)} />}
    </div>
  );
}

const AUDIT_LABEL = { present: 'Present', update: 'Updated', not_found: 'Not found', replaced: 'Replaced', add: 'New' };
const SERVICE_LABEL = {
  serviced_operational: 'Operational', serviced_minor_issue: 'Minor issue', serviced_fault_raised: 'Fault raised',
  out_of_service: 'Out of service', unable_to_service: 'Unable', asset_not_present: 'Not present', further_visit_required: 'Follow-up',
};

const StepTitle = ({ children }) => <h2 className="font-bold text-slate-700 px-1">{children}</h2>;
const Empty = ({ children }) => <div className="rounded-2xl bg-white shadow p-6 text-center text-slate-400 text-sm">{children}</div>;

function AssetList({ assets, title, onPick, badge, footer, emptyDone }) {
  return (
    <div className="space-y-3">
      <StepTitle>{title}{emptyDone && <span className="ml-2 text-green-600 text-sm">✓ all done</span>}</StepTitle>
      {assets.length === 0 && <Empty>Nothing here.</Empty>}
      {assets.map(a => {
        const b = badge(a);
        return (
          <button key={a.asset_key} onClick={() => onPick(a)} data-testid={`asset-row-${a.asset_key}`}
            className="w-full text-left rounded-2xl bg-white shadow p-4 flex items-center justify-between active:scale-[0.99] transition-transform">
            <div className="min-w-0">
              <div className="font-semibold truncate">{a.asset_name} {a.is_treadmill && <span className="text-blue-600 text-xs">· treadmill</span>}</div>
              <div className="text-xs text-slate-500 truncate">{a.equipment_type} · {a.serial_number || 'no serial'}</div>
            </div>
            <span className="px-3 py-1 rounded-full text-xs font-semibold flex-shrink-0" style={{ background: b.color + '22', color: b.color }}>{b.text}</span>
          </button>
        );
      })}
      {footer}
    </div>
  );
}

function Sheet({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 z-[300] flex items-end sm:items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl p-5 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-lg">{title}</h3>
          <button onClick={onClose} className="text-slate-400 p-1"><XCircle size={22} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

function AuditSheet({ asset, onSubmit, onClose, busy }) {
  const [view, setView] = useState('actions');
  const [changes, setChanges] = useState({ asset_name: asset.asset_name, model_code: asset.model_code || '', serial_number: asset.serial_number || '', location: asset.location || '' });
  const [reason, setReason] = useState('');
  const inp = 'w-full border rounded-xl px-3 py-2.5 mt-1';
  return (
    <Sheet title={asset.asset_name} onClose={onClose}>
      {view === 'actions' && (
        <div className="space-y-2">
          <BigButton testId="audit-present" icon={CheckCircle} color="#16a34a" disabled={busy} onClick={() => onSubmit({ action: 'present' })}>Confirm present</BigButton>
          <BigButton testId="audit-update" icon={PenTool} color="#1d4ed8" variant="outline" onClick={() => setView('update')}>Update details</BigButton>
          <BigButton testId="audit-notfound" icon={XCircle} color="#dc2626" variant="outline" onClick={() => setView('notfound')}>Machine not found</BigButton>
        </div>
      )}
      {view === 'update' && (
        <div className="space-y-2">
          {['asset_name', 'model_code', 'serial_number', 'location'].map(f => (
            <label key={f} className="block text-xs text-slate-500 capitalize">{f.replace('_', ' ')}
              <input className={inp} data-testid={`audit-field-${f}`} value={changes[f]} onChange={e => setChanges(c => ({ ...c, [f]: e.target.value }))} /></label>
          ))}
          <BigButton testId="audit-save-update" icon={Save} disabled={busy} onClick={() => onSubmit({ action: 'update', changes })}>Save changes</BigButton>
        </div>
      )}
      {view === 'notfound' && (
        <div className="space-y-2">
          <select className={inp} data-testid="audit-notfound-reason" value={reason} onChange={e => setReason(e.target.value)}>
            <option value="">Select a reason…</option>
            {['Removed from station', 'Disposed', 'Transferred', 'Temporarily away', 'Unable to locate', 'Unknown'].map(r => <option key={r} value={r}>{r}</option>)}
          </select>
          <BigButton testId="audit-save-notfound" color="#dc2626" disabled={busy || !reason} onClick={() => onSubmit({ action: 'not_found', reason })}>Mark not found</BigButton>
        </div>
      )}
    </Sheet>
  );
}

function AddAssetSheet({ onSubmit, onClose, busy, onLookup, onRequestTransfer }) {
  const [na, setNa] = useState({ asset_name: '', equipment_type: '', model_code: '', serial_number: '' });
  const [match, setMatch] = useState(null);
  const [ignore, setIgnore] = useState(false);
  const [checking, setChecking] = useState(false);
  const timer = useRef();
  const inp = 'w-full border rounded-xl px-3 py-2.5 mt-1';

  const runLookup = (next) => {
    clearTimeout(timer.current);
    const hasSignal = next.serial_number || (next.model_code && next.asset_name);
    if (!hasSignal || !onLookup) { setMatch(null); return; }
    timer.current = setTimeout(async () => {
      setChecking(true);
      const matches = await onLookup({ serial: next.serial_number, model: next.model_code, name: next.asset_name });
      setChecking(false);
      setMatch(matches[0] || null);
      setIgnore(false);
    }, 400);
  };

  const setField = (f, v) => {
    const next = { ...na, [f]: v };
    setNa(next);
    if (['serial_number', 'model_code', 'asset_name'].includes(f)) runLookup(next);
  };

  const showTransfer = match && !ignore;
  return (
    <Sheet title="Add machine" onClose={onClose}>
      <div className="space-y-2">
        {[['asset_name', 'Name / make+model'], ['equipment_type', 'Equipment type'], ['model_code', 'Model code'], ['serial_number', 'Serial number']].map(([f, l]) => (
          <label key={f} className="block text-xs text-slate-500">{l}
            <input className={inp} data-testid={`add-field-${f}`} value={na[f]} onChange={e => setField(f, e.target.value)} /></label>
        ))}
        {checking && <p className="text-xs text-slate-400" data-testid="add-lookup-checking">Checking the register…</p>}

        {showTransfer ? (
          <div className="rounded-2xl border-2 p-3 mt-1" data-testid="transfer-banner"
            style={{ borderColor: '#d97706', background: '#fffbeb' }}>
            <div className="flex items-start gap-2">
              <AlertTriangle size={18} className="text-amber-600 mt-0.5" />
              <div className="text-sm text-amber-900">
                This {match.match === 'serial' ? 'serial' : 'machine'} is already registered at{' '}
                <b>{match.station_name || 'another station'}</b>{match.serial_number ? <> ({match.serial_number})</> : null}.
                It looks like it may have been moved here.
              </div>
            </div>
            <div className="mt-3 space-y-2">
              <BigButton testId="transfer-request-btn" icon={RefreshCw} color="#d97706" disabled={busy}
                onClick={() => onRequestTransfer(match.asset_id, '')}>Request transfer to this station</BigButton>
              <button data-testid="transfer-add-anyway" className="w-full text-sm text-slate-500 underline py-1"
                onClick={() => setIgnore(true)}>No — add as a new machine anyway</button>
            </div>
          </div>
        ) : (
          <>
            <p className="text-xs text-slate-400">Unknown fields can be left blank — the office will review.</p>
            <BigButton testId="add-asset-save" icon={Plus} disabled={busy || !na.asset_name} onClick={() => onSubmit(na)}>Add machine</BigButton>
          </>
        )}
      </div>
    </Sheet>
  );
}

function ServiceSheet({ asset, onSubmit, onClose, onRaiseFault, busy }) {
  const opts = [
    ['serviced_operational', 'Serviced — Operational', '#16a34a'],
    ['serviced_minor_issue', 'Serviced — Minor issue', '#d97706'],
    ['serviced_fault_raised', 'Serviced — Fault raised', '#d97706'],
    ['out_of_service', 'Out of service', '#dc2626'],
    ['unable_to_service', 'Unable to service', '#dc2626'],
    ['further_visit_required', 'Further visit required', '#64748b'],
  ];
  const [notes, setNotes] = useState('');
  return (
    <Sheet title={`Service — ${asset.asset_name}`} onClose={onClose}>
      <textarea className="w-full border rounded-xl px-3 py-2 mb-3" rows={2} placeholder="Notes (optional)" data-testid="service-notes" value={notes} onChange={e => setNotes(e.target.value)} />
      <div className="space-y-2">
        {opts.map(([v, l, c]) => (
          <BigButton key={v} testId={`service-outcome-${v}`} color={c} variant="outline" disabled={busy} onClick={() => onSubmit({ outcome: v, notes })}>{l}</BigButton>
        ))}
      </div>
    </Sheet>
  );
}

function CalibrationSheet({ asset, config, existing, onSubmit, onClose, busy }) {
  const speedPts = config?.speed_points_mph || [3, 6, 9, 12];
  const inclinePts = config?.incline_points_pct || [0, 5, 10, 15];
  const [speed, setSpeed] = useState(() => speedPts.map(t => ({ target: t, measured: '' })));
  const [incline, setIncline] = useState(() => inclinePts.map(t => ({ target: t, measured: '' })));
  const [phase, setPhase] = useState('speed'); // speed -> incline -> result
  const [idx, setIdx] = useState(0);
  const [result, setResult] = useState(null);
  const [action, setAction] = useState('');
  const isRetest = !!existing;

  const rows = phase === 'speed' ? speed : incline;
  const setRows = phase === 'speed' ? setSpeed : setIncline;
  const unit = phase === 'speed' ? 'mph' : '%';

  const submit = async () => {
    const r = await onSubmit({
      speed: speed.map(s => ({ target: s.target, measured: parseFloat(s.measured) })),
      incline: incline.map(s => ({ target: s.target, measured: parseFloat(s.measured) })),
      action_if_fail: action || undefined,
    });
    if (r?.last_calibration) setResult(r.last_calibration);
  };

  if (result) {
    const failed = result.overall === 'fail';
    return (
      <Sheet title={`${asset.asset_name}`} onClose={onClose}>
        <div className="text-center py-2">
          <div className="inline-block px-4 py-1 rounded-full text-white font-bold" style={{ background: RESULT_COLOR[result.overall] }} data-testid="calib-result">{result.overall.toUpperCase()}</div>
        </div>
        <ResultTable rows={result.speed} label="Speed (mph)" />
        <ResultTable rows={result.incline} label="Incline (%)" />
        {failed && (
          <div className="mt-3 space-y-2">
            <p className="text-sm text-red-600 font-semibold">Calibration outside permitted tolerance. What action was taken?</p>
            <select className="w-full border rounded-xl px-3 py-2.5" data-testid="calib-fail-action" value={action} onChange={e => setAction(e.target.value)}>
              <option value="">Select…</option>
              {['adjusted_retested', 'fault_raised', 'taken_out_of_service', 'further_repair_required', 'technical_support_contacted'].map(a => <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>)}
            </select>
            <BigButton testId="calib-retest" icon={RefreshCw} color="#1d4ed8" onClick={() => {
              setSpeed(speedPts.map(t => ({ target: t, measured: '' })));
              setIncline(inclinePts.map(t => ({ target: t, measured: '' })));
              setResult(null); setPhase('speed'); setIdx(0);
            }}>Retest</BigButton>
          </div>
        )}
        <BigButton testId="calib-done" color="#16a34a" icon={CheckCircle} onClick={onClose}>Done{isRetest ? '' : ''}</BigButton>
      </Sheet>
    );
  }

  return (
    <Sheet title={`${asset.asset_name}`} onClose={onClose}>
      <div className="text-xs text-slate-500 mb-1">Serial: {asset.serial_number || '—'} {isRetest && <span className="text-amber-600 font-semibold">· RETEST</span>}</div>
      <div className="font-bold text-blue-700 uppercase text-sm">{phase} calibration</div>
      <div className="text-center my-3">
        <div className="text-slate-500 text-sm">Test {idx + 1} of {rows.length} — Machine setting</div>
        <div className="text-4xl font-bold my-1" data-testid="calib-target">{rows[idx].target} {unit}</div>
        <div className="text-slate-500 text-sm">Actual measured {phase}</div>
        <div className="text-3xl font-bold text-blue-700 border-b-2 border-blue-300 inline-block min-w-[100px]" data-testid="calib-measured">{rows[idx].measured || '—'} {rows[idx].measured && unit}</div>
      </div>
      <NumPad value={rows[idx].measured}
        onChange={(v) => setRows(rs => rs.map((r, i) => i === idx ? { ...r, measured: v } : r))}
        onDone={() => {
          if (idx < rows.length - 1) setIdx(idx + 1);
          else if (phase === 'speed') { setPhase('incline'); setIdx(0); }
          else submit();
        }} />
      <div className="flex justify-between mt-2 text-xs text-slate-400">
        <button onClick={() => idx > 0 ? setIdx(idx - 1) : (phase === 'incline' && (setPhase('speed'), setIdx(speedPts.length - 1)))}>◀ prev test</button>
        <button data-testid="calib-submit" onClick={submit} className="text-blue-600 font-semibold">Submit all →</button>
      </div>
    </Sheet>
  );
}

function ResultTable({ rows, label }) {
  return (
    <div className="mt-2">
      <div className="text-xs font-semibold text-slate-500">{label}</div>
      <div className="grid grid-cols-4 gap-1 mt-1">
        {rows.map((r, i) => (
          <div key={i} className="rounded-lg p-1.5 text-center text-xs" style={{ background: RESULT_COLOR[r.result] + '22' }}>
            <div className="font-bold">{r.target}</div>
            <div style={{ color: RESULT_COLOR[r.result] }}>{r.measured}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FaultSheet({ asset, onSubmit, onClose, busy }) {
  const [f, setF] = useState({ description: '', severity: 'p3', out_of_service: false, safety_concern: false });
  return (
    <Sheet title="Raise a fault" onClose={onClose}>
      {asset && <div className="text-xs text-slate-500 mb-2">{asset.asset_name} · {asset.serial_number}</div>}
      <textarea className="w-full border rounded-xl px-3 py-2 mb-2" rows={3} placeholder="Describe the fault" data-testid="fault-description" value={f.description} onChange={e => setF(x => ({ ...x, description: e.target.value }))} />
      <label className="block text-xs text-slate-500 mb-2">Severity
        <select className="w-full border rounded-xl px-3 py-2.5 mt-1" data-testid="fault-severity" value={f.severity} onChange={e => setF(x => ({ ...x, severity: e.target.value }))}>
          <option value="p1">P1 — Critical</option><option value="p2">P2 — High</option><option value="p3">P3 — Normal</option><option value="p4">P4 — Low</option>
        </select></label>
      <label className="flex items-center gap-2 text-sm mb-1"><input type="checkbox" data-testid="fault-oos" checked={f.out_of_service} onChange={e => setF(x => ({ ...x, out_of_service: e.target.checked }))} />Mark machine out of service</label>
      <label className="flex items-center gap-2 text-sm mb-3"><input type="checkbox" data-testid="fault-safety" checked={f.safety_concern} onChange={e => setF(x => ({ ...x, safety_concern: e.target.checked }))} />Safety concern</label>
      <BigButton testId="fault-submit" color="#dc2626" icon={AlertTriangle} disabled={busy || !f.description}
        onClick={() => onSubmit({ ...f, asset_key: asset?.asset_key, asset_serial: asset?.serial_number, asset_name: asset?.asset_name })}>Raise fault</BigButton>
    </Sheet>
  );
}

function ReviewPanel({ state }) {
  const p = state.progress;
  const rows = [
    ['Assets expected', p.expected_assets], ['Confirmed', p.confirmed], ['Updated', p.updated],
    ['New assets', p.new], ['Not found', p.not_found], ['Machines serviced', `${p.serviced}/${p.to_service}`],
    ['Treadmills calibrated', `${p.treadmills_calibrated}/${p.treadmills_required}`], ['Faults raised', p.faults_raised],
    ['Assets outstanding', p.assets_remaining],
  ];
  return (
    <div className="space-y-2" data-testid="review-panel">
      <StepTitle>Station service summary</StepTitle>
      <div className="rounded-2xl bg-white shadow divide-y">
        {rows.map(([l, v]) => (
          <div key={l} className="flex justify-between px-4 py-2.5 text-sm">
            <span className="text-slate-500">{l}</span><span className="font-semibold">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SignPanel({ blockers, canComplete, onComplete, onPartial, onGoTo, busy }) {
  const canvasRef = useRef(null);
  const [name, setName] = useState('');
  const [drawn, setDrawn] = useState(false);
  const draw = (e) => {
    const c = canvasRef.current; if (!c) return;
    const rect = c.getBoundingClientRect();
    const x = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
    const y = (e.touches ? e.touches[0].clientY : e.clientY) - rect.top;
    const ctx = c.getContext('2d');
    if (e.type === 'pointerdown' || e.type === 'touchstart' || e.type === 'mousedown') { ctx.beginPath(); ctx.moveTo(x, y); c._drawing = true; }
    else if (c._drawing) { ctx.lineTo(x, y); ctx.strokeStyle = '#111'; ctx.lineWidth = 2; ctx.stroke(); setDrawn(true); }
  };
  const stop = () => { if (canvasRef.current) canvasRef.current._drawing = false; };

  if (!canComplete) {
    return (
      <div className="space-y-3" data-testid="sign-blocked">
        <div className="rounded-2xl bg-red-50 border border-red-200 p-4">
          <div className="font-bold text-red-700 flex items-center gap-2"><AlertTriangle size={18} />You cannot complete this visit yet</div>
          <ul className="mt-2 space-y-2">
            {blockers.map((b, i) => (
              <li key={i} className="text-sm text-red-700 flex items-center justify-between gap-2">
                <span>{b.message}</span>
                <button data-testid={`blocker-goto-${b.type}`} onClick={() => onGoTo(b)} className="text-xs underline font-semibold flex-shrink-0">Go to</button>
              </li>
            ))}
          </ul>
        </div>
        <BigButton testId="save-partial-btn" variant="outline" color="#64748b" icon={Save}
          onClick={() => { const r = prompt('Reason for partial visit?'); if (r) onPartial(r); }}>Save as partial visit</BigButton>
      </div>
    );
  }
  return (
    <div className="space-y-3" data-testid="sign-panel">
      <StepTitle>Sign & complete</StepTitle>
      <p className="text-sm text-slate-600 px-1">I confirm the above service information is complete and accurate.</p>
      <input className="w-full border rounded-xl px-3 py-2.5" placeholder="Engineer name" data-testid="sign-name" value={name} onChange={e => setName(e.target.value)} />
      <div className="rounded-2xl bg-white shadow p-2">
        <div className="text-xs text-slate-400 px-1 mb-1">Signature</div>
        <canvas ref={canvasRef} width={340} height={140} data-testid="sign-canvas"
          className="w-full border rounded-xl touch-none bg-slate-50"
          onPointerDown={draw} onPointerMove={draw} onPointerUp={stop} onPointerLeave={stop} />
        <button className="text-xs text-slate-400 mt-1" onClick={() => { const c = canvasRef.current; c.getContext('2d').clearRect(0, 0, c.width, c.height); setDrawn(false); }}>Clear</button>
      </div>
      <BigButton testId="complete-visit-btn" color="#16a34a" icon={CheckCircle} disabled={busy || !name || !drawn}
        onClick={() => onComplete(canvasRef.current.toDataURL('image/png'), name)}>Complete visit</BigButton>
    </div>
  );
}

function Toast({ toast, onClose }) {
  useEffect(() => { const t = setTimeout(onClose, 3500); return () => clearTimeout(t); }, [onClose]);
  return (
    <div data-testid="wizard-toast" className="fixed bottom-24 inset-x-4 z-50 rounded-xl px-4 py-3 text-sm text-white shadow-lg"
      style={{ background: toast.err ? '#dc2626' : '#16a34a' }}>{toast.err || toast.ok}</div>
  );
}
