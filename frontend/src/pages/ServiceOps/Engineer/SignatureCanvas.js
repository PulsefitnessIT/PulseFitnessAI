/**
 * SignatureCanvas — iter 215dp.
 *
 * Touch / mouse signature capture. Renders to a 600x200 canvas and
 * returns a base64 PNG via `onSubmit(dataUrl)`.
 */
import React, { useEffect, useRef, useState } from 'react';
import { X, RotateCcw, Check } from 'lucide-react';

export default function SignatureCanvas({ onSubmit, onCancel }) {
  const canvasRef = useRef(null);
  const [drawing, setDrawing] = useState(false);
  const [hasInk, setHasInk] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.lineWidth = 2.4;
    ctx.strokeStyle = '#0f172a';
  }, []);

  const point = (e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    if (e.touches && e.touches[0]) {
      return { x: e.touches[0].clientX - rect.left, y: e.touches[0].clientY - rect.top };
    }
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const start = (e) => {
    e.preventDefault();
    const ctx = canvasRef.current.getContext('2d');
    const p = point(e);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    setDrawing(true);
  };
  const move = (e) => {
    if (!drawing) return;
    e.preventDefault();
    const ctx = canvasRef.current.getContext('2d');
    const p = point(e);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    setHasInk(true);
  };
  const stop = () => setDrawing(false);

  const clear = () => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    setHasInk(false);
  };

  const submit = () => {
    if (!hasInk) return;
    const dataUrl = canvasRef.current.toDataURL('image/png');
    onSubmit?.(dataUrl);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center" style={{ background: 'rgba(0,0,0,0.6)' }} data-testid="signature-overlay">
      <div className="w-full sm:max-w-lg bg-white rounded-t-2xl sm:rounded-2xl p-4 space-y-3" data-testid="signature-modal">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-extrabold">Customer signature</h3>
          <button type="button" onClick={onCancel} aria-label="Close" data-testid="signature-cancel" className="p-1 rounded hover:bg-black/10"><X size={16} /></button>
        </div>
        <p className="text-xs opacity-70">Please ask the customer to sign in the area below to confirm the work is complete.</p>
        <div className="rounded-xl border-2 border-dashed" style={{ borderColor: '#cbd5e1', height: 220 }}>
          <canvas
            ref={canvasRef}
            className="w-full h-full touch-none rounded-xl"
            style={{ background: '#f8fafc' }}
            onMouseDown={start}
            onMouseMove={move}
            onMouseUp={stop}
            onMouseLeave={stop}
            onTouchStart={start}
            onTouchMove={move}
            onTouchEnd={stop}
            data-testid="signature-canvas"
          />
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={clear} className="flex-1 px-3 py-2 rounded-lg border text-sm font-bold inline-flex items-center justify-center gap-1.5" style={{ borderColor: '#cbd5e1' }} data-testid="signature-clear">
            <RotateCcw size={14} /> Clear
          </button>
          <button type="button" onClick={submit} disabled={!hasInk} className="flex-1 px-3 py-2 rounded-lg text-sm font-bold text-white inline-flex items-center justify-center gap-1.5 disabled:opacity-50" style={{ background: '#10b981' }} data-testid="signature-submit">
            <Check size={14} /> Capture
          </button>
        </div>
      </div>
    </div>
  );
}
