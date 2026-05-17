/**
 * Iter 216h173 — BookingsTab extracted from MemberPortal.js for lazy-loading.
 *
 * Owns the upcoming + past bookings list plus its modals (CalendarFeedModal,
 * SwapModal) and the AttendeeGroupedList / BookingRow primitives.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  ArrowLeftRight, CalendarPlus, Download, Link as LinkIcon, RefreshCw, X,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
  API, AdSlot, CenterLoader, EmptyCard, Pill,
} from '../portalShared';

export default function BookingsTab({ headers, slug }) {
  const [data, setData] = useState({ upcoming: [], past: [] });
  const [loading, setLoading] = useState(true);
  const [feedUrl, setFeedUrl] = useState(null);
  const [swappingFrom, setSwappingFrom] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [payingAll, setPayingAll] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/member/bookings`, { headers });
      setData(data);
      try {
        const seenAt = localStorage.getItem('mbr_waitlist_promo_seen_at') || '';
        let newest = seenAt;
        const fresh = (data?.upcoming || []).filter((b) => {
          const at = b.promoted_from_waitlist_at;
          if (!at) return false;
          if (at > newest) newest = at;
          return at > seenAt;
        });
        if (fresh.length > 0) {
          const first = fresh[0];
          const occName = first.occurrence?.name || 'your class';
          notify.success(`🎉 You're in! A spot just opened for ${occName}.`,
            { duration: 7000, id: `wl-promo-${first.id}` });
        }
        if (newest && newest !== seenAt) {
          localStorage.setItem('mbr_waitlist_promo_seen_at', newest);
        }
      } catch { /* badge is best-effort */ }
    }
    catch { notify.error('Failed to load bookings'); }
    finally { setLoading(false); }
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const loadInvoices = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/member/invoices`, { headers });
      setInvoices(data.invoices || []);
    } catch { /* silent — billing is optional */ }
  }, [headers]);
  useEffect(() => { loadInvoices(); }, [loadInvoices]);

  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get('paid_all')) {
      notify.success('Payment received — thank you! 🎉');
      loadInvoices();
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [loadInvoices]);

  const unpaid = useMemo(
    () => (invoices || []).filter((i) => i.status === 'draft' || i.status === 'sent'),
    [invoices],
  );
  const outstandingPence = unpaid.reduce((s, i) => s + (i.total_pence || 0), 0);

  const payAll = async () => {
    if (unpaid.length === 0) { notify.info("You're all paid up."); return; }
    setPayingAll(true);
    try {
      const { data } = await axios.post(`${API}/member/invoices/pay-all`, {}, { headers });
      window.location.href = data.checkout_url;
    } catch (e) {
      notifyApiError(notify, e, 'Could not start checkout');
    } finally {
      setPayingAll(false);
    }
  };

  const showFeedUrl = async () => {
    try {
      const { data } = await axios.get(`${API}/member/calendar-feed`, { headers });
      setFeedUrl(data);
    } catch (e) { notifyApiError(notify, e, 'Could not get calendar feed'); }
  };

  const downloadIcs = (booking) => {
    axios.get(`${API}/member/bookings/${booking.id}/calendar.ics`,
      { headers, responseType: 'blob' })
      .then((r) => {
        const url = URL.createObjectURL(r.data);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(booking.occurrence?.name || 'class').replace(/\s+/g, '-').toLowerCase()}.ics`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
      })
      .catch((e) => notifyApiError(notify, e, 'Calendar download failed'));
  };

  return (
    <div data-testid="member-bookings">
      <AdSlot slug={slug} placement="bookings_top" />
      <div className="flex items-end justify-between gap-3 mb-4 flex-wrap">
        <h2 className="text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.02em' }}>Your bookings</h2>
        <button onClick={showFeedUrl}
          className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-brand-cyan)] hover:underline flex items-center gap-1"
          data-testid="member-bookings-calendar-feed">
          <CalendarPlus size={11} /> Subscribe to calendar
        </button>
      </div>
      {loading ? <CenterLoader /> : (
        <>
          <section className="mb-6">
            <h3 className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50 mb-2">Upcoming</h3>
            {data.upcoming.length === 0 ? <EmptyCard text="No upcoming bookings. Head to Book to grab a class." /> : (
              <AttendeeGroupedList
                bookings={data.upcoming}
                renderRow={(b) => (
                  <BookingRow key={b.id} b={b}
                    onSwap={() => setSwappingFrom(b)}
                    onAddToCalendar={() => downloadIcs(b)} />
                )} />
            )}
          </section>
          <section>
            <h3 className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50 mb-2">Past</h3>
            {data.past.length === 0 ? <EmptyCard text="No history yet." /> : (
              <div className="space-y-2">
                {data.past.map((b) => <BookingRow key={b.id} b={b} past onRebook={async (src) => {
                  try {
                    const { data: r } = await axios.post(`${API}/member/bookings/rebook`, { source_booking_id: src.id }, { headers });
                    if (r.already_booked) notify.info('Already booked', "You're already on the next session — see you there.");
                    else notify.success('Booked', r.status === 'waitlist' ? "You're on the waitlist." : `See you on ${new Date(r.starts_at).toLocaleString([], { weekday:'short', day:'numeric', month:'short', hour:'2-digit', minute:'2-digit' })}`);
                    load();
                  } catch (e) { notifyApiError(notify, e, 'Book again failed'); }
                }} />)}
              </div>
            )}
          </section>
        </>
      )}

      {unpaid.length > 0 && (
        <section data-testid="member-billing-outstanding">
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 flex items-center gap-4 flex-wrap">
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-amber-300 mb-1">
                {unpaid.length} invoice{unpaid.length === 1 ? '' : 's'} outstanding
              </div>
              <div className="text-xl font-black text-white">£{(outstandingPence / 100).toFixed(2)}</div>
              <div className="text-xs text-white/60 mt-0.5">
                Pay all outstanding invoices in one secure checkout.
              </div>
            </div>
            <button onClick={payAll} disabled={payingAll}
              className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-full text-sm font-extrabold"
              style={{ background: 'var(--color-brand-cyan)', color: '#0A0C10' }}
              data-testid="member-pay-all">
              {payingAll ? 'Opening checkout…' : `Pay £${(outstandingPence / 100).toFixed(2)} now →`}
            </button>
          </div>
          <div className="mt-3 space-y-1.5">
            {unpaid.map((inv) => (
              <div key={inv.id} className="flex items-center justify-between text-xs text-white/70 px-3 py-2 rounded-lg bg-white/5"
                data-testid={`member-invoice-${inv.id}`}>
                <span>{inv.period} · {inv.lines?.length || 0} line item{(inv.lines?.length || 0) === 1 ? '' : 's'}</span>
                <span className="font-bold text-white">£{(inv.total_pence / 100).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {feedUrl && <CalendarFeedModal feed={feedUrl} onClose={() => setFeedUrl(null)} headers={headers} onRotate={async () => {
        try {
          await axios.post(`${API}/member/calendar-feed/rotate`, {}, { headers });
          showFeedUrl();
          notify.success('New calendar URL — old links are now invalid');
        } catch (e) { notifyApiError(notify, e, 'Failed'); }
      }} />}
      {swappingFrom && (
        <SwapModal headers={headers} booking={swappingFrom}
          onClose={(refresh) => { setSwappingFrom(null); if (refresh) load(); }} />
      )}
    </div>
  );
}

function AttendeeGroupedList({ bookings, renderRow }) {
  const groups = React.useMemo(() => {
    const byKey = new Map();
    for (const b of bookings) {
      const name = b.attendee_name || 'You';
      const key = b.attendee_sub_profile_id || `name:${name}:${b.attendee_kind || 'self'}`;
      if (!byKey.has(key)) byKey.set(key, { name, kind: b.attendee_kind || 'self', rows: [] });
      byKey.get(key).rows.push(b);
    }
    return Array.from(byKey.values());
  }, [bookings]);

  if (groups.length <= 1) {
    return <div className="space-y-2">{bookings.map(renderRow)}</div>;
  }
  return (
    <div className="space-y-4" data-testid="member-bookings-grouped">
      {groups.map((g) => (
        <div key={g.name + g.kind} data-testid={`member-bookings-group-${(g.name || '').toLowerCase().replace(/\s+/g, '-')}`}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-extrabold uppercase tracking-[0.22em] text-white/70">
              {g.name}
            </span>
            <span className="text-[10px] text-white/40">
              {g.rows.length} class{g.rows.length === 1 ? '' : 'es'}
            </span>
          </div>
          <div className="space-y-2">{g.rows.map(renderRow)}</div>
        </div>
      ))}
    </div>
  );
}

function BookingRow({ b, past, onSwap, onAddToCalendar, onRebook }) {
  const tone = {
    booked: 'emerald', waitlist: 'violet', attended: 'emerald',
    cancelled: 'amber', late_cancel: 'amber', no_show: 'amber',
  }[b.status] || 'amber';
  const canManage = !past && (b.status === 'booked' || b.status === 'waitlist');
  return (
    <div className="rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.03] p-3.5"
      data-testid={`member-booking-${b.id}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="font-bold text-white text-sm truncate">
            {b.occurrence?.name || 'Class'}
            {b.attendee_kind === 'sub_profile' && (
              <span className="ml-1.5 text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-fuchsia-500/20 text-fuchsia-300 uppercase">
                {b.attendee_name || 'family'}
              </span>
            )}
            {b.attendee_kind === 'guest' && (
              <span className="ml-1.5 text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 uppercase">
                guest: {b.attendee_name}
              </span>
            )}
            {b.swapped_from_occurrence_id && (
              <span className="ml-1.5 text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 uppercase">swapped</span>
            )}
            {b.promoted_from_waitlist_at && (
              <span className="ml-1.5 text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 uppercase"
                data-testid={`member-booking-promoted-${b.id}`}>
                Promoted
              </span>
            )}
          </div>
          <div className="text-xs text-white/60">
            {b.occurrence?.starts_at && new Date(b.occurrence.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            {b.occurrence?.room_name && ` · ${b.occurrence.room_name}`}
          </div>
        </div>
        <Pill tone={tone} testid={b.status === 'waitlist' ? `member-booking-waitlist-pos-${b.id}` : undefined}>
          {b.status === 'waitlist' && b.waitlist_position
            ? `Waitlist · #${b.waitlist_position}`
            : (b.status || '').replace('_', ' ')}
        </Pill>
      </div>
      {canManage && (
        <div className="flex gap-2 mt-3 -mx-1">
          <button onClick={onAddToCalendar}
            className="flex-1 px-2 py-1.5 rounded-md text-[10px] font-bold uppercase tracking-wider border border-white/10 text-white/80 hover:bg-white dark:bg-zinc-900/5 hover:text-white flex items-center justify-center gap-1"
            data-testid={`member-booking-cal-${b.id}`}>
            <Download size={10} /> .ics
          </button>
          {b.status === 'booked' && (
            <button onClick={onSwap}
              className="flex-1 px-2 py-1.5 rounded-md text-[10px] font-bold uppercase tracking-wider border border-blue-400/40 text-blue-300 hover:bg-blue-500/10 flex items-center justify-center gap-1"
              data-testid={`member-booking-swap-${b.id}`}>
              <ArrowLeftRight size={10} /> Swap
            </button>
          )}
        </div>
      )}
      {past && onRebook && (b.status === 'attended' || b.status === 'booked') && (
        <div className="flex mt-3 -mx-1">
          <button onClick={() => onRebook(b)}
            className="flex-1 px-2 py-1.5 rounded-md text-[10px] font-bold uppercase tracking-wider border border-[color:var(--color-brand-cyan)]/50 text-[color:var(--color-brand-cyan)] hover:bg-[color:var(--color-brand-cyan)]/10 flex items-center justify-center gap-1"
            data-testid={`member-booking-rebook-${b.id}`}>
            <RefreshCw size={10} /> Book again
          </button>
        </div>
      )}
    </div>
  );
}

function CalendarFeedModal({ feed, onClose, onRotate }) {
  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      notify.success('Copied');
    } catch { notify.error('Copy failed'); }
  };
  return (
    <div className="fixed inset-0 z-[80] bg-black/80 grid place-items-center p-3" onClick={onClose}>
      <div className="w-full max-w-md bg-zinc-900 border border-white/10 rounded-2xl p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="member-calendar-feed-modal">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">Auto-syncing calendar</p>
            <h3 className="text-lg font-extrabold text-white mt-1">Subscribe — never miss a class</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-white dark:bg-zinc-900/10 text-white/60"><X size={14} /></button>
        </div>

        <p className="text-xs text-white/60 mb-3">{feed.instructions}</p>

        <div className="space-y-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider font-bold text-white/50 mb-1">Apple / iOS</p>
            <button onClick={() => copy(feed.webcal_url)}
              className="w-full text-left px-3 py-2 rounded-md border border-white/10 bg-white dark:bg-zinc-900/5 text-xs font-mono text-[var(--color-brand-cyan)] hover:bg-white dark:bg-zinc-900/10 truncate"
              data-testid="member-calendar-feed-webcal">
              <LinkIcon size={10} className="inline mr-1" /> {feed.webcal_url}
            </button>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider font-bold text-white/50 mb-1">Google / Outlook (paste as URL)</p>
            <button onClick={() => copy(feed.https_url)}
              className="w-full text-left px-3 py-2 rounded-md border border-white/10 bg-white dark:bg-zinc-900/5 text-xs font-mono text-[var(--color-brand-cyan)] hover:bg-white dark:bg-zinc-900/10 truncate"
              data-testid="member-calendar-feed-https">
              <LinkIcon size={10} className="inline mr-1" /> {feed.https_url}
            </button>
          </div>
        </div>

        <button onClick={onRotate}
          className="mt-4 text-[10px] uppercase tracking-wider font-bold text-white/40 hover:text-red-300"
          data-testid="member-calendar-feed-rotate">
          Reset URL (invalidates old links)
        </button>
      </div>
    </div>
  );
}

function SwapModal({ headers, booking, onClose }) {
  const [occs, setOccs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [swapping, setSwapping] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const from = new Date().toISOString();
        const to = new Date(Date.now() + 14 * 86400000).toISOString();
        const { data } = await axios.get(`${API}/member/timetable`, { headers, params: { from, to } });
        const myName = booking.occurrence?.name;
        const list = (data.occurrences || []).filter((o) =>
          o.id !== booking.occurrence_id
          && (myName ? o.name === myName : true)
          && !o.full
          && !o.my_booking
        );
        setOccs(list);
      } catch (e) {
        notifyApiError(notify, e, 'Failed');
      }
      setLoading(false);
    })();
  // eslint-disable-next-line
  }, []);

  const swap = async (target) => {
    setSwapping(target.id);
    try {
      await axios.post(`${API}/member/bookings/${booking.id}/swap`,
        { target_occurrence_id: target.id }, { headers });
      notify.success(`Swapped to ${new Date(target.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`);
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, 'Swap failed');
    }
    setSwapping(null);
  };

  return (
    <div className="fixed inset-0 z-[80] bg-black/80 grid place-items-center p-3" onClick={() => onClose(false)}>
      <div className="w-full max-w-md bg-zinc-900 border border-white/10 rounded-2xl shadow-2xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
        data-testid="member-swap-modal">
        <div className="px-5 py-4 border-b border-white/10 flex items-start justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] font-extrabold text-blue-400">Swap booking</p>
            <h3 className="text-lg font-extrabold text-white mt-0.5">{booking.occurrence?.name}</h3>
            <p className="text-xs text-white/50 mt-0.5">
              From {new Date(booking.occurrence?.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </p>
          </div>
          <button onClick={() => onClose(false)} className="p-1.5 rounded hover:bg-white dark:bg-zinc-900/10 text-white/60"><X size={14} /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-3">
          {loading ? <CenterLoader /> : occs.length === 0 ? (
            <div className="text-center text-xs text-white/50 py-8">
              No alternative slots in the next 14 days. Try cancelling and rebooking.
            </div>
          ) : (
            <div className="space-y-2">
              {occs.map((o) => (
                <button key={o.id} onClick={() => swap(o)}
                  disabled={!!swapping}
                  className="w-full text-left rounded-lg border border-white/10 bg-white dark:bg-zinc-900/[0.03] p-3 hover:border-blue-400/50 hover:bg-blue-500/5 disabled:opacity-50 transition"
                  data-testid={`member-swap-target-${o.id}`}>
                  <div className="font-bold text-white text-sm">
                    {new Date(o.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                  </div>
                  <div className="text-[11px] text-white/60 mt-0.5">
                    {o.instructor_name} · {o.capacity - (o.bookings_count || 0)} spots left
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
