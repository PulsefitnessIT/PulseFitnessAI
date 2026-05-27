/**
 * IncidentSignaturePad — Iter 220t
 *
 * Lightweight HTML5 canvas signature pad. Returns a PNG data URL via
 * `onChange(dataUrl)`. Mobile friendly (touch + pointer events).
 * No external deps.
 */
import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Eraser } from 'lucide-react';

export default function IncidentSignaturePad({ onChange, height = 140, testId = 'incident-signature-pad' }) {
  const canvasRef = useRef(null);
  const drawing = useRef(false);
  const last = useRef({ x: 0, y: 0 });
  const [empty, setEmpty] = useState(true);

  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    // Hi-DPI handling for crisp lines.
    const dpr = window.devicePixelRatio || 1;
    const rect = c.getBoundingClientRect();
    c.width = rect.width * dpr;
    c.height = height * dpr;
    const ctx = c.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#0F172A';
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, rect.width, height);
  }, [height]);

  const pos = (e) => {
    const c = canvasRef.current;
    const rect = c.getBoundingClientRect();
    if (e.touches && e.touches[0]) return { x: e.touches[0].clientX - rect.left, y: e.touches[0].clientY - rect.top };
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };
  const start = (e) => { e.preventDefault(); drawing.current = true; last.current = pos(e); };
  const move = (e) => {
    if (!drawing.current) return;
    e.preventDefault();
    const ctx = canvasRef.current.getContext('2d');
    const p = pos(e);
    ctx.beginPath();
    ctx.moveTo(last.current.x, last.current.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    last.current = p;
    if (empty) setEmpty(false);
  };
  const end = () => {
    if (!drawing.current) return;
    drawing.current = false;
    const url = canvasRef.current.toDataURL('image/png');
    if (onChange) onChange(url);
  };
  const clear = () => {
    const c = canvasRef.current;
    const ctx = c.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const w = c.width / dpr;
    const h = c.height / dpr;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, w, h);
    setEmpty(true);
    if (onChange) onChange('');
  };

  return (
    <div data-testid={testId} className="space-y-1">
      <div className="relative rounded-lg border border-dashed border-slate-300 bg-white overflow-hidden">
        <canvas
          ref={canvasRef}
          style={{ width: '100%', height: `${height}px`, touchAction: 'none', display: 'block' }}
          onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
          onTouchStart={start} onTouchMove={move} onTouchEnd={end}
        />
        {empty ? (
          <span className="absolute inset-0 flex items-center justify-center text-xs text-slate-400 pointer-events-none">
            Sign here
          </span>
        ) : null}
      </div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">Use a finger or mouse to sign. Saved as a PNG image.</span>
        <Button size="sm" variant="ghost" onClick={clear} type="button" data-testid={`${testId}-clear`}>
          <Eraser size={12} className="mr-1" /> Clear
        </Button>
      </div>
    </div>
  );
}
