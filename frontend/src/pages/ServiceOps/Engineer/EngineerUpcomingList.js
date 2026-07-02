/**
 * EngineerUpcomingList — Iter 220i
 *
 * Engineer-facing list of all upcoming jobs in date order. Surfaced
 * when the engineer taps the "Upcoming" tile on the Home screen.
 * Each row links straight to the job detail.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Loader2, Calendar, MapPin, ChevronRight, CalendarX,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

function fmtDate(iso) {
  if (!iso) return { day: '—', time: '' };
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { day: iso, time: '' };
  return {
    day: d.toLocaleDateString(undefined, { weekday: 'short', day: '2-digit', month: 'short' }),
    time: d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
  };
}

export default function EngineerUpcomingList() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/jobs?when=upcoming`, auth());
      setJobs(r.data?.jobs || r.data || []);
    } catch (e) {
      notify.error('Could not load upcoming jobs', e?.response?.data?.detail || e?.message);
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Group by ISO day so the list reads like a diary.
  const byDay = jobs.reduce((acc, j) => {
    const day = (j.scheduled_at || j.scheduled_for || '').slice(0, 10) || 'unscheduled';
    if (!acc[day]) acc[day] = [];
    acc[day].push(j);
    return acc;
  }, {});
  const days = Object.keys(byDay).sort();

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-upcoming">
      <header className="sticky top-0 z-10 bg-white border-b border-slate-200">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            onClick={() => navigate('/svc/engineer')}
            className="p-2 -ml-2 rounded-lg hover:bg-slate-100"
            data-testid="upcoming-back"
          >
            <ArrowLeft size={18} className="text-slate-700" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-extrabold text-slate-900">Upcoming jobs</h1>
            <p className="text-xs text-slate-500">
              {loading ? 'Loading…' : `${jobs.length} ${jobs.length === 1 ? 'job' : 'jobs'} scheduled`}
            </p>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-4 pb-24 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-slate-400">
            <Loader2 size={20} className="animate-spin mr-2" /> Loading…
          </div>
        ) : jobs.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center" data-testid="upcoming-empty">
            <CalendarX size={32} className="text-slate-300 mx-auto" />
            <p className="mt-3 text-sm font-bold text-slate-900">Nothing booked yet</p>
            <p className="mt-1 text-xs text-slate-500">
              Tap <b>New job</b> on your home screen to schedule one.
            </p>
            <button
              type="button"
              onClick={() => navigate('/svc/engineer/jobs/new')}
              className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 text-white text-xs font-bold"
              data-testid="upcoming-cta-new"
            >
              Book a job
            </button>
          </div>
        ) : (
          days.map((day) => {
            const list = byDay[day];
            const headline = day === 'unscheduled'
              ? 'Unscheduled'
              : new Date(`${day}T00:00:00`).toLocaleDateString(undefined, {
                weekday: 'long', day: '2-digit', month: 'long',
              });
            return (
              <div key={day} data-testid={`upcoming-day-${day}`}>
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2 px-1">
                  {headline}
                </p>
                <div className="space-y-2">
                  {list.map((j) => {
                    const f = fmtDate(j.scheduled_at || j.scheduled_for);
                    return (
                      <button
                        key={j.id}
                        type="button"
                        onClick={() => navigate(`/svc/engineer/jobs/${j.id}`)}
                        className="w-full text-left bg-white rounded-2xl border border-slate-200 p-3 flex items-center gap-3 hover:shadow-sm hover:border-cyan-300 transition-all"
                        data-testid={`upcoming-job-${j.id}`}
                      >
                        <div className="w-12 h-12 rounded-xl bg-cyan-50 text-cyan-700 flex flex-col items-center justify-center flex-shrink-0">
                          <Calendar size={14} />
                          <span className="text-[10px] font-bold mt-0.5">{f.time || '—'}</span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <p className="text-[10px] font-bold tracking-wider text-cyan-600">{j.reference}</p>
                            {j.priority && (
                              <span className="text-[9px] uppercase font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                                {j.priority}
                              </span>
                            )}
                          </div>
                          <p className="text-sm font-bold text-slate-900 truncate" data-testid={`upcoming-job-title-${j.id}`}>
                            {j.title || '(no title)'}
                          </p>
                          <p className="text-[11px] text-slate-500 truncate flex items-center gap-1">
                            <MapPin size={9} />
                            {[j.site_name, j.site_postcode].filter(Boolean).join(' · ') || j.customer_name || '—'}
                          </p>
                        </div>
                        <ChevronRight size={14} className="text-slate-300 flex-shrink-0" />
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })
        )}
      </main>
    </div>
  );
}
