/**
 * Iter 216h173 — ProfileTab extracted from MemberPortal.js for lazy-loading.
 *
 * Owns the personal-details card, drop-in opt-in toggle, AutoPayCard,
 * WalletCard, and referral panel. None of these are needed for the
 * initial Home tab paint, so loading them async on first Profile visit
 * is a net win.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import {
  API, MEMBER_TOKEN_KEY, Pill, Row, Stat,
} from '../portalShared';

export default function ProfileTab({ member, onSignOut, slug }) {
  const [ref, setRef] = useState(null);
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem(MEMBER_TOKEN_KEY)}` }), []);
  const [dropInOptIn, setDropInOptIn] = useState(!!member.drop_in_optin);
  const [dropInBusy, setDropInBusy] = useState(false);
  useEffect(() => {
    axios.get(`${API}/member/referrals`, { headers }).then((r) => setRef(r.data)).catch(() => {});
  }, [headers]);

  const toggleDropIn = async () => {
    const next = !dropInOptIn;
    setDropInBusy(true);
    setDropInOptIn(next);
    try {
      await axios.post(`${API}/member/dropin-optin`, { opt_in: next }, { headers });
      notify.success(next ? "You'll get drop-in invites" : 'Drop-in invites turned off');
    } catch (e) {
      setDropInOptIn(!next);  // revert
      notify.error('Could not save preference');
    }
    setDropInBusy(false);
  };

  const baseUrl = slug ? `${window.location.origin}/m/${slug}` : `${window.location.origin}/members`;
  const shareUrl = ref ? `${baseUrl}?ref=${ref.code}` : '';
  const copyCode = async () => {
    try { await navigator.clipboard.writeText(ref.code); notify.success('Code copied'); }
    catch { window.prompt('Your referral code:', ref.code); }
  };
  const shareLink = async () => {
    if (navigator.share) {
      try { await navigator.share({ title: 'Join me at the studio', url: shareUrl, text: `Use my code ${ref.code} for £5 off your first class.` }); return; }
      catch { /* fallthrough to copy */ }
    }
    try { await navigator.clipboard.writeText(shareUrl); notify.success('Share link copied'); }
    catch { window.prompt('Share this link:', shareUrl); }
  };

  return (
    <div data-testid="member-profile">
      <h2 className="text-xl font-extrabold tracking-tight mb-4" style={{ letterSpacing: '-0.02em' }}>Profile</h2>
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-5 space-y-3">
        <Row label="Name" value={`${member.first_name} ${member.last_name || ''}`} />
        <Row label="Email" value={member.email} />
        <Row label="Phone" value={member.phone || '—'} />
        <Row label="Status" value={<Pill tone={member.status === 'active' ? 'emerald' : 'amber'}>{member.status}</Pill>} />
        <Row label="Member since" value={member.created_at ? new Date(member.created_at).toLocaleDateString() : '—'} />
      </div>

      <section className="mt-5 rounded-xl border border-white/10 bg-white/[0.03] p-4" data-testid="member-dropin-card">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-extrabold">Drop-in invites</p>
            <p className="text-[11px] text-white/50 dark:text-white/50 mt-1 leading-relaxed">
              Get a heads-up email when a class you'd like opens up at the last minute.
            </p>
          </div>
          <button onClick={toggleDropIn} disabled={dropInBusy}
            className={`relative w-12 h-6 rounded-full transition flex-shrink-0 ${dropInOptIn ? 'bg-emerald-500' : 'bg-white/15 dark:bg-zinc-900'}`}
            data-testid="member-dropin-optin-toggle">
            <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${dropInOptIn ? 'translate-x-6' : 'translate-x-0.5'}`} />
          </button>
        </div>
      </section>
      <AutoPayCard />
      <WalletCard />
      {ref && (
        <section className="mt-6" data-testid="member-referral">
          <div className="rounded-xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.1)] to-transparent p-5">
            <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-[var(--color-brand-cyan)] mb-2">Bring a friend · £5 each</div>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[9px] font-bold uppercase tracking-[0.2em] text-white/50">Your code</div>
                <div className="text-2xl font-extrabold tracking-tight mt-0.5" data-testid="member-referral-code">{ref.code}</div>
              </div>
              <div className="flex gap-2">
                <button onClick={copyCode} className="px-3 py-2 rounded-lg text-[10px] font-extrabold uppercase tracking-wider border border-white/15 text-white/80 hover:bg-white/5" data-testid="member-referral-copy">Copy</button>
                <button onClick={shareLink} className="px-3 py-2 rounded-lg text-[10px] font-extrabold uppercase tracking-wider" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="member-referral-share">Share</button>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 mt-4 pt-4 border-t border-white/10">
              <Stat label="Friends joined" value={ref.stats.friends_joined} />
              <Stat label="Pending"         value={ref.stats.pending} />
              <Stat label="Credit earned"   value={`£${(ref.stats.credit_earned_pence / 100).toFixed(2)}`} />
            </div>
          </div>
          <p className="text-[10px] text-white/40 mt-3 leading-relaxed text-center">Credit lands the moment your friend pays for their first plan.</p>
        </section>
      )}
      <button onClick={onSignOut} className="mt-5 w-full rounded-lg py-3 text-sm font-bold border border-red-500/30 bg-red-500/5 text-red-300 hover:bg-red-500/15" data-testid="member-profile-signout">
        Sign out
      </button>
      <div className="mt-6 text-[10px] text-white/30 text-center tracking-wider uppercase">Pulse Fitness Memberships · Phase 1a</div>
    </div>
  );
}

function WalletCard() {
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem(MEMBER_TOKEN_KEY)}` }), []);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showLedger, setShowLedger] = useState(false);
  const QUICK_AMOUNTS = [2500, 5000, 10000];  // £25 / £50 / £100

  const load = useCallback(async () => {
    try {
      const { data: d } = await axios.get(`${API}/member/wallet`, { headers });
      setData(d);
    } catch { /* non-fatal */ }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get('wallet') === 'topped_up') {
      notify.success('Top-up received — wallet credited');
      setTimeout(load, 1200);
    } else if (qs.get('wallet') === 'cancelled') {
      notify.info('Top-up cancelled');
    }
  }, [load]);

  const topup = async (amountPence) => {
    setBusy(true);
    try {
      const { data: d } = await axios.post(`${API}/member/wallet/topup`, { amount_pence: amountPence }, { headers });
      if (d?.checkout_url) window.location.href = d.checkout_url;
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not start top-up');
    } finally {
      setBusy(false);
    }
  };

  const balance = data?.balance_pence || 0;
  const ledger = data?.ledger || [];

  return (
    <section className="mt-5 rounded-xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.08)] to-transparent p-4" data-testid="member-wallet-card">
      <div className="flex items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-[0.22em] font-extrabold text-[var(--color-brand-cyan)]">Family wallet</div>
          <div className="text-3xl font-black tracking-tight mt-0.5 tabular-nums" data-testid="member-wallet-balance">
            £{(balance / 100).toFixed(2)}
          </div>
          <p className="text-[11px] text-white/50 mt-1 leading-relaxed">
            Pre-paid balance. We deduct from here first on the 1st of each month before charging your card.
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {QUICK_AMOUNTS.map((a) => (
          <button key={a} onClick={() => topup(a)} disabled={busy}
            className="rounded-lg px-3 py-2 text-[11px] font-extrabold uppercase tracking-wider border border-white/15 hover:bg-white/5"
            data-testid={`member-wallet-topup-${a}`}>
            + £{a / 100}
          </button>
        ))}
        <button onClick={() => setShowLedger((v) => !v)}
          className="ml-auto text-[10px] font-bold uppercase tracking-wider text-white/60 hover:text-white"
          data-testid="member-wallet-toggle-ledger">
          {showLedger ? 'Hide history' : 'View history'}
        </button>
      </div>
      {showLedger && (
        <div className="mt-3 pt-3 border-t border-white/10" data-testid="member-wallet-ledger">
          {ledger.length === 0 ? (
            <p className="text-[11px] text-white/40 italic">No wallet activity yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {ledger.map((e) => (
                <li key={e.id} className="flex items-center justify-between text-[11px] py-0.5">
                  <span className="text-white/70">
                    <span className="font-bold uppercase tracking-wider text-[10px] text-white/50 mr-2">{e.kind}</span>
                    {e.note || '—'}
                  </span>
                  <span className={`tabular-nums font-bold ${e.amount_pence >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                    {e.amount_pence >= 0 ? '+' : ''}£{(e.amount_pence / 100).toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function AutoPayCard() {
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem(MEMBER_TOKEN_KEY)}` }), []);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/member/billing/auto-pay`, { headers });
      setStatus(data);
    } catch { /* non-fatal */ }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get('autopay') === 'saved') {
      notify.success('Card saved — Auto-Bill is now active');
      setTimeout(load, 800);
    } else if (qs.get('autopay') === 'cancelled') {
      notify.info('Card save cancelled');
    }
  }, [load]);

  const startSetup = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/member/billing/auto-pay/setup`, {}, { headers });
      if (data?.checkout_url) window.location.href = data.checkout_url;
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not start Auto-Bill setup');
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/member/billing/auto-pay/disable`, {}, { headers });
      notify.success('Auto-Bill turned off');
      await load();
    } catch {
      notify.error('Could not disable Auto-Bill');
    } finally {
      setBusy(false);
    }
  };

  const enabled = !!status?.enabled;

  return (
    <section className="mt-5 rounded-xl border border-white/10 bg-white/[0.03] p-4" data-testid="member-autopay-card">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-extrabold flex items-center gap-2">
            Family Auto-Bill
            {enabled && (
              <span className="text-[9px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300"
                data-testid="member-autopay-badge">Active</span>
            )}
          </p>
          <p className="text-[11px] text-white/50 mt-1 leading-relaxed">
            {enabled
              ? `We'll quietly charge ${status?.card_brand ? status.card_brand.toUpperCase() : 'your card'}${status?.card_last4 ? ` •••• ${status.card_last4}` : ''} on the 1st of each month for last month's classes. Never log in to pay again.`
              : 'Save a card once — we charge it on the 1st of each month for last month\'s invoice. One less login for busy parents.'}
          </p>
        </div>
        {enabled ? (
          <button onClick={disable} disabled={busy}
            className="shrink-0 rounded-lg px-3 py-2 text-[10px] font-extrabold uppercase tracking-wider border border-red-500/30 text-red-300 hover:bg-red-500/10"
            data-testid="member-autopay-disable">
            {busy ? '…' : 'Turn off'}
          </button>
        ) : (
          <button onClick={startSetup} disabled={busy}
            className="shrink-0 rounded-lg px-3 py-2 text-[11px] font-extrabold uppercase tracking-wider"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="member-autopay-enable">
            {busy ? 'Loading…' : 'Set up →'}
          </button>
        )}
      </div>
    </section>
  );
}
