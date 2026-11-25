import { useEffect, useState, useCallback } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Btn, Spinner, Empty, Badge, inputCls, Field, ROLE_LABEL } from '../ui';
import { Users, Plus, Loader2, Mail, KeyRound, X, Pencil, Power, Copy, Check, RefreshCw } from 'lucide-react';
import { CoverageBadge, EngineerCoverage, loginStatus } from './engineers/EngineerCoverage';
import DeactivateEngineerModal from './engineers/DeactivateEngineerModal';

const ROLE_OPTS = [
  { value: 'engineer', label: 'Engineer' },
  { value: 'lead', label: 'Lead Engineer' },
  { value: 'staff', label: 'MOD Operations (staff)' },
];

const emptyForm = () => ({
  full_name: '', email: '', phone: '', bfpo_role: 'engineer',
  password_mode: 'invite', temp_password: '',
  bfpo_territory_ids: [], bfpo_site_ids: [],
});

function ChipPick({ options, selected, onToggle, testid }) {
  return (
    <div className="flex flex-wrap gap-1.5" data-testid={testid}>
      {options.length === 0 && <span className="text-xs text-slate-400">None available</span>}
      {options.map((o) => {
        const on = selected.includes(o.id);
        return (
          <button type="button" key={o.id} onClick={() => onToggle(o.id)}
            data-testid={`${testid}-${o.id}`}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors ${on ? 'bg-cyan-600 text-white border-cyan-600' : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'}`}>
            {o.name}
          </button>
        );
      })}
    </div>
  );
}

function CopyLine({ value, label, testid }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1800); } catch { /* noop */ } };
  return (
    <div className="mt-2">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">{label}</p>
      <div className="flex items-center gap-2">
        <code className="flex-1 text-xs bg-slate-100 rounded-lg px-3 py-2 break-all" data-testid={`${testid}-value`}>{value}</code>
        <button onClick={copy} className="p-2 rounded-lg bg-slate-100 hover:bg-slate-200" data-testid={`${testid}-copy`}>
          {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4 text-slate-500" />}
        </button>
      </div>
    </div>
  );
}

export default function StaffEngineers() {
  const [members, setMembers] = useState([]);
  const [territories, setTerritories] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null); // { mode:'create'|'edit', form, id }
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [result, setResult] = useState(null); // { name, invite_url, temp_password }
  const [deact, setDeact] = useState(null); // { engineer, jobs }
  const [rowErr, setRowErr] = useState('');

  const load = useCallback(async () => {
    const [m, t, s] = await Promise.all([
      bfpo.get('/staff/team'), bfpo.get('/staff/territories'), bfpo.get('/sites'),
    ]);
    setMembers(m.data.members); setTerritories(t.data.territories); setSites(s.data.sites);
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => { setErr(''); setResult(null); setModal({ mode: 'create', form: emptyForm() }); };
  const openEdit = (m) => {
    setErr(''); setResult(null);
    setModal({ mode: 'edit', id: m.id, form: {
      full_name: m.full_name || '', email: m.email || '', phone: m.phone || '',
      bfpo_role: m.bfpo_role, password_mode: 'invite', temp_password: '',
      // Dangling references (deleted territory/site) are dropped here so a save corrects them.
      bfpo_territory_ids: (m.bfpo_territory_ids || []).filter((id) => territories.some((t) => t.id === id)),
      bfpo_site_ids: (m.bfpo_site_ids || []).filter((id) => sites.some((x) => x.id === id)),
    }, original: { t: m.bfpo_territory_ids || [], s: m.bfpo_site_ids || [] } });
  };
  const setF = (patch) => setModal((mo) => ({ ...mo, form: { ...mo.form, ...patch } }));
  const toggle = (key, id) => setModal((mo) => {
    const arr = mo.form[key];
    return { ...mo, form: { ...mo.form, [key]: arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id] } };
  });

  const submit = async () => {
    setBusy(true); setErr('');
    const f = modal.form;
    try {
      if (modal.mode === 'create') {
        const body = {
          full_name: f.full_name, email: f.email, phone: f.phone, bfpo_role: f.bfpo_role,
          password_mode: f.password_mode, temp_password: f.temp_password,
          bfpo_territory_ids: f.bfpo_role === 'staff' ? [] : f.bfpo_territory_ids,
          bfpo_site_ids: f.bfpo_role === 'staff' ? [] : f.bfpo_site_ids,
        };
        const r = await bfpo.post('/staff/engineers', body);
        setResult({ name: r.data.member.full_name, invite_url: r.data.invite_url, temp_password: r.data.temp_password });
        setModal(null);
      } else {
        const t = f.bfpo_role === 'staff' ? [] : f.bfpo_territory_ids;
        const sIds = f.bfpo_role === 'staff' ? [] : f.bfpo_site_ids;
        const same = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
        await bfpo.patch(`/staff/engineers/${modal.id}`, {
          full_name: f.full_name, phone: f.phone, bfpo_role: f.bfpo_role,
          ...(same(t, modal.original.t) && same(sIds, modal.original.s) ? {} : { bfpo_territory_ids: t, bfpo_site_ids: sIds }),
        });
        setModal(null);
      }
      await load();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setErr(typeof d === 'string' ? d : d?.message || 'Something went wrong');
    } finally { setBusy(false); }
  };

  const resend = async (m) => {
    setRowErr('');
    try {
      const r = await bfpo.post(`/staff/engineers/${m.id}/resend-invite`);
      setResult({ name: m.full_name, invite_url: r.data.invite_url, temp_password: null });
      load();
    } catch (e) { setRowErr(e?.response?.data?.detail || 'Could not resend the invite'); }
  };
  const toggleActive = async (m) => {
    setRowErr('');
    if (m.is_active) {
      const r = await bfpo.get(`/staff/engineers/${m.id}/open-jobs`);
      if (r.data.jobs.length) { setDeact({ engineer: m, jobs: r.data.jobs }); return; }
      if (!window.confirm(`Deactivate ${m.full_name}? They will be signed out and cannot sign in.`)) return;
    }
    try { await bfpo.post(`/staff/engineers/${m.id}/status`, { active: !m.is_active }); load(); } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.code === 'open_jobs') setDeact({ engineer: m, jobs: d.jobs }); else setRowErr(typeof d === 'string' ? d : 'Could not change status');
    }
  };

  if (loading) return <Spinner />;
  const terrOpts = territories.map((t) => ({ id: t.id, name: t.name }));
  const terrName = Object.fromEntries(territories.map((t) => [t.id, t.name]));
  const siteOpts = sites.map((s) => ({ id: s.id, name: `${s.name}${s.kind === 'mod_site' ? ' (MOD establishment)' : s.territory_id ? ` · ${terrName[s.territory_id] || ''}` : ''}` }));

  return (
    <div className="p-6 max-w-5xl mx-auto" data-testid="staff-engineers">
      <div className="flex items-start justify-end gap-3 mb-5">
        <Btn variant="primary" onClick={openCreate} data-testid="add-engineer-btn"><Plus className="w-4 h-4" /> Invite engineer</Btn>
      </div>

      {result && (
        <Card className="p-4 mb-5 border-emerald-200 bg-emerald-50/40" data-testid="engineer-result">
          <div className="flex items-start justify-between">
            <p className="font-semibold text-slate-900">{result.name} is set up.</p>
            <button onClick={() => setResult(null)} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-4 h-4" /></button>
          </div>
          {result.invite_url && <>
            <p className="text-sm text-slate-600 mt-1">An email with a set-password link has been sent. You can also share this link directly:</p>
            <CopyLine value={result.invite_url} label="Invite link" testid="invite-link" />
          </>}
          {result.temp_password && <>
            <p className="text-sm text-slate-600 mt-1">Share this temporary password securely — they'll be asked to change it on first sign-in.</p>
            <CopyLine value={result.temp_password} label="Temporary password" testid="temp-pw" />
          </>}
        </Card>
      )}

      {rowErr && <p className="text-sm text-red-600 mb-3" data-testid="engineer-row-error">{rowErr}</p>}
      {members.length === 0 ? <Empty icon={Users} title="No engineers yet" sub="Invite your first engineer to get started." testid="engineers-empty" /> : (
        <div className="space-y-2">
          {members.map((m) => {
            const [loginLabel, loginCls] = loginStatus(m);
            return (
              <Card key={m.id} className="p-4" data-testid={`engineer-row-${m.id}`}>
                <div className="flex items-start gap-3 flex-wrap">
                  <div className="flex-1 min-w-[200px]">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-slate-900">{m.full_name}</p>
                      <Badge className="bg-slate-100 text-slate-600 border-slate-200">{ROLE_LABEL[m.bfpo_role] || m.bfpo_role}</Badge>
                      <Badge className={loginCls} data-testid={`engineer-login-${m.id}`}>{loginLabel}</Badge>
                      {m.bfpo_role !== 'staff' && <CoverageBadge coverage={m.coverage} testid={`engineer-coverage-status-${m.id}`} />}
                    </div>
                    <p className="text-sm text-slate-500 mt-0.5">{m.email}{m.phone ? ` · ${m.phone}` : ''}</p>
                    {m.bfpo_role !== 'staff' && <EngineerCoverage m={m} />}
                  </div>
                  <div className="flex items-center gap-1">
                    {m.is_active && (
                      <button onClick={() => resend(m)} title="Resend invite" aria-label={`Resend invite to ${m.full_name}`} className="p-2 rounded-lg hover:bg-slate-100 text-slate-500" data-testid={`engineer-resend-${m.id}`}><RefreshCw className="w-4 h-4" /></button>
                    )}
                    <button onClick={() => openEdit(m)} title="Edit details and coverage" aria-label={`Edit ${m.full_name}`} className="p-2 rounded-lg hover:bg-slate-100 text-slate-500" data-testid={`engineer-edit-${m.id}`}><Pencil className="w-4 h-4" /></button>
                    <button onClick={() => toggleActive(m)} title={m.is_active ? 'Deactivate' : 'Reactivate'} aria-label={`${m.is_active ? 'Deactivate' : 'Reactivate'} ${m.full_name}`} className={`p-2 rounded-lg hover:bg-slate-100 ${m.is_active ? 'text-red-500' : 'text-emerald-600'}`} data-testid={`engineer-toggle-${m.id}`}><Power className="w-4 h-4" /></button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {deact && <DeactivateEngineerModal engineer={deact.engineer} jobs={deact.jobs} engineers={members}
        onClose={() => setDeact(null)} onDone={() => { setDeact(null); load(); }} />}
      {modal && (
        <div className="fixed inset-0 z-[60] bg-black/40 flex items-center justify-center p-4" data-testid="engineer-modal" onMouseDown={() => setModal(null)}>
          <div className="bg-white rounded-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto" onMouseDown={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-slate-900">{modal.mode === 'create' ? 'Invite engineer' : 'Edit engineer'}</h2>
              <button onClick={() => setModal(null)} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <Field label="Full name"><input className={inputCls} value={modal.form.full_name} onChange={(e) => setF({ full_name: e.target.value })} data-testid="eng-form-name" /></Field>
              <Field label="Email"><input type="email" className={inputCls} value={modal.form.email} disabled={modal.mode === 'edit'} onChange={(e) => setF({ email: e.target.value })} data-testid="eng-form-email" /></Field>
              <Field label="Phone number"><input className={inputCls} value={modal.form.phone} onChange={(e) => setF({ phone: e.target.value })} data-testid="eng-form-phone" /></Field>
              <Field label="Role">
                <select className={inputCls} value={modal.form.bfpo_role} onChange={(e) => setF({ bfpo_role: e.target.value })} data-testid="eng-form-role">
                  {ROLE_OPTS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </Field>

              {modal.form.bfpo_role !== 'staff' && <>
                <Field label="Territories" hint="Engineers see jobs across their assigned territories."><ChipPick options={terrOpts} selected={modal.form.bfpo_territory_ids} onToggle={(id) => toggle('bfpo_territory_ids', id)} testid="eng-form-territory" /></Field>
                <Field label="Allocated sites" hint="Specific sites this engineer is responsible for (optional)."><ChipPick options={siteOpts} selected={modal.form.bfpo_site_ids} onToggle={(id) => toggle('bfpo_site_ids', id)} testid="eng-form-site" /></Field>
              </>}

              {modal.mode === 'create' && <>
                <Field label="How should they get their password?">
                  <div className="flex flex-col gap-2">
                    <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                      <input type="radio" name="pwmode" checked={modal.form.password_mode === 'invite'} onChange={() => setF({ password_mode: 'invite' })} data-testid="eng-form-mode-invite" />
                      <Mail className="w-4 h-4 text-slate-400" /> Email a set-password link (recommended)
                    </label>
                    <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                      <input type="radio" name="pwmode" checked={modal.form.password_mode === 'temp'} onChange={() => setF({ password_mode: 'temp' })} data-testid="eng-form-mode-temp" />
                      <KeyRound className="w-4 h-4 text-slate-400" /> Set a temporary password (forced change on first login)
                    </label>
                  </div>
                </Field>
                {modal.form.password_mode === 'temp' && (
                  <Field label="Temporary password" hint="Leave blank to auto-generate one."><input className={inputCls} value={modal.form.temp_password} onChange={(e) => setF({ temp_password: e.target.value })} data-testid="eng-form-temp-pw" /></Field>
                )}
              </>}

              {err && <p className="text-sm text-red-600" data-testid="eng-form-error">{err}</p>}
              <Btn variant="primary" full disabled={busy || !modal.form.full_name || (modal.mode === 'create' && !modal.form.email)} onClick={submit} data-testid="eng-form-submit">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : (modal.mode === 'create' ? <Plus className="w-4 h-4" /> : <Check className="w-4 h-4" />)}
                {modal.mode === 'create' ? 'Create & send invite' : 'Save changes'}
              </Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
