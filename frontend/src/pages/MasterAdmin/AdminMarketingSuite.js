/**
 * Master Admin — Marketing Suite
 * Two sub-tabs: Plans (editor) + Analytics (platform KPIs).
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useBrandContext } from './BrandContext';
import { Edit2, Save, Loader2, PoundSterling, Mail, ImagePlus, Workflow, Users, Plus, Trash2, X } from 'lucide-react';
import { notify, useConfirm } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const SUB_TABS = [
 { id: 'analytics', label: 'Analytics' },
 { id: 'campaigns', label: 'Campaigns & Journeys' },
 { id: 'plans', label: 'Plans' },
 { id: 'subscriptions', label: 'Subscriptions' },
];

const PlansEditor = ({ API, headers }) => {
 const [plans, setPlans] = useState([]);
 const [editing, setEditing] = useState(null);
 const [busy, setBusy] = useState(false);

 const load = () => axios.get(`${API}/master-admin/marketing/plans`, { headers }).then((r) => setPlans(r.data.plans));
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
 useEffect(() => { load();   }, []);

 const save = async () => {
 setBusy(true);
 try {
 await axios.put(`${API}/master-admin/marketing/plans/${editing.id}`, {
 name: editing.name,
 monthly_price_gbp: parseFloat(editing.monthly_price_gbp) || 0,
 annual_price_gbp: parseFloat(editing.annual_price_gbp) || 0,
 limits: editing.limits, features: editing.features, active: editing.active,
 }, { headers });
 setEditing(null); load();
 } finally { setBusy(false); }
 };

 return (
 <div className="space-y-3" data-testid="admin-marketing-plans">
 {plans.map((p) => (
 <div key={p.id} className="rounded-xl border border-zinc-200 bg-white p-4" data-testid={`plan-card-${p.id}`}>
 <div className="flex items-start justify-between">
 <div>
 <p className="font-bold text-zinc-900">{p.name} <span className="text-zinc-400 text-xs font-normal">({p.id})</span></p>
 <p className="text-2xl font-bold mt-1 text-[var(--color-brand-blue)]">£{p.monthly_price_gbp}<span className="text-zinc-400 text-sm font-normal">/mo</span></p>
 <p className="text-[11px] text-zinc-400 mt-1">£{p.annual_price_gbp}/yr</p>
 </div>
 <button onClick={() => setEditing({ ...p })} className="text-xs inline-flex items-center gap-1 text-zinc-500 hover:text-zinc-900" data-testid={`plan-edit-${p.id}`}>
 <Edit2 size={11} /> Edit
 </button>
 </div>
 <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 text-[11px]">
 <p>{p.limits.contacts.toLocaleString()} contacts</p>
 <p>{p.limits.monthly_emails.toLocaleString()} emails/mo</p>
 <p>{p.limits.ai_generations.toLocaleString()} AI gens/mo</p>
 <p>{p.limits.social_accounts} social accts</p>
 </div>
 </div>
 ))}

 {editing && (
 <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-6" onClick={() => setEditing(null)}>
 <div className="bg-white rounded-xl p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto space-y-3" onClick={(e) => e.stopPropagation()} data-testid="plan-edit-modal">
 <p className="font-bold text-lg">Edit {editing.id}</p>
 <label className="block text-xs">Name <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} className="w-full mt-1 px-2 py-1.5 border rounded text-sm" /></label>
 <label className="block text-xs">Monthly £ <input type="number" value={editing.monthly_price_gbp} onChange={(e) => setEditing({ ...editing, monthly_price_gbp: e.target.value })} className="w-full mt-1 px-2 py-1.5 border rounded text-sm" data-testid="plan-edit-monthly" /></label>
 <label className="block text-xs">Annual £ <input type="number" value={editing.annual_price_gbp} onChange={(e) => setEditing({ ...editing, annual_price_gbp: e.target.value })} className="w-full mt-1 px-2 py-1.5 border rounded text-sm" /></label>
 <p className="text-xs font-semibold mt-3">Limits</p>
 {Object.keys(editing.limits).map((k) => (
 <label key={k} className="block text-xs">{k}
 <input type="number" value={editing.limits[k]} onChange={(e) => setEditing({ ...editing, limits: { ...editing.limits, [k]: parseInt(e.target.value, 10) || 0 } })} className="w-full mt-1 px-2 py-1.5 border rounded text-sm" />
 </label>
 ))}
 <p className="text-xs font-semibold mt-3">Features</p>
 {Object.keys(editing.features).map((k) => (
 <label key={k} className="flex items-center gap-2 text-xs">
 <input type="checkbox" checked={editing.features[k]} onChange={(e) => setEditing({ ...editing, features: { ...editing.features, [k]: e.target.checked } })} />
 {k}
 </label>
 ))}
 <div className="flex gap-2 pt-3">
 <button onClick={save} disabled={busy} className="flex-1 px-3 py-2 bg-[var(--color-brand-blue)] text-white text-sm rounded font-semibold inline-flex items-center justify-center gap-1.5" data-testid="plan-save-btn">
 {busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save
 </button>
 <button onClick={() => setEditing(null)} className="flex-1 px-3 py-2 border border-zinc-200 text-sm rounded font-semibold">Cancel</button>
 </div>
 </div>
 </div>
 )}
 </div>
 );
};

const Tile = ({ label, value, accent = 'text-zinc-900', icon: Icon, sub, onClick }) => (
 <div
   className={`rounded-xl border border-zinc-200 bg-white p-4 ${onClick ? 'cursor-pointer transition-all hover:-translate-y-0.5 hover:shadow-md hover:border-zinc-300' : ''}`}
   onClick={onClick}
   role={onClick ? 'button' : undefined}
   tabIndex={onClick ? 0 : undefined}
   onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } } : undefined}
   data-testid={`mkt-tile-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
 >
 <p className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold flex items-center gap-1">{Icon && <Icon size={11} />} {label}</p>
 <p className={`text-2xl font-bold mt-1 ${accent}`}>{value}</p>
 {sub && <p className="text-[11px] text-zinc-400 mt-1">{sub}</p>}
 </div>
);

const Analytics = ({ API, headers, onNavTab, onGoSection, onGoAiUsage }) => {
  const { brand } = useBrandContext();
  const [data, setData] = useState(null);
  useEffect(() => {
    // Iter 216h25 — pass top-bar BrandPicker to the analytics endpoint.
    const qs = brand && brand !== 'all' ? `?brand=${encodeURIComponent(brand)}` : '';
    axios.get(`${API}/master-admin/marketing/analytics${qs}`, { headers }).then((r) => setData(r.data)).catch(() => setData({}));
    // eslint-disable-next-line
  }, [brand]);
 if (!data) return <div className="flex items-center gap-2 text-zinc-400 py-8"><Loader2 className="animate-spin" size={14} /> Loading…</div>;
 return (
 <div className="space-y-4" data-testid="admin-marketing-analytics">
 <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
 {/* Iter 233b — KPI tiles navigate to the view holding the detail they
     summarise (Subscriptions tab, platform Emails log, AI Usage tab).
     Iter 235 — Campaigns / journeys now deep-link to the read-only
     cross-org Campaigns & Journeys browser. */}
 <Tile label="MRR (gross)" value={`£${(data.mrr_gbp || 0).toLocaleString()}`} accent="text-emerald-700" icon={PoundSterling} onClick={() => onNavTab?.('subscriptions')} />
 <Tile label="Subscriptions" value={data.total_subscriptions || 0} icon={Users} onClick={() => onNavTab?.('subscriptions')} />
 <Tile label="Emails (30d)" value={(data.emails_30d || 0).toLocaleString()} icon={Mail} onClick={() => onGoSection?.('emails')} />
 <Tile label="AI gens (30d)" value={(data.ai_generations_30d || 0).toLocaleString()} icon={ImagePlus} onClick={onGoAiUsage} />
 <Tile label="Campaigns (30d)" value={data.campaigns_30d || 0} icon={Mail} onClick={() => onNavTab?.('campaigns')} />
 <Tile label="Active journeys" value={data.journeys_active || 0} icon={Workflow} onClick={() => onNavTab?.('campaigns')} />
 </div>

 <div className="rounded-xl border border-zinc-200 bg-white p-5">
 <p className="text-xs font-semibold text-zinc-700 mb-3 uppercase tracking-wider">By plan</p>
 <div className="space-y-1.5">
 {Object.entries(data.by_plan || {}).map(([pid, count]) => (
 <div key={pid} className="flex items-center justify-between text-sm">
 <span className="capitalize">{pid}</span>
 <span className="font-semibold">{count}</span>
 </div>
 ))}
 {!Object.keys(data.by_plan || {}).length && <p className="text-xs text-zinc-400">No subscriptions yet.</p>}
 </div>
 </div>

 <div className="rounded-xl border border-zinc-200 bg-white p-5">
 <p className="text-xs font-semibold text-zinc-700 mb-3 uppercase tracking-wider">Top orgs by emails sent (30d)</p>
 {(data.top_orgs_by_email || []).length === 0 ? (
 <p className="text-xs text-zinc-400">No email activity yet.</p>
 ) : (
 <ul className="space-y-2">
 {data.top_orgs_by_email.map((r) => (
 <li key={r.organization_id} className="flex items-center justify-between text-sm">
 <span>{r.name}</span>
 <span className="font-semibold tabular-nums">{r.emails_30d.toLocaleString()}</span>
 </li>
 ))}
 </ul>
 )}
 </div>
 </div>
 );
};

const SubscriptionEditor = ({ API, headers, initial, plans, orgs, onClose, onSaved }) => {
 const isNew = !initial?.organization_id;
 const [form, setForm] = useState(() => ({
 organization_id: initial?.organization_id || '',
 plan_id: initial?.plan_id || (plans[0]?.id || 'pro'),
 status: initial?.status || 'active',
 comp_seats: !!initial?.comp_seats,
 trial_ends_at: initial?.trial_ends_at ? initial.trial_ends_at.slice(0, 10) : '',
 }));
 const [busy, setBusy] = useState(false);

 const submit = async () => {
 if (!form.organization_id) { notify.error('Pick an organisation'); return; }
 setBusy(true);
 try {
 const payload = {
 plan_id: form.plan_id,
 status: form.status,
 comp_seats: form.comp_seats,
 trial_ends_at: form.trial_ends_at ? new Date(form.trial_ends_at).toISOString() : null,
 };
 await axios.put(`${API}/master-admin/marketing/subscriptions/${form.organization_id}`, payload, { headers });
 notify.success(isNew ? 'Subscription created' : 'Subscription updated');
 onSaved();
 onClose();
 } catch (e) {
 notifyApiError(notify, e, 'Save failed');
 } finally { setBusy(false); }
 };

 return (
 <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-6" onClick={onClose}>
 <div className="bg-white rounded-xl p-6 max-w-md w-full space-y-3" onClick={(e) => e.stopPropagation()} data-testid="sub-edit-modal">
 <div className="flex items-center justify-between">
 <p className="font-bold text-lg">{isNew ? 'Add subscription' : 'Edit subscription'}</p>
 <button onClick={onClose} className="text-zinc-400 hover:text-zinc-700"><X size={18} /></button>
 </div>
 <label className="block text-xs font-semibold">Organisation
 <select
 value={form.organization_id}
 onChange={(e) => setForm({ ...form, organization_id: e.target.value })}
 disabled={!isNew}
 className="w-full mt-1 px-2 py-1.5 border rounded text-sm disabled:bg-zinc-100"
 data-testid="sub-edit-org"
 >
 <option value="">Select an organisation…</option>
 {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
 </select>
 </label>
 <label className="block text-xs font-semibold">Plan
 <select value={form.plan_id} onChange={(e) => setForm({ ...form, plan_id: e.target.value })} className="w-full mt-1 px-2 py-1.5 border rounded text-sm" data-testid="sub-edit-plan">
 {plans.map((p) => <option key={p.id} value={p.id}>{p.name} (£{p.monthly_price_gbp}/mo)</option>)}
 </select>
 </label>
 <label className="block text-xs font-semibold">Status
 <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className="w-full mt-1 px-2 py-1.5 border rounded text-sm" data-testid="sub-edit-status">
 <option value="active">active</option>
 <option value="trial">trial</option>
 <option value="past_due">past_due</option>
 <option value="cancelled">cancelled</option>
 </select>
 </label>
 <label className="block text-xs font-semibold">Trial ends (optional)
 <input type="date" value={form.trial_ends_at} onChange={(e) => setForm({ ...form, trial_ends_at: e.target.value })} className="w-full mt-1 px-2 py-1.5 border rounded text-sm" data-testid="sub-edit-trial-end" />
 </label>
 <label className="flex items-center gap-2 text-xs font-semibold">
 <input type="checkbox" checked={form.comp_seats} onChange={(e) => setForm({ ...form, comp_seats: e.target.checked })} data-testid="sub-edit-comp" />
 Comp seats (free, bypass billing)
 </label>
 <div className="flex gap-2 pt-2">
 <button onClick={submit} disabled={busy} className="flex-1 px-3 py-2 bg-[var(--color-brand-blue)] text-white text-sm rounded font-semibold inline-flex items-center justify-center gap-1.5" data-testid="sub-save-btn">
 {busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save
 </button>
 <button onClick={onClose} className="flex-1 px-3 py-2 border border-zinc-200 text-sm rounded font-semibold">Cancel</button>
 </div>
 </div>
 </div>
 );
};

const Subscriptions = ({ API, headers }) => {
 const confirm = useConfirm();
 const { brand } = useBrandContext();
 const [subs, setSubs] = useState(null);
 const [plans, setPlans] = useState([]);
 const [orgs, setOrgs] = useState([]);
 const [editing, setEditing] = useState(null); // null=hidden, {} = new, {…sub} = edit

 const reload = useCallback(() => {
   const qs = brand && brand !== 'all' ? `?brand=${encodeURIComponent(brand)}` : '';
   return axios.get(`${API}/master-admin/marketing/subscriptions${qs}`, { headers })
     .then((r) => setSubs(r.data.subscriptions))
     .catch(() => setSubs([]));
 }, [API, headers, brand]);

 useEffect(() => {
 reload();
 axios.get(`${API}/master-admin/marketing/plans`, { headers }).then((r) => setPlans(r.data.plans)).catch(() => {});
 const orgQs = brand && brand !== 'all' ? `?brand=${encodeURIComponent(brand)}` : '';
 axios.get(`${API}/master-admin/organizations${orgQs}`, { headers }).then((r) => setOrgs(r.data.organizations || [])).catch(() => {});
 // eslint-disable-next-line
 }, [brand]);

 const remove = async (orgId, orgName) => {
 const ok = await confirm({
 title: `Remove the marketing subscription for ${orgName}?`,
 detail: 'They will lose Marketing Suite access immediately.',
 tone: 'danger',
 confirmLabel: 'Remove',
 });
 if (!ok) return;
 try {
 await axios.delete(`${API}/master-admin/marketing/subscriptions/${orgId}`, { headers });
 notify.success('Subscription removed');
 reload();
 } catch (e) {
 notifyApiError(notify, e, 'Remove failed');
 }
 };

 if (!subs) return <div className="flex items-center gap-2 text-zinc-400 py-8"><Loader2 className="animate-spin" size={14} /> Loading…</div>;

 // Orgs that don't yet have a subscription (used for the"Add" picker)
 const subscribedIds = new Set(subs.map((s) => s.organization_id));
 const unsubscribedOrgs = orgs.filter((o) => !subscribedIds.has(o.id));

 return (
 <div className="space-y-3" data-testid="admin-marketing-subs">
 <div className="flex items-center justify-between">
 <p className="text-xs text-zinc-500">{subs.length} active subscription{subs.length === 1 ? '' : 's'}</p>
 <button
 onClick={() => setEditing({})}
 className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded"
 data-testid="sub-add-btn"
 >
 <Plus size={13} /> Add subscription
 </button>
 </div>
 <div className="rounded-xl border border-zinc-200 bg-white overflow-x-auto">
 <table className="w-full text-sm">
 <thead className="border-b border-zinc-100 text-[10px] uppercase tracking-wider text-zinc-400">
 <tr>
 <th className="text-left py-2 px-4 font-semibold">Org</th>
 <th className="text-left font-semibold">Status</th>
 <th className="text-left font-semibold">Plan</th>
 <th className="text-left font-semibold">Trial / Period</th>
 <th className="font-semibold pr-4 text-right">Actions</th>
 </tr>
 </thead>
 <tbody>
 {subs.map((s) => (
 <tr key={s.organization_id} className="border-b border-zinc-50 last:border-b-0" data-testid={`sub-row-${s.organization_id}`}>
 <td className="py-3 px-4">
 <p className="font-medium text-zinc-900">{s.organization_name || '—'}</p>
 <p className="text-[10px] text-zinc-400 uppercase">{s.account_type || '—'}{s.comp_seats ? ' · COMP' : ''}</p>
 </td>
 <td><span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${s.status === 'active' ? 'bg-emerald-50 text-emerald-700' : s.status === 'trial' ? 'bg-amber-50 text-amber-700' : 'bg-zinc-100 text-zinc-600'}`}>{s.status}</span></td>
 <td>{plans.find((p) => p.id === s.plan_id)?.name || s.plan_id}</td>
 <td className="text-[11px] text-zinc-500">
 {s.trial_ends_at ? `Trial ends ${new Date(s.trial_ends_at).toLocaleDateString()}` : (s.current_period_end ? `Renews ${new Date(s.current_period_end).toLocaleDateString()}` : '—')}
 </td>
 <td className="pr-4 text-right space-x-2">
 <button onClick={() => setEditing(s)} className="text-xs inline-flex items-center gap-1 text-zinc-500 hover:text-[var(--color-brand-blue)]" data-testid={`sub-edit-${s.organization_id}`}>
 <Edit2 size={11} /> Edit
 </button>
 <button onClick={() => remove(s.organization_id, s.organization_name)} className="text-xs inline-flex items-center gap-1 text-zinc-500 hover:text-red-600" data-testid={`sub-remove-${s.organization_id}`}>
 <Trash2 size={11} /> Remove
 </button>
 </td>
 </tr>
 ))}
 </tbody>
 </table>
 {subs.length === 0 && <p className="p-5 text-sm text-zinc-400 text-center">No subscriptions yet — click <strong>Add subscription</strong> to provision the first one.</p>}
 </div>

 {editing !== null && (
 <SubscriptionEditor
 API={API}
 headers={headers}
 initial={editing.organization_id ? editing : null}
 plans={plans}
 orgs={editing.organization_id ? orgs : unsubscribedOrgs}
 onClose={() => setEditing(null)}
 onSaved={reload}
 />
 )}
 </div>
 );
};

const STATUS_BADGE = {
  sent: 'bg-emerald-50 text-emerald-700',
  active: 'bg-emerald-50 text-emerald-700',
  sending: 'bg-blue-50 text-blue-700',
  scheduled: 'bg-amber-50 text-amber-700',
  draft: 'bg-zinc-100 text-zinc-600',
  paused: 'bg-amber-50 text-amber-700',
  archived: 'bg-zinc-100 text-zinc-500',
};

const StatusPill = ({ status }) => (
  <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${STATUS_BADGE[status] || 'bg-zinc-100 text-zinc-600'}`}>{status || '—'}</span>
);

/* Iter 235 — read-only cross-org Campaigns & Journeys browser. */
const CampaignsJourneys = ({ API, headers }) => {
  const { brand } = useBrandContext();
  const [campaigns, setCampaigns] = useState(null);
  const [journeys, setJourneys] = useState(null);
  const [status, setStatus] = useState('all');

  useEffect(() => {
    const params = [];
    if (brand && brand !== 'all') params.push(`brand=${encodeURIComponent(brand)}`);
    if (status !== 'all') params.push(`status=${encodeURIComponent(status)}`);
    const qs = params.length ? `?${params.join('&')}` : '';
    axios.get(`${API}/master-admin/marketing/campaigns${qs}`, { headers }).then((r) => setCampaigns(r.data.campaigns)).catch(() => setCampaigns([]));
    axios.get(`${API}/master-admin/marketing/journeys${qs}`, { headers }).then((r) => setJourneys(r.data.journeys)).catch(() => setJourneys([]));
    // eslint-disable-next-line
  }, [brand, status]);

  if (!campaigns || !journeys) return <div className="flex items-center gap-2 text-zinc-400 py-8"><Loader2 className="animate-spin" size={14} /> Loading…</div>;

  const fmtDate = (d) => (d ? new Date(d).toLocaleDateString() : '—');
  const pct = (num, den) => (den ? `${Math.round((num / den) * 100)}%` : '—');

  return (
    <div className="space-y-5" data-testid="admin-marketing-campaigns">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-xs text-zinc-500">Read-only view of every tenant's campaigns and journeys. Edits happen inside the org's own Marketing Suite.</p>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-2 py-1.5 border border-zinc-200 rounded text-xs" data-testid="cj-status-filter">
          <option value="all">All statuses</option>
          <option value="draft">draft</option>
          <option value="scheduled">scheduled</option>
          <option value="sent">sent</option>
          <option value="active">active</option>
          <option value="paused">paused</option>
        </select>
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white overflow-x-auto">
        <p className="text-xs font-semibold text-zinc-700 uppercase tracking-wider px-4 pt-4 pb-2 flex items-center gap-1.5"><Mail size={12} /> Campaigns <span className="text-zinc-400 font-normal normal-case">({campaigns.length})</span></p>
        <table className="w-full text-sm">
          <thead className="border-b border-zinc-100 text-[10px] uppercase tracking-wider text-zinc-400">
            <tr>
              <th className="text-left py-2 px-4 font-semibold">Campaign</th>
              <th className="text-left font-semibold">Org</th>
              <th className="text-left font-semibold">Status</th>
              <th className="text-left font-semibold">Channel</th>
              <th className="text-right font-semibold">Sent</th>
              <th className="text-right font-semibold">Open rate</th>
              <th className="text-right font-semibold pr-4">Sent at</th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((c) => (
              <tr key={c.id} className="border-b border-zinc-50 last:border-b-0" data-testid={`cj-campaign-row-${c.id}`}>
                <td className="py-2.5 px-4">
                  <p className="font-medium text-zinc-900">{c.name}</p>
                  {c.ab_test?.enabled && <p className="text-[10px] text-violet-600 font-semibold">A/B test</p>}
                </td>
                <td className="text-zinc-600">{c.organization_name || '—'}</td>
                <td><StatusPill status={c.status} /></td>
                <td className="text-[11px] text-zinc-500 uppercase">{c.channel || '—'}</td>
                <td className="text-right tabular-nums">{(c.metrics?.sent || 0).toLocaleString()}</td>
                <td className="text-right tabular-nums">{pct(c.metrics?.opened || 0, c.metrics?.sent || 0)}</td>
                <td className="text-right text-[11px] text-zinc-500 pr-4">{fmtDate(c.sent_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {campaigns.length === 0 && <p className="p-5 text-sm text-zinc-400 text-center">No campaigns match this filter.</p>}
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white overflow-x-auto">
        <p className="text-xs font-semibold text-zinc-700 uppercase tracking-wider px-4 pt-4 pb-2 flex items-center gap-1.5"><Workflow size={12} /> Journeys <span className="text-zinc-400 font-normal normal-case">({journeys.length})</span></p>
        <table className="w-full text-sm">
          <thead className="border-b border-zinc-100 text-[10px] uppercase tracking-wider text-zinc-400">
            <tr>
              <th className="text-left py-2 px-4 font-semibold">Journey</th>
              <th className="text-left font-semibold">Org</th>
              <th className="text-left font-semibold">Status</th>
              <th className="text-left font-semibold">Trigger</th>
              <th className="text-right font-semibold">Steps</th>
              <th className="text-right font-semibold">Entered</th>
              <th className="text-right font-semibold pr-4">Converted</th>
            </tr>
          </thead>
          <tbody>
            {journeys.map((j) => (
              <tr key={j.id} className="border-b border-zinc-50 last:border-b-0" data-testid={`cj-journey-row-${j.id}`}>
                <td className="py-2.5 px-4 font-medium text-zinc-900">{j.name}</td>
                <td className="text-zinc-600">{j.organization_name || '—'}</td>
                <td><StatusPill status={j.status} /></td>
                <td className="text-[11px] text-zinc-500">{j.trigger?.event || '—'}</td>
                <td className="text-right tabular-nums">{j.node_count ?? 0}</td>
                <td className="text-right tabular-nums">{(j.metrics?.entered || 0).toLocaleString()}</td>
                <td className="text-right tabular-nums pr-4">{(j.metrics?.converted || 0).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {journeys.length === 0 && <p className="p-5 text-sm text-zinc-400 text-center">No journeys match this filter.</p>}
      </div>
    </div>
  );
};

const AdminMarketingSuite = ({ API, onGoSection, onGoAiUsage }) => {
 const [tab, setTab] = useState('analytics');
 const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };
 return (
 <div className="space-y-4" data-testid="admin-marketing-suite">
 <div className="flex gap-1 border-b border-zinc-200 -mt-2">
 {SUB_TABS.map((t) => (
 <button key={t.id} onClick={() => setTab(t.id)} className={`px-4 py-2.5 text-sm font-medium border-b-2 ${tab === t.id ? 'border-[var(--color-brand-blue)] text-[var(--color-brand-blue)]' : 'border-transparent text-zinc-500 hover:text-zinc-800'}`} data-testid={`admin-marketing-subtab-${t.id}`}>
 {t.label}
 </button>
 ))}
 </div>
 {tab === 'analytics' && <Analytics API={API} headers={headers} onNavTab={setTab} onGoSection={onGoSection} onGoAiUsage={onGoAiUsage} />}
 {tab === 'campaigns' && <CampaignsJourneys API={API} headers={headers} />}
 {tab === 'plans' && <PlansEditor API={API} headers={headers} />}
 {tab === 'subscriptions' && <Subscriptions API={API} headers={headers} />}
 </div>
 );
};

export default AdminMarketingSuite;
