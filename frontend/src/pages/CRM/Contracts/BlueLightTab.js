import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Radio, Save, Search, Download, Filter, MapPin, Gauge, AlertTriangle,
  CheckCircle, Clock, CalendarClock, FileCheck2, ChevronUp, ChevronDown,
} from 'lucide-react';
import Button from '@/components/shared/Button';

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
  const [sort, setSort] = useState('station_name');
  const [direction, setDirection] = useState('asc');
  const [saving, setSaving] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [meta, setMeta] = useState(null);
  const [cfg, setCfg] = useState(null);

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
      const params = new URLSearchParams({ search: debouncedSearch, status: statusFilter, sort, direction });
      const res = await axios.get(`${API}/crm/v2/contracts/${contractId}/stations?${params}`, { headers: headers() });
      setStations(res.data.stations || []);
    } catch (e) { setStations([]); } finally { setLoading(false); }
  }, [API, headers, contractId, debouncedSearch, statusFilter, sort, direction]);

  useEffect(() => { loadOverview(); }, [loadOverview]);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => { if (isBL) loadStations(); }, [isBL, loadStations]);

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
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: c.textMuted }} className="text-[11px] uppercase">
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
                <tr><td colSpan={stationCols.length} className="px-3 py-8 text-center" style={{ color: c.textMuted }}>Loading…</td></tr>
              ) : stations.length === 0 ? (
                <tr><td colSpan={stationCols.length} className="px-3 py-8 text-center" style={{ color: c.textMuted }} data-testid="bl-station-empty">No stations match.</td></tr>
              ) : stations.map(r => (
                <tr key={r.site_id} className="border-t" style={{ borderColor: c.border }} data-testid={`bl-station-row-${r.site_id}`}>
                  <td className="px-3 py-2 font-medium whitespace-nowrap" style={{ color: c.text }}>{r.station_name}</td>
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
      <label className="text-xs md:col-span-2 flex items-center gap-2 mt-1" style={{ color: c.textMuted }}>
        <input data-testid="bl-cfg-calibration-required" type="checkbox" checked={!!cfg.calibration_required}
          onChange={e => set('calibration_required', e.target.checked)} />
        Treadmill calibration required on this contract
      </label>
    </div>
  );
}
