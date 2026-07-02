/**
 * PartnerEngineerReferralCard.js (iter 216h287 — Gap 9)
 *
 * Engineer-side dashboard card to recruit fellow engineers. Surfaces:
 *   • The personal share link (`/engineer/r/{code}`)
 *   • One-click copy + share-by-email helpers
 *   • Live pipeline list (masked emails — privacy-first)
 *   • Counter "X / 10 to free plan" tying back to the tier ladder
 *
 * Pulls from GET /partners/me/engineer-referrals. Renders nothing
 * while loading or for non-partners.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Copy, Mail, UserPlus, Users, ArrowUpRight, CheckCircle2, Clock, XCircle } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_META = {
  approved: { Icon: CheckCircle2, tone: 'text-emerald-700 bg-emerald-100', label: 'Approved' },
  pending:  { Icon: Clock,        tone: 'text-amber-700 bg-amber-100',     label: 'Awaiting review' },
  rejected: { Icon: XCircle,      tone: 'text-zinc-600 bg-zinc-200',       label: 'Not approved' },
};

export default function PartnerEngineerReferralCard() {
  const [data, setData] = useState(null);
  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/api/partners/me/engineer-referrals`, { headers });
        setData(r.data);
      } catch { /* silent — non-partners */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!data) return null;

  const { share_link, referrals, summary, referral_code } = data;
  const remaining = Math.max(0, 10 - summary.approved);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(share_link);
      notify.success('Recruit link copied');
    } catch {
      notify.error('Copy failed — copy manually');
    }
  };

  const emailShare = () => {
    const subject = encodeURIComponent('Join me on the Pulse Fitness Partner Engineer network');
    const body = encodeURIComponent(
      `Hey,\n\nIf you do any gym maintenance work, the Pulse Fitness Partner Engineer network is worth a look. ` +
      `They route inbound jobs to local engineers and the platform fee drops fast — I'd genuinely recommend it.\n\n` +
      `My recommendation link (it auto-attributes me as your sponsor): ${share_link}\n\nCheers`,
    );
    window.location.href = `mailto:?subject=${subject}&body=${body}`;
  };

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden"
         data-testid="partner-engineer-referral-card">
      <div className="px-4 py-3 flex items-center gap-3 border-b border-zinc-100 dark:border-zinc-800 bg-gradient-to-r from-blue-50/40 to-white dark:from-zinc-900 dark:to-zinc-900">
        <UserPlus size={16} className="text-zinc-500" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">Recruit a fellow engineer</p>
          <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
            {summary.approved} approved
            {summary.pending > 0 && <> · {summary.pending} pending</>}
            {' '}· each one counts toward your free-plan ladder
          </p>
        </div>
        {remaining > 0 ? (
          <span className="text-[11px] font-bold text-zinc-700 dark:text-zinc-300 bg-zinc-100 dark:bg-zinc-800 px-2 py-1 rounded"
                data-testid="eref-remaining-pill">
            {remaining} to free
          </span>
        ) : (
          <span className="text-[11px] font-bold text-emerald-700 bg-emerald-100 px-2 py-1 rounded"
                data-testid="eref-remaining-pill">
            Free plan unlocked
          </span>
        )}
      </div>

      <div className="px-4 py-3 space-y-3">
        <div className="flex items-center gap-2 bg-zinc-50 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-md px-3 py-2"
             data-testid="eref-share-link-row">
          <span className="text-[12px] text-zinc-500 shrink-0 hidden sm:inline">Your link</span>
          <span className="text-[12px] text-zinc-900 dark:text-zinc-100 font-mono truncate flex-1"
                data-testid="eref-share-link">{share_link}</span>
          <button type="button" onClick={copy}
                  className="px-2 py-1 text-[11px] font-bold text-white rounded inline-flex items-center gap-1"
                  style={{ background: '#0891b2' }}
                  data-testid="eref-copy-btn">
            <Copy size={11} /> Copy
          </button>
          <button type="button" onClick={emailShare}
                  className="px-2 py-1 text-[11px] font-bold text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded inline-flex items-center gap-1"
                  data-testid="eref-email-btn">
            <Mail size={11} /> Email
          </button>
        </div>
        <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
          Attribution code <span className="font-mono">{referral_code}</span> — anyone who applies through
          your link gets you the credit when they&apos;re approved.
        </p>
      </div>

      {referrals.length > 0 && (
        <div className="border-t border-zinc-100 dark:border-zinc-800" data-testid="eref-list">
          {referrals.slice(0, 8).map((r) => {
            const meta = STATUS_META[r.status] || STATUS_META.pending;
            const Icon = meta.Icon;
            return (
              <div key={r.id} className="px-4 py-2.5 flex items-center gap-3 border-b border-zinc-100 dark:border-zinc-800 last:border-b-0"
                   data-testid={`eref-row-${r.id}`}>
                <Users size={14} className="text-zinc-400 shrink-0" />
                <span className="text-[12px] text-zinc-700 dark:text-zinc-300 font-mono flex-1 truncate">{r.referred_email_masked}</span>
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded inline-flex items-center gap-1 ${meta.tone}`}>
                  <Icon size={10} /> {meta.label}
                </span>
              </div>
            );
          })}
          {referrals.length > 8 && (
            <div className="px-4 py-2 text-[11px] text-zinc-500 inline-flex items-center gap-1">
              <ArrowUpRight size={11} /> +{referrals.length - 8} more
            </div>
          )}
        </div>
      )}
    </div>
  );
}
