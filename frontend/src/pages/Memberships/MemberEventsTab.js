/**
 * Member-side Events tab (iter 216ak · Sprint B · G6).
 *
 * Powered by:
 *   GET  /api/member/events — list upcoming events + `my_tickets`.
 *   POST /api/member/events/{id}/tickets — buy N tickets on statement.
 *
 * UX: card-per-event with date, price, remaining tickets, and a
 * "Buy tickets" popover that supports 1–8 tickets added to the next
 * monthly invoice (same pattern as the costume-→-invoice hook).
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Sparkles, Loader2, Calendar, Ticket, MapPin, Plus, Minus,
  CheckCircle2, AlertTriangle,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

export default function MemberEventsTab({ API, headers }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [buying, setBuying] = useState(null); // eventId
  const [qtyMap, setQtyMap] = useState({});

  const load = () => {
    setLoading(true);
    axios.get(`${API}/member/events`, { headers })
      .then((r) => setEvents(r.data?.events || []))
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  };
  useEffect(load, [API, headers]);

  const buy = async (e) => {
    const qty = qtyMap[e.id] || 1;
    setBuying(e.id);
    try {
      const r = await axios.post(`${API}/member/events/${e.id}/tickets`,
        { quantity: qty, payment: 'on-statement' }, { headers });
      notify.success(
        `${qty} ticket${qty === 1 ? '' : 's'} reserved — £${(r.data.total_pence / 100).toFixed(2)} added to your next statement`,
      );
      setQtyMap((m) => ({ ...m, [e.id]: 1 }));
      load();
    } catch (err) {
      notifyApiError(notify, err, 'Could not reserve tickets');
    }
    setBuying(null);
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-white/60 text-xs py-8" data-testid="member-events-loading">
        <Loader2 size={12} className="animate-spin" /> Loading events…
      </div>
    );
  }

  return (
    <div data-testid="member-events">
      <div className="mb-3">
        <h2 className="text-xl font-extrabold tracking-tight" data-testid="member-events-title">Events & shows</h2>
        <p className="text-xs text-white/50 mt-0.5">Tickets go on your next statement — no card charged today.</p>
      </div>

      {events.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 p-8 text-center" data-testid="member-events-empty">
          <Sparkles size={28} className="mx-auto text-white/30 mb-2" />
          <p className="text-sm font-bold text-white/80">No upcoming events right now</p>
          <p className="text-xs text-white/50 mt-1">Check back — recitals, showcases and trip days land here first.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {events.map((e) => {
            const priceFree = !e.ticket_price_pence;
            const qty = qtyMap[e.id] || 1;
            const soldOut = e.tickets_remaining === 0;
            const canBuy = (e.ticket_capacity || 0) > 0 || priceFree;
            return (
              <div key={e.id} className="rounded-xl p-3 border border-white/10 bg-white/[0.03]" data-testid={`member-event-${e.id}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-base font-extrabold text-white truncate">{e.name}</p>
                    <div className="flex flex-wrap gap-2 mt-1 text-[11px] text-white/60">
                      <span className="inline-flex items-center gap-1"><Calendar size={10} /> {formatDate(e.starts_at)}</span>
                      {e.venue && <span className="inline-flex items-center gap-1"><MapPin size={10} /> {e.venue}</span>}
                      <span className="inline-flex items-center gap-1 font-bold text-white/80">
                        <Ticket size={10} /> {priceFree ? 'Free' : `£${(e.ticket_price_pence / 100).toFixed(2)}`}
                      </span>
                      {e.tickets_remaining !== null && e.tickets_remaining !== undefined && (
                        <span className="text-white/50">{e.tickets_remaining} left</span>
                      )}
                    </div>
                    {e.description && <p className="text-xs text-white/60 mt-1.5 line-clamp-2">{e.description}</p>}
                    {(e.my_tickets || 0) > 0 && (
                      <span className="inline-flex items-center gap-1 mt-2 text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400" data-testid={`member-event-mine-${e.id}`}>
                        <CheckCircle2 size={9} /> You have {e.my_tickets} ticket{e.my_tickets === 1 ? '' : 's'}
                      </span>
                    )}
                  </div>
                </div>

                {canBuy && !soldOut && (
                  <div className="mt-3 flex items-center gap-2 justify-end">
                    <div className="inline-flex items-center gap-1 border border-white/10 rounded-full px-1 py-0.5" data-testid={`member-event-qty-${e.id}`}>
                      <button type="button" onClick={() => setQtyMap((m) => ({ ...m, [e.id]: Math.max(1, qty - 1) }))}
                              className="w-6 h-6 rounded-full hover:bg-white/10 inline-flex items-center justify-center">
                        <Minus size={11} />
                      </button>
                      <span className="w-6 text-center text-sm font-extrabold">{qty}</span>
                      <button type="button" onClick={() => setQtyMap((m) => ({ ...m, [e.id]: Math.min(8, qty + 1) }))}
                              className="w-6 h-6 rounded-full hover:bg-white/10 inline-flex items-center justify-center">
                        <Plus size={11} />
                      </button>
                    </div>
                    <button type="button" onClick={() => buy(e)} disabled={buying === e.id}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-extrabold"
                            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
                            data-testid={`member-event-buy-${e.id}`}>
                      {buying === e.id ? <Loader2 size={11} className="animate-spin" /> : <Ticket size={11} />}
                      {priceFree ? 'Reserve' : `Buy £${((e.ticket_price_pence * qty) / 100).toFixed(2)}`}
                    </button>
                  </div>
                )}
                {soldOut && (
                  <p className="mt-2 text-[11px] text-amber-400 inline-flex items-center gap-1"><AlertTriangle size={11} /> Sold out</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' }) +
      ' · ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}
