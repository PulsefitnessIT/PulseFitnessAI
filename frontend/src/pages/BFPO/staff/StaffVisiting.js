import React, { useEffect, useState, useCallback } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Btn, Spinner, Empty, Badge, inputCls, Field } from '../ui';
import { KeyRound, Trash2, Plus, Loader2 } from 'lucide-react';

export default function StaffVisiting() {
  const [grants, setGrants] = useState([]);
  const [engineers, setEngineers] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ engineer_id: '', site_id: '', from_date: '', to_date: '' });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [g, e, s] = await Promise.all([bfpo.get('/staff/visiting-access'), bfpo.get('/staff/engineers'), bfpo.get('/sites')]);
    setGrants(g.data.grants); setEngineers(e.data.engineers); setSites(s.data.sites); setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const grant = async () => {
    setBusy(true);
    try { await bfpo.post('/staff/visiting-access', form); setForm({ engineer_id: '', site_id: '', from_date: '', to_date: '' }); await load(); }
    finally { setBusy(false); }
  };
  const revoke = async (id) => { await bfpo.delete(`/staff/visiting-access/${id}`); load(); };

  if (loading) return <Spinner />;
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="p-6 max-w-4xl mx-auto" data-testid="staff-visiting">
      <p className="text-slate-500 text-sm mb-4">Grant a UK engineer temporary access to a site for a date range.</p>

      <Card className="p-4 mb-6">
        <p className="font-semibold text-slate-900 flex items-center gap-2 mb-3"><Plus className="w-4 h-4 text-cyan-600" /> New grant</p>
        <div className="grid md:grid-cols-2 gap-3">
          <Field label="Engineer">
            <select className={inputCls} value={form.engineer_id} onChange={(e) => setForm({ ...form, engineer_id: e.target.value })} data-testid="visiting-engineer">
              <option value="">— choose —</option>{engineers.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
            </select>
          </Field>
          <Field label="Site">
            <select className={inputCls} value={form.site_id} onChange={(e) => setForm({ ...form, site_id: e.target.value })} data-testid="visiting-site">
              <option value="">— choose —</option>{sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="From"><input type="date" className={inputCls} value={form.from_date} onChange={(e) => setForm({ ...form, from_date: e.target.value })} data-testid="visiting-from" /></Field>
          <Field label="To"><input type="date" className={inputCls} value={form.to_date} onChange={(e) => setForm({ ...form, to_date: e.target.value })} data-testid="visiting-to" /></Field>
        </div>
        <Btn variant="primary" className="mt-3" disabled={busy || !form.engineer_id || !form.site_id} onClick={grant} data-testid="visiting-grant">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />} Grant access</Btn>
      </Card>

      {grants.length === 0 ? <Empty icon={KeyRound} title="No visiting grants" testid="visiting-empty" /> : (
        <div className="space-y-2">
          {grants.map((g) => {
            const active = (g.from_date || '') <= today && today <= (g.to_date || '9999');
            return (
              <Card key={g.id} className="p-4 flex items-center gap-3" data-testid={`visiting-grant-${g.id}`}>
                <div className="flex-1">
                  <p className="font-semibold text-slate-900">{g.engineer_name} → {g.site_name}</p>
                  <p className="text-sm text-slate-500">{g.from_date} to {g.to_date} · granted by {g.granted_by}</p>
                </div>
                <Badge className={active ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-slate-100 text-slate-500 border-slate-200'}>{active ? 'Active' : 'Expired'}</Badge>
                <button onClick={() => revoke(g.id)} className="text-red-500 p-2" data-testid={`visiting-revoke-${g.id}`}><Trash2 className="w-4 h-4" /></button>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
