/**
 * /complete-profile — Iter 220bz backward-compat gate.
 *
 * Existing trials that signed up before the mandatory step-2 form
 * shipped are routed here from `DashboardRoute` until their org doc
 * has `profile_completed_at`. Same fields as the new signup flow's
 * step 2; sign-out + close are intentionally NOT exposed (this is a
 * blocking gate). The user can only proceed by completing the form.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Loader2, ArrowRight, ShieldCheck, LogOut } from 'lucide-react';

import { useAuth } from '../App';
import ProfileCompletionFields, {
  emptyProfileForm, findMissingRequired,
} from '../components/shared/ProfileCompletionFields';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function CompleteProfilePage() {
  const navigate = useNavigate();
  const { user, token, logout } = useAuth();
  const [form, setForm] = useState(() => ({
    ...emptyProfileForm(),
    primary_contact_name: user?.full_name || '',
    primary_contact_email: user?.email || '',
    primary_contact_phone: user?.phone || '',
  }));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // If they already completed it, skip the gate entirely.
  useEffect(() => {
    if (user?.profile_completed_at) navigate('/dashboard', { replace: true });
  }, [user, navigate]);

  useEffect(() => {
    const prev = document.title;
    document.title = 'Complete your profile · Pulse Fitness';
    return () => { document.title = prev; };
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    const missing = findMissingRequired(form);
    if (missing.length) {
      setError(`Please fill in: ${missing.join(', ').replace(/_/g, ' ')}`);
      return;
    }
    setLoading(true);
    try {
      // Only send the keys the server allows; strip the UI-only toggle.
      const {
        has_different_company_phone,
        company_search_query: _company_search_query,
        ...payload
      } = form;
      if (!has_different_company_phone) payload.company_phone = '';
      await axios.post(`${API}/account/complete-profile`, payload, {
        headers: { Authorization: `Bearer ${token}` },
      });
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not save. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-zinc-950">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-16">
        <div className="mb-6 flex items-start justify-between">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-emerald-700">
              <ShieldCheck size={11} /> One-time setup
            </span>
            <h1 className="mt-3 text-2xl md:text-3xl font-black tracking-tight text-slate-900 dark:text-zinc-100" data-testid="complete-profile-title">
              Finish setting up your account
            </h1>
            <p className="mt-1.5 text-sm text-slate-500 max-w-xl">
              We need a few details before we unlock the dashboard.
              Takes ~60 seconds and is required by our compliance policy.
            </p>
          </div>
          <button
            type="button"
            onClick={logout}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-full border border-slate-200 bg-white text-xs font-semibold text-slate-600 hover:text-slate-900 hover:border-slate-400 transition dark:bg-zinc-900 dark:border-zinc-800 dark:text-zinc-300"
            data-testid="complete-profile-signout"
          >
            <LogOut size={12} /> Sign out
          </button>
        </div>

        <form onSubmit={submit} data-testid="complete-profile-form">
          {error ? (
            <div
              className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"
              data-testid="complete-profile-error"
            >
              {error}
            </div>
          ) : null}

          <ProfileCompletionFields form={form} setForm={setForm} />

          <button
            type="submit"
            disabled={loading}
            className="gx-cta mt-6 w-full inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-bold disabled:opacity-60"
            data-testid="complete-profile-submit"
          >
            {loading
              ? <><Loader2 size={14} className="animate-spin" /> Saving…</>
              : <>Save and continue <ArrowRight size={14} /></>}
          </button>
        </form>
      </div>
    </div>
  );
}
