/* SiconMappings.js — configurable reference-data + customer/site mapping (§11/§13). */
import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Loader2, Plus, Trash2, Save, Link2, Tags } from 'lucide-react';

const MapEditor = ({ title, entries, onChange, hint }) => (
  <div className="rounded-lg border border-white/10 p-3">
    <div className="text-sm font-semibold text-[var(--theme-text)] mb-1">{title}</div>
    <div className="text-xs text-[var(--theme-text-muted)] mb-2">{hint}</div>
    <div className="space-y-2">
      {entries.map((row, i) => (
        <div key={i} className="flex gap-2 items-center">
          <Input value={row.k} onChange={(e) => onChange(entries.map((r, j) => j === i ? { ...r, k: e.target.value } : r))} placeholder="Sicon id or name" className="h-8 text-xs" data-testid={`map-key-${title}-${i}`} />
          <span className="text-[var(--theme-text-muted)]">→</span>
          <Input value={row.v} onChange={(e) => onChange(entries.map((r, j) => j === i ? { ...r, v: e.target.value } : r))} placeholder="Pulse value" className="h-8 text-xs" data-testid={`map-val-${title}-${i}`} />
          <Button size="icon" variant="ghost" onClick={() => onChange(entries.filter((_, j) => j !== i))}><Trash2 size={14} /></Button>
        </div>
      ))}
      <Button size="sm" variant="outline" onClick={() => onChange([...entries, { k: '', v: '' }])}><Plus size={14} className="mr-1" /> Add mapping</Button>
    </div>
  </div>
);

const toRows = (obj) => Object.entries(obj || {}).map(([k, v]) => ({ k, v: String(v) }));
const toObj = (rows) => Object.fromEntries(rows.filter((r) => r.k.trim()).map((r) => [r.k.trim(), r.v.trim()]));

const SiconMappings = () => {
  const { API } = useAuth();
  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [ts, setTs] = useState([]);
  const [pr, setPr] = useState([]);
  const [ct, setCt] = useState([]);
  const [lookups, setLookups] = useState(null);
  const [custData, setCustData] = useState({ links: [], companies: [], sites: [] });
  const [newLink, setNewLink] = useState({ entity: 'customer', external_id: '', pulse_id: '' });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ref, cust] = await Promise.all([
        axios.get(`${API}/sicon/read/reference`, { headers }),
        axios.get(`${API}/sicon/read/customer-mappings`, { headers }),
      ]);
      setTs(toRows(ref.data.mappings.tracking_status_mapping));
      setPr(toRows(ref.data.mappings.priority_mapping));
      setCt(toRows(ref.data.mappings.case_type_mapping));
      setLookups(ref.data.lookups);
      setCustData(cust.data);
    } catch (e) { notifyApiError(e); }
    setLoading(false);
  }, [API]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);

  const saveRef = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/sicon/read/reference`, {
        tracking_status_mapping: toObj(ts), priority_mapping: toObj(pr), case_type_mapping: toObj(ct),
      }, { headers });
      notify.success('Reference mappings saved');
    } catch (e) { notifyApiError(e); } finally { setSaving(false); }
  };

  const saveLink = async () => {
    if (!newLink.external_id || !newLink.pulse_id) { notify.error('Enter a Sicon id and pick a Pulse record'); return; }
    try {
      await axios.post(`${API}/sicon/read/customer-mappings`, newLink, { headers });
      notify.success('Mapping saved');
      setNewLink({ entity: 'customer', external_id: '', pulse_id: '' });
      load();
    } catch (e) { notifyApiError(e); }
  };

  if (loading) return <div className="flex items-center gap-2 text-sm text-[var(--theme-text-muted)] py-6"><Loader2 className="animate-spin" size={16} /> Loading mappings…</div>;

  const pulseOpts = newLink.entity === 'customer' ? custData.companies : custData.sites;

  return (
    <div className="space-y-5" data-testid="sicon-mappings">
      <Card className="p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2"><Tags size={18} className="text-[var(--theme-brand)]" /><h3 className="font-bold text-[var(--theme-text)]">Reference-data mapping</h3></div>
          <Button size="sm" onClick={saveRef} disabled={saving} data-testid="sicon-save-reference">{saving ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <Save size={14} className="mr-1.5" />} Save</Button>
        </div>
        {lookups && !lookups.error && (lookups.tracking_statuses?.length || 0) === 0 && (
          <div className="text-xs text-[var(--theme-text-muted)] mb-3">Connect Sicon to pull the live lookup lists. You can still define mappings manually (Sicon id or name → Pulse value).</div>
        )}
        <div className="grid md:grid-cols-3 gap-3">
          <MapEditor title="Tracking status" entries={ts} onChange={setTs} hint="Sicon status → open / in_progress / awaiting_engineer / engineer_assigned / resolved" />
          <MapEditor title="Priority" entries={pr} onChange={setPr} hint="Sicon priority → operational_minor / operational_fault / limited_use / out_of_order / safety_critical" />
          <MapEditor title="Case type" entries={ct} onChange={setCt} hint="Sicon case type → your Pulse fault category" />
        </div>
      </Card>

      <Card className="p-5">
        <div className="flex items-center gap-2 mb-3"><Link2 size={18} className="text-[var(--theme-brand)]" /><h3 className="font-bold text-[var(--theme-text)]">Customer &amp; site mapping</h3></div>
        <div className="text-xs text-[var(--theme-text-muted)] mb-3">Link a Sicon customer / sub-location to a Pulse company / site once — every import reuses it (no name-only guessing).</div>
        <div className="flex flex-wrap gap-2 items-center mb-4">
          <select value={newLink.entity} onChange={(e) => setNewLink({ ...newLink, entity: e.target.value, pulse_id: '' })} className="h-9 rounded-md border border-white/15 bg-transparent text-sm px-2" data-testid="sicon-link-entity">
            <option value="customer">Customer → Company</option>
            <option value="site">Sub-location → Site</option>
          </select>
          <Input value={newLink.external_id} onChange={(e) => setNewLink({ ...newLink, external_id: e.target.value })} placeholder={newLink.entity === 'customer' ? 'Sicon customerId' : 'siconSubLocationDbKey'} className="h-9 text-sm w-48" data-testid="sicon-link-extid" />
          <select value={newLink.pulse_id} onChange={(e) => setNewLink({ ...newLink, pulse_id: e.target.value })} className="h-9 rounded-md border border-white/15 bg-transparent text-sm px-2 min-w-[180px]" data-testid="sicon-link-pulseid">
            <option value="">{`Select Pulse ${newLink.entity === 'customer' ? 'company' : 'site'}…`}</option>
            {(pulseOpts || []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
          <Button size="sm" onClick={saveLink} data-testid="sicon-save-link"><Plus size={14} className="mr-1" /> Link</Button>
        </div>
        {custData.links.length === 0 ? (
          <div className="text-sm text-[var(--theme-text-muted)]">No mappings yet.</div>
        ) : (
          <div className="space-y-1.5" data-testid="sicon-link-list">
            {custData.links.map((l) => (
              <div key={`${l.external_entity_type}-${l.external_id}`} className="flex items-center justify-between text-sm border border-white/10 rounded px-3 py-1.5">
                <span className="text-[var(--theme-text)]">{l.external_entity_type} <b>{l.external_id}</b> → {l.pulse_entity_type} {String(l.pulse_entity_id).slice(0, 8)}…</span>
                <span className="text-xs text-[var(--theme-text-muted)]">{l.sync_status}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};

export default SiconMappings;
