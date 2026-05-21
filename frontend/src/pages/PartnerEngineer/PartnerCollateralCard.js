/**
 * PartnerCollateralCard.js (iter 216h285)
 *
 * Download buttons for the three pieces of partner referral
 * collateral: A4 QR poster (PNG), social-share card (PNG), one-page
 * pitch deck (PDF). Each download streams from
 * GET /api/partners/me/collateral/{kind}.
 *
 * Hides itself silently for non-approved partners (the backend
 * returns 403 in that case).
 */
import { useState } from 'react';
import axios from 'axios';
import { Image as ImageIcon, FileText, Printer, Download, Loader2 } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL;

const KINDS = [
  {
    key: 'qr-poster',
    label: 'QR poster',
    hint: 'A4 PNG. Print and stick on a gym wall, in your van, or workshop.',
    Icon: Printer,
  },
  {
    key: 'social-card',
    label: 'Social share card',
    hint: '1200×630 PNG sized for Instagram, LinkedIn and link previews.',
    Icon: ImageIcon,
  },
  {
    key: 'pdf-pitch',
    label: 'PDF pitch deck',
    hint: 'One-page A4 PDF you can email straight to a gym owner.',
    Icon: FileText,
  },
];

export default function PartnerCollateralCard() {
  const [busy, setBusy] = useState(null);
  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

  const download = async (kind) => {
    setBusy(kind);
    try {
      const r = await axios.get(`${API}/api/partners/me/collateral/${kind}`, {
        headers, responseType: 'blob',
      });
      // Pull the filename out of the Content-Disposition header so the
      // browser-saved file matches what the backend produced.
      const disp = r.headers['content-disposition'] || '';
      const match = /filename="([^"]+)"/.exec(disp);
      const filename = match ? match[1] : `gymaxis-${kind}`;
      const blob = new Blob([r.data], { type: r.headers['content-type'] });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      notify.success(`${KINDS.find((k) => k.key === kind).label} downloaded`);
    } catch (e) {
      notify.error(e?.response?.data?.detail || `Could not generate ${kind}`);
    } finally { setBusy(null); }
  };

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 space-y-3" data-testid="partner-collateral-card">
      <div className="flex items-center gap-2">
        <Download size={16} className="text-zinc-500" />
        <h3 className="text-sm font-bold text-zinc-900">Share kit</h3>
      </div>
      <p className="text-[11px] text-zinc-500 leading-relaxed">
        Branded, ready-to-share collateral. Each file embeds your referral code and QR — every signup with these counts towards your tier drop.
      </p>
      <div className="grid sm:grid-cols-3 gap-2">
        {KINDS.map((k) => {
          const Icon = k.Icon;
          const isBusy = busy === k.key;
          return (
            <button
              key={k.key}
              type="button"
              onClick={() => download(k.key)}
              disabled={isBusy}
              className="text-left p-3 border border-zinc-200 rounded-lg hover:bg-zinc-50 disabled:opacity-60 transition-colors"
              data-testid={`partner-collateral-${k.key}`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Icon size={14} className="text-blue-600" />
                <p className="text-[13px] font-bold text-zinc-900">{k.label}</p>
                {isBusy && <Loader2 size={11} className="animate-spin text-zinc-400 ml-auto" />}
              </div>
              <p className="text-[10px] text-zinc-500 leading-snug">{k.hint}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
