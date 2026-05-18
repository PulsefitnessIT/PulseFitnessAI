/**
 * Iter 215bk — Memberships member edit drawer.
 *
 * Replaces the slim plan-only drawer with a full operator-grade record:
 * a side drawer (right slide) with four tabs:
 *
 *   • Profile  — name, contact, address, DOB / age, emergency contact, tags
 *   • Classes  — upcoming bookings + recent attendance + no-show count
 *   • Payments — invoices, payments history, totals + plan controls
 *                (assign, freeze, cancel, record payment) — preserves the
 *                actions that lived in the legacy drawer.
 *   • Family   — parent member linker (if this member is a child) + a list
 *                of any members linking up to this one as a parent.
 *
 * The drawer chrome matches the design-polished modal spec from iter 215bj:
 * sticky tabbed header, X close top-right, single body scroll only, white
 * surfaces on light theme. Pulse routes never load this component (it's
 * mounted only inside MembershipsConsole which is GymAxis-only).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import {
  X, Loader2, User, CalendarDays, CreditCard, Users, Activity as ActivityIcon,
  Save, Pause, XOctagon, Search, Link as LinkIcon, Plus, Mail, Phone,
  MapPin, Cake, ShieldAlert, Tag as TagIcon, FileText, AlertCircle,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import ActivityTimelineTab from '@/pages/Memberships/ActivityTimelineTab';
import Button from '@/components/shared/Button';
import { COUNTRIES, RELATIONSHIP_OPTIONS } from '@/utils/crmDropdowns';

const TABS = [
  { id: 'profile',  label: 'Profile',  icon: User },
  { id: 'classes',  label: 'Classes',  icon: CalendarDays },
  { id: 'payments', label: 'Payments', icon: CreditCard },
  { id: 'activity', label: 'Activity', icon: ActivityIcon },
  { id: 'family',   label: 'Family',   icon: Users },
];

function formatGBP(pence) {
  return `£${((Number(pence) || 0) / 100).toFixed(2)}`;
}

function calcAge(dob) {
  if (!dob) return null;
  const d = new Date(dob);
  if (Number.isNaN(d.getTime())) return null;
  const ms = Date.now() - d.getTime();
  return Math.floor(ms / (365.25 * 24 * 60 * 60 * 1000));
}

const Field = ({ label, hint, children }) => (
  <label className="block">
    <span className="block text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-1">{label}</span>
    {children}
    {hint && <span className="block text-[11px] text-[color:var(--theme-text-muted)] mt-1">{hint}</span>}
  </label>
);

const Input = ({ value, onChange, type = 'text', placeholder, testid }) => (
  <input
    type={type}
    value={value ?? ''}
    onChange={(e) => onChange(e.target.value)}
    placeholder={placeholder}
    className="w-full h-10 px-3 rounded-lg bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] text-sm text-[color:var(--theme-text)] placeholder-[color:var(--theme-text-muted)] focus:outline-none focus:border-[color:var(--color-brand-cyan)]"
    data-testid={testid}
  />
);

const Textarea = ({ value, onChange, rows = 3, placeholder, testid }) => (
  <textarea
    value={value ?? ''}
    onChange={(e) => onChange(e.target.value)}
    rows={rows}
    placeholder={placeholder}
    className="w-full px-3 py-2 rounded-lg bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] text-sm text-[color:var(--theme-text)] placeholder-[color:var(--theme-text-muted)] focus:outline-none focus:border-[color:var(--color-brand-cyan)] resize-y"
    data-testid={testid}
  />
);

const Empty = ({ text }) => (
  <div className="rounded-lg border border-dashed border-[color:var(--theme-border)] p-6 text-center text-sm text-[color:var(--theme-text-muted)]">
    {text}
  </div>
);

const StatusBadge = ({ status }) => {
  const map = {
    active:    'bg-emerald-50 text-emerald-700 border-emerald-200',
    frozen:    'bg-blue-50 text-blue-700 border-blue-200',
    cancelled: 'bg-zinc-50 text-zinc-600 border-zinc-200',
    paid:      'bg-emerald-50 text-emerald-700 border-emerald-200',
    pending:   'bg-amber-50 text-amber-700 border-amber-200',
    unpaid:    'bg-rose-50 text-rose-700 border-rose-200',
    void:      'bg-zinc-50 text-zinc-500 border-zinc-200',
    booked:    'bg-blue-50 text-blue-700 border-blue-200',
    attended:  'bg-emerald-50 text-emerald-700 border-emerald-200',
    no_show:   'bg-rose-50 text-rose-700 border-rose-200',
  };
  const tone = map[(status || '').toLowerCase()] || 'bg-zinc-50 text-zinc-600 border-zinc-200';
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded border ${tone}`}>
      {status || '—'}
    </span>
  );
};

// ── Profile tab ────────────────────────────────────────────────
function ProfileTab({ form, setForm, member, age, onSave, saving }) {
  const isMinor = age !== null && age < 18;
  return (
    <div className="space-y-5" data-testid="member-drawer-profile">
      {isMinor && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2 flex items-center gap-2 text-xs text-amber-800" data-testid="member-drawer-minor-banner">
          <ShieldAlert size={13} className="shrink-0" />
          <span>Member is under 18 ({age}). Use the <strong>Family</strong> tab to link a parent / guardian.</span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Field label="First name"><Input value={form.first_name} onChange={(v) => setForm({ ...form, first_name: v })} testid="member-drawer-first-name" /></Field>
        <Field label="Last name"><Input value={form.last_name} onChange={(v) => setForm({ ...form, last_name: v })} testid="member-drawer-last-name" /></Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Email"><Input type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} testid="member-drawer-email" /></Field>
        <Field label="Phone"><Input value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} testid="member-drawer-phone" /></Field>
      </div>
      <Field label="Date of birth" hint={age !== null ? `Age ${age}` : undefined}>
        <Input type="date" value={(form.dob || '').slice(0, 10)} onChange={(v) => setForm({ ...form, dob: v })} testid="member-drawer-dob" />
      </Field>

      <div className="pt-1">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2 flex items-center gap-1.5"><MapPin size={11} /> Address</p>
        <div className="space-y-2">
          <Input value={form.address_line1} onChange={(v) => setForm({ ...form, address_line1: v })} placeholder="Address line 1" testid="member-drawer-addr1" />
          <Input value={form.address_line2} onChange={(v) => setForm({ ...form, address_line2: v })} placeholder="Address line 2 (optional)" testid="member-drawer-addr2" />
          <div className="grid grid-cols-3 gap-2">
            <Input value={form.city} onChange={(v) => setForm({ ...form, city: v })} placeholder="City" testid="member-drawer-city" />
            <Input value={form.postcode} onChange={(v) => setForm({ ...form, postcode: v })} placeholder="Postcode" testid="member-drawer-postcode" />
            <Input value={form.country} onChange={(v) => setForm({ ...form, country: v })} placeholder="Country" list="member-drawer-country-list" testid="member-drawer-country" />
          </div>
          <datalist id="member-drawer-country-list">
            {COUNTRIES.map((c) => <option key={c} value={c} />)}
          </datalist>
        </div>
      </div>

      <div className="pt-1">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2 flex items-center gap-1.5"><ShieldAlert size={11} /> Emergency contact</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name"><Input value={form.emergency_contact_name} onChange={(v) => setForm({ ...form, emergency_contact_name: v })} testid="member-drawer-eg-name" /></Field>
          <Field label="Phone"><Input value={form.emergency_contact_phone} onChange={(v) => setForm({ ...form, emergency_contact_phone: v })} testid="member-drawer-eg-phone" /></Field>
        </div>
        {/* Iter 216h195 — Relationship is now a curated dropdown so
            reports can aggregate "who's listed as Parent vs Spouse". */}
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Relationship">
            <Input
              value={form.emergency_contact_relationship || ''}
              onChange={(v) => setForm({ ...form, emergency_contact_relationship: v })}
              list="member-drawer-relationship-list"
              placeholder="Select…"
              testid="member-drawer-eg-rel"
            />
            <datalist id="member-drawer-relationship-list">
              {RELATIONSHIP_OPTIONS.map((r) => <option key={r} value={r} />)}
            </datalist>
          </Field>
        </div>
      </div>

      <Field label="Notes (operator-only)">
        <Textarea value={form.notes} onChange={(v) => setForm({ ...form, notes: v })} testid="member-drawer-notes" />
      </Field>

      <Field label="Tags (comma-separated)">
        <Input
          value={(form.tags || []).join(', ')}
          onChange={(v) => setForm({ ...form, tags: v.split(',').map((t) => t.trim()).filter(Boolean) })}
          placeholder="e.g. corporate, vip, swim-only"
          testid="member-drawer-tags"
        />
      </Field>

      <div className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface-hover)] px-3 py-2 text-[11px] text-[color:var(--theme-text-muted)] flex items-center gap-1.5">
        <Cake size={11} /> Member since {member.created_at ? new Date(member.created_at).toLocaleDateString() : '—'}
        {member.no_show_count > 0 && <span className="ml-auto text-rose-600 font-bold">{member.no_show_count} no-show{member.no_show_count === 1 ? '' : 's'}</span>}
      </div>

      <button
        type="button"
        onClick={onSave}
        disabled={saving}
        className="gx-btn-primary w-full h-10 rounded-lg text-sm font-bold disabled:opacity-60 inline-flex items-center justify-center gap-2"
        data-testid="member-drawer-save"
      >
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save profile
      </button>
    </div>
  );
}

// ── Classes tab ────────────────────────────────────────────────
function ClassesTab({ bookings }) {
  const upcoming = bookings.filter((b) => {
    const t = b.occurrence?.starts_at && new Date(b.occurrence.starts_at).getTime();
    return t && t > Date.now() && b.status !== 'cancelled';
  });
  const past = bookings.filter((b) => !upcoming.includes(b));

  const Row = ({ b }) => (
    <div className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-3 flex items-center justify-between gap-3">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-[color:var(--theme-text)] truncate">{b.occurrence?.name || '—'}</p>
        <p className="text-[11px] text-[color:var(--theme-text-muted)]">
          {b.occurrence?.starts_at ? new Date(b.occurrence.starts_at).toLocaleString() : '—'}
        </p>
      </div>
      <StatusBadge status={b.status} />
    </div>
  );

  return (
    <div className="space-y-5" data-testid="member-drawer-classes">
      <section>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Upcoming ({upcoming.length})</p>
        {upcoming.length === 0 ? <Empty text="No upcoming classes booked." /> : (
          <div className="space-y-1.5">{upcoming.map((b) => <Row key={b.id} b={b} />)}</div>
        )}
      </section>
      <section>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Recent history ({past.length})</p>
        {past.length === 0 ? <Empty text="No past bookings yet." /> : (
          <div className="space-y-1.5">{past.slice(0, 15).map((b) => <Row key={b.id} b={b} />)}</div>
        )}
      </section>
    </div>
  );
}

// ── Payments tab ───────────────────────────────────────────────
function PaymentsTab({ memberId, API, headers, memberships, plans, onAssignPlan, onFreeze, onCancel, onRecord }) {
  const [pay, setPay] = useState({ payments: [], invoices: [], totals: { paid_pence: 0, outstanding_pence: 0 } });
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/memberships/members/${memberId}/payments`, { headers });
        if (!cancelled) setPay(r.data);
      } catch (_) {
        if (!cancelled) setPay({ payments: [], invoices: [], totals: { paid_pence: 0, outstanding_pence: 0 } });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [API, headers, memberId]);

  const active = memberships.find((x) => ['active', 'frozen'].includes(x.status));

  return (
    <div className="space-y-5" data-testid="member-drawer-payments">
      {/* Plan controls */}
      <section>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Current plan</p>
        {active ? (
          <div className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div>
                <p className="text-sm font-semibold text-[color:var(--theme-text)]">{active.plan?.name || '—'}</p>
                <p className="text-[11px] text-[color:var(--theme-text-muted)]">
                  Since {new Date(active.start_date).toLocaleDateString()} · <StatusBadge status={active.status} />
                </p>
              </div>
              <p className="text-[11px] text-[color:var(--theme-text-muted)]">
                Credits <span className="font-bold text-[color:var(--theme-text)]">{active.credits_remaining ?? '∞'}</span>
              </p>
            </div>
            <div className="flex gap-2 mt-3">
              <Button variant="secondary" size="sm" onClick={onFreeze} icon={Pause} data-testid="member-drawer-freeze">Freeze</Button>
              <Button variant="destructive" size="sm" onClick={onCancel} icon={XOctagon} data-testid="member-drawer-cancel">Cancel</Button>
            </div>
          </div>
        ) : <Empty text="No active plan." />}
      </section>

      {/* Plan picker */}
      <section>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">{active ? 'Top-up or change plan' : 'Assign / sell a plan'}</p>
        <div className="space-y-1.5">
          {(plans || []).map((p) => (
            <div key={p.id} className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-3" data-testid={`member-drawer-plan-${p.id}`}>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-1 h-7 rounded" style={{ background: p.colour || 'var(--color-brand-cyan)' }} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-[color:var(--theme-text)] truncate">{p.name}</p>
                  <p className="text-[11px] text-[color:var(--theme-text-muted)]">{formatGBP(p.price_pence)} · {p.billing_cycle}</p>
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => onRecord(p)} className="gx-btn-primary flex-1 h-8 rounded-lg text-[11px] font-bold uppercase tracking-wider" data-testid={`member-drawer-record-${p.id}`}>
                  Record payment
                </button>
                <button onClick={() => onAssignPlan(p.id)} className="flex-1 h-8 rounded-lg text-[11px] font-bold uppercase tracking-wider border border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)] hover:bg-[color:var(--theme-surface-hover)]" data-testid={`member-drawer-assign-${p.id}`}>
                  Comp / assign
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Totals */}
      <section className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-3">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Lifetime paid</p>
          <p className="text-lg font-bold text-emerald-600 mt-1 tabular-nums">{formatGBP(pay.totals?.paid_pence)}</p>
        </div>
        <div className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-3">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Outstanding</p>
          <p className={`text-lg font-bold mt-1 tabular-nums ${(pay.totals?.outstanding_pence || 0) > 0 ? 'text-rose-600' : 'text-[color:var(--theme-text-muted)]'}`}>
            {formatGBP(pay.totals?.outstanding_pence)}
          </p>
        </div>
      </section>

      {/* Invoices */}
      <section>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Invoices ({(pay.invoices || []).length})</p>
        {loading ? <Empty text="Loading…" /> : (pay.invoices.length === 0 ? <Empty text="No invoices yet." /> : (
          <div className="space-y-1.5">
            {pay.invoices.slice(0, 10).map((inv) => (
              <div key={inv.id || inv._id} className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-2.5 flex items-center justify-between gap-2 text-xs" data-testid={`member-drawer-invoice-${inv.id || inv._id || 'na'}`}>
                <div className="min-w-0">
                  <p className="font-semibold text-[color:var(--theme-text)] truncate">{inv.description || inv.label || 'Invoice'}</p>
                  <p className="text-[10px] text-[color:var(--theme-text-muted)]">{inv.issued_at ? new Date(inv.issued_at).toLocaleDateString() : ''}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="font-bold tabular-nums">{formatGBP(inv.amount_pence)}</span>
                  <StatusBadge status={inv.status} />
                </div>
              </div>
            ))}
          </div>
        ))}
      </section>

      {/* Payments */}
      <section>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Payments ({(pay.payments || []).length})</p>
        {loading ? <Empty text="Loading…" /> : (pay.payments.length === 0 ? <Empty text="No payments recorded." /> : (
          <div className="space-y-1.5">
            {pay.payments.slice(0, 10).map((p) => (
              <div key={p.id || p._id} className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-2.5 flex items-center justify-between gap-2 text-xs" data-testid={`member-drawer-payment-${p.id || p._id || 'na'}`}>
                <div className="min-w-0">
                  <p className="font-semibold text-[color:var(--theme-text)] truncate">{p.method || 'Payment'}{p.reference ? ` · ${p.reference}` : ''}</p>
                  <p className="text-[10px] text-[color:var(--theme-text-muted)]">{p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="font-bold tabular-nums">{formatGBP(p.amount_pence)}</span>
                  <StatusBadge status={p.status || 'paid'} />
                </div>
              </div>
            ))}
          </div>
        ))}
      </section>
    </div>
  );
}

// ── Family tab ─────────────────────────────────────────────────
function FamilyTab({ memberId, member, API, headers, age, onSavedParent }) {
  const [parent, setParent] = useState(null);
  const [children, setChildren] = useState([]);
  const [search, setSearch] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [linking, setLinking] = useState(false);

  const reload = useCallback(async () => {
    try {
      // Resolve parent
      if (member?.parent_member_id) {
        const r = await axios.get(`${API}/memberships/members/${member.parent_member_id}`, { headers });
        setParent(r.data?.member || null);
      } else {
        setParent(null);
      }
      // Resolve children
      const c = await axios.get(`${API}/memberships/members/${memberId}/children`, { headers });
      setChildren(c.data?.children || []);
    } catch (_) { /* drawer kept light on errors */ }
  }, [API, headers, memberId, member?.parent_member_id]);
  useEffect(() => { reload(); }, [reload]);

  const runSearch = useCallback(async () => {
    if (!search.trim()) { setResults([]); return; }
    setSearching(true);
    try {
      const r = await axios.get(`${API}/memberships/members`, { headers, params: { q: search } });
      setResults((r.data?.members || []).filter((m) => m.id !== memberId).slice(0, 8));
    } catch (e) { notifyApiError(notify, e, 'Search failed'); }
    finally { setSearching(false); }
  }, [API, headers, memberId, search]);

  const link = async (parentId) => {
    setLinking(true);
    try {
      await axios.patch(`${API}/memberships/members/${memberId}`, { parent_member_id: parentId }, { headers });
      notify.success('Parent linked');
      onSavedParent && onSavedParent(parentId);
    } catch (e) { notifyApiError(notify, e, 'Failed to link parent'); }
    finally { setLinking(false); }
  };

  const unlink = async () => {
    setLinking(true);
    try {
      await axios.patch(`${API}/memberships/members/${memberId}`, { parent_member_id: null }, { headers });
      notify.success('Parent unlinked');
      onSavedParent && onSavedParent(null);
    } catch (e) { notifyApiError(notify, e, 'Failed to unlink'); }
    finally { setLinking(false); }
  };

  const isChild = age !== null && age < 18;

  return (
    <div className="space-y-5" data-testid="member-drawer-family">
      {/* Linked parent */}
      <section>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2 flex items-center gap-1.5">
          <LinkIcon size={11} /> {isChild ? 'Parent / guardian' : 'Linked parent'}
        </p>
        {parent ? (
          <div className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-3 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[color:var(--theme-text)] truncate">{parent.first_name} {parent.last_name}</p>
              <p className="text-[11px] text-[color:var(--theme-text-muted)] truncate flex items-center gap-1.5"><Mail size={10} /> {parent.email}</p>
              {parent.phone && <p className="text-[11px] text-[color:var(--theme-text-muted)] truncate flex items-center gap-1.5"><Phone size={10} /> {parent.phone}</p>}
            </div>
            <button onClick={unlink} disabled={linking} className="text-[11px] font-bold text-rose-600 hover:underline shrink-0" data-testid="member-drawer-unlink-parent">
              {linking ? '…' : 'Unlink'}
            </button>
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-[color:var(--theme-border)] bg-[color:var(--theme-surface-hover)] p-3">
            <p className="text-sm text-[color:var(--theme-text)]">No parent linked.</p>
            <p className="text-[11px] text-[color:var(--theme-text-muted)] mt-0.5">Search for an existing member to link as the parent / guardian.</p>
            <div className="mt-3 flex gap-2">
              <div className="relative flex-1">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[color:var(--theme-text-muted)]" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && runSearch()}
                  placeholder="Search by name / email"
                  className="w-full h-9 pl-7 pr-2 rounded-lg bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] text-sm text-[color:var(--theme-text)] placeholder-[color:var(--theme-text-muted)] focus:outline-none focus:border-[color:var(--color-brand-cyan)]"
                  data-testid="member-drawer-parent-search"
                />
              </div>
              <button onClick={runSearch} className="h-9 px-3 rounded-lg border border-[color:var(--theme-border)] text-sm font-bold hover:bg-[color:var(--theme-surface-hover)]" data-testid="member-drawer-parent-search-btn">
                {searching ? <Loader2 size={13} className="animate-spin" /> : 'Find'}
              </button>
            </div>
            {results.length > 0 && (
              <ul className="mt-2 space-y-1 max-h-56 overflow-y-auto">
                {results.map((r) => (
                  <li key={r.id} className="rounded-md border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-2 flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-[color:var(--theme-text)] truncate">{r.first_name} {r.last_name}</p>
                      <p className="text-[11px] text-[color:var(--theme-text-muted)] truncate">{r.email}</p>
                    </div>
                    <button onClick={() => link(r.id)} disabled={linking} className="gx-btn-primary h-8 px-3 rounded-md text-[11px] font-bold uppercase tracking-wider" data-testid={`member-drawer-link-parent-${r.id}`}>
                      <Plus size={11} /> Link
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {/* Linked children */}
      <section>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2 flex items-center gap-1.5">
          <Users size={11} /> Linked children ({children.length})
        </p>
        {children.length === 0 ? <Empty text="No members link to this profile as parent." /> : (
          <div className="space-y-1.5">
            {children.map((c) => (
              <div key={c.id} className="rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-2.5 flex items-center justify-between gap-2 text-sm" data-testid={`member-drawer-child-${c.id}`}>
                <div className="min-w-0">
                  <p className="font-semibold text-[color:var(--theme-text)] truncate">{c.first_name} {c.last_name}</p>
                  <p className="text-[11px] text-[color:var(--theme-text-muted)] truncate">{c.email}{c.dob ? ` · ${calcAge(c.dob)} yrs` : ''}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// ── Drawer ─────────────────────────────────────────────────────
export default function MemberEditDrawer({ API, headers, memberId, onClose, onAssignPlan, onFreeze, onCancel, onRecord }) {
  const [data, setData] = useState(null);
  const [plans, setPlans] = useState([]);
  const [tab, setTab] = useState('profile');
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [a, b] = await Promise.all([
        axios.get(`${API}/memberships/members/${memberId}`, { headers }),
        axios.get(`${API}/memberships/plans`, { headers }),
      ]);
      setData(a.data);
      setPlans(b.data.plans || []);
      setForm({
        first_name: a.data.member.first_name || '',
        last_name:  a.data.member.last_name  || '',
        email:      a.data.member.email      || '',
        phone:      a.data.member.phone      || '',
        address_line1: a.data.member.address_line1 || '',
        address_line2: a.data.member.address_line2 || '',
        city:       a.data.member.city       || '',
        postcode:   a.data.member.postcode   || '',
        country:    a.data.member.country    || '',
        dob:        a.data.member.dob        || '',
        emergency_contact_name:  a.data.member.emergency_contact_name  || '',
        emergency_contact_phone: a.data.member.emergency_contact_phone || '',
        notes:      a.data.member.notes      || '',
        tags:       Array.isArray(a.data.member.tags) ? a.data.member.tags : [],
      });
    } catch { notify.error('Failed to load member'); onClose(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [memberId]);
  useEffect(() => { reload(); }, [reload]);

  const age = useMemo(() => calcAge(form?.dob || data?.member?.dob), [form?.dob, data?.member?.dob]);

  const saveProfile = async () => {
    if (!form) return;
    setSaving(true);
    try {
      await axios.patch(`${API}/memberships/members/${memberId}`, form, { headers });
      notify.success('Profile saved');
      reload();
    } catch (e) { notifyApiError(notify, e, 'Failed to save'); }
    finally { setSaving(false); }
  };

  if (!data || !form) {
    return createPortal((
      <div className="fixed inset-0 z-[100] bg-black/40">
        <div className="absolute inset-x-0 top-16 bottom-16 sm:inset-0 flex justify-end">
          <div className="w-full sm:max-w-xl h-full bg-[color:var(--theme-surface)] sm:border-l border-[color:var(--theme-border)] flex items-center justify-center">
            <Loader2 size={20} className="animate-spin text-[color:var(--theme-text-muted)]" />
          </div>
        </div>
      </div>
    ), document.body);
  }

  const m = data.member;

  return createPortal((
    // Iter 215d6.2 — portaled to document.body to escape transformed
    // ancestors. Drawer respects the mobile safe zone (below Navbar,
    // above MobileBottomNav) so the header X + sticky footer are never
    // hidden by fixed chrome.
    <div className="fixed inset-0 z-[100] bg-black/40" onClick={() => onClose(false)} data-testid="member-edit-drawer">
      <div className="absolute inset-x-0 top-16 bottom-16 sm:inset-0 flex justify-end">
      <div className="w-full sm:max-w-xl h-full bg-[color:var(--theme-surface)] sm:border-l border-[color:var(--theme-border)] flex flex-col overflow-hidden" onClick={(e) => e.stopPropagation()}>
        {/* Sticky header — name + tabs */}
        <header className="flex-shrink-0 bg-[color:var(--theme-surface)] border-b border-[color:var(--theme-border)]">
          <div className="px-5 py-4 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[color:var(--color-brand-cyan)]">Member record</p>
              <h3 className="text-xl font-bold tracking-tight text-[color:var(--theme-text)] truncate">{m.first_name} {m.last_name}</h3>
              <p className="text-xs text-[color:var(--theme-text-muted)] truncate flex items-center gap-2 mt-0.5">
                <span className="inline-flex items-center gap-1"><Mail size={10} /> {m.email}</span>
                {m.phone && <span className="inline-flex items-center gap-1"><Phone size={10} /> {m.phone}</span>}
                {age !== null && <span className="inline-flex items-center gap-1"><Cake size={10} /> {age}</span>}
              </p>
              {Array.isArray(m.tags) && m.tags.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {m.tags.slice(0, 6).map((t) => (
                    <span key={t} className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider rounded bg-[color:var(--theme-surface-hover)] text-[color:var(--theme-text-muted)] border border-[color:var(--theme-border)]"><TagIcon size={8} /> {t}</span>
                  ))}
                </div>
              )}
            </div>
            <button onClick={() => onClose(false)} className="h-9 w-9 rounded-full flex items-center justify-center border border-[color:var(--theme-border)] bg-[color:var(--theme-bg,transparent)] text-[color:var(--theme-text)] hover:bg-[color:var(--theme-surface-hover)] focus:outline-none focus:ring-2 focus:ring-[color:var(--color-brand-cyan)] focus:ring-offset-1 transition-colors shrink-0" aria-label="Close" data-testid="member-drawer-close">
              <X size={18} />
            </button>
          </div>
          <nav className="px-3 pb-2 flex items-center gap-1 overflow-x-auto" role="tablist">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setTab(t.id)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors whitespace-nowrap ${
                    active
                      ? 'bg-[color:var(--color-brand-cyan)] text-white'
                      : 'text-[color:var(--theme-text-muted)] hover:bg-[color:var(--theme-surface-hover)] hover:text-[color:var(--theme-text)]'
                  }`}
                  data-testid={`member-drawer-tab-${t.id}`}
                >
                  <Icon size={12} /> {t.label}
                </button>
              );
            })}
          </nav>
        </header>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {tab === 'profile'  && <ProfileTab form={form} setForm={setForm} member={m} age={age} onSave={saveProfile} saving={saving} />}
          {tab === 'classes'  && <ClassesTab bookings={data.recent_bookings || []} />}
          {tab === 'payments' && (
            <PaymentsTab
              memberId={memberId}
              API={API}
              headers={headers}
              memberships={data.memberships || []}
              plans={plans}
              onAssignPlan={onAssignPlan}
              onFreeze={onFreeze}
              onCancel={onCancel}
              onRecord={onRecord}
            />
          )}
          {tab === 'activity' && (
            <ActivityTimelineTab memberId={memberId} API={API} headers={headers} />
          )}
          {tab === 'family'   && (
            <FamilyTab
              memberId={memberId}
              member={m}
              API={API}
              headers={headers}
              age={age}
              onSavedParent={(pid) => {
                setData((cur) => cur && ({ ...cur, member: { ...cur.member, parent_member_id: pid } }));
              }}
            />
          )}
        </div>
      </div>
      </div>
    </div>
  ), document.body);
}
