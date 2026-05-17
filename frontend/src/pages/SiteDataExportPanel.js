/**
 * Iter 216h163 — Self-service per-site data export.
 *
 * HQ owners pick a site they're allowed to export and pull the entire
 * dataset (equipment, faults, service cases, audit trail, etc.) as
 * either a JSON dump or a ZIP of CSVs. Every download is audit-logged
 * server-side and shows up in the Master Admin Compliance trail.
 */
import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { notify } from '@/components/notifications';
import {
  Download, FileJson, FileArchive, Loader2, ShieldCheck, Building2,
  Database, Info,
} from 'lucide-react';

const SiteDataExportPanel = () => {
  const { API } = useAuth();
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState('');
  const [downloading, setDownloading] = useState(null); // 'json' | 'zip' | null

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const token = localStorage.getItem('token');
      try {
        const res = await axios.get(
          `${API}/account/data-export/sites`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        const list = res.data?.sites || [];
        setSites(list);
        if (list.length) setSelectedId(list[0].id);
      } catch (err) {
        if (err.response?.status === 403) {
          notify.error('Owner or manager role required to access data export');
        } else {
          notify.error('Failed to load exportable sites');
        }
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [API]);

  const selected = useMemo(
    () => sites.find(s => s.id === selectedId) || null,
    [sites, selectedId],
  );

  const downloadBlob = async (fmt) => {
    if (!selected) return;
    setDownloading(fmt);
    const token = localStorage.getItem('token');
    try {
      const res = await axios.get(
        `${API}/account/data-export/site/${selected.id}.${fmt}`,
        { headers: { Authorization: `Bearer ${token}` }, responseType: 'blob' },
      );
      const mime = fmt === 'json' ? 'application/json' : 'application/zip';
      const blob = new Blob([res.data], { type: mime });
      const url = URL.createObjectURL(blob);
      const safe = (selected.name || 'site').replace(/[^\w-]+/g, '_').slice(0, 40);
      const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const a = document.createElement('a');
      a.href = url;
      a.download = `site_export_${safe}_${stamp}.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      notify.success(`Site export downloaded (${fmt.toUpperCase()})`);
    } catch (err) {
      if (err.response?.status === 403) {
        notify.error('You do not have access to that site');
      } else {
        notify.error(`Failed to download ${fmt.toUpperCase()} export`);
      }
    } finally {
      setDownloading(null);
    }
  };

  return (
    <Card
      className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6"
      data-testid="site-data-export-panel"
    >
      <div className="flex items-start gap-3 mb-4">
        <div className="w-10 h-10 rounded-lg bg-[rgb(var(--rgb-brand-blue)/0.12)] flex items-center justify-center flex-shrink-0">
          <Database size={20} className="text-[var(--color-brand-blue)]" />
        </div>
        <div className="flex-1">
          <h3 className="text-xl font-semibold text-[var(--theme-text)] mb-1">
            Per-site data export
          </h3>
          <p className="text-sm text-[var(--color-text-muted)] max-w-2xl">
            Download everything held for a single site — equipment, faults,
            service cases, quotes, invoices, visit notes, and the 12-month
            audit trail. JSON is the data-portability format (ICO Art. 20);
            ZIP/CSV is what finance opens in Excel. Every download is
            audit-logged on the Compliance trail.
          </p>
        </div>
      </div>

      <div className="rounded-lg bg-blue-500/10 border border-blue-500/30 p-3 mb-4 flex items-start gap-2">
        <ShieldCheck size={16} className="text-[var(--color-brand-blue)] flex-shrink-0 mt-0.5" />
        <p className="text-xs text-[var(--color-text-muted)]">
          You can only export sites you own. Cross-tenant requests are
          blocked at the API. The download includes a recorded
          <code className="mx-1 px-1 py-0.5 rounded bg-white/5 text-[var(--color-brand-blue)] text-[11px]">site_data_export</code>
          audit entry with your email, IP, and the row counts shipped.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-[var(--color-text-muted)] py-6">
          <Loader2 size={16} className="animate-spin" /> Loading sites…
        </div>
      ) : sites.length === 0 ? (
        <div className="flex items-center gap-2 text-[var(--color-text-muted)] py-6">
          <Info size={16} /> No exportable sites for your account.
        </div>
      ) : (
        <>
          <label className="block text-xs uppercase tracking-wide text-[var(--color-text-muted)] mb-2">
            Choose a site
          </label>
          <div
            className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 mb-5"
            data-testid="site-data-export-sites"
          >
            {sites.map(s => {
              const active = selectedId === s.id;
              return (
                <button
                  key={s.id}
                  onClick={() => setSelectedId(s.id)}
                  data-testid={`site-data-export-pick-${s.id}`}
                  className={`text-left p-3 rounded-lg border transition-colors ${
                    active
                      ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.12)]'
                      : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.06]'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Building2 size={14} className={active ? 'text-[var(--color-brand-blue)]' : 'text-[var(--color-text-muted)]'} />
                    <span className="text-sm font-medium text-[var(--theme-text)] truncate">
                      {s.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {s.is_head_office && (
                      <Badge className="bg-amber-500/15 text-amber-300 border-amber-500/30 text-[10px]">
                        Head Office
                      </Badge>
                    )}
                    <Badge className="bg-white/5 text-[var(--color-text-muted)] border-white/10 text-[10px]">
                      {s.kind === 'mod_child' ? 'MOD child site' : 'Internal site'}
                    </Badge>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              size="sm"
              onClick={() => downloadBlob('json')}
              disabled={!selected || downloading !== null}
              className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-alt)]"
              data-testid="site-data-export-json-btn"
            >
              {downloading === 'json' ? (
                <Loader2 size={14} className="animate-spin mr-2" />
              ) : (
                <FileJson size={14} className="mr-2" />
              )}
              Download JSON
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => downloadBlob('zip')}
              disabled={!selected || downloading !== null}
              className="border-[var(--color-brand-blue)] text-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue)] hover:text-white"
              data-testid="site-data-export-zip-btn"
            >
              {downloading === 'zip' ? (
                <Loader2 size={14} className="animate-spin mr-2" />
              ) : (
                <FileArchive size={14} className="mr-2" />
              )}
              Download CSV bundle (ZIP)
            </Button>
            {selected && (
              <span className="text-xs text-[var(--color-text-muted)] flex items-center gap-1.5">
                <Download size={12} />
                Selected: <strong className="text-[var(--theme-text)]">{selected.name}</strong>
              </span>
            )}
          </div>
        </>
      )}
    </Card>
  );
};

export default SiteDataExportPanel;
