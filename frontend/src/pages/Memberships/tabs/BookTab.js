/**
 * Iter 216h173 — BookTab extracted from MemberPortal.js for lazy-loading.
 *
 * Owns the weekly timetable / book-class flow plus its co-located widgets
 * (ClassCard, FamilyBookingPicker). Pulled out so the initial portal
 * bundle no longer ships ~150 LoC of timetable logic that's only needed
 * once a member taps the Book tab.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  ChevronLeft, ChevronRight, Clock, MapPin, Users as UsersIcon, X, CreditCard,
} from 'lucide-react';
import { notify, useConfirm } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { useStudioVocab } from '@/hooks/useStudioVocab';
import {
  API, AdSlot, CenterLoader, CTAButton, EmptyCard, Pill, SocialPulse,
  formatTime, groupByDay, startOfWeek,
} from '../portalShared';
import BuyCreditPackModal from '../modals/BuyCreditPackModal';

export default function BookTab({ headers, slug }) {
  const vocab = useStudioVocab();
  const [occs, setOccs] = useState([]);
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [loading, setLoading] = useState(true);
  const [actingId, setActingId] = useState(null);
  const [familyPickerOcc, setFamilyPickerOcc] = useState(null);
  const [subProfiles, setSubProfiles] = useState([]);
  // Iter 216h202 — Lee's ask: when the booking 402s with "Need 1
  // credit", auto-open the buy-pack modal with a contextual prompt.
  const [buyPackOpen, setBuyPackOpen] = useState(false);
  const [buyPackPrompt, setBuyPackPrompt] = useState('');
  const confirmFn = useConfirm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const from = weekStart.toISOString();
      const to = new Date(weekStart.getTime() + 7 * 86400000).toISOString();
      const [tt, sps] = await Promise.all([
        axios.get(`${API}/member/timetable`, { headers, params: { from, to } }),
        axios.get(`${API}/member/sub-profiles`, { headers }).catch(() => ({ data: { sub_profiles: [] } })),
      ]);
      setOccs(tt.data.occurrences || []);
      setSubProfiles(sps.data?.sub_profiles || []);
    } catch { notify.error('Failed to load timetable'); }
    finally { setLoading(false); }
  }, [headers, weekStart]);
  useEffect(() => { load(); }, [load]);

  // Iter 216h202 — centralised 402 handler. Opens the buy-pack modal
  // with the server's "Need N credits…" message as a prompt.
  const handleBookingError = (err, fallback) => {
    if (err?.response?.status === 402) {
      setBuyPackPrompt(err?.response?.data?.detail || 'Need credits to book this class');
      setBuyPackOpen(true);
      return;
    }
    notifyApiError(notify, err, fallback);
  };

  const book = async (occ) => {
    if (subProfiles.length > 0) {
      setFamilyPickerOcc(occ);
      return;
    }
    setActingId(occ.id);
    try {
      await axios.post(`${API}/member/bookings`, { occurrence_id: occ.id }, { headers });
      notify.success(`Booked · ${occ.name}`);
      load();
    } catch (err) { handleBookingError(err, 'Failed to book'); }
    finally { setActingId(null); }
  };

  const confirmFamilyBooking = async (attendees) => {
    const occ = familyPickerOcc;
    setFamilyPickerOcc(null);
    setActingId(occ.id);
    try {
      const r = await axios.post(`${API}/member/bookings`,
        { occurrence_id: occ.id, attendees },
        { headers });
      const booked = r.data.booked ?? (r.data.booking ? 1 : 0);
      const wl = r.data.waitlisted || 0;
      const peopleNoun = booked === 1 ? vocab.member_singular : vocab.member_plural;
      notify.success(
        booked && wl
          ? `${booked} ${peopleNoun} booked, ${wl} on waitlist for ${occ.name}`
          : booked > 1
          ? `${booked} ${peopleNoun} booked for ${occ.name}`
          : `Booked · ${occ.name}`,
      );
      load();
    } catch (err) { handleBookingError(err, 'Failed to book'); }
    finally { setActingId(null); }
  };

  const cancel = async (bookingId, occ) => {
    const ok = await confirmFn({
      title: `Cancel booking for ${occ.name}?`,
      detail: occ.starts_at ? `Scheduled ${new Date(occ.starts_at).toLocaleString()}. If you cancel within the studio's late window, your class credit may not be refunded.` : undefined,
      tone: 'warning',
      confirmLabel: 'Yes, cancel',
      cancelLabel: 'Keep booking',
    });
    if (!ok) return;
    setActingId(occ.id);
    try {
      const { data } = await axios.delete(`${API}/member/bookings/${bookingId}`, { headers });
      notify.success(data.status === 'late_cancel' ? 'Late cancel — credit not refunded' : 'Booking cancelled');
      load();
    } catch (err) { notifyApiError(notify, err, 'Failed'); }
    finally { setActingId(null); }
  };

  const byDay = groupByDay(occs, weekStart);

  return (
    <div data-testid="member-book">
      <AdSlot slug={slug} placement="book_top" />
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.02em' }}>Book a class</h2>
        <div className="flex items-center gap-1">
          {/* Iter 216h202 — permanent "Buy credits" entry point so
             members can top up before they need to. */}
          <button
            onClick={() => { setBuyPackPrompt(''); setBuyPackOpen(true); }}
            className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[var(--color-brand-cyan)]/40 bg-[var(--color-brand-cyan)]/10 text-[var(--color-brand-cyan)] text-[11px] font-extrabold uppercase tracking-wider hover:bg-[var(--color-brand-cyan)]/20"
            data-testid="member-book-buy-credits"
          >
            <CreditCard size={12} /> Buy credits
          </button>
          <button onClick={() => setWeekStart(new Date(weekStart.getTime() - 7 * 86400000))} className="p-1.5 rounded-lg border border-white/10 hover:bg-white/5" data-testid="member-book-prev-week"><ChevronLeft size={14} /></button>
          <button onClick={() => setWeekStart(new Date(weekStart.getTime() + 7 * 86400000))} className="p-1.5 rounded-lg border border-white/10 hover:bg-white/5" data-testid="member-book-next-week"><ChevronRight size={14} /></button>
        </div>
      </div>
      <div className="text-xs text-white/50 mb-3">{weekStart.toLocaleDateString([], { month: 'short', day: 'numeric' })} – {new Date(weekStart.getTime() + 6 * 86400000).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}</div>

      {loading ? <CenterLoader /> : occs.length === 0 ? (
        <EmptyCard text="No classes this week. Try another week." />
      ) : (
        <div className="space-y-5">
          {byDay.map(({ day, items }) => (
            <section key={day.toISOString()} data-testid={`member-book-day-${day.getDay()}`}>
              <h3 className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50 mb-2">
                {day.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' })}
              </h3>
              {items.length === 0 ? <div className="text-xs text-white/30 italic">No classes.</div> : (
                <div className="space-y-2">
                  {items.map((o) => (
                    <ClassCard key={o.id} occ={o} busy={actingId === o.id} studioSlug={slug}
                      onBook={() => book(o)}
                      onCancel={() => cancel(o.my_booking.id, o)} />
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      )}
      {familyPickerOcc && (
        <FamilyBookingPicker
          occ={familyPickerOcc}
          subProfiles={subProfiles}
          onClose={() => setFamilyPickerOcc(null)}
          onConfirm={confirmFamilyBooking}
        />
      )}
      <BuyCreditPackModal
        headers={headers}
        open={buyPackOpen}
        onClose={() => setBuyPackOpen(false)}
        prompt={buyPackPrompt}
      />
    </div>
  );
}

function FamilyBookingPicker({ occ, subProfiles, onClose, onConfirm }) {
  const [selectedSelf, setSelectedSelf] = useState(true);
  const [selectedSubs, setSelectedSubs] = useState(new Set());

  const toggleSub = (id) => {
    setSelectedSubs((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const total = (selectedSelf ? 1 : 0) + selectedSubs.size;

  const submit = () => {
    if (total === 0) {
      notify.error('Pick at least one person');
      return;
    }
    const attendees = [];
    if (selectedSelf) attendees.push({ kind: 'self' });
    for (const id of selectedSubs) {
      attendees.push({ kind: 'sub_profile', sub_profile_id: id });
    }
    onConfirm(attendees);
  };

  return (
    <div className="fixed inset-0 z-[80] bg-black/80 grid place-items-center p-3" onClick={onClose}>
      <div className="w-full max-w-md bg-zinc-900 border border-white/10 rounded-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="member-family-booking-picker">
        <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] font-extrabold text-[var(--color-brand-cyan)]">Who's coming?</p>
            <h3 className="text-lg font-extrabold text-white mt-0.5">{occ.name}</h3>
            <p className="text-xs text-white/50 mt-0.5">
              {new Date(occ.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-white/10 text-white/60"><X size={14} /></button>
        </div>
        <div className="p-5 space-y-2">
          <label className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/[0.03]"
            data-testid="member-fpicker-self">
            <input type="checkbox" checked={selectedSelf}
              onChange={(e) => setSelectedSelf(e.target.checked)}
              className="accent-[var(--color-brand-cyan)]" />
            <span className="font-bold text-white text-sm">Me</span>
          </label>
          {subProfiles.map((sp) => (
            <label key={sp.id}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/[0.03]"
              data-testid={`member-fpicker-sub-${sp.id}`}>
              <input type="checkbox" checked={selectedSubs.has(sp.id)}
                onChange={() => toggleSub(sp.id)}
                className="accent-[var(--color-brand-cyan)]" />
              <span className="font-bold text-white text-sm">
                {sp.first_name} {sp.last_name}
                <span className="ml-2 text-[10px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/60 uppercase">
                  {sp.relationship}
                </span>
              </span>
            </label>
          ))}
        </div>
        <div className="px-5 py-4 border-t border-white/10 flex items-center justify-between">
          <span className="text-xs text-white/60">
            {total === 0 ? 'No-one selected' : total === 1 ? '1 spot' : `${total} spots`}
          </span>
          <button onClick={submit} disabled={total === 0}
            className="px-4 py-2 rounded-md text-sm font-extrabold disabled:opacity-50"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="member-fpicker-confirm">
            Book {total > 1 ? `${total} spots` : ''}
          </button>
        </div>
      </div>
    </div>
  );
}

function ClassCard({ occ, busy, onBook, onCancel, studioSlug }) {
  const myStatus = occ.my_booking?.status;
  const wlPos = occ.my_booking?.waitlist_position;
  const pct = occ.capacity > 0 ? Math.min(100, ((occ.bookings_count || 0) / occ.capacity) * 100) : 0;
  const barColor = pct >= 95 ? 'var(--color-danger)' : pct >= 70 ? 'var(--color-warning)' : 'var(--color-success)';

  let cta;
  if (myStatus === 'booked')   cta = <CTAButton tone="cancel"  onClick={onCancel} busy={busy} testid={`member-cancel-${occ.id}`}>Cancel</CTAButton>;
  else if (myStatus === 'waitlist') cta = <CTAButton tone="cancel" onClick={onCancel} busy={busy} testid={`member-cancel-${occ.id}`}>Leave waitlist</CTAButton>;
  else if (occ.full && !occ.my_booking) cta = <CTAButton tone="waitlist" onClick={onBook} busy={busy} testid={`member-waitlist-${occ.id}`}>Join waitlist</CTAButton>;
  else                          cta = <CTAButton tone="book"   onClick={onBook}   busy={busy} testid={`member-book-${occ.id}`}>Book</CTAButton>;

  const wlCount = occ.waitlist_count || 0;
  const instructor = occ.instructor;  // { id, name, slug, photo_url } — iter 215w
  const instructorHref = instructor && studioSlug ? `/m/${studioSlug}/i/${instructor.slug}` : null;
  return (
    <div className="rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.03] p-3.5 flex items-stretch gap-3" data-testid={`member-class-${occ.id}`}
         style={{ borderLeft: `3px solid ${occ.colour || 'var(--color-brand-cyan)'}` }}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="font-bold text-white text-sm truncate">{occ.name}</span>
          {myStatus === 'booked'   && <Pill tone="emerald">Booked</Pill>}
          {myStatus === 'waitlist' && (
            <Pill tone="violet" testid={`member-waitlist-position-${occ.id}`}>
              {wlPos ? `Waitlist · #${wlPos}${wlCount ? ` of ${wlCount}` : ''}` : 'Waitlist'}
            </Pill>
          )}
        </div>
        <div className="text-xs text-white/60 flex items-center gap-3 flex-wrap">
          <span className="flex items-center gap-1"><Clock size={10} /> {formatTime(occ.starts_at)}–{formatTime(occ.ends_at)}</span>
          {instructorHref ? (
            <a href={instructorHref} onClick={(e) => e.stopPropagation()}
               className="flex items-center gap-1.5 hover:text-white transition"
               data-testid={`member-class-instructor-${occ.id}`}>
              {instructor.photo_url && (
                <img src={instructor.photo_url} alt="" className="w-4 h-4 rounded-full object-cover" loading="lazy" decoding="async" />
              )}
              <span>· {instructor.name} →</span>
            </a>
          ) : occ.instructor_name && (
            <span>· {occ.instructor_name}</span>
          )}
          {occ.room_name && <span className="flex items-center gap-1"><MapPin size={10} /> {occ.room_name}</span>}
          {occ.full && wlCount > 0 && !myStatus && (
            <span className="text-violet-300 font-semibold">· {wlCount} on waitlist</span>
          )}
        </div>
        <div className="mt-2 flex items-center gap-2">
          <div className="w-24 h-1 rounded bg-white dark:bg-zinc-900/10 overflow-hidden"><div className="h-full" style={{ width: `${pct}%`, background: barColor }} /></div>
          <span className="text-[10px] text-white/50 flex items-center gap-1"><UsersIcon size={9} />{occ.bookings_count || 0}/{occ.capacity}</span>
        </div>
        <SocialPulse occId={occ.id} />
      </div>
      <div className="flex items-center">{cta}</div>
    </div>
  );
}
