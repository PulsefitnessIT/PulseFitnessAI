/**
 * EngineerJobDetailV2 — Phase 3 light-mode job workflow.
 *
 * Iter 216h133. Light-mode GymAxis aesthetic. Tabs: Time · Travel ·
 * Photos · Parts · Complete. Surfaces all existing engineer.py
 * primitives plus new Phase 3 endpoints (mileage, ad-hoc parts,
 * generate-invoice-draft).
 *
 * Endpoints used:
 *   GET    /api/svc/engineer/jobs/{caseId}
 *   POST   /api/svc/engineer/time/start | /time/stop
 *   POST   /api/svc/engineer/photos                       (existing)
 *   POST   /api/files/upload?category=photos              (existing)
 *   POST   /api/svc/engineer/jobs/{id}/mileage            (Phase 3 NEW)
 *   GET    /api/svc/engineer/jobs/{id}/mileage            (Phase 3 NEW)
 *   POST   /api/svc/engineer/jobs/{id}/parts/use          (Phase 3 NEW)
 *   POST   /api/svc/engineer/jobs/{id}/parts/{id}/consume (Phase 3 NEW)
 *   POST   /api/svc/engineer/jobs/{id}/generate-invoice-draft (Phase 3 NEW)
 *   POST   /api/svc/engineer/jobs/{id}/complete           (existing)
 *   POST   /api/svc/engineer/signature                    (existing)
 *   GET    /api/svc/parts                                 (catalogue search)
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Clock, Camera, Wrench, Car, Loader2, RefreshCw,
  Play, Square, Plus, Trash2, Check, AlertTriangle, Receipt,
  ChevronRight, CheckCircle2, Search, Package, X, Image as ImageIcon,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import SignatureCanvas from './SignatureCanvas';
import EngineerDictationButton from './EngineerDictationButton';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });
const fmtGBP = (n) => `£${Number(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtMins = (m) => {
  const total = Math.max(0, Math.round(m || 0));
  const h = Math.floor(total / 60);
  const r = total % 60;
  return h > 0 ? `${h}h ${r}m` : `${r}m`;
};

const TABS = [
  { id: 'time',     label: 'Time',     icon: Clock },
  { id: 'travel',   label: 'Travel',   icon: Car },
  { id: 'photos',   label: 'Photos',   icon: Camera },
  { id: 'parts',    label: 'Parts',    icon: Wrench },
  { id: 'complete', label: 'Complete', icon: CheckCircle2 },
];

export default function EngineerJobDetailV2() {
  const navigate = useNavigate();
  const { caseId } = useParams();
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('time');
  const [mileage, setMileage] = useState({ items: [], total_miles: 0, total_amount_gbp: 0 });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [j, m] = await Promise.all([
        axios.get(`${API}/svc/engineer/jobs/${caseId}`, auth()),
        axios.get(`${API}/svc/engineer/jobs/${caseId}/mileage`, auth()).catch(() => ({ data: { items: [], total_miles: 0, total_amount_gbp: 0 } })),
      ]);
      setJob(j.data);
      setMileage(m.data);
    } catch (e) {
      const status = e?.response?.status;
      if (status === 404) notify.error('Job not found');
      else if (status === 403) notify.error('Not assigned to this job');
      else notify.error('Failed to load job');
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => { load(); }, [load]);

  const activeTimer = useMemo(() => (job?.time_entries || []).find(t => !t.end_at) || null, [job]);

  if (loading && !job) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-400">
        <Loader2 className="animate-spin mr-2" size={18} /> Loading job…
      </div>
    );
  }
  if (!job) {
    return <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-500">Job unavailable.</div>;
  }

  const lockedComplete = ['closed', 'invoiced', 'awaiting_sign_off', 'repaired'].includes(job.status);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-job-detail-v2">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
          <button onClick={() => navigate('/svc/engineer')} className="p-2 rounded-full hover:bg-slate-100" aria-label="Back" data-testid="job-back">
            <ArrowLeft size={18} />
          </button>
          <div className="flex-1 min-w-0">
            <p className="text-[10px] uppercase tracking-[0.2em] font-bold text-blue-700">{job.reference}</p>
            <h1 className="text-base font-extrabold text-slate-900 truncate">{job.title}</h1>
            <p className="text-xs text-slate-500 truncate">
              {job.site_name || 'Unknown site'}{job.asset_name ? ` · ${job.asset_name}` : ''} · <span className="capitalize">{job.status}</span>
            </p>
          </div>
          <button onClick={load} aria-label="Refresh" className="p-2 rounded-full border border-slate-200 bg-white" data-testid="job-refresh">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
        <ActiveTimerBar timer={activeTimer} onStop={async () => {
          setBusy(true);
          try {
            await axios.post(`${API}/svc/engineer/time/stop`, { entry_id: activeTimer.id }, auth());
            notify.success('Timer stopped');
            await load();
          } catch (e) {
            notify.error('Could not stop timer');
          } finally { setBusy(false); }
        }} />
        <nav className="max-w-4xl mx-auto px-2 flex items-center gap-0.5 overflow-x-auto" data-testid="job-tabs">
          {TABS.map(t => {
            const Icon = t.icon;
            const active = activeTab === t.id;
            return (
              <button key={t.id} type="button" onClick={() => setActiveTab(t.id)}
                className={`relative flex items-center gap-1.5 px-3 py-2 text-xs font-bold uppercase tracking-wide ${active ? 'text-blue-700' : 'text-slate-500 hover:text-slate-700'}`}
                data-testid={`job-tab-${t.id}`}>
                <Icon size={14} />
                {t.label}
                {active && <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-blue-700 rounded-t" />}
              </button>
            );
          })}
        </nav>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-5 pb-28 space-y-4">
        {activeTab === 'time'   && <TimeTab job={job} busy={busy} setBusy={setBusy} onChange={load} />}
        {activeTab === 'travel' && <TravelTab job={job} mileage={mileage} onChange={load} />}
        {activeTab === 'photos' && <PhotosTab job={job} onChange={load} />}
        {activeTab === 'parts'  && <PartsTab job={job} onChange={load} />}
        {activeTab === 'complete' && <CompleteTab job={job} locked={lockedComplete} onChange={load} navigate={navigate} />}
      </main>
    </div>
  );
}

// ─────────────────────────── Active timer bar ───────────────────────────

function ActiveTimerBar({ timer, onStop }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!timer) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [timer]);
  if (!timer) return null;
  const ms = Math.max(0, now - new Date(timer.start_at).getTime());
  const mins = Math.floor(ms / 60000);
  const secs = String(Math.floor((ms % 60000) / 1000)).padStart(2, '0');
  return (
    <div className="bg-emerald-50 border-y border-emerald-200" data-testid="job-active-timer-bar">
      <div className="max-w-4xl mx-auto px-4 py-2 flex items-center gap-3">
        <Clock size={16} className="text-emerald-600" />
        <div className="flex-1 min-w-0">
          <p className="text-[10px] uppercase font-bold tracking-wide text-emerald-700">
            On the clock · {timer.category}
          </p>
          <p className="text-base font-extrabold tabular-nums text-emerald-900">{mins}m {secs}s</p>
        </div>
        <button onClick={onStop} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700" data-testid="job-active-timer-stop">
          <Square size={12} /> Stop
        </button>
      </div>
    </div>
  );
}

// ────────────────────────────── Time tab ────────────────────────────────

function TimeTab({ job, busy, setBusy, onChange }) {
  const entries = job.time_entries || [];
  const active = entries.find(e => !e.end_at);
  const blockedBySafety = !job.safety_signoff && job?.safety_template;

  const start = async (category) => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/engineer/time/start`,
        { case_id: job.id, category }, auth());
      notify.success(`${category.replace('_', ' ')} timer started`);
      await onChange();
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.code === 'safety_signoff_required') {
        notify.error('Complete the H&S checklist first (on the existing job detail page).');
      } else {
        notify.error('Could not start timer');
      }
    } finally { setBusy(false); }
  };

  const totalsByCategory = entries.reduce((acc, e) => {
    const k = e.category || 'on_site';
    acc[k] = (acc[k] || 0) + (e.duration_minutes || 0);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {blockedBySafety && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 flex items-start gap-2" data-testid="time-safety-warning">
          <AlertTriangle size={14} className="mt-0.5" />
          <span>Pre-job H&amp;S checklist required before starting the <b>on-site</b> timer.</span>
        </div>
      )}

      <div className="grid grid-cols-3 gap-2" data-testid="time-totals">
        <Totals label="On site"   value={fmtMins(totalsByCategory.on_site)} color="#1d4ed8" />
        <Totals label="Travel"    value={fmtMins(totalsByCategory.travel)}  color="#6366f1" />
        <Totals label="Admin"     value={fmtMins(totalsByCategory.admin)}   color="#64748b" />
      </div>

      {!active ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="time-start-card">
          <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Start a timer</p>
          <div className="grid grid-cols-3 gap-2">
            <button disabled={busy} onClick={() => start('on_site')} className="flex flex-col items-center gap-1 py-3 rounded-xl border border-blue-200 bg-blue-50 text-blue-800 hover:bg-blue-100 disabled:opacity-50" data-testid="time-start-on_site">
              <Play size={16} /><span className="text-xs font-bold">On site</span>
            </button>
            <button disabled={busy} onClick={() => start('travel')} className="flex flex-col items-center gap-1 py-3 rounded-xl border border-indigo-200 bg-indigo-50 text-indigo-800 hover:bg-indigo-100 disabled:opacity-50" data-testid="time-start-travel">
              <Car size={16} /><span className="text-xs font-bold">Travel</span>
            </button>
            <button disabled={busy} onClick={() => start('admin')} className="flex flex-col items-center gap-1 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-800 hover:bg-slate-100 disabled:opacity-50" data-testid="time-start-admin">
              <Clock size={16} /><span className="text-xs font-bold">Admin</span>
            </button>
          </div>
        </div>
      ) : null}

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="time-history">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">History</p>
        {entries.length === 0 ? (
          <p className="text-center text-sm text-slate-400 py-6">No time logged yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {entries.map(e => (
              <li key={e.id} className="py-2 flex items-center gap-3" data-testid={`time-entry-${e.id}`}>
                <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full"
                  style={{ background: e.category === 'on_site' ? '#dbeafe' : e.category === 'travel' ? '#e0e7ff' : '#f1f5f9',
                           color: e.category === 'on_site' ? '#1d4ed8' : e.category === 'travel' ? '#4338ca' : '#475569' }}>
                  {e.category}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{fmtMins(e.duration_minutes)} {!e.end_at && <span className="text-emerald-600">· running</span>}</p>
                  <p className="text-[11px] text-slate-500">{new Date(e.start_at).toLocaleString('en-GB')}</p>
                </div>
                {e.chargeable && <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">£</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

const Totals = ({ label, value, color }) => (
  <div className="bg-white rounded-2xl border border-slate-200 p-3 text-center">
    <p className="text-[10px] uppercase font-bold tracking-wide text-slate-500">{label}</p>
    <p className="text-base font-extrabold tabular-nums mt-0.5" style={{ color }}>{value}</p>
  </div>
);

// ─────────────────────────── Travel / Mileage tab ───────────────────────

function TravelTab({ job, mileage, onChange }) {
  const [form, setForm] = useState({ miles: '', from_postcode: '', to_postcode: '', notes: '', chargeable: true });
  const [adding, setAdding] = useState(false);

  const submit = async () => {
    const miles = Number(form.miles);
    if (!(miles > 0)) { notify.error('Enter miles > 0'); return; }
    setAdding(true);
    try {
      await axios.post(`${API}/svc/engineer/jobs/${job.id}/mileage`, {
        miles,
        from_postcode: form.from_postcode || null,
        to_postcode: form.to_postcode || null,
        notes: form.notes || null,
        chargeable: form.chargeable,
      }, auth());
      notify.success('Mileage logged');
      setForm({ miles: '', from_postcode: '', to_postcode: '', notes: '', chargeable: true });
      await onChange();
    } catch (e) {
      notify.error('Could not log mileage');
    } finally { setAdding(false); }
  };

  const remove = async (id) => {
    try {
      await axios.delete(`${API}/svc/engineer/jobs/${job.id}/mileage/${id}`, auth());
      notify.success('Removed');
      await onChange();
    } catch { notify.error('Could not delete'); }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2">
        <Totals label="Miles"   value={mileage.total_miles?.toFixed(1) || '0.0'} color="#6366f1" />
        <Totals label="Billable" value={fmtGBP(mileage.total_amount_gbp)} color="#059669" />
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="mileage-form">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Log mileage</p>
        <div className="grid grid-cols-2 gap-2">
          <Input label="Miles *" type="number" v={form.miles} on={v => setForm(f => ({ ...f, miles: v }))} testid="mileage-miles" />
          <div className="flex items-end gap-2">
            <label className="text-xs text-slate-600 flex items-center gap-2 select-none">
              <input type="checkbox" checked={form.chargeable} onChange={e => setForm(f => ({ ...f, chargeable: e.target.checked }))} data-testid="mileage-chargeable" />
              Chargeable
            </label>
          </div>
          <Input label="From postcode" v={form.from_postcode} on={v => setForm(f => ({ ...f, from_postcode: v }))} testid="mileage-from" />
          <Input label="To postcode"   v={form.to_postcode}   on={v => setForm(f => ({ ...f, to_postcode: v }))}   testid="mileage-to" />
        </div>
        <Input label="Notes" v={form.notes} on={v => setForm(f => ({ ...f, notes: v }))} testid="mileage-notes" fullWidth />
        <button onClick={submit} disabled={adding} className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold disabled:opacity-50" data-testid="mileage-add-btn">
          {adding ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          Add mileage
        </button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="mileage-history">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">History</p>
        {mileage.items.length === 0 ? (
          <p className="text-center text-sm text-slate-400 py-6">No mileage logged yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {mileage.items.map(m => (
              <li key={m.id} className="py-2 flex items-center gap-3" data-testid={`mileage-row-${m.id}`}>
                <Car size={16} className="text-indigo-500" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{m.miles} mi · {fmtGBP(m.amount_gbp)}</p>
                  <p className="text-[11px] text-slate-500 truncate">
                    {(m.from_postcode || '—')} → {(m.to_postcode || '—')}
                    {m.notes ? ` · ${m.notes}` : ''}
                  </p>
                </div>
                <button onClick={() => remove(m.id)} className="p-1 text-slate-400 hover:text-rose-600" aria-label="Remove" data-testid={`mileage-remove-${m.id}`}>
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

const Input = ({ label, v, on, testid, type = 'text', fullWidth }) => (
  <div className={fullWidth ? 'col-span-2 mt-2' : ''}>
    <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">{label}</label>
    <input type={type} value={v ?? ''} onChange={e => on(e.target.value)} className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white" data-testid={testid} />
  </div>
);

// ─────────────────────────── Photos tab ──────────────────────────────

function PhotosTab({ job, onChange }) {
  const [uploading, setUploading] = useState(false);
  const [caption, setCaption] = useState('');
  const [stage, setStage] = useState('progress'); // before / progress / after
  const fileInput = useRef(null);
  const photos = job.photos || [];

  const grouped = useMemo(() => ({
    before:   photos.filter(p => (p.caption || '').toLowerCase().startsWith('[before]')),
    progress: photos.filter(p => !/^\[(before|after)]/i.test(p.caption || '')),
    after:    photos.filter(p => (p.caption || '').toLowerCase().startsWith('[after]')),
  }), [photos]);

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const u = await axios.post(`${API}/files/upload?category=photos`, fd, {
        ...auth(),
        headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
      });
      const fileUrl = u.data?.download_url || u.data?.storage_path;
      const prefix = stage === 'before' ? '[BEFORE] ' : stage === 'after' ? '[AFTER] ' : '';
      await axios.post(`${API}/svc/engineer/photos`, {
        case_id: job.id, file_url: fileUrl, mime_type: u.data?.content_type || 'image/jpeg',
        caption: (prefix + (caption || '')).trim(),
      }, auth());
      notify.success('Photo attached');
      setCaption('');
      e.target.value = '';
      await onChange();
    } catch (err) {
      notify.error('Upload failed');
    } finally { setUploading(false); }
  };

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="photos-uploader">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Capture a photo</p>
        <div className="flex gap-1 mb-3" data-testid="photo-stage-toggle">
          {['before', 'progress', 'after'].map(s => (
            <button key={s} type="button" onClick={() => setStage(s)}
              className={`flex-1 py-1.5 rounded-lg text-xs font-bold capitalize border ${stage === s ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200'}`}
              data-testid={`photo-stage-${s}`}>
              {s}
            </button>
          ))}
        </div>
        <input type="text" placeholder="Optional caption" value={caption} onChange={e => setCaption(e.target.value)} className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white mb-2" data-testid="photo-caption" />
        <input ref={fileInput} type="file" accept="image/*" capture="environment" onChange={onFile} className="hidden" data-testid="photo-file-input" />
        <button type="button" onClick={() => fileInput.current?.click()} disabled={uploading} className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold disabled:opacity-50" data-testid="photo-upload-btn">
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
          Take / upload photo
        </button>
      </div>

      {(['before', 'progress', 'after']).map(stage => (
        <div key={stage} className="bg-white rounded-2xl border border-slate-200 p-4" data-testid={`photos-group-${stage}`}>
          <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2 capitalize">{stage} ({grouped[stage].length})</p>
          {grouped[stage].length === 0 ? (
            <p className="text-center text-xs text-slate-400 py-4">No {stage} photos.</p>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {grouped[stage].map(p => (
                <a key={p.id} href={p.file_url} target="_blank" rel="noopener" className="aspect-square rounded-lg overflow-hidden bg-slate-100 border border-slate-200 hover:border-slate-300" data-testid={`photo-${p.id}`}>
                  {/* eslint-disable-next-line jsx-a11y/img-redundant-alt */}
                  <img src={p.file_url} alt={p.caption || 'job photo'} className="w-full h-full object-cover" />
                </a>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────── Parts tab ───────────────────────────────

function PartsTab({ job, onChange }) {
  const [search, setSearch] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [adhoc, setAdhoc] = useState({ part_sku: '', qty: 1, notes: '' });
  const [busy, setBusy] = useState(false);

  const runSearch = useCallback(async (q) => {
    if (!q || q.length < 2) { setResults([]); return; }
    setSearching(true);
    try {
      const r = await axios.get(`${API}/svc/parts`, { ...auth(), params: { q, limit: 12 } });
      setResults(r.data?.items || []);
    } catch { setResults([]); }
    finally { setSearching(false); }
  }, []);
  useEffect(() => {
    const id = setTimeout(() => runSearch(search), 300);
    return () => clearTimeout(id);
  }, [search, runSearch]);

  const consume = async (allocationId) => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/engineer/jobs/${job.id}/parts/${allocationId}/consume`, {}, auth());
      notify.success('Marked as used');
      await onChange();
    } catch { notify.error('Could not update'); }
    finally { setBusy(false); }
  };

  const usePart = async (sku, qty = 1) => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/engineer/jobs/${job.id}/parts/use`, {
        part_sku: sku, qty, notes: adhoc.notes || null,
      }, auth());
      notify.success(`${sku} × ${qty} added`);
      setAdhoc({ part_sku: '', qty: 1, notes: '' });
      setSearch('');
      setResults([]);
      await onChange();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not add part');
    } finally { setBusy(false); }
  };

  const allocated = job.allocated_parts || [];
  const open = allocated.filter(a => !a.fulfilled);
  const used = allocated.filter(a => a.fulfilled);

  return (
    <div className="space-y-4">
      {open.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="parts-allocated">
          <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Allocated for this job</p>
          <ul className="divide-y divide-slate-100">
            {open.map(a => (
              <li key={a.id} className="py-2 flex items-center gap-3" data-testid={`parts-allocated-${a.id}`}>
                <Package size={16} className="text-slate-500" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{a.qty} × {a.part_sku}</p>
                  <p className="text-[11px] text-slate-500 truncate">{a.part_name} · from {a.source}</p>
                </div>
                <button onClick={() => consume(a.id)} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-emerald-600 text-white text-xs font-bold disabled:opacity-50" data-testid={`parts-consume-${a.id}`}>
                  <Check size={12} /> Mark used
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="parts-adhoc-form">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Add a part you used</p>
        <div className="relative mb-2">
          <Search size={14} className="absolute left-3 top-3 text-slate-400" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search catalogue by SKU or name…" className="w-full text-sm border border-slate-200 rounded-lg pl-9 pr-3 py-2 bg-white" data-testid="parts-search" />
        </div>
        {results.length > 0 && (
          <ul className="border border-slate-200 rounded-lg divide-y divide-slate-100 max-h-56 overflow-y-auto mb-2" data-testid="parts-search-results">
            {results.map(p => (
              <li key={p.id} className="flex items-center gap-3 px-3 py-2 hover:bg-slate-50" data-testid={`parts-result-${p.sku}`}>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{p.sku}</p>
                  <p className="text-[11px] text-slate-500 truncate">{p.name} · {fmtGBP(p.list_price)}</p>
                </div>
                <button onClick={() => usePart(p.sku, 1)} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-blue-600 text-white text-xs font-bold disabled:opacity-50" data-testid={`parts-use-${p.sku}`}>
                  <Plus size={12} /> Use
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="grid grid-cols-3 gap-2 mt-2">
          <Input label="SKU"   v={adhoc.part_sku} on={v => setAdhoc(f => ({ ...f, part_sku: v }))} testid="parts-adhoc-sku" />
          <Input label="Qty"   type="number" v={adhoc.qty} on={v => setAdhoc(f => ({ ...f, qty: Math.max(1, Number(v)) }))} testid="parts-adhoc-qty" />
          <div className="flex items-end">
            <button onClick={() => adhoc.part_sku && usePart(adhoc.part_sku.toUpperCase(), Number(adhoc.qty) || 1)} disabled={busy || !adhoc.part_sku} className="w-full inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold disabled:opacity-50" data-testid="parts-adhoc-add">
              <Plus size={14} /> Add
            </button>
          </div>
        </div>
      </div>

      {used.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="parts-used-list">
          <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Used on this job</p>
          <ul className="divide-y divide-slate-100">
            {used.map(a => (
              <li key={a.id} className="py-2 flex items-center gap-3" data-testid={`parts-used-${a.id}`}>
                <CheckCircle2 size={16} className="text-emerald-500" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{a.qty} × {a.part_sku}</p>
                  <p className="text-[11px] text-slate-500 truncate">{a.part_name}</p>
                </div>
                {a.list_price_gbp ? <span className="text-xs font-bold text-slate-700 tabular-nums">{fmtGBP(a.list_price_gbp * (a.qty || 0))}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────── Complete tab ───────────────────────────

function CompleteTab({ job, locked, onChange, navigate }) {
  const [summary, setSummary] = useState(job.resolution_notes || '');
  const [signatureName, setSignatureName] = useState('');
  const [signatureData, setSignatureData] = useState('');
  const [showSignature, setShowSignature] = useState(false);
  const [target, setTarget] = useState('awaiting_sign_off');
  const [busy, setBusy] = useState(false);
  const [autoInvoice, setAutoInvoice] = useState(true);
  const [draft, setDraft] = useState(null);

  const complete = async () => {
    if (!summary.trim()) { notify.error('Add a work summary'); return; }
    setBusy(true);
    try {
      if (signatureData && signatureName.trim()) {
        await axios.post(`${API}/svc/engineer/signature`, {
          case_id: job.id, signed_by_name: signatureName.trim(),
          image_data: signatureData, summary: summary.trim(),
        }, auth());
      }
      await axios.post(`${API}/svc/engineer/jobs/${job.id}/complete`, {
        summary: summary.trim(), target, chargeable: true,
      }, auth());
      notify.success('Job completed');
      if (autoInvoice) {
        try {
          const r = await axios.post(
            `${API}/svc/engineer/jobs/${job.id}/generate-invoice-draft`, {}, auth(),
          );
          setDraft(r.data);
          notify.success(`Draft ${r.data.invoice_number} created`);
        } catch (e) {
          const m = e?.response?.data?.detail || 'No chargeable lines yet';
          notify.error(`Invoice draft skipped: ${m}`);
        }
      }
      await onChange();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not complete job');
    } finally { setBusy(false); }
  };

  if (locked) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-5 text-center" data-testid="complete-locked">
        <CheckCircle2 size={28} className="mx-auto text-emerald-500 mb-2" />
        <p className="text-sm font-bold text-slate-900 capitalize">{job.status.replace('_', ' ')}</p>
        <p className="text-xs text-slate-500 mt-1">This job is already wrapped up.</p>
        {job.invoice_draft_id ? (
          <button onClick={() => navigate(`/svc/engineer/invoices/${job.invoice_draft_id}`)} className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-bold" data-testid="complete-open-invoice">
            <Receipt size={14} /> Open invoice {job.invoice_draft_number}
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="complete-summary-card">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Work summary *</p>
        <textarea rows={4} value={summary} onChange={e => setSummary(e.target.value)} placeholder="What was repaired / replaced / advised…" className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white" data-testid="complete-summary" />
      </div>

      <EngineerDictationButton
        caseId={job.id}
        hint={`${job.title || ''} · ${job.asset_name || ''}`.trim()}
        onResult={(data) => {
          // Prefer the polished summary; fall back to raw transcript.
          if (data?.summary) setSummary(data.summary);
          else if (data?.transcript) setSummary(data.transcript);
        }}
      />

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="complete-signature-card">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Customer signature (optional)</p>
        <Input label="Signed by" v={signatureName} on={setSignatureName} testid="complete-signed-by" fullWidth />
        <button type="button" onClick={() => setShowSignature(true)} className="mt-2 w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-slate-200 bg-white text-slate-700 text-sm font-bold" data-testid="complete-open-signature">
          {signatureData ? <><Check size={14} className="text-emerald-600" /> Signature captured · re-sign</> : <><ImageIcon size={14} /> Capture signature</>}
        </button>
        {showSignature && (
          <SignatureCanvas
            onSubmit={(dataUrl) => { setSignatureData(dataUrl); setShowSignature(false); }}
            onCancel={() => setShowSignature(false)}
          />
        )}
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="complete-options-card">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Outcome</p>
        <div className="flex gap-2 flex-wrap">
          {[
            { id: 'awaiting_sign_off', label: 'Awaiting sign-off' },
            { id: 'repaired',          label: 'Repaired' },
            { id: 'closed',            label: 'Close & invoice' },
          ].map(o => (
            <button key={o.id} type="button" onClick={() => setTarget(o.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-bold border ${target === o.id ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-700 border-slate-200'}`}
              data-testid={`complete-target-${o.id}`}>
              {o.label}
            </button>
          ))}
        </div>
        <label className="mt-3 flex items-center gap-2 text-xs text-slate-700 select-none">
          <input type="checkbox" checked={autoInvoice} onChange={e => setAutoInvoice(e.target.checked)} data-testid="complete-auto-invoice" />
          Generate invoice draft from time + mileage + parts
        </label>
      </div>

      {draft && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 flex items-center gap-3" data-testid="complete-draft-banner">
          <CheckCircle2 size={20} className="text-emerald-600" />
          <div className="flex-1">
            <p className="text-sm font-bold text-emerald-900">Invoice draft {draft.invoice_number} created</p>
            <p className="text-[11px] text-emerald-800">{(draft.lines || []).length} line(s) · total {fmtGBP(draft.total)}</p>
          </div>
          <button onClick={() => navigate(`/svc/engineer/invoices/${draft.id}`)} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-emerald-600 text-white text-xs font-bold" data-testid="complete-open-draft">
            <ChevronRight size={12} /> Open
          </button>
        </div>
      )}

      <div className="sticky bottom-4">
        <button onClick={complete} disabled={busy} className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-2xl bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold shadow-md disabled:opacity-50" data-testid="complete-submit">
          {busy ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
          Complete job
        </button>
      </div>
    </div>
  );
}
