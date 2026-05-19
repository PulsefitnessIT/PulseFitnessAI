/**
 * Member portal — Home tab.
 *
 * Reads the operator's saved layout (PUT /api/member-app/layout) and renders
 * the active cards. Each card is a simple shortcut that either switches the
 * portal to an existing tab or shows an inline summary. This is the screen
 * the gym owner customises in the Mobile App Builder.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import {
  CalendarDays, ClipboardList, Dumbbell, Wrench, Trophy, Activity,
  ShoppingBag, BarChart3, Megaphone, QrCode, Share2, Sparkles, ChevronRight,
  Clock, MapPin, Users, AlertCircle, Zap,
} from 'lucide-react';
import { useStudioVocab } from '@/hooks/useStudioVocab';

const ICONS = {
  CalendarDays, ClipboardList, Dumbbell, Wrench, Trophy, Activity,
  ShoppingBag, BarChart3, Megaphone, QrCode, Share2, Sparkles,
};

// Card-type → portal tab to switch to when tapped. null means "no action / informational".
const CARD_TARGET = {
  class_booking: 'book',
  my_bookings: 'bookings',
  membership_card: 'pass',
  refer_a_friend: 'profile',
  pt_enquiry: 'profile',
  shop: 'profile',
};

// Card-type → human-readable label/desc fallback if backend doesn't return one
// (the registry endpoint is the authoritative source).
export default function HomeTab({ headers, setTab, API }) {
  const vocab = useStudioVocab();
  const [layout, setLayout] = useState(null);
  const [registry, setRegistry] = useState({});
  const [widget, setWidget] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    Promise.all([
      axios.get(`${API}/member-app/layout`, { headers }).catch(() => null),
      axios.get(`${API}/member-app/cards`, { headers }).catch(() => null),
      axios.get(`${API}/member/home-widget`, { headers }).catch(() => null),
    ]).then(([lay, reg, w]) => {
      if (!alive) return;
      setLayout(lay?.data?.layout || null);
      const map = {};
      (reg?.data?.cards || []).forEach((c) => { map[c.id] = c; });
      setRegistry(map);
      setWidget(w?.data || null);
      setLoading(false);
    });
    return () => { alive = false; };
  }, [headers, API]);

  if (loading) {
    return <div className="text-center text-white/50 text-sm py-12" data-testid="member-home-loading">Loading…</div>;
  }

  const cards = (layout?.cards || []).filter((c) => c.enabled);
  const hero = widget && (widget.next_class || widget.outstanding_invoice_pence || widget.unsigned_forms)
    ? <HomeWidgetHero w={widget} setTab={setTab} vocab={vocab} />
    : null;

  if (!hero && cards.length === 0) {
    return (
      <div className="text-center text-white/60 text-sm py-12" data-testid="member-home-empty">
        Your gym hasn't customised this screen yet.
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="member-home-tab">
      {hero}
      {cards.map((card) => {
        const spec = registry[card.type];
        if (!spec) return null;
        const Icon = ICONS[spec.icon] || Sparkles;
        const target = CARD_TARGET[card.type];
        const onClick = target ? () => setTab(target) : undefined;

        return (
          <button
            key={card.type}
            onClick={onClick}
            disabled={!onClick}
            className="w-full text-left rounded-xl p-4 transition border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] disabled:cursor-default disabled:hover:bg-white/[0.04]"
            data-testid={`member-home-card-${card.type}`}
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(25,205,255,0.15)', color: 'var(--color-brand-cyan)' }}>
                <Icon size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-white truncate">{spec.title}</div>
                <div className="text-xs text-white/60 truncate">{spec.description}</div>
              </div>
              {onClick && <ChevronRight size={18} className="text-white/40 flex-shrink-0" />}
            </div>
          </button>
        );
      })}
    </div>
  );
}

/* ───────── Home widget hero (iter 216ak · Sprint B · G12) ───────── */

function HomeWidgetHero({ w, setTab, _vocab }) {
  const nc = w.next_class;
  const hasInvoices = (w.outstanding_invoice_pence || 0) > 0;
  const hasForms = (w.unsigned_forms || 0) > 0;

  return (
    <div className="space-y-3" data-testid="member-home-widget">
      {nc && (
        <button type="button" onClick={() => setTab('bookings')}
          className="w-full text-left rounded-2xl p-4 border border-white/10 bg-gradient-to-br from-white/[0.05] to-transparent hover:from-white/[0.08]"
          data-testid="member-home-next-class">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-[10px] uppercase tracking-[0.22em] font-extrabold text-[var(--color-brand-cyan)] inline-flex items-center gap-1"><Zap size={9} /> Next up</p>
              <h3 className="text-lg font-black text-white truncate mt-0.5">{nc.name}</h3>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-white/70">
                <span className="inline-flex items-center gap-1"><Clock size={10} /> {formatStartsAt(nc.starts_at)}</span>
                {nc.room_name && <span className="inline-flex items-center gap-1"><MapPin size={10} /> {nc.room_name}</span>}
                {nc.capacity > 0 && <span className="inline-flex items-center gap-1"><Users size={10} /> {nc.booked_count}/{nc.capacity}</span>}
              </div>
            </div>
            <InMinuteBadge mins={nc.in_minutes} />
          </div>
        </button>
      )}

      {(hasInvoices || hasForms) && (
        <div className="rounded-xl p-3 border border-amber-500/30 bg-amber-500/10 inline-flex items-start gap-2 w-full"
             data-testid="member-home-reminders">
          <AlertCircle size={13} className="text-amber-400 mt-0.5 flex-shrink-0" />
          <div className="flex-1 min-w-0 text-xs">
            {hasInvoices && (
              <p className="font-bold text-amber-400">
                £{(w.outstanding_invoice_pence / 100).toFixed(2)} outstanding on your account
              </p>
            )}
            {hasForms && (
              <p className="text-amber-300/90 mt-0.5">
                {w.unsigned_forms} form{w.unsigned_forms === 1 ? '' : 's'} awaiting your signature
              </p>
            )}
          </div>
        </div>
      )}

      {(w.last_booked || []).length > 0 && (
        <div data-testid="member-home-rebook">
          <p className="text-[10px] uppercase tracking-[0.2em] font-extrabold text-white/40 mb-2">Quick rebook</p>
          <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1">
            {w.last_booked.map((t) => (
              <button key={t.id} onClick={() => setTab('book')}
                className="flex-shrink-0 rounded-lg px-3 py-2 border border-white/10 bg-white/[0.04] hover:bg-white/[0.08] text-xs"
                data-testid={`member-home-rebook-${t.id}`}>
                <span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ background: t.colour || 'var(--color-brand-cyan)' }} />
                <span className="font-bold text-white">{t.name}</span>
                {t.duration_min && <span className="text-white/50 ml-1">· {t.duration_min}m</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function InMinuteBadge({ mins }) {
  if (mins === null || mins === undefined) return null;
  if (mins < 60) return <span className="text-[10px] font-extrabold px-2 py-1 rounded-full bg-emerald-500/15 text-emerald-400 whitespace-nowrap">in {mins}m</span>;
  if (mins < 60 * 24) return <span className="text-[10px] font-extrabold px-2 py-1 rounded-full bg-white/10 text-white/80 whitespace-nowrap">in {Math.round(mins / 60)}h</span>;
  const days = Math.round(mins / (60 * 24));
  return <span className="text-[10px] font-extrabold px-2 py-1 rounded-full bg-white/5 text-white/60 whitespace-nowrap">in {days}d</span>;
}

function formatStartsAt(iso) {
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    const tomorrow = new Date(now); tomorrow.setDate(now.getDate() + 1);
    if (sameDay) return `Today · ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    if (d.toDateString() === tomorrow.toDateString()) return `Tomorrow · ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    return d.toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

