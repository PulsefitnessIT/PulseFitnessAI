/**
 * Iter 216h173 — Shared building blocks for the member portal tabs.
 *
 * Extracted from MemberPortal.js so each lazy-loaded tab (Book, Bookings,
 * Plan, Pass, Profile) can pull the same primitives without dragging the
 * entire portal chunk along.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2 } from 'lucide-react';

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;
export const MEMBER_TOKEN_KEY = 'member_token';

export function CTAButton({ tone, onClick, busy, children, testid }) {
  const styles = {
    book:     'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] hover:brightness-110',
    waitlist: 'bg-violet-500/20 text-violet-200 border border-violet-400/40',
    cancel:   'bg-transparent text-white/70 border border-white/20 hover:bg-white dark:bg-zinc-900/5',
  };
  return (
    <button onClick={onClick} disabled={busy} data-testid={testid}
      className={`px-3 py-2 rounded-lg text-xs font-extrabold uppercase tracking-wider transition shrink-0 ${styles[tone]} disabled:opacity-50`}>
      {busy ? '…' : children}
    </button>
  );
}

export function Pill({ tone, children, testid }) {
  const map = {
    emerald: 'bg-emerald-500/20 text-emerald-300',
    violet: 'bg-violet-500/20 text-violet-300',
    amber: 'bg-amber-500/20 text-amber-300',
  };
  return <span data-testid={testid} className={`text-[9px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded ${map[tone]}`}>{children}</span>;
}

export function Stat({ label, value }) {
  return (
    <div>
      <div className="text-xl font-extrabold tracking-tight">{value}</div>
      <div className="text-[9px] font-bold uppercase tracking-[0.2em] text-white/50 mt-0.5">{label}</div>
    </div>
  );
}

export function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/40">{label}</span>
      <span className="text-sm font-bold text-white text-right">{value}</span>
    </div>
  );
}

export function LabelledInput({ label, value, onChange, type = 'text', required, testid }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/50">{label}{required ? ' *' : ''}</span>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} required={required}
        autoCapitalize={type === 'email' ? 'none' : undefined}
        autoCorrect={type === 'email' ? 'off' : undefined}
        className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
        data-testid={testid} />
    </label>
  );
}

export function CenterLoader() {
  return <div className="py-12 grid place-items-center text-white/40"><Loader2 className="animate-spin" /></div>;
}

export function EmptyCard({ text }) {
  return <div className="rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.02] p-5 text-center text-white/50 text-sm">{text}</div>;
}

export function formatTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function startOfWeek(d) {
  const copy = new Date(d); copy.setHours(0, 0, 0, 0);
  const day = copy.getDay();
  copy.setDate(copy.getDate() - day);  // Sunday
  return copy;
}

export function groupByDay(occs, weekStart) {
  const days = [...Array(7)].map((_, i) => {
    const d = new Date(weekStart.getTime() + i * 86400000); d.setHours(0, 0, 0, 0); return d;
  });
  return days.map((day) => ({
    day,
    items: occs.filter((o) => new Date(o.starts_at).toDateString() === day.toDateString())
               .sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at)),
  }));
}

export function SocialPulse({ occId }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    let cancel = false;
    axios.get(`${API}/member/social-pulse/${occId}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem(MEMBER_TOKEN_KEY)}` },
    }).then((r) => { if (!cancel) setData(r.data); }).catch(() => {});
    return () => { cancel = true; };
  }, [occId]);
  if (!data) return null;
  const { booked_this_week, recent_names } = data;
  if (!booked_this_week && !recent_names?.length) return null;
  const pieces = [];
  if (booked_this_week > 0) pieces.push(`🔥 ${booked_this_week} booked this week`);
  if (recent_names?.length > 0) pieces.push(`${recent_names.slice(0, 2).join(', ')} just joined`);
  return (
    <div className="mt-1.5 text-[10px] text-white/55 font-medium truncate" data-testid={`member-social-pulse-${occId}`}>
      {pieces.join(' · ')}
    </div>
  );
}

export function AdSlot({ slug, placement }) {
  const [ads, setAds] = useState([]);
  useEffect(() => {
    if (!slug) { setAds([]); return; }
    axios.get(`${API}/m/${slug}/ads`, { params: { placement } })
      .then((r) => setAds(r.data.ads || [])).catch(() => {});
  }, [slug, placement]);
  if (ads.length === 0) return null;
  const ad = ads[0];  // one-at-a-time for now
  const click = () => {
    if (slug) axios.post(`${API}/m/${slug}/ads/${ad.id}/click`).catch(() => {});
    if (ad.cta_url) window.open(ad.cta_url, '_blank', 'noopener');
  };
  const bg = ad.background_colour || 'var(--color-brand-cyan)';
  return (
    <div onClick={click} data-testid={`member-ad-${ad.id}`}
      className={`rounded-xl p-4 mb-4 cursor-pointer transition hover:scale-[1.01]`}
      style={{ background: `linear-gradient(135deg, ${bg}22, transparent)`, border: `1px solid ${bg}44` }}>
      <div className="flex items-center gap-3">
        {ad.image_url && <img src={ad.image_url} alt="" className="h-12 w-12 rounded-lg object-cover" loading="lazy" decoding="async" />}
        <div className="flex-1 min-w-0">
          <div className="font-extrabold text-sm text-white truncate">{ad.headline}</div>
          {ad.body && <div className="text-xs text-white/70 truncate">{ad.body}</div>}
        </div>
        {ad.cta_label && <div className="text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-1 rounded shrink-0" style={{ background: bg, color: 'var(--color-surface-darker)' }}>{ad.cta_label}</div>}
      </div>
    </div>
  );
}
