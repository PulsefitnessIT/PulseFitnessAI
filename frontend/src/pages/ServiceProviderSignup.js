/**
 * Self-serve Service Provider signup (Iter 253).
 *
 * Public page where a field-service supplier signs up for the Service Desk
 * + Engineer App package. On success they're logged in and sent to the
 * setup wizard (/service-desk/setup), then their own Service Desk.
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ArrowRight, Eye, EyeOff, Loader2, Headphones, Check } from 'lucide-react';

import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PERKS = [
  'Branded Service Desk for your whole team',
  'Offline-ready Engineer App (jobs, photos, signatures, invoices)',
  'SLA tracking, scheduling & customer job-tracking portal',
  'Optional Sage / Sicon integration when you need it',
];

export default function ServiceProviderSignup() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [form, setForm] = useState({ company_name: '', full_name: '', email: '', password: '' });
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/service-provider/signup`, form);
      if (!data?.token) throw new Error('No token returned');
      login(data.token, data.user);
      navigate('/service-desk/setup', { replace: true });
    } catch (err) {
      notifyApiError(notify, err, 'Could not create your account');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-white" data-testid="sp-signup-page">
      {/* Left — value panel */}
      <div className="md:w-1/2 bg-slate-900 text-white p-8 md:p-14 flex flex-col justify-center">
        <div className="flex items-center gap-2 mb-8">
          <Headphones className="text-orange-400" size={26} />
          <span className="text-lg font-bold tracking-tight">GymAxis Service Ops</span>
        </div>
        <h1 className="text-3xl md:text-4xl font-bold leading-tight mb-4">
          Run your field-service business on one platform.
        </h1>
        <p className="text-slate-300 text-base mb-8 max-w-md">
          Spin up your own Service Desk and Engineer App in minutes. No setup calls required —
          but we're here if you want a hand.
        </p>
        <ul className="space-y-3">
          {PERKS.map((p) => (
            <li key={p} className="flex items-start gap-3 text-slate-200">
              <span className="mt-0.5 inline-flex items-center justify-center w-5 h-5 rounded-full bg-orange-500/20 text-orange-400 shrink-0">
                <Check size={13} />
              </span>
              <span className="text-sm">{p}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Right — form */}
      <div className="md:w-1/2 p-8 md:p-14 flex flex-col justify-center">
        <div className="max-w-md w-full mx-auto">
          <h2 className="text-2xl font-bold text-slate-900 mb-1">Create your account</h2>
          <p className="text-sm text-slate-500 mb-8">Start your free trial — no card needed.</p>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Company name</label>
              <input
                required value={form.company_name} onChange={set('company_name')}
                placeholder="FitFix Engineering Ltd"
                className="w-full px-3 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none"
                data-testid="sp-signup-company"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Your name</label>
              <input
                required value={form.full_name} onChange={set('full_name')}
                placeholder="Sam Smith"
                className="w-full px-3 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none"
                data-testid="sp-signup-name"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Work email</label>
              <input
                required type="email" value={form.email} onChange={set('email')}
                placeholder="you@company.com"
                className="w-full px-3 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none"
                data-testid="sp-signup-email"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
              <div className="relative">
                <input
                  required type={showPass ? 'text' : 'password'} value={form.password} onChange={set('password')}
                  placeholder="At least 8 characters"
                  className="w-full px-3 py-2.5 pr-10 border border-slate-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none"
                  data-testid="sp-signup-password"
                />
                <button type="button" onClick={() => setShowPass((s) => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  aria-label={showPass ? 'Hide password' : 'Show password'}>
                  {showPass ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              type="submit" disabled={loading}
              className="w-full inline-flex items-center justify-center gap-2 bg-orange-500 hover:bg-orange-600 disabled:opacity-60 text-white font-semibold py-2.5 rounded-lg transition-colors"
              data-testid="sp-signup-submit"
            >
              {loading ? <Loader2 className="animate-spin" size={18} /> : <>Create account <ArrowRight size={18} /></>}
            </button>
          </form>

          <p className="text-sm text-slate-500 mt-6 text-center">
            Already have an account? <Link to="/login" className="text-orange-600 font-medium hover:underline">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
