/**
 * Master Admin — MOD bulk-import panel (Iter 216h117).
 *
 * Closes the P1 backlog item: a single CSV upload provisions thousands
 * of MOD sites under a parent HQ / branch, mints their shared kiosk
 * logins, and optionally emails credentials to each site's nominated
 * primary contact.
 *
 * Endpoints:
 *   GET  /api/master-admin/mod/bulk-import/template
 *   POST /api/master-admin/mod/bulk-import?parent_org_id=...&notify=true
 *   GET  /api/master-admin/mod/bulk-import/export-credentials?import_id=...
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
  Download, Upload, Loader2, CheckCircle2, AlertCircle, FileSpreadsheet,
  ShieldCheck, Mail, KeyRound, Copy,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { notify } from '@/components/notifications';

const API_BASE = process.env.REACT_APP_BACKEND_URL + '/api';

const downloadTemplate = async (token) => {
  const r = await fetch(`${API_BASE}/master-admin/mod/bulk-import/template`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error(`Template fetch failed: ${r.status}`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'mod_sites_template.csv';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

const MODBulkImport = ({ API }) => {
  const token = localStorage.getItem('token');
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [orgs, setOrgs] = useState([]);
  const [parentId, setParentId] = useState('');
  const [notifyOpt, setNotifyOpt] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const fileInput = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        // The master-admin/organizations endpoint returns ALL orgs
        // including MOD HQ + branch tiers, which pulse-organizations
        // doesn't surface. Filter client-side to mod_org / mod_branch.
        const { data } = await axios.get(
          `${API}/master-admin/organizations`,
          { headers },
        );
        const list = (data?.organizations || []).filter(
          (o) => o.account_type === 'mod_org' || o.account_type === 'mod_branch',
        );
        setOrgs(list);
      } catch (e) {
        // Silent — admin can still type an org ID manually if needed.
      }
    })();
  }, [API, headers]);

  const onPick = () => fileInput.current?.click();

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (!parentId) {
      notify.error('Pick a parent MOD HQ / branch first');
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await axios.post(
        `${API}/master-admin/mod/bulk-import?parent_org_id=${encodeURIComponent(parentId)}&notify=${notifyOpt}`,
        fd,
        { headers: { ...headers, 'Content-Type': 'multipart/form-data' } },
      );
      setResult(data);
      notify.success(
        `Imported ${data.imported} MOD sites`,
        data.skipped ? `${data.skipped} skipped — see errors below.` : 'All rows accepted.',
      );
    } catch (err) {
      notify.error('Import failed', err?.response?.data?.detail || 'Server error');
    } finally {
      setBusy(false);
    }
  };

  const downloadCredentials = async () => {
    if (!result?.import_id) return;
    try {
      const r = await fetch(
        `${API}/master-admin/mod/bulk-import/export-credentials?import_id=${encodeURIComponent(result.import_id)}`,
        { headers },
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `mod_sites_credentials_${result.import_id.slice(0, 8)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      notify.success('Credentials CSV downloaded');
    } catch (e) {
      notify.error('Download failed', e.message);
    }
  };

  return (
    <div className="space-y-5" data-testid="mod-bulk-import">
      <Card className="p-5 rounded-xl border-zinc-200">
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck size={18} className="text-cyan-600" />
          <h3 className="text-base font-extrabold tracking-tight">MOD — bulk site provisioning</h3>
        </div>
        <p className="text-xs text-zinc-600 leading-relaxed">
          Provision dozens or thousands of MOD child sites in one upload.
          The endpoint creates the <code>mod_site</code> orgs under the
          chosen parent HQ / branch, mints a shared kiosk login per site,
          and (optionally) emails each row's credentials to its
          <code> primary_contact_email</code>. The plaintext credentials
          can be downloaded as a CSV for the next 10 minutes after the
          import completes.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <div>
            <Label className="text-xs font-bold text-zinc-700">Parent MOD organisation</Label>
            <Select value={parentId} onValueChange={setParentId}>
              <SelectTrigger className="mt-1" data-testid="mod-bulk-parent-select">
                <SelectValue placeholder="Pick a MOD HQ or branch…" />
              </SelectTrigger>
              <SelectContent>
                {orgs.map((o) => (
                  <SelectItem key={o.id} value={o.id} data-testid={`mod-bulk-parent-${o.id}`}>
                    {o.name} · {o.account_type === 'mod_org' ? 'HQ' : 'Branch'}
                  </SelectItem>
                ))}
                {orgs.length === 0 ? (
                  <SelectItem value="__empty__" disabled>
                    No MOD orgs yet — seed via Master Admin → MOD console.
                  </SelectItem>
                ) : null}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-zinc-500 mt-1">
              HQ tier accepts a CSV spanning multiple branches. Branch tier
              forces every imported site into the parent's branch.
            </p>
          </div>

          <div>
            <Label className="text-xs font-bold text-zinc-700">Email credentials on import?</Label>
            <div className="mt-2 flex items-center gap-2">
              <input
                type="checkbox"
                checked={notifyOpt}
                onChange={(e) => setNotifyOpt(e.target.checked)}
                id="mod-bulk-notify"
                data-testid="mod-bulk-notify"
                className="h-4 w-4"
              />
              <label htmlFor="mod-bulk-notify" className="text-sm text-zinc-700 inline-flex items-center gap-1">
                <Mail size={13} className="text-zinc-500" />
                Email each row's <code className="text-[11px]">primary_contact_email</code> with their credentials
              </label>
            </div>
            <p className="text-[11px] text-zinc-500 mt-1">
              Rows without a contact email are still provisioned — credentials
              live only on the downloadable CSV.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mt-5 items-center">
          <Button
            variant="outline"
            onClick={() => downloadTemplate(token).catch((e) => notify.error('Template error', e.message))}
            data-testid="mod-bulk-template-btn"
          >
            <Download size={14} className="mr-1.5" /> Download template
          </Button>
          <Button
            onClick={onPick}
            disabled={!parentId || busy}
            data-testid="mod-bulk-upload-btn"
          >
            {busy ? <Loader2 size={14} className="animate-spin mr-1.5" /> : <Upload size={14} className="mr-1.5" />}
            {busy ? 'Provisioning…' : 'Upload CSV'}
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={onFile}
            data-testid="mod-bulk-file-input"
          />
        </div>
      </Card>

      {result && (
        <Card className="p-5 rounded-xl border-zinc-200" data-testid="mod-bulk-result-card">
          <div className="flex items-center justify-between gap-2 mb-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={16} className="text-emerald-600" />
              <h4 className="text-sm font-extrabold">Import complete</h4>
              <span className="text-[10px] uppercase tracking-wider bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded font-bold">
                {result.imported} provisioned
              </span>
              {result.skipped ? (
                <span className="text-[10px] uppercase tracking-wider bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-bold" data-testid="mod-bulk-skipped">
                  {result.skipped} skipped
                </span>
              ) : null}
            </div>
            <Button
              variant="outline"
              onClick={downloadCredentials}
              data-testid="mod-bulk-export-credentials"
            >
              <Download size={13} className="mr-1.5" /> Credentials CSV
            </Button>
          </div>

          {(result.errors || []).length > 0 && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs mb-3" data-testid="mod-bulk-errors">
              <div className="flex items-center gap-1.5 font-bold text-amber-900 mb-1">
                <AlertCircle size={13} /> {result.error_count} row issue{result.error_count === 1 ? '' : 's'}
              </div>
              <ul className="list-disc pl-5 space-y-0.5 text-amber-900/80">
                {result.errors.slice(0, 12).map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
                {result.errors.length > 12 ? (
                  <li>… and {result.errors.length - 12} more</li>
                ) : null}
              </ul>
            </div>
          )}

          <div className="overflow-x-auto -mx-2">
            <table className="w-full text-xs" data-testid="mod-bulk-credentials-table">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-zinc-500 border-b border-zinc-200">
                  <th className="px-2 py-2">Site</th>
                  <th className="px-2 py-2">Username</th>
                  <th className="px-2 py-2">Password</th>
                  <th className="px-2 py-2">Notified</th>
                </tr>
              </thead>
              <tbody>
                {(result.credentials || []).map((c) => (
                  <tr key={c.username} className="border-b border-zinc-100">
                    <td className="px-2 py-2 font-semibold">{c.site_name}</td>
                    <td className="px-2 py-2 font-mono text-zinc-700">{c.username}</td>
                    <td className="px-2 py-2">
                      <button
                        type="button"
                        className="font-mono inline-flex items-center gap-1 text-zinc-700 hover:text-zinc-900"
                        onClick={() => {
                          navigator.clipboard.writeText(c.password);
                          notify.success('Password copied');
                        }}
                        data-testid={`mod-bulk-copy-${c.username}`}
                        title="Copy password"
                      >
                        <Copy size={11} /> {c.password}
                      </button>
                    </td>
                    <td className="px-2 py-2">
                      {c.notified
                        ? <span className="text-emerald-700 font-bold">yes</span>
                        : <span className="text-zinc-400">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-[11px] text-zinc-500 mt-3 flex items-center gap-1">
            <KeyRound size={11} /> {result.note}
          </p>
        </Card>
      )}

      <Card className="p-5 rounded-xl border-zinc-200 bg-zinc-50">
        <div className="flex items-center gap-2 mb-2">
          <FileSpreadsheet size={14} className="text-zinc-500" />
          <h4 className="text-sm font-bold text-zinc-800">Required CSV columns</h4>
        </div>
        <ul className="text-[12px] text-zinc-600 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
          <li><code>site_name</code> — display name (required)</li>
          <li><code>mod_branch</code> — branch grouping (required when parent is a mod_org)</li>
          <li><code>mod_force</code> — army / raf / navy</li>
          <li><code>postcode</code> — UK postcode</li>
          <li><code>primary_contact_email</code> — destination for credentials</li>
          <li><code>address</code> — free-text full address</li>
          <li><code>site_code</code> — optional username slug</li>
          <li><code>primary_contact_name</code> — optional, used in email</li>
        </ul>
      </Card>
    </div>
  );
};

export default MODBulkImport;
