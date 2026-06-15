/** Org Chart — publish & share a read-only public link. */
import { useState } from 'react';
import { createPortal } from 'react-dom';
import { toast } from 'sonner';
import {
  X, Share2, Link2, Copy, Check, RefreshCw, Globe, Lock, Loader2, ExternalLink,
} from 'lucide-react';
import { ocApi } from './api';

const center = {
  position: 'fixed', inset: 0, zIndex: 1100, background: 'rgba(2,12,40,0.45)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};
const box = {
  width: 'min(460px, 92vw)', borderRadius: 18, padding: 22,
  background: 'var(--theme-surface, #fff)', boxShadow: '0 20px 60px rgba(2,12,40,0.3)',
};

export default function ShareModal({ chart, onClose, onChanged }) {
  const published = !!chart?.is_public;
  const [token, setToken] = useState(chart?.public_token || null);
  const [showContact, setShowContact] = useState(!!chart?.public_show_contact);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const url = token ? ocApi.publicUrl(token) : '';

  const publish = async () => {
    setBusy(true);
    try { const r = await ocApi.publish(chart.id, showContact); setToken(r.public_token); toast.success('Public link ready'); onChanged?.(); }
    catch { toast.error('Could not publish'); } finally { setBusy(false); }
  };
  const unpublish = async () => {
    setBusy(true);
    try { await ocApi.unpublish(chart.id); setToken(null); toast.success('Public link disabled'); onChanged?.(); }
    catch { toast.error('Could not unpublish'); } finally { setBusy(false); }
  };
  const rotate = async () => {
    setBusy(true);
    try { const r = await ocApi.rotateLink(chart.id); setToken(r.public_token); toast.success('New link generated — the old one no longer works'); onChanged?.(); }
    catch { toast.error('Could not rotate'); } finally { setBusy(false); }
  };
  const toggleContact = async (next) => {
    setShowContact(next);
    if (token) { try { await ocApi.publish(chart.id, next); onChanged?.(); } catch { /* ignore */ } }
  };
  const copy = () => { navigator.clipboard.writeText(url); setCopied(true); toast.success('Link copied'); setTimeout(() => setCopied(false), 1500); };

  return createPortal(
    <div style={center} onMouseDown={onClose}>
      <div style={box} onMouseDown={(e) => e.stopPropagation()} data-testid="orgchart-share-modal">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold pulse-font-heading inline-flex items-center gap-2" style={{ color: 'var(--theme-text)' }}><Share2 size={16} /> Share org chart</h3>
          <button onClick={onClose} data-testid="orgchart-share-close"><X size={18} style={{ color: 'var(--theme-text-muted)' }} /></button>
        </div>

        {!token ? (
          <div className="text-center py-2">
            <Globe size={26} className="mx-auto mb-2" style={{ color: 'var(--color-brand-cyan)' }} />
            <p className="text-sm font-semibold mb-1" style={{ color: 'var(--theme-text)' }}>Publish a read-only link</p>
            <p className="text-xs mb-4" style={{ color: 'var(--theme-text-muted)' }}>Anyone with the link can view the structure — no login needed. Emails, phones, notes and salary bands are never shared unless you opt in.</p>
            <label className="flex items-center justify-center gap-2 text-xs mb-4" style={{ color: 'var(--theme-text)' }}>
              <input type="checkbox" checked={showContact} onChange={(e) => setShowContact(e.target.checked)} data-testid="orgchart-share-contact" /> Also show email &amp; phone on cards
            </label>
            <button onClick={publish} disabled={busy} className="w-full py-2.5 rounded-lg text-sm font-bold inline-flex items-center justify-center gap-2 disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-share-publish">
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Globe size={15} />} Publish link
            </button>
          </div>
        ) : (
          <div>
            <div className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full mb-3" style={{ background: 'rgba(22,163,74,0.12)', color: '#16a34a' }}>
              <Globe size={12} /> Live — anyone with the link can view
            </div>
            <div className="flex items-center gap-2 rounded-lg border p-2 mb-3" style={{ borderColor: 'var(--theme-border)' }}>
              <Link2 size={14} style={{ color: 'var(--theme-text-muted)', flexShrink: 0 }} />
              <input readOnly value={url} className="flex-1 text-xs bg-transparent outline-none" style={{ color: 'var(--theme-text)' }} data-testid="orgchart-share-url" />
              <button onClick={copy} className="flex-shrink-0" data-testid="orgchart-share-copy">{copied ? <Check size={14} style={{ color: '#16a34a' }} /> : <Copy size={14} style={{ color: 'var(--color-brand-cyan)' }} />}</button>
            </div>
            <label className="flex items-center justify-between gap-2 text-xs mb-4 px-1" style={{ color: 'var(--theme-text)' }}>
              <span className="inline-flex items-center gap-1.5"><Lock size={12} style={{ color: 'var(--theme-text-muted)' }} /> Show email &amp; phone on cards</span>
              <input type="checkbox" checked={showContact} onChange={(e) => toggleContact(e.target.checked)} data-testid="orgchart-share-contact-live" />
            </label>
            <div className="flex flex-wrap gap-2">
              <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="orgchart-share-open"><ExternalLink size={13} /> Open</a>
              <button onClick={rotate} disabled={busy} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border disabled:opacity-50" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="orgchart-share-rotate"><RefreshCw size={13} /> New link</button>
              <button onClick={unpublish} disabled={busy} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border disabled:opacity-50 ml-auto" style={{ borderColor: '#fca5a5', color: '#dc2626' }} data-testid="orgchart-share-unpublish"><Lock size={13} /> Stop sharing</button>
            </div>
          </div>
        )}
      </div>
    </div>, document.body,
  );
}
