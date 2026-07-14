import { useEffect, useState, useCallback } from 'react';
import { Plus, Search, Building2, ArrowLeft, MapPin, Boxes, Package, KeyRound } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { StatCard, Spinner, Modal, Field, input, money, StatusBadge } from './shared';

function DealerDetail({ dealerId, onBack }) {
  const [data, setData] = useState(null);
  const [users, setUsers] = useState([]);
  const [modal, setModal] = useState(false);
  const [uform, setUform] = useState({ email: '', full_name: '' });
  const [tempPw, setTempPw] = useState(null);
  const loadUsers = useCallback(() => { dpApi.listDealerUsers(dealerId).then((d) => setUsers(d.users || [])); }, [dealerId]);
  useEffect(() => { dpApi.getDealer(dealerId).then(setData); loadUsers(); }, [dealerId, loadUsers]);
  const createLogin = async () => {
    if (!uform.email.trim()) { notify.error('Email required'); return; }
    try {
      const r = await dpApi.createDealerUser(dealerId, uform);
      setTempPw({ email: r.email, password: r.temp_password });
      setUform({ email: '', full_name: '' }); loadUsers();
      notify.success('Dealer login created');
    } catch (e) { notify.error(e?.response?.data?.detail || 'Failed to create login'); }
  };
  if (!data) return <Spinner />;
  const d = data.dealer; const r = data.rollup;
  return (
    <div className="space-y-5" data-testid="dp-dealer-detail">
      <button onClick={onBack} data-testid="dp-dealer-back" className="text-sm text-slate-500 hover:text-slate-800 inline-flex items-center gap-1">
        <ArrowLeft size={14} /> Back to dealers
      </button>
      <div className="flex items-start gap-3">
        <div className="w-11 h-11 rounded-xl bg-[var(--gx-brand-from)]/10 flex items-center justify-center"><Building2 className="text-[var(--gx-brand-from)]" size={20} /></div>
        <div>
          <h2 className="text-xl font-bold text-slate-900">{d.name}</h2>
          <p className="text-sm text-slate-400">{[d.country, d.region].filter(Boolean).join(' · ')} · {d.default_percentage ?? '—'}% spare parts allowance</p>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Allowance total" value={money(r.allowance_total)} tone="brand" />
        <StatCard label="Approved parts" value={money(r.approved_value)} />
        <StatCard label="Allowance remaining" value={money(r.allowance_remaining)} tone="emerald" />
        <StatCard label="Stock value" value={money(r.stock_value)} />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><MapPin size={15} /> Remote stores ({data.stores.length})</h3>
        {data.stores.length === 0 && <p className="text-sm text-slate-400">No remote stores yet.</p>}
        <div className="grid sm:grid-cols-2 gap-2">
          {data.stores.map((s) => (
            <div key={s.id} className="border border-slate-100 rounded-lg p-3 text-sm">
              <div className="font-medium text-slate-800">{s.name}</div>
              <div className="text-xs text-slate-400 capitalize">{s.store_type} · {[s.country, s.region].filter(Boolean).join(', ')}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><Boxes size={15} /> Current stock ({data.stock.length} lines)</h3>
        {data.stock.length === 0 && <p className="text-sm text-slate-400">No stock held yet.</p>}
        {data.stock.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                <th className="py-2">Part</th><th>On hand</th><th>In transit</th><th className="text-right">Value</th>
              </tr></thead>
              <tbody>
                {data.stock.map((s) => (
                  <tr key={s.id} className="border-b border-slate-50">
                    <td className="py-2"><span className="font-mono text-xs text-slate-500">{s.part_sku}</span> {s.part_name}</td>
                    <td className="tabular-nums">{s.qty_on_hand}</td>
                    <td className="tabular-nums text-slate-400">{s.qty_in_transit || 0}</td>
                    <td className="text-right tabular-nums">{money((s.qty_on_hand || 0) * (s.unit_value || 0))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="dp-dealer-logins">
        <div className="flex items-center mb-3">
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2"><KeyRound size={15} /> Dealer portal logins ({users.length})</h3>
          <button data-testid="dp-create-login-btn" onClick={() => { setModal(true); setTempPw(null); }} className="ml-auto text-xs font-semibold text-[var(--gx-brand-from)]">+ Create login</button>
        </div>
        {users.length === 0 ? <p className="text-sm text-slate-400">No portal logins yet — create one so this dealer can access their own store.</p> : (
          <div className="space-y-1.5">
            {users.map((u) => (
              <div key={u.id} className="flex items-center justify-between text-sm py-1 border-b border-slate-50 last:border-0">
                <span className="text-slate-700">{u.email}</span>
                <span className="text-xs text-slate-400">{u.must_change_password ? 'Awaiting first login' : 'Active'}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><Package size={15} /> Allocations ({data.allocations.length})</h3>
        {data.allocations.length === 0 && <p className="text-sm text-slate-400">No allocations yet.</p>}
        <div className="space-y-2">
          {data.allocations.map((a) => (
            <div key={a.id} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-50 last:border-0">
              <span className="text-slate-600">{money(a.recommended_value)} · {(a.items || []).length} parts</span>
              <StatusBadge status={a.status} />
            </div>
          ))}
        </div>
      </div>

      <Modal open={modal} onClose={() => setModal(false)} title="Create dealer portal login" testid="dp-login-modal"
        footer={tempPw ? <button onClick={() => setModal(false)} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Done</button> : <>
          <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-login-save" onClick={createLogin} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Create login</button>
        </>}>
        {tempPw ? (
          <div className="space-y-2" data-testid="dp-login-temp">
            <p className="text-sm text-slate-600">Login created for <strong>{tempPw.email}</strong>. Share this temporary password securely — they'll be asked to change it on first login.</p>
            <div className="font-mono text-sm bg-slate-100 rounded-lg px-3 py-2 select-all">{tempPw.password}</div>
          </div>
        ) : (
          <>
            <Field label="Email *"><input data-testid="dp-login-email" className={input} value={uform.email} onChange={(e) => setUform({ ...uform, email: e.target.value })} placeholder="portal@dealer.com" /></Field>
            <Field label="Contact name"><input className={input} value={uform.full_name} onChange={(e) => setUform({ ...uform, full_name: e.target.value })} /></Field>
            <p className="text-xs text-slate-400">A temporary password will be generated. The dealer sees only their own store.</p>
          </>
        )}
      </Modal>
    </div>
  );
}

export default function DealersTab() {
  const [dealers, setDealers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [selected, setSelected] = useState(null);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ name: '', country: '', region: '', currency: 'GBP', default_percentage: '', account_manager: '' });

  const load = useCallback(() => {
    setLoading(true);
    dpApi.listDealers({ search: q }).then((d) => setDealers(d.dealers || [])).finally(() => setLoading(false));
  }, [q]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.name.trim()) { notify.error('Dealer name required'); return; }
    try {
      await dpApi.createDealer({ ...form, default_percentage: form.default_percentage === '' ? null : Number(form.default_percentage) });
      notify.success('Dealer added');
      setModal(false); setForm({ name: '', country: '', region: '', currency: 'GBP', default_percentage: '', account_manager: '' });
      load();
    } catch { notify.error('Failed to save dealer'); }
  };

  if (selected) return <DealerDetail dealerId={selected} onBack={() => { setSelected(null); load(); }} />;

  return (
    <div className="space-y-4" data-testid="dp-dealers-tab">
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-xs">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input data-testid="dp-dealer-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search dealers…" className={`${input} pl-9`} />
        </div>
        <button data-testid="dp-add-dealer-btn" onClick={() => setModal(true)} className="ml-auto inline-flex items-center gap-1.5 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg hover:opacity-90">
          <Plus size={15} /> Add dealer
        </button>
      </div>

      {loading ? <Spinner /> : dealers.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No dealers yet. Add your first international dealer.</div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {dealers.map((d) => (
            <button key={d.id} data-testid={`dp-dealer-card-${d.id}`} onClick={() => setSelected(d.id)} className="text-left rounded-xl border border-slate-200 bg-white p-4 hover:shadow-md hover:border-[var(--gx-brand-from)]/40 transition-all">
              <div className="flex items-center gap-2 mb-1">
                <Building2 size={16} className="text-[var(--gx-brand-from)]" />
                <span className="font-semibold text-slate-900 truncate">{d.name}</span>
              </div>
              <div className="text-xs text-slate-400">{[d.country, d.region].filter(Boolean).join(' · ') || 'No location'}</div>
              <div className="text-xs text-slate-500 mt-2">{d.default_percentage ?? '—'}% allowance · {d.currency}</div>
            </button>
          ))}
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="Add dealer" testid="dp-dealer-modal"
        footer={<>
          <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-dealer-save" onClick={save} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Save dealer</button>
        </>}>
        <Field label="Dealer name *"><input data-testid="dp-dealer-name" className={input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Country"><input className={input} value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} /></Field>
          <Field label="Region"><input className={input} value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Currency"><input className={input} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></Field>
          <Field label="Spare parts %"><input type="number" step="0.1" className={input} value={form.default_percentage} onChange={(e) => setForm({ ...form, default_percentage: e.target.value })} placeholder="2.5" /></Field>
        </div>
        <Field label="Account manager"><input className={input} value={form.account_manager} onChange={(e) => setForm({ ...form, account_manager: e.target.value })} /></Field>
      </Modal>
    </div>
  );
}
