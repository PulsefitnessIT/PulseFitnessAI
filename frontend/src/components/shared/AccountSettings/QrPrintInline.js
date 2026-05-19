/**
 * Inline QR-print panel for Account Settings → Onboarding (Iter 216h108).
 *
 * User feedback: "We have lost the ability to print QR codes in bulk
 * within Account Settings". This component restores that — fetches
 * every machine in the org, lets the operator select / select-all,
 * and opens a print-ready window with one QR per machine.
 *
 * Identical print template to PulseSettingsTab so labels look the
 * same wherever they're triggered.
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Printer, Loader2, CheckSquare, Square, Search } from 'lucide-react';
import { API, useAuthHeaders } from './shared';

export default function QrPrintInline({ onClose }) {
  const headers = useAuthHeaders();
  const [equipment, setEquipment] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [filter, setFilter] = useState('');

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/equipment`, { headers: headers() });
        if (alive) setEquipment(r.data?.equipment || []);
      } catch {
        if (alive) toast.error('Could not load equipment');
      } finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, [headers]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return equipment;
    return equipment.filter((e) =>
      [e.name, e.manufacturer, e.model, e.serial_number, e.location]
        .filter(Boolean).some((v) => String(v).toLowerCase().includes(q))
    );
  }, [equipment, filter]);

  const allSelected = filtered.length > 0 && filtered.every((e) => selected.has(e.id));
  const toggleOne = (id) => setSelected((p) => {
    const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  const toggleAll = () => setSelected((p) => {
    const n = new Set(p);
    if (allSelected) filtered.forEach((e) => n.delete(e.id));
    else filtered.forEach((e) => n.add(e.id));
    return n;
  });

  const printSelected = () => {
    const items = equipment.filter((e) => selected.has(e.id));
    if (!items.length) { toast.error('Select at least one machine'); return; }
    const printWindow = window.open('', '_blank');
    if (!printWindow) { toast.error('Pop-up blocked — please allow pop-ups to print'); return; }
    const origin = window.location.origin;
    // Pulse Fitness logo CDN — same asset used by PulseSettingsTab so
    // labels look identical wherever they're triggered.
    const logoUrl = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg';
    const rows = items.map((eq) => {
      const url = `${origin}/scan/${eq.id}`;
      const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(url)}`;
      const itemCode = eq.model || eq.equipment_type || '';
      const fullName = eq.name || 'Unknown';
      const name = fullName.includes(',') ? fullName.split(',')[0].trim() : (fullName.length > 35 ? fullName.slice(0, 35) + '…' : fullName);
      const serial = eq.serial_number || '';
      return `<div style="width:200px;text-align:center;page-break-inside:avoid;margin:8px;border:1px dashed #ccc;border-radius:8px;padding:10px 6px 8px;">
        <img src="${qrUrl}" width="140" height="140" style="display:block;margin:0 auto;" />
        <img src="${logoUrl}" width="70" style="display:block;margin:6px auto 2px;" />
        ${itemCode ? `<p style="font-size:11px;color:#000;margin:4px 0 0;font-family:sans-serif;font-weight:800;letter-spacing:0.3px;">${itemCode}</p>` : ''}
        <p style="font-size:9px;color:#000;margin:2px 0 0;font-family:sans-serif;font-weight:600;line-height:1.2;">${name}</p>
        ${serial ? `<p style="font-size:8px;color:#000;font-family:monospace;margin:3px 0 0;background:#f0f0f0;display:inline-block;padding:1px 6px;border-radius:3px;">S/N: ${serial}</p>` : ''}
      </div>`;
    }).join('');
    printWindow.document.write(`<!DOCTYPE html><html><head><title>QR Codes</title>
      <style>@media print{body{margin:0}}body{font-family:sans-serif}</style></head>
      <body><div style="display:flex;flex-wrap:wrap;justify-content:center;gap:4px;padding:12px;">${rows}</div>
      <script>setTimeout(()=>window.print(),1500)</script></body></html>`);
    printWindow.document.close();
  };

  if (loading) {
    return <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--theme-text-muted)' }}><Loader2 size={14} className="animate-spin" /> Loading equipment…</div>;
  }

  return (
    <div className="space-y-3" data-testid="account-qr-print-inline">
      <div>
        <h3 className="text-base font-semibold" style={{ color: 'var(--theme-text)' }}>Print QR codes</h3>
        <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
          Select the machines you want labels for, then click <strong>Print</strong>. Each label includes a unique scan URL,
          your brand logo, the model, serial number, and asset name.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[180px]">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--theme-text-muted)' }} />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search machines…"
            className="w-full pl-7 pr-3 py-1.5 text-xs rounded-md border focus:outline-none"
            style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="account-qr-search"
          />
        </div>
        <button
          type="button"
          onClick={toggleAll}
          className="account-btn-secondary inline-flex items-center gap-1.5 text-xs"
          data-testid="account-qr-select-all"
        >
          {allSelected ? <CheckSquare size={13} /> : <Square size={13} />}
          {allSelected ? 'Deselect all' : 'Select all'}
        </button>
      </div>

      <div className="max-h-64 overflow-auto rounded-lg border" style={{ borderColor: 'var(--theme-border)' }} data-testid="account-qr-list">
        {filtered.length === 0 ? (
          <p className="p-4 text-xs text-center" style={{ color: 'var(--theme-text-muted)' }}>No equipment matches.</p>
        ) : filtered.map((eq) => (
          <label
            key={eq.id}
            className="flex items-center gap-3 px-3 py-2 text-sm cursor-pointer hover:bg-black/[0.02]"
            style={{ borderTop: '1px solid var(--theme-border)' }}
            data-testid={`account-qr-row-${eq.id}`}
          >
            <input
              type="checkbox"
              checked={selected.has(eq.id)}
              onChange={() => toggleOne(eq.id)}
              data-testid={`account-qr-check-${eq.id}`}
            />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate" style={{ color: 'var(--theme-text)' }}>{eq.name}</div>
              <div className="text-[11px] truncate" style={{ color: 'var(--theme-text-muted)' }}>
                {[eq.manufacturer, eq.model, eq.serial_number].filter(Boolean).join(' · ') || '—'}
              </div>
            </div>
          </label>
        ))}
      </div>

      <div className="flex items-center justify-between pt-2">
        <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
          {selected.size} of {equipment.length} selected
        </span>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} className="account-btn-secondary" data-testid="account-qr-close">
            Back
          </button>
          <button
            type="button"
            onClick={printSelected}
            disabled={selected.size === 0}
            className="account-btn-primary inline-flex items-center gap-2 disabled:opacity-50"
            data-testid="account-qr-print-btn"
          >
            <Printer size={14} /> Print {selected.size || ''} QR{selected.size === 1 ? '' : 's'}
          </button>
        </div>
      </div>
    </div>
  );
}
