/**
 * EngineerReferralLanding.js (iter 216h287 — Gap 9)
 *
 * Public branded recruit page reached via an engineer-of-engineer
 * referral link `/engineer/r/:code`. Shows the referring engineer's
 * first name + company + service area, with a single big CTA into
 * the standard public apply form, carrying the `?eref=CODE` query
 * param so the application stays attributed.
 *
 * Lean by design — no shared marketing chrome. The point is to
 * convert a referred engineer in under 10 seconds.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Link, useParams, Navigate } from 'react-router-dom';
import { Wrench, ShieldCheck, ArrowRight, Sparkles, Loader2, MapPin } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';

export default function EngineerReferralLanding() {
  const { code } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/partners/public/by-eref/${encodeURIComponent(code)}`);
        setData(r.data);
      } catch (e) {
        setError(e?.response?.data?.detail || 'Referral link not found');
      }
    })();
  }, [code]);

  if (error) {
    // Don't 404 hard — punt to the standard apply form so the lead isn't lost
    return <Navigate to="/partners/engineers/apply" replace />;
  }

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center" data-testid="eref-loading">
        <Loader2 size={20} className="animate-spin text-zinc-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950 flex flex-col" data-testid="eref-landing-page">
      <header className="px-6 py-4 flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800">
        <Link to="/" className="text-sm font-bold tracking-tight inline-flex items-center gap-1.5 text-zinc-900 dark:text-zinc-100">
          <ShieldCheck size={14} className="text-blue-700" /> GymAxis Partner Network
        </Link>
        <Link to="/partners/engineers" className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
          About the network
        </Link>
      </header>
      <main className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="max-w-2xl w-full text-center">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-100 text-blue-900 text-[11px] font-bold mb-5"
               data-testid="eref-recommended-pill">
            <Sparkles size={11} /> Personally recommended by an active GymAxis engineer
          </div>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-zinc-900 dark:text-zinc-100">
            <span data-testid="eref-engineer-first-name">{data.first_name}</span>
            {data.company_name && (
              <span className="text-zinc-500 dark:text-zinc-400 font-bold"> · {data.company_name}</span>
            )}
            <br />
            thinks you&apos;d be a brilliant Partner Engineer.
          </h1>
          <p className="mt-5 text-base sm:text-lg text-zinc-600 dark:text-zinc-400 leading-relaxed">
            Run your own gym maintenance round on the country&apos;s fastest-growing
            workforce platform. Inbound jobs, instant quoting, paid faster — and your
            fees drop the more engineers you recommend.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              to={`/partners/engineers/apply?eref=${encodeURIComponent(data.referral_code)}`}
              className="inline-flex items-center gap-2 px-7 py-3.5 rounded-md text-sm font-bold text-white shadow-sm transition-transform hover:scale-[1.02]"
              style={{ background: 'var(--color-brand-blue, #0055FF)' }}
              data-testid="eref-apply-cta"
            >
              <Wrench size={14} /> Apply in 3 minutes <ArrowRight size={14} />
            </Link>
            <Link
              to="/partners/engineers"
              className="text-sm text-zinc-600 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100"
              data-testid="eref-learn-more-link"
            >
              Read the network terms
            </Link>
          </div>

          <div className="mt-10 grid grid-cols-1 sm:grid-cols-3 gap-3 text-left max-w-xl mx-auto" data-testid="eref-perks">
            <Perk icon={Wrench} title="Inbound jobs" body="Gyms route work to local engineers — you set your radius and skills." />
            <Perk icon={Sparkles} title="Plan drops as you grow" body="Refer 5 gyms or engineers → £15/mo. 10 → free. Same ladder either way." />
            <Perk icon={ShieldCheck} title="Backed by GymAxis" body="DBS, RTW, insurance all verified by the platform — gyms trust the badge." />
          </div>

          {data.service_area && (
            <p className="mt-8 text-[12px] text-zinc-500 dark:text-zinc-400 inline-flex items-center gap-1.5"
               data-testid="eref-service-area">
              <MapPin size={11} /> {data.first_name} is based around {data.service_area}
            </p>
          )}
        </div>
      </main>
      <footer className="px-6 py-4 text-center text-[11px] text-zinc-400 border-t border-zinc-200 dark:border-zinc-800">
        Attribution: <span className="font-mono">{data.referral_code}</span> ·{' '}
        <Link to="/privacy" className="hover:underline">Privacy</Link>
      </footer>
    </div>
  );
}

function Perk({ icon: Icon, title, body }) {
  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
      <Icon size={16} className="text-blue-700 mb-2" />
      <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">{title}</p>
      <p className="text-[12px] text-zinc-600 dark:text-zinc-400 mt-0.5 leading-snug">{body}</p>
    </div>
  );
}
