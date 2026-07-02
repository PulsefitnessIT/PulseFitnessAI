/**
 * Pulse Fitness Memberships — Public Kiosk Check-in (Phase 4).
 *
 * Tablet-friendly fullscreen UI at /checkin/kiosk?token=...
 *
 * Flow:
 *   1. Member taps "Check in"
 *   2. Types their name → sees results (first name + last initial only)
 *   3. Taps theirs → enters 6-digit code from their Pass tab
 *   4. Backend verifies TOTP, marks the next-class booking as attended
 *   5. Big "Welcome, {first_name}!" success screen → auto-resets in 4s
 */
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { CheckCircle2, AlertTriangle, Search, ArrowLeft, Loader2 } from 'lucide-react';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function KioskCheckin() {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const [step, setStep] = useState('idle');  // idle | search | code | success | error
  const [studio, setStudio] = useState('Studio');
  const [classes, setClasses] = useState([]);
  const [error, setError] = useState(null);
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [member, setMember] = useState(null);
  const [code, setCode] = useState('');
  const [success, setSuccess] = useState(null);
  const [loading, setLoading] = useState(false);

  // Bootstrap — fetch today's classes (also validates the token)
  useEffect(() => {
    if (!token) {
      setError('No kiosk token in the URL. Ask your studio admin for a fresh URL.');
      setStep('error');
      return;
    }
    axios.get(`${API_BASE}/memberships/kiosk/today?token=${encodeURIComponent(token)}`)
      .then((r) => {
        setStudio(r.data.organization_name || 'Studio');
        setClasses(r.data.classes || []);
      })
      .catch((e) => {
        setError(e.response?.data?.detail || 'Could not connect to Pulse Fitness');
        setStep('error');
      });
  }, [token]);

  // Auto-reset to idle after success
  useEffect(() => {
    if (step === 'success') {
      const t = setTimeout(reset, 5000);
      return () => clearTimeout(t);
    }
  }, [step]);

  // Debounced lookup
  useEffect(() => {
    if (step !== 'search' || q.length < 2) { setResults([]); return; }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const r = await axios.post(`${API_BASE}/memberships/kiosk/lookup`, { token, q });
        if (!cancelled) setResults(r.data.results || []);
      } catch (e) {
        if (!cancelled) setResults([]);
      }
    }, 200);
    return () => { cancelled = true; clearTimeout(t); };
  }, [q, step, token]);

  const reset = () => {
    setStep('idle'); setQ(''); setResults([]); setMember(null); setCode(''); setSuccess(null);
  };

  const submitCode = async () => {
    if (code.length !== 6 || !member) return;
    setLoading(true);
    try {
      const r = await axios.post(`${API_BASE}/memberships/kiosk/checkin`, {
        token, member_id: member.id, code,
      });
      setSuccess(r.data);
      setStep('success');
    } catch (e) {
      const msg = e.response?.data?.detail || 'Code did not match';
      setError(msg);
      setTimeout(() => setError(null), 3500);
    }
    setLoading(false);
  };

  if (step === 'error') {
    return (
      <Shell studio="Kiosk error">
        <div className="text-center max-w-md">
          <AlertTriangle size={56} className="mx-auto text-red-400 mb-4" />
          <h2 className="text-2xl font-extrabold mb-2">Kiosk unavailable</h2>
          <p className="text-white/70 text-sm">{error}</p>
        </div>
      </Shell>
    );
  }

  if (step === 'success') {
    return (
      <Shell studio={studio}>
        <div className="text-center max-w-md" data-testid="kiosk-success">
          <div className="w-32 h-32 rounded-full bg-emerald-500/20 mx-auto grid place-items-center mb-6">
            <CheckCircle2 size={72} className="text-emerald-400" />
          </div>
          <h2 className="text-4xl font-extrabold mb-3">Welcome, {success?.first_name}!</h2>
          {success?.next_class_name ? (
            <p className="text-white/80 text-lg">You're checked in for <strong>{success.next_class_name}</strong>.</p>
          ) : (
            <p className="text-white/70 text-base">No class booking found in the next hour — see reception if you need help.</p>
          )}
          <button onClick={reset}
            className="mt-8 px-6 py-2.5 rounded-full text-sm font-bold bg-white/10 text-white hover:bg-white/20"
            data-testid="kiosk-reset">
            Done
          </button>
        </div>
      </Shell>
    );
  }

  if (step === 'idle') {
    return (
      <Shell studio={studio}>
        <div className="text-center max-w-md">
          <h2 className="text-5xl font-extrabold mb-2 tracking-tight">Welcome</h2>
          <p className="text-white/70 mb-10">Tap below to check in for your class.</p>
          <button onClick={() => setStep('search')}
            className="px-10 py-4 rounded-full text-base font-extrabold tracking-wide"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="kiosk-start">
            Check in
          </button>
          {classes.length > 0 && (
            <div className="mt-12 text-left">
              <p className="text-[10px] uppercase tracking-[0.18em] font-bold text-white/40 mb-2">Today at {studio}</p>
              <div className="space-y-1.5">
                {classes.slice(0, 5).map((c) => (
                  <div key={c.id} className="flex items-center gap-3 text-sm border-l-2 border-cyan-400/60 pl-3">
                    <span className="font-mono text-white/60 w-12">
                      {c.starts_at && new Date(c.starts_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <span className="font-bold flex-1 truncate">{c.name}</span>
                    {c.instructor_name && <span className="text-xs text-white/40">{c.instructor_name}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </Shell>
    );
  }

  if (step === 'search') {
    return (
      <Shell studio={studio} onBack={reset}>
        <div className="w-full max-w-md">
          <h2 className="text-3xl font-extrabold mb-1">Find your name</h2>
          <p className="text-white/60 text-sm mb-6">Type your first or last name.</p>
          <div className="relative">
            <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/40 pointer-events-none" />
            <input autoFocus type="text" placeholder="e.g. Emma"
              value={q} onChange={(e) => setQ(e.target.value)}
              className="w-full pl-11 pr-4 py-4 rounded-full bg-white/10 text-white text-lg placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-cyan-400 dark:bg-zinc-900"
              data-testid="kiosk-search-input" />
          </div>
          <div className="mt-4 space-y-2 max-h-[40vh] overflow-y-auto">
            {results.map((m) => (
              <button key={m.id}
                onClick={() => { setMember(m); setStep('code'); setCode(''); }}
                className="w-full text-left px-4 py-3 rounded-2xl bg-white/5 hover:bg-white/10 border border-white/10 transition dark:bg-zinc-900"
                data-testid={`kiosk-result-${m.id}`}>
                <p className="font-extrabold text-base">{m.display_name}</p>
              </button>
            ))}
            {q.length >= 2 && results.length === 0 && (
              <p className="text-center text-white/50 text-sm py-4">No matches — try a different spelling.</p>
            )}
          </div>
        </div>
      </Shell>
    );
  }

  if (step === 'code') {
    return (
      <Shell studio={studio} onBack={() => setStep('search')}>
        <div className="w-full max-w-md text-center">
          <h2 className="text-3xl font-extrabold mb-1">Hi, {member?.display_name}</h2>
          <p className="text-white/60 text-sm mb-6">
            Open your member app, tap <strong>Pass</strong>, then enter the 6-digit code shown there.
          </p>
          <input autoFocus type="tel" inputMode="numeric" pattern="[0-9]*"
            placeholder="······"
            maxLength={6}
            value={code}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, '').slice(0, 6);
              setCode(v);
              if (v.length === 6) {
                // Auto-submit when 6 digits typed
                setTimeout(() => submitCode(), 50);
              }
            }}
            className="w-full px-4 py-5 rounded-2xl bg-white/10 text-white text-3xl tracking-[0.5em] text-center font-mono placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-cyan-400"
            data-testid="kiosk-code-input" />
          {error && <p className="mt-3 text-sm text-red-400 font-bold">{error}</p>}
          <button onClick={submitCode} disabled={code.length !== 6 || loading}
            className="mt-6 px-8 py-3.5 rounded-full text-sm font-extrabold disabled:opacity-40"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="kiosk-code-submit">
            {loading ? <Loader2 size={14} className="animate-spin inline mr-1" /> : null}
            Confirm
          </button>
        </div>
      </Shell>
    );
  }

  return null;
}


function Shell({ studio, children, onBack }) {
  const subtle = useMemo(() => ({
    background: 'radial-gradient(circle at 20% 20%, rgba(25,205,255,0.12), transparent 60%), radial-gradient(circle at 80% 80%, rgba(25, 205, 255,0.10), transparent 60%), var(--color-surface-darker)',
  }), []);
  return (
    <div className="min-h-screen w-full text-white overflow-hidden flex flex-col" style={subtle} data-testid="kiosk-shell">
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          {onBack && (
            <button onClick={onBack} className="w-10 h-10 rounded-full bg-white/5 hover:bg-white/10 grid place-items-center dark:bg-zinc-900" data-testid="kiosk-back">
              <ArrowLeft size={18} />
            </button>
          )}
          <p className="text-[10px] uppercase tracking-[0.25em] font-bold text-cyan-400">{studio}</p>
        </div>
        <p className="text-[10px] uppercase tracking-[0.18em] font-bold text-white/40">Kiosk · Pulse Fitness</p>
      </div>
      <div className="flex-1 grid place-items-center p-6">
        {children}
      </div>
      <div className="px-6 py-3 text-center">
        <p className="text-[10px] text-white/30">{new Date().toLocaleString([], { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}</p>
      </div>
    </div>
  );
}
