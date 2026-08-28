import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Radio, Save, Search, Download, Filter, MapPin, Gauge, AlertTriangle,
  CheckCircle, Clock, CalendarClock, FileCheck2, ChevronUp, ChevronDown, ClipboardList,
  FileSpreadsheet,
} from 'lucide-react';
import Button from '@/components/shared/Button';
import BlueLightImportPanel from './BlueLightImportPanel';

const STATUS_META = {
  not_planned: { label: 'Not Planned', color: 'var(--color-text-faint-alt)' },
  planned: { label: 'Planned', color: 'var(--color-accent-violet)' },
  scheduled: { label: 'Scheduled', color: 'var(--color-info-ios)' },
  travelling: { label: 'Travelling', color: 'var(--color-accent-amber)' },
  on_site: { label: 'On Site', color: 'var(--color-accent-amber)' },
  in_progress: { label: 'In Progress', color: 'var(--color-accent-amber)' },
  awaiting_information: { label: 'Awaiting Info', color: 'var(--color-accent-amber)' },
  follow_up_required: { label: 'Follow-up', color: 'var(--color-warning)' },
  completed: { label: 'Completed', color: 'var(--color-success-alt)' },
  certificate_generated: { label: 'Cert Generated', color: 'var(--color-success-alt-2)' },
  certificate_sent: { label: 'Cert Sent', color: 'var(--color-success-alt)' },
  overdue: { label: 'Overdue', color: 'var(--color-danger)' },
};

const StatusPill = ({ status }) => {
  const m = STATUS_META[status] || { label: status || '—', color: 'var(--color-text-faint-alt)' };
  return (
    <span data-testid={`bl-status-${status}`} className="px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap"
      style={{ background: m.color + '22', color: m.color }}>{m.label}</span>
  );
};

const CELL_META = {
  'n/a': { label: 'N/A', color: 'var(--color-text-faint-alt)' },
  pending: { label: 'Pending', color: 'var(--color-accent-amber)' },
  in_progress: { label: 'In progress', color: 'var(--color-accent-amber)' },
  complete: { label: 'Complete', color: 'var(--color-success-alt)' },
  passed: { label: 'Passed', color: 'var(--color-success-alt)' },
  outstanding: { label: 'Outstanding', color: 'var(--color-text-faint-alt)' },
  generated: { label: 'Generated', color: 'var(--color-success-alt-2)' },
  sent: { label: 'Sent', color: 'var(--color-success-alt)' },
  awaiting_review: { label: 'Awaiting review', color: 'var(--color-accent-amber)' },
  send_failed: { label: 'Send failed', color: 'var(--color-danger)' },
  approved: { label: 'Approved', color: 'var(--color-success-alt)' },
  reverted: { label: 'Reverted', color: 'var(--color-text-faint-alt)' },
  removed: { label: 'Removed', color: 'var(--color-danger)' },
  rejected: { label: 'Rejected', color: 'var(--color-text-faint-alt)' },
};

const CellPill = ({ value }) => {
  const m = CELL_META[value] || { label: value || '—', color: 'var(--color-text-faint-alt)' };
  return (
    <span className="px-2 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap"
      style={{ background: m.color + '1f', color: m.color }}>{m.label}</span>
  );
};

function StatTile({ label, value, sub, icon: Icon, color, testId }) {
  return (
    <div data-testid={testId} className="rounded-xl p-3 border" style={{ borderColor: 'var(--color-border)', background: 'var(--color-surface)' }}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wide" style={{ color: 'var(--color-text-muted)' }}>{label}</span>
        {Icon && <Icon size={14} style={{ color: color || 'var(--color-text-muted)' }} />}
      </div>
      <div className="text-2xl font-bold mt-1" style={{ color: color || 'var(--color-text)' }}>{value}</div>
      {sub && <div className="text-[11px] mt-0.5" style={{ color: 'var(--color-text-muted)' }}>{sub}</div>}
    </div>
  );
}

export default function BlueLightTab({ contract, contractId, API, headers, c, reload }) {
  const [overview, setOverview] = useState(null);
  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [certStatusFilter, setCertStatusFilter] = useState('');
  const [sort, setSort] = useState('station_name');
  const [direction, setDirection] = useState('asc');
  const [saving, setSaving] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [meta, setMeta] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [certs, setCerts] = useState(null);
  const [showCerts, setShowCerts] = useState(false);
  const [recon, setRecon] = useState(null);
  const [showRecon, setShowRecon] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [engineers, setEngineers] = useState([]);
  const [selected, setSelected] = useState(() => new Set());
  const [planDate, setPlanDate] = useState('');
  const [planWindowEnd, setPlanWindowEnd] = useState('');
  const [planEngineer, setPlanEngineer] = useState('');
  const [planning, setPlanning] = useState(false);
  const [planMsg, setPlanMsg] = useState(null);

  const isBL = !!(contract?.is_blue_light);

  const loadOverview = useCallback(async () => {
    try {
      const [ov, mt] = await Promise.all([
        axios.get(`${API}/crm/v2/contracts/${contractId}/overview`, { headers: headers() }),
        axios.get(`${API}/crm/v2/blue-light/customer-types`, { headers: headers() }),
      ]);
      setOverview(ov.data);
      setMeta(mt.data);
      setCfg({ ...(mt.data.defaults || {}), ...(ov.data.contract?.blue_light || {}) });
    } catch (e) { /* noop */ }
  }, [API, headers, contractId]);

  const loadStations = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ search: debouncedSearch, status: statusFilter, cert_status: certStatusFilter, sort, direction });
      const res = await axios.get(`${API}/crm/v2/contracts/${contractId}/stations?${params}`, { headers: headers() });
      setStations(res.data.stations || []);
    } catch (e) { setStations([]); } finally { setLoading(false); }
  }, [API, headers, contractId, debouncedSearch, statusFilter, certStatusFilter, sort, direction]);

  useEffect(() => { loadOverview(); }, [loadOverview]);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => { if (isBL) loadStations(); }, [isBL, loadStations]);
  const loadEngineers = useCallback(() => {
    axios.get(`${API}/crm/v2/contracts/${contractId}/engineers`, { headers: headers() })
      .then(r => setEngineers(r.data.engineers || [])).catch(() => setEngineers([]));
  }, [API, headers, contractId]);
  useEffect(() => { if (isBL) loadEngineers(); }, [isBL, loadEngineers]);

  const toggleRow = (id) => setSelected(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  const allSelected = stations.length > 0 && stations.every(r => selected.has(r.site_id));
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(stations.map(r => r.site_id)));
  const clearSel = () => setSelected(new Set());

  const refreshAll = async () => { await Promise.all([loadOverview(), loadStations()]); loadEngineers(); loadCerts(); };

  const loadCerts = useCallback(() => {
    axios.get(`${API}/crm/v2/contracts/${contractId}/certificates`, { headers: headers() })
      .then(r => setCerts(r.data)).catch(() => setCerts({ certificates: [], by_status: {} }));
  }, [API, headers, contractId]);
  useEffect(() => { if (isBL) loadCerts(); }, [isBL, loadCerts]);

  const loadRecon = useCallback(() => {
    axios.get(`${API}/crm/v2/contracts/${contractId}/asset-changes`, { headers: headers() })
      .then(r => setRecon(r.data)).catch(() => setRecon({ items: [], counts: {} }));
  }, [API, headers, contractId]);
  useEffect(() => { if (isBL) loadRecon(); }, [isBL, loadRecon]);

  const reviewChange = async (item, action) => {
    try {
      await axios.post(`${API}/crm/v2/contracts/${contractId}/asset-changes/review`,
        { item_id: item.id, action }, { headers: headers() });
      loadRecon(); loadOverview();
    } catch (e) { alert(e.response?.data?.detail || 'Review failed'); }
  };

  const downloadCert = (cert) => {
    axios.get(`${API}/crm/v2/certificates/${cert.id}/download`, { headers: headers(), responseType: 'blob' })
      .then(res => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
        a.download = cert.filename || 'certificate.pdf'; a.click(); URL.revokeObjectURL(a.href);
      }).catch(() => alert('Could not download the certificate.'));
  };
  const approveCert = async (cert) => {
    try {
      const r = await axios.post(`${API}/crm/v2/certificates/${cert.id}/approve`, {}, { headers: headers() });
      alert(r.data.success ? `Certificate sent to ${(r.data.recipients || []).join(', ')}.` : `Send failed: ${r.data.error || 'unknown'}`);
      loadCerts(); loadOverview();
    } catch (e) { alert(e.response?.data?.detail || 'Approve/send failed'); }
  };

  const planVisits = async (force = false) => {
    if (!planDate) { alert('Choose a scheduled date first.'); return; }
    setPlanning(true); setPlanMsg(null);
    try {
      const eng = engineers.find(e => e.id === planEngineer);
      const res = await axios.post(`${API}/crm/v2/contracts/${contractId}/plan-visits`, {
        site_ids: Array.from(selected), scheduled_date: planDate,
        service_window_end: planWindowEnd, engineer_id: planEngineer,
        engineer_name: eng?.full_name || '', force,
      }, { headers: headers() });
      const d = res.data;
      setPlanMsg({ created: d.created_count, skipped: d.skipped || [], cycle: d.cycle_label });
      clearSel();
      await refreshAll();
    } catch (e) { alert(e.response?.data?.detail || 'Failed to plan visits'); }
    finally { setPlanning(false); }
  };

  const reassign = async () => {
    if (!planEngineer) { alert('Pick an engineer to reassign to.'); return; }
    setPlanning(true); setPlanMsg(null);
    try {
      const eng = engineers.find(e => e.id === planEngineer);
      const res = await axios.post(`${API}/crm/v2/contracts/${contractId}/reassign-visits`, {
        site_ids: Array.from(selected), engineer_id: planEngineer, engineer_name: eng?.full_name || '',
      }, { headers: headers() });
      setPlanMsg({ reassigned: res.data.updated, engineer: res.data.engineer_name });
      clearSel();
      await refreshAll();
    } catch (e) { alert(e.response?.data?.detail || 'Failed to reassign'); }
    finally { setPlanning(false); }
  };

  const saveConfig = async (extra = {}) => {
    setSaving(true);
    try {
      await axios.put(`${API}/crm/v2/contracts/${contractId}/blue-light-config`,
        { ...cfg, ...extra }, { headers: headers() });
      await loadOverview();
      if (reload) await reload();
      setShowConfig(false);
    } catch (e) { alert(e.response?.data?.detail || 'Failed to save configuration'); }
    finally { setSaving(false); }
  };

  const setSortCol = (col) => {
    if (sort === col) setDirection(direction === 'asc' ? 'desc' : 'asc');
    else { setSort(col); setDirection('asc'); }
  };

  const exportCsv = () => {
    axios.get(`${API}/crm/v2/contracts/${contractId}/stations.csv`, { headers: headers(), responseType: 'blob' }).then(res => {
      const blob = new Blob([res.data], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `stations-${contractId.slice(0, 8)}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    }).catch(() => alert('Could not export the station list. Please try again.'));
  };

  const s = overview?.stats || {};
  const stationCols = [
    ['station_name', 'Station'], ['address', 'Address'], ['contact_name', 'Contact'],
    ['telephone', 'Tel'], ['asset_count', 'Assets'], ['treadmill_count', 'Treadmills'],
    ['next_service_due', 'Next Due'], ['scheduled_date', 'Scheduled'],
    ['assigned_engineer_name', 'Engineer'], ['visit_status', 'Visit'],
    ['calibration_status', 'Calibration'], ['faults_raised', 'Faults'],
    ['certificate_status', 'Certificate'],
  ];

  if (!isBL) {
    return (
      <div data-testid="bl-enable-panel" className="max-w-2xl mx-auto text-center py-10">
        <Radio size={40} className="mx-auto mb-4" style={{ color: 'var(--color-info-ios)' }} />
        <h3 className="text-lg font-bold mb-2" style={{ color: c.text }}>Blue Light / Multi-Site PTE Service</h3>
        <p className="text-sm mb-6" style={{ color: c.textMuted }}>
          Turn this contract into a multi-site physical training equipment service programme — station
          service matrix, treadmill calibration and automatic certificates. Configurable per contract.
        </p>
        {meta && cfg && (
          <div className="text-left rounded-xl border p-4 mb-4" style={{ borderColor: c.border, background: 'var(--color-surface)' }}>
            <ConfigForm cfg={cfg} setCfg={setCfg} meta={meta} c={c} />
          </div>
        )}
        <Button onClick={() => saveConfig()} disabled={saving} icon={CheckCircle} data-testid="bl-enable-btn">
          {saving ? 'Enabling…' : 'Enable Blue Light Service'}
        </Button>
        <div className="mt-3">
          <button className="text-[12px] underline" data-testid="bl-enable-import"
            style={{ color: 'var(--color-info-ios)' }}
            onClick={async () => { await saveConfig(); setShowImport(true); }}>
            or enable &amp; import stations &amp; assets from a spreadsheet
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="bl-tab">
      {/* Overview stats */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: c.text }}>
          <Radio size={16} style={{ color: 'var(--color-info-ios)' }} /> Contract Overview
          <span className="text-[11px] font-normal" style={{ color: c.textMuted }}>
            · {meta?.customer_types?.find(t => t.id === overview?.contract?.customer_type)?.name || 'Blue Light'}
          </span>
        </h3>
        <Button variant="ghost" size="sm" icon={Filter} onClick={() => setShowConfig(v => !v)} data-testid="bl-config-toggle">
          Configure
        </Button>
      </div>

      <div className="flex justify-end -mt-2 gap-2">
        <Button variant="ghost" size="sm" icon={FileSpreadsheet} onClick={() => setShowImport(v => !v)} data-testid="bl-import-toggle">
          Import
        </Button>
        <Button variant="ghost" size="sm" icon={ClipboardList} onClick={() => setShowRecon(v => !v)} data-testid="bl-recon-toggle">
          Asset Changes{recon?.counts?.pending ? ` (${recon.counts.pending})` : ''}
        </Button>
        <Button variant="ghost" size="sm" icon={FileCheck2} onClick={() => setShowCerts(v => !v)} data-testid="bl-certs-toggle">
          Certificates{certs?.count ? ` (${certs.count})` : ''}
        </Button>
      </div>

      {showImport && (
        <BlueLightImportPanel API={API} headers={headers} contractId={contractId} c={c}
          onImported={() => { refreshAll(); }} />
      )}

      {showRecon && (
        <div className="rounded-xl border p-4" style={{ borderColor: c.border, background: 'var(--color-surface)' }} data-testid="bl-recon-panel">
          <div className="flex items-center gap-2 mb-2 text-sm font-bold" style={{ color: c.text }}>
            <ClipboardList size={15} style={{ color: 'var(--color-accent-violet)' }} /> Asset Changes From Service Visits
          </div>
          <div className="flex flex-wrap gap-3 mb-3">
            {[['new', 'New found'], ['correction', 'Corrections'], ['not_found', 'Not found'], ['pending', 'Awaiting review']].map(([k, l]) => (
              <div key={k} className="text-center px-3 py-1.5 rounded-lg" style={{ background: 'var(--color-bg)' }} data-testid={`bl-recon-count-${k}`}>
                <div className="text-lg font-bold" style={{ color: c.text }}>{recon?.counts?.[k] || 0}</div>
                <div className="text-[10px]" style={{ color: c.textMuted }}>{l}</div>
              </div>
            ))}
          </div>
          {(!recon || recon.items.length === 0) ? (
            <div className="text-sm text-center py-4" style={{ color: c.textMuted }} data-testid="bl-recon-empty">No asset changes recorded yet.</div>
          ) : (
            <div className="divide-y" style={{ borderColor: c.border }}>
              {recon.items.map(it => {
                const kindColor = { new: 'var(--color-success-alt-2)', correction: 'var(--color-accent-amber)', not_found: 'var(--color-danger)' }[it.kind];
                return (
                  <div key={it.id} className="flex items-center justify-between py-2 gap-2" data-testid={`bl-recon-row-${it.id}`}>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full font-semibold uppercase" style={{ background: kindColor + '22', color: kindColor }}>{it.kind.replace('_', ' ')}</span>
                        <span className="text-sm font-medium truncate" style={{ color: c.text }}>{it.station_name}</span>
                      </div>
                      <div className="text-[11px] mt-0.5 truncate" style={{ color: c.textMuted }}>{it.detail}</div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {['pending', 'auto_approved'].includes(it.review_status) ? (
                        <>
                          <Button size="sm" onClick={() => reviewChange(it, 'approve')} data-testid={`bl-recon-approve-${it.id}`}>Approve</Button>
                          <Button size="sm" variant="outline" onClick={() => reviewChange(it, 'revert')} data-testid={`bl-recon-revert-${it.id}`}>Revert</Button>
                        </>
                      ) : <CellPill value={it.review_status} />}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {showCerts && (
        <div className="rounded-xl border p-4" style={{ borderColor: c.border, background: 'var(--color-surface)' }} data-testid="bl-certs-panel">
          <div className="flex flex-wrap gap-3 mb-3">
            {[['generated', 'Generated'], ['sent', 'Sent'], ['awaiting_review', 'Awaiting review'], ['send_failed', 'Failed to send']].map(([k, l]) => (
              <div key={k} className="text-center px-3 py-1.5 rounded-lg" style={{ background: 'var(--color-bg)' }} data-testid={`bl-cert-count-${k}`}>
                <div className="text-lg font-bold" style={{ color: c.text }}>{certs?.by_status?.[k] || 0}</div>
                <div className="text-[10px]" style={{ color: c.textMuted }}>{l}</div>
              </div>
            ))}
          </div>
          {(!certs || certs.certificates.length === 0) ? (
            <div className="text-sm text-center py-4" style={{ color: c.textMuted }} data-testid="bl-certs-empty">No certificates yet — complete a station visit to generate one.</div>
          ) : (
            <div className="divide-y" style={{ borderColor: c.border }}>
              {certs.certificates.map(cert => (
                <div key={cert.id} className="flex items-center justify-between py-2 gap-2" data-testid={`bl-cert-row-${cert.id}`}>
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate" style={{ color: c.text }}>{cert.station_name}</div>
                    <div className="text-[11px]" style={{ color: c.textMuted }}>{cert.filename}</div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <CellPill value={cert.status} />
                    <Button variant="ghost" size="sm" icon={Download} onClick={() => downloadCert(cert)} data-testid={`bl-cert-download-${cert.id}`}>PDF</Button>
                    {cert.status === 'awaiting_review' && (
                      <Button size="sm" onClick={() => approveCert(cert)} data-testid={`bl-cert-approve-${cert.id}`}>Approve &amp; send</Button>
                    )}
                    {cert.status === 'send_failed' && (
                      <Button size="sm" variant="outline" onClick={() => approveCert(cert)} data-testid={`bl-cert-retry-${cert.id}`}>Retry send</Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {showConfig && meta && cfg && (
        <div className="rounded-xl border p-4" style={{ borderColor: c.border, background: 'var(--color-surface)' }} data-testid="bl-config-panel">
          <ConfigForm cfg={cfg} setCfg={setCfg} meta={meta} c={c} />
          <div className="flex justify-end mt-3">
            <Button onClick={() => saveConfig()} disabled={saving} icon={Save} data-testid="bl-config-save">
              {saving ? 'Saving…' : 'Save Configuration'}
            </Button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Stations" value={s.sites || 0} icon={MapPin} testId="bl-stat-sites"
          sub={`${s.assets || 0} assets · ${s.treadmills || 0} treadmills`} />
        <StatTile label="Completed" value={s.visits_completed || 0} icon={CheckCircle} color="var(--color-success-alt)"
          sub={`${s.completion_pct || 0}% of programme`} testId="bl-stat-completed" />
        <StatTile label="Scheduled" value={s.visits_scheduled || 0} icon={CalendarClock} color="var(--color-info-ios)"
          sub={`${s.visits_awaiting_booking || 0} awaiting booking`} testId="bl-stat-scheduled" />
        <StatTile label="Overdue" value={s.visits_overdue || 0} icon={AlertTriangle} color="var(--color-danger)"
          sub={s.next_planned_service_date ? `next ${s.next_planned_service_date}` : 'none planned'} testId="bl-stat-overdue" />
        <StatTile label="Certificates" value={`${s.certificates_completed || 0}/${s.sites || 0}`} icon={FileCheck2}
          color="var(--color-success-alt-2)" sub={`${s.certificates_sent || 0} sent`} testId="bl-stat-certs" />
        <StatTile label="Open Faults" value={s.open_faults || 0} icon={AlertTriangle} color="var(--color-warning)" testId="bl-stat-faults" />
        <StatTile label="Follow-ups" value={s.follow_ups_required || 0} icon={Clock} color="var(--color-accent-amber)" testId="bl-stat-followups" />
        <StatTile label="Service Every" value={`${s.service_frequency_months || 6} mo`} icon={Gauge} testId="bl-stat-freq" />
      </div>

      {/* Certificate tracker (§33) — click a tile to filter the matrix */}
      {(() => {
        const cb = s.certificates_breakdown || {};
        const tiles = [
          ['', 'All stations', cb.total_stations ?? s.sites ?? 0, 'var(--color-text)'],
          ['generated', 'Generated', cb.generated || 0, 'var(--color-success-alt-2)'],
          ['sent', 'Sent', cb.sent || 0, 'var(--color-success-alt)'],
          ['awaiting_review', 'Awaiting review', cb.awaiting_review || 0, 'var(--color-accent-amber)'],
          ['send_failed', 'Failed to send', cb.send_failed || 0, 'var(--color-danger)'],
          ['outstanding', 'No certificate', cb.outstanding || 0, 'var(--color-danger)'],
        ];
        return (
          <div className="rounded-xl border p-3" style={{ borderColor: c.border, background: 'var(--color-surface)' }} data-testid="bl-cert-tracker">
            <div className="flex items-center gap-2 mb-2 text-sm font-bold" style={{ color: c.text }}>
              <FileCheck2 size={15} style={{ color: 'var(--color-success-alt-2)' }} /> Certificate Tracker
              <span className="text-[11px] font-normal" style={{ color: c.textMuted }}>· click to find stations instantly</span>
            </div>
            <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
              {tiles.map(([key, label, val, color]) => (
                <button key={key || 'all'} data-testid={`bl-cert-track-${key || 'all'}`}
                  onClick={() => { setCertStatusFilter(key); setStatusFilter(''); }}
                  className="rounded-lg p-2 text-center transition-transform active:scale-95"
                  style={{ background: certStatusFilter === key ? color + '26' : 'var(--color-bg)', border: certStatusFilter === key ? `1px solid ${color}` : '1px solid transparent' }}>
                  <div className="text-xl font-bold" style={{ color }}>{val}</div>
                  <div className="text-[10px] leading-tight" style={{ color: c.textMuted }}>{label}</div>
                </button>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Bulk planning bar */}
      <div className="rounded-xl border p-3 flex flex-wrap items-end gap-3" style={{ borderColor: c.border, background: 'var(--color-surface)' }} data-testid="bl-plan-bar">
        <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: c.text }}>
          <CalendarClock size={16} style={{ color: 'var(--color-info-ios)' }} />
          {selected.size > 0 ? `${selected.size} station${selected.size > 1 ? 's' : ''} selected` : 'Bulk plan visits'}
        </div>
        <label className="text-[11px]" style={{ color: c.textMuted }}>Scheduled date
          <input data-testid="bl-plan-date" type="date" value={planDate} onChange={e => setPlanDate(e.target.value)}
            className="block px-2 py-1.5 text-sm rounded-md border bg-transparent" style={{ borderColor: c.border, color: c.text }} />
        </label>
        <label className="text-[11px]" style={{ color: c.textMuted }}>Window end (optional)
          <input data-testid="bl-plan-window" type="date" value={planWindowEnd} onChange={e => setPlanWindowEnd(e.target.value)}
            className="block px-2 py-1.5 text-sm rounded-md border bg-transparent" style={{ borderColor: c.border, color: c.text }} />
        </label>
        <label className="text-[11px]" style={{ color: c.textMuted }}>Engineer
          <select data-testid="bl-plan-engineer" value={planEngineer} onChange={e => setPlanEngineer(e.target.value)}
            className="block px-2 py-1.5 text-sm rounded-md border bg-transparent min-w-[180px]" style={{ borderColor: c.border, color: c.text }}>
            <option value="">— Unallocated —</option>
            {engineers.map(e => <option key={e.id} value={e.id}>{e.full_name}{typeof e.planned_visits === 'number' ? ` (${e.planned_visits})` : ''}</option>)}
          </select>
        </label>
        <Button onClick={() => planVisits(false)} disabled={planning || selected.size === 0} icon={CalendarClock} data-testid="bl-plan-btn">
          {planning ? 'Planning…' : `Plan ${selected.size || ''} visit${selected.size === 1 ? '' : 's'}`}
        </Button>
        <Button variant="ghost" size="sm" onClick={reassign} disabled={planning || selected.size === 0} data-testid="bl-reassign-btn">Reassign engineer</Button>
        {selected.size > 0 && <Button variant="ghost" size="sm" onClick={clearSel} data-testid="bl-clear-sel">Clear</Button>}
      </div>
      {planMsg && (
        <div className="rounded-lg border p-3 text-sm" style={{ borderColor: c.border, background: 'var(--color-surface)' }} data-testid="bl-plan-result">
          {planMsg.reassigned != null ? (
            <span style={{ color: 'var(--color-success-alt)' }}><CheckCircle size={14} className="inline mr-1" />Reassigned {planMsg.reassigned} visit(s) to {planMsg.engineer || 'Unallocated'}.</span>
          ) : (
            <>
              {planMsg.created > 0 ? (
                <span style={{ color: 'var(--color-success-alt)' }}><CheckCircle size={14} className="inline mr-1" />Planned {planMsg.created} visit(s) for the {planMsg.cycle} service cycle.</span>
              ) : (
                <span style={{ color: 'var(--color-accent-amber)' }}><AlertTriangle size={14} className="inline mr-1" />No new visits planned — every selected station already has a {planMsg.cycle} visit.</span>
              )}
              {planMsg.skipped?.length > 0 && (
                <div className="mt-1" style={{ color: 'var(--color-accent-amber)' }}>
                  <AlertTriangle size={14} className="inline mr-1" />{planMsg.skipped.length} skipped (duplicate protection): {planMsg.skipped.slice(0, 3).map(s => s.station_name || s.site_id).join(', ')}{planMsg.skipped.length > 3 ? '…' : ''}{' '}
                  <button className="ml-2 underline" data-testid="bl-plan-force" onClick={() => { setSelected(new Set(planMsg.skipped.map(s => s.site_id))); }}>re-select skipped</button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Station matrix */}
      <div className="rounded-xl border" style={{ borderColor: c.border }}>
        <div className="flex flex-wrap items-center gap-2 p-3 border-b" style={{ borderColor: c.border }}>
          <div className="relative flex-1 min-w-[180px]">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: c.textMuted }} />
            <input data-testid="bl-station-search" value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search station, town, contact…"
              className="w-full pl-8 pr-3 py-1.5 text-sm rounded-md border bg-transparent"
              style={{ borderColor: c.border, color: c.text }} />
          </div>
          <select data-testid="bl-station-status-filter" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="px-2 py-1.5 text-sm rounded-md border bg-transparent" style={{ borderColor: c.border, color: c.text }}>
            <option value="">All statuses</option>
            {Object.entries(STATUS_META).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
          </select>
          <Button variant="ghost" size="sm" icon={Download} onClick={exportCsv} data-testid="bl-station-export">Export</Button>
          {certStatusFilter && (
            <button data-testid="bl-cert-filter-clear" onClick={() => setCertStatusFilter('')}
              className="text-xs px-2 py-1 rounded-full flex items-center gap-1"
              style={{ background: 'var(--color-info-ios)22', color: 'var(--color-info-ios)' }}>
              Certificate: {certStatusFilter.replace(/_/g, ' ')} ✕
            </button>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: c.textMuted }} className="text-[11px] uppercase">
                <th className="px-3 py-2 w-8">
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} data-testid="bl-select-all" aria-label="Select all stations" />
                </th>
                {stationCols.map(([col, label]) => (
                  <th key={col} className="text-left font-semibold px-3 py-2 cursor-pointer whitespace-nowrap"
                    onClick={() => setSortCol(col)} data-testid={`bl-sort-${col}`}>
                    <span className="inline-flex items-center gap-1">{label}
                      {sort === col && (direction === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={stationCols.length + 1} className="px-3 py-8 text-center" style={{ color: c.textMuted }}>Loading…</td></tr>
              ) : stations.length === 0 ? (
                <tr><td colSpan={stationCols.length + 1} className="px-3 py-8 text-center" style={{ color: c.textMuted }} data-testid="bl-station-empty">No stations match.</td></tr>
              ) : stations.map(r => (
                <tr key={r.site_id} className="border-t" style={{ borderColor: c.border }} data-testid={`bl-station-row-${r.site_id}`}>
                  <td className="px-3 py-2">
                    <input type="checkbox" checked={selected.has(r.site_id)} onChange={() => toggleRow(r.site_id)}
                      data-testid={`bl-select-${r.site_id}`} aria-label={`Select ${r.station_name}`} />
                  </td>
                  <td className="px-3 py-2 font-medium whitespace-nowrap" style={{ color: c.text }}>
                    {r.visit_id && ['scheduled', 'in_progress', 'travelling', 'on_site', 'follow_up_required'].includes(r.visit_status) ? (
                      <a href={`/blue-light/visit/${r.visit_id}`} target="_blank" rel="noreferrer"
                        data-testid={`bl-open-visit-${r.site_id}`} className="underline decoration-dotted"
                        style={{ color: 'var(--color-info-ios)' }}>{r.station_name}</a>
                    ) : r.station_name}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap" style={{ color: c.textDim }}>{r.address}</td>
                  <td className="px-3 py-2 whitespace-nowrap" style={{ color: c.textDim }}>{r.contact_name}</td>
                  <td className="px-3 py-2 whitespace-nowrap" style={{ color: c.textDim }}>{r.telephone}</td>
                  <td className="px-3 py-2 text-center" style={{ color: c.text }}>{r.asset_count}</td>
                  <td className="px-3 py-2 text-center" style={{ color: r.treadmill_count ? 'var(--color-info-ios)' : c.textMuted }}>{r.treadmill_count}</td>
                  <td className="px-3 py-2 whitespace-nowrap" style={{ color: c.textDim }}>{r.next_service_due || '—'}</td>
                  <td className="px-3 py-2 whitespace-nowrap" style={{ color: c.textDim }}>{r.scheduled_date || '—'}</td>
                  <td className="px-3 py-2 whitespace-nowrap" style={{ color: c.textDim }}>{r.assigned_engineer_name || '—'}</td>
                  <td className="px-3 py-2"><StatusPill status={r.visit_status} /></td>
                  <td className="px-3 py-2"><CellPill value={r.calibration_status} /></td>
                  <td className="px-3 py-2 text-center" style={{ color: r.faults_raised ? 'var(--color-danger)' : c.textMuted }}>{r.faults_raised}</td>
                  <td className="px-3 py-2"><CellPill value={r.certificate_status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ConfigForm({ cfg, setCfg, meta, c }) {
  const set = (k, v) => setCfg(p => ({ ...p, [k]: v }));
  const numList = (str) => str.split(',').map(x => parseFloat(x.trim())).filter(x => !isNaN(x));
  const inp = 'w-full px-2 py-1.5 text-sm rounded-md border bg-transparent';
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <label className="text-xs" style={{ color: c.textMuted }}>Customer type
        <select data-testid="bl-cfg-customer-type" className={inp} style={{ borderColor: c.border, color: c.text }}
          value={cfg.customer_type} onChange={e => set('customer_type', e.target.value)}>
          {meta.customer_types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </label>
      <label className="text-xs" style={{ color: c.textMuted }}>Service frequency (months)
        <input data-testid="bl-cfg-frequency" type="number" min="1" className={inp} style={{ borderColor: c.border, color: c.text }}
          value={cfg.service_frequency_months} onChange={e => set('service_frequency_months', parseInt(e.target.value || '6', 10))} />
      </label>
      <label className="text-xs" style={{ color: c.textMuted }}>Speed points (mph, comma-separated)
        <input data-testid="bl-cfg-speed" className={inp} style={{ borderColor: c.border, color: c.text }}
          defaultValue={(cfg.speed_points_mph || []).join(', ')} onBlur={e => set('speed_points_mph', numList(e.target.value))} />
      </label>
      <label className="text-xs" style={{ color: c.textMuted }}>Incline points (%, comma-separated)
        <input data-testid="bl-cfg-incline" className={inp} style={{ borderColor: c.border, color: c.text }}
          defaultValue={(cfg.incline_points_pct || []).join(', ')} onBlur={e => set('incline_points_pct', numList(e.target.value))} />
      </label>
      <label className="text-xs" style={{ color: c.textMuted }}>Failure tolerance (% of target)
        <input data-testid="bl-cfg-tolerance" type="number" step="0.1" className={inp} style={{ borderColor: c.border, color: c.text }}
          value={cfg.tolerance_pct} onChange={e => set('tolerance_pct', parseFloat(e.target.value || '5'))} />
      </label>
      <label className="text-xs" style={{ color: c.textMuted }}>Certificate approval
        <select data-testid="bl-cfg-approval" className={inp} style={{ borderColor: c.border, color: c.text }}
          value={cfg.certificate_approval_mode} onChange={e => set('certificate_approval_mode', e.target.value)}>
          <option value="auto_send">Auto-send after completion</option>
          <option value="office_review">Office review before send</option>
          <option value="manager_approval">Manager approval</option>
        </select>
      </label>
      <label className="text-xs md:col-span-2" style={{ color: c.textMuted }}>Certificate recipients (emails, comma-separated)
        <input data-testid="bl-cfg-recipients" className={inp} style={{ borderColor: c.border, color: c.text }}
          defaultValue={(cfg.certificate_recipients || []).join(', ')}
          onBlur={e => set('certificate_recipients', e.target.value.split(',').map(x => x.trim()).filter(Boolean))} />
      </label>
      <label className="text-xs md:col-span-2" style={{ color: c.textMuted }}>Customer logo URL (crest shown on the certificate)
        <input data-testid="bl-cfg-logo" className={inp} style={{ borderColor: c.border, color: c.text }}
          defaultValue={cfg.customer_logo_url || ''} placeholder="https://…/crest.png"
          onBlur={e => set('customer_logo_url', e.target.value.trim())} />
      </label>
      <label className="text-xs md:col-span-2 flex items-center gap-2 mt-1" style={{ color: c.textMuted }}>
        <input data-testid="bl-cfg-calibration-required" type="checkbox" checked={!!cfg.calibration_required}
          onChange={e => set('calibration_required', e.target.checked)} />
        Treadmill calibration required on this contract
      </label>
    </div>
  );
}
