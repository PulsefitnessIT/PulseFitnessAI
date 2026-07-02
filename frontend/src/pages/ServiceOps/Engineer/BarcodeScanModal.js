/**
 * BarcodeScanModal — Iter 220da.
 *
 * Field engineers stick QR/barcode labels on every machine. This
 * modal lets them point a phone camera at the sticker and jump
 * straight to the matched equipment row.
 *
 * Detection strategy:
 *   1. Prefer the native ``BarcodeDetector`` API (Chromium on
 *      Android + macOS). Zero-dep, ~5ms / frame.
 *   2. Fall back to a manual text input on browsers that don't
 *      expose it (iOS Safari, Firefox).
 *
 * On a successful decode we call
 * ``GET /svc/engineer/equipment/by-code/{code}`` and:
 *   * ``match=exact`` → close + call ``onMatch(equipment)``.
 *   * ``match=fuzzy`` → close + call ``onMatch(equipment)``.
 *   * ``match=multiple`` → render a 1-tap chooser inline.
 *   * 404 → render a friendly "no match" state with manual retry.
 */
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Camera, Loader2, X, Search, AlertTriangle, Check } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

function hasBarcodeDetector() {
  return typeof window !== 'undefined' && 'BarcodeDetector' in window;
}

export default function BarcodeScanModal({ open, onClose, onMatch, onCode, onMachine }) {
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
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  };

  const handleClose = () => {
    stopCamera();
    setError('');
    setOptions([]);
    setManualValue('');
    onClose?.();
  };

  const lookup = async (code) => {
    // Iter 276 — a scanned Pulse Fitness QR may be a URL that identifies a
    // machine. Route Operations `/scan/{id}` and engineer `/r/eq/{id}`
    // stickers to the machine-history view; `/r/c/{code}` → code lookup.
    if (onMachine) {
      let machineId = null;
      let opsCode = null;
      const ops = /\/scan\/([^/?#]+)/.exec(code) || /\/r\/eq\/([^/?#]+)/.exec(code);
      if (ops) machineId = decodeURIComponent(ops[1]);
      const codeUrl = /\/r\/c\/([^/?#]+)/.exec(code);
      if (codeUrl) opsCode = decodeURIComponent(codeUrl[1]);
      if (machineId) {
        stopCamera();
        onMachine(machineId);
        handleClose();
        return;
      }
      if (opsCode) code = opsCode; // fall through to by-code lookup below
    }
    // Iter 275b — when used to LINK a pre-printed sticker, hand back the
    // raw scanned/typed code instead of resolving an existing machine.
    if (onCode) {
      stopCamera();
      onCode(code);
      handleClose();
      return;
    }
    setBusy(true);
    setError('');
    setOptions([]);
    try {
      const r = await axios.get(
        `${API}/svc/engineer/equipment/by-code/${encodeURIComponent(code)}`,
        auth(),
      );
      if (r.data?.match === 'multiple') {
        setOptions(r.data.options || []);
      } else if (r.data?.equipment) {
        stopCamera();
        notify.success(
          'Match found',
          `${r.data.equipment.name || r.data.equipment.serial_number || 'Equipment'}`,
        );
        onMatch?.(r.data.equipment);
        handleClose();
      } else {
        setError('No match for this code.');
      }
    } catch (e) {
      const status = e?.response?.status;
      if (status === 404) {
        setError(`No equipment matched "${code}".`);
      } else {
        setError(e?.response?.data?.detail || e?.message || 'Lookup failed.');
      }
    } finally {
      setBusy(false);
    }
  };

  // Start the camera + detector loop when the modal opens and the
  // browser supports BarcodeDetector.
  useEffect(() => {
    if (!open || manualMode || !hasBarcodeDetector()) return;
    let cancelled = false;
    (async () => {
      try {
        // eslint-disable-next-line no-undef
        detectorRef.current = new BarcodeDetector({
          formats: ['qr_code', 'code_128', 'code_39', 'ean_13', 'ean_8', 'upc_a', 'upc_e'],
        });
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        const tick = async () => {
          if (cancelled || !videoRef.current) return;
          try {
            const found = await detectorRef.current.detect(videoRef.current);
            if (found?.length) {
              const code = found[0].rawValue;
              if (code) {
                stopCamera();
                lookup(code);
                return;
              }
            }
          } catch (_e) { /* ignore per-frame errors */ }
          rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
      } catch (e) {
        // Camera permission denied, no devices, etc → manual entry.
        setManualMode(true);
        setError('Camera unavailable — type the code instead.');
      }
    })();
    return () => {
      cancelled = true;
      stopCamera();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, manualMode]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/70 flex items-end sm:items-center justify-center"
      data-testid="barcode-scan-modal"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md bg-white rounded-t-3xl sm:rounded-3xl shadow-xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100">
          <Camera size={16} className="text-cyan-600" />
          <p className="text-sm font-bold text-slate-900 flex-1">Scan equipment</p>
          <button
            type="button"
            onClick={handleClose}
            className="w-8 h-8 rounded-full hover:bg-slate-100 flex items-center justify-center text-slate-500"
            data-testid="barcode-scan-close"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {!manualMode ? (
            <div className="relative aspect-video bg-slate-900 rounded-2xl overflow-hidden">
              <video
                ref={videoRef}
                playsInline
                muted
                className="absolute inset-0 w-full h-full object-cover"
                data-testid="barcode-scan-video"
              />
              <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                <div className="w-2/3 aspect-square border-2 border-white/60 rounded-2xl shadow-[0_0_0_2000px_rgba(0,0,0,0.35)]" />
              </div>
              <p className="absolute bottom-2 inset-x-2 text-center text-[11px] font-bold uppercase tracking-wide text-white/90">
                Point at QR or barcode
              </p>
            </div>
          ) : (
            <div className="space-y-2" data-testid="barcode-scan-manual">
              <p className="text-xs text-slate-600">
                Type the serial number or asset tag printed on the machine.
              </p>
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search
                    size={14}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                  />
                  <input
                    type="text"
                    value={manualValue}
                    onChange={(e) => setManualValue(e.target.value)}
                    placeholder="e.g. GA-12345"
                    className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    data-testid="barcode-scan-manual-input"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && manualValue.trim()) lookup(manualValue.trim());
                    }}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => manualValue.trim() && lookup(manualValue.trim())}
                  disabled={busy || !manualValue.trim()}
                  className="px-3 py-2 rounded-xl bg-cyan-600 text-white text-xs font-bold disabled:opacity-50"
                  data-testid="barcode-scan-manual-submit"
                >
                  {busy ? <Loader2 size={12} className="animate-spin" /> : 'Look up'}
                </button>
              </div>
            </div>
          )}

          {error && (
            <div
              className="p-2 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800 flex items-start gap-2"
              data-testid="barcode-scan-error"
            >
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {options.length > 0 && (
            <div className="space-y-1" data-testid="barcode-scan-options">
              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
                Multiple matches — pick one
              </p>
              {options.map((eq) => (
                <button
                  key={eq.id}
                  type="button"
                  onClick={() => {
                    onMatch?.(eq);
                    handleClose();
                  }}
                  className="w-full text-left px-3 py-2 rounded-xl border border-slate-200 hover:bg-slate-50"
                  data-testid={`barcode-scan-option-${eq.id}`}
                >
                  <p className="text-sm font-bold text-slate-900">{eq.name || 'Unnamed'}</p>
                  <p className="text-[11px] text-slate-500">
                    {eq.serial_number || eq.asset_tag || ''}
                    {eq.model ? ` · ${eq.model}` : ''}
                  </p>
                </button>
              ))}
            </div>
          )}

          {!manualMode && hasBarcodeDetector() && (
            <button
              type="button"
              onClick={() => { stopCamera(); setManualMode(true); }}
              className="text-[11px] font-bold uppercase tracking-wide text-slate-500 hover:text-slate-700 inline-flex items-center gap-1"
              data-testid="barcode-scan-switch-manual"
            >
              <Check size={11} /> Or type the code instead
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
