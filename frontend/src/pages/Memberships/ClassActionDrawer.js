/**
 * Class Action Drawer — opens from a click on any class in the operator
 * Timetable. Two operator superpowers:
 *
 *   1. Announce — broadcast an email + in-app message to all attendees
 *   2. Mark attendance — quick-mark attended / no-show on every booking
 *
 * Mobile-first: drawer slides up from the bottom on small screens,
 * centered modal on lg+.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Megaphone, ListChecks, X, Send, CheckCircle2, XCircle, Loader2, Mail, Inbox, Users, MapPin, Edit3, UserPlus, Search,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { ClassTemplateEditor } from '@/pages/Memberships/StudioBuilderTab';


export default function ClassActionDrawer({ API, headers, occurrence, onClose, onChange }) {
  const [view, setView] = useState('announce');

  if (!occurrence) return null;

  return (
    <div className="fixed inset-0 z-[80] bg-black/70 grid items-end sm:place-items-center p-0 sm:p-3"
      onClick={onClose}>
      <div className="bg-[color:var(--theme-surface)] dark:bg-zinc-900 w-full max-w-2xl border border-[color:var(--theme-border)] rounded-t-2xl sm:rounded-2xl shadow-2xl flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
        data-testid="mbr-class-action-drawer">
        <div className="px-4 sm:px-5 py-3 sm:py-4 border-b border-[color:var(--theme-border)] flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[10px] uppercase tracking-[0.18em] font-extrabold text-[var(--color-brand-cyan)]">
              {occurrence.template?.name || 'Class'}
            </p>
            <h3 className="text-lg sm:text-xl font-extrabold tracking-tight mt-0.5 truncate">
              {occurrence.starts_at && new Date(occurrence.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </h3>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-[color:var(--theme-text-muted)] mt-0.5">
              {occurrence.instructor_name && <span className="truncate">{occurrence.instructor_name}</span>}
              {occurrence.template?.room_name && <span className="truncate"><MapPin size={9} className="inline mr-0.5" />{occurrence.template.room_name}</span>}
              <span><Users size={9} className="inline mr-0.5" />{occurrence.bookings_count || 0}/{occurrence.capacity || 0}</span>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-zinc-500/10 flex-shrink-0">
            <X size={14} />
          </button>
        </div>

        <div className="flex border-b border-[color:var(--theme-border)] bg-[color:var(--theme-surface-hover)] dark:bg-zinc-900/30">
          <button onClick={() => setView('announce')}
            className={`flex-1 px-3 py-2.5 text-xs font-extrabold uppercase tracking-wider flex items-center justify-center gap-1.5 ${
              view === 'announce'
                ? 'text-[var(--color-brand-cyan)] border-b-2 border-[var(--color-brand-cyan)] bg-[color:var(--theme-surface)] dark:bg-zinc-900'
                : 'text-[color:var(--theme-text-muted)]'
            }`}
            data-testid="mbr-cad-tab-announce">
            <Megaphone size={11} /> Announce
          </button>
          <button onClick={() => setView('attendance')}
            className={`flex-1 px-3 py-2.5 text-xs font-extrabold uppercase tracking-wider flex items-center justify-center gap-1.5 ${
              view === 'attendance'
                ? 'text-[var(--color-brand-cyan)] border-b-2 border-[var(--color-brand-cyan)] bg-[color:var(--theme-surface)] dark:bg-zinc-900'
                : 'text-[color:var(--theme-text-muted)]'
            }`}
            data-testid="mbr-cad-tab-attendance">
            <ListChecks size={11} /> Attendance
          </button>
          <button onClick={() => setView('edit')}
            className={`flex-1 px-3 py-2.5 text-xs font-extrabold uppercase tracking-wider flex items-center justify-center gap-1.5 ${
              view === 'edit'
                ? 'text-[var(--color-brand-cyan)] border-b-2 border-[var(--color-brand-cyan)] bg-[color:var(--theme-surface)] dark:bg-zinc-900'
                : 'text-[color:var(--theme-text-muted)]'
            }`}
            data-testid="mbr-cad-tab-edit">
            <Edit3 size={11} /> Edit class
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-5">
          {view === 'announce' && <AnnounceView API={API} headers={headers} occurrence={occurrence} />}
          {view === 'attendance' && (
            <AttendanceView API={API} headers={headers} occurrence={occurrence}
              onSaved={() => { onChange?.(); }} />
          )}
          {view === 'edit' && (
            <EditClassInline API={API} headers={headers} occurrence={occurrence}
              onSaved={() => { onChange?.(); onClose?.(); }} />
          )}
        </div>
      </div>
    </div>
  );
}


/* ────────────── Edit class template (iter 216ah · G3) ────────────── */

function EditClassInline({ API, headers, occurrence, onSaved }) {
  // Fetch the current template so we seed the editor with live data.
  const [template, setTemplate] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    axios.get(`${API}/memberships/classes/templates`, { headers })
      .then((r) => {
        if (!live) return;
        const tpl = (r.data?.templates || []).find((t) => t.id === occurrence.template_id);
        setTemplate(tpl || { id: occurrence.template_id, name: occurrence.name });
      })
      .catch(() => setTemplate({ id: occurrence.template_id, name: occurrence.name }))
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [API, headers, occurrence.template_id, occurrence.name]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[color:var(--theme-text-muted)] text-xs py-6">
        <Loader2 size={12} className="animate-spin" /> Loading class template…
      </div>
    );
  }
  if (!template) return <p className="text-xs text-[color:var(--theme-text-muted)]">Template not found.</p>;

  // Reuse the Studio Builder editor — same shape, same backend. Renders
  // its own modal overlay, so here we just mount it.
  return (
    <div className="text-xs text-[color:var(--theme-text-muted)] pb-2" data-testid="mbr-cad-edit-wrap">
      <p className="mb-2">
        Editing the template will update every future occurrence. Past occurrences are preserved.
      </p>
      <ClassTemplateEditor
        API={API} auth={{ headers }}
        initial={template}
        onSaved={onSaved}
        onClose={onSaved}
      />
    </div>
  );
}


/* ────────────── Announce ────────────── */


function AnnounceView({ API, headers, occurrence }) {
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [channels, setChannels] = useState({ email: true, in_app: true });
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    axios.get(`${API}/memberships/occurrences/${occurrence.id}/announcements`, { headers })
      .then((r) => setHistory(r.data?.announcements || []))
      .catch(() => {});
  }, [API, headers, occurrence.id]);

  const send = async () => {
    if (!message.trim()) { notify.error('Type a message'); return; }
    const selected = Object.entries(channels).filter(([, v]) => v).map(([k]) => k);
    if (selected.length === 0) { notify.error('Pick at least one channel'); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/memberships/occurrences/${occurrence.id}/announce`,
        { title: title.trim(), message: message.trim(), channels: selected },
        { headers });
      const sent = r.data?.sent_count || 0;
      notify.success(sent ? `Announced to ${sent} attendee${sent === 1 ? '' : 's'}` : 'No attendees to notify yet');
      setTitle('');
      setMessage('');
      // Refresh history
      const h = await axios.get(`${API}/memberships/occurrences/${occurrence.id}/announcements`, { headers });
      setHistory(h.data?.announcements || []);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to announce');
    }
    setBusy(false);
  };

  return (
    <div className="space-y-3">
      <p className="text-xs text-[color:var(--theme-text-muted)] -mt-1 mb-1">
        Sends to every booked, waitlisted, or attended member.
      </p>

      <label className="block">
        <span className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)]">Title (optional)</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="Studio change · Bring a towel · …"
          maxLength={120}
          className="mt-1 w-full px-3 py-2 rounded-md text-sm bg-[color:var(--theme-surface-hover)] border border-[color:var(--theme-border)] focus:outline-none focus:border-[var(--color-brand-cyan)]"
          data-testid="mbr-cad-ann-title" />
      </label>

      <label className="block">
        <span className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)]">Message *</span>
        <textarea value={message} onChange={(e) => setMessage(e.target.value)}
          rows={4} maxLength={1500}
          placeholder="We've moved tonight's class to Studio B — see you there!"
          className="mt-1 w-full px-3 py-2 rounded-md text-sm bg-[color:var(--theme-surface-hover)] border border-[color:var(--theme-border)] focus:outline-none focus:border-[var(--color-brand-cyan)] resize-y"
          data-testid="mbr-cad-ann-message" />
        <span className="block text-[10px] text-[color:var(--theme-text-muted)] mt-1">
          {message.length}/1500
        </span>
      </label>

      <div>
        <p className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)] mb-1">Channels</p>
        <div className="flex gap-2 flex-wrap">
          <ChannelToggle active={channels.email} icon={Mail} label="Email"
            onClick={() => setChannels((p) => ({ ...p, email: !p.email }))}
            testid="mbr-cad-ann-channel-email" />
          <ChannelToggle active={channels.in_app} icon={Inbox} label="In-app"
            onClick={() => setChannels((p) => ({ ...p, in_app: !p.in_app }))}
            testid="mbr-cad-ann-channel-in_app" />
        </div>
      </div>

      <button onClick={send} disabled={busy || !message.trim()}
        className="w-full sm:w-auto sm:self-end px-4 py-2.5 rounded-md text-sm font-extrabold disabled:opacity-60 flex items-center justify-center gap-1.5"
        style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
        data-testid="mbr-cad-ann-send">
        {busy ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
        Send announcement
      </button>

      {history.length > 0 && (
        <div className="mt-5 pt-4 border-t border-[color:var(--theme-border)]">
          <p className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)] mb-2">Past announcements</p>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {history.map((a) => (
              <div key={a.id}
                className="rounded-lg border border-[color:var(--theme-border)] p-2.5"
                data-testid={`mbr-cad-ann-history-${a.id}`}>
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <p className="text-xs font-extrabold">{a.title}</p>
                  <span className="text-[10px] text-[color:var(--theme-text-muted)]">
                    {new Date(a.sent_at).toLocaleString()}
                  </span>
                  <span className="text-[10px] text-[color:var(--theme-text-muted)] ml-auto">
                    {a.recipient_count} recipient{a.recipient_count === 1 ? '' : 's'}
                  </span>
                </div>
                <p className="text-[12px] whitespace-pre-wrap text-[color:var(--theme-text-muted)] line-clamp-3">{a.message}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


function ChannelToggle({ active, icon: Icon, label, onClick, testid }) {
  return (
    <button onClick={onClick}
      className={`px-2.5 py-1.5 rounded-md text-[11px] font-bold border flex items-center gap-1 ${
        active
          ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] border-[var(--color-brand-cyan)]'
          : 'bg-transparent border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]'
      }`}
      data-testid={testid}>
      <Icon size={10} /> {label}
    </button>
  );
}


/* ────────────── Attendance ────────────── */


function AttendanceView({ API, headers, occurrence, onSaved }) {
  const [bookings, setBookings] = useState([]);
  const [marks, setMarks] = useState({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showAdd, setShowAdd] = useState(false);

  const load = () => {
    setLoading(true);
    axios.get(`${API}/memberships/occurrences/${occurrence.id}/roster`, { headers })
      .then((r) => setBookings(r.data?.roster || []))
      .catch(async () => {
        // Operator endpoint not present? fall back to bookings list.
        try {
          const r = await axios.get(`${API}/memberships/bookings?occurrence_id=${occurrence.id}`, { headers });
          setBookings(r.data?.bookings || []);
        } catch { setBookings([]); }
      })
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- todo: review missing dep(s) 'load'; pre-existing as of iter 216h226-polish-5.
  useEffect(() => { load();   }, []);

  const set = (id, status) => setMarks((p) => ({ ...p, [id]: p[id] === status ? null : status }));

  const markAllPresent = () => {
    const next = {};
    bookings.forEach((b) => {
      if (b.status === 'booked' || b.status === 'attended') next[b.id] = 'attended';
    });
    setMarks(next);
  };

  const submit = async () => {
    const items = Object.entries(marks).filter(([, s]) => !!s).map(([booking_id, status]) => ({ booking_id, status }));
    if (items.length === 0) { notify.error('No marks to save'); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/memberships/occurrences/${occurrence.id}/attendance`,
        { items }, { headers });
      notify.success(`${r.data?.attended_added || 0} attended · ${r.data?.no_show_added || 0} no-show`);
      setMarks({});
      load();
      onSaved?.();
    } catch (e) {
      notifyApiError(notify, e, 'Failed');
    }
    setBusy(false);
  };

  if (loading) return (
    <div className="flex items-center justify-center py-10 text-[color:var(--theme-text-muted)] text-sm gap-2">
      <Loader2 size={14} className="animate-spin" /> Loading roster…
    </div>
  );

  if (bookings.length === 0) {
    return (
      <div>
        <div className="text-center py-10">
          <Users size={32} className="mx-auto text-[color:var(--theme-text-muted)] mb-3" />
          <p className="text-sm font-bold">No bookings yet</p>
          <button onClick={() => setShowAdd(true)}
            className="mt-3 inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-extrabold"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="mbr-cad-add-member-empty">
            <UserPlus size={11} /> Add member
          </button>
        </div>
        {showAdd && (
          <AddMemberPicker API={API} headers={headers} occurrence={occurrence}
            onDone={() => { setShowAdd(false); load(); onSaved?.(); }}
            onClose={() => setShowAdd(false)} />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => setShowAdd(true)}
          className="px-2.5 py-1 rounded-md text-[11px] font-extrabold inline-flex items-center gap-1"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid="mbr-cad-add-member">
          <UserPlus size={10} /> Add member
        </button>
        <button onClick={markAllPresent}
          className="px-2.5 py-1 rounded-md text-[11px] font-bold border border-emerald-400/40 text-emerald-500 hover:bg-emerald-500/10 flex items-center gap-1"
          data-testid="mbr-cad-att-all-present">
          <CheckCircle2 size={10} /> Mark all present
        </button>
        <button onClick={() => setMarks({})}
          className="px-2.5 py-1 rounded-md text-[11px] font-bold border border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]"
          data-testid="mbr-cad-att-clear">
          Clear
        </button>
        <span className="ml-auto text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)]">
          {Object.values(marks).filter(Boolean).length}/{bookings.length} marked
        </span>
      </div>

      <div className="space-y-2 max-h-[40vh] overflow-y-auto -mx-1 px-1">
        {bookings.map((b) => {
          const mark = marks[b.id] ?? (b.status === 'attended' ? 'attended' : b.status === 'no_show' ? 'no_show' : null);
          const memberName = b.member?.name || b.attendee_name || b.member_name || '—';
          return (
            <div key={b.id}
              className="rounded-lg border border-[color:var(--theme-border)] bg-white/[0.03] p-2.5 flex items-center gap-2"
              data-testid={`mbr-cad-att-row-${b.id}`}>
              <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.15)] grid place-items-center text-[var(--color-brand-cyan)] font-extrabold text-[11px]">
                {(memberName || '?').slice(0, 1).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold truncate">{memberName}</p>
                <p className="text-[10px] text-[color:var(--theme-text-muted)] truncate">
                  {b.member?.email || b.attendee_email || ''}
                  {b.attendee_kind && b.attendee_kind !== 'self' && (
                    <span className="ml-1 text-fuchsia-400 uppercase font-bold">· {b.attendee_kind}</span>
                  )}
                </p>
              </div>
              <div className="flex gap-1 flex-shrink-0">
                <button onClick={() => set(b.id, 'attended')}
                  className={`p-1.5 rounded-md ${
                    mark === 'attended'
                      ? 'bg-emerald-500 text-white'
                      : 'border border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]'
                  }`}
                  title="Attended"
                  data-testid={`mbr-cad-att-mark-${b.id}-attended`}>
                  <CheckCircle2 size={13} />
                </button>
                <button onClick={() => set(b.id, 'no_show')}
                  className={`p-1.5 rounded-md ${
                    mark === 'no_show'
                      ? 'bg-amber-500 text-white'
                      : 'border border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]'
                  }`}
                  title="No-show"
                  data-testid={`mbr-cad-att-mark-${b.id}-no_show`}>
                  <XCircle size={13} />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <button onClick={submit} disabled={busy || Object.values(marks).filter(Boolean).length === 0}
        className="w-full px-4 py-2.5 rounded-md text-sm font-extrabold disabled:opacity-50 flex items-center justify-center gap-1.5"
        style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
        data-testid="mbr-cad-att-save">
        {busy ? <Loader2 size={12} className="animate-spin" /> : <ListChecks size={12} />}
        Save attendance
      </button>

      {showAdd && (
        <AddMemberPicker API={API} headers={headers} occurrence={occurrence}
          onDone={() => { setShowAdd(false); load(); onSaved?.(); }}
          onClose={() => setShowAdd(false)} />
      )}
    </div>
  );
}


/* ────────────── Operator booking picker (iter 216ah · G4) ────────────── */

function AddMemberPicker({ API, headers, occurrence, onDone, onClose }) {
  const [query, setQuery] = useState('');
  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [booking, setBooking] = useState(false);

  useEffect(() => {
    let live = true;
    axios.get(`${API}/memberships/members`, { headers })
      .then((r) => { if (live) setRows(r.data?.members || []); })
      .catch(() => {})
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [API, headers]);

  const filtered = rows.filter((m) => {
    if (m.archived) return false;
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const full = `${m.first_name || ''} ${m.last_name || ''} ${m.email || ''}`.toLowerCase();
    return full.includes(q);
  }).slice(0, 60);

  const toggle = (id) => setSelected((s) => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const bookAll = async () => {
    if (selected.size === 0) return;
    setBooking(true);
    try {
      const r = await axios.post(
        `${API}/memberships/occurrences/${occurrence.id}/bookings`,
        { member_ids: Array.from(selected), allow_waitlist: true, bypass_credits: true },
        { headers },
      );
      const { booked = 0, waitlisted = 0, skipped = 0 } = r.data || {};
      notify.success(
        booked && waitlisted
          ? `${booked} booked, ${waitlisted} waitlisted`
          : waitlisted
          ? `${waitlisted} added to the waitlist`
          : `${booked} booked${skipped ? ` · ${skipped} skipped (already in class)` : ''}`,
      );
      onDone?.();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to book');
    }
    setBooking(false);
  };

  return (
    <div className="fixed inset-0 z-[100] bg-black/60 grid items-end sm:place-items-center p-0 sm:p-3" onClick={onClose} data-testid="mbr-cad-add-picker">
      <div className="w-full max-w-lg rounded-t-2xl sm:rounded-2xl shadow-2xl flex flex-col max-h-[80vh] bg-[color:var(--theme-surface)] dark:bg-zinc-900 border border-[color:var(--theme-border)]"
        onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-3 flex items-start justify-between border-b border-[color:var(--theme-border)]">
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] font-extrabold text-[var(--color-brand-cyan)]">Add to class</p>
            <h3 className="text-base font-extrabold">Book members into {occurrence.name}</h3>
            <p className="text-[10px] text-[color:var(--theme-text-muted)] mt-0.5">
              Credits aren't deducted for operator bookings.
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-white/5"><X size={14} /></button>
        </div>
        <div className="px-4 py-2 border-b border-[color:var(--theme-border)]">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[color:var(--theme-text-muted)]" />
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="Search members by name or email…"
              autoFocus
              className="w-full pl-7 pr-2 py-2 rounded-md text-xs border border-[color:var(--theme-border)] bg-transparent focus:outline-none focus:border-[var(--color-brand-cyan)]"
              data-testid="mbr-cad-add-search" />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="flex items-center gap-2 text-xs p-4 text-[color:var(--theme-text-muted)]">
              <Loader2 size={12} className="animate-spin" /> Loading…
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-xs p-4 text-[color:var(--theme-text-muted)]">No matching members.</p>
          ) : filtered.map((m) => {
            const label = `${m.first_name || ''} ${m.last_name || ''}`.trim() || m.email || m.id;
            const isSel = selected.has(m.id);
            return (
              <button key={m.id} type="button" onClick={() => toggle(m.id)}
                className={`w-full flex items-center gap-2 px-3 py-2 text-left text-xs rounded-md ${isSel ? 'bg-[var(--color-brand-cyan)]/10' : 'hover:bg-white/5'}`}
                data-testid={`mbr-cad-add-row-${m.id}`}>
                <div className={`w-4 h-4 rounded border flex items-center justify-center ${isSel ? 'bg-[var(--color-brand-cyan)] border-transparent' : 'border-[color:var(--theme-border)]'}`}>
                  {isSel && <CheckCircle2 size={10} className="text-[color:var(--color-surface-darker)]" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-bold truncate">{label}</p>
                  {m.email && <p className="text-[10px] text-[color:var(--theme-text-muted)] truncate">{m.email}</p>}
                </div>
              </button>
            );
          })}
        </div>
        <div className="px-4 py-3 flex items-center justify-between gap-2 border-t border-[color:var(--theme-border)]">
          <span className="text-[11px] font-bold text-[color:var(--theme-text-muted)]">
            {selected.size} selected
          </span>
          <div className="flex items-center gap-2">
            <button onClick={onClose} className="px-3 py-1.5 text-xs font-bold rounded-lg border border-[color:var(--theme-border)]">Cancel</button>
            <button onClick={bookAll} disabled={booking || selected.size === 0}
              className="px-4 py-1.5 text-xs font-extrabold rounded-lg inline-flex items-center gap-1.5 disabled:opacity-50"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
              data-testid="mbr-cad-add-confirm">
              {booking ? <Loader2 size={11} className="animate-spin" /> : <UserPlus size={11} />}
              Book {selected.size || ''}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
