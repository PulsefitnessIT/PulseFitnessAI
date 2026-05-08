import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Database, Search, Download, FileJson, FileSpreadsheet, ChevronLeft, ChevronRight, Loader2, ShieldAlert, Eye } from 'lucide-react';
import { notify } from '@/components/notifications';

/**
 * Iter 225 — read-only Mongo collection browser for Master Admins.
 *
 * Surfaces:
 *   - Two-pane layout: list of collections (left), table of docs (right)
 *   - Per-collection text search across id/name/email/slug/serial_number
 *   - Pagination (25 / 50 / 100)
 *   - Each row → click → expanded JSON view in a side drawer
 *   - Export current filtered query as JSON (ndjson) or CSV (10k cap)
 *
 * Sensitive fields (password, hash, secret, token, mfa_, backup_code,
 * stripe_secret, api_key, private_key, credential) are redacted server-side.
 */
const DbViewerPanel = () => {
  const { API } = useAuth();
  const [collections, setCollections] = useState([]);
  const [collectionsLoading, setCollectionsLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [activeName, setActiveName] = useState(null);
  const [docs, setDocs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState('');
  const [docsLoading, setDocsLoading] = useState(false);
  const [redactedKeys, setRedactedKeys] = useState([]);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [exporting, setExporting] = useState(false);

  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

  // ─── Initial collection list ───
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/master-admin/db/collections`, { headers: headers() });
        if (cancelled) return;
        setCollections(r.data?.collections || []);
      } catch (e) {
        notify.error('Could not load collections', e.response?.data?.detail || 'Check master admin permissions.');
      }
      setCollectionsLoading(false);
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Fetch docs whenever active collection / page / search changes ───
  useEffect(() => {
    if (!activeName) return;
    let cancelled = false;
    setDocsLoading(true);
    (async () => {
      try {
        const params = { page, page_size: pageSize };
        if (search.trim()) params.q = search.trim();
        const r = await axios.get(`${API}/master-admin/db/collections/${encodeURIComponent(activeName)}`, {
          headers: headers(), params,
        });
        if (cancelled) return;
        setDocs(r.data?.docs || []);
        setTotal(r.data?.total || 0);
        setRedactedKeys(r.data?.redacted_keys || []);
      } catch (e) {
        if (!cancelled) {
          notify.error(`Could not browse '${activeName}'`, e.response?.data?.detail || 'Try again');
          setDocs([]); setTotal(0);
        }
      }
      if (!cancelled) setDocsLoading(false);
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeName, page, pageSize, search]);

  const filteredCollections = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return collections;
    return collections.filter((c) => c.name.toLowerCase().includes(q));
  }, [collections, filter]);

  const pages = total === 0 ? 0 : Math.ceil(total / pageSize);

  const onPickCollection = (name) => {
    setActiveName(name);
    setPage(1);
    setSearch('');
    setSelectedDoc(null);
  };

  const onExport = async (format) => {
    if (!activeName) return;
    setExporting(true);
    try {
      const params = new URLSearchParams({ format, confirm: 'true' });
      if (search.trim()) params.set('q', search.trim());
      const url = `${API}/master-admin/db/collections/${encodeURIComponent(activeName)}/export?${params.toString()}`;
      const r = await axios.get(url, {
        headers: headers(), responseType: 'blob',
      });
      const blob = new Blob([r.data], { type: format === 'csv' ? 'text/csv' : 'application/x-ndjson' });
      const dlUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = dlUrl;
      a.download = `${activeName}.${format === 'csv' ? 'csv' : 'ndjson'}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(dlUrl);
      const count = r.headers['x-export-count'] || '?';
      notify.success(`Exported ${count} rows`, `${activeName}.${format}`);
    } catch (e) {
      notify.error('Export failed', e.response?.data?.detail || 'Try again');
    }
    setExporting(false);
  };

  const renderCellValue = (val) => {
    if (val === null || val === undefined) return <span className="text-zinc-400 italic">null</span>;
    if (typeof val === 'boolean') return <span className="text-blue-600">{String(val)}</span>;
    if (typeof val === 'number') return <span className="text-amber-700 font-mono">{val}</span>;
    if (typeof val === 'object') return <span className="text-zinc-500 font-mono text-xs">{Array.isArray(val) ? `[${val.length}]` : '{…}'}</span>;
    const s = String(val);
    if (s === '[REDACTED]') return <Badge className="bg-rose-50 text-rose-700 border border-rose-200">REDACTED</Badge>;
    return <span className="text-zinc-800">{s.length > 60 ? `${s.slice(0, 60)}…` : s}</span>;
  };

  const tableColumns = useMemo(() => {
    if (docs.length === 0) return [];
    // Pick the most common keys across the page (limit 8 to fit a screen).
    const counts = {};
    for (const d of docs) for (const k of Object.keys(d)) counts[k] = (counts[k] || 0) + 1;
    const ordered = Object.entries(counts)
      .filter(([k]) => k !== '_id')
      .sort((a, b) => b[1] - a[1])
      .map(([k]) => k);
    // Always promote `id` and `name` / `email` to the front when present.
    const front = ['id', 'name', 'email'].filter((k) => ordered.includes(k));
    const rest = ordered.filter((k) => !front.includes(k));
    return [...front, ...rest].slice(0, 8);
  }, [docs]);

  return (
    <div className="space-y-4" data-testid="db-viewer-panel">
      <div className="flex items-center gap-3">
        <Database className="text-zinc-700" size={22} />
        <div>
          <h2 className="text-xl font-semibold text-zinc-900">Database</h2>
          <p className="text-zinc-500 text-sm">Read-only browser. Sensitive fields auto-redacted. Exports capped at 10,000 rows.</p>
        </div>
      </div>

      <Card className="p-5 bg-amber-50 border-amber-200 flex items-start gap-3" data-testid="db-viewer-warning">
        <ShieldAlert size={16} className="text-amber-700 mt-0.5 shrink-0" />
        <div className="text-amber-900 text-xs">
          <strong>Read-only.</strong> No edits or deletes are exposed via this UI or its API. Logs:
          every collection browse and export is recorded against your master admin session.
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
        {/* ── Collection list ── */}
        <Card className="p-5 bg-white border-zinc-200" data-testid="db-collection-list">
          <div className="relative mb-2">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
            <Input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder={`Filter ${collections.length} collections…`}
              className="pl-8 bg-white border-zinc-200 text-zinc-900"
              data-testid="db-collection-filter"
            />
          </div>
          <div className="max-h-[60vh] overflow-y-auto -mx-1">
            {collectionsLoading && (
              <p className="text-zinc-400 text-xs px-3 py-4 text-center">Loading…</p>
            )}
            {!collectionsLoading && filteredCollections.map((c) => (
              <button
                key={c.name}
                type="button"
                onClick={() => onPickCollection(c.name)}
                className={`w-full text-left px-3 py-2 rounded-md flex items-center justify-between text-sm hover:bg-zinc-100 transition-colors ${activeName === c.name ? 'bg-zinc-900 text-white hover:bg-zinc-900' : 'text-zinc-800'}`}
                data-testid={`db-collection-${c.name}`}
              >
                <span className="font-mono truncate">{c.name}</span>
                <span className={`text-xs ml-2 shrink-0 ${activeName === c.name ? 'text-zinc-300' : 'text-zinc-500'}`}>
                  {c.count >= 0 ? c.count.toLocaleString() : '—'}
                </span>
              </button>
            ))}
            {!collectionsLoading && filteredCollections.length === 0 && (
              <p className="text-zinc-400 text-xs px-3 py-4 text-center">No collections match.</p>
            )}
          </div>
        </Card>

        {/* ── Document table ── */}
        <Card className="p-5 bg-white border-zinc-200 min-h-[200px]" data-testid="db-doc-table-card">
          {!activeName && (
            <div className="flex flex-col items-center justify-center py-20 text-zinc-400">
              <Database size={32} className="mb-2" />
              <p className="text-sm">Pick a collection on the left to start browsing.</p>
            </div>
          )}
          {activeName && (
            <>
              <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
                <div className="flex items-center gap-2">
                  <h3 className="font-mono text-sm font-semibold text-zinc-900">{activeName}</h3>
                  <Badge className="bg-zinc-100 text-zinc-700 border border-zinc-200">
                    {total.toLocaleString()} {total === 1 ? 'doc' : 'docs'}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm" variant="outline"
                    onClick={() => onExport('json')}
                    disabled={exporting || total === 0}
                    className="h-8 text-xs border-zinc-200 text-zinc-700"
                    data-testid="db-export-json-btn"
                  >
                    <FileJson size={12} className="mr-1" /> Export JSON
                  </Button>
                  <Button
                    size="sm" variant="outline"
                    onClick={() => onExport('csv')}
                    disabled={exporting || total === 0}
                    className="h-8 text-xs border-zinc-200 text-zinc-700"
                    data-testid="db-export-csv-btn"
                  >
                    <FileSpreadsheet size={12} className="mr-1" /> Export CSV
                  </Button>
                </div>
              </div>

              <div className="flex items-center gap-2 mb-3">
                <div className="relative flex-1">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
                  <Input
                    value={search}
                    onChange={(e) => { setPage(1); setSearch(e.target.value); }}
                    placeholder="Search by id, name, email, slug, serial_number…"
                    className="pl-8 bg-white border-zinc-200 text-zinc-900"
                    data-testid="db-doc-search"
                  />
                </div>
                <select
                  value={pageSize}
                  onChange={(e) => { setPage(1); setPageSize(Number(e.target.value)); }}
                  className="h-9 bg-white border border-zinc-200 text-zinc-900 rounded-md px-2 text-sm"
                  data-testid="db-page-size"
                >
                  <option value={25}>25 / page</option>
                  <option value={50}>50 / page</option>
                  <option value={100}>100 / page</option>
                </select>
              </div>

              {redactedKeys.length > 0 && (
                <p className="text-zinc-500 text-[11px] mb-2">
                  <ShieldAlert size={11} className="inline -mt-0.5 mr-1" />
                  Fields containing <code>{redactedKeys.join(', ')}</code> are redacted server-side.
                </p>
              )}

              <div className="overflow-x-auto border border-zinc-200 rounded-md" data-testid="db-doc-table">
                <table className="w-full text-sm">
                  <thead className="bg-zinc-50 text-zinc-600 text-xs uppercase tracking-wide">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium w-8"></th>
                      {tableColumns.map((col) => (
                        <th key={col} className="text-left px-3 py-2 font-medium font-mono">{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {docsLoading && (
                      <tr><td colSpan={tableColumns.length + 1} className="text-center py-8 text-zinc-400">
                        <Loader2 size={16} className="inline animate-spin mr-1" /> Loading…
                      </td></tr>
                    )}
                    {!docsLoading && docs.map((d, idx) => (
                      <tr
                        key={d.id || d._id || idx}
                        className="border-t border-zinc-100 hover:bg-zinc-50 cursor-pointer"
                        onClick={() => setSelectedDoc(d)}
                        data-testid={`db-doc-row-${idx}`}
                      >
                        <td className="px-3 py-2"><Eye size={12} className="text-zinc-400" /></td>
                        {tableColumns.map((col) => (
                          <td key={col} className="px-3 py-2 max-w-[220px] truncate">
                            {renderCellValue(d[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                    {!docsLoading && docs.length === 0 && (
                      <tr><td colSpan={tableColumns.length + 1} className="text-center py-8 text-zinc-400 text-sm">
                        No documents match.
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              {pages > 1 && (
                <div className="flex items-center justify-between mt-3">
                  <p className="text-zinc-500 text-xs">
                    Page {page} of {pages}
                  </p>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm" variant="outline"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      className="h-7 px-2 border-zinc-200"
                      data-testid="db-page-prev"
                    >
                      <ChevronLeft size={12} />
                    </Button>
                    <Button
                      size="sm" variant="outline"
                      disabled={page >= pages}
                      onClick={() => setPage((p) => Math.min(pages, p + 1))}
                      className="h-7 px-2 border-zinc-200"
                      data-testid="db-page-next"
                    >
                      <ChevronRight size={12} />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </Card>
      </div>

      {/* ── Detail drawer ── */}
      {selectedDoc && (
        <div
          className="fixed inset-0 bg-black/30 z-40 flex justify-end"
          onClick={() => setSelectedDoc(null)}
          data-testid="db-doc-drawer-backdrop"
        >
          <div
            className="bg-white w-full max-w-xl h-full overflow-y-auto p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
            data-testid="db-doc-drawer"
          >
            <div className="flex items-start justify-between mb-3">
              <div>
                <p className="text-zinc-500 text-xs uppercase tracking-wide">Document</p>
                <p className="font-mono text-sm text-zinc-900 break-all">
                  {selectedDoc.id || selectedDoc._id || '(no id)'}
                </p>
              </div>
              <Button
                size="sm" variant="ghost"
                onClick={() => setSelectedDoc(null)}
                className="h-7 px-2 text-zinc-500"
                data-testid="db-doc-drawer-close"
              >
                Close
              </Button>
            </div>
            <pre className="bg-zinc-50 border border-zinc-200 rounded-md p-3 text-xs font-mono whitespace-pre-wrap break-words text-zinc-800" data-testid="db-doc-drawer-json">
              {JSON.stringify(selectedDoc, null, 2)}
            </pre>
            <div className="mt-3 flex gap-2">
              <Button
                size="sm" variant="outline"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(JSON.stringify(selectedDoc, null, 2));
                    notify.micro('Copied JSON');
                  } catch {
                    notify.error('Copy failed');
                  }
                }}
                className="h-8 text-xs border-zinc-200 text-zinc-700"
                data-testid="db-doc-drawer-copy"
              >
                <Download size={12} className="mr-1" /> Copy JSON
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DbViewerPanel;
