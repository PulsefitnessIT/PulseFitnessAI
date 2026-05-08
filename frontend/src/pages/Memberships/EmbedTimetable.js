/**
 * Embeddable timetable widget — gym pastes an <iframe> on their website
 * and this page renders inside it. Minimal chrome, mobile-friendly,
 * loads the public timetable for an org and links each class through
 * to the branded share page.
 *
 * Route: /embed/:slug/timetable
 */
import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Clock, Users, MapPin } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;


export default function EmbedTimetable() {
  const { slug } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    axios.get(`${API}/m/${slug}/timetable/embed?days_ahead=14`)
      .then((r) => setData(r.data))
      .catch((e) => setError(e.response?.data?.detail || 'Studio not found'));
  }, [slug]);

  if (error) {
    return (
      <div className="p-6 text-center text-zinc-700 text-sm" data-testid="embed-error">
        {error}
      </div>
    );
  }
  if (!data) {
    return <div className="p-8 text-center text-zinc-400 animate-pulse text-sm">Loading timetable…</div>;
  }

  const { organization: org, occurrences } = data;
  // Group by day for a cleaner read
  const byDay = occurrences.reduce((acc, o) => {
    const d = new Date(o.starts_at);
    const key = d.toDateString();
    (acc[key] = acc[key] || { date: d, items: [] }).items.push(o);
    return acc;
  }, {});

  return (
    <div className="min-h-screen bg-white text-zinc-900 p-4 sm:p-6 font-sans dark:bg-zinc-900 dark:text-zinc-100" data-testid="embed-timetable">
      <header className="mb-6 flex items-center gap-3">
        {org.logo_url && <img src={org.logo_url} alt={org.name} className="h-9 max-w-[120px] object-contain" />}
        <div>
          <h1 className="text-lg sm:text-xl font-extrabold tracking-tight" style={{ color: org.primary_color }}>{org.name}</h1>
          <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Class timetable</p>
        </div>
      </header>

      {Object.values(byDay).length === 0 ? (
        <p className="text-sm text-zinc-500">No classes scheduled in the next 14 days.</p>
      ) : (
        <div className="space-y-5">
          {Object.values(byDay).map(({ date, items }) => (
            <section key={date.toISOString()}>
              <h2 className="text-[10px] uppercase tracking-[0.2em] font-extrabold text-zinc-400 mb-2">
                {date.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' })}
              </h2>
              <div className="space-y-2">
                {items.map((o) => (
                  <a key={o.id}
                    href={`/m/${slug}/c/${o.id}`}
                    target="_top"
                    rel="noopener"
                    className="block rounded-lg border border-zinc-200 hover:border-current p-3 transition group dark:border-zinc-800"
                    style={{ '--brand': org.primary_color }}
                    data-testid={`embed-class-${o.id}`}>
                    <div className="flex items-center gap-3">
                      <div className="flex-shrink-0 w-14 text-center">
                        <p className="text-base font-extrabold tracking-tight">
                          {new Date(o.starts_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </p>
                        <p className="text-[10px] text-zinc-500">{o.duration_min}min</p>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-bold text-sm truncate group-hover:underline">{o.name}</p>
                        <p className="text-[11px] text-zinc-500 truncate flex items-center gap-2 mt-0.5">
                          {o.instructor_name && <span>{o.instructor_name}</span>}
                          {o.location && <span><MapPin size={9} className="inline mr-0.5" />{o.location}</span>}
                        </p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        {o.is_full ? (
                          <span className="text-[10px] font-extrabold uppercase tracking-wider text-amber-600">Waitlist</span>
                        ) : (
                          <span className="text-[10px] font-extrabold uppercase tracking-wider text-emerald-600">
                            <Users size={9} className="inline mr-0.5" />{o.spots_left} left
                          </span>
                        )}
                      </div>
                    </div>
                  </a>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <footer className="mt-8 pt-4 border-t border-zinc-200 text-[10px] text-zinc-400 text-center dark:border-zinc-800">
        Powered by <a href="https://gymaxis.app" target="_blank" rel="noopener" className="hover:underline">GymAxis</a>
      </footer>
    </div>
  );
}
