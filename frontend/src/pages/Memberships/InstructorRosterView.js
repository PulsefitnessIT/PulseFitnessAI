/**
 * Operator-facing instructor roster (create / edit / photo / publish).
 * Rendered inside InstructorsTab.js as a 3rd subtab.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { Plus, Edit3, Image as ImageIcon, ExternalLink, Copy, X, Eye, EyeOff, Trash2, Upload, Link as LinkIcon, Mail, AlertTriangle, MapPin, ShieldCheck, PoundSterling, Download, CalendarDays } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const empty = () => ({
  name: '', email: '', phone: '', headline: '', bio: '',
  photo_url: '', hero_photo_url: '',
  specialties: [], qualifications: [],
  years_experience: '',
  social: { instagram: '', tiktok: '', linkedin: '', website: '' },
  is_published: true,
  // Iter 215bl — extended profile fields (parity with member drawer).
  dob: '', address_line1: '', address_line2: '', city: '', postcode: '', country: '',
  emergency_contact_name: '', emergency_contact_phone: '',
  notes: '', tags: [],
  // Iter 216ae — Phase F: safeguarding & payroll.
  dbs_reference: '', dbs_issued_on: '', dbs_expires_on: '',
  safeguarding_completed_on: '', safeguarding_expires_on: '',
  first_aid_completed_on: '', first_aid_expires_on: '',
  hourly_rate_pence: '', substitute_available: true,
});

function calcAge(dob) {
  if (!dob) return null;
  const d = new Date(dob);
  if (Number.isNaN(d.getTime())) return null;
  return Math.floor((Date.now() - d.getTime()) / (365.25 * 24 * 60 * 60 * 1000));
}

async function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

export default function InstructorRosterView({ API, headers }) {
  const [rows, setRows] = useState([]);
  const [compMap, setCompMap] = useState({}); // id -> compliance
  const [compSummary, setCompSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | 'new' | <instructorDoc>
  const [orgSlug, setOrgSlug] = useState(null);
  const [showPayroll, setShowPayroll] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: r1 }, compR] = await Promise.all([
        axios.get(`${API}/memberships/instructors`, { headers }),
        axios.get(`${API}/memberships/instructors/compliance`, { headers }).catch(() => null),
      ]);
      setRows(r1.instructors || []);
      if (compR?.data) {
        const map = {};
        (compR.data.compliance || []).forEach((c) => { map[c.id] = c.compliance; });
        setCompMap(map);
        setCompSummary(compR.data.summary || null);
      }
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load instructors');
    } finally { setLoading(false); }
  }, [API, headers]);

  const loadOrg = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/memberships/me`, { headers });
      setOrgSlug(data?.organization?.membership_app_slug || data?.organization?.slug || null);
    } catch { /* non-fatal */ }
  }, [API, headers]);

  useEffect(() => { load(); loadOrg(); }, [load, loadOrg]);

  const publicBase = typeof window !== 'undefined' ? window.location.origin : '';

  return (
    <div data-testid="mbr-instructor-roster">
      <div className="flex items-end justify-between gap-4 flex-wrap mb-4">
        <div>
          <h3 className="text-xl font-black tracking-tight">Instructor roster</h3>
          <p className="mt-1 text-sm text-[color:var(--theme-text-muted)]">
            Give each instructor their own bio page. Photos, specialties, social links — a shareable mini-site that sells their classes.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={() => setShowPayroll(true)}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-extrabold border border-[color:var(--theme-border)] hover:bg-white/5"
            data-testid="mbr-instructor-payroll-btn">
            <PoundSterling size={13} /> Export payroll
          </button>
          <button onClick={() => setEditing('new')}
            className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-extrabold"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="mbr-instructor-add">
            <Plus size={13} /> Add instructor
          </button>
        </div>
      </div>

      {compSummary && compSummary.total > 0 && (
        <div className="mb-4 grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="mbr-instructor-compliance-strip">
          <ComplianceKpi label="Compliant" value={compSummary.green} tone="green" />
          <ComplianceKpi label="Expiring soon" value={compSummary.amber} tone="amber" />
          <ComplianceKpi label="Expired" value={compSummary.red} tone="red" />
          <ComplianceKpi label="Missing" value={compSummary.missing} tone="missing" />
        </div>
      )}

      {loading ? (
        <div className="p-8 text-center text-sm text-[color:var(--theme-text-muted)]">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="p-8 text-center rounded-xl border border-dashed border-[color:var(--theme-border)]">
          <div className="text-sm text-[color:var(--theme-text-muted)]">
            No instructors yet. Add your first teacher to start building their public profile.
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {rows.map((inst) => {
            const initials = (inst.name || '?').split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();
            const publicPath = orgSlug ? `${publicBase}/m/${orgSlug}/i/${inst.slug}` : null;
            return (
              <div key={inst.id}
                className="rounded-xl border border-[color:var(--theme-border)] p-4 flex flex-col gap-3"
                data-testid={`mbr-instructor-card-${inst.id}`}>
                <div className="flex items-center gap-3">
                  {inst.photo_url ? (
                    <img src={inst.photo_url} alt={inst.name}
                      className="w-16 h-16 rounded-full object-cover"
                      style={{ border: '2px solid var(--color-brand-cyan)' }} />
                  ) : (
                    <div className="w-16 h-16 rounded-full grid place-items-center text-xl font-black"
                      style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}>
                      {initials}
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="font-bold truncate">{inst.name}</div>
                    {inst.headline && <div className="text-xs text-[color:var(--theme-text-muted)] truncate">{inst.headline}</div>}
                    {!inst.is_published && (
                      <div className="mt-1 inline-flex items-center gap-1 text-[10px] font-bold uppercase text-amber-400">
                        <EyeOff size={10} /> Hidden
                      </div>
                    )}
                  </div>
                </div>

                {(inst.specialties || []).length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {inst.specialties.slice(0, 4).map((s) => (
                      <span key={s} className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-white/5">{s}</span>
                    ))}
                  </div>
                )}

                {compMap[inst.id] && (
                  <ComplianceBadge comp={compMap[inst.id]} testid={`mbr-instructor-comp-${inst.id}`} />
                )}

                <div className="flex items-center gap-1.5 pt-2 border-t border-[color:var(--theme-border)] mt-auto">
                  <button onClick={() => setEditing(inst)}
                    className="flex-1 inline-flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-bold rounded-lg border border-[color:var(--theme-border)] hover:bg-white/5"
                    data-testid={`mbr-instructor-edit-${inst.id}`}>
                    <Edit3 size={11} /> Edit
                  </button>
                  {publicPath && inst.is_published && (
                    <>
                      <a href={publicPath} target="_blank" rel="noreferrer"
                         className="inline-flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-bold rounded-lg border border-[color:var(--theme-border)] hover:bg-white/5"
                         data-testid={`mbr-instructor-view-${inst.id}`}>
                        <ExternalLink size={11} /> View
                      </a>
                      <button onClick={async () => {
                        try { await navigator.clipboard.writeText(publicPath); notify.success('Profile link copied'); } catch { /* ignore */ }
                      }}
                        className="inline-flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-bold rounded-lg border border-[color:var(--theme-border)] hover:bg-white/5"
                        title="Copy share link"
                        data-testid={`mbr-instructor-copy-${inst.id}`}>
                        <Copy size={11} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {editing && (
        <EditorDrawer API={API} headers={headers} initial={editing === 'new' ? empty() : editing}
          onClose={(changed) => { setEditing(null); if (changed) load(); }} />
      )}

      {showPayroll && (
        <PayrollExportModal API={API} headers={headers}
          onClose={() => setShowPayroll(false)} />
      )}
    </div>
  );
}

/* ───────────── Compliance helpers (Phase F) ───────────── */

const TONE_STYLES = {
  green: { bg: 'rgba(16,185,129,0.12)', fg: '#10b981', label: 'Compliant' },
  amber: { bg: 'rgba(245,158,11,0.14)', fg: '#f59e0b', label: 'Expiring' },
  red: { bg: 'rgba(239,68,68,0.15)', fg: '#ef4444', label: 'Expired' },
  missing: { bg: 'rgba(148,163,184,0.12)', fg: '#94a3b8', label: 'Missing' },
};

function ComplianceKpi({ label, value, tone }) {
  const s = TONE_STYLES[tone] || TONE_STYLES.missing;
  return (
    <div className="rounded-lg p-2.5" style={{ background: s.bg, border: `1px solid ${s.fg}30` }}
      data-testid={`mbr-instructor-kpi-${tone}`}>
      <p className="text-[9px] uppercase tracking-wider font-bold" style={{ color: s.fg }}>{label}</p>
      <p className="text-lg font-extrabold mt-0.5">{value}</p>
    </div>
  );
}

function ComplianceBadge({ comp, testid }) {
  const s = TONE_STYLES[comp.status] || TONE_STYLES.missing;
  const tip = (comp.items || [])
    .map((i) => `${i.label}: ${i.expires_on || 'not recorded'}${i.status === 'red' ? ' (expired)' : i.status === 'amber' ? ' (soon)' : ''}`)
    .join(' · ');
  return (
    <div
      className="flex items-center gap-1.5 text-[10px] font-bold px-2 py-1 rounded-md"
      style={{ background: s.bg, color: s.fg, border: `1px solid ${s.fg}30` }}
      title={tip}
      data-testid={testid}>
      <ShieldCheck size={11} /> {s.label}
      {comp.earliest_expiry && (
        <span className="opacity-70 font-normal ml-1">· earliest {comp.earliest_expiry}</span>
      )}
    </div>
  );
}

/* ───────────── Payroll Export Modal (Phase F) ───────────── */

function PayrollExportModal({ API, headers, onClose }) {
  const todayISO = new Date().toISOString().slice(0, 10);
  const firstOfMonth = (() => { const d = new Date(); d.setDate(1); return d.toISOString().slice(0, 10); })();
  const [from, setFrom] = useState(firstOfMonth);
  const [to, setTo] = useState(todayISO);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!from || !to) { notify.error('Pick both dates'); return; }
    setBusy(true);
    try {
      const res = await axios.get(
        `${API}/memberships/instructors/payroll.csv`,
        { headers, params: { date_from: from, date_to: to }, responseType: 'blob' },
      );
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `payroll-${from}-to-${to}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      notify.success('Payroll CSV downloaded');
      onClose();
    } catch (e) {
      notifyApiError(notify, e, 'Payroll export failed');
    } finally { setBusy(false); }
  };

  return createPortal((
    <div className="fixed inset-0 z-[110] bg-black/50 grid place-items-center p-4" onClick={onClose} data-testid="mbr-payroll-modal">
      <div className="w-full max-w-md rounded-2xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[color:var(--color-brand-cyan)]">Payroll export</p>
            <h3 className="text-lg font-extrabold">Download CSV</h3>
            <p className="text-xs text-[color:var(--theme-text-muted)] mt-1">
              Aggregates completed classes by instructor. Pay is computed from class rate → instructor hourly × duration.
            </p>
          </div>
          <button onClick={onClose} className="h-9 w-9 rounded-full grid place-items-center border border-[color:var(--theme-border)] hover:bg-white/5">
            <X size={16} />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3 mt-2">
          <label className="block">
            <span className="block text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] mb-1">From</span>
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)}
              className="w-full h-10 px-3 rounded-lg bg-transparent border border-[color:var(--theme-border)] text-sm"
              data-testid="mbr-payroll-from" />
          </label>
          <label className="block">
            <span className="block text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] mb-1">To</span>
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)}
              className="w-full h-10 px-3 rounded-lg bg-transparent border border-[color:var(--theme-border)] text-sm"
              data-testid="mbr-payroll-to" />
          </label>
        </div>
        <div className="flex items-center gap-2 mt-4 flex-wrap">
          {[
            { label: 'This month', f: firstOfMonth, t: todayISO },
            { label: 'Last 30d', f: new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10), t: todayISO },
            { label: 'YTD', f: `${new Date().getFullYear()}-01-01`, t: todayISO },
          ].map((p) => (
            <button key={p.label} type="button" onClick={() => { setFrom(p.f); setTo(p.t); }}
              className="text-[10px] font-bold px-2 py-1 rounded border border-[color:var(--theme-border)] hover:bg-white/5 inline-flex items-center gap-1">
              <CalendarDays size={10} /> {p.label}
            </button>
          ))}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-2 text-xs font-bold rounded-lg border border-[color:var(--theme-border)] hover:bg-white/5">Cancel</button>
          <button onClick={run} disabled={busy}
            className="px-4 py-2 text-xs font-extrabold rounded-lg inline-flex items-center gap-1 disabled:opacity-50"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="mbr-payroll-run">
            <Download size={12} /> {busy ? 'Generating…' : 'Download CSV'}
          </button>
        </div>
      </div>
    </div>
  ), document.body);
}

function ListInput({ value, onChange, placeholder, testid }) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const v = draft.trim();
    if (!v || (value || []).includes(v)) { setDraft(''); return; }
    onChange([...(value || []), v]);
    setDraft('');
  };
  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {(value || []).map((v, i) => (
          <span key={v} className="inline-flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-xs font-bold">
            {v}
            <button onClick={() => onChange(value.filter((_, j) => j !== i))}
              className="opacity-60 hover:opacity-100" title="Remove">
              <X size={10} />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-1.5">
        <input type="text" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={placeholder}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          className="flex-1 rounded-lg border border-[color:var(--theme-border)] bg-transparent px-3 py-1.5 text-sm"
          data-testid={testid} />
        <button type="button" onClick={add} className="px-3 py-1.5 rounded-lg border border-[color:var(--theme-border)] text-xs font-bold hover:bg-white/5">Add</button>
      </div>
    </div>
  );
}

function PhotoField({ label, value, onChange, aspect, testid }) {
  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 3 * 1024 * 1024) { notify.error('Image too large — max 3MB'); return; }
    try {
      const url = await fileToDataUrl(f);
      onChange(url);
    } catch {
      notify.error('Could not read image');
    }
  };
  return (
    <div>
      <label className="block text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">{label}</label>
      <div className="mt-1 flex items-center gap-3">
        {value ? (
          <img src={value} alt={label}
            style={{ width: aspect === 'wide' ? 180 : 72, height: aspect === 'wide' ? 72 : 72,
                     objectFit: 'cover', borderRadius: aspect === 'wide' ? 12 : '50%',
                     border: '1px solid var(--theme-border)' }} />
        ) : (
          <div style={{ width: aspect === 'wide' ? 180 : 72, height: 72,
                        borderRadius: aspect === 'wide' ? 12 : '50%',
                        border: '1px dashed var(--theme-border)',
                        display: 'grid', placeItems: 'center', color: 'var(--theme-text-muted)' }}>
            <ImageIcon size={20} />
          </div>
        )}
        <div className="flex items-center gap-2">
          <label className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-bold rounded-lg border border-[color:var(--theme-border)] hover:bg-white/5 cursor-pointer"
            data-testid={testid}>
            <Upload size={12} /> Upload
            <input type="file" accept="image/*" className="hidden" onChange={onFile} />
          </label>
          {value && (
            <button type="button" onClick={() => onChange('')}
              className="inline-flex items-center gap-1 px-2 py-1.5 text-xs font-bold rounded-lg border border-[color:var(--theme-border)] hover:bg-red-500/10 text-red-400">
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function EditorDrawer({ API, headers, initial, onClose }) {
  const [f, setF] = useState(() => ({ ...empty(), ...initial, social: { ...empty().social, ...(initial.social || {}) }, tags: Array.isArray(initial.tags) ? initial.tags : [] }));
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState('profile');
  const isNew = !initial.id;

  const up = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  const upSocial = (k) => (v) => setF((s) => ({ ...s, social: { ...s.social, [k]: v } }));
  const age = calcAge(f.dob);

  const save = async () => {
    if (!f.name?.trim()) { notify.error('Name is required'); return; }
    setSaving(true);
    try {
      const payload = {
        ...f,
        years_experience: f.years_experience === '' ? null : Number(f.years_experience),
        hourly_rate_pence: f.hourly_rate_pence === '' || f.hourly_rate_pence === null || f.hourly_rate_pence === undefined
          ? null
          : Number(f.hourly_rate_pence),
      };
      if (isNew) {
        await axios.post(`${API}/memberships/instructors`, payload, { headers });
      } else {
        await axios.patch(`${API}/memberships/instructors/${initial.id}`, payload, { headers });
      }
      notify.success(isNew ? 'Instructor created' : 'Instructor updated');
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, 'Save failed');
    } finally { setSaving(false); }
  };

  const archive = async () => {
    if (!window.confirm(`Archive ${initial.name}? They'll no longer appear on the public roster.`)) return;
    setSaving(true);
    try {
      await axios.delete(`${API}/memberships/instructors/${initial.id}`, { headers });
      notify.success('Archived');
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, 'Archive failed');
    } finally { setSaving(false); }
  };

  const inviteLogin = async () => {
    if (!initial.email) { notify.error('Add an email first, then save, then invite.'); return; }
    setSaving(true);
    try {
      const { data } = await axios.post(
        `${API}/memberships/instructors/${initial.id}/invite-login`, {}, { headers },
      );
      if (data.already_linked) notify.info(`${initial.name} already has a login.`);
      else if (data.linked_existing) notify.success('Linked to an existing account.');
      else notify.success(`Invite sent to ${initial.email}.`);
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, 'Invite failed');
    } finally { setSaving(false); }
  };

  const TABS = [
    { id: 'profile',  label: 'Profile' },
    { id: 'public',   label: 'Public bio' },
    { id: 'social',   label: 'Social' },
    { id: 'safeguarding', label: 'Compliance & pay' },
  ];

  const Field = ({ label, hint, children, span = 1 }) => (
    <label className={`block ${span === 2 ? 'col-span-2' : ''}`}>
      <span className="block text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-1">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-[color:var(--theme-text-muted)] mt-1">{hint}</span>}
    </label>
  );

  const inputClass = "w-full h-10 px-3 rounded-lg bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] text-sm text-[color:var(--theme-text)] placeholder-[color:var(--theme-text-muted)] focus:outline-none focus:border-[color:var(--color-brand-cyan)]";

  return (
    // Iter 215d6.2 — portal to document.body so fixed positioning is
    // relative to the viewport, not any transformed ancestor (e.g.
    // `.module-fade-in` used to leave a residual transform).
    createPortal((
    // Iter 215d6 — drawer lives in the mobile safe zone (below Navbar,
    // above MobileBottomNav) so the sticky header (with X close) and
    // sticky footer (Save/Cancel/Archive) are always visible. Desktop
    // continues to use the full-height side-panel pattern.
    <div className="fixed inset-0 z-[100] bg-black/40" onClick={() => onClose(false)} data-testid="mbr-instructor-drawer">
      <div className="absolute inset-x-0 top-16 bottom-16 sm:inset-0 flex justify-end">
        <div className="relative w-full sm:max-w-2xl h-full bg-[color:var(--theme-surface)] sm:border-l border-[color:var(--theme-border)] flex flex-col overflow-hidden" onClick={(e) => e.stopPropagation()}>
        {/* Sticky header — same chrome as MemberEditDrawer */}
        <header className="flex-shrink-0 bg-[color:var(--theme-surface)] border-b border-[color:var(--theme-border)]">
          <div className="px-5 py-4 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[color:var(--color-brand-cyan)]">Instructor record</p>
              <h3 className="text-xl font-bold tracking-tight text-[color:var(--theme-text)] truncate">{isNew ? 'New instructor' : f.name}</h3>
              <p className="text-xs text-[color:var(--theme-text-muted)] truncate flex items-center gap-2 mt-0.5">
                {f.email && <span className="inline-flex items-center gap-1"><Mail size={10} /> {f.email}</span>}
                {age !== null && <span className="inline-flex items-center gap-1">Age {age}</span>}
                {f.is_published ? <span className="inline-flex items-center gap-1 text-emerald-600"><Eye size={10} /> Published</span> : <span className="inline-flex items-center gap-1 text-amber-600"><EyeOff size={10} /> Hidden</span>}
              </p>
            </div>
            <button onClick={() => onClose(false)} className="h-9 w-9 rounded-full flex items-center justify-center border border-[color:var(--theme-border)] bg-[color:var(--theme-bg,transparent)] text-[color:var(--theme-text)] hover:bg-[color:var(--theme-surface-hover)] focus:outline-none focus:ring-2 focus:ring-[color:var(--color-brand-cyan)] focus:ring-offset-1 transition-colors shrink-0" aria-label="Close" data-testid="mbr-instructor-close">
              <X size={18} />
            </button>
          </div>
          <nav className="px-3 pb-2 flex items-center gap-1 overflow-x-auto" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors whitespace-nowrap ${
                  tab === t.id
                    ? 'bg-[color:var(--color-brand-cyan)] text-white'
                    : 'text-[color:var(--theme-text-muted)] hover:bg-[color:var(--theme-surface-hover)] hover:text-[color:var(--theme-text)]'
                }`}
                data-testid={`mbr-instructor-tab-${t.id}`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </header>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {tab === 'profile' && (
            <>
              <PhotoField label="Profile photo (square)" value={f.photo_url} onChange={up('photo_url')} testid="mbr-instructor-photo-upload" />

              <div className="grid grid-cols-2 gap-3">
                <Field label="Full name *">
                  <input type="text" value={f.name} onChange={(e) => up('name')(e.target.value)} className={inputClass} data-testid="mbr-instructor-name" />
                </Field>
                <Field label="Headline">
                  <input type="text" value={f.headline} onChange={(e) => up('headline')(e.target.value)} placeholder="RYT-500 · Vinyasa & Pre-natal · 8 yrs" className={inputClass} data-testid="mbr-instructor-headline" />
                </Field>
                <Field label="Email"><input type="email" value={f.email || ''} onChange={(e) => up('email')(e.target.value)} className={inputClass} data-testid="mbr-instructor-email" /></Field>
                <Field label="Phone"><input type="tel" value={f.phone || ''} onChange={(e) => up('phone')(e.target.value)} className={inputClass} data-testid="mbr-instructor-phone" /></Field>
              </div>

              <Field label="Date of birth" hint={age !== null ? `Age ${age}` : undefined}>
                <input type="date" value={(f.dob || '').slice(0, 10)} onChange={(e) => up('dob')(e.target.value)} className={inputClass} data-testid="mbr-instructor-dob" />
              </Field>

              <div>
                <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2 flex items-center gap-1.5"><MapPin size={11} /> Address</p>
                <div className="space-y-2">
                  <input type="text" placeholder="Address line 1" value={f.address_line1 || ''} onChange={(e) => up('address_line1')(e.target.value)} className={inputClass} data-testid="mbr-instructor-addr1" />
                  <input type="text" placeholder="Address line 2 (optional)" value={f.address_line2 || ''} onChange={(e) => up('address_line2')(e.target.value)} className={inputClass} data-testid="mbr-instructor-addr2" />
                  <div className="grid grid-cols-3 gap-2">
                    <input type="text" placeholder="City" value={f.city || ''} onChange={(e) => up('city')(e.target.value)} className={inputClass} data-testid="mbr-instructor-city" />
                    <input type="text" placeholder="Postcode" value={f.postcode || ''} onChange={(e) => up('postcode')(e.target.value)} className={inputClass} data-testid="mbr-instructor-postcode" />
                    <input type="text" placeholder="Country" value={f.country || ''} onChange={(e) => up('country')(e.target.value)} className={inputClass} data-testid="mbr-instructor-country" />
                  </div>
                </div>
              </div>

              <div>
                <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2 flex items-center gap-1.5"><AlertTriangle size={11} /> Emergency contact</p>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Name"><input type="text" value={f.emergency_contact_name || ''} onChange={(e) => up('emergency_contact_name')(e.target.value)} className={inputClass} data-testid="mbr-instructor-eg-name" /></Field>
                  <Field label="Phone"><input type="tel" value={f.emergency_contact_phone || ''} onChange={(e) => up('emergency_contact_phone')(e.target.value)} className={inputClass} data-testid="mbr-instructor-eg-phone" /></Field>
                </div>
              </div>

              <Field label="Notes (operator-only)">
                <textarea rows={3} value={f.notes || ''} onChange={(e) => up('notes')(e.target.value)} className={`${inputClass} h-auto py-2 resize-y`} data-testid="mbr-instructor-notes" />
              </Field>

              <Field label="Tags (comma-separated)">
                <input type="text" value={(f.tags || []).join(', ')} onChange={(e) => up('tags')(e.target.value.split(',').map((t) => t.trim()).filter(Boolean))} placeholder="e.g. yoga, pilates, full-time" className={inputClass} data-testid="mbr-instructor-tags" />
              </Field>
            </>
          )}

          {tab === 'public' && (
            <>
              <PhotoField label="Hero photo (wide, optional)" aspect="wide" value={f.hero_photo_url} onChange={up('hero_photo_url')} testid="mbr-instructor-hero-upload" />

              <Field label="Bio">
                <textarea value={f.bio} onChange={(e) => up('bio')(e.target.value)} rows={6} placeholder="Tell members what draws them to this instructor — teaching style, background, what makes their classes different." className={`${inputClass} h-auto py-2 resize-y`} data-testid="mbr-instructor-bio" />
              </Field>

              <Field label="Specialties">
                <ListInput value={f.specialties} onChange={up('specialties')} placeholder="e.g. Vinyasa" testid="mbr-instructor-specialty-input" />
              </Field>
              <Field label="Qualifications">
                <ListInput value={f.qualifications} onChange={up('qualifications')} placeholder="e.g. RYT-500" testid="mbr-instructor-qual-input" />
              </Field>
              <Field label="Years teaching">
                <input type="number" value={f.years_experience ?? ''} onChange={(e) => up('years_experience')(e.target.value)} className={`${inputClass} w-32`} data-testid="mbr-instructor-years" />
              </Field>

              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={!!f.is_published} onChange={(e) => up('is_published')(e.target.checked)} data-testid="mbr-instructor-publish-toggle" />
                <span className="inline-flex items-center gap-1 text-[color:var(--theme-text)]"><Eye size={12} /> Show on public roster &amp; allow sharing</span>
              </label>
            </>
          )}

          {tab === 'social' && (
            <fieldset className="rounded-lg border border-[color:var(--theme-border)] p-4 space-y-2">
              <legend className="px-2 text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Social links</legend>
              {['instagram', 'tiktok', 'linkedin', 'website'].map((k) => (
                <div key={k} className="flex items-center gap-2">
                  <LinkIcon size={12} className="text-[color:var(--theme-text-muted)] shrink-0" />
                  <span className="w-20 text-xs capitalize text-[color:var(--theme-text-muted)]">{k}</span>
                  <input type="text" value={f.social[k] || ''} onChange={(e) => upSocial(k)(e.target.value)} placeholder={k === 'website' ? 'https://…' : k === 'instagram' ? '@handle or full URL' : ''} className={inputClass} />
                </div>
              ))}
            </fieldset>
          )}

          {tab === 'safeguarding' && (
            <>
              <div className="rounded-lg border border-[color:var(--theme-border)] p-4 space-y-3" data-testid="mbr-instructor-safeguarding">
                <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] flex items-center gap-1.5">
                  <ShieldCheck size={11} /> DBS check
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="DBS reference">
                    <input type="text" value={f.dbs_reference || ''} onChange={(e) => up('dbs_reference')(e.target.value)} className={inputClass} placeholder="e.g. 001234567890" data-testid="mbr-instructor-dbs-ref" />
                  </Field>
                  <Field label="Issued on">
                    <input type="date" value={(f.dbs_issued_on || '').slice(0, 10)} onChange={(e) => up('dbs_issued_on')(e.target.value)} className={inputClass} data-testid="mbr-instructor-dbs-issued" />
                  </Field>
                  <Field label="Expires on" span={2}>
                    <input type="date" value={(f.dbs_expires_on || '').slice(0, 10)} onChange={(e) => up('dbs_expires_on')(e.target.value)} className={inputClass} data-testid="mbr-instructor-dbs-expires" />
                  </Field>
                </div>
              </div>

              <div className="rounded-lg border border-[color:var(--theme-border)] p-4 space-y-3">
                <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] flex items-center gap-1.5">
                  <ShieldCheck size={11} /> Safeguarding training
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Completed on">
                    <input type="date" value={(f.safeguarding_completed_on || '').slice(0, 10)} onChange={(e) => up('safeguarding_completed_on')(e.target.value)} className={inputClass} data-testid="mbr-instructor-sg-completed" />
                  </Field>
                  <Field label="Expires on">
                    <input type="date" value={(f.safeguarding_expires_on || '').slice(0, 10)} onChange={(e) => up('safeguarding_expires_on')(e.target.value)} className={inputClass} data-testid="mbr-instructor-sg-expires" />
                  </Field>
                </div>
              </div>

              <div className="rounded-lg border border-[color:var(--theme-border)] p-4 space-y-3">
                <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] flex items-center gap-1.5">
                  <AlertTriangle size={11} /> First aid certificate
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Completed on">
                    <input type="date" value={(f.first_aid_completed_on || '').slice(0, 10)} onChange={(e) => up('first_aid_completed_on')(e.target.value)} className={inputClass} data-testid="mbr-instructor-fa-completed" />
                  </Field>
                  <Field label="Expires on">
                    <input type="date" value={(f.first_aid_expires_on || '').slice(0, 10)} onChange={(e) => up('first_aid_expires_on')(e.target.value)} className={inputClass} data-testid="mbr-instructor-fa-expires" />
                  </Field>
                </div>
              </div>

              <div className="rounded-lg border border-[color:var(--theme-border)] p-4 space-y-3">
                <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] flex items-center gap-1.5">
                  <PoundSterling size={11} /> Payroll
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Hourly rate (GBP)" hint="Used when a class has no flat rate set on the template.">
                    <input
                      type="number" step="0.01" min="0"
                      value={f.hourly_rate_pence === '' || f.hourly_rate_pence == null ? '' : (Number(f.hourly_rate_pence) / 100).toFixed(2)}
                      onChange={(e) => {
                        const v = e.target.value;
                        up('hourly_rate_pence')(v === '' ? '' : Math.round(Number(v) * 100));
                      }}
                      className={inputClass} placeholder="e.g. 35.00" data-testid="mbr-instructor-hourly-rate" />
                  </Field>
                </div>
                <label className="flex items-center gap-2 text-sm mt-2">
                  <input type="checkbox" checked={f.substitute_available !== false}
                    onChange={(e) => up('substitute_available')(e.target.checked)}
                    data-testid="mbr-instructor-substitute-toggle" />
                  <span className="text-[color:var(--theme-text)]">Available as a substitute / for cover</span>
                </label>
              </div>
            </>
          )}
        </div>

        {/* Sticky footer */}
        <div className="flex-shrink-0 bg-[color:var(--theme-surface)] border-t border-[color:var(--theme-border)] p-4 flex items-center gap-3 flex-wrap">
          {!isNew && (
            <>
              <button onClick={archive} disabled={saving} className="inline-flex items-center gap-1 px-3 py-2 text-xs font-bold rounded-lg border border-rose-300 text-rose-700 bg-rose-50 hover:bg-rose-100" data-testid="mbr-instructor-archive">
                <Trash2 size={12} /> Archive
              </button>
              {initial.email && (
                <button onClick={inviteLogin} disabled={saving} className="inline-flex items-center gap-1 px-3 py-2 text-xs font-bold rounded-lg border border-[color:var(--theme-border)] text-[color:var(--theme-text)] hover:bg-[color:var(--theme-surface-hover)]" title={initial.user_id ? 'Already linked to a login' : 'Create a login + email them a magic link'} data-testid="mbr-instructor-invite">
                  <Mail size={12} /> {initial.user_id ? 'Resend invite' : 'Invite to log in'}
                </button>
              )}
            </>
          )}
          <button onClick={() => onClose(false)} className="ml-auto px-3 py-2 text-xs font-bold rounded-lg border border-[color:var(--theme-border)] text-[color:var(--theme-text)] hover:bg-[color:var(--theme-surface-hover)]" data-testid="mbr-instructor-cancel">
            Cancel
          </button>
          <button onClick={save} disabled={saving} className="px-4 py-2 text-sm font-extrabold rounded-lg bg-[color:var(--color-brand-cyan)] text-white hover:opacity-90 disabled:opacity-60" data-testid="mbr-instructor-save">
            {saving ? 'Saving…' : (isNew ? 'Create' : 'Save')}
          </button>
        </div>
        </div>
      </div>
    </div>
    ), document.body)
  );
}
