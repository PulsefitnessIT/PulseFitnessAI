/**
 * CrashPackWizard — calm, shock-friendly step-by-step crash report for drivers.
 * Lives in the Staff Portal (Vehicle tab). Autosaves a draft between steps and
 * supports phone-camera photo capture. Insurance guidance is shown at the end.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import {
  Loader2, X, ChevronLeft, ChevronRight, ShieldAlert, Phone, Copy, Camera,
  Plus, Trash2, CheckCircle2, Car, Check, PartyPopper, MapPin,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const CORE = '#19CDFF';

async function compress(file, maxEdge = 1600, q = 0.8) {
  if (!file?.type?.startsWith('image/')) return file;
  try {
    const url = await new Promise((r, j) => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.onerror = j; fr.readAsDataURL(file); });
    const img = await new Promise((r, j) => { const im = new Image(); im.onload = () => r(im); im.onerror = j; im.src = url; });
    const s = Math.min(1, maxEdge / Math.max(img.width, img.height));
    const c = document.createElement('canvas'); c.width = Math.round(img.width * s); c.height = Math.round(img.height * s);
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    const blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', q));
    return blob ? new File([blob], 'photo.jpg', { type: 'image/jpeg' }) : file;
  } catch { return file; }
}

const STEPS = ['Safe?', 'Your details', 'The accident', 'Photos', 'Other drivers', 'Witnesses', 'Police', 'Review'];

const field = 'w-full rounded-xl border px-3.5 py-3 text-base bg-white';
const fStyle = { borderColor: 'var(--theme-border)', color: 'var(--theme-text)' };
const Label = ({ children }) => <span className="block text-[13px] font-semibold mb-1.5" style={{ color: 'var(--theme-text-muted)' }}>{children}</span>;

function YesNo({ value, onChange, testId }) {
  return (
    <div className="grid grid-cols-2 gap-2" data-testid={testId}>
      {[['yes', 'Yes'], ['no', 'No']].map(([v, l]) => (
        <button key={v} type="button" onClick={() => onChange(v)} data-testid={`${testId}-${v}`}
          className="min-h-[52px] rounded-xl border-2 font-bold text-base transition-all active:scale-[0.98]"
          style={value === v
            ? (v === 'yes' ? { background: '#FEF3C7', borderColor: '#F59E0B', color: '#92400E' } : { background: CORE, borderColor: CORE, color: '#00121a' })
            : { borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)', background: 'var(--theme-surface)' }}>
          {l}
        </button>
      ))}
    </div>
  );
}

function PhotoTile({ label, ids, onAdd, onRemove, jwt, busy, testId }) {
  const ref = useRef();
  return (
    <div data-testid={testId}>
      <Label>{label}</Label>
      <div className="grid grid-cols-3 gap-2">
        {(ids || []).map((fid) => (
          <div key={fid} className="relative rounded-xl overflow-hidden border aspect-square" style={{ borderColor: 'var(--theme-border)' }}>
            <img alt="" src={`${API}/vehicle-checks/photo/${fid}?auth=${jwt}`} className="w-full h-full object-cover" />
            <button type="button" onClick={() => onRemove(fid)} className="absolute top-1 right-1 bg-black/60 text-white rounded-full p-1" data-testid={`${testId}-remove-${fid}`}><X size={13} /></button>
          </div>
        ))}
        <button type="button" onClick={() => ref.current?.click()} disabled={busy} data-testid={`${testId}-add`}
          className="aspect-square rounded-xl border-2 border-dashed flex flex-col items-center justify-center gap-1 text-xs font-semibold disabled:opacity-50"
          style={{ borderColor: CORE, color: CORE }}>
          {busy ? <Loader2 size={20} className="animate-spin" /> : <Camera size={22} />} Add
        </button>
      </div>
      <input ref={ref} type="file" accept="image/*" capture="environment" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onAdd(f); e.target.value = ''; }} />
    </div>
  );
}

export default function CrashPackWizard({ H, jwt, resumePackId, onClose, onDone }) {
  const [boot, setBoot] = useState(null);
  const [packId, setPackId] = useState(resumePackId || null);
  const [vehicleId, setVehicleId] = useState('');
  const [step, setStep] = useState(0);
  const [data, setData] = useState({ your_details: {}, accident: {}, third_parties: [], witnesses: [], police: {} });
  const [photos, setPhotos] = useState({ vehicle_damage: [], scene: [], other_vehicle: [], sketch: [] });
  const [busy, setBusy] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [saved, setSaved] = useState('');
  const [err, setErr] = useState('');
  const [done, setDone] = useState(false);
  const [declared, setDeclared] = useState(false);
  const [geo, setGeo] = useState(''); // '', 'locating', 'ok', 'denied'

  const captureGps = useCallback(() => {
    if (!navigator.geolocation) { setGeo('denied'); return; }
    setGeo('locating');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setD('accident', { gps: {
          lat: pos.coords.latitude, lng: pos.coords.longitude,
          accuracy: Math.round(pos.coords.accuracy || 0), captured_at: new Date().toISOString(),
        } });
        setGeo('ok');
      },
      () => setGeo('denied'),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    axios.get(`${API}/new-starter/portal/crash-packs/bootstrap`, { headers: H })
      .then((r) => {
        setBoot(r.data);
        if (!resumePackId && (r.data.vehicles || []).length === 1) setVehicleId(r.data.vehicles[0].id);
      }).catch(() => setBoot({ vehicles: [], insurance: {} }));
  }, [H, resumePackId]);

  useEffect(() => {
    if (!resumePackId) return;
    axios.get(`${API}/new-starter/portal/crash-packs/${resumePackId}`, { headers: H }).then((r) => {
      const p = r.data.pack; setVehicleId(p.vehicle_id);
      setData(p.data || {}); setPhotos(p.photos || {});
    }).catch(() => {});
  }, [resumePackId, H]);

  const ensurePack = useCallback(async () => {
    if (packId) return packId;
    const r = await axios.post(`${API}/new-starter/portal/crash-packs`, { vehicle_id: vehicleId }, { headers: H });
    const p = r.data.pack; setPackId(p.id); setData(p.data || {}); setPhotos(p.photos || {});
    return p.id;
  }, [packId, vehicleId, H]);

  const save = useCallback(async (nextData, nextPhotos) => {
    if (!packId) return;
    try {
      await axios.put(`${API}/new-starter/portal/crash-packs/${packId}`,
        { data: nextData || data, photos: nextPhotos || photos }, { headers: H });
      setSaved('Draft saved'); setTimeout(() => setSaved(''), 1500);
    } catch { /* keep local state; will retry on next step */ }
  }, [packId, data, photos, H]);

  const setD = (section, patch) => setData((d) => ({ ...d, [section]: { ...(d[section] || {}), ...patch } }));

  const uploadPhoto = async (slot, file) => {
    setErr(''); setPhotoBusy(true);
    try {
      const pid = await ensurePack();
      const fd = new FormData(); fd.append('file', await compress(file));
      const r = await axios.post(`${API}/new-starter/portal/crash-packs/photo`, fd, { headers: { ...H, 'Content-Type': 'multipart/form-data' } });
      const next = { ...photos, [slot]: [...(photos[slot] || []), r.data.file_id] };
      setPhotos(next);
      await axios.put(`${API}/new-starter/portal/crash-packs/${pid}`, { photos: next }, { headers: H });
    } catch (e) { setErr(e?.response?.data?.detail || 'Photo upload failed — check your connection and try again.'); }
    finally { setPhotoBusy(false); }
  };
  const removePhoto = async (slot, fid) => {
    const next = { ...photos, [slot]: (photos[slot] || []).filter((x) => x !== fid) };
    setPhotos(next); if (packId) axios.put(`${API}/new-starter/portal/crash-packs/${packId}`, { photos: next }, { headers: H }).catch(() => {});
  };

  const go = async (dir) => {
    setErr('');
    if (dir > 0 && step === 0) {
      if (!vehicleId) { setErr('Please choose the vehicle you were driving.'); return; }
      setBusy(true); try { await ensurePack(); } catch { setErr('Could not start the crash pack. Try again.'); setBusy(false); return; } setBusy(false);
    }
    if (dir > 0 && step >= 1) await save();
    setStep((s) => Math.min(STEPS.length - 1, Math.max(0, s + dir)));
    window.scrollTo(0, 0);
  };

  const submit = async () => {
    if (!declared) { setErr('Please confirm the declaration to submit.'); return; }
    setBusy(true); setErr('');
    try {
      await axios.post(`${API}/new-starter/portal/crash-packs/${packId}/submit`, { data, photos }, { headers: H });
      setDone(true);
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not submit — please check your details.'); }
    finally { setBusy(false); }
  };

  const ins = boot?.insurance || {};
  const yd = data.your_details || {}; const ac = data.accident || {};
  // Auto-capture location the first time the driver reaches the accident step.
  useEffect(() => {
    if (step === 2 && geo === '' && !(data.accident || {}).gps) captureGps();
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps

  const shell = (body) => (
    <div className="fixed inset-0 z-[200] overflow-y-auto" style={{ background: 'var(--theme-bg)' }} data-testid="crash-pack-wizard-modal">
      <div className="sticky top-0 z-10 backdrop-blur-md border-b px-4 py-3 flex items-center justify-between gap-3"
        style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <button onClick={onClose} className="inline-flex items-center gap-1 text-sm font-semibold" style={{ color: 'var(--theme-text-muted)' }} data-testid="crash-pack-close"><X size={18} /> Close</button>
        <div className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>Crash Pack</div>
        <span className="text-[11px] font-semibold min-w-[70px] text-right" style={{ color: saved ? '#10B981' : 'transparent' }}>{saved || '.'}</span>
      </div>
      {!done && (
        <div className="h-1.5 w-full" style={{ background: 'var(--theme-border)' }}>
          <div className="h-full transition-all" style={{ width: `${(step / (STEPS.length - 1)) * 100}%`, background: CORE }} />
        </div>
      )}
      <div className="max-w-xl mx-auto px-4 pb-28 pt-5 space-y-5">{body}</div>
      {!done && (
        <div className="fixed bottom-0 left-0 right-0 z-20 p-4 backdrop-blur-md border-t flex items-center justify-between gap-3"
          style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <button onClick={() => go(-1)} disabled={step === 0 || busy} data-testid="crash-prev"
            className="inline-flex items-center gap-1 px-4 py-3 rounded-xl border font-semibold disabled:opacity-40" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}><ChevronLeft size={18} /> Back</button>
          <div className="text-xs font-semibold" style={{ color: 'var(--theme-text-muted)' }}>Step {step + 1} / {STEPS.length}</div>
          {step < STEPS.length - 1 ? (
            <button onClick={() => go(1)} disabled={busy} data-testid="crash-next"
              className="inline-flex items-center gap-1 px-5 py-3 rounded-xl font-bold disabled:opacity-50" style={{ background: CORE, color: '#00121a' }}>{busy ? <Loader2 size={18} className="animate-spin" /> : <>Next <ChevronRight size={18} /></>}</button>
          ) : (
            <button onClick={submit} disabled={busy} data-testid="submit-crash-pack-btn"
              className="inline-flex items-center gap-1 px-5 py-3 rounded-xl font-bold disabled:opacity-50" style={{ background: '#10B981', color: 'white' }}>{busy ? <Loader2 size={18} className="animate-spin" /> : <>Submit <Check size={18} /></>}</button>
          )}
        </div>
      )}
      {err && <div className="fixed bottom-20 left-0 right-0 px-4 z-30"><div className="max-w-xl mx-auto rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-sm px-4 py-2.5" data-testid="crash-error">{err}</div></div>}
    </div>
  );

  if (!boot) return shell(<div className="flex justify-center py-16"><Loader2 className="animate-spin" style={{ color: CORE }} /></div>);

  if (done) {
    return shell(
      <div className="text-center py-10 space-y-5" data-testid="crash-pack-done">
        <div className="mx-auto w-16 h-16 rounded-full flex items-center justify-center" style={{ background: '#D1FAE5' }}><PartyPopper size={30} className="text-emerald-600" /></div>
        <h2 className="text-2xl font-extrabold" style={{ color: 'var(--theme-text)' }}>Crash Pack sent</h2>
        <p className="text-base" style={{ color: 'var(--theme-text-muted)' }}>Your manager has been notified. Keep safe — here are the important numbers to call now.</p>
        <InsuranceBlock ins={ins} />
        <button onClick={() => { onDone?.(); onClose(); }} className="mt-2 px-6 py-3 rounded-xl font-bold" style={{ background: CORE, color: '#00121a' }} data-testid="crash-done-close">Done</button>
      </div>,
    );
  }

  // Steps
  let body = null;
  if (step === 0) {
    body = (
      <div className="space-y-5" data-testid="step-safety-reassurance">
        <div className="rounded-2xl border-2 p-4 flex items-start gap-3" style={{ background: '#FFFBEB', borderColor: '#FDE68A' }}>
          <ShieldAlert className="text-amber-500 shrink-0 mt-0.5" size={22} />
          <div><div className="font-bold text-amber-900">Take a breath — you're okay.</div><p className="text-sm text-amber-800 mt-1">Make sure everyone is safe and out of danger first. When you're ready, this will walk you through everything, one step at a time. You can stop and come back anytime.</p></div>
        </div>
        <div className="rounded-2xl border p-4 space-y-2" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <div className="font-bold text-base" style={{ color: 'var(--theme-text)' }}>A few important things</div>
          {(ins.rules || []).map((r, i) => (
            <div key={i} className="flex items-start gap-2 text-sm" style={{ color: 'var(--theme-text)' }}><Check size={16} className="text-emerald-500 shrink-0 mt-0.5" /> {r}</div>
          ))}
        </div>
        <div>
          <Label>Which vehicle were you driving?</Label>
          {(boot.vehicles || []).length === 0 ? (
            <div className="rounded-xl border p-4 text-sm" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>No assigned vehicle found. Please contact your manager.</div>
          ) : (
            <div className="space-y-2">
              {boot.vehicles.map((v) => (
                <button key={v.id} type="button" onClick={() => setVehicleId(v.id)} data-testid={`crash-vehicle-${v.id}`}
                  className="w-full flex items-center gap-3 rounded-xl border-2 p-3.5 text-left"
                  style={vehicleId === v.id ? { borderColor: CORE, background: 'var(--theme-surface)' } : { borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
                  <Car size={20} style={{ color: CORE }} />
                  <div><div className="font-bold uppercase" style={{ color: 'var(--theme-text)' }}>{v.reg_no}</div><div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{v.make_model || 'Vehicle'}</div></div>
                  {vehicleId === v.id && <Check size={18} className="ml-auto text-emerald-500" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  } else if (step === 1) {
    const toggles = [['accidents_5yr', 'Any accidents in the last 5 years?'], ['convictions_5yr', 'Any convictions in the last 5 years?'], ['disqualifications_11yr', 'Any disqualifications in the last 11 years?'], ['medical_dvla', 'Any medical conditions notifiable to the DVLA?']];
    body = (
      <div className="space-y-4" data-testid="step-your-details">
        <StepHead title="Your details & vehicle" sub="We've pre-filled what we can — just check it's right." />
        {[['name', 'Your name'], ['mobile', 'Mobile number'], ['date_of_birth', 'Date of birth'], ['length_residency', 'Length of residency in the UK'], ['date_passed_test', 'Date you passed your driving test']].map(([k, l]) => (
          <label className="block" key={k}><Label>{l}</Label><input className={field} style={fStyle} value={yd[k] ?? (k === 'name' ? boot.prefill?.name : k === 'mobile' ? boot.prefill?.mobile : k === 'date_of_birth' ? boot.prefill?.date_of_birth : '') ?? ''} onChange={(e) => setD('your_details', { [k]: e.target.value })} data-testid={`yd-${k}`} /></label>
        ))}
        <label className="block"><Label>Home address</Label><textarea rows={2} className={field} style={fStyle} value={yd.address ?? boot.prefill?.address ?? ''} onChange={(e) => setD('your_details', { address: e.target.value })} data-testid="yd-address" /></label>
        <div className="grid grid-cols-3 gap-2">
          {[['reg_number', 'Reg'], ['make_model', 'Make / model'], ['mileage', 'Mileage']].map(([k, l]) => (
            <label className="block" key={k}><Label>{l}</Label><input className={field} style={fStyle} value={yd[k] || ''} onChange={(e) => setD('your_details', { [k]: e.target.value })} data-testid={`yd-${k}`} /></label>
          ))}
        </div>
        <label className="block"><Label>Social or business use</Label>
          <select className={field} style={fStyle} value={yd.use || ''} onChange={(e) => setD('your_details', { use: e.target.value })} data-testid="yd-use"><option value="">Select…</option><option>Social</option><option>Business</option><option>Social & Business</option></select></label>
        {toggles.map(([k, l]) => (
          <div key={k}><Label>{l}</Label><YesNo value={yd[k]} onChange={(v) => setD('your_details', { [k]: v })} testId={`yd-${k}`} /></div>
        ))}
        <label className="block"><Label>Any damage to your vehicle?</Label><textarea rows={3} className={field} style={fStyle} value={yd.vehicle_damage || ''} onChange={(e) => setD('your_details', { vehicle_damage: e.target.value })} data-testid="yd-damage" /></label>
      </div>
    );
  } else if (step === 2) {
    body = (
      <div className="space-y-4" data-testid="step-the-accident">
        <StepHead title="The accident" sub="When and where it happened." />
        <div className="grid grid-cols-2 gap-2">
          <label className="block"><Label>Date</Label><input type="date" className={field} style={fStyle} value={ac.date || ''} onChange={(e) => setD('accident', { date: e.target.value })} data-testid="ac-date" /></label>
          <label className="block"><Label>Time</Label><input type="time" className={field} style={fStyle} value={ac.time || ''} onChange={(e) => setD('accident', { time: e.target.value })} data-testid="ac-time" /></label>
        </div>
        <label className="block"><Label>Location (street / junction / postcode)</Label><input className={field} style={fStyle} value={ac.location || ''} onChange={(e) => setD('accident', { location: e.target.value })} data-testid="ac-location" /></label>
        <div className="rounded-xl border p-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="ac-gps-card">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2"><MapPin size={18} style={{ color: CORE }} /><span className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Your location</span></div>
            <button type="button" onClick={captureGps} disabled={geo === 'locating'} data-testid="ac-gps-capture"
              className="text-xs font-bold px-3 py-1.5 rounded-full border disabled:opacity-50" style={{ borderColor: CORE, color: CORE }}>
              {geo === 'locating' ? 'Locating…' : ac.gps ? 'Update' : 'Capture'}
            </button>
          </div>
          {ac.gps ? (
            <div className="mt-2 text-sm" style={{ color: 'var(--theme-text-muted)' }} data-testid="ac-gps-value">
              📍 {ac.gps.lat.toFixed(5)}, {ac.gps.lng.toFixed(5)} <span className="text-xs">(±{ac.gps.accuracy}m)</span>
              <a href={`https://maps.google.com/?q=${ac.gps.lat},${ac.gps.lng}`} target="_blank" rel="noreferrer" className="ml-2 font-semibold underline" style={{ color: CORE }}>View map</a>
            </div>
          ) : (
            <p className="mt-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>{geo === 'denied' ? 'Location unavailable — you can still type the location above.' : 'We’ll pin exactly where this happened. Allow location when asked.'}</p>
          )}
        </div>
        <label className="block"><Label>Describe what happened in detail</Label><textarea rows={6} className={field} style={fStyle} value={ac.detail || ''} onChange={(e) => setD('accident', { detail: e.target.value })} placeholder="Road conditions, direction of travel, what each vehicle was doing…" data-testid="ac-detail" /></label>
      </div>
    );
  } else if (step === 3) {
    body = (
      <div className="space-y-5" data-testid="step-photos">
        <StepHead title="Photos & sketch" sub="Take photos now if you safely can — you can also add a sketch later." />
        <PhotoTile label="Damage to your vehicle" ids={photos.vehicle_damage} onAdd={(f) => uploadPhoto('vehicle_damage', f)} onRemove={(id) => removePhoto('vehicle_damage', id)} jwt={jwt} busy={photoBusy} testId="photo-vehicle-damage" />
        <PhotoTile label="The scene / road layout" ids={photos.scene} onAdd={(f) => uploadPhoto('scene', f)} onRemove={(id) => removePhoto('scene', id)} jwt={jwt} busy={photoBusy} testId="photo-scene" />
        <PhotoTile label="Other vehicle(s)" ids={photos.other_vehicle} onAdd={(f) => uploadPhoto('other_vehicle', f)} onRemove={(id) => removePhoto('other_vehicle', id)} jwt={jwt} busy={photoBusy} testId="photo-other-vehicle" />
        <div className="rounded-xl border p-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
          <PhotoTile label="Sketch of the accident (photo of a hand-drawn sketch)" ids={photos.sketch} onAdd={(f) => uploadPhoto('sketch', f)} onRemove={(id) => removePhoto('sketch', id)} jwt={jwt} busy={photoBusy} testId="photo-sketch" />
          <p className="text-xs mt-2" style={{ color: 'var(--theme-text-muted)' }}>No need to do this now if you can't — your draft is saved and you can come back to add it later.</p>
          <label className="block mt-2"><Label>Sketch note (optional)</Label><input className={field} style={fStyle} value={(data.accident || {}).sketch_note || ''} onChange={(e) => setD('accident', { sketch_note: e.target.value })} data-testid="sketch-note" /></label>
        </div>
      </div>
    );
  } else if (step === 4) {
    const list = data.third_parties || [];
    const setTP = (i, patch) => setData((d) => ({ ...d, third_parties: (d.third_parties || []).map((t, idx) => idx === i ? { ...t, ...patch } : t) }));
    body = (
      <div className="space-y-4" data-testid="step-third-parties">
        <StepHead title="Other drivers involved" sub="Add anyone else involved. Leave blank if no one else was." />
        {list.map((tp, i) => (
          <div key={i} className="rounded-2xl border p-4 space-y-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid={`third-party-${i}`}>
            <div className="flex items-center justify-between"><span className="font-bold" style={{ color: 'var(--theme-text)' }}>Driver {i + 1}</span><button onClick={() => setData((d) => ({ ...d, third_parties: d.third_parties.filter((_, x) => x !== i) }))} className="text-rose-500" data-testid={`remove-third-party-${i}`}><Trash2 size={16} /></button></div>
            {[['name', 'Name'], ['phone', 'Phone'], ['address', 'Address'], ['insurer', 'Insurer / policy number'], ['vehicle', 'Vehicle make / model'], ['reg', 'Reg number'], ['passengers', 'Number of passengers'], ['damage', 'Extent of damage'], ['injuries', 'Injuries to driver / passengers']].map(([k, l]) => (
              <label className="block" key={k}><Label>{l}</Label><input className={field} style={fStyle} value={tp[k] || ''} onChange={(e) => setTP(i, { [k]: e.target.value })} data-testid={`tp-${i}-${k}`} /></label>
            ))}
          </div>
        ))}
        <button onClick={() => setData((d) => ({ ...d, third_parties: [...(d.third_parties || []), {}] }))} data-testid="add-third-party-btn"
          className="w-full inline-flex items-center justify-center gap-2 rounded-xl border-2 border-dashed py-3 font-semibold" style={{ borderColor: CORE, color: CORE }}><Plus size={18} /> Add another driver</button>
      </div>
    );
  } else if (step === 5) {
    const list = data.witnesses || [];
    const setW = (i, patch) => setData((d) => ({ ...d, witnesses: (d.witnesses || []).map((t, idx) => idx === i ? { ...t, ...patch } : t) }));
    body = (
      <div className="space-y-4" data-testid="step-witnesses">
        <StepHead title="Witnesses" sub="Anyone who saw what happened. Optional." />
        {list.map((w, i) => (
          <div key={i} className="rounded-2xl border p-4 space-y-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid={`witness-${i}`}>
            <div className="flex items-center justify-between"><span className="font-bold" style={{ color: 'var(--theme-text)' }}>Witness {i + 1}</span><button onClick={() => setData((d) => ({ ...d, witnesses: d.witnesses.filter((_, x) => x !== i) }))} className="text-rose-500" data-testid={`remove-witness-${i}`}><Trash2 size={16} /></button></div>
            {[['name', 'Name'], ['phone', 'Phone'], ['note', 'Passenger / bystander (optional)']].map(([k, l]) => (
              <label className="block" key={k}><Label>{l}</Label><input className={field} style={fStyle} value={w[k] || ''} onChange={(e) => setW(i, { [k]: e.target.value })} data-testid={`w-${i}-${k}`} /></label>
            ))}
          </div>
        ))}
        <button onClick={() => setData((d) => ({ ...d, witnesses: [...(d.witnesses || []), {}] }))} data-testid="add-witness-btn"
          className="w-full inline-flex items-center justify-center gap-2 rounded-xl border-2 border-dashed py-3 font-semibold" style={{ borderColor: CORE, color: CORE }}><Plus size={18} /> Add a witness</button>
      </div>
    );
  } else if (step === 6) {
    const po = data.police || {};
    body = (
      <div className="space-y-4" data-testid="step-police">
        <StepHead title="Police details" sub="Only if the police attended." />
        <div><Label>Did the police attend?</Label><YesNo value={po.attended} onChange={(v) => setD('police', { attended: v })} testId="police-attended" /></div>
        {[['crime_ref', 'Police crime / incident reference'], ['officer_name', 'Officer name'], ['collar_number', 'Officer collar number'], ['station', 'Police station / constabulary']].map(([k, l]) => (
          <label className="block" key={k}><Label>{l}</Label><input className={field} style={fStyle} value={po[k] || ''} onChange={(e) => setD('police', { [k]: e.target.value })} data-testid={`police-${k}`} /></label>
        ))}
        <div className="rounded-xl border p-3 text-sm flex items-start gap-2" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}><ShieldAlert size={16} className="text-amber-500 shrink-0 mt-0.5" /> If the police request documents, tell them you'll present them at the nearest Police Station.</div>
      </div>
    );
  } else {
    body = (
      <div className="space-y-4" data-testid="step-review-submit">
        <StepHead title="Review & submit" sub="Quick check, then send it to your manager." />
        <ReviewRow label="Vehicle" value={`${yd.reg_number || ''} ${yd.make_model || ''}`} />
        <ReviewRow label="Accident" value={`${ac.date || ''} ${ac.time || ''} — ${(ac.detail || '').slice(0, 80)}`} />
        <ReviewRow label="Photos" value={`${Object.values(photos).reduce((n, a) => n + (a?.length || 0), 0)} attached`} />
        <ReviewRow label="Other drivers" value={`${(data.third_parties || []).length}`} />
        <ReviewRow label="Witnesses" value={`${(data.witnesses || []).length}`} />
        <label className="flex items-start gap-3 rounded-xl border p-3 cursor-pointer" style={{ borderColor: 'var(--theme-border)' }} data-testid="crash-declaration">
          <input type="checkbox" checked={declared} onChange={(e) => setDeclared(e.target.checked)} className="mt-1 h-5 w-5 accent-cyan-500" data-testid="crash-declaration-check" />
          <span className="text-sm" style={{ color: 'var(--theme-text)' }}>I confirm the information above is true and accurate to the best of my knowledge.</span>
        </label>
        <div className="rounded-xl border p-3 text-xs" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>After you submit, we'll show you the insurance claim line and policy number to call.</div>
      </div>
    );
  }
  return shell(body);
}

const StepHead = ({ title, sub }) => (
  <div><h2 className="text-2xl font-extrabold tracking-tight" style={{ color: 'var(--theme-text)' }}>{title}</h2><p className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>{sub}</p></div>
);
const ReviewRow = ({ label, value }) => (
  <div className="flex items-center justify-between gap-3 rounded-xl border px-3.5 py-3" style={{ borderColor: 'var(--theme-border)' }}>
    <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)' }}>{label}</span>
    <span className="text-sm text-right truncate max-w-[60%]" style={{ color: 'var(--theme-text)' }}>{value || '—'}</span>
  </div>
);

function InsuranceBlock({ ins }) {
  const copy = (t) => navigator.clipboard?.writeText(t);
  const call = (p) => (p || '').replace(/\s/g, '');
  return (
    <div className="max-w-md mx-auto space-y-3 text-left" data-testid="crash-insurance-block">
      <a href={`tel:${call(ins.qbe_claim_line)}`} data-testid="emergency-qbe-call-btn" className="flex items-center justify-between rounded-2xl border-2 p-4" style={{ background: '#ECFDF5', borderColor: '#6EE7B7' }}>
        <div><div className="text-xs font-bold uppercase text-emerald-700">QBE 24h claim line</div><div className="text-xl font-extrabold font-mono text-emerald-900">{ins.qbe_claim_line}</div><div className="text-[11px] text-emerald-700 mt-0.5">{ins.qbe_claim_note}</div></div>
        <Phone className="text-emerald-600 shrink-0" size={24} />
      </a>
      <a href={`tel:${call(ins.broker_phone)}`} data-testid="emergency-circle-call-btn" className="flex items-center justify-between rounded-2xl border-2 p-4" style={{ background: '#ECFDF5', borderColor: '#6EE7B7' }}>
        <div><div className="text-xs font-bold uppercase text-emerald-700">{ins.broker_name}</div><div className="text-xl font-extrabold font-mono text-emerald-900">{ins.broker_phone}</div><div className="text-[11px] text-emerald-700 mt-0.5">{ins.broker_note}</div></div>
        <Phone className="text-emerald-600 shrink-0" size={24} />
      </a>
      <button onClick={() => copy(ins.qbe_policy_number)} className="w-full flex items-center justify-between rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="crash-policy-copy">
        <div><div className="text-xs font-bold uppercase" style={{ color: 'var(--theme-text-muted)' }}>QBE policy number</div><div className="text-lg font-extrabold font-mono" style={{ color: 'var(--theme-text)' }}>{ins.qbe_policy_number}</div></div>
        <Copy size={18} style={{ color: 'var(--theme-text-muted)' }} />
      </button>
    </div>
  );
}
