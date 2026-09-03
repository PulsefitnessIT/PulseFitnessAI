import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { X, Search, ScanLine, Camera, MapPin, Check } from 'lucide-react';
import { notify } from '@/components/notifications';
import { StepTitle } from './WizardPrimitives';

export function StepEquipment({ allEquipment, search, setSearch, selectedIds, onToggle, error }) {
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scanError, setScanError] = useState(null);

  const handleScan = useCallback((rawValue) => {
    setScannerOpen(false);
    setScanError(null);
    let scannedId = null;
    const m = /\/scan\/([0-9a-fA-F-]{8,})/.exec(rawValue || '');
    if (m) scannedId = m[1];
    else if (/^[0-9a-fA-F-]{20,}$/.test((rawValue || '').trim())) scannedId = rawValue.trim();
    if (!scannedId) { setScanError('QR did not look like a Pulse equipment tag.'); return; }
    const hit = allEquipment.find((e) => e.id === scannedId);
    if (!hit) { setScanError('Scanned machine is not on this site.'); return; }
    if (!selectedIds.includes(scannedId)) onToggle(scannedId);
    notify.success(`Added — ${hit.name}`);
  }, [allEquipment, onToggle, selectedIds]);

  // Filter, then group by location.
  const groups = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = !q ? allEquipment : allEquipment.filter((e) =>
      (e.name || '').toLowerCase().includes(q) ||
      (e.machine_type || '').toLowerCase().includes(q) ||
      (e.serial_number || '').toLowerCase().includes(q) ||
      (e.location || '').toLowerCase().includes(q));
    const byLoc = {};
    for (const e of filtered) {
      const loc = (e.location || '').trim() || 'Unassigned';
      (byLoc[loc] = byLoc[loc] || []).push(e);
    }
    // Sort: named locations alphabetically, "Unassigned" last.
    return Object.keys(byLoc)
      .sort((a, b) => (a === 'Unassigned' ? 1 : b === 'Unassigned' ? -1 : a.localeCompare(b)))
      .map((loc) => ({ loc, items: byLoc[loc] }));
  }, [allEquipment, search]);

  const multiLocation = groups.filter((g) => g.loc !== 'Unassigned').length > 1
    || (groups.length > 1);
  const totalShown = groups.reduce((n, g) => n + g.items.length, 0);

  return (
    <div data-testid="mod-step-equipment">
      <StepTitle eyebrow="Step 1" title="Which machines?" subtitle="Tick every machine you're reporting — you'll describe each one's fault next." />
      {error && selectedIds.length === 0 && (
        <div className="mb-3 rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-[11px] font-bold text-red-600 dark:text-red-300" data-testid="mod-equipment-error">
          Tick at least one machine to continue.
        </div>
      )}
      {selectedIds.length > 0 && (
        <div className="mb-3 text-xs font-bold" style={{ color: 'var(--color-brand-cyan)' }} data-testid="mod-equipment-selected-count">
          {selectedIds.length} machine{selectedIds.length > 1 ? 's' : ''} selected
        </div>
      )}
      <div className="flex gap-2 mb-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--theme-text-muted)' }} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, type, serial or location"
            className="w-full rounded-lg border pl-9 pr-3 py-2.5 text-sm focus:outline-none focus:border-[var(--color-brand-cyan)]"
            style={{ background: 'var(--theme-surface-2)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="mod-equipment-search"
          />
        </div>
        <button
          type="button"
          onClick={() => { setScanError(null); setScannerOpen(true); }}
          className="flex items-center gap-1.5 rounded-lg border border-[rgb(var(--rgb-brand-cyan)/0.5)] bg-[rgb(var(--rgb-brand-cyan)/0.12)] text-[var(--color-brand-cyan)] px-3 py-2.5 text-sm font-bold hover:bg-[rgb(var(--rgb-brand-cyan)/0.2)]"
          data-testid="mod-equipment-qr-scan"
          title="Scan QR tag"
        >
          <ScanLine size={15} /> Scan
        </button>
      </div>
      {scanError && (
        <div className="mb-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-600 dark:text-amber-300" data-testid="mod-scan-error">
          {scanError}
        </div>
      )}
      {scannerOpen && <QRScanInline onScan={handleScan} onClose={() => setScannerOpen(false)} />}

      {totalShown === 0 ? (
        <div className="text-center py-6 text-sm" style={{ color: 'var(--theme-text-muted)' }}>No equipment matches.</div>
      ) : (
        <div className="max-h-[52vh] overflow-y-auto space-y-4">
          {groups.map((g) => (
            <div key={g.loc} data-testid={`mod-equipment-group-${g.loc.replace(/\s+/g, '-').toLowerCase()}`}>
              {multiLocation && (
                <div className="flex items-center gap-1.5 mb-2 sticky top-0 py-1 z-[1]" style={{ background: 'var(--theme-surface)' }}>
                  <MapPin size={12} style={{ color: 'var(--color-brand-cyan)' }} />
                  <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{g.loc}</span>
                  <span className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>· {g.items.length}</span>
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {g.items.map((e) => {
                  const picked = selectedIds.includes(e.id);
                  const displayName = e.name || e.machine_type || e.serial_number;
                  return (
                    <button
                      key={e.id}
                      type="button"
                      role="checkbox"
                      aria-checked={picked}
                      aria-label={displayName}
                      onClick={() => onToggle(e.id)}
                      className={`text-left rounded-xl border p-3 transition-all flex items-start gap-2.5 ${picked ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.12)]' : 'hover:border-[var(--color-brand-cyan)]'}`}
                      style={picked ? {} : { background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }}
                      data-testid={`mod-equipment-${e.id}`}
                    >
                      <span
                        className={`mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0 ${picked ? 'bg-[var(--color-brand-cyan)] border-[var(--color-brand-cyan)]' : ''}`}
                        style={picked ? {} : { borderColor: 'var(--theme-text-muted)' }}
                      >
                        {picked && <Check size={11} className="text-[#04121a]" strokeWidth={3} />}
                      </span>
                      <span className="min-w-0">
                        <span className="block font-bold text-sm truncate" style={{ color: 'var(--theme-text)' }}>{displayName}</span>
                        <span className="block text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>
                          {[e.machine_type, e.serial_number].filter(Boolean).join(' · ')}
                        </span>
                        {e.status === 'out_of_service' && (
                          <span className="block text-[10px] font-bold text-red-500 dark:text-red-300 mt-1 uppercase tracking-wider">Out of service</span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* In-wizard QR scanner — browser BarcodeDetector. */
function QRScanInline({ onScan, onClose }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const scanningRef = useRef(true);
  const [nativeUnsupported, setNativeUnsupported] = useState(false);
  const [cameraDenied, setCameraDenied] = useState(false);

  const stop = useCallback(() => {
    scanningRef.current = false;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  useEffect(() => {
    let raf;
    const start = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
        });
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        if (!('BarcodeDetector' in window)) { setNativeUnsupported(true); return; }
        const detector = new window.BarcodeDetector({ formats: ['qr_code'] });
        const tick = async () => {
          if (!scanningRef.current || !videoRef.current) return;
          try {
            const codes = await detector.detect(videoRef.current);
            if (codes.length > 0) { stop(); onScan(codes[0].rawValue); return; }
          } catch { /* frame error */ }
          raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      } catch {
        setCameraDenied(true);
      }
    };
    start();
    return () => { cancelAnimationFrame(raf); stop(); };
  }, [onScan, stop]);

  if (cameraDenied) {
    return (
      <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-4 mb-3 text-sm text-red-600 dark:text-red-200" data-testid="mod-scan-camera-denied">
        <Camera size={16} className="inline mr-1.5 -mt-0.5" />
        Camera access required. Enable it in your browser settings and try again.
        <button onClick={() => { stop(); onClose(); }} className="ml-3 underline font-bold">Close</button>
      </div>
    );
  }

  return (
    <div className="relative rounded-xl overflow-hidden border border-[rgb(var(--rgb-brand-cyan)/0.5)] bg-black mb-3" data-testid="mod-qr-scanner">
      <video ref={videoRef} className="w-full" playsInline muted style={{ maxHeight: '42vh', objectFit: 'cover' }} />
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-44 h-44 border-2 border-[var(--color-brand-cyan)] rounded-2xl relative">
          <div className="absolute top-0 left-0 w-6 h-6 border-t-4 border-l-4 border-[var(--color-brand-cyan)] rounded-tl-xl" />
          <div className="absolute top-0 right-0 w-6 h-6 border-t-4 border-r-4 border-[var(--color-brand-cyan)] rounded-tr-xl" />
          <div className="absolute bottom-0 left-0 w-6 h-6 border-b-4 border-l-4 border-[var(--color-brand-cyan)] rounded-bl-xl" />
          <div className="absolute bottom-0 right-0 w-6 h-6 border-b-4 border-r-4 border-[var(--color-brand-cyan)] rounded-br-xl" />
          <div className="absolute left-2 right-2 top-1/2 h-0.5 bg-[rgb(var(--rgb-brand-cyan)/0.6)] animate-pulse" />
        </div>
      </div>
      <div className="absolute top-2 left-0 right-0 text-center">
        <span className="bg-black/70 text-white text-[11px] font-bold px-3 py-1 rounded-full">Point at the machine's QR tag</span>
      </div>
      {nativeUnsupported && (
        <div className="absolute bottom-12 left-0 right-0 text-center">
          <span className="bg-amber-600/90 text-white text-[10px] px-3 py-1 rounded-full">QR detection unavailable — use Chrome / Safari or pick from the list</span>
        </div>
      )}
      <div className="absolute bottom-2 left-0 right-0 text-center">
        <button onClick={() => { stop(); onClose(); }} className="rounded-full bg-black/70 text-white text-xs font-bold px-3 py-1.5 hover:bg-black/80" data-testid="mod-qr-cancel">
          <X size={12} className="inline mr-1 -mt-0.5" /> Cancel
        </button>
      </div>
    </div>
  );
}
