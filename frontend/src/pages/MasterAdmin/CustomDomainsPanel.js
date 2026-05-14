/**
 * Custom Domains Panel — Master Admin → Settings & Compliance
 * (Iter 216h111).
 *
 * Lets a Master Admin configure custom tenant hostnames (e.g.
 *   join.acmegym.com  →  /m/{slug}/join
 *   app.acmegym.com   →  /m/{slug}
 *
 * Visitors landing on a verified custom host get auto-redirected to
 * the configured route by the SPA host-detector mounted in App.js.
 *
 * Per-org workflow:
 *   1. Pick an org from the dropdown.
 *   2. "Add domain" → enter hostname + pick primary route.
 *      Panel surfaces the CNAME + TXT records to configure at the
 *      customer's DNS host.
 *   3. Once the customer's DNS resolves, "Verify" runs the TXT
 *      lookup and flips the record to live.
 *   4. The platform master admin (not Pulse-delegated) can also
 *      "Force-verify" — used for staging hostnames where public
 *      DNS won't be configured.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Globe, ShieldCheck, AlertTriangle, RefreshCw, Trash2, Plus,
  Copy, ExternalLink, Building2, Link as LinkIcon, Loader2, Sparkles,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function authHeaders() {
  const token = localStorage.getItem('token') || '';
  return { Authorization: `Bearer ${token}` };
}

function timeAgo(iso) {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (!t) return '—';
  const diff = Math.max(0, (Date.now() - t) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return `${Math.floor(diff / 86400)} d ago`;
}

const CustomDomainsPanel = () => {
  const [orgs, setOrgs] = useState([]);
  const [orgsLoading, setOrgsLoading] = useState(true);
  const [orgFilter, setOrgFilter] = useState('');
  const [selectedOrgId, setSelectedOrgId] = useState('');

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  // Add-domain form state
  const [newHostname, setNewHostname] = useState('');
  const [newRoute, setNewRoute] = useState('join');
  const [creating, setCreating] = useState(false);

  // Per-row action state
  const [busyId, setBusyId] = useState(null);

  // ── Load orgs ─────────────────────────────────────────────────
  const loadOrgs = useCallback(async () => {
    setOrgsLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/organizations`, { headers: authHeaders() });
      const raw = Array.isArray(r.data) ? r.data : (r.data?.organizations || []);
      // Filter to orgs that can plausibly host a public member-app
      // surface — pulse-pro, lite, gymaxis. MOD orgs are excluded.
      const eligible = raw.filter((o) => {
        const at = (o.account_type || '').toLowerCase();
        if (!at || at.startsWith('mod') || at === 'platform') return false;
        // Skip orgs without a real name — they're typically transient
        // sign-up / test stubs that have no public surface to brand.
        if (!o.name) return false;
        return true;
      });
      eligible.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
      setOrgs(eligible);
      if (!selectedOrgId && eligible[0]) setSelectedOrgId(eligible[0].id);
    } catch (e) {
      toast.error('Could not load organisations');
    } finally {
      setOrgsLoading(false);
    }
  }, [selectedOrgId]);

  useEffect(() => { loadOrgs(); /* eslint-disable-next-line */ }, []);

  // ── Load this org's domains ──────────────────────────────────
  const loadDomains = useCallback(async (orgId) => {
    if (!orgId) return;
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/master-admin/custom-domains/orgs/${orgId}`,
        { headers: authHeaders() },
      );
      setData(r.data);
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Failed to load custom domains';
      toast.error(typeof msg === 'string' ? msg : 'Failed to load custom domains');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedOrgId) loadDomains(selectedOrgId);
  }, [selectedOrgId, loadDomains]);

  // ── Mutations ────────────────────────────────────────────────
  const submitNew = async (e) => {
    e?.preventDefault?.();
    if (!selectedOrgId || !newHostname.trim()) {
      toast.error('Enter a hostname');
      return;
    }
    setCreating(true);
    try {
      await axios.post(
        `${API}/master-admin/custom-domains/orgs/${selectedOrgId}`,
        { hostname: newHostname.trim(), primary_route: newRoute },
        { headers: authHeaders() },
      );
      toast.success(`Added ${newHostname.trim()}`);
      setNewHostname('');
      setNewRoute('join');
      loadDomains(selectedOrgId);
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Failed to add domain';
      toast.error(typeof msg === 'string' ? msg : 'Failed to add domain');
    } finally {
      setCreating(false);
    }
  };

  const handleVerify = async (domainId) => {
    setBusyId(domainId);
    try {
      const r = await axios.post(
        `${API}/master-admin/custom-domains/orgs/${selectedOrgId}/${domainId}/verify`,
        {},
        { headers: authHeaders() },
      );
      if (r.data?.verified) {
        toast.success('Domain verified — live now');
      } else {
        toast.warning(r.data?.message || 'TXT record not detected yet');
      }
      loadDomains(selectedOrgId);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Verification failed');
    } finally {
      setBusyId(null);
    }
  };

  const handleForceVerify = async (domainId) => {
    if (!window.confirm('Force-verify this domain WITHOUT a DNS lookup? Only use this for demo / staging hostnames.')) return;
    setBusyId(domainId);
    try {
      await axios.post(
        `${API}/master-admin/custom-domains/orgs/${selectedOrgId}/${domainId}/force-verify`,
        {},
        { headers: authHeaders() },
      );
      toast.success('Force-verified');
      loadDomains(selectedOrgId);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Force-verify failed');
    } finally {
      setBusyId(null);
    }
  };

  const handleRouteChange = async (domainId, route) => {
    setBusyId(domainId);
    try {
      await axios.patch(
        `${API}/master-admin/custom-domains/orgs/${selectedOrgId}/${domainId}`,
        { primary_route: route },
        { headers: authHeaders() },
      );
      toast.success('Route updated');
      loadDomains(selectedOrgId);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not update route');
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (domainId, hostname) => {
    if (!window.confirm(`Remove ${hostname}? Visitors hitting this hostname will fall back to the default platform experience.`)) return;
    setBusyId(domainId);
    try {
      await axios.delete(
        `${API}/master-admin/custom-domains/orgs/${selectedOrgId}/${domainId}`,
        { headers: authHeaders() },
      );
      toast.success('Domain removed');
      loadDomains(selectedOrgId);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not delete domain');
    } finally {
      setBusyId(null);
    }
  };

  const copyToClipboard = (value, label = 'Value') => {
    try {
      navigator.clipboard?.writeText(value);
      toast.success(`${label} copied`);
    } catch {
      toast.error('Could not copy');
    }
  };

  const filteredOrgs = useMemo(() => {
    const q = orgFilter.trim().toLowerCase();
    if (!q) return orgs;
    return orgs.filter((o) =>
      (o.name || '').toLowerCase().includes(q)
      || (o.slug || '').toLowerCase().includes(q),
    );
  }, [orgFilter, orgs]);

  const selectedOrg = orgs.find((o) => o.id === selectedOrgId);

  return (
    <div className="space-y-6" data-testid="custom-domains-panel">
      {/* Header */}
      <div className="rounded-2xl border border-zinc-800 bg-gradient-to-br from-zinc-900 to-zinc-950 p-6">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center shrink-0">
            <Globe className="w-6 h-6 text-cyan-400" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-xl font-bold text-white">Custom domains</h2>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 rounded-full px-2 py-0.5">
                P1
              </span>
            </div>
            <p className="text-sm text-zinc-400 leading-relaxed">
              Point a customer's own domain (e.g. <code className="px-1.5 py-0.5 rounded bg-zinc-800 text-cyan-200 text-xs">join.acmegym.com</code>) at a specific tenant surface — sign-up, member app, brag page or public timetable.
              Each domain must be verified via a TXT record before it starts serving traffic.
            </p>
          </div>
        </div>
      </div>

      {/* Org selector */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
        <div className="flex items-center gap-3 mb-3">
          <Building2 className="w-4 h-4 text-zinc-400" />
          <label className="text-sm font-semibold text-zinc-200">Choose organisation</label>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            type="text"
            value={orgFilter}
            onChange={(e) => setOrgFilter(e.target.value)}
            placeholder="Search org name or slug…"
            className="md:col-span-1 bg-zinc-950 border border-zinc-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
            data-testid="cd-org-search"
          />
          <select
            value={selectedOrgId}
            onChange={(e) => setSelectedOrgId(e.target.value)}
            disabled={orgsLoading}
            className="md:col-span-2 bg-zinc-950 border border-zinc-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
            data-testid="cd-org-select"
          >
            {orgsLoading && <option value="">Loading…</option>}
            {!orgsLoading && filteredOrgs.length === 0 && <option value="">No orgs match</option>}
            {!orgsLoading && filteredOrgs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name || '(unnamed)'} {o.account_type ? `· ${o.account_type}` : ''}
              </option>
            ))}
          </select>
        </div>
        {selectedOrg && (
          <p className="text-xs text-zinc-500 mt-2">
            Public member surfaces resolve under <code className="px-1 py-0.5 rounded bg-zinc-800 text-cyan-300">/m/{data?.org_slug || selectedOrg.slug || selectedOrg.id}</code>
          </p>
        )}
      </div>

      {/* Add domain form */}
      <form
        onSubmit={submitNew}
        className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5"
        data-testid="cd-add-form"
      >
        <div className="flex items-center gap-2 mb-3">
          <Plus className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-white">Add a custom domain</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
          <div className="md:col-span-6">
            <label className="block text-[11px] uppercase tracking-wider text-zinc-500 mb-1">Hostname</label>
            <input
              type="text"
              value={newHostname}
              onChange={(e) => setNewHostname(e.target.value)}
              placeholder="join.acmegym.com"
              className="w-full bg-zinc-950 border border-zinc-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
              data-testid="cd-new-hostname"
              required
            />
            <p className="text-[11px] text-zinc-500 mt-1">Lowercase FQDN. Subdomains of platform-owned hosts (gymaxisai.com / pulsefitness.ai) are blocked.</p>
          </div>
          <div className="md:col-span-4">
            <label className="block text-[11px] uppercase tracking-wider text-zinc-500 mb-1">Primary route</label>
            <select
              value={newRoute}
              onChange={(e) => setNewRoute(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
              data-testid="cd-new-route"
            >
              {(data?.allowed_routes || []).map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2 flex items-end">
            <button
              type="submit"
              disabled={creating || !selectedOrgId}
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed text-zinc-950 font-semibold text-sm"
              data-testid="cd-submit"
            >
              {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              {creating ? 'Adding…' : 'Add'}
            </button>
          </div>
        </div>
      </form>

      {/* Domain list */}
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 overflow-hidden">
        <div className="px-5 py-3 border-b border-zinc-800 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <LinkIcon className="w-4 h-4 text-zinc-400" />
            Configured domains{data ? ` (${(data.domains || []).length})` : ''}
          </h3>
          {selectedOrgId && (
            <button
              type="button"
              onClick={() => loadDomains(selectedOrgId)}
              className="text-xs text-zinc-400 hover:text-white inline-flex items-center gap-1"
              data-testid="cd-refresh"
            >
              <RefreshCw className="w-3 h-3" /> Refresh
            </button>
          )}
        </div>

        {loading && (
          <div className="px-5 py-12 text-center text-sm text-zinc-500">
            <Loader2 className="w-5 h-5 animate-spin inline-block mr-2" /> Loading…
          </div>
        )}

        {!loading && data && (data.domains || []).length === 0 && (
          <div className="px-5 py-12 text-center" data-testid="cd-empty">
            <Sparkles className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
            <p className="text-sm text-zinc-400">No custom domains for this organisation yet.</p>
            <p className="text-xs text-zinc-600 mt-1">Add one above to white-label their sign-up funnel.</p>
          </div>
        )}

        {!loading && data && (data.domains || []).map((d) => (
          <div key={d.id} className="px-5 py-4 border-t border-zinc-800/80" data-testid={`cd-row-${d.id}`}>
            <div className="flex items-start justify-between gap-4 flex-wrap">
              {/* Hostname + status */}
              <div className="flex items-start gap-3 min-w-0 flex-1">
                <div className={`w-10 h-10 rounded-lg shrink-0 flex items-center justify-center ${d.verified ? 'bg-emerald-500/10 border border-emerald-500/30' : 'bg-amber-500/10 border border-amber-500/30'}`}>
                  {d.verified ? <ShieldCheck className="w-5 h-5 text-emerald-400" /> : <AlertTriangle className="w-5 h-5 text-amber-400" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <code className="text-sm font-semibold text-white break-all" data-testid={`cd-host-${d.id}`}>{d.hostname}</code>
                    {d.verified ? (
                      <span className="text-[10px] uppercase tracking-wider font-bold text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-full px-2 py-0.5">Verified · live</span>
                    ) : (
                      <span className="text-[10px] uppercase tracking-wider font-bold text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-full px-2 py-0.5">Awaiting DNS</span>
                    )}
                  </div>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    {d.primary_route_label}
                  </p>
                  <p className="text-[11px] text-zinc-600 mt-0.5">
                    Added {timeAgo(d.created_at)}{d.verified_at ? ` · verified ${timeAgo(d.verified_at)}` : ''}
                  </p>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 flex-wrap">
                <select
                  value={d.primary_route}
                  onChange={(e) => handleRouteChange(d.id, e.target.value)}
                  disabled={busyId === d.id}
                  className="bg-zinc-950 border border-zinc-700 text-white rounded-md px-2 py-1.5 text-xs"
                  data-testid={`cd-route-${d.id}`}
                >
                  {(data.allowed_routes || []).map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
                {!d.verified && (
                  <button
                    type="button"
                    onClick={() => handleVerify(d.id)}
                    disabled={busyId === d.id}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-semibold hover:bg-emerald-500/20 disabled:opacity-50"
                    data-testid={`cd-verify-${d.id}`}
                  >
                    {busyId === d.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <ShieldCheck className="w-3 h-3" />} Verify
                  </button>
                )}
                {!d.verified && (
                  <button
                    type="button"
                    onClick={() => handleForceVerify(d.id)}
                    disabled={busyId === d.id}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-zinc-800 border border-zinc-700 text-zinc-300 text-xs font-semibold hover:bg-zinc-700 disabled:opacity-50"
                    title="GymAxis platform admin only — bypasses DNS check for staging hosts"
                    data-testid={`cd-force-verify-${d.id}`}
                  >
                    Force
                  </button>
                )}
                {d.verified && (
                  <a
                    href={`https://${d.hostname}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold hover:bg-cyan-500/20"
                    data-testid={`cd-open-${d.id}`}
                  >
                    <ExternalLink className="w-3 h-3" /> Open
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => handleDelete(d.id, d.hostname)}
                  disabled={busyId === d.id}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-red-500/10 border border-red-500/30 text-red-300 text-xs font-semibold hover:bg-red-500/20 disabled:opacity-50"
                  data-testid={`cd-delete-${d.id}`}
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            </div>

            {/* DNS records callout (only while unverified) */}
            {!d.verified && d.dns_record && (
              <div className="mt-4 rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  <span className="text-xs font-semibold text-amber-200 uppercase tracking-wider">DNS records to set</span>
                </div>
                <div className="space-y-3">
                  <DnsRow
                    type="CNAME"
                    host={d.dns_record.cname.host}
                    value={d.dns_record.cname.value}
                    onCopy={copyToClipboard}
                    rowKey={`${d.id}-cname`}
                  />
                  <DnsRow
                    type="TXT"
                    host={d.dns_record.txt.host}
                    value={d.dns_record.txt.value}
                    onCopy={copyToClipboard}
                    rowKey={`${d.id}-txt`}
                  />
                </div>
                <p className="text-[11px] text-zinc-500 mt-3 leading-relaxed">
                  After adding both records at your DNS provider, click <strong className="text-white">Verify</strong> above. DNS can take up to 30 minutes to propagate.
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

const DnsRow = ({ type, host, value, onCopy, rowKey }) => (
  <div className="grid grid-cols-1 md:grid-cols-12 gap-2 items-start" data-testid={`cd-dns-${rowKey}`}>
    <div className="md:col-span-2">
      <span className="inline-block text-[10px] uppercase tracking-wider font-bold bg-zinc-800 border border-zinc-700 text-zinc-300 rounded-full px-2 py-1">{type}</span>
    </div>
    <div className="md:col-span-5 min-w-0">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-0.5">Host</div>
      <div className="flex items-center gap-1.5">
        <code className="block w-full px-2 py-1.5 bg-zinc-900 border border-zinc-800 rounded text-xs text-cyan-200 break-all">{host}</code>
        <button
          type="button"
          onClick={() => onCopy(host, 'Host')}
          className="shrink-0 p-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
          aria-label="Copy host"
        >
          <Copy className="w-3 h-3" />
        </button>
      </div>
    </div>
    <div className="md:col-span-5 min-w-0">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-0.5">Value</div>
      <div className="flex items-center gap-1.5">
        <code className="block w-full px-2 py-1.5 bg-zinc-900 border border-zinc-800 rounded text-xs text-emerald-200 break-all">{value}</code>
        <button
          type="button"
          onClick={() => onCopy(value, 'Value')}
          className="shrink-0 p-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
          aria-label="Copy value"
        >
          <Copy className="w-3 h-3" />
        </button>
      </div>
    </div>
  </div>
);

export default CustomDomainsPanel;
