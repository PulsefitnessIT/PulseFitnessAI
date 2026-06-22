/**
 * AdminMODSitesBulkImport — /admin/mod-sites/bulk-import
 *
 * Iter 216h138. Master-admin page to import 1000+ MOD sites in one
 * shot. Four-step flow:
 *   1. Download CSV template
 *   2. Upload filled CSV → preview (first 100 rows + counts)
 *   3. Confirm commit
 *   4. Download credentials CSV (username + auto-generated password
 *      per site) to distribute to base PTIs
 *
 * Backed by:
 *   GET  /api/master-admin/mod-sites/template.csv
 *   POST /api/master-admin/mod-sites/preview-csv     (multipart)
 *   POST /api/master-admin/mod-sites/bulk-import     (multipart)
 *   GET  /api/master-admin/mod-sites/bulk-import/{batch_id}/credentials.csv
 */
import { useCallback, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, FileUp, Download, ShieldCheck, AlertTriangle, Loader2,
  CheckCircle2, Upload, Crown, Building2, KeyRound, RotateCw,
  Mail, Send, Inbox,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

export default function AdminMODSitesBulkImport() {
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);     // { sites, count, would_create, would_skip, errors }
  const [committing, setCommitting] = useState(false);
  const [progress, setProgress] = useState(null);    // { processed, total_rows }
  const [previewing, setPreviewing] = useState(false);
  const [result, setResult] = useState(null);        // { batch_id, created, skipped, errors, credentials_csv_b64 }
  const [modRootId, setModRootId] = useState('mod-root-uk');
  // Iter 216h139 — Email dispatch state
  const [testOnlyEmail, setTestOnlyEmail] = useState('');
  const [emailSending, setEmailSending] = useState(false);
  const [delivery, setDelivery] = useState(null);    // { status, total, sent, failed, missing, receiptAvailable }

  const downloadTemplate = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/master-admin/mod-sites/template.csv`, {
        ...auth(), responseType: 'blob',
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'gymaxis-mod-sites-template.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      notify.error('Could not download template');
    }
  }, []);

  const onPickFile = (e) => {
    const f = e.target.files?.[0];
    setFile(f || null);
    setPreview(null);
    setResult(null);
  };

  const runPreview = useCallback(async () => {
    if (!file) return;
    setPreviewing(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await axios.post(`${API}/master-admin/mod-sites/preview-csv`, fd, {
        ...auth(),
        headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
      });
      setPreview(r.data);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Preview failed');
    } finally { setPreviewing(false); }
  }, [file]);

  const runCommit = useCallback(async () => {
    if (!file) return;
    setCommitting(true);
    setProgress(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      // Async flow: immediate {batch_id, status:"running"} then poll
      const r = await axios.post(
        `${API}/master-admin/mod-sites/bulk-import?mod_root_id=${encodeURIComponent(modRootId)}`,
        fd, {
          ...auth(),
          headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
          timeout: 60_000,
        },
      );
      const batchId = r.data.batch_id;
      if (!batchId) {
        notify.error('Bulk import did not return a batch id');
        setCommitting(false);
        return;
      }
      // Poll status every 2 s for up to 10 min
      let finalState = null;
      for (let i = 0; i < 300; i += 1) {
        await new Promise((res) => setTimeout(res, 2000));
        try {
          const s = await axios.get(
            `${API}/master-admin/mod-sites/bulk-import/${batchId}/status`, auth(),
          );
          setProgress({
            processed: s.data.processed,
            total_rows: s.data.total_rows,
            created:    s.data.created,
            skipped:    s.data.skipped,
          });
          if (s.data.status === 'done' || s.data.status === 'failed') {
            finalState = s.data;
            break;
          }
        } catch {
          // transient — keep polling
        }
      }
      if (finalState) {
        setResult(finalState);
        notify.success(`Imported ${finalState.created} sites (${finalState.skipped} skipped)`);
      } else {
        notify.error('Import is taking longer than expected — check back later');
      }
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Import failed');
    } finally { setCommitting(false); }
  }, [file, modRootId]);

  const downloadCredentials = useCallback(() => {
    if (!result?.credentials_csv_b64) return;
    const blob = new Blob([atob(result.credentials_csv_b64)], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `gymaxis-mod-credentials-${(result.batch_id || 'batch').slice(0, 8)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  // Iter 216h139 — Send credentials by email (background dispatcher)
  const sendCredentialsByEmail = useCallback(async () => {
    if (!result?.batch_id) return;
    if (!testOnlyEmail) {
      const ok = window.confirm(
        `Email credentials to all ${result.created} sites? `
        + 'Each base PTI gets their own login & password. '
        + 'Use the test field if you want to preview the email first.',
      );
      if (!ok) return;
    }
    setEmailSending(true);
    setDelivery(null);
    try {
      const r = await axios.post(
        `${API}/master-admin/mod-sites/bulk-import/${result.batch_id}/send-credentials`,
        { test_only_email: testOnlyEmail || null }, auth(),
      );
      const total = r.data.delivery_total;
      // Poll status every 2s
      let final = null;
      for (let i = 0; i < 300; i += 1) {
        await new Promise((res) => setTimeout(res, 2000));
        try {
          const s = await axios.get(
            `${API}/master-admin/mod-sites/bulk-import/${result.batch_id}/status`,
            auth(),
          );
          setDelivery({
            status:  s.data.delivery_status,
            total,
            sent:    s.data.delivery_sent || 0,
            failed:  s.data.delivery_failed || 0,
            missing: s.data.delivery_missing || 0,
            receiptAvailable: s.data.delivery_receipt_available,
          });
          if (s.data.delivery_status === 'done') {
            final = s.data;
            break;
          }
        } catch { /* keep polling */ }
      }
      if (final) {
        notify.success(`Emailed ${final.delivery_sent}/${total} sites`);
      } else {
        notify.error('Email dispatch is taking longer than expected');
      }
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Email dispatch failed');
    } finally {
      setEmailSending(false);
    }
  }, [result, testOnlyEmail]);

  const downloadDeliveryReceipt = useCallback(async () => {
    if (!result?.batch_id) return;
    try {
      const r = await axios.get(
        `${API}/master-admin/mod-sites/bulk-import/${result.batch_id}/delivery-receipt.csv`,
        { ...auth(), responseType: 'blob' },
      );
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `gymaxis-mod-delivery-${result.batch_id.slice(0, 8)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      notify.error('Could not download delivery receipt');
    }
  }, [result]);

  const reset = () => {
    setFile(null); setPreview(null); setResult(null);
    if (fileRef.current) fileRef.current.value = '';
  };

  const previewIssues = useMemo(() => preview?.errors?.length || 0, [preview]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="admin-mod-bulk-import-page">
      <header className="sticky top-0 z-10 bg-white/95 backdrop-blur border-b border-slate-200">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
          <button onClick={() => navigate('/master-admin')} className="p-2 rounded-full hover:bg-slate-100" aria-label="Back" data-testid="mod-bulk-back">
            <ArrowLeft size={18} />
          </button>
          <div className="flex-1">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
              Master admin · MOD onboarding
            </p>
            <h1 className="text-lg font-extrabold flex items-center gap-2">
              <Crown size={18} /> Bulk-import MOD sites (CSV)
            </h1>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6 space-y-5">
        {/* Hero */}
        <section className="rounded-2xl p-5 text-white shadow-md"
          style={{ background: 'linear-gradient(135deg, #1d4ed8 0%, #6366f1 60%, #8b5cf6 100%)' }}>
          <p className="text-[10px] uppercase tracking-[0.18em] font-bold opacity-90">Scales to 1000+ sites</p>
          <h2 className="text-2xl font-extrabold mt-1">One CSV. Every MOD facility.</h2>
          <p className="text-sm opacity-95 mt-1 max-w-2xl">
            Download the template, paste your estate, upload back. Each
            site is created with a username login and an auto-generated
            password — you download the credentials CSV at the end to
            distribute via your usual channels.
          </p>
        </section>

        {/* Step 1 — Template */}
        <Step n={1} label="Download the template">
          <div className="flex items-center gap-3 flex-wrap">
            <button
              type="button"
              onClick={downloadTemplate}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold"
              data-testid="mod-bulk-template-btn"
            >
              <Download size={14} /> Download template.csv
            </button>
            <p className="text-xs text-slate-500 max-w-md">
              Fill in <code className="font-mono">site_name</code>, <code className="font-mono">branch</code>,
              and at minimum a postcode per row. Leave <code className="font-mono">password</code> blank
              to auto-generate.
            </p>
          </div>
        </Step>

        {/* Step 2 — Upload */}
        <Step n={2} label="Upload your filled CSV">
          <div className="space-y-2">
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              onChange={onPickFile}
              className="hidden"
              data-testid="mod-bulk-file-input"
            />
            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white border border-slate-200 text-slate-700 text-sm font-bold hover:bg-slate-50"
                data-testid="mod-bulk-choose-file"
              >
                <Upload size={14} /> {file ? 'Choose another file' : 'Choose CSV file'}
              </button>
              {file && (
                <span className="text-xs text-slate-600" data-testid="mod-bulk-file-name">
                  {file.name} · {(file.size / 1024).toFixed(0)} KB
                </span>
              )}
              <div className="flex-1" />
              <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 flex items-center gap-2">
                <Building2 size={12} /> MOD root ID
              </label>
              <input
                type="text"
                value={modRootId}
                onChange={(e) => setModRootId(e.target.value)}
                className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white font-mono"
                placeholder="mod-root-uk"
                data-testid="mod-bulk-root-id"
              />
            </div>
            <button
              type="button"
              onClick={runPreview}
              disabled={!file || previewing}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-600 text-white text-sm font-bold disabled:opacity-50"
              data-testid="mod-bulk-preview-btn"
            >
              {previewing ? <Loader2 size={14} className="animate-spin" /> : <FileUp size={14} />}
              Preview rows
            </button>
          </div>
        </Step>

        {/* Step 3 — Preview */}
        {preview && (
          <Step n={3} label="Review &amp; commit">
            <div className="grid grid-cols-3 gap-3 mb-3" data-testid="mod-bulk-preview-stats">
              <Stat label="Rows parsed" value={preview.count} color="#1d4ed8" />
              <Stat label="Will create" value={preview.would_create} color="#059669" testid="mod-bulk-stat-create" />
              <Stat label="Will skip (exists)" value={preview.would_skip} color="#d97706" testid="mod-bulk-stat-skip" />
            </div>

            {previewIssues > 0 && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900 mb-3" data-testid="mod-bulk-errors">
                <p className="font-bold mb-1 flex items-center gap-1">
                  <AlertTriangle size={12} /> {previewIssues} validation issue(s)
                </p>
                <ul className="space-y-0.5 max-h-24 overflow-y-auto">
                  {preview.errors.slice(0, 12).map((e, i) => (
                    <li key={i}>Line {e.line}: {e.error}</li>
                  ))}
                </ul>
              </div>
            )}

            {preview.sites?.length ? (
              <div className="border border-slate-200 rounded-lg overflow-x-auto mb-3 max-h-72 overflow-y-auto" data-testid="mod-bulk-preview-table">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 sticky top-0 z-[1]">
                    <tr className="text-left text-[10px] uppercase font-bold tracking-wide text-slate-500">
                      <th className="px-3 py-1.5">Site code</th>
                      <th className="px-3 py-1.5">Name</th>
                      <th className="px-3 py-1.5">Branch</th>
                      <th className="px-3 py-1.5">Postcode</th>
                      <th className="px-3 py-1.5">State</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {preview.sites.map((s, i) => (
                      <tr key={s.site_code || i} data-testid={`mod-bulk-row-${s.site_code}`}>
                        <td className="px-3 py-1.5 font-mono text-slate-700">{s.site_code}</td>
                        <td className="px-3 py-1.5">{s.site_name}</td>
                        <td className="px-3 py-1.5">{s.branch}</td>
                        <td className="px-3 py-1.5 font-mono">{s.postcode}</td>
                        <td className="px-3 py-1.5">
                          {s.already_exists ? (
                            <span className="text-amber-700 font-bold">skip · exists</span>
                          ) : (
                            <span className="text-emerald-700 font-bold">create</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {preview.count > preview.sites.length && (
                  <p className="px-3 py-1.5 text-[11px] text-slate-500 bg-slate-50 border-t border-slate-200">
                    Showing first {preview.sites.length} of {preview.count} rows
                  </p>
                )}
              </div>
            ) : null}

            <div className="flex gap-2 flex-wrap">
              <button
                type="button"
                onClick={runCommit}
                disabled={committing || preview.would_create === 0}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-emerald-600 text-white text-sm font-bold disabled:opacity-50 hover:bg-emerald-700"
                data-testid="mod-bulk-commit-btn"
              >
                {committing
                  ? <><Loader2 size={14} className="animate-spin" />
                      {progress
                        ? `Importing… ${progress.processed}/${progress.total_rows}`
                        : 'Committing…'}
                    </>
                  : <><ShieldCheck size={14} /> Commit · create {preview.would_create} site(s)</>}
              </button>
              <button
                type="button"
                onClick={reset}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white border border-slate-200 text-slate-700 text-sm font-bold"
                data-testid="mod-bulk-reset-btn"
              >
                <RotateCw size={14} /> Start over
              </button>
            </div>
          </Step>
        )}

        {/* Step 4 — Result */}
        {result && (
          <Step n={4} label="Distribute credentials">
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 mb-3" data-testid="mod-bulk-result">
              <div className="flex items-center gap-3">
                <CheckCircle2 size={22} className="text-emerald-600" />
                <div className="flex-1">
                  <p className="text-base font-extrabold text-emerald-900">
                    Imported {result.created} site(s)
                  </p>
                  <p className="text-xs text-emerald-800">
                    {result.skipped > 0 ? `${result.skipped} skipped (site_code already exists). ` : ''}
                    {result.errors?.length > 0 ? `${result.errors.length} error(s) — see below.` : 'No errors.'}
                  </p>
                </div>
              </div>
            </div>

            {result.errors?.length > 0 && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900 mb-3">
                <p className="font-bold mb-1">Errors</p>
                <ul className="space-y-0.5 max-h-24 overflow-y-auto">
                  {result.errors.map((e, i) => (
                    <li key={i}>Line {e.line || '-'}: {e.error}</li>
                  ))}
                </ul>
              </div>
            )}

            {result.credentials_csv_b64 && (
              <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 mb-3">
                <p className="text-[11px] uppercase font-bold tracking-wide text-blue-700 mb-1 flex items-center gap-1">
                  <KeyRound size={12} /> Option A — Download CSV
                </p>
                <p className="text-xs text-blue-900 mb-3">
                  Distribute the credentials yourself via your secure channel
                  (DEFCONN, MS Teams, etc.). Each base PTI logs in at
                  <code className="bg-white px-1 mx-1 rounded">https://pulsefitness.ai/login</code>
                  with their <code>site_code</code> + password.
                </p>
                <button
                  type="button"
                  onClick={downloadCredentials}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-600 text-white text-sm font-bold"
                  data-testid="mod-bulk-download-credentials-btn"
                >
                  <Download size={14} /> Download credentials.csv
                </button>
              </div>
            )}

            {/* Iter 216h139 — Email dispatcher */}
            {result.credentials_csv_b64 && (
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4" data-testid="mod-bulk-email-card">
                <p className="text-[11px] uppercase font-bold tracking-wide text-emerald-700 mb-1 flex items-center gap-1">
                  <Mail size={12} /> Option B — Email each base direct
                </p>
                <p className="text-xs text-emerald-900 mb-3">
                  Pulse Fitness emails each site's <code>site_manager_email</code> their
                  individual login + password via Resend. Then download the
                  per-recipient delivery receipt for your audit trail —
                  no manual CSV distribution required.
                </p>
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <label className="text-[11px] uppercase font-bold tracking-wide text-emerald-700 flex items-center gap-2">
                    <Inbox size={12} /> Test send to (optional):
                  </label>
                  <input
                    type="email"
                    placeholder="you@pulsefitness.ai"
                    value={testOnlyEmail}
                    onChange={(e) => setTestOnlyEmail(e.target.value)}
                    className="text-sm border border-emerald-200 rounded-lg px-3 py-1.5 bg-white"
                    data-testid="mod-bulk-test-email-input"
                  />
                  <span className="text-[11px] text-emerald-700">
                    {testOnlyEmail
                      ? 'Will email ONLY this address as a render preview.'
                      : `Will email all ${result.created} bases.`}
                  </span>
                </div>

                {delivery && (
                  <div className="bg-white rounded-lg border border-emerald-200 p-3 mb-3 grid grid-cols-3 gap-3" data-testid="mod-bulk-delivery-stats">
                    <Stat label="Sent"    value={delivery.sent}    color="#059669" testid="mod-bulk-delivery-sent" />
                    <Stat label="Failed"  value={delivery.failed}  color="#dc2626" testid="mod-bulk-delivery-failed" />
                    <Stat label="Missing" value={delivery.missing} color="#d97706" testid="mod-bulk-delivery-missing" />
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={sendCredentialsByEmail}
                    disabled={emailSending}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-600 text-white text-sm font-bold disabled:opacity-50 hover:bg-emerald-700"
                    data-testid="mod-bulk-send-email-btn"
                  >
                    {emailSending
                      ? <><Loader2 size={14} className="animate-spin" />
                          {delivery
                            ? `Sending… ${delivery.sent + delivery.failed + delivery.missing}/${delivery.total}`
                            : 'Sending…'}
                        </>
                      : <><Send size={14} />
                          {testOnlyEmail ? 'Send test email' : `Email all ${result.created} bases`}
                        </>}
                  </button>
                  {delivery?.receiptAvailable && (
                    <button
                      type="button"
                      onClick={downloadDeliveryReceipt}
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white border border-emerald-200 text-emerald-700 text-sm font-bold hover:bg-emerald-100"
                      data-testid="mod-bulk-delivery-receipt-btn"
                    >
                      <Download size={14} /> Download delivery receipt
                    </button>
                  )}
                </div>
              </div>
            )}
          </Step>
        )}
      </main>
    </div>
  );
}

const Step = ({ n, label, children }) => (
  <section className="rounded-2xl border border-slate-200 bg-white p-5">
    <p className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500 mb-3 flex items-center gap-2">
      <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-blue-100 text-blue-700 font-extrabold">{n}</span>
      Step {n} · {label}
    </p>
    {children}
  </section>
);

const Stat = ({ label, value, color, testid }) => (
  <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 text-center" data-testid={testid}>
    <p className="text-[10px] uppercase font-bold tracking-wide text-slate-500">{label}</p>
    <p className="text-xl font-extrabold tabular-nums mt-0.5" style={{ color }}>{value}</p>
  </div>
);
