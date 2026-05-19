/**
 * EngineerInbox — iter 216h144 (Phase 5).
 *
 * Engineer's triage inbox for incoming supplier-card requests.
 * Customer submits via /r/<slug>, lands here as 'pending', engineer
 * accepts (→ creates a case, auto-assigned) or declines.
 *
 *   /svc/engineer/inbox
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft, Inbox as InboxIcon, RefreshCw, Loader2, MapPin, Phone, Mail,
  CheckCircle2, X, QrCode, Share2, Clipboard, ShieldAlert, Download, Printer,
  Mail as MailIcon,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const PRIO = {
  P1: 'bg-red-100 text-red-700',
  P2: 'bg-amber-100 text-amber-700',
  P3: 'bg-blue-100 text-blue-700',
  P4: 'bg-slate-100 text-slate-700',
};

const fmtRelative = (iso) => {
  if (!iso) return '';
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
};

// ── Accept modal ──────────────────────────────────────────────
const AcceptModal = ({ req, onClose, onAccept }) => {
  const [when, setWhen] = useState('');
  const [mins, setMins] = useState(60);
  if (!req) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center sm:justify-center bg-black/50"
      onClick={onClose}
      data-testid="accept-modal"
    >
      <div
        className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-bold text-slate-900 mb-1">Accept request</h3>
        <p className="text-xs text-slate-500 mb-4">
          We'll create a job auto-assigned to you. You can reschedule later.
        </p>
        <div className="space-y-3">
          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 inline-block">
              Schedule for (optional)
            </span>
            <input
              type="datetime-local"
              value={when}
              onChange={(e) => setWhen(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              data-testid="accept-modal-time"
            />
          </label>
          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 inline-block">
              Estimated minutes
            </span>
            <input
              type="number"
              min={15}
              max={600}
              step={15}
              value={mins}
              onChange={(e) => setMins(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              data-testid="accept-modal-minutes"
            />
          </label>
        </div>
        <div className="flex gap-2 mt-4">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 border border-slate-300 rounded-lg py-2 text-sm font-semibold"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() =>
              onAccept({
                scheduled_at: when ? new Date(when).toISOString() : null,
                estimated_minutes: Number(mins) || 60,
              })
            }
            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-2 text-sm font-semibold"
            data-testid="accept-modal-submit"
          >
            Accept & assign to me
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Card share box ─────────────────────────────────────────────
const CardShareBox = () => {
  const [info, setInfo] = useState(null);
  const [qrPreview, setQrPreview] = useState(null);
  const [inbound, setInbound] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/engineer/intake-card`, auth());
      setInfo(r.data);
    } catch {
      /* swallow — endpoint exists but engineer profile may be missing */
    }
    try {
      const r = await axios.get(`${API}/svc/engineer/inbound-address`, auth());
      setInbound(r.data);
    } catch { /* inbound module optional */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  // Fetch the SVG with auth and turn it into a data URL for the <img>.
  useEffect(() => {
    if (!info?.share_url) return;
    let revoked = null;
    (async () => {
      try {
        const tok = localStorage.getItem('token') || '';
        const res = await fetch(`${API}/svc/engineer/intake-card.svg`,
          { headers: { Authorization: `Bearer ${tok}` } });
        if (!res.ok) return;
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setQrPreview(url);
        revoked = url;
      } catch { /* ignore */ }
    })();
    return () => { if (revoked) URL.revokeObjectURL(revoked); };
  }, [info?.share_url]);

  const copy = async () => {
    if (!info?.share_url) return;
    try {
      await navigator.clipboard.writeText(info.share_url);
      notify.success('Link copied');
    } catch {
      notify.error('Clipboard unavailable');
    }
  };

  const share = async () => {
    if (!info?.share_url) return;
    if (navigator.share) {
      try {
        await navigator.share({ title: 'My GymAxis request link', url: info.share_url });
      } catch { /* user dismissed */ }
    } else {
      copy();
    }
  };

  const regenerate = async () => {
    if (!window.confirm('Generate a new link? The old one will stop working.')) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/svc/engineer/intake-card/regenerate`, {}, auth());
      setInfo((s) => ({ ...s, ...r.data }));
      notify.success('New link ready');
    } finally { setBusy(false); }
  };

  if (!info?.share_url) return null;
  const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : '';
  const svgUrl = `${API}/svc/engineer/intake-card.svg`;
  const pdfUrl = `${API}/svc/engineer/intake-card.pdf`;

  const downloadAsset = async (url, filename) => {
    try {
      const res = await fetch(url, { headers: { Authorization: `Bearer ${tok}` } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(objUrl), 1500);
      notify.success(`Downloaded ${filename}`);
    } catch (e) {
      notify.error('Download failed', e?.message || String(e));
    }
  };

  return (
    <div
      className="bg-white border border-slate-200 rounded-2xl p-4"
      data-testid="inbox-share-card"
    >
      <div className="flex items-start gap-3">
        <span className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center flex-shrink-0">
          <QrCode size={18} />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-slate-900">Your supplier card link</p>
          <p className="text-xs text-slate-500 mt-0.5 truncate font-mono" data-testid="inbox-share-url">
            {info.share_url}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[120px_1fr] gap-4 mt-4 items-center">
        {/* Live QR preview */}
        <div className="bg-white border border-slate-200 rounded-xl p-2 flex items-center justify-center">
          {qrPreview ? (
            <img
              src={qrPreview}
              alt="QR code"
              className="w-24 h-24"
              data-testid="inbox-qr-preview"
            />
          ) : (
            <div className="w-24 h-24 flex items-center justify-center text-slate-300">
              <Loader2 size={20} className="animate-spin" />
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={copy}
            className="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-700 flex items-center gap-1.5"
            data-testid="inbox-share-copy"
          >
            <Clipboard size={12} /> Copy link
          </button>
          <button
            type="button"
            onClick={share}
            className="px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold flex items-center gap-1.5"
            data-testid="inbox-share-share"
          >
            <Share2 size={12} /> Share
          </button>
          <button
            type="button"
            onClick={() => downloadAsset(svgUrl, `gymaxis-qr-${info.slug}.svg`)}
            className="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-700 flex items-center gap-1.5"
            data-testid="inbox-download-svg"
          >
            <Download size={12} /> QR (SVG)
          </button>
          <button
            type="button"
            onClick={() => downloadAsset(pdfUrl, `gymaxis-card-${info.slug}.pdf`)}
            className="px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold flex items-center gap-1.5"
            data-testid="inbox-download-pdf"
          >
            <Printer size={12} /> Printable card
          </button>
          <button
            type="button"
            onClick={regenerate}
            disabled={busy}
            className="px-3 py-2 rounded-lg border border-slate-300 text-xs font-semibold text-slate-600 hover:bg-slate-50"
            data-testid="inbox-share-regenerate"
          >
            {busy ? <Loader2 size={12} className="animate-spin" /> : 'Regen link'}
          </button>
        </div>
      </div>

      {/* Inbound email address — iter 216h146 */}
      {inbound?.email ? (
        <div
          className="mt-4 border-t border-slate-100 pt-4 flex items-start gap-3"
          data-testid="inbox-inbound-email"
        >
          <span className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
            inbound.enabled ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-500'
          }`}>
            <MailIcon size={18} />
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-slate-900">
              Your inbound email
              {!inbound.enabled ? (
                <span className="ml-2 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
                  pending DNS
                </span>
              ) : null}
            </p>
            <p className="text-xs text-slate-500 mt-0.5 truncate font-mono" data-testid="inbox-inbound-email-address">
              {inbound.email}
            </p>
            <p className="text-[11px] text-slate-500 mt-1">
              Forward customer emails here and we'll auto-create a request in your inbox (AI pre-fills title and priority).
            </p>
          </div>
          <button
            type="button"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(inbound.email);
                notify.success('Email copied');
              } catch { notify.error('Clipboard unavailable'); }
            }}
            className="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-700 flex items-center gap-1.5 flex-shrink-0"
            data-testid="inbox-inbound-copy"
          >
            <Clipboard size={12} /> Copy
          </button>
        </div>
      ) : null}
    </div>
  );
};

// ── Row ───────────────────────────────────────────────────────
const Row = ({ r, onAccept, onDecline }) => {
  const cls = PRIO[r.priority] || PRIO.P3;
  return (
    <li
      className="p-4 flex items-start gap-3 bg-white hover:bg-slate-50 transition-all"
      data-testid={`inbox-row-${r.id}`}
    >
      <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold ${cls} flex-shrink-0`}>
        {r.priority}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-bold text-slate-900 truncate">{r.title}</p>
          <span className="text-[10px] text-slate-400 tabular-nums">{fmtRelative(r.created_at)}</span>
        </div>
        <p className="text-xs text-slate-600 mt-0.5 truncate">
          {r.customer_name} {r.site_name ? `· ${r.site_name}` : ''}
        </p>
        {r.description ? (
          <p className="text-xs text-slate-500 mt-1 line-clamp-2 leading-snug">{r.description}</p>
        ) : null}
        <div className="flex items-center gap-3 mt-2 text-[11px] text-slate-500 flex-wrap">
          {r.customer_email ? <span className="inline-flex items-center gap-1"><Mail size={10} />{r.customer_email}</span> : null}
          {r.customer_phone ? <span className="inline-flex items-center gap-1"><Phone size={10} />{r.customer_phone}</span> : null}
          {r.site_postcode  ? <span className="inline-flex items-center gap-1"><MapPin size={10} />{r.site_postcode}</span> : null}
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          type="button"
          onClick={() => onAccept(r)}
          className="bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg flex items-center gap-1"
          data-testid={`inbox-accept-${r.id}`}
        >
          <CheckCircle2 size={12} /> Accept
        </button>
        <button
          type="button"
          onClick={() => onDecline(r)}
          className="text-slate-400 hover:text-red-600 px-2 py-1.5"
          data-testid={`inbox-decline-${r.id}`}
          title="Decline"
        >
          <X size={14} />
        </button>
      </div>
    </li>
  );
};

// ── Main page ──────────────────────────────────────────────────
export default function EngineerInbox() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('pending'); // pending | accepted | declined | all
  const [acceptFor, setAcceptFor] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/svc/engineer/job-requests?status=${status}`,
        auth(),
      );
      setItems(r.data?.requests || []);
    } catch (e) {
      notify.error('Failed to load inbox', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const pendingCount = useMemo(
    () => items.filter((x) => x.status === 'pending').length, [items],
  );

  const onAccept = async (payload) => {
    if (!acceptFor) return;
    try {
      const r = await axios.post(
        `${API}/svc/engineer/job-requests/${acceptFor.id}/accept`,
        payload,
        auth(),
      );
      notify.success(`Created ${r.data.reference}`);
      setAcceptFor(null);
      navigate(`/svc/engineer/jobs/${r.data.case_id}`);
    } catch (e) {
      notify.error('Accept failed', e?.response?.data?.detail || e.message);
    }
  };

  const onDecline = async (r) => {
    const reason = window.prompt('Reason (optional)?') || '';
    try {
      await axios.post(
        `${API}/svc/engineer/job-requests/${r.id}/decline`,
        { reason },
        auth(),
      );
      notify.success('Declined');
      load();
    } catch (e) {
      notify.error('Decline failed', e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-inbox">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => navigate('/svc/engineer')}
              className="text-slate-500 hover:text-slate-900"
              data-testid="inbox-back"
              aria-label="Back"
            >
              <ChevronLeft size={22} />
            </button>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">
                GymAxis · Engineer
              </p>
              <h1 className="text-xl font-extrabold text-slate-900 flex items-center gap-2">
                <InboxIcon size={20} /> Incoming requests
                {pendingCount > 0 ? (
                  <span className="bg-red-500 text-white text-[10px] font-bold rounded-full px-1.5 min-w-[20px] text-center">
                    {pendingCount}
                  </span>
                ) : null}
              </h1>
            </div>
          </div>
          <button
            type="button"
            onClick={load}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
            data-testid="inbox-refresh"
            aria-label="Refresh"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-4 space-y-3">
        <CardShareBox />

        <div className="bg-white border border-slate-200 rounded-2xl px-3 py-2 flex items-center gap-1">
          {['pending', 'accepted', 'declined', 'all'].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatus(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize ${
                status === s ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-100'
              }`}
              data-testid={`inbox-filter-${s}`}
            >
              {s}
            </button>
          ))}
        </div>

        {!loading && items.length === 0 ? (
          <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-10 text-center" data-testid="inbox-empty">
            <ShieldAlert size={28} className="mx-auto text-slate-300 mb-2" />
            <p className="text-sm font-semibold text-slate-700">No {status === 'all' ? 'requests' : status + ' requests'} yet</p>
            <p className="text-xs text-slate-500 mt-1">
              Share your supplier-card link above — when a customer fills it, you'll see the request here.
            </p>
          </div>
        ) : (
          <ul className="bg-white border border-slate-200 rounded-2xl divide-y divide-slate-100 overflow-hidden">
            {items.map((r) => (
              <Row
                key={r.id}
                r={r}
                onAccept={r.status === 'pending' ? (rr) => setAcceptFor(rr) : () => {}}
                onDecline={r.status === 'pending' ? onDecline : () => {}}
              />
            ))}
          </ul>
        )}
      </main>

      <AcceptModal
        req={acceptFor}
        onClose={() => setAcceptFor(null)}
        onAccept={onAccept}
      />
    </div>
  );
}
