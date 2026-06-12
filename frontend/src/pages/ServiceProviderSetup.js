/**
 * Service Provider setup wizard (Iter 253).
 *
 * Three guided steps after self-serve signup — branding, SLA targets, and
 * the first engineer — then unlocks the Service Desk. The desk already
 * works on sensible defaults, so every step is "confirm or customise".
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Check, Loader2, Palette, Timer, UserPlus, ArrowRight, PartyPopper, UploadCloud } from 'lucide-react';

import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
// Iter 256c — the desk's import wizard, embedded as an optional final step.
import DeskImports from '@/pages/ServiceDesk/DeskImports';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const PRIORITIES = [
  { key: 'p1', label: 'P1 · Critical' },
  { key: 'p2', label: 'P2 · High' },
  { key: 'p3', label: 'P3 · Normal' },
  { key: 'p4', label: 'P4 · Low' },
];

const STEPS = [
  { id: 'branding', label: 'Branding', icon: Palette },
  { id: 'sla', label: 'SLA targets', icon: Timer },
  { id: 'engineer', label: 'First engineer', icon: UserPlus },
  { id: 'data', label: 'Bring your data', icon: UploadCloud },
];

export default function ServiceProviderSetup() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const auth = { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } };

  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState(null);
  const [branding, setBranding] = useState({ company_name: '', primary_color: '#0EA5E9', accent_color: '#7C3AED', logo_url: '' });
  const [sla, setSla] = useState({});
  const [eng, setEng] = useState({ full_name: '', email: '', mobile: '' });
  const [tempPw, setTempPw] = useState('');

  const load = useCallback(async () => {
    try {
      const { data: d } = await axios.get(`${API}/service-provider/setup`, auth);
      setData(d);
      setBranding({ company_name: d.company_name || '', ...d.branding });
      setSla(d.sla || {});
      if (d.setup_complete) navigate('/service-desk', { replace: true });
    } catch (e) {
      notifyApiError(notify, e, 'Could not load setup');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveBranding = async () => {
    setBusy(true);
    try {
      await axios.put(`${API}/service-provider/setup/branding`, branding, auth);
      setStep(1);
    } catch (e) { notifyApiError(notify, e, 'Could not save branding'); } finally { setBusy(false); }
  };

  const saveSla = async () => {
    setBusy(true);
    try {
      await axios.put(`${API}/service-provider/setup/sla`, { sla }, auth);
      setStep(2);
    } catch (e) { notifyApiError(notify, e, 'Could not save SLA'); } finally { setBusy(false); }
  };

  const addEngineer = async () => {
    setBusy(true);
    try {
      const { data: r } = await axios.post(`${API}/service-provider/setup/engineer`, eng, auth);
      if (r.temp_password) setTempPw(r.temp_password);
      notify.success('Engineer added', `${eng.full_name} can now use the Engineer App.`);
      setStep(3); // Iter 256c — optional "Bring your data" step before the desk opens
    } catch (e) { notifyApiError(notify, e, 'Could not add engineer'); } finally { setBusy(false); }
  };

  const finish = async () => {
    try {
      await axios.post(`${API}/service-provider/setup/complete`, null, auth);
      if (refreshUser) await refreshUser();
      navigate('/service-desk', { replace: true });
    } catch (e) { notifyApiError(notify, e, 'Could not finish setup'); }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500" data-testid="sp-setup-loading"><Loader2 className="animate-spin mr-2" size={18} /> Loading setup…</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4" data-testid="sp-setup-page">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-bold text-slate-900 mb-1">Welcome, {user?.full_name?.split(' ')[0] || 'there'} 👋</h1>
        <p className="text-sm text-slate-500 mb-8">A few quick steps and your Service Desk is live.</p>

        {/* Stepper */}
        <div className="flex items-center gap-2 mb-8">
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            const done = i < step;
            const active = i === step;
            return (
              <div key={s.id} className="flex items-center gap-2 flex-1" data-testid={`sp-step-${s.id}`}>
                <div className={`flex items-center gap-2 px-3 py-2 rounded-lg w-full ${active ? 'bg-orange-500 text-white' : done ? 'bg-emerald-50 text-emerald-700' : 'bg-white text-slate-400 border border-slate-200'}`}>
                  {done ? <Check size={16} /> : <Icon size={16} />}
                  <span className="text-sm font-medium">{s.label}</span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          {step === 0 && (
            <div className="space-y-4" data-testid="sp-setup-branding">
              <h2 className="text-lg font-semibold text-slate-900">Make it yours</h2>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Company name</label>
                <input value={branding.company_name} onChange={(e) => setBranding({ ...branding, company_name: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-orange-500" data-testid="sp-branding-name" />
              </div>
              <div className="flex gap-4">
                {['primary_color', 'accent_color'].map((k) => (
                  <div key={k} className="flex-1">
                    <label className="block text-sm font-medium text-slate-700 mb-1 capitalize">{k.replace('_', ' ')}</label>
                    <div className="flex items-center gap-2">
                      <input type="color" value={branding[k]} onChange={(e) => setBranding({ ...branding, [k]: e.target.value })}
                        className="w-10 h-10 rounded border border-slate-200 cursor-pointer" data-testid={`sp-branding-${k}`} />
                      <input value={branding[k]} onChange={(e) => setBranding({ ...branding, [k]: e.target.value })}
                        className="flex-1 px-3 py-2 border border-slate-300 rounded-lg outline-none font-mono text-sm" />
                    </div>
                  </div>
                ))}
              </div>
              <button onClick={saveBranding} disabled={busy}
                className="inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 disabled:opacity-60 text-white font-semibold px-5 py-2.5 rounded-lg" data-testid="sp-branding-next">
                {busy ? <Loader2 className="animate-spin" size={16} /> : <>Continue <ArrowRight size={16} /></>}
              </button>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4" data-testid="sp-setup-sla">
              <h2 className="text-lg font-semibold text-slate-900">Service-level targets</h2>
              <p className="text-sm text-slate-500">Hours to first response and to resolve, per priority. Sensible defaults are pre-filled.</p>
              <div className="space-y-2">
                <div className="grid grid-cols-3 text-xs font-semibold text-slate-500 px-1">
                  <span>Priority</span><span>Response (h)</span><span>Resolve (h)</span>
                </div>
                {PRIORITIES.map(({ key, label }) => (
                  <div key={key} className="grid grid-cols-3 gap-2 items-center" data-testid={`sp-sla-row-${key}`}>
                    <span className="text-sm text-slate-700">{label}</span>
                    <input type="number" min="0" value={sla[key]?.response_h ?? ''} onChange={(e) => setSla({ ...sla, [key]: { ...sla[key], response_h: Number(e.target.value) } })}
                      className="px-3 py-2 border border-slate-300 rounded-lg outline-none" data-testid={`sp-sla-${key}-response`} />
                    <input type="number" min="1" value={sla[key]?.resolve_h ?? ''} onChange={(e) => setSla({ ...sla, [key]: { ...sla[key], resolve_h: Number(e.target.value) } })}
                      className="px-3 py-2 border border-slate-300 rounded-lg outline-none" data-testid={`sp-sla-${key}-resolve`} />
                  </div>
                ))}
              </div>
              <div className="flex gap-3">
                <button onClick={() => setStep(0)} className="px-4 py-2.5 text-slate-600 hover:text-slate-900">Back</button>
                <button onClick={saveSla} disabled={busy}
                  className="inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 disabled:opacity-60 text-white font-semibold px-5 py-2.5 rounded-lg" data-testid="sp-sla-next">
                  {busy ? <Loader2 className="animate-spin" size={16} /> : <>Continue <ArrowRight size={16} /></>}
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4" data-testid="sp-setup-engineer">
              <h2 className="text-lg font-semibold text-slate-900">Add your first engineer</h2>
              <p className="text-sm text-slate-500">They'll get a login for the Engineer App. You can add more anytime.</p>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Engineer name</label>
                <input value={eng.full_name} onChange={(e) => setEng({ ...eng, full_name: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-orange-500" data-testid="sp-eng-name" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Engineer email</label>
                <input type="email" value={eng.email} onChange={(e) => setEng({ ...eng, email: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-orange-500" data-testid="sp-eng-email" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Mobile (optional)</label>
                <input value={eng.mobile} onChange={(e) => setEng({ ...eng, mobile: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-orange-500" data-testid="sp-eng-mobile" />
              </div>
              {tempPw && (
                <div className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-3" data-testid="sp-eng-temp-pw">
                  Temporary password: <span className="font-mono font-bold">{tempPw}</span> — share it securely; they'll change it on first sign-in.
                </div>
              )}
              <div className="flex gap-3">
                <button onClick={() => setStep(1)} className="px-4 py-2.5 text-slate-600 hover:text-slate-900">Back</button>
                <button onClick={addEngineer} disabled={busy || !eng.full_name || !eng.email}
                  className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-semibold px-5 py-2.5 rounded-lg" data-testid="sp-finish">
                  {busy ? <Loader2 className="animate-spin" size={16} /> : <>Continue <ArrowRight size={16} /></>}
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-5" data-testid="sp-setup-data">
              {tempPw && (
                <div className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-3" data-testid="sp-eng-temp-pw-recap">
                  Your engineer's temporary password: <span className="font-mono font-bold">{tempPw}</span> — share it securely; they'll change it on first sign-in.
                </div>
              )}
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">Bring your data <span className="text-sm font-normal text-slate-400">(optional)</span></h2>
                  <p className="text-sm text-slate-500 mt-0.5">
                    Import your customer book and historical cases from a CSV or Excel export — or skip and do it later from your desk under <span className="font-semibold">Insights → Import data</span>.
                  </p>
                </div>
                <button onClick={finish} disabled={busy}
                  className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-semibold px-5 py-2.5 rounded-lg shrink-0"
                  data-testid="sp-open-desk">
                  <PartyPopper size={16} /> Finish & open my desk
                </button>
              </div>
              <div className="border-t border-slate-100 pt-5">
                <DeskImports API={API} embedded />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
