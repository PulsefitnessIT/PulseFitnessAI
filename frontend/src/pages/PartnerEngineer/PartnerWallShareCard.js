/**
 * PartnerWallShareCard — Iter 220z.
 *
 * Lives on the Partner Engineer dashboard for approved engineers.
 * Surfaces the engineer's public Wall of Reviews URL with:
 *
 *   • Live URL pill (clickable, opens in a new tab)
 *   • Copy-to-clipboard button
 *   • QR code (downloadable as PNG, perfect for printed business cards
 *     and physical supplier-card flyers)
 *   • One-tap LinkedIn share (intent URL — pre-fills the headline
 *     "37 ★ reviews on GymAxis — averaging 4.8/5. Book me here:")
 *   • Average + review-count badge
 *
 * Goal: turn the wall into a viral acquisition channel for the
 * Partner Engineer Network — every engineer share is a free lead in.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import QRCode from 'qrcode';
import {
  Share2, Copy, Check, ExternalLink, Linkedin, Download, Star, QrCode,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL;

export default function PartnerWallShareCard() {
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);
  const [qrUrl, setQrUrl] = useState(null);
  const [showQr, setShowQr] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/api/partners/me/public-wall`, {
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
        });
        if (!cancelled) setData(r.data);
      } catch (_e) { /* silent — non-approved partners */ }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!data?.public_url || !showQr) return;
    QRCode.toDataURL(data.public_url, {
      width: 320, margin: 2,
      color: { dark: '#0F172A', light: '#FFFFFF' },
    }).then(setQrUrl).catch(() => setQrUrl(null));
  }, [data?.public_url, showQr]);

  if (!data?.public_url) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data.public_url);
      setCopied(true);
      notify.success('Wall URL copied');
      setTimeout(() => setCopied(false), 2500);
    } catch (_e) {
      notify.error('Could not copy — long-press to select instead');
    }
  };

  const downloadQr = () => {
    if (!qrUrl) return;
    const a = document.createElement('a');
    a.href = qrUrl;
    a.download = `gymaxis-wall-${data.public_slug}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const linkedInUrl = (() => {
    const params = new URLSearchParams({
      url: data.public_url,
      summary: data.share_text || '',
    });
    return `https://www.linkedin.com/sharing/share-offsite/?${params.toString()}`;
  })();

  const { summary } = data;
  const hasStats = summary && summary.count > 0;

  return (
    <div
      className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-gradient-to-br from-blue-50/60 via-white to-purple-50/40 dark:from-zinc-900 dark:via-zinc-900 dark:to-zinc-900 overflow-hidden"
      data-testid="partner-wall-share-card"
    >
      <div className="px-5 py-4 flex items-center gap-3 border-b border-zinc-100 dark:border-zinc-800">
        <span className="w-9 h-9 rounded-xl bg-blue-600 text-white flex items-center justify-center">
          <Share2 size={16} />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-zinc-900 dark:text-zinc-50">
            Share your wall
          </p>
          <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
            Put this link on your email signature, business card, or LinkedIn —
            every visit is a free lead.
          </p>
        </div>
        {hasStats ? (
          <div
            className="shrink-0 text-right hidden sm:block"
            data-testid="partner-wall-share-stats"
          >
            <p className="text-lg font-extrabold text-zinc-900 dark:text-zinc-50 tabular-nums">
              {summary.average.toFixed(1)}
            </p>
            <p className="text-[10px] text-zinc-500 inline-flex items-center gap-1">
              <Star size={10} className="text-amber-500 fill-amber-500" />
              {summary.count} {summary.count === 1 ? 'review' : 'reviews'}
            </p>
          </div>
        ) : null}
      </div>

      <div className="p-5 space-y-3">
        {/* URL row with copy button */}
        <div className="flex items-center gap-2 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 px-3 py-2.5">
          <a
            href={data.public_url}
            target="_blank"
            rel="noreferrer noopener"
            className="flex-1 truncate text-sm text-blue-700 dark:text-blue-300 hover:underline font-medium"
            data-testid="partner-wall-share-url"
          >
            {data.public_url.replace(/^https?:\/\//, '')}
          </a>
          <button
            type="button"
            onClick={copy}
            className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-bold bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 hover:opacity-90 transition-opacity"
            data-testid="partner-wall-share-copy-btn"
            aria-label="Copy wall URL"
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>

        {/* Action row */}
        <div className="flex flex-wrap items-center gap-2">
          <a
            href={data.public_url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 text-zinc-800 dark:text-zinc-100 hover:border-blue-400 transition-colors"
            data-testid="partner-wall-share-open-btn"
          >
            <ExternalLink size={12} /> Open my wall
          </a>
          <a
            href={linkedInUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold text-white bg-[#0a66c2] hover:bg-[#004182] transition-colors"
            data-testid="partner-wall-share-linkedin-btn"
          >
            <Linkedin size={12} /> Share on LinkedIn
          </a>
          <button
            type="button"
            onClick={() => setShowQr((v) => !v)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 text-zinc-800 dark:text-zinc-100 hover:border-blue-400 transition-colors"
            data-testid="partner-wall-share-qr-toggle"
          >
            <QrCode size={12} /> {showQr ? 'Hide QR' : 'Show QR'}
          </button>
        </div>

        {/* QR drawer */}
        {showQr ? (
          <div
            className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 p-4 flex items-center gap-4"
            data-testid="partner-wall-share-qr-panel"
          >
            <div className="shrink-0 rounded-lg overflow-hidden border border-zinc-100">
              {qrUrl ? (
                /* eslint-disable-next-line jsx-a11y/img-redundant-alt */
                <img
                  src={qrUrl}
                  alt="QR code for your reviews wall"
                  width={120}
                  height={120}
                  data-testid="partner-wall-share-qr-img"
                />
              ) : (
                <div className="w-[120px] h-[120px] flex items-center justify-center text-xs text-zinc-400">
                  Generating…
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-zinc-900 dark:text-zinc-50 mb-1">
                Print-ready QR
              </p>
              <p className="text-[12px] text-zinc-500 dark:text-zinc-400 mb-3">
                Add this to flyers and physical supplier cards — customers
                scan to see your full review history.
              </p>
              <button
                type="button"
                onClick={downloadQr}
                disabled={!qrUrl}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-40 transition-colors"
                data-testid="partner-wall-share-qr-download-btn"
              >
                <Download size={12} /> Download PNG
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
