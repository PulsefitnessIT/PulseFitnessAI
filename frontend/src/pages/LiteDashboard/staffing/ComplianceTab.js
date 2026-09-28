import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  ShieldCheck, IdCard, Receipt, RefreshCw, Loader2, AlertTriangle,
  CheckCircle2, Clock, HelpCircle,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PILL = {
  expired:   { cls: 'bg-rose-100 text-rose-700 border-rose-200',       label: 'Expired' },
  expiring:  { cls: 'bg-amber-100 text-amber-700 border-amber-200',    label: 'Expiring' },
  missing:   { cls: 'bg-slate-100 text-slate-600 border-slate-200',    label: 'Not on file' },
  ok:        { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200', label: 'Valid' },
  attention: { cls: 'bg-rose-100 text-rose-700 border-rose-200',       label: 'Check needed' },
};

function StatusPill({ status, children, testid }) {
  const p = PILL[status] || PILL.missing;
  return (
    <span data-testid={testid}
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${p.cls}`}>
      {children || p.label}
    </span>
  );
}

function SummaryCard({ testid, icon: Icon, tint, title, urgent, urgentLabel, breakdown }) {
  const clear = urgent === 0;
  return (
    <div data-testid={testid}
      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl"
          style={{ background: `${tint}1f`, color: tint }}>
          <Icon size={22} />
        </div>
        <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold ${clear ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
          {clear ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
          {clear ? 'All clear' : `${urgent} ${urgentLabel}`}
        </span>
      </div>
      <h3 className="mt-4 text-base font-bold text-slate-800">{title}</h3>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-500">
        {breakdown.map((b) => (
          <span key={b.label}><span className="font-bold text-slate-700">{b.value}</span> {b.label}</span>
        ))}
      </div>
    </div>
  );
}

function SectionCard({ title, icon: Icon, count, children }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-slate-100 px-5 py-3.5">
        <Icon size={18} className="text-slate-400" />
        <h3 className="text-sm font-bold uppercase tracking-wide text-slate-700">{title}</h3>
        <span className="ml-auto text-xs font-semibold text-slate-400">{count} to review</span>
      </div>
      <div className="divide-y divide-slate-100">{children}</div>
    </div>
  );
}

function EmptyRow({ text }) {
  return (
    <div className="flex items-center gap-2 px-5 py-6 text-sm text-slate-400">
      <CheckCircle2 size={16} className="text-emerald-500" /> {text}
    </div>
  );
}

export default function ComplianceTab({ headers }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const { data } = await axios.get(`${API}/staffing/compliance`, { headers });
      setData(data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not load compliance data.');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-400" data-testid="compliance-loading">
        <Loader2 className="animate-spin" size={22} />
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-rose-700" data-testid="compliance-error">
        {error} <button onClick={load} className="ml-2 underline">Retry</button>
      </div>
    );
  }

  const s = data.summary;
  const dbsUrgent = s.dbs.expired + s.dbs.expiring + s.dbs.missing;
  const rtwUrgent = s.right_to_work.attention + s.right_to_work.missing;
  const dbsNeed = data.dbs.filter((r) => r.status !== 'ok');
  const rtwNeed = data.right_to_work.filter((r) => r.status !== 'ok');

  return (
    <div className="space-y-6" data-testid="compliance-tab">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-bold text-slate-800">
            <ShieldCheck size={22} className="text-cyan-600" /> Compliance at a glance
          </h2>
          <p className="mt-0.5 text-sm text-slate-500">
            DBS certificates, Right-to-Work checks and outstanding vehicle fines across {s.staff_count} staff.
          </p>
        </div>
        <button onClick={load} data-testid="compliance-refresh"
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50">
          {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />} Refresh
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SummaryCard testid="compliance-card-dbs" icon={IdCard} tint="#7c3aed"
          title="Enhanced DBS" urgent={dbsUrgent} urgentLabel="need action"
          breakdown={[
            { label: 'valid', value: s.dbs.ok },
            { label: 'expiring', value: s.dbs.expiring },
            { label: 'expired', value: s.dbs.expired },
            { label: 'not on file', value: s.dbs.missing },
          ]} />
        <SummaryCard testid="compliance-card-rtw" icon={ShieldCheck} tint="#0891b2"
          title="Right to Work" urgent={rtwUrgent} urgentLabel="need action"
          breakdown={[
            { label: 'verified', value: s.right_to_work.ok },
            { label: 'to check', value: s.right_to_work.attention },
            { label: 'not on file', value: s.right_to_work.missing },
          ]} />
        <SummaryCard testid="compliance-card-fines" icon={Receipt} tint="#e11d48"
          title="Outstanding Fines" urgent={s.fines.unpaid_count} urgentLabel="unpaid"
          breakdown={[
            { label: `unpaid (£${s.fines.unpaid_total.toFixed(2)})`, value: s.fines.unpaid_count },
            { label: '14+ days overdue', value: s.fines.overdue_count },
          ]} />
      </div>

      <SectionCard title="DBS — needs attention" icon={IdCard} count={dbsNeed.length}>
        {dbsNeed.length === 0 ? <EmptyRow text="Every DBS certificate on file is valid." /> :
          dbsNeed.map((r) => (
            <div key={r.staff_id} data-testid="compliance-dbs-row"
              className="flex items-center justify-between gap-3 px-5 py-3">
              <div className="min-w-0">
                <div className="truncate font-semibold text-slate-800">{r.name}</div>
                <div className="text-xs text-slate-400">
                  {r.expiry_date ? `Expires ${r.expiry_date}` : 'No DBS on file'}
                  {typeof r.days === 'number' && r.status === 'expiring' && ` · in ${r.days} day${r.days === 1 ? '' : 's'}`}
                  {typeof r.days === 'number' && r.status === 'expired' && ` · ${Math.abs(r.days)} day${Math.abs(r.days) === 1 ? '' : 's'} ago`}
                </div>
              </div>
              <StatusPill status={r.status} testid="compliance-dbs-status">
                {r.status === 'expiring' && <Clock size={12} />}
                {r.status === 'expired' && <AlertTriangle size={12} />}
                {r.status === 'missing' && <HelpCircle size={12} />}
                {PILL[r.status]?.label}
              </StatusPill>
            </div>
          ))}
      </SectionCard>

      <SectionCard title="Right to Work — needs attention" icon={ShieldCheck} count={rtwNeed.length}>
        {rtwNeed.length === 0 ? <EmptyRow text="Every Right-to-Work check is verified." /> :
          rtwNeed.map((r) => (
            <div key={r.staff_id} data-testid="compliance-rtw-row"
              className="flex items-center justify-between gap-3 px-5 py-3">
              <div className="min-w-0">
                <div className="truncate font-semibold text-slate-800">{r.name}</div>
                <div className="text-xs text-slate-400">{r.raw_status ? `Status: ${r.raw_status}` : 'No status recorded'}</div>
              </div>
              <StatusPill status={r.status} testid="compliance-rtw-status" />
            </div>
          ))}
      </SectionCard>

      <SectionCard title="Outstanding vehicle fines" icon={Receipt} count={data.fines.length}>
        {data.fines.length === 0 ? <EmptyRow text="No unpaid fines across the fleet." /> :
          data.fines.map((f, i) => (
            <div key={`${f.vehicle_id}-${i}`} data-testid="compliance-fine-row"
              className="flex items-center justify-between gap-3 px-5 py-3">
              <div className="min-w-0">
                <div className="truncate font-semibold text-slate-800">
                  {f.reg_no} <span className="font-normal text-slate-400">{f.vehicle ? `· ${f.vehicle}` : ''}</span>
                </div>
                <div className="text-xs text-slate-400">
                  {f.kind || 'Fine'}{f.date ? ` · ${f.date}` : ''}
                  {typeof f.age_days === 'number' && ` · ${f.age_days} day${f.age_days === 1 ? '' : 's'} outstanding`}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-slate-800">£{f.value.toFixed(2)}</span>
                {f.overdue && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-100 px-2.5 py-0.5 text-xs font-semibold text-rose-700">
                    <AlertTriangle size={12} /> Overdue
                  </span>
                )}
              </div>
            </div>
          ))}
      </SectionCard>
    </div>
  );
}
