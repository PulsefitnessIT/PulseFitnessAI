/**
 * Iter 216h24 — Staff Onboarding Wizard (P6).
 *
 * 5-step linear wizard for inviting a new internal staff member,
 * platform-wide admin, or org-scoped operator. Reuses the iter-216h15
 * reset-link flow — operator never sees the plaintext password; the
 * new user sets their own on first visit via a 72 h /reset-password
 * token.
 *
 * Steps:
 *   1. Identity       — full name + email + brand context (Pulse/GymAxis/All)
 *   2. Role & scope   — role + organisation (when role is org-scoped)
 *   3. Sites          — site lock (empty = all sites in the org)
 *   4. Modules        — per-module override toggles
 *   5. Review & invite — summary + creates user + surfaces 72 h reset link
 *
 * Lives at: Master Admin → People → "Onboard staff" sub-tab.
 *
 * Backend endpoints used:
 *   • POST /api/master-admin/pulse-admins                       (platform admins, no org)
 *   • POST /api/master-admin/organizations/{org_id}/users       (org-scoped users)
 *   • PUT  /api/master-admin/users/{user_id}/edit               (allowed_site_ids, module_overrides)
 *   • POST /api/master-admin/users/{user_id}/invite-link        (re-issue 72 h link if needed)
 */
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import axios from 'axios';
import {
  UserPlus, Mail, Briefcase, MapPin, Layers, ClipboardCheck,
  ArrowLeft, ArrowRight, Check, Copy, Link as LinkIcon, RefreshCw, AlertCircle,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STEPS = [
  { id: 'identity',  label: 'Identity',  icon: UserPlus,       hint: 'Name + email + brand' },
  { id: 'role',      label: 'Role',      icon: Briefcase,      hint: 'Permissions tier' },
  { id: 'sites',     label: 'Sites',     icon: MapPin,         hint: 'Optional site lock' },
  { id: 'modules',   label: 'Modules',   icon: Layers,         hint: 'Per-module overrides' },
  { id: 'review',    label: 'Review',    icon: ClipboardCheck, hint: 'Generate invite link' },
];

const ROLES = [
  // Platform-wide
  { id: 'master_admin',        group: 'Platform',     label: 'GymAxis Master Admin',  description: 'Full HQ access across every organisation and brand.', orgRequired: false },
  { id: 'pulse_master_admin',  group: 'Platform',     label: 'Pulse Master Admin',    description: 'Master Admin scope-locked to Pulse Fitness data only.', orgRequired: false },
  { id: 'service_desk',        group: 'Platform',     label: 'Service Desk',          description: 'Internal Pulse support team — cases + helpdesk only.', orgRequired: false },
  // Org-scoped
  { id: 'owner',               group: 'Customer org', label: 'Owner',                 description: 'Primary contact + full billing/admin authority within the org.', orgRequired: true },
  { id: 'manager',             group: 'Customer org', label: 'Manager',               description: 'Day-to-day operations lead within the org.', orgRequired: true },
  { id: 'staff',               group: 'Customer org', label: 'Staff',                 description: 'Floor / coach / receptionist — most internal users.', orgRequired: true },
  { id: 'instructor',          group: 'Customer org', label: 'Instructor',            description: 'Class instructor with timetable + member access.', orgRequired: true },
];

const MODULES = [
  { key: 'operations',   label: 'Operations Portal', description: 'Equipment, faults, check-sheets, CAPEX' },
  { key: 'memberships',  label: 'Memberships',        description: 'Members, plans, classes, timetable' },
  { key: 'marketing',    label: 'Marketing Suite',    description: 'Campaigns, content, automations' },
  { key: 'crm',          label: 'CRM',                description: 'Leads, deals, AI follow-ups' },
];

const Stepper = ({ idx }) => (
  <ol className="flex items-center gap-1 sm:gap-2 flex-wrap" data-testid="staff-wizard-stepper">
    {STEPS.map((s, i) => {
      const Icon = s.icon;
      const state = i < idx ? 'done' : i === idx ? 'active' : 'todo';
      return (
        <li key={s.id} className="flex items-center gap-2" data-testid={`staff-wizard-step-${s.id}`} aria-current={state === 'active' ? 'step' : undefined}>
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center border-2 transition-colors"
            style={{
              borderColor: state === 'done' ? '#10B981' : state === 'active' ? '#0055FF' : '#E4E4E7',
              background:  state === 'done' ? '#10B981' : state === 'active' ? '#EFF6FF' : '#FFFFFF',
              color:       state === 'done' ? '#FFFFFF' : state === 'active' ? '#1D4ED8' : '#A1A1AA',
            }}
          >
            {state === 'done' ? <Check size={14} /> : <Icon size={13} />}
          </div>
          <div className="hidden sm:block">
            <div className="text-[11px] font-bold uppercase tracking-wider" style={{ color: state === 'active' ? '#1D4ED8' : '#71717A' }}>{s.label}</div>
            <div className="text-[10px] text-zinc-400">{s.hint}</div>
          </div>
          {i < STEPS.length - 1 && <div className="w-4 sm:w-8 h-px bg-zinc-200" />}
        </li>
      );
    })}
  </ol>
);

const StaffOnboardingWizard = ({ isPulseAdmin = false }) => {
  const [idx, setIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // Form state
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    brand: isPulseAdmin ? 'pulse' : 'gymaxis',
    role: 'staff',
    organization_id: '',
    allowed_site_ids: [],
    module_overrides: { operations: true, memberships: true, marketing: true, crm: true },
  });

  // Server data
  const [orgs, setOrgs] = useState([]);
  const [orgSites, setOrgSites] = useState([]);

  // Result
  const [result, setResult] = useState(null);

  const role = useMemo(() => ROLES.find((r) => r.id === form.role) || ROLES[0], [form.role]);
  const orgRequired = role.orgRequired;

  const update = (patch) => setForm((p) => ({ ...p, ...patch }));

  // Load orgs once.
  useEffect(() => {
    (async () => {
      try {
        const token = localStorage.getItem('token');
        const brand = isPulseAdmin ? 'pulse' : 'all';
        const { data } = await axios.get(`${API}/master-admin/organizations`, {
          headers: { Authorization: `Bearer ${token}` },
          params: { brand },
        });
        setOrgs(data.organizations || []);
      } catch { /* noop */ }
    })();
  }, [isPulseAdmin]);

  // Load sites when org changes.
  useEffect(() => {
    if (!form.organization_id) { setOrgSites([]); return; }
    (async () => {
      try {
        const token = localStorage.getItem('token');
        const { data } = await axios.get(`${API}/master-admin/organizations/${form.organization_id}/sites`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setOrgSites(data.sites || data || []);
      } catch { setOrgSites([]); }
    })();
  }, [form.organization_id]);

  const canNext = useCallback(() => {
    if (idx === 0) return form.full_name.trim().length > 1 && /.+@.+\..+/.test(form.email);
    if (idx === 1) return !!form.role && (!orgRequired || !!form.organization_id);
    return true;
  }, [idx, form, orgRequired]);

  const onCreate = async () => {
    setBusy(true); setError('');
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };

      let created;
      if (form.role === 'pulse_master_admin') {
        const { data } = await axios.post(`${API}/master-admin/pulse-admins`, {
          email: form.email, full_name: form.full_name,
        }, { headers });
        created = { user_id: data.user_id, invite_url: null, email: data.email, full_name: form.full_name };
      } else if (form.role === 'master_admin') {
        // For master_admin role we still need a "home" org — use the first GymAxis org.
        const homeOrg = form.organization_id || (orgs.find((o) => o.brand === 'gymaxis')?.id || orgs[0]?.id);
        if (!homeOrg) throw new Error('No organisation available to anchor the master admin.');
        const { data } = await axios.post(`${API}/master-admin/organizations/${homeOrg}/users`, {
          email: form.email, full_name: form.full_name, role: 'master_admin',
        }, { headers });
        created = { user_id: data.id, invite_url: data.invite_url, email: data.email, full_name: data.full_name, expires_at: data.invite_expires_at };
      } else if (form.role === 'service_desk') {
        // Service Desk staff live on the Pulse Service Desk endpoint.
        const homeOrg = form.organization_id || orgs[0]?.id;
        if (!homeOrg) throw new Error('No organisation available to anchor the service-desk user.');
        const { data } = await axios.post(`${API}/master-admin/organizations/${homeOrg}/users`, {
          email: form.email, full_name: form.full_name, role: 'service_desk',
        }, { headers });
        created = { user_id: data.id, invite_url: data.invite_url, email: data.email, full_name: data.full_name, expires_at: data.invite_expires_at };
      } else {
        // Org-scoped role.
        const { data } = await axios.post(`${API}/master-admin/organizations/${form.organization_id}/users`, {
          email: form.email, full_name: form.full_name, role: form.role,
        }, { headers });
        created = { user_id: data.id, invite_url: data.invite_url, email: data.email, full_name: data.full_name, expires_at: data.invite_expires_at };
      }

      // Apply allowed_site_ids + module_overrides via the existing edit endpoint.
      const extras = {};
      if (form.allowed_site_ids.length) extras.allowed_site_ids = form.allowed_site_ids;
      // Only send overrides for modules that were toggled OFF (true = inherit org default).
      const offMods = Object.fromEntries(Object.entries(form.module_overrides).filter(([, v]) => v === false));
      if (Object.keys(offMods).length) extras.module_overrides = offMods;
      if (Object.keys(extras).length) {
        await axios.put(`${API}/master-admin/users/${created.user_id}/edit`, extras, { headers });
      }

      // If we didn't get an invite_url (Pulse-admins endpoint), mint one.
      if (!created.invite_url) {
        try {
          const { data: link } = await axios.post(`${API}/master-admin/users/${created.user_id}/invite-link`, {}, { headers });
          created.invite_url = link.invite_url;
          created.expires_at = link.expires_at;
        } catch { /* noop */ }
      }

      setResult(created);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Failed to create user';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
    setBusy(false);
  };

  const copyLink = async () => {
    if (!result?.invite_url) return;
    try {
      await navigator.clipboard.writeText(result.invite_url);
    } catch { /* noop */ }
  };

  const reset = () => {
    setIdx(0); setResult(null); setError('');
    setForm({
      full_name: '', email: '',
      brand: isPulseAdmin ? 'pulse' : 'gymaxis',
      role: 'staff', organization_id: '',
      allowed_site_ids: [],
      module_overrides: { operations: true, memberships: true, marketing: true, crm: true },
    });
  };

  // ── Step renderers ────────────────────────────────────────────
  const renderIdentity = () => (
    <div className="space-y-4">
      <div>
        <label className="block text-xs font-bold uppercase tracking-wider text-zinc-500 mb-1">Full name</label>
        <input
          type="text" autoFocus value={form.full_name}
          onChange={(e) => update({ full_name: e.target.value })}
          placeholder="Jane Smith"
          className="w-full px-3 py-2 text-sm rounded-md border bg-white focus:outline-none focus:ring-2 focus:ring-blue-200"
          style={{ borderColor: '#E4E4E7' }}
          data-testid="staff-wizard-name"
        />
      </div>
      <div>
        <label className="block text-xs font-bold uppercase tracking-wider text-zinc-500 mb-1">Work email</label>
        <div className="relative">
          <Mail size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            type="email" value={form.email}
            onChange={(e) => update({ email: e.target.value })}
            placeholder="jane@pulsefitness.com"
            className="w-full pl-8 pr-3 py-2 text-sm rounded-md border bg-white focus:outline-none focus:ring-2 focus:ring-blue-200"
            style={{ borderColor: '#E4E4E7' }}
            data-testid="staff-wizard-email"
          />
        </div>
        <p className="text-[10px] text-zinc-500 mt-1">An invite link (72 h) is generated at the end. The user sets their own password — you never see it.</p>
      </div>
      {!isPulseAdmin && (
        <div>
          <label className="block text-xs font-bold uppercase tracking-wider text-zinc-500 mb-1">Brand context</label>
          <div className="flex gap-2">
            {[
              { id: 'pulse',   label: 'Pulse Fitness' },
              { id: 'gymaxis', label: 'GymAxis' },
            ].map((b) => (
              <button
                key={b.id} type="button"
                onClick={() => update({ brand: b.id, organization_id: '' })}
                className="px-3 py-1.5 text-xs font-semibold rounded-md border"
                style={{
                  borderColor: form.brand === b.id ? '#1D4ED8' : '#E4E4E7',
                  background:  form.brand === b.id ? '#EFF6FF' : '#FFFFFF',
                  color:       form.brand === b.id ? '#1D4ED8' : '#52525B',
                }}
                data-testid={`staff-wizard-brand-${b.id}`}
              >
                {b.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );

  const renderRole = () => {
    const grouped = Object.entries(ROLES.reduce((m, r) => { (m[r.group] ||= []).push(r); return m; }, {}));
    // Pulse Master Admins can only invite Pulse-scoped roles.
    const filteredGrouped = grouped.map(([g, rs]) => [
      g,
      isPulseAdmin ? rs.filter((r) => r.id !== 'master_admin') : rs,
    ]).filter(([, rs]) => rs.length > 0);

    return (
      <div className="space-y-4">
        {filteredGrouped.map(([group, rs]) => (
          <div key={group}>
            <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">{group}</p>
            <div className="grid sm:grid-cols-2 gap-2">
              {rs.map((r) => (
                <button
                  key={r.id} type="button"
                  onClick={() => update({ role: r.id })}
                  className="text-left p-3 rounded-lg border transition-colors"
                  style={{
                    borderColor: form.role === r.id ? '#1D4ED8' : '#E4E4E7',
                    background:  form.role === r.id ? '#EFF6FF' : '#FFFFFF',
                  }}
                  data-testid={`staff-wizard-role-${r.id}`}
                >
                  <p className="text-sm font-bold text-zinc-900">{r.label}</p>
                  <p className="text-[11px] text-zinc-500 mt-0.5 leading-snug">{r.description}</p>
                </button>
              ))}
            </div>
          </div>
        ))}

        {orgRequired && (
          <div className="mt-3">
            <label className="block text-xs font-bold uppercase tracking-wider text-zinc-500 mb-1">Organisation</label>
            <select
              value={form.organization_id}
              onChange={(e) => update({ organization_id: e.target.value, allowed_site_ids: [] })}
              className="w-full px-3 py-2 text-sm rounded-md border bg-white"
              style={{ borderColor: '#E4E4E7' }}
              data-testid="staff-wizard-org"
            >
              <option value="">Choose an organisation…</option>
              {orgs.map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
          </div>
        )}
      </div>
    );
  };

  const renderSites = () => {
    if (!orgRequired || !form.organization_id) {
      return (
        <p className="text-sm text-zinc-500 bg-zinc-50 rounded-md p-3 border" style={{ borderColor: '#E4E4E7' }}>
          Site-lock is only available for org-scoped roles. Platform admins automatically see every site.
        </p>
      );
    }
    const toggleSite = (id) => {
      const set = new Set(form.allowed_site_ids);
      if (set.has(id)) set.delete(id); else set.add(id);
      update({ allowed_site_ids: Array.from(set) });
    };
    const allLocked = form.allowed_site_ids.length === 0;
    return (
      <div className="space-y-3">
        <p className="text-xs text-zinc-500">
          Leave empty for <strong className="text-zinc-700">all sites</strong> in the organisation, or tick specific sites to lock this user down to those locations only.
        </p>
        <div className="rounded-lg border p-2 max-h-64 overflow-y-auto" style={{ borderColor: '#E4E4E7' }} data-testid="staff-wizard-sites-list">
          {orgSites.length === 0 && (
            <p className="text-xs text-zinc-500 p-3">No sites yet for this organisation — leave empty to grant access to all future sites.</p>
          )}
          {orgSites.map((s) => {
            const checked = form.allowed_site_ids.includes(s.id);
            return (
              <label
                key={s.id}
                className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-zinc-50 cursor-pointer"
                data-testid={`staff-wizard-site-${s.id}`}
              >
                <input
                  type="checkbox" checked={checked}
                  onChange={() => toggleSite(s.id)}
                  className="rounded"
                />
                <span className="text-sm text-zinc-700">{s.name}</span>
                {s.is_head_office && <span className="text-[10px] uppercase tracking-wider font-bold text-amber-600">HQ</span>}
              </label>
            );
          })}
        </div>
        <p className="text-[11px] text-zinc-500">
          {allLocked ? 'All sites accessible (no restriction).' : `Locked to ${form.allowed_site_ids.length} site${form.allowed_site_ids.length === 1 ? '' : 's'}.`}
        </p>
      </div>
    );
  };

  const renderModules = () => (
    <div className="space-y-3">
      <p className="text-xs text-zinc-500">
        Module overrides revoke a module for this user only, regardless of the organisation default. Leave a module ON to inherit the org-level entitlement.
      </p>
      <div className="space-y-2">
        {MODULES.map((m) => {
          const enabled = form.module_overrides[m.key] !== false;
          return (
            <label
              key={m.key}
              className="flex items-center justify-between gap-3 p-3 rounded-lg border bg-white cursor-pointer"
              style={{ borderColor: '#E4E4E7' }}
              data-testid={`staff-wizard-module-${m.key}`}
            >
              <div className="min-w-0">
                <div className="text-sm font-semibold text-zinc-900">{m.label}</div>
                <div className="text-[11px] text-zinc-500">{m.description}</div>
              </div>
              <input
                type="checkbox" checked={enabled}
                onChange={(e) => update({ module_overrides: { ...form.module_overrides, [m.key]: e.target.checked } })}
                className="w-4 h-4"
              />
            </label>
          );
        })}
      </div>
    </div>
  );

  const renderReview = () => {
    const orgName = orgs.find((o) => o.id === form.organization_id)?.name || '—';
    const lockedSites = form.allowed_site_ids.length
      ? orgSites.filter((s) => form.allowed_site_ids.includes(s.id)).map((s) => s.name).join(', ')
      : 'All sites';
    const revoked = Object.entries(form.module_overrides).filter(([, v]) => v === false).map(([k]) => k);

    if (result) {
      return (
        <div className="space-y-4" data-testid="staff-wizard-result">
          <div className="rounded-lg border bg-emerald-50 p-4" style={{ borderColor: '#A7F3D0' }}>
            <div className="flex items-center gap-2 mb-2">
              <Check size={16} className="text-emerald-700" />
              <p className="text-sm font-bold text-emerald-900">{result.full_name} invited</p>
            </div>
            <p className="text-xs text-emerald-800">
              An invite token has been minted. Share the link below by your preferred channel — the user sets their own password on first visit. Link expires in 72 hours.
            </p>
          </div>
          {result.invite_url ? (
            <div className="rounded-lg border bg-white p-3 space-y-2" style={{ borderColor: '#E4E4E7' }}>
              <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Invite link (72 h)</p>
              <code className="block text-xs text-zinc-700 break-all bg-zinc-50 p-2 rounded border" style={{ borderColor: '#F4F4F5' }} data-testid="staff-wizard-invite-link">
                {result.invite_url}
              </code>
              <div className="flex gap-2 pt-1">
                <button
                  type="button" onClick={copyLink}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold border rounded-md px-3 py-1.5 bg-white hover:bg-zinc-50"
                  style={{ borderColor: '#E4E4E7' }}
                  data-testid="staff-wizard-copy-link"
                >
                  <Copy size={12} /> Copy link
                </button>
                <a
                  href={`mailto:${result.email}?subject=Welcome to GymAxis&body=Hi ${encodeURIComponent(result.full_name)},%0D%0A%0D%0AClick this 72h link to set your password and sign in:%0D%0A${encodeURIComponent(result.invite_url)}`}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold border rounded-md px-3 py-1.5 bg-white hover:bg-zinc-50"
                  style={{ borderColor: '#E4E4E7' }}
                  data-testid="staff-wizard-email-link"
                >
                  <Mail size={12} /> Email it
                </a>
              </div>
            </div>
          ) : (
            <div className="rounded-lg border bg-amber-50 p-3 text-xs text-amber-800" style={{ borderColor: '#FDE68A' }}>
              <AlertCircle size={12} className="inline mr-1" /> No invite link returned (the backend may have emailed it directly). Re-issue via People → row → Issue & copy reset link.
            </div>
          )}
          <div className="flex gap-2">
            <button
              type="button" onClick={reset}
              className="inline-flex items-center gap-1.5 text-xs font-semibold border rounded-md px-3 py-1.5 bg-white hover:bg-zinc-50"
              style={{ borderColor: '#E4E4E7' }}
              data-testid="staff-wizard-reset"
            >
              <RefreshCw size={12} /> Invite another
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-2" data-testid="staff-wizard-review">
        {[
          ['Name', form.full_name],
          ['Email', form.email],
          ['Brand', form.brand === 'pulse' ? 'Pulse Fitness' : form.brand === 'gymaxis' ? 'GymAxis' : 'Both brands'],
          ['Role', role.label],
          ['Organisation', orgRequired ? orgName : 'Platform-wide'],
          ['Sites', orgRequired ? lockedSites : 'All sites (platform)'],
          ['Revoked modules', revoked.length ? revoked.join(', ') : 'None'],
        ].map(([k, v]) => (
          <div key={k} className="flex items-start justify-between gap-3 py-2 border-b" style={{ borderColor: '#F4F4F5' }}>
            <span className="text-[11px] font-bold uppercase tracking-wider text-zinc-500">{k}</span>
            <span className="text-sm text-zinc-900 text-right break-words">{v}</span>
          </div>
        ))}
        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 flex items-start gap-2" data-testid="staff-wizard-error">
            <AlertCircle size={12} className="mt-0.5" /> {error}
          </div>
        )}
      </div>
    );
  };

  const step = STEPS[idx];

  return (
    <div className="space-y-5" data-testid="staff-onboarding-wizard">
      <div>
        <h2 className="text-xl font-bold text-zinc-900 tracking-tight">Onboard staff</h2>
        <p className="text-sm text-zinc-500 mt-0.5">
          Invite a new {isPulseAdmin ? 'Pulse Fitness ' : ''}team member. Five quick steps — they set their own password from a 72 h invite link.
        </p>
      </div>

      <Stepper idx={idx} />

      <div className="rounded-xl border bg-white p-5" style={{ borderColor: '#E4E4E7' }}>
        <div className="flex items-center gap-2 mb-4">
          <step.icon size={16} className="text-blue-700" />
          <h3 className="text-base font-bold text-zinc-900">{step.label}</h3>
        </div>
        {idx === 0 && renderIdentity()}
        {idx === 1 && renderRole()}
        {idx === 2 && renderSites()}
        {idx === 3 && renderModules()}
        {idx === 4 && renderReview()}
      </div>

      {!result && (
        <div className="flex justify-between items-center">
          <button
            type="button"
            onClick={() => setIdx((i) => Math.max(0, i - 1))}
            disabled={idx === 0 || busy}
            className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-md border bg-white hover:bg-zinc-50 disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ borderColor: '#E4E4E7' }}
            data-testid="staff-wizard-back"
          >
            <ArrowLeft size={13} /> Back
          </button>
          {idx < STEPS.length - 1 ? (
            <button
              type="button"
              onClick={() => setIdx((i) => i + 1)}
              disabled={!canNext()}
              className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-md text-white disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: '#0055FF' }}
              data-testid="staff-wizard-next"
            >
              Next <ArrowRight size={13} />
            </button>
          ) : (
            <button
              type="button"
              onClick={onCreate}
              disabled={busy}
              className="inline-flex items-center gap-1.5 text-sm font-semibold px-4 py-1.5 rounded-md text-white disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: '#0055FF' }}
              data-testid="staff-wizard-submit"
            >
              {busy ? <RefreshCw size={13} className="animate-spin" /> : <LinkIcon size={13} />}
              {busy ? 'Creating…' : 'Generate invite link'}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default StaffOnboardingWizard;
