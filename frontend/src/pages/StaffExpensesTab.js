/**
 * Staff Portal — Expenses (monthly claim, modelled on the Pulse Fitness
 * template). Guided + dummy-proof: prefilled name/department, pick a mileage
 * rate and type miles (£ auto-calcs), add itemised lines with a nominal code
 * and Net/VAT/Total (+ "no VAT on receipt" toggle), snap a receipt photo for
 * AI autofill, watch the running total, then submit for approval.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  Receipt, Car, PoundSterling, Plus, Trash2, Upload, Send, Loader2,
  ArrowLeft, CheckCircle2, AlertCircle, RotateCw, Camera, ArrowDownUp,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const gbp = (v) => '£' + Number(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const STATUS = {
  draft: { label: 'Draft', bg: 'rgba(100,116,139,0.15)', c: '#64748b' },
  submitted: { label: 'Awaiting manager', bg: 'rgba(245,158,11,0.15)', c: '#d97706' },
  approved: { label: 'Approved — awaiting payment', bg: 'rgba(6,182,212,0.15)', c: '#0891b2' },
  reimbursed: { label: 'Reimbursed', bg: 'rgba(16,185,129,0.15)', c: '#059669' },
  rejected: { label: 'Returned to you', bg: 'rgba(239,68,68,0.15)', c: '#dc2626' },
};

function Badge({ status }) {
  const s = STATUS[status] || STATUS.draft;
  return <span className="px-2.5 py-1 rounded-full text-xs font-semibold" style={{ background: s.bg, color: s.c }} data-testid="exp-status">{s.label}</span>;
}

function ReceiptThumb({ claimId, receiptId, H }) {
  const [url, setUrl] = useState('');
  const [bad, setBad] = useState(false);
  useEffect(() => {
    let active = true; let obj;
    axios.get(`${API}/new-starter/portal/expenses/${claimId}/receipt/${receiptId}`, { headers: H, responseType: 'blob' })
      .then((r) => { if (!active) return; obj = URL.createObjectURL(r.data); setUrl(obj); })
      .catch(() => setBad(true));
    return () => { active = false; if (obj) URL.revokeObjectURL(obj); };
  }, [claimId, receiptId, H]);
  if (bad || !url) return null;
  return (
    <a href={url} target="_blank" rel="noreferrer" data-testid={`exp-receipt-thumb-${receiptId}`} title="View receipt">
      <img src={url} alt="receipt" onError={() => setBad(true)}
        className="w-10 h-10 rounded-md object-cover border" style={{ borderColor: 'var(--theme-border)' }} />
    </a>
  );
}

export default function ExpensesTab({ H }) {
  const [cfg, setCfg] = useState(null);
  const [claims, setClaims] = useState([]);
  const [view, setView] = useState('list'); // list | edit
  const [claim, setClaim] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    try {
      const [c, l] = await Promise.all([
        axios.get(`${API}/new-starter/portal/expenses/config`, { headers: H }),
        axios.get(`${API}/new-starter/portal/expenses`, { headers: H }),
      ]);
      setCfg(c.data); setClaims(l.data.claims || []);
    } catch { setErr('Could not load expenses.'); }
  }, [H]);
  useEffect(() => { load(); }, [load]);

  const newClaim = async () => {
    setBusy(true); setErr('');
    try {
      const now = new Date();
      const r = await axios.post(`${API}/new-starter/portal/expenses`,
        { claim_month: MONTHS[now.getMonth()] + ' ' + now.getFullYear(), car_registration: '' }, { headers: H });
      const c = r.data;
      c.mileage = (cfg?.mileage_rates || []).map((m) => ({ key: m.key, label: m.label, rate: m.rate, miles: '', amount: 0 }));
      c.lines = [];
      setClaim(c); setView('edit');
    } catch { setErr('Could not start a claim.'); }
    finally { setBusy(false); }
  };

  const openClaim = async (id) => {
    setBusy(true); setErr('');
    try {
      const r = await axios.get(`${API}/new-starter/portal/expenses/${id}`, { headers: H });
      const c = r.data;
      // ensure all 5 rate rows present for editing
      const byKey = Object.fromEntries((c.mileage || []).map((m) => [m.key, m]));
      c.mileage = (cfg?.mileage_rates || []).map((m) => byKey[m.key] || { key: m.key, label: m.label, rate: m.rate, miles: '', amount: 0 });
      c.lines = c.lines || [];
      setClaim(c); setView('edit');
    } catch { setErr('Could not open that claim.'); }
    finally { setBusy(false); }
  };

  const editable = claim && (claim.status === 'draft' || claim.status === 'rejected');

  // ── running totals (client-side mirror of the backend) ──
  const mileageTotal = (claim?.mileage || []).reduce((s, m) => s + (Number(m.miles) || 0) * m.rate, 0);
  const linesTotal = (claim?.lines || []).reduce((s, l) => s + (Number(l.net) || 0) + (l.no_vat ? 0 : (Number(l.vat) || 0)), 0);
  const grand = mileageTotal + linesTotal;

  const setLine = (i, patch) => setClaim((c) => ({ ...c, lines: c.lines.map((l, j) => (j === i ? { ...l, ...patch, ...('_dup' in patch ? {} : { _dup: false }) } : l)) }));
  const addLine = () => setClaim((c) => ({ ...c, lines: [...(c.lines || []), { date: '', description: '', nominal: cfg?.nominals?.[0] || '', net: '', vat: '', no_vat: false, total: 0 }] }));
  const removeLine = (i) => setClaim((c) => ({ ...c, lines: c.lines.filter((_, j) => j !== i) }));
  const setMiles = (i, miles) => setClaim((c) => ({ ...c, mileage: c.mileage.map((m, j) => (j === i ? { ...m, miles } : m)) }));

  // Same receipt already on the claim? (same merchant + date + amount)
  const lineTotal = (l) => (Number(l.net) || 0) + (l.no_vat ? 0 : (Number(l.vat) || 0));
  const sameLine = (a, b) => {
    const am = (a.description || '').trim().toLowerCase(), bm = (b.description || '').trim().toLowerCase();
    const at = lineTotal(a), bt = lineTotal(b);
    return !!am && am === bm && !!a.date && (a.date || '') === (b.date || '') && at > 0 && Math.abs(at - bt) < 0.01;
  };

  // Oldest first; lines without a date sink to the bottom.
  const byDate = (a, b) => {
    const da = a.date || '', dbb = b.date || '';
    if (!da && !dbb) return 0;
    if (!da) return 1; if (!dbb) return -1;
    return da < dbb ? -1 : da > dbb ? 1 : 0;
  };
  const sortLinesByDate = () => setClaim((c) => ({ ...c, lines: [...(c.lines || [])].sort(byDate) }));

  const save = async () => {
    setBusy(true); setErr(''); setMsg('');
    try {
      const r = await axios.put(`${API}/new-starter/portal/expenses/${claim.id}`, {
        car_registration: claim.car_registration, claim_month: claim.claim_month, department: claim.department,
        mileage: claim.mileage.map((m) => ({ key: m.key, miles: Number(m.miles) || 0 })),
        lines: claim.lines.map((l) => ({ date: l.date, description: l.description, nominal: l.nominal, net: Number(l.net) || 0, vat: Number(l.vat) || 0, no_vat: !!l.no_vat, receipt_id: l.receipt_id })),
      }, { headers: H });
      const byKey = Object.fromEntries((r.data.mileage || []).map((m) => [m.key, m]));
      r.data.mileage = (cfg?.mileage_rates || []).map((m) => byKey[m.key] || { key: m.key, label: m.label, rate: m.rate, miles: '', amount: 0 });
      setClaim(r.data); setMsg('Saved'); setTimeout(() => setMsg(''), 1500);
      return true;
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not save.'); return false; }
    finally { setBusy(false); }
  };

  const submit = async () => {
    const ok = await save();
    if (!ok) return;
    setBusy(true); setErr('');
    try {
      await axios.post(`${API}/new-starter/portal/expenses/${claim.id}/submit`, {}, { headers: H });
      await load(); setView('list');
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not submit.'); }
    finally { setBusy(false); }
  };

  const uploadReceipt = async (i, file) => {
    if (!file) return;
    const fd = new FormData(); fd.append('file', file);
    setLine(i, { _uploading: true });
    try {
      const r = await axios.post(`${API}/new-starter/portal/expenses/${claim.id}/receipt`, fd, { headers: H });
      const s = r.data.suggestion || {};
      const filled = {
        date: s.date || claim.lines[i].date, description: s.description || claim.lines[i].description,
        net: s.net != null ? s.net : claim.lines[i].net, vat: s.vat != null ? s.vat : claim.lines[i].vat,
        no_vat: s.no_vat != null ? s.no_vat : claim.lines[i].no_vat,
      };
      const dup = (claim.lines || []).some((l, j) => j !== i && sameLine(filled, l));
      setLine(i, {
        receipt_id: r.data.receipt_id, _uploading: false,
        nominal: s.nominal || claim.lines[i].nominal, _dup: dup, ...filled,
      });
      if (dup) setErr('Heads up: this receipt looks like one already on your claim (same merchant, date & amount).');
      setTimeout(sortLinesByDate, 0);
    } catch { setLine(i, { _uploading: false }); setErr('Receipt upload failed.'); }
  };

  // Snap one or more receipts → each becomes a new, AI-filled line, then date-sorted.
  const snapNewReceipts = async (files) => {
    const list = Array.from(files || []);
    if (!list.length) return;
    setBusy(true); setErr(''); setMsg('');
    let added = 0, dups = 0;
    const working = [...(claim.lines || [])];
    for (const file of list) {
      try {
        const fd = new FormData(); fd.append('file', file);
        const r = await axios.post(`${API}/new-starter/portal/expenses/${claim.id}/receipt`, fd, { headers: H });
        const s = r.data.suggestion || {};
        const line = {
          date: s.date || '', description: s.description || '',
          nominal: s.nominal || cfg?.nominals?.[0] || '',
          net: s.net != null ? s.net : '', vat: s.vat != null ? s.vat : '',
          no_vat: s.no_vat != null ? s.no_vat : false, total: 0, receipt_id: r.data.receipt_id,
        };
        line._dup = working.some((l) => sameLine(line, l));
        if (line._dup) dups += 1;
        working.push(line);
        added += 1;
      } catch { /* skip this file, keep going */ }
    }
    setClaim((c) => ({ ...c, lines: [...working].sort(byDate) }));
    setBusy(false);
    if (dups) setErr(dups === 1
      ? 'Heads up: one receipt looks like a duplicate (same merchant, date & amount) — check the flagged line.'
      : `Heads up: ${dups} receipts look like duplicates — check the flagged lines.`);
    if (added) { setMsg(added === 1 ? 'Receipt added' : `${added} receipts added`); setTimeout(() => setMsg(''), 2500); }
    else if (!dups) setErr('Could not read those receipts — try adding a line manually.');
  };

  const inputCls = 'w-full px-2.5 py-2 rounded-lg text-sm';
  const inputStyle = { background: 'var(--theme-input-bg, #fff)', color: 'var(--theme-text)', border: '1px solid var(--theme-border)' };

  // ───────────────────────────── LIST VIEW
  if (view === 'list') {
    return (
      <div data-testid="staff-expenses">
        <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
          <div>
            <h2 className="text-lg font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>
              <Receipt size={18} className="inline mr-2" style={{ color: 'var(--color-brand-cyan)' }} />Expenses
            </h2>
            <p className="text-sm pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>Claim your mileage and expenses each month. We add it all up for you.</p>
          </div>
          <button data-testid="exp-new" onClick={newClaim} disabled={busy}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: busy ? 0.5 : 1 }}>
            {busy ? <RotateCw size={15} className="animate-spin" /> : <Plus size={15} />} New claim
          </button>
        </div>
        {err && <div className="mb-3 p-3 rounded-lg text-sm flex items-center gap-2" style={{ background: 'rgba(239,68,68,0.1)', color: '#dc2626' }}><AlertCircle size={15} />{err}</div>}
        {claims.length === 0 ? (
          <div className="p-8 text-center rounded-xl border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="exp-empty">
            No claims yet. Tap <strong>New claim</strong> to start your first one.
          </div>
        ) : (
          <div className="space-y-2">
            {claims.map((c) => (
              <button key={c.id} data-testid={`exp-claim-${c.id}`} onClick={() => openClaim(c.id)}
                className="w-full text-left p-4 rounded-xl border flex items-center justify-between gap-3 hover:-translate-y-0.5 transition-transform"
                style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
                <div>
                  <div className="font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{c.claim_month}</div>
                  <div className="text-xs pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>{gbp(c.grand_total)} · {c.department || '—'}</div>
                </div>
                <Badge status={c.status} />
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ───────────────────────────── EDIT VIEW
  if (!claim) return <div className="py-10 flex justify-center"><Loader2 className="animate-spin" size={26} style={{ color: 'var(--color-brand-cyan)' }} /></div>;
  return (
    <div data-testid="staff-expenses-edit">
      <button onClick={() => { setView('list'); load(); }} className="inline-flex items-center gap-1.5 text-sm font-medium mb-3" style={{ color: 'var(--theme-text-muted)' }} data-testid="exp-back">
        <ArrowLeft size={15} /> Back to my claims
      </button>

      <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <h2 className="text-lg font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>Expense claim</h2>
        <Badge status={claim.status} />
      </div>
      {claim.status === 'rejected' && claim.review_note && (
        <div className="mb-3 p-3 rounded-lg text-sm" style={{ background: 'rgba(239,68,68,0.1)', color: '#dc2626' }} data-testid="exp-reject-note">
          Returned by your manager: {claim.review_note}
        </div>
      )}

      {/* Header */}
      <div className="p-4 rounded-xl border mb-4" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <div className="grid sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-semibold block mb-1" style={{ color: 'var(--theme-text-muted)' }}>Name</label>
            <input value={claim.staff_name || cfg?.staff?.name || ''} disabled className={inputCls} style={{ ...inputStyle, opacity: 0.7 }} data-testid="exp-name" />
          </div>
          <div>
            <label className="text-xs font-semibold block mb-1" style={{ color: 'var(--theme-text-muted)' }}>Department</label>
            <select value={claim.department || ''} disabled={!editable} onChange={(e) => setClaim({ ...claim, department: e.target.value })} className={inputCls} style={inputStyle} data-testid="exp-department">
              <option value="">Choose…</option>
              {(cfg?.departments || []).map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold block mb-1" style={{ color: 'var(--theme-text-muted)' }}>Claim month</label>
            <input value={claim.claim_month || ''} disabled={!editable} onChange={(e) => setClaim({ ...claim, claim_month: e.target.value })} className={inputCls} style={inputStyle} data-testid="exp-month" />
          </div>
          <div>
            <label className="text-xs font-semibold block mb-1" style={{ color: 'var(--theme-text-muted)' }}><Car size={12} className="inline mr-1" />Car registration</label>
            <input value={claim.car_registration || ''} disabled={!editable} placeholder="e.g. AB12 CDE" onChange={(e) => setClaim({ ...claim, car_registration: e.target.value })} className={inputCls} style={inputStyle} data-testid="exp-car-reg" />
          </div>
        </div>
      </div>

      {/* Mileage */}
      <div className="p-4 rounded-xl border mb-4" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid="exp-mileage">
        <p className="font-bold pulse-font-heading mb-1" style={{ color: 'var(--theme-text)' }}>Mileage</p>
        <p className="text-xs pulse-font-body mb-3" style={{ color: 'var(--theme-text-muted)' }}>Enter the miles against the rate that applies to you — we work out the £.</p>
        <div className="space-y-2">
          {(claim.mileage || []).map((m, i) => (
            <div key={m.key} className="flex items-center gap-2 flex-wrap" data-testid={`exp-mileage-${m.key}`}>
              <div className="flex-1 min-w-[150px] text-sm" style={{ color: 'var(--theme-text)' }}>{m.label}
                <span className="text-xs ml-1" style={{ color: 'var(--theme-text-muted)' }}>({m.rate < 0 ? '−' : ''}£{Math.abs(m.rate).toFixed(3).replace(/0+$/, '').replace(/\.$/, '')}/mi)</span>
              </div>
              <input type="number" inputMode="decimal" value={m.miles} disabled={!editable} placeholder="miles"
                onChange={(e) => setMiles(i, e.target.value)} className="w-24 px-2.5 py-2 rounded-lg text-sm text-right" style={inputStyle} data-testid={`exp-miles-${m.key}`} />
              <div className="w-24 text-right text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>{gbp((Number(m.miles) || 0) * m.rate)}</div>
            </div>
          ))}
        </div>
        <div className="flex justify-end mt-3 pt-3 border-t text-sm font-bold" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}>
          Mileage total: <span className="ml-2" data-testid="exp-mileage-total">{gbp(mileageTotal)}</span>
        </div>
      </div>

      {/* Expense lines */}
      <div className="p-4 rounded-xl border mb-4" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid="exp-lines">
        <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
          <p className="font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>Expenses</p>
          {editable && (
            <div className="flex items-center gap-2 flex-wrap">
              <label data-testid="exp-snap-receipt" className="inline-flex items-center gap-1.5 text-sm font-semibold px-2.5 py-1.5 rounded-lg cursor-pointer" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: busy ? 0.5 : 1 }}>
                {busy ? <RotateCw size={13} className="animate-spin" /> : <Camera size={13} />} Snap receipt
                <input type="file" accept="image/*" capture="environment" multiple className="hidden" disabled={busy}
                  onChange={(e) => { snapNewReceipts(e.target.files); e.target.value = ''; }} />
              </label>
              <button data-testid="exp-sort-date" onClick={sortLinesByDate} className="inline-flex items-center gap-1.5 text-sm font-semibold px-2.5 py-1.5 rounded-lg" style={{ background: 'transparent', color: 'var(--theme-text)', border: '1px solid var(--theme-border)' }}>
                <ArrowDownUp size={13} /> Sort by date
              </button>
              <button data-testid="exp-add-line" onClick={addLine} className="inline-flex items-center gap-1.5 text-sm font-semibold px-2.5 py-1.5 rounded-lg" style={{ background: 'transparent', color: 'var(--theme-text)', border: '1px solid var(--theme-border)' }}><Plus size={13} /> Add manually</button>
            </div>
          )}
        </div>
        <p className="text-xs pulse-font-body mb-3" style={{ color: 'var(--theme-text-muted)' }}>Tap <strong>Snap receipt</strong> to photograph one or more receipts — we read the date, amount, VAT and category and add them in date order. Tick "No VAT on receipt" if there's no VAT shown.</p>
        {(claim.lines || []).length === 0 ? (
          <p className="text-sm py-3" style={{ color: 'var(--theme-text-muted)' }}>No expenses yet. {editable ? 'Tap "Snap receipt" to photograph one — we\'ll fill it in for you.' : ''}</p>
        ) : (
          <div className="space-y-3">
            {claim.lines.map((l, i) => (
              <div key={i} className="p-3 rounded-lg border" style={{ borderColor: l._dup ? '#f59e0b' : 'var(--theme-border)', background: l._dup ? 'rgba(245,158,11,0.06)' : 'transparent' }} data-testid={`exp-line-${i}`}>
                {l._dup && (
                  <div className="flex items-center gap-1.5 text-xs font-semibold mb-2" style={{ color: '#d97706' }} data-testid={`exp-line-dup-${i}`}>
                    <AlertCircle size={13} /> Possible duplicate — same merchant, date &amp; amount as another line. Remove it if it's the same receipt.
                  </div>
                )}
                <div className="grid sm:grid-cols-2 gap-2">
                  <input type="date" value={l.date || ''} disabled={!editable} onChange={(e) => setLine(i, { date: e.target.value })} className={inputCls} style={inputStyle} data-testid={`exp-line-date-${i}`} />
                  <select value={l.nominal || ''} disabled={!editable} onChange={(e) => setLine(i, { nominal: e.target.value })} className={inputCls} style={inputStyle} data-testid={`exp-line-nominal-${i}`}>
                    {(cfg?.nominals || []).map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <input value={l.description || ''} disabled={!editable} placeholder="Description (e.g. Specsavers — eye test)" onChange={(e) => setLine(i, { description: e.target.value })} className={`${inputCls} sm:col-span-2`} style={inputStyle} data-testid={`exp-line-desc-${i}`} />
                </div>
                <div className="flex items-end gap-2 mt-2 flex-wrap">
                  <div>
                    <label className="text-[11px] block" style={{ color: 'var(--theme-text-muted)' }}>Net £</label>
                    <input type="number" inputMode="decimal" value={l.net} disabled={!editable} onChange={(e) => setLine(i, { net: e.target.value })} className="w-24 px-2 py-1.5 rounded-lg text-sm text-right" style={inputStyle} data-testid={`exp-line-net-${i}`} />
                  </div>
                  <div>
                    <label className="text-[11px] block" style={{ color: 'var(--theme-text-muted)' }}>VAT £</label>
                    <input type="number" inputMode="decimal" value={l.no_vat ? '' : l.vat} disabled={!editable || l.no_vat} onChange={(e) => setLine(i, { vat: e.target.value })} className="w-24 px-2 py-1.5 rounded-lg text-sm text-right" style={{ ...inputStyle, opacity: l.no_vat ? 0.5 : 1 }} data-testid={`exp-line-vat-${i}`} />
                  </div>
                  <label className="flex items-center gap-1.5 text-xs pb-1.5" style={{ color: 'var(--theme-text-muted)' }}>
                    <input type="checkbox" checked={!!l.no_vat} disabled={!editable} onChange={(e) => setLine(i, { no_vat: e.target.checked })} data-testid={`exp-line-novat-${i}`} /> No VAT on receipt
                  </label>
                  <div className="ml-auto text-right">
                    <div className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>Line total</div>
                    <div className="text-sm font-bold" style={{ color: 'var(--theme-text)' }} data-testid={`exp-line-total-${i}`}>{gbp((Number(l.net) || 0) + (l.no_vat ? 0 : (Number(l.vat) || 0)))}</div>
                  </div>
                </div>
                {editable && (
                  <div className="flex items-center gap-3 mt-2">
                    {l.receipt_id && <ReceiptThumb claimId={claim.id} receiptId={l.receipt_id} H={H} />}
                    <label className="inline-flex items-center gap-1.5 text-xs font-medium cursor-pointer" style={{ color: 'var(--color-brand-cyan)' }} data-testid={`exp-line-receipt-${i}`}>
                      {l._uploading ? <RotateCw size={13} className="animate-spin" /> : <Upload size={13} />}
                      {l.receipt_id ? 'Replace receipt' : 'Add receipt photo'}
                      <input type="file" accept="image/*,.pdf" className="hidden" onChange={(e) => uploadReceipt(i, e.target.files?.[0])} />
                    </label>
                    <button onClick={() => removeLine(i)} className="ml-auto text-xs" style={{ color: '#dc2626' }} data-testid={`exp-line-remove-${i}`}><Trash2 size={13} className="inline" /> Remove</button>
                  </div>
                )}
                {!editable && l.receipt_id && (
                  <div className="flex items-center gap-2 mt-2">
                    <ReceiptThumb claimId={claim.id} receiptId={l.receipt_id} H={H} />
                    <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Receipt attached ✓</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Totals + actions */}
      <div className="p-4 rounded-xl border sticky bottom-2" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <div className="flex items-center justify-between mb-3">
          <span className="pulse-font-heading font-bold" style={{ color: 'var(--theme-text)' }}><PoundSterling size={16} className="inline mr-1" style={{ color: 'var(--color-brand-cyan)' }} />Total to claim</span>
          <span className="text-xl font-extrabold" style={{ color: 'var(--theme-text)' }} data-testid="exp-grand-total">{gbp(grand)}</span>
        </div>
        {err && <div className="mb-3 p-2.5 rounded-lg text-sm flex items-center gap-2" style={{ background: 'rgba(239,68,68,0.1)', color: '#dc2626' }} data-testid="exp-error"><AlertCircle size={15} />{err}</div>}
        {editable ? (
          <div className="flex items-center gap-2">
            <button onClick={save} disabled={busy} data-testid="exp-save" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold" style={{ background: 'transparent', color: 'var(--theme-text)', border: '1px solid var(--theme-border)', opacity: busy ? 0.5 : 1 }}>
              {busy ? <RotateCw size={15} className="animate-spin" /> : null} Save draft
            </button>
            <button onClick={submit} disabled={busy} data-testid="exp-submit" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', opacity: busy ? 0.5 : 1 }}>
              <Send size={15} /> Submit for approval
            </button>
            {msg && <span className="text-sm inline-flex items-center gap-1" style={{ color: '#059669' }} data-testid="exp-saved"><CheckCircle2 size={14} /> {msg}</span>}
          </div>
        ) : (
          <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>This claim has been submitted and is now read-only.</div>
        )}
      </div>
    </div>
  );
}
