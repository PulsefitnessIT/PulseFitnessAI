import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import SiconOnboardingSync from '@/pages/MasterAdmin/SiconOnboardingSync';
import {
  Activity, CheckCircle, XCircle, Clock, ArrowRight,
  RefreshCw, Copy, AlertTriangle, Loader2, Settings,
  ArrowDownToLine, ArrowUpFromLine, Zap, Shield,
  ChevronDown, ChevronUp, RotateCcw, Wifi, WifiOff,
  Package, Search, ChevronLeft, ChevronRight
} from 'lucide-react';

// ── Field-mapping reference data (Sicon spec §3.1, §3.2, §3.3) ──────
// Direction: 'outbound' (Pulse Fitness → Sicon), 'inbound' (Sicon → Pulse Fitness)
// Status: 'mapped' (auto), 'lookup' (resolved on first sync), 'pending'
//
// Source of truth: /app/memory/SICON_INTEGRATION_SPEC.md
const SICON_FIELD_MAPPINGS = [
  // ── Service Case header (outbound) ───────────────────────────────
  { source: 'issue.id',                          target: 'AnalysisField4',         direction: 'outbound', status: 'mapped' },
  { source: 'issue.machine_type + serial_number', target: 'Summary',                direction: 'outbound', status: 'mapped' },
  { source: 'issue.description',                  target: 'Description',            direction: 'outbound', status: 'mapped' },
  { source: 'issue.created_at',                   target: 'CallDate',               direction: 'outbound', status: 'mapped' },
  { source: 'issue.severity',                     target: 'PriorityID + PriorityName', direction: 'outbound', status: 'lookup' },
  { source: 'issue.fault_type',                   target: 'CaseTypeID + CaseTypeName', direction: 'outbound', status: 'lookup' },
  { source: 'issue.status',                       target: 'SiSMDocumentStatusID',   direction: 'inbound',  status: 'mapped' },
  { source: 'issue.sla_category',                 target: 'AnalysisField6',         direction: 'outbound', status: 'mapped' },
  // ── Site / Customer (outbound, with Sage lookup) ─────────────────
  { source: 'site.name + address.*',              target: 'LocationPostalName + LocationAddressLine1-4 + LocationCity + LocationCounty + LocationPostCode', direction: 'outbound', status: 'mapped' },
  { source: 'site.sicon_sublocation_id',          target: 'SubLocation.SiconSubLocationID', direction: 'outbound', status: 'lookup' },
  { source: 'company.sage_customer_account_id',   target: 'SLCustomerAccountID',    direction: 'outbound', status: 'lookup' },
  { source: 'company.sage_customer_reference',    target: 'CustomerReference',      direction: 'outbound', status: 'lookup' },
  // ── Contact (outbound) ───────────────────────────────────────────
  { source: 'issue.created_by_name',              target: 'ContactName',            direction: 'outbound', status: 'mapped' },
  { source: 'user.email',                         target: 'ContactEmail',           direction: 'outbound', status: 'mapped' },
  { source: 'user.phone',                         target: 'ContactPhoneNumber',     direction: 'outbound', status: 'mapped' },
  // ── Equipment + Contract ─────────────────────────────────────────
  { source: 'equipment.serial_number',            target: 'EquipmentIDs[]',         direction: 'outbound', status: 'lookup' },
  { source: 'contract.sicon_contract_id',         target: 'SiconContractID',        direction: 'outbound', status: 'lookup' },
  { source: 'contract.sicon_contract_number',     target: 'SiconContractNumber',    direction: 'outbound', status: 'lookup' },
  // ── AI triage payload (outbound, custom fields) ──────────────────
  { source: 'ai_triage.summary',                  target: 'AnalysisField1',         direction: 'outbound', status: 'mapped' },
  { source: 'ai_triage.severity',                 target: 'AnalysisField2',         direction: 'outbound', status: 'mapped' },
  { source: 'ai_triage.recommended_parts',        target: 'AnalysisField3',         direction: 'outbound', status: 'mapped' },
  { source: 'organization.name',                  target: 'AnalysisField5',         direction: 'outbound', status: 'mapped' },
  // ── Sicon-owned fields (inbound) ─────────────────────────────────
  { source: '—',                                  target: 'SiSMCaseId',             direction: 'inbound',  status: 'mapped' },
  { source: '—',                                  target: 'CaseNumber',             direction: 'inbound',  status: 'mapped' },
  { source: '—',                                  target: 'AssignedToSageUserID + Name', direction: 'inbound', status: 'mapped' },
  { source: '—',                                  target: 'InternalTeamID + Name',  direction: 'inbound',  status: 'mapped' },
  { source: '—',                                  target: 'ExternalTeamID + Name',  direction: 'inbound',  status: 'mapped' },
  // ── Appointments (§3.2, inbound) ─────────────────────────────────
  { source: '—',                                  target: 'Appointments[].SiconAppointmentID',     direction: 'inbound', status: 'mapped' },
  { source: 'engineer_assigned_at',               target: 'Appointments[].ScheduledStartDate',     direction: 'inbound', status: 'mapped' },
  { source: 'work_completed_at',                  target: 'Appointments[].ScheduledEndDate',       direction: 'inbound', status: 'mapped' },
  { source: 'engineer_notes',                     target: 'Appointments[].WorkDoneDescription',    direction: 'inbound', status: 'mapped' },
  { source: '—',                                  target: 'Appointments[].FurtherAction',          direction: 'inbound', status: 'mapped' },
  { source: '—',                                  target: 'Appointments[].ArrivalSignee',          direction: 'inbound', status: 'mapped' },
  // ── Tracking notes (§3.3, bidirectional) ─────────────────────────
  { source: 'issue.timeline[]',                   target: 'TrackingNotes[]',        direction: 'outbound', status: 'mapped' },
  { source: '—',                                  target: 'TrackingNotes[]',        direction: 'inbound',  status: 'mapped' },
];

const ORBIT4_FIELD_MAPPINGS = [
  { source: 'ticket.number',                              target: 'Case Subject (with prefix)', status: 'mapped' },
  { source: 'ticket.description',                         target: 'Case Description',           status: 'mapped' },
  { source: 'ticket.asset.serial_number',                 target: 'Asset Reference',            status: 'mapped' },
  { source: 'ticket.asset.brand + range + product',       target: 'Asset Name',                 status: 'mapped' },
  { source: 'ticket.asset.qr_code',                       target: 'Asset QR Code',              status: 'mapped' },
  { source: 'ticket.priority',                            target: 'Case Priority',              status: 'mapped' },
  { source: 'ticket.gym_operator.site_name',              target: 'Site / Location',            status: 'mapped' },
  { source: 'ticket.gym_operator.first_name + last_name', target: 'Contact Name',               status: 'mapped' },
  { source: 'ticket.gym_operator.email',                  target: 'Contact Email',              status: 'mapped' },
  { source: 'ticket.number',                              target: 'External Reference',         status: 'mapped' },
  { source: 'ticket.status',                              target: 'Case Status',                status: 'mapped' },
  { source: '—',                                          target: 'Assigned Team',              status: 'pending' },
  { source: '—',                                          target: 'Category',                   status: 'pending' },
];

const IntegrationAdminPanel = ({ integrationId, title, icon: Icon, color, initialSection, hideHeader = false }) => {
  const { API } = useAuth();
  const [config, setConfig] = useState(null);
  const [stats, setStats] = useState(null);
  const [logs, setLogs] = useState([]);
  const [bridgeRecords, setBridgeRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState(initialSection || 'overview');
  const [editConfig, setEditConfig] = useState({});
  const [saving, setSaving] = useState(false);
  const [expandedLog, setExpandedLog] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [orbit4Assets, setOrbit4Assets] = useState([]);
  const [assetsMeta, setAssetsMeta] = useState({});
  const [assetsPage, setAssetsPage] = useState(1);
  const [assetsSearch, setAssetsSearch] = useState('');
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [siconMappings, setSiconMappings] = useState(null);
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [configRes, statsRes, logsRes] = await Promise.all([
        axios.get(`${API}/integrations/${integrationId}`, { headers }),
        axios.get(`${API}/integrations/${integrationId}/stats`, { headers }),
        axios.get(`${API}/integrations/${integrationId}/logs?limit=20`, { headers }),
      ]);
      setConfig(configRes.data);
      setStats(statsRes.data);
      setLogs(logsRes.data.logs || []);
      setEditConfig({
        enabled: configRes.data.enabled,
        api_token: configRes.data.api_token || '',
        webhook_secret: configRes.data.webhook_secret || '',
        base_url: configRes.data.base_url || '',
        credentials: configRes.data.credentials || {},
        branding: configRes.data.branding || { display_name: 'Pulse Fitness', contact_email: '', production_webhook_domain: '', user_agent: 'PulseFitness-ServiceBridge/1.0' },
      });
      if (integrationId === 'sicon') {
        try {
          const mapRes = await axios.get(`${API}/sicon/field-mapping`, { headers });
          setSiconMappings(mapRes.data);
        } catch { setSiconMappings(null); }
      }
    } catch (err) {
      console.error('Load failed:', err);
    }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: context helpers re-create each render but read the latest token / handler at call time; adding them would invalidate the memo every render and break the optimisation.
  }, [API, integrationId]);

  const loadBridgeRecords = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/integrations/bridge/records?limit=20`, { headers });
      setBridgeRecords(res.data.records || []);
    } catch {}
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: context helpers re-create each render but read the latest token / handler at call time; adding them would invalidate the memo every render and break the optimisation.
  }, [API]);

  useEffect(() => { loadData(); loadBridgeRecords(); }, [loadData, loadBridgeRecords]);

  const testConnection = async () => {
    setTestingConnection(true);
    try {
      const url = integrationId === 'sicon'
        ? `${API}/integrations/sicon/test-connection`
        : `${API}/integrations/orbit4/test-connection`;
      const res = await axios.post(url, {}, { headers });
      setConnectionStatus(res.data);
      if (res.data.status === 'connected') notify.success(res.data.message || 'Connected');
      else notify.error(res.data.message);
      if (integrationId === 'sicon') loadData();
    } catch { notify.error('Connection test failed'); setConnectionStatus({ status: 'error', message: 'Request failed' }); }
    setTestingConnection(false);
  };

  const loadOrbit4Assets = useCallback(async (page = 1, search = '') => {
    setLoadingAssets(true);
    try {
      const params = new URLSearchParams({ page, per_page: 15 });
      if (search) params.set('search', search);
      const res = await axios.get(`${API}/integrations/orbit4/assets?${params}`, { headers });
      setOrbit4Assets(res.data.assets || []);
      setAssetsMeta(res.data.meta || {});
    } catch { notify.error('Failed to load assets'); }
    setLoadingAssets(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: context helpers re-create each render but read the latest token / handler at call time; adding them would invalidate the memo every render and break the optimisation.
  }, [API]);

  useEffect(() => {
    if (activeSection === 'assets' && integrationId === 'orbit4') loadOrbit4Assets(assetsPage, assetsSearch);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [activeSection, assetsPage]);

  // Keep the inner section in sync with the parent-controlled tab. When this
  // panel is embedded with hideHeader (e.g. SiconIntegrationPage), its section
  // nav is hidden and the only driver is the initialSection prop — which useState
  // reads once on mount. Without this, switching the outer Event Log/Configuration/
  // Field Mappings tabs left the panel stuck on whichever section mounted first.
  useEffect(() => {
    if (initialSection) setActiveSection(initialSection);
  }, [initialSection]);


  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/integrations/${integrationId}`, editConfig, { headers });
      notify.success('Configuration saved');
      loadData();
    } catch { notify.error('Failed to save'); }
    setSaving(false);
  };

  const handleToggle = async (enabled) => {
    try {
      await axios.put(`${API}/integrations/${integrationId}`, { enabled }, { headers });
      notify.success(enabled ? 'Integration enabled' : 'Integration disabled');
      loadData();
    } catch { notify.error('Failed to toggle'); }
  };

  const handleRetry = async (recordId) => {
    try {
      await axios.post(`${API}/integrations/bridge/${recordId}/retry`, {}, { headers });
      notify.success('Retry successful');
      loadBridgeRecords();
      loadData();
    } catch (e) { notifyApiError(notify, e, 'Retry failed'); }
  };

  const copyWebhookUrl = () => {
    const url = `${window.location.origin}/api/webhooks/${integrationId}`;
    navigator.clipboard.writeText(url);
    notify.success('Webhook URL copied');
  };

  if (loading) return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="animate-spin text-zinc-400 dark:text-zinc-500" size={24} />
    </div>
  );

  const sections = [
    { id: 'overview', label: 'Overview' },
    ...(integrationId === 'orbit4' ? [{ id: 'assets', label: `Live Assets (${connectionStatus?.total_assets || '...'})` }] : []),
    { id: 'logs', label: `Event Log (${stats?.total_events || 0})` },
    ...(integrationId === 'orbit4' ? [{ id: 'bridge', label: `Bridge Records (${bridgeRecords.length})` }] : []),
    { id: 'config', label: 'Configuration' },
    { id: 'mappings', label: 'Field Mappings' },
  ];

  return (
    <div className="space-y-6" data-testid={`integration-${integrationId}`}>
      {/* Header */}
      {!hideHeader && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${color}`}>
              <Icon size={24} className="text-white" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">{title}</h2>
              <p className="text-sm text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">{config?.description}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-sm text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">{config?.enabled ? 'Active' : 'Inactive'}</span>
              <Switch checked={config?.enabled || false} onCheckedChange={handleToggle} data-testid={`toggle-${integrationId}`} />
            </div>
            <Badge className={config?.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 dark:text-zinc-500'}>
              {config?.enabled ? 'Connected' : 'Disconnected'}
            </Badge>
          </div>
        </div>
      )}

      {/* Section Nav */}
      {!hideHeader && (
        <div className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800 pb-0">
          {sections.map(s => (
            <button key={s.id} onClick={() => setActiveSection(s.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeSection === s.id ? 'border-zinc-900 text-zinc-900 dark:text-zinc-100' : 'border-transparent text-zinc-500 dark:text-zinc-400 dark:text-zinc-500 hover:text-zinc-700 dark:text-zinc-300'}`}
              data-testid={`section-${s.id}`}>
              {s.label}
            </button>
          ))}
        </div>
      )}

      {/* Overview */}
      {activeSection === 'overview' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard label="Total Events" value={stats?.total_events || 0} icon={Activity} color="text-blue-600 bg-blue-50" />
            <StatCard label="Successful" value={stats?.successful || 0} icon={CheckCircle} color="text-emerald-600 bg-emerald-50" />
            <StatCard label="Errors" value={stats?.errors || 0} icon={XCircle} color="text-red-600 bg-red-50" />
            <StatCard label="Last 24h" value={stats?.last_24h || 0} icon={Clock} color="text-amber-600 bg-amber-50" />
          </div>

          {stats?.success_rate > 0 && (
            <Card className="p-5 border-zinc-200 dark:border-zinc-800">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Success Rate</span>
                <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{stats.success_rate}%</span>
              </div>
              <div className="w-full h-2 bg-zinc-100 dark:bg-zinc-800 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500 rounded-full transition-all" style={{ width: `${stats.success_rate}%` }} />
              </div>
            </Card>
          )}

          {/* Connection Test */}
          {integrationId === 'orbit4' && (
            <Card className="p-5 border-zinc-200 dark:border-zinc-800">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">API Connection</h4>
                <Button size="sm" onClick={testConnection} disabled={testingConnection} data-testid="test-connection-btn"
                  className={connectionStatus?.status === 'connected' ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : 'bg-blue-600 hover:bg-blue-700 text-white'}>
                  {testingConnection ? <Loader2 size={14} className="animate-spin mr-1" /> : connectionStatus?.status === 'connected' ? <Wifi size={14} className="mr-1" /> : <WifiOff size={14} className="mr-1" />}
                  {testingConnection ? 'Testing...' : connectionStatus?.status === 'connected' ? 'Connected' : 'Test Connection'}
                </Button>
              </div>
              {connectionStatus && (
                <div className={`rounded-lg p-3 text-sm ${connectionStatus.status === 'connected' ? 'bg-emerald-50 border border-emerald-200 text-emerald-700' : 'bg-red-50 border border-red-200 text-red-700'}`}>
                  <div className="flex items-center gap-2">
                    {connectionStatus.status === 'connected' ? <CheckCircle size={16} /> : <XCircle size={16} />}
                    <span className="font-medium">{connectionStatus.message}</span>
                  </div>
                  {connectionStatus.total_assets > 0 && (
                    <div className="mt-2 flex items-center gap-4 text-xs">
                      <span><strong>{connectionStatus.total_assets.toLocaleString()}</strong> assets</span>
                      <span>Rate limit remaining: <strong>{connectionStatus.rate_limit}</strong></span>
                      <span>Base URL: <code className="bg-emerald-100 px-1 rounded">{connectionStatus.base_url}</code></span>
                    </div>
                  )}
                </div>
              )}
              {!connectionStatus && <p className="text-xs text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">Click "Test Connection" to verify the API token and endpoint.</p>}
            </Card>
          )}

          {stats?.last_event && (
            <Card className="p-5 border-zinc-200 dark:border-zinc-800">
              <p className="text-xs text-zinc-400 dark:text-zinc-500 uppercase tracking-wider mb-1">Last Event</p>
              <div className="flex items-center gap-2">
                {stats.last_event.success ? <CheckCircle size={14} className="text-emerald-500" /> : <XCircle size={14} className="text-red-500" />}
                <span className="text-sm text-zinc-700 dark:text-zinc-300">{stats.last_event.event_type}</span>
                <span className="text-xs text-zinc-400 dark:text-zinc-500 ml-auto">{new Date(stats.last_event.timestamp).toLocaleString()}</span>
              </div>
            </Card>
          )}

          {/* Quick Info */}
          {integrationId === 'orbit4' && (
            <Card className="p-5 border-zinc-200 dark:border-zinc-800">
              <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">Webhook Endpoint</h4>
              {config?.branding?.production_webhook_domain ? (
                <>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 dark:text-zinc-500 mb-2">Production URL (visible to Orbit 4 as <strong>{config.branding.display_name || 'Pulse Fitness'}</strong>):</p>
                  <div className="flex items-center gap-2 mb-3">
                    <code className="flex-1 text-xs bg-emerald-50 border border-emerald-200 rounded px-3 py-2 text-emerald-700 font-mono" data-testid="webhook-url-production">
                      {config.branding.production_webhook_domain.replace(/\/$/, '')}/api/webhooks/orbit4
                    </code>
                    <Button size="sm" variant="outline" onClick={() => {
                      navigator.clipboard.writeText(`${config.branding.production_webhook_domain.replace(/\/$/, '')}/api/webhooks/orbit4`);
                      notify.success('Production URL copied');
                    }}>
                      <Copy size={14} />
                    </Button>
                  </div>
                  <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">Internal URL (for testing only):</p>
                </>
              ) : (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-3">
                  <p className="text-xs text-amber-700">
                    <AlertTriangle size={12} className="inline mr-1" />
                    <strong>No production domain configured.</strong> Orbit 4 will see the internal URL below. Set a Pulse Fitness domain in the Branding section to white-label this endpoint.
                  </p>
                </div>
              )}
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded px-3 py-2 text-zinc-700 dark:text-zinc-300 font-mono" data-testid="webhook-url">
                  {window.location.origin}/api/webhooks/orbit4
                </code>
                <Button size="sm" variant="outline" onClick={copyWebhookUrl} data-testid="copy-webhook-url">
                  <Copy size={14} />
                </Button>
              </div>
              <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-2">Configure the <strong>production URL</strong> in Orbit 4 → Profile → Webhooks. Subscribe to: ticket.created, ticket.updated, ticket.closed</p>
            </Card>
          )}

          {/* Visibility Notice */}
          <Card className="p-5 border-zinc-200 dark:border-zinc-800 bg-blue-50 border-blue-200">
            <div className="flex items-start gap-3">
              <Shield size={18} className="text-blue-600 flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold text-blue-900">White-Label Identity</h4>
                <p className="text-xs text-blue-700 mt-1">
                  Orbit 4 sees this integration as <strong>"{config?.branding?.display_name || 'Pulse Fitness'}"</strong> — not Pulse Fitness AI.
                  All API calls, webhook responses, and User-Agent headers identify as {config?.branding?.display_name || 'Pulse Fitness'}.
                  {!config?.branding?.production_webhook_domain && ' Configure a production domain in Branding to fully white-label the webhook URL.'}
                </p>
              </div>
            </div>
          </Card>

          {/* Data Flow */}
          <Card className="p-5 border-zinc-200 dark:border-zinc-800">
            <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-4">Data Flow</h4>
            <div className="flex items-center justify-between gap-2">
              <FlowBox label="Orbit 4" sub="Fault logged" icon={ArrowDownToLine} active={integrationId === 'orbit4' && config?.enabled} />
              <ArrowRight size={20} className="text-zinc-300 flex-shrink-0" />
              <FlowBox label="Pulse Fitness AI" sub="Middleware" icon={Zap} active={true} highlight />
              <ArrowRight size={20} className="text-zinc-300 flex-shrink-0" />
              <FlowBox label="Sicon Service" sub="Case created" icon={ArrowUpFromLine} active={integrationId === 'sicon' && config?.enabled} />
            </div>
          </Card>
        </div>
      )}

      {/* Event Log */}
      {activeSection === 'logs' && (
        <div className="space-y-2">
          <div className="flex justify-end">
            <Button size="sm" variant="outline" onClick={loadData}><RefreshCw size={14} className="mr-1" /> Refresh</Button>
          </div>
          {logs.length === 0 ? (
            <Card className="p-8 text-center border-zinc-200 dark:border-zinc-800">
              <Activity size={32} className="text-zinc-300 mx-auto mb-2" />
              <p className="text-sm text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">No events recorded yet</p>
            </Card>
          ) : (
            <div className="space-y-1">
              {logs.map((log, i) => (
                <Card key={log.id || i} className={`border-zinc-200 dark:border-zinc-800 overflow-hidden cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800 dark:bg-zinc-900/50 transition-colors ${!log.success ? 'border-l-2 border-l-red-400' : ''}`}
                  onClick={() => setExpandedLog(expandedLog === i ? null : i)}>
                  <div className="p-3 flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${log.success ? 'bg-emerald-500' : 'bg-red-500'}`} />
                    <DirectionBadge direction={log.direction} />
                    <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300 flex-1">{log.summary}</span>
                    <Badge className="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 text-xs">{log.event_type}</Badge>
                    <span className="text-xs text-zinc-400 dark:text-zinc-500">{new Date(log.timestamp).toLocaleString()}</span>
                    {expandedLog === i ? <ChevronUp size={14} className="text-zinc-400 dark:text-zinc-500" /> : <ChevronDown size={14} className="text-zinc-400 dark:text-zinc-500" />}
                  </div>
                  {expandedLog === i && (
                    <div className="px-3 pb-3 border-t border-zinc-100 dark:border-zinc-800 pt-2 space-y-2" data-testid={`log-detail-${i}`}>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                        <div><span className="text-zinc-400 dark:text-zinc-500">Event</span> <span className="text-zinc-700 dark:text-zinc-300 font-medium">{log.event_type || '—'}</span></div>
                        <div><span className="text-zinc-400 dark:text-zinc-500">Direction</span> <span className="text-zinc-700 dark:text-zinc-300 font-medium">{log.direction || 'internal'}</span></div>
                        <div><span className="text-zinc-400 dark:text-zinc-500">Status</span> <span className={`font-medium ${log.success ? 'text-emerald-600' : 'text-red-600'}`}>{log.success ? 'Success' : 'Failed'}</span></div>
                        <div><span className="text-zinc-400 dark:text-zinc-500">Time</span> <span className="text-zinc-700 dark:text-zinc-300 font-medium">{log.timestamp ? new Date(log.timestamp).toLocaleString() : '—'}</span></div>
                      </div>
                      {log.summary && <p className="text-xs text-zinc-600 dark:text-zinc-400"><span className="text-zinc-400 dark:text-zinc-500">Summary: </span>{log.summary}</p>}
                      {log.error && <p className="text-xs text-red-600">Error: {log.error}</p>}
                      {log.payload && Object.keys(log.payload).length > 0 && (
                        <pre className="text-xs bg-zinc-50 dark:bg-zinc-900/50 rounded p-2 overflow-x-auto text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 max-h-40">
                          {JSON.stringify(log.payload, null, 2)}
                        </pre>
                      )}
                      {!log.error && (!log.payload || Object.keys(log.payload).length === 0) && (
                        <p className="text-xs text-zinc-400 dark:text-zinc-500 italic">No additional payload recorded for this event.</p>
                      )}
                    </div>
                  )}
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Bridge Records (Orbit 4 only) */}
      {activeSection === 'bridge' && (
        <div className="space-y-2">
          <div className="flex justify-end">
            <Button size="sm" variant="outline" onClick={loadBridgeRecords}><RefreshCw size={14} className="mr-1" /> Refresh</Button>
          </div>
          {bridgeRecords.length === 0 ? (
            <Card className="p-8 text-center border-zinc-200 dark:border-zinc-800">
              <ArrowRight size={32} className="text-zinc-300 mx-auto mb-2" />
              <p className="text-sm text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">No bridge records yet. Records appear when Orbit 4 tickets are received.</p>
            </Card>
          ) : (
            <div className="space-y-2">
              {bridgeRecords.map(rec => (
                <Card key={rec.id} className="border-zinc-200 dark:border-zinc-800 p-5" data-testid={`bridge-${rec.id}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium text-zinc-900 dark:text-zinc-100 text-sm">{rec.sicon_data?.subject || 'No subject'}</span>
                        <BridgeStatusBadge status={rec.status} />
                      </div>
                      <div className="flex items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">
                        <span>Orbit 4: <strong>{rec.orbit4_ticket_id}</strong></span>
                        {rec.sicon_case_id && <span>Sicon: <strong>{rec.sicon_case_id}</strong></span>}
                        <span>{rec.sicon_data?.asset_serial || ''}</span>
                        <span>{rec.sicon_data?.location || ''}</span>
                      </div>
                      <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">{new Date(rec.created_at).toLocaleString()}</p>
                      {rec.error && <p className="text-xs text-red-500 mt-1">{rec.error}</p>}
                    </div>
                    {(rec.status === 'queued' || rec.status === 'error') && (
                      <Button size="sm" variant="outline" onClick={() => handleRetry(rec.id)} data-testid={`retry-${rec.id}`}>
                        <RotateCcw size={14} className="mr-1" /> Retry
                      </Button>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Live Assets (Orbit 4 only) */}
      {activeSection === 'assets' && integrationId === 'orbit4' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 dark:text-zinc-500" />
              <Input
                placeholder="Search by QR code, brand, serial number..."
                value={assetsSearch}
                onChange={e => setAssetsSearch(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { setAssetsPage(1); loadOrbit4Assets(1, assetsSearch); } }}
                className="pl-9"
                data-testid="assets-search"
              />
            </div>
            <Button size="sm" onClick={() => { setAssetsPage(1); loadOrbit4Assets(1, assetsSearch); }} data-testid="assets-search-btn">
              <Search size={14} className="mr-1" /> Search
            </Button>
            <Button size="sm" variant="outline" onClick={() => { setAssetsSearch(''); setAssetsPage(1); loadOrbit4Assets(1, ''); }}>
              <RefreshCw size={14} />
            </Button>
          </div>

          {loadingAssets ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={24} className="animate-spin text-zinc-400 dark:text-zinc-500" />
              <span className="ml-2 text-sm text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">Loading from Orbit 4...</span>
            </div>
          ) : orbit4Assets.length === 0 ? (
            <Card className="p-8 text-center border-zinc-200 dark:border-zinc-800">
              <Package size={32} className="text-zinc-300 mx-auto mb-2" />
              <p className="text-sm text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">No assets found. Ensure the API token is valid.</p>
            </Card>
          ) : (
            <>
              <div className="text-xs text-zinc-500 dark:text-zinc-400 dark:text-zinc-500 mb-1">
                Showing {assetsMeta.from || 0}–{assetsMeta.to || 0} of <strong>{(assetsMeta.total || 0).toLocaleString()}</strong> assets from Orbit 4
              </div>
              <div className="border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-zinc-50 dark:bg-zinc-900/50 border-b border-zinc-200 dark:border-zinc-800">
                      <th className="text-left py-2.5 px-3 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 font-medium">QR Code</th>
                      <th className="text-left py-2.5 px-3 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 font-medium">Brand / Product</th>
                      <th className="text-left py-2.5 px-3 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 font-medium">Serial</th>
                      <th className="text-left py-2.5 px-3 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 font-medium">Range</th>
                      <th className="text-left py-2.5 px-3 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 font-medium">Warranty</th>
                      <th className="text-right py-2.5 px-3 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 font-medium">Spend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orbit4Assets.map(asset => (
                      <tr key={asset.id} className="border-b border-zinc-100 dark:border-zinc-800 last:border-0 hover:bg-zinc-50 dark:hover:bg-zinc-800 dark:bg-zinc-900/50">
                        <td className="py-2 px-3 font-mono text-xs text-zinc-700 dark:text-zinc-300">{asset.qr_code}</td>
                        <td className="py-2 px-3">
                          <span className="font-medium text-zinc-900 dark:text-zinc-100">{asset.brand}</span>
                          <span className="text-zinc-500 dark:text-zinc-400 dark:text-zinc-500 ml-1">{asset.product}</span>
                        </td>
                        <td className="py-2 px-3 text-xs text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">{asset.serial_number}</td>
                        <td className="py-2 px-3 text-xs text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">{asset.range}</td>
                        <td className="py-2 px-3 text-xs text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">
                          {asset.warranty_end_date ? new Date(asset.warranty_end_date).toLocaleDateString() : '—'}
                        </td>
                        <td className="py-2 px-3 text-xs text-right text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">{asset.current_spend}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* Pagination */}
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">
                  Page {assetsMeta.current_page || 1} of {assetsMeta.last_page || 1}
                </span>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" disabled={!assetsMeta.from || assetsMeta.current_page <= 1}
                    onClick={() => { const p = assetsPage - 1; setAssetsPage(p); }}
                    data-testid="assets-prev">
                    <ChevronLeft size={14} />
                  </Button>
                  <Button size="sm" variant="outline" disabled={assetsMeta.current_page >= assetsMeta.last_page}
                    onClick={() => { const p = assetsPage + 1; setAssetsPage(p); }}
                    data-testid="assets-next">
                    <ChevronRight size={14} />
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Configuration */}
      {activeSection === 'config' && (
        <div className="space-y-4">
          {integrationId === 'orbit4' && (
            <>
              <Card className="p-5 border-zinc-200 dark:border-zinc-800 space-y-4">
                <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Orbit 4 API Credentials</h4>
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">API Token</Label>
                  <Input type="password" value={editConfig.api_token || ''} onChange={e => setEditConfig({...editConfig, api_token: e.target.value})}
                    placeholder="Paste your Orbit 4 API token..." className="mt-1" data-testid="orbit4-api-token" />
                  <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">Generated in Orbit 4 → Profile → API Tokens</p>
                </div>
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Webhook Secret</Label>
                  <Input type="password" value={editConfig.webhook_secret || ''} onChange={e => setEditConfig({...editConfig, webhook_secret: e.target.value})}
                    placeholder="Paste your webhook secret..." className="mt-1" data-testid="orbit4-webhook-secret" />
                  <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">Created when you add a webhook in Orbit 4 → Profile → Webhooks</p>
                </div>
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">API Base URL</Label>
                  <Input value={editConfig.base_url || ''} onChange={e => setEditConfig({...editConfig, base_url: e.target.value})}
                    placeholder="https://api.orbit4.org/v1" className="mt-1" data-testid="orbit4-base-url" />
                </div>
              </Card>
            </>
          )}

          {integrationId === 'sicon' && (
            <>
            <Card className="p-5 border-zinc-200 dark:border-zinc-800 space-y-3" data-testid="sicon-connection-test-card">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">API Connection</h4>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Verify the saved base URL and credentials reach Sicon.</p>
                </div>
                <Button size="sm" onClick={testConnection} disabled={testingConnection} data-testid="sicon-test-connection-btn"
                  className={connectionStatus?.status === 'connected' ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : 'bg-blue-600 hover:bg-blue-700 text-white'}>
                  {testingConnection ? <Loader2 size={14} className="animate-spin mr-1" /> : connectionStatus?.status === 'connected' ? <Wifi size={14} className="mr-1" /> : <WifiOff size={14} className="mr-1" />}
                  {testingConnection ? 'Testing…' : connectionStatus?.status === 'connected' ? 'Connected' : 'Test Connection'}
                </Button>
              </div>
              {connectionStatus && (
                <div className={`rounded-lg p-3 text-sm ${connectionStatus.status === 'connected' ? 'bg-emerald-50 border border-emerald-200 text-emerald-700' : 'bg-red-50 border border-red-200 text-red-700'}`} data-testid="sicon-connection-result">
                  <div className="flex items-center gap-2">
                    {connectionStatus.status === 'connected' ? <CheckCircle size={16} /> : <XCircle size={16} />}
                    <span className="font-medium">{connectionStatus.message}</span>
                  </div>
                  {connectionStatus.steps?.length > 0 && (
                    <ul className="mt-2 space-y-1 text-xs" data-testid="sicon-connection-steps">
                      {connectionStatus.steps.map(st => (
                        <li key={st.key} className="flex items-start gap-1.5" data-testid={`sicon-connection-step-${st.key}`}>
                          {st.ok ? <CheckCircle size={13} className="mt-0.5 shrink-0" /> : <XCircle size={13} className="mt-0.5 shrink-0" />}
                          <span><b>{st.label}</b> — {st.detail} <span className="opacity-60">({st.ms} ms)</span></span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {!connectionStatus && <p className="text-xs text-zinc-400 dark:text-zinc-500">Save your credentials first, then click "Test Connection".</p>}
            </Card>

            <SiconOnboardingSync API={API} headers={headers} />

            <Card className="p-5 border-zinc-200 dark:border-zinc-800 space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Sicon Service API Credentials</h4>
                {config?.credentials_set && Object.values(config.credentials_set).some(Boolean) && (
                  <Badge className="bg-emerald-50 text-emerald-700" data-testid="sicon-credentials-saved-badge"><CheckCircle size={12} className="mr-1" /> Saved</Badge>
                )}
              </div>
              <p className="text-xs text-zinc-500 -mt-2">Pulse Fitness's Sicon R260200c instance. See <code>/app/memory/SICON_INTEGRATION_SPEC.md</code> for the full integration model.</p>
              <div>
                <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">API Base URL</Label>
                <Input value={editConfig.base_url || ''} onChange={e => setEditConfig({...editConfig, base_url: e.target.value})}
                  placeholder="https://your-sicon-instance.com/api" className="mt-1" data-testid="sicon-base-url" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">API Key / Bearer Token</Label>
                  <Input type="password" value={editConfig.credentials?.api_key || ''} onChange={e => setEditConfig({...editConfig, credentials: {...(editConfig.credentials || {}), api_key: e.target.value}})}
                    placeholder={config?.credentials_set?.api_key ? '•••••• saved — type to replace' : 'Sicon API key…'} className="mt-1" data-testid="sicon-api-key" />
                  {config?.credentials_set?.api_key && <p className="text-xs text-emerald-600 mt-1"><CheckCircle size={11} className="inline mr-0.5" /> Saved — leave blank to keep the current key.</p>}
                </div>
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Auth Mode</Label>
                  <select
                    value={editConfig.credentials?.auth_mode || 'bearer'}
                    onChange={e => setEditConfig({...editConfig, credentials: {...(editConfig.credentials || {}), auth_mode: e.target.value}})}
                    className="mt-1 block w-full rounded-md border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-3 py-2 text-sm"
                    data-testid="sicon-auth-mode"
                  >
                    <option value="bearer">Bearer Token</option>
                    <option value="basic">HTTP Basic</option>
                    <option value="apikey-header">X-API-Key Header</option>
                  </select>
                </div>
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Username</Label>
                  <Input value={editConfig.credentials?.username || ''} onChange={e => setEditConfig({...editConfig, credentials: {...(editConfig.credentials || {}), username: e.target.value}})}
                    placeholder="Sage user (for Basic auth)" className="mt-1" data-testid="sicon-username" />
                </div>
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Password</Label>
                  <Input type="password" value={editConfig.credentials?.password || ''} onChange={e => setEditConfig({...editConfig, credentials: {...(editConfig.credentials || {}), password: e.target.value}})}
                    placeholder={config?.credentials_set?.password ? '•••••• saved — type to replace' : 'Sicon WebAPI password'} className="mt-1" data-testid="sicon-password" />
                  <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">Used to sign in when no bearer token is saved or it expires.</p>
                </div>
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Sicon Company ID</Label>
                  <Input value={editConfig.credentials?.company_id || ''} onChange={e => setEditConfig({...editConfig, credentials: {...(editConfig.credentials || {}), company_id: e.target.value}})}
                    placeholder="e.g. 1" className="mt-1" data-testid="sicon-company-id" />
                </div>
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Sage 200 SLCustomerAccountID</Label>
                  <Input value={editConfig.credentials?.sage_customer_account_id || ''} onChange={e => setEditConfig({...editConfig, credentials: {...(editConfig.credentials || {}), sage_customer_account_id: e.target.value}})}
                    placeholder="Pulse Fitness Sage account" className="mt-1" data-testid="sicon-sage-account-id" />
                  <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">Required for case creation; Sage owns customer master data.</p>
                </div>
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Default Site Sub-location ID</Label>
                  <Input value={editConfig.credentials?.default_sublocation_id || ''} onChange={e => setEditConfig({...editConfig, credentials: {...(editConfig.credentials || {}), default_sublocation_id: e.target.value}})}
                    placeholder="SiconSubLocationID fallback" className="mt-1" data-testid="sicon-default-sublocation" />
                </div>
              </div>
            </Card>

            <Card className="p-5 border-zinc-200 dark:border-zinc-800 space-y-4">
              <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Sync &amp; Webhooks</h4>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Poll Interval (seconds)</Label>
                  <Input type="number" min="60" step="30" value={editConfig.sync?.poll_interval_seconds || 300}
                    onChange={e => setEditConfig({...editConfig, sync: {...(editConfig.sync || {}), poll_interval_seconds: parseInt(e.target.value || '300', 10)}})}
                    className="mt-1" data-testid="sicon-poll-interval" />
                  <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">Background poller — defaults to every 5 min.</p>
                </div>
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Inbound Webhook Secret</Label>
                  <Input type="password" value={editConfig.sync?.webhook_secret || ''}
                    onChange={e => setEditConfig({...editConfig, sync: {...(editConfig.sync || {}), webhook_secret: e.target.value}})}
                    placeholder="HMAC secret for Sicon → Pulse Fitness pushes" className="mt-1" data-testid="sicon-webhook-secret" />
                </div>
                <div>
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Inbound Webhook URL</Label>
                  <Input
                    readOnly
                    value={`${(editConfig.branding?.production_webhook_domain || window.location.origin).replace(/\/$/, '')}/api/webhooks/sicon`}
                    className="mt-1 font-mono text-xs bg-zinc-50 dark:bg-zinc-900/40"
                    data-testid="sicon-webhook-url"
                  />
                  <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">Configure in Sicon Service → Integrations → Outbound Webhooks.</p>
                </div>
                <div className="flex items-center gap-2 pt-6">
                  <Switch checked={editConfig.sync?.tls_pinning || false}
                    onCheckedChange={v => setEditConfig({...editConfig, sync: {...(editConfig.sync || {}), tls_pinning: v}})}
                    data-testid="sicon-tls-pinning" />
                  <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 cursor-pointer">Enforce TLS certificate pinning</Label>
                </div>
              </div>
            </Card>
            </>
          )}

          {/* White-Label Branding */}
          <Card className="p-5 border-zinc-200 dark:border-zinc-800 space-y-4" data-testid="branding-config">
            <div>
              <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-2"><Shield size={16} className="text-blue-600" /> White-Label Branding</h4>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 dark:text-zinc-500 mt-1">Controls what third-party services see. Orbit 4 and Sicon will identify this integration as the name below — not Pulse Fitness AI.</p>
            </div>
            <div>
              <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Display Name</Label>
              <Input value={editConfig.branding?.display_name || ''} onChange={e => setEditConfig({...editConfig, branding: {...(editConfig.branding || {}), display_name: e.target.value}})}
                placeholder="Pulse Fitness" className="mt-1" data-testid="branding-display-name" />
              <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">Shown in webhook responses, API headers, and any external-facing communication</p>
            </div>
            <div>
              <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Contact Email</Label>
              <Input value={editConfig.branding?.contact_email || ''} onChange={e => setEditConfig({...editConfig, branding: {...(editConfig.branding || {}), contact_email: e.target.value}})}
                placeholder="support@pulsefitness.com" className="mt-1" data-testid="branding-contact-email" />
            </div>
            {integrationId === 'orbit4' && (
              <div>
                <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">Production Webhook Domain</Label>
                <Input value={editConfig.branding?.production_webhook_domain || ''} onChange={e => setEditConfig({...editConfig, branding: {...(editConfig.branding || {}), production_webhook_domain: e.target.value}})}
                  placeholder="https://api.pulsefitness.com" className="mt-1" data-testid="branding-webhook-domain" />
                <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">If set, this domain is shown as the webhook URL for Orbit 4. Use a Pulse Fitness subdomain with a reverse proxy pointing to this server.</p>
              </div>
            )}
            <div>
              <Label className="text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">User-Agent Header</Label>
              <Input value={editConfig.branding?.user_agent || ''} onChange={e => setEditConfig({...editConfig, branding: {...(editConfig.branding || {}), user_agent: e.target.value}})}
                placeholder="PulseFitness-ServiceBridge/1.0" className="mt-1" data-testid="branding-user-agent" />
              <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">Sent in all outbound API calls to Orbit 4 and Sicon</p>
            </div>
          </Card>

          <Button onClick={handleSave} disabled={saving} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" data-testid="save-config">
            {saving ? <Loader2 size={14} className="animate-spin mr-1" /> : <Settings size={14} className="mr-1" />}
            Save Configuration
          </Button>
        </div>
      )}

      {/* Field Mappings */}
      {activeSection === 'mappings' && (
        <div className="space-y-4">
          {integrationId === 'sicon' && siconMappings ? (
            <>
              <Card className="p-5 border-zinc-200 dark:border-zinc-800">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                  <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Pulse Fitness ↔ Sicon Service — full field map</h4>
                  <div className="flex items-center gap-2">
                    <Badge className="bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300" data-testid="sicon-mapping-count">{siconMappings.total} fields</Badge>
                    <Badge className={connectionStatus?.status === 'connected' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'} data-testid="sicon-mapping-conn">
                      {connectionStatus?.status === 'connected' ? <><Wifi size={11} className="mr-1" /> Connected</> : <><WifiOff size={11} className="mr-1" /> Not tested</>}
                    </Badge>
                  </div>
                </div>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-1">
                  Live from <code className="font-mono">GET /api/sicon/field-mapping</code> · source of truth <code className="font-mono">/app/integrations/sicon/</code>.
                  Direction: <strong>OUT</strong> = Pulse → Sicon, <strong>IN</strong> = Sicon → Pulse, <strong>BOTH</strong> = bi-directional.
                </p>
                {connectionStatus?.status !== 'connected' && (
                  <p className="text-xs text-amber-600 mb-3"><AlertTriangle size={11} className="inline mr-1" />Run <strong>Configuration → Test Connection</strong> to confirm these fields reach a live Sicon instance.</p>
                )}
              </Card>
              {Object.entries(siconMappings.grouped || {}).map(([entity, rows]) => (
                <Card key={entity} className="p-0 border-zinc-200 dark:border-zinc-800 overflow-hidden" data-testid={`sicon-mapping-group-${entity}`}>
                  <div className="flex items-center justify-between px-4 py-2.5 bg-zinc-50 dark:bg-zinc-900/50 border-b border-zinc-200 dark:border-zinc-800">
                    <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{entity}</span>
                    <span className="text-xs text-zinc-400 dark:text-zinc-500">{rows.length} fields</span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-zinc-200 dark:border-zinc-800 text-xs text-zinc-500 dark:text-zinc-400">
                          <th className="text-left py-2 px-4 font-medium">Pulse Fitness Field</th>
                          <th className="text-center py-2 px-2 font-medium w-16">Dir</th>
                          <th className="text-left py-2 px-4 font-medium">Sicon Field</th>
                          <th className="text-left py-2 px-3 font-medium w-20">Type</th>
                          <th className="text-left py-2 px-4 font-medium">Notes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row, i) => (
                          <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800 last:border-0 align-top">
                            <td className="py-2 px-4 text-zinc-700 dark:text-zinc-300 font-mono text-xs">{row.gymaxis_field}</td>
                            <td className="py-2 px-2 text-center"><DirectionBadge direction={row.direction === '→' ? 'outbound' : row.direction === '←' ? 'inbound' : 'internal'} /></td>
                            <td className="py-2 px-4 text-zinc-700 dark:text-zinc-300 font-mono text-xs">{row.sicon_field}</td>
                            <td className="py-2 px-3 text-zinc-500 dark:text-zinc-400 text-xs">{row.type}</td>
                            <td className="py-2 px-4 text-zinc-500 dark:text-zinc-400 text-xs">{row.notes}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              ))}
            </>
          ) : (
          <Card className="p-5 border-zinc-200 dark:border-zinc-800">
            <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-1">
              {integrationId === 'orbit4' ? 'Orbit 4 → Sicon Field Mapping' : 'Pulse Fitness Issue → Sicon Service Case'}
            </h4>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 dark:text-zinc-500 mb-4">
              {integrationId === 'sicon'
                ? 'Loading the full mapping table…'
                : 'How fields from Orbit 4 tickets map to Sicon service cases. These will be confirmed with Pulse Fitness.'}
            </p>
            <div className="border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-zinc-50 dark:bg-zinc-900/50 border-b border-zinc-200 dark:border-zinc-800">
                    <th className="text-left py-2.5 px-4 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 font-medium">{integrationId === 'sicon' ? 'Pulse Fitness Field' : 'Orbit 4 Field'}</th>
                    <th className="text-center py-2.5 px-2 text-zinc-400 dark:text-zinc-500 w-12"></th>
                    <th className="text-left py-2.5 px-4 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 font-medium">Sicon Field</th>
                    {integrationId === 'sicon' && (
                      <th className="text-left py-2.5 px-2 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 font-medium w-20">Direction</th>
                    )}
                    <th className="text-left py-2.5 px-4 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(integrationId === 'sicon' ? SICON_FIELD_MAPPINGS : ORBIT4_FIELD_MAPPINGS).map((row, i) => (
                    <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800 last:border-0">
                      <td className="py-2.5 px-4 text-zinc-700 dark:text-zinc-300 font-mono text-xs">{row.source}</td>
                      <td className="py-2.5 px-2 text-center"><ArrowRight size={12} className="text-zinc-300 mx-auto" /></td>
                      <td className="py-2.5 px-4 text-zinc-700 dark:text-zinc-300 font-mono text-xs">{row.target}</td>
                      {integrationId === 'sicon' && (
                        <td className="py-2.5 px-2"><DirectionBadge direction={row.direction} /></td>
                      )}
                      <td className="py-2.5 px-4">
                        <Badge className={row.status === 'mapped' ? 'bg-emerald-50 text-emerald-700' : row.status === 'pending' ? 'bg-amber-50 text-amber-700' : 'bg-blue-50 text-blue-700'}>
                          {row.status === 'mapped' ? 'Mapped' : row.status === 'pending' ? 'Awaiting confirmation' : 'Lookup'}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          )}
        </div>
      )}
    </div>
  );
};

// ── Sub-components ───────────────────────────────────────────────

const StatCard = ({ label, value, icon: Icon, color }) => (
  <Card className="p-5 border-zinc-200 dark:border-zinc-800">
    <div className="flex items-center gap-3">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}><Icon size={18} /></div>
      <div>
        <p className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">{value}</p>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">{label}</p>
      </div>
    </div>
  </Card>
);

const FlowBox = ({ label, sub, icon: Icon, active, highlight }) => (
  <div className={`flex-1 text-center p-3 rounded-lg border ${highlight ? 'bg-zinc-900 text-white border-zinc-900' : active ? 'bg-emerald-50 border-emerald-200' : 'bg-zinc-50 dark:bg-zinc-900/50 border-zinc-200 dark:border-zinc-800'}`}>
    <Icon size={16} className={`mx-auto mb-1 ${highlight ? 'text-white' : active ? 'text-emerald-600' : 'text-zinc-400 dark:text-zinc-500'}`} />
    <p className={`text-xs font-semibold ${highlight ? 'text-white' : active ? 'text-emerald-700' : 'text-zinc-500 dark:text-zinc-400 dark:text-zinc-500'}`}>{label}</p>
    <p className={`text-[10px] ${highlight ? 'text-zinc-300' : 'text-zinc-400 dark:text-zinc-500'}`}>{sub}</p>
  </div>
);

const DirectionBadge = ({ direction }) => {
  if (direction === 'inbound') return <Badge className="bg-blue-50 text-blue-700 text-[10px]">IN</Badge>;
  if (direction === 'outbound') return <Badge className="bg-violet-50 text-violet-700 text-[10px]">OUT</Badge>;
  return <Badge className="bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 dark:text-zinc-500 text-[10px]">INT</Badge>;
};

const BridgeStatusBadge = ({ status }) => {
  const styles = {
    forwarded: 'bg-emerald-50 text-emerald-700',
    queued: 'bg-amber-50 text-amber-700',
    pending: 'bg-blue-50 text-blue-700',
    error: 'bg-red-50 text-red-700',
    closed: 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 dark:text-zinc-500',
  };
  return <Badge className={`${styles[status] || styles.pending} text-xs capitalize`}>{status}</Badge>;
};

export default IntegrationAdminPanel;
