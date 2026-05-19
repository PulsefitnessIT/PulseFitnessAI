/**
 * Phase S2 — Front-desk Kiosk page.
 *
 * Public-ish full-screen page mounted at `/staffing/kiosk?id=<kiosk_id>`.
 * Staff tap their tile → enter the shared 4-6 digit PIN → punch.
 *
 * The PIN gates access to the staff directory + the punch endpoint;
 * no operator JWT is required (kiosks are physically secured at the
 * front desk and revoked individually by a manager). Once the PIN is
 * accepted on this device we cache it in sessionStorage for the
 * lifetime of the tab so users don't have to re-enter on every punch.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import {
  Lock, Loader2, ArrowLeft, Check, AlertTriangle, Play, Square, Coffee,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function PinPad({ onSubmit, error }) {
  const [pin, setPin] = useState('');
  const tap = (n) => {
    if (pin.length >= 6) return;
    setPin(pin + n);
  };
  const back = () => setPin(pin.slice(0, -1));

  const submit = () => { if (pin.length >= 4) onSubmit(pin); };
  return (
    <div className="space-y-4 text-center" data-testid="kiosk-pin-pad">
      <div className="flex justify-center gap-2 tabular-nums">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="w-9 h-12 rounded-lg border flex items-center justify-center text-xl font-bold"
            style={{
              borderColor: pin.length > i ? '#19CDFF' : 'rgba(255,255,255,0.15)',
              color: 'white',
              background: pin.length > i ? 'rgba(25,205,255,0.15)' : 'rgba(255,255,255,0.04)',
            }}>
            {pin[i] ? '●' : ''}
          </div>
        ))}
      </div>
      {error && <p className="text-rose-400 text-sm inline-flex items-center gap-1"><AlertTriangle size={14} /> {error}</p>}
      <div className="grid grid-cols-3 gap-2 max-w-[280px] mx-auto">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
          <button key={n} type="button" onClick={() => tap(String(n))}
            className="h-14 rounded-xl text-2xl font-bold transition-transform active:scale-95"
            style={{ background: 'rgba(255,255,255,0.06)', color: 'white' }}
            data-testid={`kiosk-pin-${n}`}>
            {n}
          </button>
        ))}
        <button type="button" onClick={back} className="h-14 rounded-xl text-sm font-bold inline-flex items-center justify-center"
          style={{ background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.6)' }} data-testid="kiosk-pin-back">
          ←
        </button>
        <button type="button" onClick={() => tap('0')} className="h-14 rounded-xl text-2xl font-bold"
          style={{ background: 'rgba(255,255,255,0.06)', color: 'white' }} data-testid="kiosk-pin-0">
          0
        </button>
        <button type="button" onClick={submit} className="h-14 rounded-xl text-sm font-bold"
          style={{ background: '#19CDFF', color: '#001219' }} data-testid="kiosk-pin-submit">
          OK
        </button>
      </div>
    </div>
  );
}

function PunchScreen({ kioskId, pin, staff, onBack, onPunched }) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null); // { ok, label, kind } or { ok:false, error }
  const punch = async (kind) => {
    setBusy(true);
    setFeedback(null);
    try {
      const { data } = await axios.post(`${API}/staffing/kiosk/punch`,
        { kiosk_id: kioskId, pin, staff_id: staff.id, kind });
      setFeedback({ ok: true, label: kind.replace('_', ' '), kind });
      onPunched && onPunched();
      setTimeout(onBack, 1800);
    } catch (e) {
      setFeedback({ ok: false, error: e.response?.data?.detail || 'Punch failed' });
    }
    setBusy(false);
  };
  const state = staff.state || 'off';
  const actions = state === 'off'
    ? [{ kind: 'clock_in', icon: Play, label: 'Clock In', bg: '#10B981' }]
    : state === 'on_shift'
      ? [
          { kind: 'break_start', icon: Coffee,  label: 'Start Break', bg: '#F59E0B' },
          { kind: 'clock_out',   icon: Square,  label: 'Clock Out',   bg: '#EF4444' },
        ]
      : [{ kind: 'break_end', icon: Play, label: 'End Break', bg: '#10B981' }];
  return (
    <div className="space-y-6 text-center" data-testid="kiosk-punch-screen">
      <button type="button" onClick={onBack} className="absolute top-4 left-4 inline-flex items-center gap-1 text-sm" style={{ color: 'rgba(255,255,255,0.6)' }} data-testid="kiosk-back">
        <ArrowLeft size={14} /> Back
      </button>
      <div className="space-y-1">
        <p className="text-[10px] uppercase tracking-[0.16em] font-bold" style={{ color: 'rgba(255,255,255,0.5)' }}>Welcome,</p>
        <h2 className="text-3xl font-bold" style={{ color: 'white' }}>{staff.full_name}</h2>
        <p className="text-xs" style={{ color: 'rgba(255,255,255,0.5)' }}>{staff.primary_role}</p>
      </div>
      {feedback?.ok ? (
        <div className="space-y-2">
          <div className="w-16 h-16 rounded-full inline-flex items-center justify-center" style={{ background: 'rgba(16,185,129,0.2)' }}>
            <Check size={32} className="text-emerald-400" />
          </div>
          <p className="text-lg font-bold" style={{ color: 'white' }}>{feedback.label}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {actions.map((a) => (
            <button key={a.kind} type="button" onClick={() => punch(a.kind)} disabled={busy}
              className="w-full max-w-[320px] mx-auto h-16 rounded-2xl text-base font-bold inline-flex items-center justify-center gap-2 transition-transform active:scale-95 disabled:opacity-50"
              style={{ background: a.bg, color: '#001219' }}
              data-testid={`kiosk-action-${a.kind}`}>
              {busy ? <Loader2 size={20} className="animate-spin" /> : <a.icon size={20} />}
              {a.label}
            </button>
          ))}
          {feedback?.error && (
            <p className="text-rose-400 text-sm inline-flex items-center gap-1"><AlertTriangle size={14} /> {feedback.error}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function KioskPage() {
  const [search] = useSearchParams();
  const kioskId = search.get('id');
  const [pin, setPin] = useState(() => sessionStorage.getItem(`kiosk:${kioskId}:pin`) || '');
  const [authError, setAuthError] = useState(null);
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async (currentPin) => {
    if (!kioskId) return;
    try {
      const { data: d } = await axios.get(`${API}/staffing/kiosk/${kioskId}/staff?pin=${currentPin}`);
      setData(d);
      setAuthError(null);
      sessionStorage.setItem(`kiosk:${kioskId}:pin`, currentPin);
    } catch (e) {
      setData(null);
      sessionStorage.removeItem(`kiosk:${kioskId}:pin`);
      setPin('');
      setAuthError(e.response?.data?.detail || 'Invalid PIN');
    }
  }, [kioskId]);

  useEffect(() => { if (pin) load(pin); }, [pin, load]);

  const filtered = useMemo(() => data?.staff || [], [data]);

  if (!kioskId) {
    return (
      <div className="min-h-screen flex items-center justify-center text-white" style={{ background: '#0A0C10' }}>
        <p className="text-sm">Missing kiosk id. Use the URL provided by your manager.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen relative" style={{ background: '#0A0C10', color: 'white' }} data-testid="kiosk-page">
      <div className="absolute top-4 right-4 text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'rgba(255,255,255,0.4)' }}>
        Kiosk · {data?.kiosk_name || '…'}
      </div>
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="w-full max-w-3xl">
          {!data ? (
            <div className="space-y-4">
              <div className="text-center space-y-1">
                <Lock size={28} className="mx-auto text-cyan-400" />
                <h1 className="text-2xl font-bold">Front-desk kiosk</h1>
                <p className="text-sm" style={{ color: 'rgba(255,255,255,0.5)' }}>Enter the 4-6 digit PIN</p>
              </div>
              <PinPad onSubmit={(p) => { setPin(p); }} error={authError} />
            </div>
          ) : selected ? (
            <PunchScreen
              kioskId={kioskId}
              pin={pin}
              staff={selected}
              onBack={() => { setSelected(null); load(pin); }}
              onPunched={() => load(pin)}
            />
          ) : (
            <div className="space-y-4">
              <div className="text-center">
                <h1 className="text-2xl font-bold" style={{ color: 'white' }}>Tap your name to punch</h1>
                <p className="text-sm" style={{ color: 'rgba(255,255,255,0.5)' }}>{filtered.length} staff registered</p>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3" data-testid="kiosk-staff-grid">
                {filtered.map((s) => (
                  <button key={s.id} type="button" onClick={() => setSelected(s)}
                    className="rounded-2xl p-4 text-left transition-transform active:scale-95"
                    style={{
                      background: 'rgba(255,255,255,0.06)',
                      border: `1px solid ${s.state === 'on_shift' ? '#10B981' : s.state === 'on_break' ? '#F59E0B' : 'rgba(255,255,255,0.1)'}`,
                    }}
                    data-testid={`kiosk-staff-${s.id}`}>
                    <p className="text-base font-bold truncate" style={{ color: 'white' }}>{s.full_name}</p>
                    <p className="text-[10px] uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.5)' }}>{s.primary_role}</p>
                    <p className="text-[10px] mt-1 inline-flex items-center gap-1"
                      style={{
                        color: s.state === 'on_shift' ? '#10B981' : s.state === 'on_break' ? '#F59E0B' : 'rgba(255,255,255,0.4)',
                      }}>
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'currentColor' }} />
                      {s.state === 'on_shift' ? 'On shift' : s.state === 'on_break' ? 'On break' : 'Off'}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
