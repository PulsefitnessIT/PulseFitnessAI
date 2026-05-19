/**
 * Iter 216h173 — PassTab extracted from MemberPortal.js for lazy-loading.
 *
 * Pulls in the heavy `qrcode` dependency only when the member opens the
 * Pass tab. Previously this dragged ~30 KB of QR generation code into
 * the first paint bundle for every portal session.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Loader2 } from 'lucide-react';
import QRCode from 'qrcode';
import { notify } from '@/components/notifications';
import { API } from '../portalShared';

export default function PassTab({ headers, member }) {
  const [qr, setQr] = useState(null);
  const [dataUrl, setDataUrl] = useState('');
  const [expiresIn, setExpiresIn] = useState(30);
  const pollRef = useRef(null);

  const fetchQr = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/member/qr`, { headers });
      setQr(data);
      setExpiresIn(data.expires_in || 30);
      const url = await QRCode.toDataURL(data.payload, { width: 320, margin: 1, color: { dark: 'var(--color-surface-darker)', light: 'var(--color-white)' } });
      setDataUrl(url);
    } catch { notify.error('Failed to generate pass'); }
  }, [headers]);

  useEffect(() => {
    fetchQr();
    return () => clearInterval(pollRef.current);
  }, [fetchQr]);

  useEffect(() => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(() => {
      setExpiresIn((s) => {
        if (s <= 1) { fetchQr(); return 30; }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(pollRef.current);
  }, [fetchQr, qr?.code]);

  return (
    <div data-testid="member-pass">
      <h2 className="text-xl font-extrabold tracking-tight mb-4" style={{ letterSpacing: '-0.02em' }}>Check-in pass</h2>
      <div className="rounded-2xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.1)] to-transparent p-6 text-center">
        <div className="text-[10px] font-extrabold uppercase tracking-[0.25em] text-[var(--color-brand-cyan)] mb-3">Rotating QR · scan at reception</div>
        {dataUrl ? (
          <div className="inline-block p-4 rounded-2xl bg-white dark:bg-zinc-900" data-testid="member-qr-image">
            <img src={dataUrl} alt="Member QR pass" className="w-64 h-64" decoding="async" />
          </div>
        ) : <div className="w-64 h-64 mx-auto bg-white/5 rounded-2xl grid place-items-center"><Loader2 className="animate-spin" /></div>}
        <div className="mt-4 text-[36px] font-extrabold tracking-[0.4em]" style={{ color: 'var(--color-brand-cyan)' }} data-testid="member-qr-code">{qr?.code || '––––––'}</div>
        <div className="mt-2 text-xs text-white/50">Refreshes in <span className="font-extrabold text-white">{expiresIn}s</span></div>
        <div className="mt-1 text-[10px] text-white/40 tracking-wider uppercase">{member.first_name} {member.last_name}</div>
      </div>
      <p className="text-xs text-white/50 mt-4 leading-relaxed">
        Show this screen at reception or the check-in kiosk. The code rotates every 30 seconds — expired codes won't scan.
      </p>
    </div>
  );
}
