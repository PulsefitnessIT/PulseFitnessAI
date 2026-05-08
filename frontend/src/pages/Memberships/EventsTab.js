/**
 * EventsTab — Phase D (Iter 216ac)
 *
 * Event command-centre for studios:
 *   • Master event list (recitals, showcases, competitions, workshops, camps)
 *   • Per-event costume tracker (status, sizes, totals)
 *   • Rehearsal sub-schedule
 *   • AI-drafted parent comms (Claude Haiku) with one-click bulk announce
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Loader2, Plus, Trash2, Save, Sparkles, Megaphone, Theater, Mail,
  CalendarRange, Users, X, Clock, MapPin, Wand2, ChevronRight,
} from 'lucide-react';
import { notify } from '@/components/notifications';

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

  const createEvent = async () => {
    const name = window.prompt('Event name (e.g. "Spring Recital 2026")');
    if (!name) return;
    const kind = window.prompt('Type — recital, showcase, competition, workshop, camp, other', 'recital');
    if (!kind || !KIND_META[kind]) {
      notify.error('Invalid type');
      return;
    }
    const date = window.prompt('Date YYYY-MM-DD');
    if (!date) return;
    const start = window.prompt('Start time HH:MM (24h)', '18:00') || '18:00';
    const end = window.prompt('End time HH:MM (24h)', '20:00') || '20:00';
    const venue = window.prompt('Venue', '') || '';
    const ticket = parseFloat(window.prompt('Ticket price (£) — 0 for free', '15') || '0');
    const capacity = parseInt(window.prompt('Ticket capacity — 0 unlimited', '0') || '0', 10);
    try {
      const r = await axios.post(`${API}/memberships/events`, {
        name: name.trim(), kind,
        starts_at: `${date}T${start}:00Z`,
        ends_at:   `${date}T${end}:00Z`,
        venue, description: '',
        ticket_price_pence: Math.round(ticket * 100),
        ticket_capacity: capacity,
      }, auth);
      setSelectedId(r.data?.id);
      notify.success('Event created');
      await load();
    } catch (e) {
      notify.error('Create failed', e?.response?.data?.detail || e.message);
    }
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
          <button type="button" onClick={createEvent} className="px-2 py-1 rounded text-[11px] font-bold inline-flex items-center gap-1" style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff' }} data-testid="events-create">
            <Plus size={11} /> New
          </button>
        </header>
        {events.length === 0 ? (
          <div className="text-center py-8 px-3 rounded-xl border-2 border-dashed" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid="events-empty">
            <CalendarRange size={22} className="mx-auto mb-1 opacity-50" />
            <p className="text-sm font-bold">No events yet</p>
            <p className="text-xs opacity-70 mt-1">Create your first recital or showcase to start tracking costumes &amp; tickets.</p>
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

  const addRehearsal = async () => {
    const name = window.prompt('Rehearsal name', 'Tech rehearsal');
    if (!name) return;
    const date = window.prompt('Date YYYY-MM-DD');
    if (!date) return;
    const start = window.prompt('Start HH:MM', '16:00') || '16:00';
    const end = window.prompt('End HH:MM', '18:00') || '18:00';
    const room = window.prompt('Room (optional)', '') || '';
    try {
      await axios.post(`${API}/memberships/events/${event.id}/rehearsals`, {
        name: name.trim(),
        starts_at: `${date}T${start}:00Z`,
        ends_at:   `${date}T${end}:00Z`,
        room,
      }, auth);
      load();
    } catch (e) {
      notify.error('Add failed', e?.response?.data?.detail || e.message);
    }
  };

  const removeRehearsal = async (r) => {
    if (!window.confirm(`Remove "${r.name}"?`)) return;
    await axios.delete(`${API}/memberships/events/${event.id}/rehearsals/${r.id}`, auth);
    load();
  };

  const addCostume = async () => {
    const name = window.prompt('Student name');
    if (!name) return;
    const costume = window.prompt('Costume description (e.g. "Pink ballet tutu")');
    if (!costume) return;
    const size = window.prompt('Size (optional)', 'Child M') || '';
    const cost = parseFloat(window.prompt('Cost (£)', '45') || '0');
    try {
      await axios.post(`${API}/memberships/events/${event.id}/costumes`, {
        attendee_name: name.trim(),
        costume_name: costume.trim(),
        size,
        total_pence: Math.round(cost * 100),
        status: 'needed',
      }, auth);
      load();
    } catch (e) {
      notify.error('Add failed', e?.response?.data?.detail || e.message);
    }
  };

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
    </section>
  );
}
