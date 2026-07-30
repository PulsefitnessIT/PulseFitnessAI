/**
 * MOD Annual Service Visits — month calendar for the Service Desk
 * Preventative Maintenance page.
 *
 * Shows every MOD Type A contract's annual visit, colour-coded:
 *   🟢 confirmed (scheduled)   🟡 pending confirmation (proposed)
 * Click a day to see its visits and send the MOD site contact the secure
 * Engineer Appointment Booking form.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, ShieldCheck, Loader2, Send, Copy, CheckCircle2, Clock, CalendarDays, ChevronDown, User, Car } from 'lucide-react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function fmtDate(d) {
  if (!d) return '—';
  try { return new Date(`${String(d).slice(0, 10)}T00:00:00`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return d; }
}
const money = (v, c = 'GBP') => (v == null ? '—' : new Intl.NumberFormat('en-GB', { style: 'currency', currency: c, maximumFractionDigits: 0 }).format(v));

const BOOKING_LABEL = { not_sent: 'Not sent', sent: 'Form sent', draft: 'In progress', submitted: 'Completed' };

function BookingDetails({ b }) {
  const [open, setOpen] = useState(b?.status === 'submitted');
  if (!b || b.status === 'not_sent') return null;
  const veh = [b.veh_colour, b.veh_make, b.veh_model].filter(Boolean).join(' ');
  const Row = ({ label, value }) => (
    <div className="flex justify-between gap-3 py-0.5"><span className="text-zinc-400">{label}</span><span className="text-zinc-700 dark:text-zinc-200 font-medium text-right">{value || '—'}</span></div>
  );
  return (
    <div className="mt-2 rounded-lg bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-100 dark:border-zinc-800">
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 text-[11px] font-bold text-zinc-600 dark:text-zinc-300" data-testid="mod-booking-details-toggle">
        <span className="inline-flex items-center gap-1.5"><CalendarDays size={12} /> Booking details {b.status === 'submitted' ? '(completed)' : `(${BOOKING_LABEL[b.status] || b.status})`}</span>
        <ChevronDown size={13} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="px-2.5 pb-2.5 text-[11px] space-y-2" data-testid="mod-booking-details">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wide text-zinc-400 flex items-center gap-1 mb-0.5"><User size={10} /> MOD contact</p>
            <Row label="Name" value={b.mod_contact_name} />
            <Row label="Email" value={b.mod_contact_email} />
            <Row label="Phone" value={b.mod_contact_phone} />
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wide text-zinc-400 flex items-center gap-1 mb-0.5"><User size={10} /> Engineer / visitor</p>
            <Row label="Name" value={b.engineer_name} />
            <Row label="DOB" value={b.engineer_dob} />
            <Row label="Phone" value={b.engineer_phone} />
            <Row label="Visit" value={[b.visit_start_date, b.visit_start_time].filter(Boolean).join(' ')} />
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wide text-zinc-400 flex items-center gap-1 mb-0.5"><Car size={10} /> Vehicle</p>
            <Row label="Registration" value={b.veh_reg} />
            <Row label="Details" value={veh} />
          </div>
        </div>
      )}
    </div>
  );
}

export default function MODVisitCalendar() {
  const [visits, setVisits] = useState([]);
  const [stats, setStats] = useState({ pending: 0, confirmed: 0, total: 0 });
  const [loading, setLoading] = useState(true);
  const now = new Date();
  const [cursor, setCursor] = useState({ y: now.getFullYear(), m: now.getMonth() });
  const [selectedDay, setSelectedDay] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/svc/pm/mod-visits');
      setVisits(r.data?.visits || []);
      setStats({ pending: r.data?.pending || 0, confirmed: r.data?.confirmed || 0, total: r.data?.total || 0 });
    } catch { notify.error('Could not load MOD visits'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  // Map visits by ISO day (YYYY-MM-DD).
  const byDay = useMemo(() => {
    const m = {};
    for (const v of visits) {
      const key = String(v.effective_date || '').slice(0, 10);
      if (!key) continue;
      (m[key] = m[key] || []).push(v);
    }
    return m;
  }, [visits]);

  // Build the calendar grid (Mon-first).
  const cells = useMemo(() => {
    const first = new Date(cursor.y, cursor.m, 1);
    const startOffset = (first.getDay() + 6) % 7; // Mon=0
    const daysInMonth = new Date(cursor.y, cursor.m + 1, 0).getDate();
    const arr = [];
    for (let i = 0; i < startOffset; i++) arr.push(null);
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = `${cursor.y}-${String(cursor.m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      arr.push({ d, iso, visits: byDay[iso] || [] });
    }
    return arr;
  }, [cursor, byDay]);

  const move = (delta) => {
    setSelectedDay(null);
    let m = cursor.m + delta, y = cursor.y;
    if (m < 0) { m = 11; y -= 1; } else if (m > 11) { m = 0; y += 1; }
    setCursor({ y, m });
  };

  const sendBooking = async (contractId) => {
    setBusyId(contractId);
    try {
      const r = await api.post(`/svc/pm/mod-visits/${contractId}/booking-link`, { send_email: true });
      if (r.data?.emailed) notify.success(`Booking form emailed to ${r.data.site_email}`);
      else if (r.data?.needs_email) notify.warning('No email on file for this site — link created, copy it below');
      else notify.success('Booking form link ready');
      try { await navigator.clipboard.writeText(r.data.share_url); } catch { /* noop */ }
      await load();
    } catch { notify.error('Could not create booking link'); }
    finally { setBusyId(null); }
  };

  const copyLink = async (url) => {
    try { await navigator.clipboard.writeText(url); notify.success('Booking link copied'); }
    catch { notify.error('Copy failed'); }
  };

  const selectedVisits = selectedDay ? (byDay[selectedDay] || []) : [];
  const todayIso = new Date().toISOString().slice(0, 10);

  return (
    <section className="rounded-xl border border-indigo-200 dark:border-indigo-900/50 bg-indigo-50/40 dark:bg-indigo-950/20 overflow-hidden" data-testid="mod-visit-calendar">
      <div className="px-4 py-3 border-b border-indigo-200 dark:border-indigo-900/50 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <p className="text-sm font-black text-indigo-900 dark:text-indigo-200 flex items-center gap-2">
            <ShieldCheck size={17} /> MOD Annual Service Visits
          </p>
          <p className="text-xs text-indigo-700/80 dark:text-indigo-300/70 mt-0.5">
            Type A contract visits · <span className="font-semibold">{stats.confirmed}</span> confirmed · <span className="font-semibold">{stats.pending}</span> awaiting confirmation
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500" /> Confirmed</span>
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700"><span className="w-2.5 h-2.5 rounded-full bg-amber-400" /> Pending</span>
        </div>
      </div>

      <div className="p-4">
        {/* Month nav */}
        <div className="flex items-center justify-between mb-3">
          <button onClick={() => move(-1)} className="p-1.5 rounded-lg hover:bg-white dark:hover:bg-zinc-800 text-indigo-700 dark:text-indigo-300" data-testid="mod-cal-prev" aria-label="Previous month"><ChevronLeft size={18} /></button>
          <p className="text-sm font-bold text-indigo-900 dark:text-indigo-100" data-testid="mod-cal-label">{MONTHS[cursor.m]} {cursor.y}</p>
          <button onClick={() => move(1)} className="p-1.5 rounded-lg hover:bg-white dark:hover:bg-zinc-800 text-indigo-700 dark:text-indigo-300" data-testid="mod-cal-next" aria-label="Next month"><ChevronRight size={18} /></button>
        </div>

        {loading ? (
          <div className="p-10 text-center"><Loader2 className="animate-spin mx-auto text-indigo-400" /></div>
        ) : (
          <>
            <div className="grid grid-cols-7 gap-1 mb-1">
              {DOW.map((d) => <div key={d} className="text-[10px] font-bold uppercase tracking-wide text-indigo-400 text-center py-1">{d}</div>)}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {cells.map((c, i) => {
                if (!c) return <div key={`e${i}`} />;
                const hasConfirmed = c.visits.some((v) => v.visit_status === 'confirmed');
                const hasPending = c.visits.some((v) => v.visit_status !== 'confirmed');
                const isToday = c.iso === todayIso;
                const isSel = c.iso === selectedDay;
                return (
                  <button
                    key={c.iso}
                    onClick={() => c.visits.length && setSelectedDay(isSel ? null : c.iso)}
                    className={`relative aspect-square rounded-lg text-left p-1.5 text-xs transition-colors border
                      ${c.visits.length ? 'cursor-pointer hover:ring-2 hover:ring-indigo-300' : 'cursor-default'}
                      ${isSel ? 'ring-2 ring-indigo-500 bg-white dark:bg-zinc-800' : 'bg-white/70 dark:bg-zinc-900/40 border-indigo-100 dark:border-zinc-800'}
                      ${isToday ? 'font-black text-indigo-700' : 'text-zinc-600 dark:text-zinc-300'}`}
                    data-testid={c.visits.length ? `mod-cal-day-${c.iso}` : undefined}
                  >
                    <span>{c.d}</span>
                    {c.visits.length > 0 && (
                      <div className="absolute bottom-1 left-1 right-1 flex items-center gap-0.5 flex-wrap">
                        {hasConfirmed && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />}
                        {hasPending && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
                        {c.visits.length > 1 && <span className="text-[9px] font-bold text-indigo-500 ml-0.5">{c.visits.length}</span>}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </>
        )}

        {/* Selected-day detail */}
        {selectedDay && (
          <div className="mt-4 rounded-lg border border-indigo-200 dark:border-indigo-900/50 bg-white dark:bg-zinc-900 p-3" data-testid="mod-cal-day-detail">
            <p className="text-xs font-bold text-indigo-800 dark:text-indigo-200 flex items-center gap-1.5 mb-2"><CalendarDays size={14} /> {fmtDate(selectedDay)} · {selectedVisits.length} visit{selectedVisits.length !== 1 ? 's' : ''}</p>
            <ul className="space-y-2">
              {selectedVisits.map((v) => (
                <li key={v.contract_id} className="rounded-lg border border-zinc-100 dark:border-zinc-800 p-2.5" data-testid={`mod-visit-${v.contract_id}`}>
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{v.mod_site_name}</p>
                      <p className="text-[11px] text-zinc-500">{v.quote_number} · {v.equipment_count ?? '—'} machines · {money(v.annual_value, v.currency)}/yr{v.engineer ? ` · ${v.engineer}` : ''}</p>
                    </div>
                    {v.visit_status === 'confirmed'
                      ? <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-700 bg-emerald-100 dark:bg-emerald-900/40 dark:text-emerald-300 px-2 py-0.5 rounded-full"><CheckCircle2 size={11} /> Confirmed</span>
                      : <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 bg-amber-100 dark:bg-amber-900/40 dark:text-amber-300 px-2 py-0.5 rounded-full"><Clock size={11} /> Pending confirmation</span>}
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-2 pt-2 border-t border-zinc-100 dark:border-zinc-800 flex-wrap">
                    <span className="text-[11px] text-zinc-500">Booking form: <span className="font-semibold text-zinc-700 dark:text-zinc-300">{BOOKING_LABEL[v.booking_status] || v.booking_status}</span></span>
                    <div className="flex items-center gap-1.5">
                      {v.share_url && (
                        <button onClick={() => copyLink(v.share_url)} className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-lg border border-zinc-200 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-800" data-testid={`mod-visit-copy-${v.contract_id}`}><Copy size={12} /> Copy link</button>
                      )}
                      <button onClick={() => sendBooking(v.contract_id)} disabled={busyId === v.contract_id} className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50" data-testid={`mod-visit-send-${v.contract_id}`}>
                        {busyId === v.contract_id ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />} {v.booking_status === 'not_sent' ? 'Send booking form' : 'Resend'}
                      </button>
                    </div>
                  </div>
                  <BookingDetails b={v.booking} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
