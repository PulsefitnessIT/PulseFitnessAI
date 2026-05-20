/**
 * EventsTab — Phase D (Iter 216ac)
 *
 * Event command-centre for studios:
 *   • Master event list (recitals, showcases, competitions, workshops, camps)
 *   • Per-event costume tracker (status, sizes, totals)
 *   • Rehearsal sub-schedule
 *   • AI-drafted parent comms (Claude Haiku) with one-click bulk announce
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Loader2, Plus, Trash2, Sparkles, Megaphone, Theater,
  CalendarRange, Users, X, Clock, MapPin, Wand2, ChevronRight,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { ModalShell, ModalActions, Input, Select } from '@/pages/Memberships/_shared';

const KIND_META = {
  recital:     { label: 'Recital',     emoji: 'R', tone: '#a855f7' },
  showcase:    { label: 'Showcase',    tone: '#ec4899' },
  competition: { label: 'Competition', tone: '#f97316' },
  workshop:    { label: 'Workshop',    tone: '#10b981' },
  camp:        { label: 'Camp',        tone: '#3b82f6' },
  other:       { label: 'Event',       tone: '#64748b' },
};

const COSTUME_TONES = {
  needed:   '#94a3b8',
  ordered:  '#f59e0b',
  arrived:  '#3b82f6',
  fitted:   '#10b981',
  paid:     '#16a34a',
  refunded: '#ef4444',
};
const COSTUME_NEXT = {
  needed: 'ordered', ordered: 'arrived', arrived: 'fitted', fitted: 'paid',
};

const fmtGBP = (p) => `£${(((p ?? 0) / 100) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtDT = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); }
  catch { return iso.slice(0, 16); }
};

export default function EventsTab({ API, headers }) {
  const auth = useMemo(() => ({ headers }), [headers]);
  const [loading, setLoading] = useState(true);
  const [events, setEvents] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  // Iter 216h250 — replaced the window.prompt() chain (which silently
  // cancelled the event when the user typed a kind that wasn't in
  // KIND_META) with a proper Pulse-themed modal that exposes the kind
  // values as a dropdown.
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/memberships/events`, auth);
      const rows = r.data?.events || [];
      setEvents(rows);
      if (!selectedId && rows.length) setSelectedId(rows[0].id);
    } catch (e) {
      notify.error('Failed to load events', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [API, auth, selectedId]);
  useEffect(() => { load(); }, [load]);

  const handleCreated = (id) => {
    setSelectedId(id);
    setCreateOpen(false);
    load();
  };

  const archiveEvent = async (event) => {
    if (!window.confirm(`Archive "${event.name}"? Tickets and costumes are preserved.`)) return;
    try {
      await axios.delete(`${API}/memberships/events/${event.id}`, auth);
      if (selectedId === event.id) setSelectedId(null);
      await load();
    } catch (e) {
      notify.error('Archive failed', e?.response?.data?.detail || e.message);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground p-6" data-testid="events-tab-loading">
        <Loader2 size={14} className="animate-spin" /> Loading events…
      </div>
    );
  }

  const selected = events.find((e) => e.id === selectedId);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px,1fr] gap-4" data-testid="events-tab">
      {/* Master list */}
      <aside className="rounded-2xl border p-3" style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }} data-testid="events-list-card">
        <header className="flex items-center justify-between mb-2">
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
            <Theater size={11} /> Events
          </p>
          <button type="button" onClick={() => setCreateOpen(true)} className="px-2 py-1 rounded text-[11px] font-bold inline-flex items-center gap-1" style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff' }} data-testid="events-create">
            <Plus size={11} /> New
          </button>
        </header>
        {events.length === 0 ? (
          <div className="text-center py-8 px-3 rounded-xl border-2 border-dashed" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid="events-empty">
            <CalendarRange size={22} className="mx-auto mb-1 opacity-50" />
            <p className="text-sm font-bold">No events yet</p>
            <p className="text-xs opacity-70 mt-1">Create your first recital or showcase to start tracking costumes &amp; tickets.</p>
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="mt-3 inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-extrabold"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
              data-testid="events-empty-create"
            >
              <Plus size={12} /> Create event
            </button>
          </div>
        ) : (
          <ul className="space-y-1.5" data-testid="events-list">
            {events.map((ev) => {
              const meta = KIND_META[ev.kind] || KIND_META.other;
              const active = ev.id === selectedId;
              return (
                <li key={ev.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(ev.id)}
                    className={`w-full text-left rounded-lg p-2.5 border transition-all ${active ? 'ring-2' : ''}`}
                    style={{
                      borderColor: active ? meta.tone : 'var(--theme-border, #e2e8f0)',
                      background: active ? `${meta.tone}14` : 'transparent',
                      cursor: 'pointer', color: 'inherit',
                    }}
                    data-testid={`events-list-${ev.id}`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: meta.tone, color: '#fff' }}>
                        {meta.label}
                      </span>
                      <span className="text-[10px] opacity-60 tabular-nums ml-auto">{(ev.starts_at || '').slice(0, 10)}</span>
                    </div>
                    <p className="text-sm font-bold mt-1 truncate">{ev.name}</p>
                    <p className="text-[11px] opacity-70 truncate">{ev.venue || 'Venue TBC'}</p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </aside>

      {/* Detail */}
      {selected ? (
        <EventDetailCard
          API={API}
          auth={auth}
          event={selected}
          onChanged={load}
          onArchive={archiveEvent}
        />
      ) : (
        <div className="rounded-2xl border-2 border-dashed p-12 text-center" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid="events-detail-empty">
          <Theater size={28} className="mx-auto mb-2 opacity-50" />
          <p className="text-sm font-bold">Select or create an event to start</p>
        </div>
      )}
      {createOpen && (
        <CreateEventModal
          API={API}
          auth={auth}
          onClose={() => setCreateOpen(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Detail
// ─────────────────────────────────────────────────────────────────
function EventDetailCard({ API, auth, event, onChanged, onArchive }) {
  const [rehearsals, setRehearsals] = useState([]);
  const [costumes, setCostumes] = useState([]);
  const [costumeSummary, setCostumeSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [draft, setDraft] = useState({ subject: '', body_html: '', audience: 'all_members' });
  const [announcing, setAnnouncing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, c] = await Promise.all([
        axios.get(`${API}/memberships/events/${event.id}/rehearsals`, auth),
        axios.get(`${API}/memberships/events/${event.id}/costumes`, auth),
      ]);
      setRehearsals(r.data?.rehearsals || []);
      setCostumes(c.data?.costumes || []);
      setCostumeSummary(c.data?.summary || {});
    } finally { setLoading(false); }
  }, [API, auth, event.id]);
  useEffect(() => { load(); }, [load]);

  const meta = KIND_META[event.kind] || KIND_META.other;

  const addRehearsal = () => setRehearsalOpen(true);

  const removeRehearsal = async (r) => {
    if (!window.confirm(`Remove "${r.name}"?`)) return;
    await axios.delete(`${API}/memberships/events/${event.id}/rehearsals/${r.id}`, auth);
    load();
  };

  const addCostume = () => setCostumeOpen(true);

  const [rehearsalOpen, setRehearsalOpen] = useState(false);
  const [costumeOpen, setCostumeOpen] = useState(false);

  const advanceCostume = async (c) => {
    const next = COSTUME_NEXT[c.status];
    if (!next) return;
    try {
      await axios.patch(`${API}/memberships/events/${event.id}/costumes/${c.id}`, {
        status: next,
      }, auth);
      load();
    } catch (e) {
      notify.error('Update failed', e?.response?.data?.detail || e.message);
    }
  };
  const removeCostume = async (c) => {
    if (!window.confirm(`Remove costume for ${c.attendee_name}?`)) return;
    await axios.delete(`${API}/memberships/events/${event.id}/costumes/${c.id}`, auth);
    load();
  };

  const draftWithAI = async () => {
    setAiBusy(true);
    setAiOpen(true);
    try {
      const r = await axios.post(`${API}/memberships/events/${event.id}/ai-comms`, {}, auth);
      setDraft({
        subject: r.data?.subject || `${event.name} — important update`,
        body_html: r.data?.body_html || '',
        audience: 'all_members',
      });
    } catch (e) {
      notify.error('AI draft failed', e?.response?.data?.detail || e.message);
    } finally { setAiBusy(false); }
  };

  const sendAnnouncement = async () => {
    if (!draft.subject.trim() || !draft.body_html.trim()) {
      notify.error('Need subject and body');
      return;
    }
    setAnnouncing(true);
    try {
      const r = await axios.post(`${API}/memberships/events/${event.id}/announce`, draft, auth);
      notify.success('Announcement sent', `${r.data?.sent ?? 0} of ${r.data?.audience_size ?? 0} delivered`);
      setAiOpen(false);
      onChanged && onChanged();
    } catch (e) {
      notify.error('Send failed', e?.response?.data?.detail || e.message);
    } finally { setAnnouncing(false); }
  };

  return (
    <section className="rounded-2xl border" style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }} data-testid="events-detail">
      <header className="p-4 border-b flex items-start gap-3 flex-wrap" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }}>
        <div className="rounded-full p-2.5" style={{ background: `${meta.tone}1f` }}>
          <Theater size={18} style={{ color: meta.tone }} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60">{meta.label}</p>
          <h2 className="text-lg font-bold">{event.name}</h2>
          <div className="text-[12px] opacity-70 mt-1 flex flex-wrap items-center gap-2">
            <Clock size={11} /> {fmtDT(event.starts_at)} → {fmtDT(event.ends_at).split(', ').slice(-1)[0]}
            {event.venue ? (<><MapPin size={11} className="ml-2" /> {event.venue}</>) : null}
            {event.ticket_capacity > 0 ? (
              <><Users size={11} className="ml-2" /> {event.tickets_sold ?? 0}/{event.ticket_capacity} tickets</>
            ) : null}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={draftWithAI} className="px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5" style={{ background: '#a855f7', color: '#fff' }} data-testid="events-ai-draft">
            <Sparkles size={11} /> AI draft comms
          </button>
          <button type="button" onClick={() => onArchive(event)} className="px-2 py-1 rounded text-[11px] border" style={{ borderColor: 'var(--theme-border)' }} data-testid="events-archive">
            <Trash2 size={11} />
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4">
        {/* Rehearsals */}
        <div className="rounded-xl border p-3" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid="events-rehearsals">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
              <CalendarRange size={11} /> Rehearsals
            </p>
            <button type="button" onClick={addRehearsal} className="px-2 py-1 rounded text-[11px] font-bold inline-flex items-center gap-1" style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff' }} data-testid="events-rehearsal-add">
              <Plus size={11} /> Add
            </button>
          </div>
          {loading ? <Loader2 size={14} className="animate-spin" /> : rehearsals.length === 0 ? (
            <p className="text-[11px] opacity-60 italic">No rehearsals scheduled — add one to keep parents informed.</p>
          ) : (
            <ul className="space-y-1.5" data-testid="events-rehearsal-list">
              {rehearsals.map((r) => (
                <li key={r.id} className="flex items-start gap-2 p-2 rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`events-rehearsal-${r.id}`}>
                  <Clock size={12} className="mt-0.5 opacity-60" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-bold truncate">{r.name}</p>
                    <p className="text-[11px] opacity-70 tabular-nums">{fmtDT(r.starts_at)}{r.room ? ` · ${r.room}` : ''}</p>
                  </div>
                  <button type="button" onClick={() => removeRehearsal(r)} className="opacity-60 hover:opacity-100" style={{ background: 'none', border: 0, cursor: 'pointer', color: 'inherit', padding: 0 }} data-testid={`events-rehearsal-remove-${r.id}`}>
                    <X size={12} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Costumes */}
        <div className="rounded-xl border p-3" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid="events-costumes">
          <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
            <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
              <Users size={11} /> Costumes
              <span className="opacity-70 text-[10px] tabular-nums ml-1">
                {costumes.length} · {fmtGBP(costumeSummary.total_pence)} total
              </span>
            </p>
            <button type="button" onClick={addCostume} className="px-2 py-1 rounded text-[11px] font-bold inline-flex items-center gap-1" style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff' }} data-testid="events-costume-add">
              <Plus size={11} /> Add
            </button>
          </div>
          {loading ? <Loader2 size={14} className="animate-spin" /> : costumes.length === 0 ? (
            <p className="text-[11px] opacity-60 italic">No costumes tracked yet — add one per student to keep on top of orders.</p>
          ) : (
            <ul className="space-y-1.5" data-testid="events-costume-list">
              {costumes.map((c) => {
                const tone = COSTUME_TONES[c.status] || '#94a3b8';
                const next = COSTUME_NEXT[c.status];
                return (
                  <li key={c.id} className="flex items-start gap-2 p-2 rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`events-costume-${c.id}`}>
                    <span style={{ width: 6, alignSelf: 'stretch', background: tone, borderRadius: 3, flexShrink: 0 }} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-bold truncate">{c.attendee_name} <span className="opacity-60 font-normal">— {c.costume_name}</span></p>
                      <p className="text-[11px] opacity-70 tabular-nums">
                        {c.size ? `Size ${c.size} · ` : ''}
                        {fmtGBP(c.total_pence)}
                        <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase" style={{ background: `${tone}26`, color: tone }} data-testid={`events-costume-status-${c.id}`}>
                          {c.status}
                        </span>
                      </p>
                    </div>
                    {next ? (
                      <button type="button" onClick={() => advanceCostume(c)} className="px-2 py-0.5 rounded text-[10px] font-bold border inline-flex items-center gap-1" style={{ borderColor: tone, color: tone }} data-testid={`events-costume-advance-${c.id}`} title={`Mark ${next}`}>
                        <ChevronRight size={10} /> {next}
                      </button>
                    ) : null}
                    <button type="button" onClick={() => removeCostume(c)} className="opacity-60 hover:opacity-100" style={{ background: 'none', border: 0, cursor: 'pointer', color: 'inherit', padding: 0 }} data-testid={`events-costume-remove-${c.id}`}>
                      <X size={12} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {costumes.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5" data-testid="events-costume-summary">
              {Object.entries(costumeSummary.by_status || {}).map(([s, n]) => {
                const tone = COSTUME_TONES[s] || '#94a3b8';
                return (
                  <span key={s} className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase" style={{ background: `${tone}26`, color: tone }} data-testid={`events-costume-summary-${s}`}>
                    {n} {s}
                  </span>
                );
              })}
            </div>
          ) : null}
        </div>
      </div>

      {/* AI comms drawer */}
      {aiOpen ? (
        <div className="border-t p-4 space-y-2" style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'rgba(168,85,247,0.04)' }} data-testid="events-ai-comms">
          <div className="flex items-center justify-between">
            <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
              <Wand2 size={11} className="text-violet-500" /> AI-drafted parent comms
            </p>
            <button type="button" onClick={() => setAiOpen(false)} className="opacity-60 hover:opacity-100" style={{ background: 'none', border: 0, cursor: 'pointer', color: 'inherit', padding: 0 }}>
              <X size={14} />
            </button>
          </div>
          {aiBusy ? (
            <div className="flex items-center gap-2 text-xs"><Loader2 size={12} className="animate-spin" /> Claude is drafting…</div>
          ) : (
            <>
              <label className="block">
                <span className="text-[10px] font-bold opacity-70 uppercase">Subject</span>
                <input value={draft.subject} onChange={(e) => setDraft((d) => ({ ...d, subject: e.target.value }))} className="w-full px-2 py-1 text-sm rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid="events-ai-subject" />
              </label>
              <label className="block">
                <span className="text-[10px] font-bold opacity-70 uppercase">Body (HTML)</span>
                <textarea rows={9} value={draft.body_html} onChange={(e) => setDraft((d) => ({ ...d, body_html: e.target.value }))} className="w-full px-2 py-1 text-xs rounded border font-mono" style={{ borderColor: 'var(--theme-border)' }} data-testid="events-ai-body" />
              </label>
              <label className="inline-flex items-center gap-2 text-xs">
                <span className="text-[10px] font-bold opacity-70 uppercase">Audience</span>
                <select value={draft.audience} onChange={(e) => setDraft((d) => ({ ...d, audience: e.target.value }))} className="px-2 py-1 text-xs rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid="events-ai-audience">
                  <option value="all_members">All members</option>
                  <option value="event_attendees">Costumed attendees only</option>
                </select>
              </label>
              <div className="flex items-center justify-end gap-2 pt-1">
                <button type="button" onClick={draftWithAI} disabled={aiBusy} className="px-2 py-1 rounded text-[11px] border" style={{ borderColor: 'var(--theme-border)' }} data-testid="events-ai-redraft">
                  <Sparkles size={11} className="inline mr-1" /> Re-draft
                </button>
                <button type="button" onClick={sendAnnouncement} disabled={announcing} className="px-3 py-1.5 rounded text-xs font-bold inline-flex items-center gap-1.5" style={{ background: '#10b981', color: '#fff', opacity: announcing ? 0.6 : 1 }} data-testid="events-ai-send">
                  {announcing ? <Loader2 size={11} className="animate-spin" /> : <Megaphone size={11} />}
                  Send announcement
                </button>
              </div>
            </>
          )}
        </div>
      ) : null}
      {rehearsalOpen && (
        <RehearsalModal
          API={API}
          auth={auth}
          eventId={event.id}
          onClose={() => setRehearsalOpen(false)}
          onSaved={() => { setRehearsalOpen(false); load(); }}
        />
      )}
      {costumeOpen && (
        <CostumeModal
          API={API}
          auth={auth}
          eventId={event.id}
          onClose={() => setCostumeOpen(false)}
          onSaved={() => { setCostumeOpen(false); load(); }}
        />
      )}
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────
// Modals (Iter 216h250) — replace window.prompt() chains with
// Pulse-themed dialogs. The kind picker is a <select> bound to
// KIND_META so the silent "Invalid type" reject can't happen
// (user can only pick valid values).
// ─────────────────────────────────────────────────────────────────

function CreateEventModal({ API, auth, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: '', kind: 'recital',
    date: '', start: '18:00', end: '20:00',
    venue: '', ticket_price: '15', capacity: '0',
  });
  // Iter 216h251 — auto-populate rehearsals & costumes for the picked
  // kind. Default ON for kinds that benefit (recital / showcase /
  // competition). Operator can untick before saving.
  const [useTemplate, setUseTemplate] = useState(true);
  const [saving, setSaving] = useState(false);
  const up = (k) => (v) => setForm((p) => ({ ...p, [k]: v }));

  const templatedKinds = new Set(['recital', 'showcase', 'competition']);
  const templateApplies = templatedKinds.has(form.kind);

  const submit = async () => {
    if (!form.name.trim()) { notify.error('Event name required'); return; }
    if (!form.date) { notify.error('Date required'); return; }
    setSaving(true);
    try {
      const r = await axios.post(`${API}/memberships/events`, {
        name: form.name.trim(),
        kind: form.kind,
        starts_at: `${form.date}T${form.start}:00Z`,
        ends_at:   `${form.date}T${form.end}:00Z`,
        venue: form.venue || '',
        description: '',
        ticket_price_pence: Math.round((parseFloat(form.ticket_price) || 0) * 100),
        ticket_capacity: parseInt(form.capacity, 10) || 0,
      }, auth);
      const newId = r.data?.id;

      // Iter 216h251 — bootstrap from kind. Best-effort: a failure here
      // doesn't roll back the event itself — the operator can add
      // rehearsals/costumes manually if the template call fails.
      if (newId && useTemplate && templateApplies) {
        try {
          const b = await axios.post(
            `${API}/memberships/events/${newId}/bootstrap-from-kind`,
            { include_rehearsals: true, include_costumes: true },
            auth,
          );
          const rc = b.data?.rehearsals_created ?? 0;
          const cc = b.data?.costumes_created ?? 0;
          if (rc || cc) {
            notify.success('Event created', `${rc} rehearsal${rc === 1 ? '' : 's'} · ${cc} costume row${cc === 1 ? '' : 's'} added from template`);
          } else {
            notify.success('Event created');
          }
        } catch {
          notify.success('Event created');
        }
      } else {
        notify.success('Event created');
      }
      onCreated?.(newId);
    } catch (e) {
      notify.error('Create failed', e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const kindOptions = Object.entries(KIND_META).map(([value, meta]) => ({ value, label: meta.label }));

  return (
    <ModalShell title="New event" eyebrow="Studio events" testId="events-create-modal" onClose={onClose} wide>
      <Input label="Event name" value={form.name} onChange={up('name')} required testid="events-create-name" placeholder='e.g. "Spring Recital 2026"' />
      <Select label="Type" value={form.kind} onChange={up('kind')} options={kindOptions} testid="events-create-kind" />
      <Input label="Date" type="date" value={form.date} onChange={up('date')} required testid="events-create-date" />
      <div className="grid grid-cols-2 gap-3">
        <Input label="Start time" type="time" value={form.start} onChange={up('start')} testid="events-create-start" />
        <Input label="End time" type="time" value={form.end} onChange={up('end')} testid="events-create-end" />
      </div>
      <Input label="Venue" value={form.venue} onChange={up('venue')} testid="events-create-venue" placeholder="Optional" />
      <div className="grid grid-cols-2 gap-3">
        <Input label="Ticket price (£)" type="number" value={form.ticket_price} onChange={up('ticket_price')} testid="events-create-price" hint="0 for free" />
        <Input label="Ticket capacity" type="number" value={form.capacity} onChange={up('capacity')} testid="events-create-capacity" hint="0 = unlimited" />
      </div>
      {templateApplies && (
        <label className="flex items-start gap-2 rounded-lg p-3 border" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface-hover)' }} data-testid="events-create-template-row">
          <input
            type="checkbox"
            checked={useTemplate}
            onChange={(e) => setUseTemplate(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-[color:var(--color-brand-cyan)]"
            data-testid="events-create-template"
          />
          <span className="text-xs" style={{ color: 'var(--theme-text)' }}>
            <strong>Use {form.kind} template</strong>
            <span className="block text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
              Pre-fill rehearsals (e.g. tech + dress) and add a costume row for every active member. You can edit or delete any of them after.
            </span>
          </span>
        </label>
      )}
      <ModalActions onCancel={onClose} onSave={submit} saving={saving} testId="events-create-submit" />
    </ModalShell>
  );
}

function RehearsalModal({ API, auth, eventId, onClose, onSaved }) {
  const [form, setForm] = useState({ name: 'Tech rehearsal', date: '', start: '16:00', end: '18:00', room: '' });
  const [saving, setSaving] = useState(false);
  const up = (k) => (v) => setForm((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!form.name.trim()) { notify.error('Rehearsal name required'); return; }
    if (!form.date) { notify.error('Date required'); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/events/${eventId}/rehearsals`, {
        name: form.name.trim(),
        starts_at: `${form.date}T${form.start}:00Z`,
        ends_at:   `${form.date}T${form.end}:00Z`,
        room: form.room || '',
      }, auth);
      notify.success('Rehearsal added');
      onSaved?.();
    } catch (e) {
      notify.error('Add failed', e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  return (
    <ModalShell title="New rehearsal" eyebrow="Rehearsal schedule" testId="events-rehearsal-modal" onClose={onClose}>
      <Input label="Rehearsal name" value={form.name} onChange={up('name')} required testid="events-rehearsal-name" />
      <Input label="Date" type="date" value={form.date} onChange={up('date')} required testid="events-rehearsal-date" />
      <div className="grid grid-cols-2 gap-3">
        <Input label="Start" type="time" value={form.start} onChange={up('start')} testid="events-rehearsal-start" />
        <Input label="End" type="time" value={form.end} onChange={up('end')} testid="events-rehearsal-end" />
      </div>
      <Input label="Room" value={form.room} onChange={up('room')} testid="events-rehearsal-room" placeholder="Optional" />
      <ModalActions onCancel={onClose} onSave={submit} saving={saving} testId="events-rehearsal-submit" />
    </ModalShell>
  );
}

function CostumeModal({ API, auth, eventId, onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', costume: '', size: 'Child M', cost: '45' });
  const [saving, setSaving] = useState(false);
  const up = (k) => (v) => setForm((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!form.name.trim()) { notify.error('Student name required'); return; }
    if (!form.costume.trim()) { notify.error('Costume description required'); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/events/${eventId}/costumes`, {
        attendee_name: form.name.trim(),
        costume_name: form.costume.trim(),
        size: form.size || '',
        total_pence: Math.round((parseFloat(form.cost) || 0) * 100),
        status: 'needed',
      }, auth);
      notify.success('Costume added');
      onSaved?.();
    } catch (e) {
      notify.error('Add failed', e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  return (
    <ModalShell title="New costume" eyebrow="Costume tracker" testId="events-costume-modal" onClose={onClose}>
      <Input label="Student name" value={form.name} onChange={up('name')} required testid="events-costume-name" />
      <Input label="Costume description" value={form.costume} onChange={up('costume')} required testid="events-costume-desc" placeholder='e.g. "Pink ballet tutu"' />
      <div className="grid grid-cols-2 gap-3">
        <Input label="Size" value={form.size} onChange={up('size')} testid="events-costume-size" placeholder="Optional" />
        <Input label="Cost (£)" type="number" value={form.cost} onChange={up('cost')} testid="events-costume-cost" />
      </div>
      <ModalActions onCancel={onClose} onSave={submit} saving={saving} testId="events-costume-submit" />
    </ModalShell>
  );
}
