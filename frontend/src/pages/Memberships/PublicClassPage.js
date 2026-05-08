/**
 * Branded share page for a single class — the URL gyms drop on
 * Instagram, in WhatsApp, etc. Shows class details + an in-app book CTA.
 *
 * Route: /m/:slug/c/:occId
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import {
  Calendar, Clock, MapPin, Users, ArrowLeft, ExternalLink,
  CheckCircle2, AlertCircle,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function PublicClassPage() {
  const { slug, occId } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    axios.get(`${API}/m/${slug}/c/${occId}`)
      .then((r) => setData(r.data))
      .catch((e) => setError(e.response?.data?.detail || 'Class not found'));
  }, [slug, occId]);

  if (error) {
    return (
      <div className="min-h-screen grid place-items-center bg-zinc-950 text-white p-8" data-testid="public-class-error">
        <div className="text-center">
          <AlertCircle size={42} className="text-red-400 mx-auto mb-3" />
          <p className="text-lg font-bold">{error}</p>
          <button onClick={() => nav('/')} className="mt-4 text-sm text-[var(--color-brand-cyan)] hover:underline">Go home</button>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen grid place-items-center bg-zinc-950 text-white">
        <div className="animate-pulse text-white/50">Loading…</div>
      </div>
    );
  }

  const { organization: org, class: cls } = data;
  const startsAt = cls.starts_at ? new Date(cls.starts_at) : null;
  const dateStr = startsAt ? startsAt.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' }) : '';
  const timeStr = startsAt ? startsAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

  const bookUrl = `/m/${slug}?goto=book&occ=${occId}`;

  return (
    <div className="min-h-screen text-white" data-testid="public-class-page"
      style={{ background: `linear-gradient(135deg, ${org.primary_color}10, var(--color-surface-darker) 60%)` }}>
      <header className="px-4 py-4 flex items-center justify-between max-w-3xl mx-auto">
        <button onClick={() => nav(`/m/${slug}`)} className="text-white/60 hover:text-white text-xs font-bold flex items-center gap-1">
          <ArrowLeft size={12} /> All classes
        </button>
        {org.logo_url ? (
          <img src={org.logo_url} alt={org.name} className="h-8 max-w-[160px] object-contain" />
        ) : (
          <p className="text-xs font-extrabold tracking-wider text-white/70 uppercase">{org.name}</p>
        )}
      </header>

      <main className="max-w-3xl mx-auto px-4 pb-12">
        {cls.image_url && (
          <div className="w-full aspect-video rounded-2xl overflow-hidden mb-5 ring-1 ring-white/10">
            <img src={cls.image_url} alt={cls.name} className="w-full h-full object-cover" />
          </div>
        )}

        <p className="text-[10px] uppercase tracking-[0.2em] font-extrabold mb-1"
          style={{ color: org.primary_color }}>
          {cls.is_course_session ? `Course · session ${cls.course_session_index}/${cls.course_session_total}` : 'Class'}
        </p>
        <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.03em' }}>
          {cls.name}
        </h1>
        {cls.description && (
          <p className="mt-3 text-white/70 leading-relaxed max-w-xl">{cls.description}</p>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-6">
          {dateStr && (
            <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <p className="text-[9px] uppercase tracking-wider font-bold text-white/50 flex items-center gap-1"><Calendar size={9} /> Date</p>
              <p className="font-bold mt-0.5 text-sm" data-testid="public-class-date">{dateStr}</p>
            </div>
          )}
          {timeStr && (
            <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <p className="text-[9px] uppercase tracking-wider font-bold text-white/50 flex items-center gap-1"><Clock size={9} /> Time</p>
              <p className="font-bold mt-0.5 text-sm" data-testid="public-class-time">
                {timeStr} · {cls.duration_min} min
              </p>
            </div>
          )}
          {cls.location && (
            <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <p className="text-[9px] uppercase tracking-wider font-bold text-white/50 flex items-center gap-1"><MapPin size={9} /> Location</p>
              <p className="font-bold mt-0.5 text-sm">{cls.location}</p>
            </div>
          )}
          {cls.instructor_name && (
            <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <p className="text-[9px] uppercase tracking-wider font-bold text-white/50">Instructor</p>
              <p className="font-bold mt-0.5 text-sm">{cls.instructor_name}</p>
            </div>
          )}
          {cls.capacity > 0 && (
            <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <p className="text-[9px] uppercase tracking-wider font-bold text-white/50 flex items-center gap-1"><Users size={9} /> Spots left</p>
              <p className="font-bold mt-0.5 text-sm" data-testid="public-class-spots">
                {cls.is_full ? <span className="text-amber-400">Full · waitlist</span> : `${cls.spots_left} of ${cls.capacity}`}
              </p>
              {!cls.is_full && (
                <div className="mt-1.5 h-1 rounded bg-white/10 overflow-hidden">
                  <div className="h-full rounded" style={{ width: `${cls.fill_pct}%`, background: org.primary_color }} />
                </div>
              )}
            </div>
          )}
        </div>

        <a href={bookUrl}
          className="mt-7 block w-full py-4 rounded-xl text-base font-extrabold text-center uppercase tracking-wider transition hover:brightness-110"
          style={{ background: org.primary_color, color: 'var(--color-surface-darker)' }}
          data-testid="public-class-book">
          {cls.is_full ? 'Join the waitlist' : 'Book your spot'}
        </a>
        <p className="text-[10px] text-white/40 text-center mt-3">
          Sign in or create your free account to confirm — secured by Stripe.
        </p>

        <a href={`/m/${slug}`}
          className="mt-6 block text-center text-xs text-white/50 hover:text-white"
          data-testid="public-class-all-classes">
          View all {org.name} classes <ExternalLink size={9} className="inline ml-0.5" />
        </a>
      </main>
    </div>
  );
}
