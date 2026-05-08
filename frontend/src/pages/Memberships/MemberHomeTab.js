/**
 * Member portal — Home tab.
 *
 * Reads the operator's saved layout (PUT /api/member-app/layout) and renders
 * the active cards. Each card is a simple shortcut that either switches the
 * portal to an existing tab or shows an inline summary. This is the screen
 * the gym owner customises in the Mobile App Builder.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  CalendarDays, ClipboardList, Dumbbell, Wrench, Trophy, Activity,
  ShoppingBag, BarChart3, Megaphone, QrCode, Share2, Sparkles, ChevronRight,
} from 'lucide-react';

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
  const [layout, setLayout] = useState(null);
  const [registry, setRegistry] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    Promise.all([
      axios.get(`${API}/member-app/layout`, { headers }).catch(() => null),
      axios.get(`${API}/member-app/cards`, { headers }).catch(() => null),
    ]).then(([lay, reg]) => {
      if (!alive) return;
      setLayout(lay?.data?.layout || null);
      const map = {};
      (reg?.data?.cards || []).forEach((c) => { map[c.id] = c; });
      setRegistry(map);
      setLoading(false);
    });
    return () => { alive = false; };
  }, [headers, API]);

  if (loading) {
    return <div className="text-center text-white/50 text-sm py-12" data-testid="member-home-loading">Loading…</div>;
  }

  const cards = (layout?.cards || []).filter((c) => c.enabled);

  if (cards.length === 0) {
    return (
      <div className="text-center text-white/60 text-sm py-12" data-testid="member-home-empty">
        Your gym hasn't customised this screen yet.
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="member-home-tab">
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
