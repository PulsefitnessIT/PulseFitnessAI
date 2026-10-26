import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Loader2, CheckCircle2, RefreshCw, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { notify } from '@/components/notifications';
import { GapCell } from './GapCell';
import { BulkFillBar } from './BulkFillBar';
import { GapsSummary } from './GapsSummary';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

export const GAP_COLUMNS = [
  ['name', 'Description', 'w-48'], ['sicon_customer_ref', 'Customer Ref', 'w-28'],
  ['location', 'Location', 'w-36'], ['sub_location', 'Sublocation', 'w-28'],
  ['manufacturer', 'Make', 'w-32'], ['model', 'Model', 'w-32'], ['serial_number', 'Serial Number', 'w-36'],
  ['install_date', 'Install Date', 'w-36'], ['last_service_date', 'Last Service', 'w-36'],
  ['service_interval', 'Interval', 'w-20'], ['service_period', 'Period', 'w-24'],
  ['next_service_date', 'Next Service', 'w-36'], ['equipment_group', 'Equipment Group', 'w-32'],
  ['asset_number', 'Asset Tag', 'w-28'], ['condition', 'Condition', 'w-28'],
  ['equipment_type', 'Equipment Type', 'w-32'], ['manufacturing_date', 'Manufacture Date', 'w-36'],
];
const MOD_COLUMN = ['mod_code', 'MOD Code', 'w-28'];
const columnsFor = (isMod) => (isMod ? [GAP_COLUMNS[0], MOD_COLUMN, ...GAP_COLUMNS.slice(1)] : GAP_COLUMNS);

const GapRow = ({ item, onSave, columns }) => (
  <tr className={`border-t border-zinc-100 ${item.missing.length ? '' : 'bg-emerald-50/50'}`} data-testid={`gap-row-${item.id}`}>
    <td className="px-2 py-1.5 align-middle">
      {item.missing.length
        ? <span className="text-[10px] font-semibold text-red-600 whitespace-nowrap" data-testid={`gap-row-status-${item.id}`}>{item.missing.length} missing</span>
        : <span className="text-[10px] font-semibold text-emerald-700 inline-flex items-center gap-1" data-testid={`gap-row-status-${item.id}`}><CheckCircle2 size={11} /> Complete</span>}
    </td>
    {columns.map(([f, , w]) => (
      <td key={f} className="px-1.5 py-1.5"><GapCell item={item} field={f} width={w} missing={item.missing.includes(f)} onSave={onSave} /></td>
    ))}
  </tr>
);

export default function EquipmentGapsPanel({ organizationId, headers, onChanged }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [show, setShow] = useState('incomplete');
  const [siteId, setSiteId] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await axios.get(`${API}/equipment-gaps`, { headers, params: { organization_id: organizationId, show, site_id: siteId || undefined } });
      setData(d);
    } catch (e) { notify.error('Could not load missing information', e?.response?.data?.detail || e.message); }
    finally { setLoading(false); }
  }, [organizationId, show, siteId, headers]);
  useEffect(() => { load(); }, [load]);

  const saveCell = async (id, field, value) => {
    try {
      const { data: r } = await axios.patch(`${API}/equipment-gaps/${id}`, { [field]: value }, { headers });
      setData((d) => {
        const before = d.items.find((it) => it.id === id);
        const s = { ...d.summary, by_field: { ...d.summary.by_field } };
        before.missing.forEach((f) => { s.by_field[f] -= 1; });
        r.item.missing.forEach((f) => { s.by_field[f] = (s.by_field[f] || 0) + 1; });
        const delta = (before.missing.length ? 1 : 0) - (r.item.missing.length ? 1 : 0);
        s.complete += delta; s.incomplete -= delta;
        s.percent_complete = s.total ? Math.round((100 * s.complete) / s.total) : 100;
        return { ...d, summary: s, items: d.items.map((it) => (it.id === id ? { ...it, ...r.item } : it)) };
      });
      onChanged?.();
    } catch (e) { notify.error('Not saved', e?.response?.data?.detail?.message || e?.response?.data?.detail || e.message); throw e; }
  };

  const bulk = async (field, value, onlyBlank) => {
    try {
      const { data: r } = await axios.post(`${API}/equipment-gaps/bulk`, { organization_id: organizationId, site_id: siteId || undefined, field, value, only_blank: onlyBlank }, { headers });
      notify.success(`Updated ${r.updated} asset(s)`);
      load();
      onChanged?.();
    } catch (e) { notify.error('Bulk fill failed', e?.response?.data?.detail || e.message); }
  };

  const exportSheet = async () => {
    try {
      const res = await axios.get(`${API}/equipment-gaps/export.xlsx`, { headers, responseType: 'blob', params: { organization_id: organizationId, site_id: siteId || undefined } });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url; a.download = `Equipment Import - ${data?.organization_name || 'assets'}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { notify.error('Export failed', 'Please try again.'); }
  };

  if (loading && !data) return <div className="py-16 grid place-items-center"><Loader2 className="animate-spin text-zinc-400" /></div>;
  const siteName = data?.sites?.find((s) => s.id === siteId)?.name;

  return (
    <div className="space-y-4" data-testid="equipment-gaps-panel">
      <GapsSummary summary={data?.summary} />
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex gap-1">
          {[['incomplete', 'Needs information'], ['all', 'All assets']].map(([k, l]) => (
            <Button key={k} size="sm" variant={show === k ? 'default' : 'outline'} onClick={() => setShow(k)} data-testid={`gaps-show-${k}`}
              style={show === k ? { color: '#fff' } : undefined}
              className={`h-8 text-xs ${show === k ? 'bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white' : ''}`}>{l}</Button>
          ))}
        </div>
        {data?.sites?.length > 0 && (
          <select value={siteId} onChange={(e) => setSiteId(e.target.value)} className="h-8 rounded-md border border-zinc-200 bg-white px-2 text-xs" data-testid="gaps-site-filter">
            <option value="">All sites</option>
            {data.sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="outline" onClick={exportSheet} className="h-8" data-testid="gaps-export"><Download size={13} className="mr-1.5" /> Sicon sheet</Button>
          <Button size="sm" variant="outline" onClick={load} className="h-8" data-testid="gaps-refresh"><RefreshCw size={13} className={`mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Refresh</Button>
        </div>
      </div>
      <BulkFillBar onApply={bulk} siteName={siteName} />
      {data?.items?.length ? (
        <div className="overflow-auto rounded-lg border border-zinc-200 max-h-[60vh]">
          <table className="min-w-full text-xs" data-testid="gaps-table">
            <thead className="sticky top-0 z-[1] bg-zinc-50 text-[10px] uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="px-2 py-2 text-left font-semibold">Status</th>
                {columnsFor(data.is_mod).map(([f, l]) => <th key={f} className="px-1.5 py-2 text-left font-semibold whitespace-nowrap">{l}</th>)}
              </tr>
            </thead>
            <tbody>{data.items.map((it) => <GapRow key={it.id} item={it} onSave={saveCell} columns={columnsFor(data.is_mod)} />)}</tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-6 text-center text-sm text-emerald-800" data-testid="gaps-empty">
          <CheckCircle2 className="mx-auto mb-2" /> Every asset here has the Sicon essentials.
        </div>
      )}
      <p className="text-[11px] text-zinc-500">Red cells are Sicon essentials{data?.is_mod ? ' (plus MOD Code for MOD sites)' : ''}. Changes save as you leave each cell. Next Service is worked out from Last Service + Interval when left blank.</p>
    </div>
  );
}
