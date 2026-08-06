/**
 * EquipmentScanModal — factory-barcode scanner for gym staff (Operations → Equipment).
 *
 * Phones auto-open the app from a QR code, but the linear factory barcodes
 * (serial e.g. 17150704760 / model e.g. 510H-AAA) can't do that. This modal
 * lets staff point the camera at either barcode, decodes it, resolves it to a
 * machine via GET /api/equipment/scan/resolve, then drops them onto the SAME
 * options page the QR opens (/scan/{id}: Check / Log Fault / Photo).
 *
 * Serial → one machine. Model code → one (if a site is set) or a chooser.
 * Falls back to manual entry on browsers without BarcodeDetector (iOS Safari).
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Camera, Loader2, X, Search, AlertTriangle } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

function hasBarcodeDetector() {
  return typeof window !== 'undefined' && 'BarcodeDetector' in window;
}

export default function EquipmentScanModal({ open, onClose, siteId }) {
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const detectorRef = useRef(null);
  const rafRef = useRef(null);
  const [manualMode, setManualMode] = useState(!hasBarcodeDetector());
  const [manualValue, setManualValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [options, setOptions] = useState([]);

  const stopCamera = () => {
    if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
    if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
  };

  const handleClose = () => {
    stopCamera();
    setError(''); setOptions([]); setManualValue('');
    onClose?.();
  };

  const goToMachine = (id) => {
    stopCamera();
    handleClose();
    navigate(`/scan/${id}`);
  };

  const lookup = async (raw) => {
    let code = (raw || '').trim();
    if (!code) return;
    // A scanned Pulse QR is a full /scan/{id} URL — jump straight in.
    const urlMatch = /\/scan\/([^/?#]+)/.exec(code);
    if (urlMatch) { goToMachine(decodeURIComponent(urlMatch[1])); return; }
    setBusy(true); setError(''); setOptions([]);
    try {
      const r = await axios.get(
        `${API}/equipment/scan/resolve`,
        { ...auth(), params: { code, site_id: siteId || undefined } },
      );
      if (r.data?.match === 'multiple') {
        setOptions(r.data.options || []);
      } else if (r.data?.equipment?.id) {
        goToMachine(r.data.equipment.id);
      } else {
        setError('No match for this barcode.');
      }
    } catch (e) {
      const status = e?.response?.status;
      if (status === 404) setError(`No machine matched "${code}". Try the other barcode, or type the serial number.`);
      else setError(e?.response?.data?.detail || e?.message || 'Lookup failed.');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!open || manualMode || !hasBarcodeDetector()) return;
    let cancelled = false;
    (async () => {
      try {
        // eslint-disable-next-line no-undef
        detectorRef.current = new BarcodeDetector({
          formats: ['qr_code', 'code_128', 'code_39', 'ean_13', 'ean_8', 'upc_a', 'upc_e', 'itf', 'codabar'],
        });
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } }, audio: false,
        });
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play(); }
        const tick = async () => {
          if (cancelled || !videoRef.current) return;
          try {
            const found = await detectorRef.current.detect(videoRef.current);
            if (found?.length && found[0].rawValue) { stopCamera(); lookup(found[0].rawValue); return; }
          } catch (_e) { /* ignore per-frame errors */ }
          rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
      } catch (e) {
        setManualMode(true);
        setError('Camera unavailable — type the serial number instead.');
      }
    })();
    return () => { cancelled = true; stopCamera(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, manualMode]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[90] bg-slate-900/70 flex items-end sm:items-center justify-center"
      data-testid="equipment-scan-modal"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md bg-white rounded-t-3xl sm:rounded-3xl shadow-xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100">
          <Camera size={16} className="text-cyan-600" />
          <p className="text-sm font-bold text-slate-900 flex-1">Scan machine barcode</p>
          <button
            type="button"
            onClick={handleClose}
            className="w-8 h-8 rounded-full hover:bg-slate-100 flex items-center justify-center text-slate-500"
            data-testid="equipment-scan-close"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {!manualMode ? (
            <div className="relative aspect-video bg-slate-900 rounded-2xl overflow-hidden">
              <video ref={videoRef} playsInline muted className="absolute inset-0 w-full h-full object-cover" data-testid="equipment-scan-video" />
              <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                <div className="w-3/4 h-16 border-2 border-white/70 rounded-xl shadow-[0_0_0_2000px_rgba(0,0,0,0.35)]" />
              </div>
              <p className="absolute bottom-2 inset-x-2 text-center text-[11px] font-bold uppercase tracking-wide text-white/90">
                Point at the barcode on the machine
              </p>
            </div>
          ) : (
            <div className="space-y-2" data-testid="equipment-scan-manual">
              <p className="text-xs text-slate-600">Type the serial number printed under the barcode.</p>
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    value={manualValue}
                    onChange={(e) => setManualValue(e.target.value)}
                    placeholder="e.g. 17150704760"
                    className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    data-testid="equipment-scan-manual-input"
                    onKeyDown={(e) => { if (e.key === 'Enter' && manualValue.trim()) lookup(manualValue.trim()); }}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => manualValue.trim() && lookup(manualValue.trim())}
                  disabled={busy || !manualValue.trim()}
                  className="px-3 py-2 rounded-xl bg-cyan-600 text-white text-xs font-bold disabled:opacity-50"
                  data-testid="equipment-scan-manual-submit"
                >
                  {busy ? <Loader2 size={12} className="animate-spin" /> : 'Look up'}
                </button>
              </div>
            </div>
          )}

          {busy && !manualMode && (
            <p className="text-xs text-cyan-700 flex items-center gap-2" data-testid="equipment-scan-busy"><Loader2 size={12} className="animate-spin" /> Looking up machine…</p>
          )}

          {error && (
            <div className="p-2 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800 flex items-start gap-2" data-testid="equipment-scan-error">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {options.length > 0 && (
            <div className="space-y-1" data-testid="equipment-scan-options">
              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Multiple machines — pick one</p>
              {options.map((eq) => (
                <button
                  key={eq.id}
                  type="button"
                  onClick={() => goToMachine(eq.id)}
                  className="w-full text-left px-3 py-2 rounded-xl border border-slate-200 hover:bg-slate-50"
                  data-testid={`equipment-scan-option-${eq.id}`}
                >
                  <p className="text-sm font-bold text-slate-900">{eq.name || 'Unnamed'}</p>
                  <p className="text-[11px] text-slate-500">
                    {eq.serial_number || eq.asset_tag || ''}
                    {eq.model ? ` · ${eq.model}` : ''}
                    {eq.location ? ` · ${eq.location}` : ''}
                  </p>
                </button>
              ))}
            </div>
          )}

          {!manualMode && hasBarcodeDetector() && (
            <button
              type="button"
              onClick={() => { stopCamera(); setManualMode(true); }}
              className="text-[11px] font-bold uppercase tracking-wide text-slate-500 hover:text-slate-700"
              data-testid="equipment-scan-switch-manual"
            >
              Or type the serial number instead
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
