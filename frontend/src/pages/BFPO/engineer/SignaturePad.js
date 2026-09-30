import React, { useRef, useState, useEffect } from 'react';
import { Btn } from '../ui';
import { Eraser } from 'lucide-react';

export default function SignaturePad({ onChange }) {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const ratio = window.devicePixelRatio || 1;
    c.width = c.offsetWidth * ratio;
    c.height = c.offsetHeight * ratio;
    const ctx = c.getContext('2d');
    ctx.scale(ratio, ratio);
    ctx.lineWidth = 2.5; ctx.lineCap = 'round'; ctx.strokeStyle = '#0f172a';
  }, []);

  const pos = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return { x: t.clientX - rect.left, y: t.clientY - rect.top };
  };
  const start = (e) => { e.preventDefault(); drawing.current = true; const p = pos(e); const ctx = canvasRef.current.getContext('2d'); ctx.beginPath(); ctx.moveTo(p.x, p.y); };
  const move = (e) => { if (!drawing.current) return; e.preventDefault(); const p = pos(e); const ctx = canvasRef.current.getContext('2d'); ctx.lineTo(p.x, p.y); ctx.stroke(); if (!dirty) setDirty(true); };
  const end = () => { if (!drawing.current) return; drawing.current = false; if (onChange) onChange(canvasRef.current.toDataURL('image/png')); };
  const clear = () => { const c = canvasRef.current; c.getContext('2d').clearRect(0, 0, c.width, c.height); setDirty(false); if (onChange) onChange(''); };

  return (
    <div>
      <canvas ref={canvasRef} data-testid="signature-pad"
        className="w-full h-40 border-2 border-dashed border-slate-300 rounded-xl bg-slate-50 touch-none"
        onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
        onTouchStart={start} onTouchMove={move} onTouchEnd={end} />
      <div className="flex justify-between items-center mt-1">
        <span className="text-xs text-slate-400">{dirty ? 'Signature captured' : 'Sign above'}</span>
        <button onClick={clear} className="text-xs text-slate-500 flex items-center gap-1" data-testid="signature-clear"><Eraser className="w-3 h-3" /> Clear</button>
      </div>
    </div>
  );
}
