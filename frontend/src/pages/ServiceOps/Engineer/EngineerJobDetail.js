/**
 * EngineerJobDetail — iter 215dp (Phase 2).
 *
 * Mobile-first job detail with three primary actions an engineer needs
 * on site: start/stop a timer, capture photos, and complete with a
 * customer signature.
 *
 * Designed for offline-first use: every mutation routes through
 * `queuedMutation` so writes survive lift / basement signal loss and
 * replay automatically when the device comes back online.
 *
 * Backed by:
 *   GET  /api/svc/engineer/jobs/{id}
 *   POST /api/svc/engineer/time/start | /time/stop
 *   POST /api/svc/engineer/photos
 *   POST /api/svc/engineer/signature
 *   POST /api/svc/engineer/jobs/{id}/complete
 *   POST /api/files/upload     (multipart, photos)
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Phone, MapPin, Wrench, Loader2, Play, Square, Camera, PenLine,
  CheckCircle, Image as ImageIcon, ChevronRight, Clock, AlertTriangle, WifiOff,
  Sparkles, Mic, MicOff, Navigation, Plus, FileText, Send, Package, Trash2, Search,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { queuedMutation } from '@/utils/queuedMutation';
import SignatureCanvas from './SignatureCanvas';
import useVoiceDictation from '@/hooks/useVoiceDictation';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const PRIORITY_COLOUR = { p1: '#ef4444', p2: '#f59e0b', p3: '#1d4ed8', p4: '#6b7280' };
const STATUS_LABEL = {
  new: 'New', triaged: 'Triaged', assigned: 'Assigned', en_route: 'En route',
  on_site: 'On site', paused_parts: 'Waiting parts', paused_customer: 'Waiting customer',
  repaired: 'Repaired', awaiting_sign_off: 'Awaiting sign-off', closed: 'Closed', invoiced: 'Invoiced',
};

function newIdemKey() {
  return (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID()
    : `idem-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function fmtRelative(iso) {
  if (!iso) return '—';
  const ms = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(ms);
  const m = Math.floor(abs / 60000), h = Math.floor(m / 60), d = Math.floor(h / 24);
  const sign = ms < 0 ? '-' : '';
  if (d >= 1) return `${sign}${d}d ${h % 24}h`;
  if (h >= 1) return `${sign}${h}h ${m % 60}m`;
  return `${sign}${m}m`;
}

function ActiveTimer({ entry }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  if (!entry) return null;
  const elapsed = Math.max(0, Math.floor((now - new Date(entry.start_at).getTime()) / 1000));
  const m = Math.floor(elapsed / 60), s = String(elapsed % 60).padStart(2, '0');
  return (
    <p className="text-sm font-extrabold tabular-nums" data-testid="job-active-timer">
      {m}m {s}s · {entry.category}
    </p>
  );
}

export default function EngineerJobDetail() {
  const navigate = useNavigate();
  const { caseId } = useParams();
  const fileInputRef = useRef(null);

  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [showSig, setShowSig] = useState(false);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [completeSummary, setCompleteSummary] = useState('');
  const [completeChargeable, setCompleteChargeable] = useState(false);
  const [online, setOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true);
  const [signatureName, setSignatureName] = useState('');
  const [noteDraft, setNoteDraft] = useState('');

  // Voice dictation — appends to whichever field the engineer is filling.
  const wrapVoice = useVoiceDictation({
    onResult: (text) => setCompleteSummary((s) => `${s} ${text}`.trim()),
    onError: () => notify.error('Voice input unavailable', 'Falling back to keyboard.'),
  });
  const noteVoice = useVoiceDictation({
    onResult: (text) => setNoteDraft((s) => `${s} ${text}`.trim()),
    onError: () => notify.error('Voice input unavailable', 'Falling back to keyboard.'),
  });

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/jobs/${caseId}`, auth());
      setJob(r.data);
    } catch (e) {
      if (online) notify.error('Failed to load job', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [caseId, online]);

  useEffect(() => { load(); }, [load]);

  const activeTimer = useMemo(
    () => (job?.time_entries || []).find((t) => !t.end_at),
    [job],
  );

  const colour = PRIORITY_COLOUR[job?.priority] || '#6b7280';

  // ── Time tracking ────────────────────────────────────────────
  const startTimer = async (category) => {
    if (busy || !job) return;
    setBusy(`start-${category}`);
    const idem = newIdemKey();
    const headers = { 'Content-Type': 'application/json', 'Idempotency-Key': idem, ...auth().headers };
    const result = await queuedMutation({
      method: 'POST',
      url: `${API}/svc/engineer/time/start`,
      body: { case_id: job.id, category },
      headers,
      label: `Start ${category} timer · ${job.reference}`,
      kind: 'svc-time-start',
    });
    if (result?.queued) {
      notify.info('Saved offline', 'Will sync when you reconnect.');
    } else {
      notify.success('Timer started');
    }
    await load();
    setBusy('');
  };

  const stopTimer = async () => {
    if (busy || !activeTimer) return;
    setBusy('stop');
    const idem = newIdemKey();
    const headers = { 'Content-Type': 'application/json', 'Idempotency-Key': idem, ...auth().headers };
    const result = await queuedMutation({
      method: 'POST',
      url: `${API}/svc/engineer/time/stop`,
      body: { entry_id: activeTimer.id },
      headers,
      label: `Stop timer · ${job.reference}`,
      kind: 'svc-time-stop',
    });
    if (result?.queued) {
      notify.info('Saved offline');
    } else {
      notify.success('Timer stopped');
    }
    await load();
    setBusy('');
  };

  // ── Free-text note (offline-safe via queuedMutation) ─────────
  const submitNote = async () => {
    const body = (noteDraft || '').trim();
    if (!body || !job) return;
    if (noteVoice.listening) noteVoice.stop();
    setBusy('note');
    const idem = newIdemKey();
    const result = await queuedMutation({
      method: 'POST',
      url: `${API}/svc/cases/${job.id}/notes`,
      body: { body, visibility: 'internal' },
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idem, ...auth().headers },
      label: `Note · ${job.reference}`,
      kind: 'svc-note',
    });
    if (result.queued) {
      notify.info('Note queued', 'It will sync once you’re back online.');
    } else {
      notify.success('Note saved');
      await load();
    }
    setNoteDraft('');
    setBusy('');
  };

  // ── Photo capture ────────────────────────────────────────────
  const onPhotoFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !job) return;
    setBusy('photo');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const up = await axios.post(`${API}/files/upload?category=service-photos`, fd, {
        headers: { ...auth().headers },
      });
      const fileUrl = up.data?.url || up.data?.file_url || up.data?.path || `/api/files/${up.data?.id}/view`;
      const idem = newIdemKey();
      await queuedMutation({
        method: 'POST',
        url: `${API}/svc/engineer/photos`,
        body: {
          case_id: job.id,
          file_url: fileUrl,
          mime_type: file.type || 'image/jpeg',
          taken_at: new Date().toISOString(),
        },
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idem, ...auth().headers },
        label: `Photo · ${job.reference}`,
        kind: 'svc-photo',
      });
      notify.success('Photo attached');
      await load();
    } catch (err) {
      notify.error('Photo upload failed', err?.response?.data?.detail || err.message);
    } finally { setBusy(''); }
  };

  // ── Photo classification (AI) ────────────────────────────────
  const classifyPhoto = async (photoId) => {
    if (!photoId || busy) return;
    setBusy(`classify-${photoId}`);
    try {
      const r = await axios.post(`${API}/svc/ai/photo/classify`, { photo_id: photoId }, auth());
      if (r.data?.ok) {
        notify.success(`AI: ${r.data.severity}`, (r.data.tags || []).slice(0, 3).join(' · ') || r.data.summary);
        await load();
      } else {
        notify.error('AI analysis unavailable', r.data?.error || 'Try again');
      }
    } catch (e) {
      notify.error('AI failed', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  };

  // ── Signature ────────────────────────────────────────────────
  const submitSignature = async (dataUrl) => {
    if (!job) return;
    setBusy('signature');
    setShowSig(false);
    const idem = newIdemKey();
    const result = await queuedMutation({
      method: 'POST',
      url: `${API}/svc/engineer/signature`,
      body: {
        case_id: job.id,
        signed_by_name: (signatureName || 'Customer').trim(),
        image_data: dataUrl,
        summary: completeSummary || '',
      },
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idem, ...auth().headers },
      label: `Signature · ${job.reference}`,
      kind: 'svc-signature',
    });
    if (result?.queued) {
      notify.info('Signature queued — will sync online');
    } else {
      notify.success('Signature captured');
    }
    setSignatureName('');
    await load();
    setBusy('');
  };

  // ── Parts allocation (iter 216h84) ───────────────────────────
  const [partsOpen, setPartsOpen] = useState(false);
  const [partSearch, setPartSearch] = useState('');
  const [partResults, setPartResults] = useState([]);
  const [partSearchBusy, setPartSearchBusy] = useState(false);
  const [partQty, setPartQty] = useState(1);
  const [partSource, setPartSource] = useState('van');
  const allocatedParts = useMemo(() => job?.allocated_parts || [], [job]);

  useEffect(() => {
    if (!partsOpen) { setPartResults([]); return; }
    const q = partSearch.trim();
    if (!q) { setPartResults([]); return; }
    const t = setTimeout(async () => {
      setPartSearchBusy(true);
      try {
        const r = await axios.get(
          `${API}/svc/parts?search=${encodeURIComponent(q)}&limit=10`,
          auth(),
        );
        setPartResults(r.data?.parts || []);
      } catch {
        setPartResults([]);
      } finally { setPartSearchBusy(false); }
    }, 250);
    return () => clearTimeout(t);
  }, [partSearch, partsOpen]);

  const allocatePart = async (part) => {
    if (!job || busy) return;
    setBusy(`part-${part.sku}`);
    try {
      await axios.post(
        `${API}/svc/parts/allocate`,
        {
          case_id: job.id,
          part_sku: part.sku,
          qty: Math.max(1, parseInt(partQty, 10) || 1),
          source: partSource,
          engineer_id: job.assigned_engineer_id,
        },
        auth(),
      );
      notify.success('Part allocated', `${partQty} × ${part.sku}`);
      setPartSearch('');
      setPartResults([]);
      await load();
    } catch (e) {
      notify.error('Could not allocate part', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  };

  const deallocatePart = async (allocationId) => {
    if (!allocationId || busy) return;
    if (!window.confirm('Remove this part from the job?')) return;
    setBusy(`unalloc-${allocationId}`);
    try {
      await axios.delete(`${API}/svc/parts/allocate/${allocationId}`, auth());
      notify.success('Part removed');
      await load();
    } catch (e) {
      notify.error('Could not remove', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  };

  // ── Service Report (PDF + email) ─────────────────────────────
  const openServiceReport = () => {
    if (!job) return;
    const url = `${API}/svc/cases/${job.id}/service-report.pdf?token=${encodeURIComponent(localStorage.getItem('token') || '')}`;
    // Some browsers ignore Authorization header on window.open; fallback: fetch + blob.
    fetch(`${API}/svc/cases/${job.id}/service-report.pdf`, auth())
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob(); })
      .then((blob) => {
        const blobUrl = URL.createObjectURL(blob);
        window.open(blobUrl, '_blank', 'noopener');
        setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
      })
      .catch((e) => notify.error('Could not open report', e.message || String(e)));
    void url;
  };

  const emailServiceReport = async () => {
    if (!job || busy) return;
    const defaultTo = job.customer_email || '';
    const to = window.prompt('Send the service report to which email?', defaultTo);
    if (!to) return;
    const note = window.prompt('Add a short note (optional)', '') || '';
    setBusy('email-report');
    try {
      const r = await axios.post(
        `${API}/svc/cases/${job.id}/service-report/email`,
        { to, note },
        auth(),
      );
      notify.success('Report emailed', `Sent to ${r.data?.to || to}`);
      await load();
    } catch (e) {
      notify.error('Could not send report', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  };

  // ── Complete ─────────────────────────────────────────────────
  const submitComplete = async (target) => {
    if (!job) return;
    if (!completeSummary.trim()) {
      notify.error('Please add a fix summary before completing');
      return;
    }
    setBusy(`complete-${target}`);
    try {
      await axios.post(
        `${API}/svc/engineer/jobs/${job.id}/complete`,
        { summary: completeSummary.trim(), chargeable: completeChargeable, target },
        auth(),
      );
      notify.success(`Job marked ${target.replace('_', ' ')}`);
      setCompleteOpen(false);
      setCompleteSummary('');
      setCompleteChargeable(false);
      navigate('/svc/engineer');
    } catch (e) {
      notify.error('Failed to complete job', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" data-testid="job-detail-loading">
        <Loader2 size={20} className="animate-spin opacity-60" />
      </div>
    );
  }
  if (!job) {
    return <div className="min-h-screen p-6 text-center opacity-70" data-testid="job-detail-missing">Job not found.</div>;
  }

  const isClosed = job.status === 'closed' || job.status === 'invoiced';
  const slaMs = job.sla_resolve_at ? new Date(job.sla_resolve_at).getTime() - Date.now() : 0;
  const slaBreached = job.sla_resolve_at && slaMs < 0;
  const slaAtRisk = job.sla_resolve_at && !slaBreached && slaMs < 2 * 3600 * 1000;
  const slaColour = slaBreached ? '#ef4444' : slaAtRisk ? '#f59e0b' : '#10b981';

  return (
    <div className="min-h-screen pb-24" style={{ background: 'var(--theme-bg, #f8fafc)' }} data-testid="job-detail-page">
      <header className="px-4 pt-4 pb-3 sticky top-0 z-10 flex items-center gap-2" style={{ background: 'var(--theme-surface, #fff)', borderBottom: '1px solid var(--theme-border, #e5e7eb)' }}>
        <button type="button" onClick={() => navigate('/svc/engineer')} aria-label="Back" className="p-1.5 rounded-full hover:bg-black/5" data-testid="job-back">
          <ArrowLeft size={18} />
        </button>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold opacity-60 tracking-wider uppercase tabular-nums">{job.reference}</p>
          <h1 className="text-base font-extrabold truncate" data-testid="job-title">{job.title}</h1>
        </div>
        {!online ? <WifiOff size={14} className="opacity-70" data-testid="offline-icon" /> : null}
      </header>

      <main className="px-4 mt-3 space-y-3">
        {/* Meta strip */}
        <section className="rounded-2xl border p-3 space-y-2" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }}>
          <div className="flex items-center justify-between gap-2">
            <span
              className="px-2 py-0.5 rounded text-[10px] font-extrabold tracking-wider"
              style={{ background: `${colour}22`, color: colour }}
              data-testid="job-priority-pill"
            >
              {(job.priority || 'p3').toUpperCase()}
            </span>
            {job.case_type ? (
              <span
                className="px-2 py-0.5 rounded text-[10px] font-extrabold tracking-wider uppercase"
                style={{ background: '#1d4ed822', color: '#1d4ed8' }}
                data-testid="job-case-type-pill"
              >
                {job.case_type}
              </span>
            ) : null}
            <span className="text-[10px] font-bold uppercase tracking-wider opacity-70" data-testid="job-status-pill">
              {STATUS_LABEL[job.status] || job.status}
            </span>
            {job.sla_resolve_at ? (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold"
                style={{ background: `${slaColour}22`, color: slaColour }}
                data-testid="job-sla-pill"
              >
                {slaBreached ? <AlertTriangle size={10} /> : <Clock size={10} />}
                {slaBreached ? 'SLA breached' : slaAtRisk ? 'SLA at risk' : `SLA ${fmtRelative(job.sla_resolve_at)}`}
              </span>
            ) : null}
          </div>
          <div className="text-xs opacity-80 space-y-1">
            {job.site_name ? (
              <p className="inline-flex items-center gap-1.5 flex-wrap">
                <MapPin size={12} /> {job.site_name}
                {(job.site_postcode || job.site_address) ? (
                  <a
                    href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(
                      `${job.site_name || ''} ${job.site_postcode || job.site_address || ''}`.trim(),
                    )}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
                    style={{ background: '#1d4ed822', color: '#1d4ed8' }}
                    data-testid="job-directions"
                  >
                    <Navigation size={10} /> Directions
                  </a>
                ) : null}
              </p>
            ) : null}
            {job.asset_name ? <p className="inline-flex items-center gap-1.5"><Wrench size={12} /> {job.asset_name}</p> : null}
            {job.fault_code ? <p className="opacity-70">Fault: <strong>{job.fault_code}</strong></p> : null}
          </div>
          {job.description ? <p className="text-sm border-t pt-2" style={{ borderColor: 'var(--theme-border)' }}>{job.description}</p> : null}
        </section>

        {/* Iter 216h85 — Asset history sidebar */}
        {(job.asset_history || []).length > 0 ? (
          <section
            className="rounded-2xl border p-3"
            style={{ borderColor: 'var(--theme-border)', background: '#fef9c3' }}
            data-testid="job-asset-history"
          >
            <p className="text-[10px] font-bold uppercase tracking-wider text-amber-900 mb-1.5">
              ⚡ Asset history · {job.asset_name || 'this asset'} ({job.asset_history.length} prior visit{job.asset_history.length === 1 ? '' : 's'})
            </p>
            <ul className="space-y-1.5">
              {job.asset_history.map((h) => (
                <li key={h.id} className="text-xs" data-testid={`job-asset-history-${h.id}`}>
                  <span className="font-bold opacity-80">{h.reference || h.id.slice(0, 8)}</span>
                  <span className="opacity-70"> · {h.title || 'Job'}</span>
                  {h.fault_code ? <span className="opacity-60"> · {h.fault_code}</span> : null}
                  {h.customer_rating ? <span className="opacity-70"> · {'★'.repeat(h.customer_rating)}</span> : null}
                  <span className="opacity-50 ml-1 tabular-nums">
                    · {(h.closed_at || h.created_at || '').split('T')[0]}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* Customer */}
        {(job.customer_name || job.customer_phone || job.customer_email) ? (
          <section className="rounded-2xl border p-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }} data-testid="job-customer">
            <p className="text-[10px] font-bold uppercase tracking-wider opacity-60 mb-1.5">Site contact</p>
            <p className="font-bold">{job.customer_name || '—'}</p>
            <div className="flex gap-2 mt-2">
              {job.customer_phone ? (
                <a href={`tel:${job.customer_phone}`} className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold text-white" style={{ background: '#10b981' }} data-testid="customer-call">
                  <Phone size={14} /> Call
                </a>
              ) : null}
              {job.customer_email ? (
                <a href={`mailto:${job.customer_email}`} className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold border" style={{ borderColor: 'var(--theme-border)' }} data-testid="customer-email">
                  Email
                </a>
              ) : null}
            </div>
          </section>
        ) : null}

        {/* Active timer */}
        {activeTimer ? (
          <section className="rounded-2xl p-3 text-white shadow-lg" style={{ background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)' }} data-testid="job-timer-banner">
            <p className="text-[10px] uppercase tracking-wider opacity-90 font-bold">Currently working</p>
            <ActiveTimer entry={activeTimer} />
            <button
              type="button"
              onClick={stopTimer}
              disabled={busy === 'stop'}
              className="mt-2 w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-white/20 backdrop-blur-sm text-white font-bold text-sm hover:bg-white/30 disabled:opacity-60"
              data-testid="job-stop-timer"
            >
              <Square size={14} /> Stop timer
            </button>
          </section>
        ) : !isClosed ? (
          <section className="rounded-2xl border p-3 space-y-2" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }} data-testid="job-timer-actions">
            <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">Time tracking</p>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => startTimer('travel')}
                disabled={busy.startsWith('start')}
                className="inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-lg text-sm font-bold border disabled:opacity-60"
                style={{ borderColor: 'var(--theme-border)' }}
                data-testid="job-start-travel"
              >
                <Play size={13} /> Travel
              </button>
              <button
                type="button"
                onClick={() => startTimer('on_site')}
                disabled={busy.startsWith('start')}
                className="inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-lg text-sm font-bold text-white disabled:opacity-60"
                style={{ background: 'var(--color-brand-blue, #1d4ed8)' }}
                data-testid="job-start-onsite"
              >
                <Play size={13} /> On site
              </button>
            </div>
          </section>
        ) : null}

        {/* Free-text note with voice dictation */}
        {!isClosed ? (
          <section
            className="rounded-2xl border p-3 space-y-2"
            style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }}
            data-testid="job-add-note-section"
          >
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">Quick note</p>
              {noteVoice.supported ? (
                <button
                  type="button"
                  onClick={noteVoice.listening ? noteVoice.stop : noteVoice.start}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider"
                  style={noteVoice.listening
                    ? { background: '#ef4444', color: 'white' }
                    : { background: '#1d4ed822', color: '#1d4ed8' }}
                  data-testid="job-note-voice-toggle"
                >
                  {noteVoice.listening ? <MicOff size={11} /> : <Mic size={11} />}
                  {noteVoice.listening ? 'Listening…' : 'Dictate'}
                </button>
              ) : null}
            </div>
            <textarea
              value={noteDraft}
              onChange={(e) => setNoteDraft(e.target.value)}
              rows={2}
              placeholder="e.g. Customer reports treadmill stops at 8 km/h. Front roller bearing rough."
              className="w-full px-3 py-2 rounded-lg border bg-transparent text-sm"
              style={{ borderColor: 'var(--theme-border)' }}
              data-testid="job-note-input"
            />
            <button
              type="button"
              onClick={submitNote}
              disabled={busy === 'note' || !noteDraft.trim()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white disabled:opacity-50"
              style={{ background: 'var(--color-brand-blue, #1d4ed8)' }}
              data-testid="job-note-submit"
            >
              <Plus size={12} /> {busy === 'note' ? 'Saving…' : 'Save note'}
            </button>
          </section>
        ) : null}


        {/* Parts used (iter 216h84) */}
        {!isClosed ? (
          <section
            className="rounded-2xl border p-3 space-y-2"
            style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }}
            data-testid="job-parts-section"
          >
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">
                Parts used ({allocatedParts.length})
              </p>
              <button
                type="button"
                onClick={() => setPartsOpen((v) => !v)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold text-white"
                style={{ background: 'var(--color-brand-blue, #1d4ed8)' }}
                data-testid="job-parts-toggle"
              >
                <Package size={12} /> {partsOpen ? 'Close' : 'Add part'}
              </button>
            </div>
            {allocatedParts.length > 0 ? (
              <ul className="space-y-1.5">
                {allocatedParts.map((p) => (
                  <li
                    key={p.id}
                    className="flex items-center gap-2 px-2 py-1.5 rounded-lg border text-xs"
                    style={{ borderColor: 'var(--theme-border)' }}
                    data-testid={`job-part-row-${p.id}`}
                  >
                    <span className="font-bold">{p.qty} ×</span>
                    <span className="truncate flex-1">
                      <span className="font-semibold">{p.part_sku}</span>
                      <span className="opacity-60"> · {p.part_name || ''}</span>
                    </span>
                    <span
                      className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full"
                      style={{
                        background: p.source === 'van' ? '#fef9c3' : '#e0e7ff',
                        color: p.source === 'van' ? '#92400e' : '#3730a3',
                      }}
                    >
                      {p.source}
                    </span>
                    <button
                      type="button"
                      onClick={() => deallocatePart(p.id)}
                      disabled={busy === `unalloc-${p.id}`}
                      className="p-1 opacity-60 hover:opacity-100 disabled:opacity-40"
                      data-testid={`job-part-remove-${p.id}`}
                      aria-label="Remove"
                    >
                      <Trash2 size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            ) : !partsOpen ? (
              <p className="text-xs opacity-60 italic">No parts used yet — tap Add part to record consumables.</p>
            ) : null}
            {partsOpen ? (
              <div className="space-y-2 pt-1 border-t" style={{ borderColor: 'var(--theme-border)' }}>
                <div className="flex items-center gap-1.5">
                  <Search size={12} className="opacity-50" />
                  <input
                    type="text"
                    value={partSearch}
                    onChange={(e) => setPartSearch(e.target.value)}
                    placeholder="Search SKU, name or manufacturer…"
                    className="flex-1 px-2 py-1.5 rounded-lg border bg-transparent text-xs"
                    style={{ borderColor: 'var(--theme-border)' }}
                    data-testid="job-parts-search"
                  />
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <label className="flex items-center gap-1">
                    <span className="opacity-60">Qty</span>
                    <input
                      type="number"
                      min={1}
                      value={partQty}
                      onChange={(e) => setPartQty(e.target.value)}
                      className="w-12 px-1.5 py-1 rounded border bg-transparent text-xs"
                      style={{ borderColor: 'var(--theme-border)' }}
                      data-testid="job-parts-qty"
                    />
                  </label>
                  <label className="flex items-center gap-1 ml-2">
                    <span className="opacity-60">From</span>
                    <select
                      value={partSource}
                      onChange={(e) => setPartSource(e.target.value)}
                      className="px-1.5 py-1 rounded border bg-transparent text-xs"
                      style={{ borderColor: 'var(--theme-border)' }}
                      data-testid="job-parts-source"
                    >
                      <option value="van">Van</option>
                      <option value="warehouse">Warehouse</option>
                    </select>
                  </label>
                </div>
                {partSearchBusy ? (
                  <p className="text-xs opacity-50 italic">Searching…</p>
                ) : partResults.length === 0 && partSearch ? (
                  <p className="text-xs opacity-50 italic" data-testid="job-parts-empty">No matches in your catalogue.</p>
                ) : null}
                {partResults.length > 0 ? (
                  <ul className="space-y-1">
                    {partResults.map((p) => (
                      <li key={p.sku} className="flex items-center gap-2">
                        <span className="flex-1 text-xs truncate">
                          <span className="font-bold">{p.sku}</span>
                          <span className="opacity-60"> · {p.name}</span>
                        </span>
                        <button
                          type="button"
                          onClick={() => allocatePart(p)}
                          disabled={busy.startsWith('part-')}
                          className="px-2 py-1 rounded-md text-[11px] font-bold text-white disabled:opacity-50"
                          style={{ background: '#10b981' }}
                          data-testid={`job-parts-allocate-${p.sku}`}
                        >
                          {busy === `part-${p.sku}` ? '…' : 'Allocate'}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : allocatedParts.length > 0 ? (
          <section
            className="rounded-2xl border p-3"
            style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }}
            data-testid="job-parts-section-readonly"
          >
            <p className="text-[10px] font-bold uppercase tracking-wider opacity-60 mb-2">
              Parts used ({allocatedParts.length})
            </p>
            <ul className="space-y-1.5">
              {allocatedParts.map((p) => (
                <li key={p.id} className="text-xs">
                  <span className="font-bold">{p.qty} ×</span>{' '}
                  <span className="font-semibold">{p.part_sku}</span>
                  <span className="opacity-60"> · {p.part_name || ''}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* Photos */}
        <section className="rounded-2xl border p-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }} data-testid="job-photos-section">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">Photos ({job.photos?.length || 0})</p>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy === 'photo'}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white disabled:opacity-60"
              style={{ background: 'var(--color-brand-blue, #1d4ed8)' }}
              data-testid="job-add-photo"
            >
              <Camera size={12} /> {busy === 'photo' ? 'Uploading…' : 'Add photo'}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={onPhotoFile}
              data-testid="job-photo-input"
            />
          </div>
          {(job.photos || []).length === 0 ? (
            <p className="text-xs opacity-60 italic">No photos yet — add before/after shots so customers + auditors can see the work.</p>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-2">
                {(job.photos || []).slice(0, 9).map((p) => (
                  <div key={p.id} className="space-y-0.5">
                    <a
                      href={p.file_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block aspect-square rounded-lg border overflow-hidden flex items-center justify-center bg-slate-100"
                      style={{ borderColor: 'var(--theme-border)' }}
                      data-testid={`job-photo-${p.id}`}
                    >
                      {p.file_url ? (
                        <img src={p.file_url} alt={p.caption || 'service'} className="w-full h-full object-cover" loading="lazy" />
                      ) : (
                        <ImageIcon size={20} className="opacity-40" />
                      )}
                    </a>
                    {p.ai?.severity ? (
                      <span
                        className="block text-center text-[9px] font-bold uppercase tracking-wider rounded-sm"
                        style={{
                          background: p.ai.severity === 'high' ? '#fee2e2' : p.ai.severity === 'med' ? '#fef3c7' : '#dcfce7',
                          color: p.ai.severity === 'high' ? '#991b1b' : p.ai.severity === 'med' ? '#92400e' : '#166534',
                        }}
                        title={p.ai.summary}
                        data-testid={`job-photo-ai-${p.id}`}
                      >
                        {p.ai.severity} · {(p.ai.tags || [])[0] || ''}
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => classifyPhoto(p.id)}
                        disabled={busy === `classify-${p.id}`}
                        className="block w-full text-[9px] font-bold uppercase tracking-wider rounded-sm py-0.5 border disabled:opacity-50"
                        style={{ borderColor: 'var(--theme-border)' }}
                        data-testid={`job-photo-classify-${p.id}`}
                      >
                        {busy === `classify-${p.id}` ? '…' : 'Analyse'}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Service Report — visible once the job is ready for sign-off or closed */}
        {(['repaired', 'awaiting_sign_off', 'closed', 'invoiced'].includes(job.status)) ? (
          <section
            className="rounded-2xl border p-3 space-y-2"
            style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }}
            data-testid="job-service-report-section"
          >
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">Service report</p>
              {job.service_report_sent_at ? (
                <span
                  className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full"
                  style={{ background: '#dcfce7', color: '#166534' }}
                  data-testid="job-service-report-sent-pill"
                >
                  Sent · {fmtRelative(job.service_report_sent_at)}
                </span>
              ) : null}
            </div>
            <p className="text-xs opacity-70">
              One-page PDF: site, asset, time, parts, photos, sign-off, rating. Hand to the customer or email it.
            </p>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={openServiceReport}
                disabled={busy.startsWith('email-report')}
                className="inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-lg text-sm font-bold border disabled:opacity-60"
                style={{ borderColor: 'var(--theme-border)' }}
                data-testid="job-view-service-report"
              >
                <FileText size={13} /> View report
              </button>
              <button
                type="button"
                onClick={emailServiceReport}
                disabled={busy === 'email-report'}
                className="inline-flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-lg text-sm font-bold text-white disabled:opacity-60"
                style={{ background: '#1d4ed8' }}
                data-testid="job-email-service-report"
              >
                <Send size={13} /> {busy === 'email-report' ? 'Sending…' : (job.service_report_sent_at ? 'Resend' : 'Send to customer')}
              </button>
            </div>
            {job.service_report_sent_to ? (
              <p className="text-[10px] opacity-60" data-testid="job-service-report-recipient">
                Last sent to {job.service_report_sent_to}
              </p>
            ) : null}
          </section>
        ) : null}

        {/* Complete & sign-off */}
        {!isClosed ? (
          <section className="rounded-2xl border p-3 space-y-2" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }} data-testid="job-complete-section">
            <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">Wrap up</p>
            {!completeOpen ? (
              <button
                type="button"
                onClick={() => setCompleteOpen(true)}
                className="w-full inline-flex items-center justify-center gap-2 px-3 py-3 rounded-xl text-sm font-extrabold text-white"
                style={{ background: '#0f172a' }}
                data-testid="job-open-complete"
              >
                <CheckCircle size={16} /> Complete this job
              </button>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider opacity-60">Work summary</span>
                  {wrapVoice.supported ? (
                    <button
                      type="button"
                      onClick={wrapVoice.listening ? wrapVoice.stop : wrapVoice.start}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider"
                      style={wrapVoice.listening
                        ? { background: '#ef4444', color: 'white' }
                        : { background: '#1d4ed822', color: '#1d4ed8' }}
                      data-testid="job-wrap-voice-toggle"
                    >
                      {wrapVoice.listening ? <MicOff size={11} /> : <Mic size={11} />}
                      {wrapVoice.listening ? 'Listening…' : 'Dictate'}
                    </button>
                  ) : null}
                </div>
                <textarea
                  value={completeSummary}
                  onChange={(e) => setCompleteSummary(e.target.value)}
                  rows={3}
                  placeholder="Replaced running belt + reset deck. Tested at 12 km/h for 5 min — no slap."
                  className="w-full px-3 py-2 rounded-lg border bg-transparent text-sm"
                  style={{ borderColor: 'var(--theme-border)' }}
                  data-testid="job-complete-summary"
                />
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={completeChargeable}
                    onChange={(e) => setCompleteChargeable(e.target.checked)}
                    data-testid="job-complete-chargeable"
                  />
                  This visit is chargeable (raises Sage invoice draft)
                </label>

                <div className="grid grid-cols-2 gap-2 pt-1">
                  <input
                    type="text"
                    placeholder="Signed by (name)"
                    value={signatureName}
                    onChange={(e) => setSignatureName(e.target.value)}
                    className="px-3 py-2 rounded-lg border bg-transparent text-sm"
                    style={{ borderColor: 'var(--theme-border)' }}
                    data-testid="job-signed-by"
                  />
                  <button
                    type="button"
                    onClick={() => setShowSig(true)}
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold border"
                    style={{ borderColor: 'var(--theme-border)' }}
                    data-testid="job-open-signature"
                  >
                    <PenLine size={13} /> Capture signature
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => submitComplete('awaiting_sign_off')}
                    disabled={busy.startsWith('complete')}
                    className="px-3 py-2.5 rounded-lg text-sm font-bold border disabled:opacity-60"
                    style={{ borderColor: 'var(--theme-border)' }}
                    data-testid="job-mark-awaiting"
                  >
                    Mark for sign-off
                  </button>
                  <button
                    type="button"
                    onClick={() => submitComplete('closed')}
                    disabled={busy.startsWith('complete')}
                    className="px-3 py-2.5 rounded-lg text-sm font-bold text-white disabled:opacity-60"
                    style={{ background: '#10b981' }}
                    data-testid="job-mark-closed"
                  >
                    {busy === 'complete-closed' ? 'Closing…' : 'Close job'}
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => { setCompleteOpen(false); setCompleteSummary(''); }}
                  className="w-full text-center text-xs opacity-60 underline pt-1"
                  data-testid="job-cancel-complete"
                >
                  cancel
                </button>
              </div>
            )}
          </section>
        ) : (
          <p className="text-center text-sm opacity-60 italic" data-testid="job-closed-msg">This job is {STATUS_LABEL[job.status] || job.status}. Read-only.</p>
        )}

        {/* Recent timeline (read-only on mobile) */}
        <section className="rounded-2xl border p-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }} data-testid="job-timeline-section">
          <p className="text-[10px] font-bold uppercase tracking-wider opacity-60 mb-1.5">Recent timeline</p>
          <ol className="space-y-1.5">
            {(job.events || []).slice(0, 8).map((ev) => (
              <li key={ev.id} className="text-xs">
                <span className="font-bold opacity-80">{ev.type}</span>
                {ev.body ? <span className="opacity-70">: {ev.body}</span> : null}
                <span className="opacity-50 ml-1 tabular-nums">· {new Date(ev.at).toLocaleTimeString()}</span>
              </li>
            ))}
            {(job.events || []).length === 0 ? <li className="text-xs opacity-60">No events yet.</li> : null}
          </ol>
        </section>
      </main>

      {showSig ? (
        <SignatureCanvas onSubmit={submitSignature} onCancel={() => setShowSig(false)} />
      ) : null}
    </div>
  );
}
