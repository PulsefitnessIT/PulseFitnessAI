/**
 * Public Email Preference Centre — routed at /preferences/:token (no auth).
 * Linked from the {{preferences_link}} merge tag in every campaign send.
 * Recipients toggle category-level subscriptions or unsubscribe from all.
 */
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Check, Loader2, ShieldCheck, MailX } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

export default function PublicPreferencesPage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [optedOut, setOptedOut] = useState([]);
  const [unsubAll, setUnsubAll] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    axios.get(`${API}/comms/public/preferences/${token}`)
      .then(res => {
        setData(res.data);
        setOptedOut(res.data.opted_out_categories || []);
        setUnsubAll(!!res.data.unsubscribed_all);
      })
      .catch(() => setError('This link is invalid or has expired.'));
  }, [token]);

  const toggleCategory = (id) => {
    setSaved(false);
    setOptedOut(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]);
  };

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await axios.post(`${API}/comms/public/preferences/${token}`, {
        unsubscribed_all: unsubAll,
        opted_out_categories: unsubAll ? [] : optedOut,
      });
      setSaved(true);
    } catch {
      setError('Sorry, we could not save your preferences. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  if (error) {
    return (
      <Shell>
        <div className="text-center py-10" data-testid="prefs-error">
          <MailX className="w-10 h-10 mx-auto mb-4 text-rose-400" />
          <p className="text-slate-300">{error}</p>
        </div>
      </Shell>
    );
  }

  if (!data) {
    return (
      <Shell>
        <div className="flex items-center justify-center py-16" data-testid="prefs-loading">
          <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
        </div>
      </Shell>
    );
  }

  return (
    <Shell orgName={data.org_name} orgLogo={data.org_logo}>
      <div data-testid="prefs-page">
        <h1 className="text-2xl font-bold mb-1" style={{ color: '#fff' }}>Email preferences</h1>
        <p className="text-sm text-slate-400 mb-6" data-testid="prefs-email">
          Managing preferences for <span className="text-cyan-300">{data.email}</span>
        </p>

        <div className={`space-y-3 transition-opacity ${unsubAll ? 'opacity-40 pointer-events-none' : ''}`}>
          {data.categories.map(cat => {
            const subscribed = !optedOut.includes(cat.id);
            return (
              <button
                key={cat.id}
                type="button"
                onClick={() => toggleCategory(cat.id)}
                data-testid={`prefs-category-${cat.id}`}
                className="w-full text-left flex items-start gap-4 p-4 rounded-xl border border-white/10 bg-white/[0.03] hover:bg-white/[0.06] transition-colors"
              >
                <span
                  className={`mt-0.5 flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center border transition-colors ${
                    subscribed ? 'bg-cyan-400 border-cyan-400 text-slate-900' : 'border-white/25 text-transparent'
                  }`}
                >
                  <Check className="w-4 h-4" strokeWidth={3} />
                </span>
                <span>
                  <span className="block text-sm font-semibold" style={{ color: '#fff' }}>{cat.label}</span>
                  <span className="block text-xs text-slate-400 mt-0.5">{cat.desc}</span>
                </span>
              </button>
            );
          })}
        </div>

        <label
          className="flex items-center gap-3 mt-6 p-4 rounded-xl border border-rose-500/20 bg-rose-500/[0.06] cursor-pointer"
          data-testid="prefs-unsub-all-row"
        >
          <input
            type="checkbox"
            checked={unsubAll}
            onChange={(e) => { setUnsubAll(e.target.checked); setSaved(false); }}
            className="w-4 h-4 accent-rose-500"
            data-testid="prefs-unsub-all-checkbox"
          />
          <span className="text-sm text-rose-200">Unsubscribe from all emails</span>
        </label>

        <button
          onClick={save}
          disabled={saving}
          data-testid="prefs-save-btn"
          className="mt-6 w-full py-3 rounded-xl bg-cyan-400 text-slate-900 font-semibold text-sm hover:bg-cyan-300 transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <Check className="w-4 h-4" /> : null}
          {saved ? 'Preferences saved' : 'Save preferences'}
        </button>

        <p className="text-xs text-slate-500 mt-6 flex items-start gap-2" data-testid="prefs-why">
          <ShieldCheck className="w-4 h-4 flex-shrink-0 mt-0.5 text-slate-400" />
          You're receiving these emails because of your relationship with {data.org_name}. You can update these choices at any time.
        </p>
      </div>
    </Shell>
  );
}

function Shell({ children, orgName, orgLogo }) {
  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: '#05070A' }}>
      <div className="w-full max-w-lg">
        <div className="flex items-center gap-3 mb-5">
          {orgLogo
            ? <img src={orgLogo} alt={orgName} className="h-9 max-w-[160px] object-contain" />
            : <span className="text-lg font-bold" style={{ color: '#fff' }}>{orgName || 'Pulse Fitness'}</span>}
        </div>
        <div className="rounded-2xl border border-white/10 bg-[#0A0C12] p-7 shadow-2xl">
          {children}
        </div>
        <p className="text-center text-[11px] text-slate-600 mt-4">Powered by Pulse Fitness AI</p>
      </div>
    </div>
  );
}
