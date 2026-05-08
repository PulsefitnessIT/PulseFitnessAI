import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
  Upload, Layout, Trash2, Plus, Loader2, ZoomIn, ZoomOut,
  Save, Search, Brain, ImageIcon, Grid3X3, Eye, Edit, Info, AlertTriangle,
  RotateCw, Undo2, PanelRightClose, PanelRightOpen
} from 'lucide-react';

const GRID = 0.25;
const TYPE_DIMS = {
  'Treadmill':{w:2.0,h:0.8},'Cross Trainer':{w:1.8,h:0.7},'Cycle':{w:1.2,h:0.5},
  'Recumbent':{w:1.5,h:0.6},'Rower':{w:2.4,h:0.5},'Stepper':{w:1.2,h:0.8},
  'StepMill':{w:1.2,h:0.8},'AirBike':{w:1.3,h:0.6},'Bike':{w:1.2,h:0.5},
  'Ski Erg':{w:0.6,h:1.5},'Strength':{w:1.5,h:1.2},'Chest Press':{w:1.5,h:1.2},
  'Shoulder Press':{w:1.4,h:1.2},'Lat Pulldown':{w:1.5,h:1.3},'Leg Press':{w:2.0,h:1.0},
  'Leg Extension':{w:1.4,h:1.0},'Leg Curl':{w:1.4,h:1.0},'Cable':{w:1.5,h:2.0},
  'Functional':{w:3.0,h:1.5},'Rack':{w:1.5,h:1.5},'Bench':{w:1.5,h:0.7},
  'Dumbbell':{w:2.5,h:0.6},'default':{w:1.2,h:0.8},
};
const PALETTE = ['var(--pulse-primary-hover)','#4CAF50','#FF9800','#E91E63','#9C27B0','#00BCD4','#FF5722','#8BC34A','#FFEB3B','#795548'];

function fallbackDims(eq) {
  const n = (eq.name||eq.equipment_type||'').toLowerCase();
  for (const [k,d] of Object.entries(TYPE_DIMS)) if (k!=='default' && n.includes(k.toLowerCase())) return d;
  return TYPE_DIMS.default;
}
function color(num) { return PALETTE[(num-1)%PALETTE.length]; }
function sn(v, on) { return on ? Math.round(v/GRID)*GRID : Math.round(v*100)/100; }

/* ═══════ SVG CANVAS (Mouse + Touch) ═══════ */
const GymCanvas = ({ gymW, gymH, px, bgUrl, items, setItems, placing, onPlace, snapOn, selIdx, setSelIdx, setDirty, onScaleChange }) => {
  const ref = useRef(null);
  const scrollRef = useRef(null);
  const prevPxRef = useRef(px);
  const [dragIdx, setDragIdx] = useState(null);
  const [off, setOff] = useState({x:0,y:0});
  const [hover, setHover] = useState(null);
  const pinchRef = useRef(null);
  const W = gymW*px, H = gymH*px;

  // Preserve scroll center when zoom (px) changes
  useEffect(() => {
    const container = scrollRef.current;
    if (!container || prevPxRef.current === px) return;
    const ratio = px / prevPxRef.current;
    const oldCX = container.scrollLeft + container.clientWidth / 2;
    const oldCY = container.scrollTop + container.clientHeight / 2;
    container.scrollLeft = oldCX * ratio - container.clientWidth / 2;
    container.scrollTop = oldCY * ratio - container.clientHeight / 2;
    prevPxRef.current = px;
  }, [px]);

  const toM = useCallback((cx,cy) => {
    const r = ref.current?.getBoundingClientRect();
    return r ? {mx:(cx-r.left)/px, my:(cy-r.top)/px} : {mx:0,my:0};
  }, [px]);

  const justSelectedRef = useRef(false);

  /* ── Shared start/move/end logic ── */
  const startDrag = useCallback((cx, cy, idx) => {
    if (placing) return;
    const {mx,my} = toM(cx,cy);
    setDragIdx(idx);
    setSelIdx(idx);
    justSelectedRef.current = true;
    setOff({x:mx-items[idx].x, y:my-items[idx].y});
  }, [placing, toM, items, setSelIdx]);

  const moveDrag = useCallback((cx, cy) => {
    if (dragIdx===null) return;
    const {mx,my} = toM(cx,cy);
    const p = items[dragIdx];
    const rw = (p.rotation===90||p.rotation===270)?p.h:p.w;
    const rh = (p.rotation===90||p.rotation===270)?p.w:p.h;
    const nx = sn(Math.max(0,Math.min(gymW-rw,mx-off.x)),snapOn);
    const ny = sn(Math.max(0,Math.min(gymH-rh,my-off.y)),snapOn);
    setItems(prev => prev.map((pp,i)=>i===dragIdx?{...pp,x:nx,y:ny}:pp));
    setDirty(true);
  }, [dragIdx,off,gymW,gymH,items,setItems,snapOn,toM,setDirty]);

  const endDrag = useCallback(() => setDragIdx(null), []);

  /* ── Mouse handlers ── */
  const onMouseDown = (e, idx) => { e.stopPropagation(); startDrag(e.clientX, e.clientY, idx); };

  const onMouseMove = useCallback((e) => moveDrag(e.clientX, e.clientY), [moveDrag]);
  const onMouseUp = useCallback(() => endDrag(), [endDrag]);

  useEffect(() => {
    if (dragIdx!==null) {
      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
      return () => { window.removeEventListener('mousemove', onMouseMove); window.removeEventListener('mouseup', onMouseUp); };
    }
  }, [dragIdx, onMouseMove, onMouseUp]);

  /* ── Touch handlers ── */
  const onTouchStartItem = useCallback((e, idx) => {
    if (e.touches.length === 1) {
      e.stopPropagation();
      const t = e.touches[0];
      startDrag(t.clientX, t.clientY, idx);
    }
  }, [startDrag]);

  const onTouchMoveCanvas = useCallback((e) => {
    if (e.touches.length === 2 && onScaleChange) {
      e.preventDefault();
      const dist = Math.hypot(e.touches[0].clientX-e.touches[1].clientX, e.touches[0].clientY-e.touches[1].clientY);
      if (pinchRef.current !== null) {
        const delta = dist - pinchRef.current;
        if (Math.abs(delta) > 8) {
          onScaleChange(delta > 0 ? 5 : -5);
          pinchRef.current = dist;
        }
      } else {
        pinchRef.current = dist;
      }
      return;
    }
    if (dragIdx !== null && e.touches.length === 1) {
      e.preventDefault();
      const t = e.touches[0];
      moveDrag(t.clientX, t.clientY);
    }
  }, [dragIdx, moveDrag, onScaleChange]);

  const onTouchEndCanvas = useCallback(() => {
    pinchRef.current = null;
    endDrag();
  }, [endDrag]);

  // Canvas click / tap — place machine or deselect
  const onClick = (e) => {
    if (justSelectedRef.current) {
      justSelectedRef.current = false;
      return; // Don't deselect — user just clicked an equipment shape
    }
    if (placing) {
      const cx = e.clientX ?? e.changedTouches?.[0]?.clientX;
      const cy = e.clientY ?? e.changedTouches?.[0]?.clientY;
      if (cx != null) {
        const {mx,my} = toM(cx,cy);
        onPlace(sn(mx,snapOn), sn(my,snapOn));
      }
    } else {
      setSelIdx(null);
    }
  };

  // Grid lines
  const lines = [];
  for (let x=0;x<=gymW;x++) lines.push(<line key={`v${x}`} x1={x*px} y1={0} x2={x*px} y2={H} stroke="rgba(255,255,255,0.05)" strokeWidth={x%5===0?1.5:0.5}/>);
  for (let y=0;y<=gymH;y++) lines.push(<line key={`h${y}`} x1={0} y1={y*px} x2={W} y2={y*px} stroke="rgba(255,255,255,0.05)" strokeWidth={y%5===0?1.5:0.5}/>);

  /* ── Toolbar action helpers (keep complexity low) ── */
  const rotateSelected = (e) => {
    e.stopPropagation();
    setItems(prev=>prev.map((pp,i)=>i===selIdx?{...pp,rotation:((pp.rotation||0)+90)%360}:pp));
    setDirty(true);
  };
  const removeSelected = (e) => {
    e.stopPropagation();
    setItems(prev=>prev.filter((_,i)=>i!==selIdx));
    setSelIdx(null);
    setDirty(true);
  };

  return (
    <div ref={scrollRef} className="relative overflow-auto rounded-lg border touch-none"
      style={{borderColor:'var(--theme-border)',background:'var(--theme-bg)'}} data-testid="gym-canvas">
      <svg ref={ref} width={W} height={H}
        style={{display:'block',cursor:placing?'crosshair':'default',touchAction:'none',background:'var(--color-surface-dark-2)'}}
        onClick={onClick}
        onTouchMove={onTouchMoveCanvas}
        onTouchEnd={onTouchEndCanvas}
        onTouchCancel={onTouchEndCanvas}>
        {bgUrl && <image href={bgUrl} x={0} y={0} width={W} height={H} opacity={0.4} preserveAspectRatio="xMidYMid slice"/>}
        {lines}
        {/* Scale labels */}
        {Array.from({length:Math.floor(gymW/5)+1},(_,i)=><text key={`sx${i}`} x={i*5*px+3} y={11} fill="rgba(255,255,255,0.2)" fontSize={9}>{i*5}m</text>)}
        {Array.from({length:Math.floor(gymH/5)+1},(_,i)=><text key={`sy${i}`} x={4} y={i*5*px+12} fill="rgba(255,255,255,0.2)" fontSize={9}>{i*5}m</text>)}

        {/* Equipment shapes */}
        {items.map((p,idx) => {
          const c = color(p.number||1);
          const rot = p.rotation||0;
          const rw = (rot===90||rot===270)?p.h:p.w, rh = (rot===90||rot===270)?p.w:p.h;
          const pcx = (p.x+rw/2)*px, pcy = (p.y+rh/2)*px;
          const isSel = selIdx===idx;
          const isHov = hover===idx;
          return (
            <g key={idx}
              onMouseDown={e=>onMouseDown(e,idx)}
              onTouchStart={e=>onTouchStartItem(e,idx)}
              onMouseEnter={()=>setHover(idx)}
              onMouseLeave={()=>setHover(null)}
              style={{cursor:placing?'crosshair':dragIdx===idx?'grabbing':'grab'}}
              data-testid={`gym-equip-${p.equipment_id||idx}`}>
              {/* Shadow for depth */}
              <rect x={p.x*px+2} y={p.y*px+2} width={rw*px} height={rh*px} fill="rgba(0,0,0,0.3)" rx={4}/>
              {/* Main shape */}
              <rect x={p.x*px} y={p.y*px} width={rw*px} height={rh*px}
                fill={isSel?c+'50':isHov?c+'40':c+'25'}
                stroke={isSel?'#fff':isHov?c:c+'99'}
                strokeWidth={isSel?2.5:isHov?2:1.2} rx={4}/>
              {/* Number */}
              <text x={pcx} y={pcy-3} textAnchor="middle" dominantBaseline="middle"
                fill="white" fontSize={Math.min(18,Math.min(rw,rh)*px*0.45)} fontWeight="800"
                style={{pointerEvents:'none',textShadow:'0 1px 3px rgba(0,0,0,0.8)'}}>{p.number||'?'}</text>
              {/* Dims label on hover/select */}
              {(isHov||isSel) && (
                <text x={pcx} y={pcy+10} textAnchor="middle" dominantBaseline="middle"
                  fill="rgba(255,255,255,0.6)" fontSize={8} style={{pointerEvents:'none'}}>
                  {p.w}×{p.h}m
                </text>
              )}
            </g>
          );
        })}

        {/* Mini Toolbar for selected machine */}
        {selIdx!==null && items[selIdx] && (() => {
          const p = items[selIdx];
          const rot = p.rotation||0;
          const rw = (rot===90||rot===270)?p.h:p.w;
          const tx = (p.x+rw/2)*px;
          const ty = p.y*px - 48;
          const updateDim = (field, val) => {
            const n = parseFloat(val);
            if (!isNaN(n) && n > 0) { setItems(prev=>prev.map((pp,i)=>i===selIdx?{...pp,[field]:n}:pp)); setDirty(true); }
          };
          return (
            <foreignObject x={tx-160} y={Math.max(0,ty)} width={320} height={44}>
              <div className="flex items-center justify-center" xmlns="http://www.w3.org/1999/xhtml">
                <div className="flex items-center gap-1 rounded-lg px-2 py-1.5 shadow-xl"
                  style={{background:'var(--theme-surface)',border:'1px solid var(--theme-border)'}} data-testid={`toolbar-${selIdx}`}>
                  <span className="text-[10px] px-0.5" style={{color:'var(--theme-text-muted)'}}>W</span>
                  <input type="number" step="0.1" min="0.1" value={p.w} onChange={e=>updateDim('w',e.target.value)}
                    onClick={e=>e.stopPropagation()}
                    className="w-12 h-6 text-[11px] text-center font-mono rounded focus:outline-none focus:ring-1 focus:ring-[var(--pulse-primary-hover)]"
                    style={{background:'var(--theme-bg)',border:'1px solid var(--theme-border)',color:'var(--theme-text)'}}
                    data-testid={`toolbar-w-${selIdx}`}/>
                  <span className="text-[10px]" style={{color:'var(--theme-text-muted)'}}>×</span>
                  <input type="number" step="0.1" min="0.1" value={p.h} onChange={e=>updateDim('h',e.target.value)}
                    onClick={e=>e.stopPropagation()}
                    className="w-12 h-6 text-[11px] text-center font-mono rounded focus:outline-none focus:ring-1 focus:ring-[var(--pulse-primary-hover)]"
                    style={{background:'var(--theme-bg)',border:'1px solid var(--theme-border)',color:'var(--theme-text)'}}
                    data-testid={`toolbar-h-${selIdx}`}/>
                  <span className="text-[9px]" style={{color:'var(--theme-text-muted)'}}>m</span>
                  <div className="w-px h-5 mx-0.5" style={{background:'var(--theme-border)'}}/>
                  <button onClick={rotateSelected} className="p-1.5 rounded transition-colors" style={{color:'var(--theme-text)'}} title="Rotate 90°"><RotateCw size={15}/></button>
                  <div className="w-px h-5 mx-0.5" style={{background:'var(--theme-border)'}}/>
                  <button onClick={removeSelected} className="p-1.5 rounded text-red-500 transition-colors" title="Remove"><Trash2 size={15}/></button>
                </div>
              </div>
            </foreignObject>
          );
        })()}
      </svg>
    </div>
  );
};

/* ═══════ SIDEBAR (collapsible on mobile) ═══════ */
const Sidebar = ({ equipment, items, search, setSearch, onSelect, placing, legend, collapsed, onToggle }) => {
  const placedIds = new Set(items.map(p=>p.equipment_id));
  const q = search.toLowerCase();
  const filtered = equipment.filter(eq => (eq.name||'').toLowerCase().includes(q)||(eq.equipment_type||'').toLowerCase().includes(q)||(eq.serial_number||'').toLowerCase().includes(q));
  const unplaced = filtered.filter(eq=>!placedIds.has(eq.id));

  if (collapsed) {
    return (
      <div className="w-10 shrink-0 flex flex-col items-center border-l py-2"
        style={{borderColor:'var(--theme-border)',background:'var(--theme-surface)'}} data-testid="equipment-sidebar-collapsed">
        <button onClick={onToggle} className="p-1.5 rounded transition-colors mb-2"
          style={{color:'var(--theme-text-muted)'}} title="Open sidebar" data-testid="sidebar-expand-btn">
          <PanelRightClose size={16}/>
        </button>
        <Badge className="bg-[rgb(var(--rgb-pulse-primary-hover)/0.15)] text-[var(--pulse-primary-hover)] border-0 text-[9px] px-1">{unplaced.length}</Badge>
      </div>
    );
  }

  return (
    <div className="w-60 shrink-0 flex flex-col border-l"
      style={{borderColor:'var(--theme-border)',background:'var(--theme-surface)'}} data-testid="equipment-sidebar">
      <div className="p-3 border-b" style={{borderColor:'var(--theme-border)'}}>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-semibold" style={{color:'var(--theme-text)'}}>Equipment Key</h4>
          <button onClick={onToggle} className="p-1 rounded transition-colors md:hidden"
            style={{color:'var(--theme-text-muted)'}} title="Collapse sidebar" data-testid="sidebar-collapse-btn">
            <PanelRightOpen size={14}/>
          </button>
        </div>
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{color:'var(--theme-text-muted)'}}/>
          <Input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Filter..."
            className="text-xs pl-7 h-8"
            style={{background:'var(--theme-bg)',borderColor:'var(--theme-border)',color:'var(--theme-text)'}}/>
        </div>
        {placing && (
          <div className="mt-2 p-2 bg-[rgb(var(--rgb-pulse-primary-hover)/0.1)] border border-[rgb(var(--rgb-pulse-primary-hover)/0.3)] rounded text-[10px] text-[var(--pulse-primary-hover)] text-center animate-pulse">
            Tap on the drawing to place <strong>#{placing.number}</strong>
          </div>
        )}
      </div>
      {/* Legend */}
      <div className="p-2 border-b max-h-28 overflow-y-auto" style={{borderColor:'var(--theme-border)'}}>
        <p className="text-[9px] font-medium mb-1 px-1 uppercase tracking-wider" style={{color:'var(--theme-text-muted)'}}>Legend</p>
        {legend.map(l=>(
          <div key={l.number} className="flex items-center gap-1.5 px-1 py-0.5 text-[10px]">
            <div className="w-5 h-4 rounded flex items-center justify-center text-white font-bold text-[9px] shrink-0" style={{background:color(l.number)+'40',border:`1.5px solid ${color(l.number)}`}}>{l.number}</div>
            <span className="truncate" style={{color:'var(--theme-text-muted)'}}>{l.label}</span>
          </div>
        ))}
      </div>
      {/* Available machines */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-2">
          <p className="text-[9px] font-medium mb-1 px-1 uppercase tracking-wider" style={{color:'var(--theme-text-muted)'}}>Available ({unplaced.length})</p>
          {unplaced.map(eq=>(
            <button key={eq.id} onClick={()=>onSelect(eq)}
              className={`w-full text-left p-2 rounded text-xs transition-all mb-0.5 ${placing?.id===eq.id?'bg-[rgb(var(--rgb-pulse-primary-hover)/0.15)] ring-1 ring-[rgb(var(--rgb-pulse-primary-hover)/0.5)] text-[var(--pulse-primary-hover)]':''}`}
              style={placing?.id===eq.id ? {} : {color:'var(--theme-text)'}}
              data-testid={`sidebar-equip-${eq.id}`}>
              <div className="flex items-center gap-2">
                <div className="w-5 h-4 rounded flex items-center justify-center text-white font-bold text-[9px] shrink-0" style={{background:color(eq.number)+'40',border:`1.5px solid ${color(eq.number)}`}}>{eq.number}</div>
                <span className="truncate">{(eq.name||'').split(',')[0].trim()}</span>
              </div>
              {eq.serial_number && <p className="text-[10px] ml-7 truncate" style={{color:'var(--theme-text-muted)'}}>{eq.serial_number}</p>}
              {(eq.length_m&&eq.width_m) && <p className="text-[9px] text-[rgb(var(--rgb-pulse-primary-hover)/0.5)] ml-7">{eq.length_m}m × {eq.width_m}m</p>}
            </button>
          ))}
          {unplaced.length===0 && <p className="text-[10px] text-emerald-500 text-center py-3 opacity-60">All machines placed</p>}
        </div>
      </div>
    </div>
  );
};

/* ═══════ INTERACTIVE VIEW CANVAS (read-only, click for details) ═══════ */
const GymViewCanvas = ({ gymW, gymH, px, bgUrl, items, legend, onMachineClick }) => {
  const ref = useRef(null);
  const [hover, setHover] = useState(null);
  const W = gymW * px, H = gymH * px;

  const lines = [];
  for (let x = 0; x <= gymW; x++) lines.push(<line key={`v${x}`} x1={x*px} y1={0} x2={x*px} y2={H} stroke="rgba(255,255,255,0.05)" strokeWidth={x%5===0?1.5:0.5}/>);
  for (let y = 0; y <= gymH; y++) lines.push(<line key={`h${y}`} x1={0} y1={y*px} x2={W} y2={y*px} stroke="rgba(255,255,255,0.05)" strokeWidth={y%5===0?1.5:0.5}/>);

  return (
    <div className="relative overflow-auto rounded-lg border" style={{borderColor:'var(--theme-border)',background:'var(--theme-bg)'}} data-testid="gym-view-canvas">
      <svg ref={ref} width={W} height={H} style={{display:'block',cursor:'pointer',background:'var(--color-surface-dark-2)'}}>
        {bgUrl && <image href={bgUrl} x={0} y={0} width={W} height={H} opacity={0.4} preserveAspectRatio="xMidYMid slice"/>}
        {lines}
        {items.map((p, idx) => {
          const c = color(p.number || 1);
          const rot = p.rotation || 0;
          const rw = (rot===90||rot===270) ? p.h : p.w;
          const rh = (rot===90||rot===270) ? p.w : p.h;
          const pcx = (p.x + rw/2) * px, pcy = (p.y + rh/2) * px;
          const isHov = hover === idx;
          return (
            <g key={idx}
              onClick={() => onMachineClick(p, idx)}
              onMouseEnter={() => setHover(idx)} onMouseLeave={() => setHover(null)}
              style={{cursor:'pointer'}} data-testid={`view-equip-${p.equipment_id||idx}`}>
              <rect x={p.x*px+2} y={p.y*px+2} width={rw*px} height={rh*px} fill="rgba(0,0,0,0.3)" rx={4}/>
              <rect x={p.x*px} y={p.y*px} width={rw*px} height={rh*px}
                fill={isHov ? c+'50' : c+'25'} stroke={isHov ? '#fff' : c+'99'}
                strokeWidth={isHov ? 2.5 : 1.2} rx={4}/>
              <text x={pcx} y={pcy-3} textAnchor="middle" dominantBaseline="middle"
                fill="white" fontSize={Math.min(18, Math.min(rw,rh)*px*0.45)} fontWeight="800"
                style={{pointerEvents:'none',textShadow:'0 1px 3px rgba(0,0,0,0.8)'}}>{p.number||'?'}</text>
              {isHov && (
                <text x={pcx} y={pcy+10} textAnchor="middle" dominantBaseline="middle"
                  fill="rgba(255,255,255,0.7)" fontSize={8} style={{pointerEvents:'none'}}>
                  Click for details
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
};

/* ═══════ MACHINE DETAIL PANEL (shown in view mode) ═══════ */
const MachineDetailPanel = ({ machine, equipmentData, onClose, onLogFault, API }) => {
  const eq = equipmentData?.find(e => e.id === machine?.equipment_id);
  if (!machine) return null;
  const name = eq?.name || machine.name || 'Unknown Machine';
  const serial = eq?.serial_number || machine.serial_number || '';
  const model = eq?.model || '';
  const manufacturer = eq?.manufacturer || machine.manufacturer || '';
  const eqType = eq?.equipment_type || machine.equipment_type || '';

  return (
    <div className="w-72 shrink-0 flex flex-col border-l overflow-y-auto"
      style={{borderColor:'var(--theme-border)',background:'var(--theme-surface)'}} data-testid="machine-detail-panel">
      <div className="p-4 border-b" style={{borderColor:'var(--theme-border)'}}>
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-semibold text-sm" style={{color:'var(--theme-text)'}}>Machine Details</h4>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-white transition-colors text-xs">Close</button>
        </div>
        <div className="w-8 h-8 rounded flex items-center justify-center text-white font-bold text-sm mb-3"
          style={{background:color(machine.number||1)+'50',border:`2px solid ${color(machine.number||1)}`}}>
          {machine.number||'?'}
        </div>
      </div>
      <div className="p-4 space-y-3 text-xs">
        {model && <div><p className="uppercase tracking-wider mb-0.5" style={{color:'var(--theme-text-muted)',fontSize:'9px'}}>Item Code / Model</p><p className="font-semibold" style={{color:'var(--theme-text)'}}>{model}</p></div>}
        <div><p className="uppercase tracking-wider mb-0.5" style={{color:'var(--theme-text-muted)',fontSize:'9px'}}>Equipment Name</p><p style={{color:'var(--theme-text)'}}>{name}</p></div>
        {eqType && <div><p className="uppercase tracking-wider mb-0.5" style={{color:'var(--theme-text-muted)',fontSize:'9px'}}>Type</p><p style={{color:'var(--theme-text)'}}>{eqType}</p></div>}
        {manufacturer && <div><p className="uppercase tracking-wider mb-0.5" style={{color:'var(--theme-text-muted)',fontSize:'9px'}}>Manufacturer</p><p style={{color:'var(--theme-text)'}}>{manufacturer}</p></div>}
        {serial && <div><p className="uppercase tracking-wider mb-0.5" style={{color:'var(--theme-text-muted)',fontSize:'9px'}}>Serial Number</p><p className="font-mono" style={{color:'var(--theme-text)'}}>{serial}</p></div>}
        <div><p className="uppercase tracking-wider mb-0.5" style={{color:'var(--theme-text-muted)',fontSize:'9px'}}>Position</p><p style={{color:'var(--theme-text)'}}>{machine.w}m × {machine.h}m at ({machine.x?.toFixed(1)}, {machine.y?.toFixed(1)})</p></div>
      </div>
      <div className="p-4 mt-auto border-t" style={{borderColor:'var(--theme-border)'}}>
        <Button className="w-full bg-amber-500 hover:bg-amber-600 text-white" size="sm" onClick={() => onLogFault(eq || machine)} data-testid="view-log-fault-btn">
          <AlertTriangle size={14} className="mr-1.5"/> Log a Fault
        </Button>
      </div>
    </div>
  );
};

/* ═══════ MAIN ═══════ */
const PulseGymLayoutTab = () => {
  const { API } = useAuth();
  const [eqData, setEqData] = useState({equipment:[],legend:[]});
  const [layouts, setLayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(null);
  const [items, setItems] = useState([]);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [scale, setScale] = useState(40);
  const [bgUrl, setBgUrl] = useState(null);
  const [placing, setPlacing] = useState(null);
  const [selIdx, setSelIdx] = useState(null);
  const [sSearch, setSSearch] = useState('');
  const [snapOn, setSnapOn] = useState(true);
  const [history, setHistory] = useState([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  // View mode (read-only interactive)
  const [viewing, setViewing] = useState(null);
  const [viewBgUrl, setViewBgUrl] = useState(null);
  const [viewMachine, setViewMachine] = useState(null);
  const [viewScale, setViewScale] = useState(40);
  // Create dialog
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newL, setNewL] = useState(20);
  const [newW, setNewW] = useState(15);
  const [upFile, setUpFile] = useState(null);
  const [creating, setCreating] = useState(false);
  const [aiDetecting, setAiDetecting] = useState(false);

  const token = localStorage.getItem('token');
  const headers = {Authorization:`Bearer ${token}`};

  const load = useCallback(async()=>{
    try {
      const [dR,lR] = await Promise.all([
        axios.get(`${API}/gym-layouts/equipment-dimensions`,{headers}),
        axios.get(`${API}/gym-layouts`,{headers}),
      ]);
      setEqData(dR.data||{equipment:[],legend:[]});
      setLayouts(lR.data?.layouts||[]);
    } catch(e){console.error(e);}
    setLoading(false);
  },[API]);

  useEffect(()=>{load();},[load]);

  // Expose equipment for toolbar fault logging
  useEffect(()=>{window.__gymEquipment=eqData.equipment;},[eqData.equipment]);

  const loadBg = useCallback(async(fid)=>{
    if(!fid||fid.length<10){setBgUrl(null);return;}
    try{const r=await axios.get(`${API}/files/${fid}`,{headers,responseType:'blob'});setBgUrl(URL.createObjectURL(r.data));}catch{setBgUrl(null);}
  },[API]);

  // ── Undo ──
  const pushHistory = () => setHistory(prev=>[...prev.slice(-19),JSON.stringify(items)]);
  const undo = () => {
    if(!history.length)return;
    const prev = history[history.length-1];
    setHistory(h=>h.slice(0,-1));
    setItems(JSON.parse(prev));
    setSelIdx(null);
    setDirty(true);
  };

  // ── Place machine ──
  const handlePlace = (mx,my) => {
    if(!placing) return;
    pushHistory();
    const dims = (placing.length_m&&placing.width_m)?{w:placing.length_m,h:placing.width_m}:fallbackDims(placing);
    const newItem = {
      equipment_id:placing.id, name:placing.name, serial_number:placing.serial_number||'',
      equipment_type:placing.equipment_type, manufacturer:placing.manufacturer, number:placing.number,
      x:Math.max(0,mx-dims.w/2), y:Math.max(0,my-dims.h/2), w:dims.w, h:dims.h, rotation:0,
    };
    const newIdx = items.length;
    setItems(prev=>[...prev,newItem]);
    setPlacing(null);
    setSelIdx(newIdx); // Auto-select → shows toolbar immediately
    setDirty(true);
  };

  // ── CRUD ──
  const handleCreate = async()=>{
    if(!newName.trim()){notify.error('Enter a name');return;}
    setCreating(true);
    let fpId=null, aiPos=[];
    if(upFile){
      try{
        const fd=new FormData();fd.append('file',upFile);
        const uR=await axios.post(`${API}/files/upload?category=floor-plans`,fd,{headers:{...headers,'Content-Type':'multipart/form-data'}});
        fpId=uR.data.id; notify.success('Floor plan uploaded');
        setAiDetecting(true);
        try{
          const df=new FormData();df.append('file',upFile);
          const dR=await axios.post(`${API}/gym-layouts/detect-equipment`,df,{headers:{...headers,'Content-Type':'multipart/form-data'},timeout:60000});
          const det=dR.data?.equipment||[];
          if(det.length>0){notify.success(`AI detected ${det.length} machines`);aiPos=det.map((d,i)=>{const dm=fallbackDims(d);return{equipment_id:null,name:d.name||d.type,serial_number:'',equipment_type:d.type,number:i+1,x:sn((d.x_percent/100)*newL,true),y:sn((d.y_percent/100)*newW,true),w:d.width_m||dm.w,h:d.length_m||dm.h,rotation:0,ai_detected:true};});}
          else notify.info('No equipment detected — place manually from sidebar');
        }catch{notify.info('AI unavailable — place manually');}
        setAiDetecting(false);
      }catch(e){notifyApiError(notify, e, 'Upload failed');setCreating(false);setAiDetecting(false);return;}
    }
    try{
      const r=await axios.post(`${API}/gym-layouts`,{name:newName,gym_length:newL,gym_width:newW,equipment_positions:aiPos,floor_plan_url:fpId||''},{headers});
      const c={...r.data,floor_plan_url:fpId||''};
      if(fpId)await axios.patch(`${API}/gym-layouts/${c.id}`,{name:newName,gym_length:newL,gym_width:newW,equipment_positions:aiPos,floor_plan_url:fpId},{headers}).catch(()=>{});
      notify.success('Layout created');
      setShowCreate(false);setNewName('');setUpFile(null);
      setActive(c);setItems(aiPos);setDirty(false);setHistory([]);
      if(fpId)loadBg(fpId);
      load();
    }catch{notify.error('Failed to create');}
    setCreating(false);
  };

  const open = (l)=>{setActive(l);setItems(l.equipment_positions||[]);setDirty(false);setSelIdx(null);setPlacing(null);setHistory([]);loadBg(l.floor_plan_url);};
  const openView = async(l)=>{
    setViewing(l);setViewMachine(null);setViewScale(40);
    if(l.floor_plan_url&&l.floor_plan_url.length>10){
      try{const r=await axios.get(`${API}/files/${l.floor_plan_url}`,{headers,responseType:'blob'});setViewBgUrl(URL.createObjectURL(r.data));}catch{setViewBgUrl(null);}
    } else { setViewBgUrl(null); }
  };
  const closeView = ()=>{setViewing(null);setViewBgUrl(null);setViewMachine(null);};
  const handleViewLogFault = (eq) => {
    // Navigate to the faults tab with this equipment pre-selected
    window.dispatchEvent(new CustomEvent('open-fault-for-equipment', { detail: eq }));
    closeView();
  };
  const save = async()=>{
    if(!active)return;setSaving(true);
    try{await axios.patch(`${API}/gym-layouts/${active.id}`,{name:active.name,gym_length:active.gym_length,gym_width:active.gym_width,equipment_positions:items,floor_plan_url:active.floor_plan_url||''},{headers});notify.success('Layout saved — view it from the layout cards');setDirty(false);await load();setActive(null);setItems([]);setBgUrl(null);setPlacing(null);setSelIdx(null);}catch{notify.error('Save failed');}
    setSaving(false);
  };
  const del = async(id)=>{try{await axios.delete(`${API}/gym-layouts/${id}`,{headers});notify.success('Deleted');if(active?.id===id){setActive(null);setItems([]);setBgUrl(null);}load();}catch{notify.error('Delete failed');}};
  const back = ()=>{if(dirty&&!window.confirm('Unsaved changes will be lost. Continue?'))return;setActive(null);setItems([]);setBgUrl(null);setPlacing(null);setSelIdx(null);};

  if(loading)return<div className="flex justify-center py-16"><Loader2 className="animate-spin text-[var(--pulse-primary-hover)]" size={28}/></div>;

  /* ═══ VIEW MODE (read-only interactive) ═══ */
  if(viewing){
    const vW = viewing.gym_length||20, vH = viewing.gym_width||15;
    const vItems = viewing.equipment_positions||[];
    return(
      <div className="space-y-2" data-testid="gym-layout-viewer">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Button variant="outline" size="sm" className="border-[var(--theme-border)] text-[var(--color-text-muted)] h-8" onClick={closeView} data-testid="view-back-btn">Back</Button>
            <h3 className="font-semibold text-sm" style={{color:'var(--theme-text)'}}>{viewing.name}</h3>
            <Badge className="bg-[rgb(var(--rgb-pulse-primary-hover)/0.15)] text-[var(--pulse-primary-hover)] border-0 text-[10px]">{vW}×{vH}m</Badge>
            <Badge className="bg-white/10 text-[var(--color-text-muted)] border-0 text-[10px]">{vItems.length} machines</Badge>
            <Badge className="bg-emerald-500/15 text-emerald-400 border-0 text-[10px]">View Mode</Badge>
          </div>
          <div className="flex items-center gap-1.5">
            <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-[var(--color-text-muted)] h-8 w-8 p-0" onClick={()=>setViewScale(s=>Math.max(15,s-5))}><ZoomOut size={13}/></Button>
            <span className="text-[10px] text-[#555] w-10 text-center">{viewScale}px</span>
            <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-[var(--color-text-muted)] h-8 w-8 p-0" onClick={()=>setViewScale(s=>Math.min(80,s+5))}><ZoomIn size={13}/></Button>
            <Button size="sm" variant="outline" className="border-[rgb(var(--rgb-pulse-primary-hover)/0.3)] text-[var(--pulse-primary-hover)] h-8 px-3" onClick={()=>{closeView();open(viewing);}} data-testid="view-edit-btn">
              <Edit size={13} className="mr-1"/>Edit Layout
            </Button>
          </div>
        </div>
        <p className="text-[10px]" style={{color:'var(--theme-text-muted)'}}>Click any machine to view details and log faults.</p>
        <div className="flex" style={{height:'calc(100vh - 300px)',minHeight:320}}>
          <div className="flex-1 overflow-auto">
            <GymViewCanvas gymW={vW} gymH={vH} px={viewScale} bgUrl={viewBgUrl}
              items={vItems} legend={eqData.legend}
              onMachineClick={(m)=>setViewMachine(m)}/>
          </div>
          {viewMachine && (
            <MachineDetailPanel machine={viewMachine} equipmentData={eqData.equipment}
              onClose={()=>setViewMachine(null)} onLogFault={handleViewLogFault} API={API}/>
          )}
        </div>
      </div>
    );
  }

  /* ═══ EDITOR ═══ */
  if(active){
    const gW=active.gym_length||20, gH=active.gym_width||15;
    return(
      <div className="space-y-2" data-testid="gym-layout-editor">
        {/* Top bar */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Button variant="outline" size="sm" className="border-[var(--theme-border)] text-[var(--color-text-muted)] h-8" onClick={back} data-testid="layout-back-btn">Back</Button>
            <h3 className="text-white font-semibold text-sm truncate max-w-[120px] sm:max-w-none">{active.name}</h3>
            <Badge className="bg-[rgb(var(--rgb-pulse-primary-hover)/0.15)] text-[var(--pulse-primary-hover)] border-0 text-[10px]">{gW}×{gH}m</Badge>
            <Badge className="bg-white/10 text-[var(--color-text-muted)] border-0 text-[10px]">{items.length} placed</Badge>
            {dirty && <Badge className="bg-amber-500/15 text-amber-400 border-0 text-[10px] animate-pulse">Unsaved</Badge>}
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-[var(--color-text-muted)] h-8 w-8 p-0" onClick={undo} disabled={!history.length} title="Undo" data-testid="layout-undo"><Undo2 size={13}/></Button>
            <Button size="sm" variant="outline"
              className={`h-8 px-2.5 text-[11px] font-medium ${snapOn ? 'border-[rgb(var(--rgb-pulse-primary-hover)/0.5)] text-[var(--pulse-primary-hover)] bg-[rgb(var(--rgb-pulse-primary-hover)/0.1)]' : 'border-[var(--theme-border)] text-[var(--color-text-muted)]'}`}
              onClick={()=>setSnapOn(s=>!s)} data-testid="layout-snap-toggle">
              <Grid3X3 size={13} className="mr-1"/>{snapOn ? 'Snap ON' : 'Snap OFF'}
            </Button>
            <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-[var(--color-text-muted)] h-8 w-8 p-0" onClick={()=>setScale(s=>Math.max(15,s-5))} data-testid="layout-zoom-out"><ZoomOut size={13}/></Button>
            <span className="text-[10px] text-[#555] w-10 text-center">{scale}px</span>
            <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-[var(--color-text-muted)] h-8 w-8 p-0" onClick={()=>setScale(s=>Math.min(80,s+5))} data-testid="layout-zoom-in"><ZoomIn size={13}/></Button>
            <Button size="sm" onClick={save} disabled={saving||!dirty} className="bg-[var(--pulse-primary-hover)] hover:bg-[var(--pulse-primary-light)] text-white h-8 px-3" data-testid="layout-save">
              {saving?<Loader2 size={13} className="animate-spin mr-1"/>:<Save size={13} className="mr-1"/>}Save
            </Button>
          </div>
        </div>
        {/* Instructions */}
        <p className="text-[10px] text-[#555] hidden sm:block">
          Select a machine from the sidebar → tap/click to place → drag to reposition → tap placed machine for toolbar (rotate / resize / delete)
          {snapOn?' · Grid snap ON':' · Free movement'}
        </p>
        <p className="text-[10px] text-[#555] sm:hidden">
          Tap sidebar machine → tap canvas to place → drag to move · Pinch to zoom
        </p>
        {/* Canvas + Sidebar */}
        <div className="flex" style={{height:'calc(100vh - 330px)',minHeight:320}}>
          <div className="flex-1 overflow-auto">
            <GymCanvas gymW={gW} gymH={gH} px={scale} bgUrl={bgUrl}
              items={items} setItems={setItems} placing={placing} onPlace={handlePlace}
              snapOn={snapOn} selIdx={selIdx} setSelIdx={setSelIdx} setDirty={setDirty}
              onScaleChange={(d)=>setScale(s=>Math.max(15,Math.min(80,s+d)))}/>
          </div>
          <Sidebar equipment={eqData.equipment} items={items} search={sSearch} setSearch={setSSearch}
            onSelect={setPlacing} placing={placing} legend={eqData.legend}
            collapsed={sidebarCollapsed} onToggle={()=>setSidebarCollapsed(c=>!c)}/>
        </div>
      </div>
    );
  }

  /* ═══ LIST ═══ */
  return(
    <div className="space-y-4" data-testid="gym-layout-list">
      <div className="flex items-center justify-between">
        <div><h3 className="text-white font-semibold text-lg">Gym Floor Plans</h3><p className="text-[var(--color-text-muted)] text-sm">Import CAD drawings and plan equipment placement.</p></div>
        <Button onClick={()=>setShowCreate(true)} className="bg-[var(--pulse-primary-hover)] hover:bg-[var(--pulse-primary-light)] text-white" data-testid="create-layout-btn"><Plus size={16} className="mr-2"/>New Layout</Button>
      </div>
      {layouts.length===0?(
        <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-12 text-center">
          <Layout size={40} className="text-[var(--color-text-muted)] mx-auto mb-3 opacity-40"/>
          <h4 className="text-white font-medium mb-1">No Layouts Yet</h4>
          <p className="text-[var(--color-text-muted)] text-sm mb-4">Import a CAD drawing or create a blank layout.</p>
          <Button onClick={()=>setShowCreate(true)} variant="outline" className="border-[rgb(var(--rgb-pulse-primary-hover)/0.3)] text-[var(--pulse-primary-hover)]"><Plus size={16} className="mr-2"/>Create Layout</Button>
        </Card>
      ):(
        <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {layouts.map(l=>(
            <Card key={l.id} className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-5 hover:border-[rgb(var(--rgb-pulse-primary-hover)/0.3)] transition-all" data-testid={`layout-card-${l.id}`}>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-white font-medium truncate">{l.name}</h4>
                <div className="flex items-center gap-1 shrink-0">
                  <Button size="sm" variant="ghost" className="text-[var(--color-text-muted)] h-7 w-7 p-0" onClick={()=>open(l)} title="Edit Layout" data-testid={`layout-edit-${l.id}`}><Edit size={14}/></Button>
                  <Button size="sm" variant="ghost" className="text-red-400 h-7 w-7 p-0" onClick={e=>{e.stopPropagation();del(l.id);}}><Trash2 size={14}/></Button>
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs mb-3">
                <Badge className="bg-white/10 border-0 text-[var(--color-text-muted)]">{l.gym_length}×{l.gym_width}m</Badge>
                <Badge className="bg-[rgb(var(--rgb-pulse-primary-hover)/0.1)] border-0 text-[var(--pulse-primary-hover)]">{(l.equipment_positions||[]).length} machines</Badge>
                {l.floor_plan_url&&<Badge className="bg-emerald-500/10 border-0 text-emerald-400"><ImageIcon size={10} className="mr-1"/>CAD</Badge>}
              </div>
              <Button size="sm" className="w-full bg-[var(--pulse-primary-hover)] hover:bg-[var(--pulse-primary-light)] text-white h-8" onClick={()=>openView(l)} data-testid={`layout-view-${l.id}`}>
                <Eye size={13} className="mr-1.5"/>View Interactive Layout
              </Button>
            </Card>
          ))}
        </div>
      )}
      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={v=>{if(!creating)setShowCreate(v);}}>
        <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] max-w-md">
          <DialogHeader><DialogTitle className="text-white">New Gym Layout</DialogTitle></DialogHeader>
          <div className="space-y-4 pt-2">
            <div><Label className="text-[var(--color-text-muted)]">Layout Name</Label><Input value={newName} onChange={e=>setNewName(e.target.value)} placeholder="e.g. Main Gym Floor" className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1" data-testid="layout-name-input"/></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-[var(--color-text-muted)]">Length (m)</Label><Input type="number" value={newL} onChange={e=>setNewL(+e.target.value)} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1"/></div>
              <div><Label className="text-[var(--color-text-muted)]">Width (m)</Label><Input type="number" value={newW} onChange={e=>setNewW(+e.target.value)} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1"/></div>
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)]">Import CAD Drawing (optional)</Label>
              <p className="text-[10px] text-[var(--color-text-muted)] mb-2">PDF, JPG or PNG. AI will detect equipment.</p>
              <label className="flex items-center justify-center gap-2 p-4 border-2 border-dashed border-[var(--theme-border)] rounded-lg cursor-pointer hover:border-[var(--pulse-primary-hover)] transition-colors">
                <input type="file" className="hidden" accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={e=>setUpFile(e.target.files?.[0]||null)}/>
                <Upload size={18} className="text-[var(--color-text-muted)]"/><span className="text-sm text-[var(--color-text-muted)]">{upFile?upFile.name:'Choose file...'}</span>
              </label>
            </div>
            {upFile&&<div className="p-2 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded flex items-center gap-2 text-xs text-[var(--pulse-primary-hover)]"><Brain size={14}/>AI will analyse this drawing</div>}
            <Button onClick={handleCreate} disabled={creating} className="w-full bg-[var(--pulse-primary-hover)] hover:bg-[var(--pulse-primary-light)] text-white" data-testid="create-layout-confirm">
              {creating?(aiDetecting?<><Loader2 size={14} className="animate-spin mr-2"/>AI Detecting...</>:<><Loader2 size={14} className="animate-spin mr-2"/>Creating...</>):<><Layout size={16} className="mr-2"/>Create Layout</>}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default PulseGymLayoutTab;
