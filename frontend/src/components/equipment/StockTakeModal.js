/**
 * StockTakeModal — bulk equipment audit by rapid barcode scanning.
 *
 * Staff pick a Zone (or All), then the camera stays open and ticks off each
 * machine as its barcode is scanned (beep + vibrate + running "X of Y"), no
 * re-opening between machines. On finish the report (found / missing /
 * unexpected) is saved so managers can review it later.
 *
 * Matching is on-device against the site's loaded equipment for zero lag.
 */
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Camera, Loader2, X, CheckCircle, AlertTriangle, Search, ClipboardList } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });
const hasDetector = () => typeof window !== 'undefined' && 'BarcodeDetector' in window;
const norm = (s) => (s == null ? '' : String(s)).trim().toLowerCase();

function feedback() {
  try { navigator.vibrate?.(60); } catch (_e) { /* noop */ }
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ac = new Ctx();
    const o = ac.createOscillator();
    const g = ac.createGain();
    o.connect(g); g.connect(ac.destination);
    o.frequency.value = 880; g.gain.value = 0.08;
    o.start(); o.stop(ac.currentTime + 0.09);
    setTimeout(() => ac.close?.(), 200);
  } catch (_e) { /* noop */ }
}

export default function StockTakeModal({ open, onClose, equipment, locations, siteId, onSaved }) {
  const [step, setStep] = useState('setup'); // setup | scanning | done
  const [location, setLocation] = useState('all');
  const [manualMode, setManualMode] = useState(!hasDetector());
  const [manualValue, setManualValue] = useState('');
  const [foundIds, setFoundIds] = useState([]);
  const [unexpected, setUnexpected] = useState([]);
  const [toast, setToast] = useState(null);
  const [saving, setSaving] = useState(false);
  const [report, setReport] = useState(null);

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const detectorRef = useRef(null);
  const rafRef = useRef(null);
  const seenRef = useRef({}); // code -> last ts (debounce)
  const startTsRef = useRef(0);
  const foundRef = useRef([]);
  useEffect(() => { foundRef.current = foundIds; }, [foundIds]);

  const expected = (equipment || []).filter((e) => location === 'all' || norm(e.location) === norm(location));
  const expectedIdSet = new Set(expected.map((e) => e.id));

  const stopCamera = () => {
    if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
    if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
  };

  const reset = () => {
    stopCamera();
    setStep('setup'); setLocation('all'); setFoundIds([]); setUnexpected([]);
    setToast(null); setReport(null); setManualValue(''); seenRef.current = {};
  };

  const handleClose = () => { reset(); onClose?.(); };

  const flash = (kind, text) => {
    setToast({ kind, text });
    setTimeout(() => setToast((t) => (t && t.text === text ? null : t)), 1600);
  };

  // Process one decoded value (from camera or manual entry).
  const process = (raw) => {
    let code = (raw || '').trim();
    if (!code) return;
    const urlMatch = /\/scan\/([^/?#]+)/.exec(code);
    if (urlMatch) code = decodeURIComponent(urlMatch[1]);
    const c = norm(code);
    // exact unique identifier across the whole site list
    const all = equipment || [];
    let machine = all.find((e) => [e.serial_number, e.asset_tag, e.id, e.barcode, e.sticker_code].some((v) => norm(v) === c));
    if (!machine) {
      const modelHits = all.filter((e) => norm(e.model) === c || norm(e.model_code) === c);
      if (modelHits.length === 1) machine = modelHits[0];
      else if (modelHits.length > 1) {
        // ambiguous model — tick the single expected+unfound one if that's unique
        const cand = modelHits.filter((e) => expectedIdSet.has(e.id) && !foundRef.current.includes(e.id));
        if (cand.length === 1) machine = cand[0];
        else { flash('warn', 'Model scanned — scan the serial barcode'); return; }
      }
    }
    if (!machine) {
      setUnexpected((u) => (u.some((x) => x.code === code) ? u : [...u, { code, reason: 'unknown' }]));
      flash('warn', `Unknown: ${code}`);
      return;
    }
    if (!expectedIdSet.has(machine.id)) {
      setUnexpected((u) => (u.some((x) => x.id === machine.id) ? u : [...u, { code, id: machine.id, name: machine.name, reason: 'different zone' }]));
      flash('warn', `${machine.name || machine.serial_number} — different zone`);
      return;
    }
    if (foundRef.current.includes(machine.id)) { flash('dup', 'Already scanned'); return; }
    setFoundIds((f) => [...f, machine.id]);
    feedback();
    flash('ok', `✓ ${machine.name || machine.serial_number}`);
  };

  // Continuous camera loop while scanning.
  useEffect(() => {
    if (step !== 'scanning' || manualMode || !hasDetector()) return;
    let cancelled = false;
    (async () => {
      try {
        // eslint-disable-next-line no-undef
        detectorRef.current = new BarcodeDetector({ formats: ['qr_code', 'code_128', 'code_39', 'ean_13', 'ean_8', 'upc_a', 'upc_e', 'itf', 'codabar'] });
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play(); }
        const tick = async () => {
          if (cancelled || !videoRef.current) return;
          try {
            const found = await detectorRef.current.detect(videoRef.current);
            if (found?.length && found[0].rawValue) {
              const val = found[0].rawValue;
              const now = Date.now();
              if (!seenRef.current[val] || now - seenRef.current[val] > 2500) {
                seenRef.current[val] = now;
                process(val);
              }
            }
          } catch (_e) { /* ignore per-frame errors */ }
          rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
      } catch (e) {
        setManualMode(true);
      }
    })();
    return () => { cancelled = true; stopCamera(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, manualMode]);

  const startScanning = () => { startTsRef.current = Date.now(); setStep('scanning'); };

  const finish = async () => {
    stopCamera();
    setSaving(true);
    try {
      const payload = {
        site_id: siteId || undefined,
        location: location === 'all' ? 'All' : location,
        found: foundIds.map((id) => ({ id })),
        unexpected,
        duration_seconds: startTsRef.current ? Math.round((Date.now() - startTsRef.current) / 1000) : 0,
      };
      const r = await axios.post(`${API}/equipment/stocktakes`, payload, auth());
      setReport(r.data);
      setStep('done');
      onSaved?.();
    } catch (e) {
      flash('warn', e.response?.data?.detail || 'Save failed');
    }
    setSaving(false);
  };

  if (!open) return null;

  const remaining = expected.filter((e) => !foundIds.includes(e.id));

  return (
    <div className="fixed inset-0 z-[90] bg-slate-900/70 flex items-end sm:items-center justify-center" data-testid="stocktake-modal" role="dialog" aria-modal="true">
      <div className="w-full max-w-md bg-white rounded-t-3xl sm:rounded-3xl shadow-xl overflow-hidden max-h-[92vh] flex flex-col">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100 shrink-0">
          <ClipboardList size={16} className="text-cyan-600" />
          <p className="text-sm font-bold text-slate-900 flex-1">Stock-take{step !== 'setup' ? ` · ${location === 'all' ? 'All equipment' : location}` : ''}</p>
          <button type="button" onClick={handleClose} className="w-8 h-8 rounded-full hover:bg-slate-100 flex items-center justify-center text-slate-500" data-testid="stocktake-close" aria-label="Close"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-3 overflow-y-auto">
          {step === 'setup' && (
            <div className="space-y-3" data-testid="stocktake-setup">
              <p className="text-xs text-slate-600">Pick a zone to audit, then rapid-scan every machine's barcode. We'll tick them off and flag anything missing.</p>
              <label className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Zone / location</label>
              <select value={location} onChange={(e) => setLocation(e.target.value)} className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" data-testid="stocktake-location">
                <option value="all">All equipment</option>
                {(locations || []).map((l) => <option key={l} value={l}>{l}</option>)}
              </select>
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 text-sm text-slate-700" data-testid="stocktake-expected-count">
                <span className="font-bold text-slate-900">{expected.length}</span> machine{expected.length === 1 ? '' : 's'} to find in {location === 'all' ? 'this site' : location}.
              </div>
              <button type="button" onClick={startScanning} disabled={expected.length === 0} className="w-full py-3 rounded-xl bg-cyan-600 hover:bg-cyan-700 text-white text-sm font-bold disabled:opacity-50 flex items-center justify-center gap-2" data-testid="stocktake-start">
                <Camera size={16} /> Start scanning
              </button>
            </div>
          )}

          {step === 'scanning' && (
            <div className="space-y-3" data-testid="stocktake-scanning">
              {!manualMode ? (
                <div className="relative aspect-video bg-slate-900 rounded-2xl overflow-hidden">
                  <video ref={videoRef} playsInline muted className="absolute inset-0 w-full h-full object-cover" data-testid="stocktake-video" />
                  <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                    <div className="w-3/4 h-14 border-2 border-white/70 rounded-xl" />
                  </div>
                  {toast && (
                    <div className={`absolute bottom-2 inset-x-2 text-center text-xs font-bold py-1.5 rounded-lg ${toast.kind === 'ok' ? 'bg-green-600 text-white' : toast.kind === 'dup' ? 'bg-slate-700 text-white' : 'bg-amber-500 text-white'}`} data-testid="stocktake-toast">{toast.text}</div>
                  )}
                </div>
              ) : (
                <div className="space-y-2" data-testid="stocktake-manual">
                  <p className="text-xs text-slate-600">Camera unavailable — type each serial and press Enter.</p>
                  <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                      <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input value={manualValue} onChange={(e) => setManualValue(e.target.value)} placeholder="Serial number" className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-sm" data-testid="stocktake-manual-input"
                        onKeyDown={(e) => { if (e.key === 'Enter' && manualValue.trim()) { process(manualValue.trim()); setManualValue(''); } }} />
                    </div>
                    <button type="button" onClick={() => { if (manualValue.trim()) { process(manualValue.trim()); setManualValue(''); } }} className="px-3 py-2 rounded-xl bg-cyan-600 text-white text-xs font-bold" data-testid="stocktake-manual-add">Add</button>
                  </div>
                  {toast && <div className={`text-xs font-bold ${toast.kind === 'ok' ? 'text-green-600' : toast.kind === 'dup' ? 'text-slate-500' : 'text-amber-600'}`}>{toast.text}</div>}
                </div>
              )}

              {/* Live progress */}
              <div>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="font-bold text-slate-900" data-testid="stocktake-progress">{foundIds.length} of {expected.length} found</span>
                  {unexpected.length > 0 && <span className="text-amber-600 text-xs font-bold" data-testid="stocktake-unexpected-count">{unexpected.length} unexpected</span>}
                </div>
                <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-cyan-500 transition-all" style={{ width: `${expected.length ? (foundIds.length / expected.length) * 100 : 0}%` }} />
                </div>
              </div>

              {remaining.length > 0 && (
                <div data-testid="stocktake-remaining">
                  <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400 mb-1">Still to find ({remaining.length})</p>
                  <div className="space-y-1 max-h-32 overflow-y-auto">
                    {remaining.slice(0, 40).map((e) => (
                      <div key={e.id} className="text-xs text-slate-600 flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-slate-300" />{e.name || e.serial_number} <span className="text-slate-400">· {e.serial_number}</span></div>
                    ))}
                  </div>
                </div>
              )}

              <button type="button" onClick={finish} disabled={saving} className="w-full py-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-sm font-bold disabled:opacity-50 flex items-center justify-center gap-2" data-testid="stocktake-finish">
                {saving ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />} Finish &amp; save report
              </button>
            </div>
          )}

          {step === 'done' && report && (
            <div className="space-y-3" data-testid="stocktake-done">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-2 rounded-xl bg-green-50 border border-green-100"><p className="text-lg font-bold text-green-700" data-testid="stocktake-found-count">{report.found_count}</p><p className="text-[10px] uppercase text-green-700/70">Found</p></div>
                <div className="p-2 rounded-xl bg-red-50 border border-red-100"><p className="text-lg font-bold text-red-700" data-testid="stocktake-missing-count">{report.missing_count}</p><p className="text-[10px] uppercase text-red-700/70">Missing</p></div>
                <div className="p-2 rounded-xl bg-amber-50 border border-amber-100"><p className="text-lg font-bold text-amber-700">{report.unexpected_count}</p><p className="text-[10px] uppercase text-amber-700/70">Unexpected</p></div>
              </div>
              {report.missing?.length > 0 && (
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wide text-red-600 mb-1 flex items-center gap-1"><AlertTriangle size={11} /> Missing — not scanned</p>
                  <div className="space-y-1 max-h-40 overflow-y-auto" data-testid="stocktake-missing-list">
                    {report.missing.map((e) => <div key={e.id} className="text-xs text-slate-700">{e.name || e.serial_number} <span className="text-slate-400">· {e.serial_number}{e.location ? ` · ${e.location}` : ''}</span></div>)}
                  </div>
                </div>
              )}
              {report.unexpected?.length > 0 && (
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wide text-amber-600 mb-1">Unexpected scans</p>
                  <div className="space-y-1 max-h-28 overflow-y-auto">
                    {report.unexpected.map((u, i) => <div key={i} className="text-xs text-slate-700">{u.name || u.code} <span className="text-slate-400">· {u.reason}</span></div>)}
                  </div>
                </div>
              )}
              <button type="button" onClick={handleClose} className="w-full py-3 rounded-xl bg-cyan-600 text-white text-sm font-bold" data-testid="stocktake-done-close">Done</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
