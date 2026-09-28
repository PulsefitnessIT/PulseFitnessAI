import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import SiconDashboard from './SiconDashboard';
import SiconMappings from './SiconMappings';
import {
 Link2, Zap, Shield, CheckCircle, XCircle, Loader2,
 RefreshCw, Clock, ArrowRight, ScrollText
} from 'lucide-react';

const SiconIntegrationTab = () => {
 const { API } = useAuth();
 const [config, setConfig] = useState(null);
 const [loading, setLoading] = useState(true);
 const [saving, setSaving] = useState(false);
 const [testing, setTesting] = useState(false);
 const [auditLogs, setAuditLogs] = useState([]);

 const [form, setForm] = useState({
 base_url: '',
 username: '',
 password: '',
 company_id: 0,
 enabled: false,
 auto_sync_faults: false,
 auto_sync_status: false,
 default_case_type_id: 0,
 default_case_type_name: '',
 default_priority_id: 0,
 default_internal_team_id: 0,
 default_external_team_id: 0,
 default_assigned_user_id: 0,
 default_contract_id: 0,
 default_contract_line_id: 0,
 priority_mapping: { low: 0, medium: 0, critical: 0 },
 location_address: { name: '', line1: '', line2: '', city: '', postcode: '' },
 });

 const token = localStorage.getItem('token');
 const headers = { Authorization: `Bearer ${token}` };

 const loadConfig = useCallback(async () => {
 try {
 const res = await axios.get(`${API}/sicon/config`, { headers });
 setConfig(res.data);
 if (res.data.configured) {
 setForm(f => ({
 ...f,
 base_url: res.data.base_url || '',
 username: res.data.username || '',
 company_id: res.data.company_id || 0,
 enabled: res.data.enabled || false,
 auto_sync_faults: res.data.auto_sync_faults || false,
 auto_sync_status: res.data.auto_sync_status || false,
 default_case_type_id: res.data.default_case_type_id || 0,
 default_case_type_name: res.data.default_case_type_name || '',
 default_priority_id: res.data.default_priority_id || 0,
 default_internal_team_id: res.data.default_internal_team_id || 0,
 default_external_team_id: res.data.default_external_team_id || 0,
 default_assigned_user_id: res.data.default_assigned_user_id || 0,
 default_contract_id: res.data.default_contract_id || 0,
 default_contract_line_id: res.data.default_contract_line_id || 0,
 priority_mapping: res.data.priority_mapping || { low: 0, medium: 0, critical: 0 },
 location_address: res.data.location_address || { name: '', line1: '', line2: '', city: '', postcode: '' },
 }));
 }
 } catch (err) { console.error('Sicon config load error:', err); }
 setLoading(false);
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: context helpers re-create each render but read the latest token / handler at call time; adding them would invalidate the memo every render and break the optimisation.
 }, [API]);

 const loadAuditLog = useCallback(async () => {
 try {
 const res = await axios.get(`${API}/sicon/audit-log`, { headers });
 setAuditLogs(res.data.logs || []);
 } catch (err) { console.error('Sicon audit log error:', err); }
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: context helpers re-create each render but read the latest token / handler at call time; adding them would invalidate the memo every render and break the optimisation.
 }, [API]);

 useEffect(() => { loadConfig(); }, [loadConfig]);

 const handleSave = async () => {
 setSaving(true);
 try {
 await axios.put(`${API}/sicon/config`, form, { headers });
 notify.success('Sicon configuration saved');
 loadConfig();
 } catch (err) {
 notifyApiError(notify, err, 'Failed to save');
 }
 setSaving(false);
 };

 const handleTestConnection = async () => {
 setTesting(true);
 try {
 const res = await axios.post(`${API}/sicon/test-connection`, {}, { headers });
 if (res.data.connected) {
 notify.success('Connected to Sicon WebAPI successfully');
 } else {
 notify.error(res.data.error || 'Connection failed');
 }
 loadConfig();
 } catch (err) {
 notifyApiError(notify, err, 'Connection test failed');
 }
 setTesting(false);
 };

 if (loading) {
 return (
 <div className="flex items-center justify-center p-12">
 <Loader2 size={24} className="animate-spin text-[var(--color-brand-blue)]" />
 </div>
 );
 }

 return (
 <div className="space-y-6" data-testid="sicon-integration-tab">
 {/* Header */}
 <div className="flex items-start justify-between">
 <div>
 <div className="flex items-center gap-3 mb-1">
 <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-[var(--color-brand-blue)] to-[var(--color-blue-500)] flex items-center justify-center">
 <Link2 size={20} className="text-white" />
 </div>
 <div>
 <h2 className="text-xl font-bold text-white">Sicon Service Integration</h2>
 <p className="text-[var(--color-text-muted)] text-sm">Connect Pulse Fitness AI to Pulse Fitness Sicon Service (Sage 200)</p>
 </div>
 </div>
 </div>
 {config?.configured && (
 <Badge className={config.connection_status === 'connected' ? 'bg-green-500/20 text-green-400' : config.connection_status === 'error' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'} data-testid="sicon-connection-badge">
 {config.connection_status === 'connected' ? <><CheckCircle size={12} className="mr-1" /> Connected</> :
 config.connection_status === 'error' ? <><XCircle size={12} className="mr-1" /> Error</> :
 <><Clock size={12} className="mr-1" /> Not Tested</>}
 </Badge>
 )}
 </div>

 {/* Security Notice */}
 <Card className="bg-[rgb(var(--rgb-brand-blue)/0.05)] border-[rgb(var(--rgb-brand-blue)/0.2)] p-5">
 <div className="flex items-start gap-3">
 <Shield size={20} className="text-[var(--color-brand-blue)] flex-shrink-0 mt-0.5" />
 <div>
 <p className="text-white text-sm font-medium">Enterprise-Grade Security</p>
 <p className="text-[var(--color-text-muted)] text-xs mt-1">
 Credentials are AES-256 encrypted at rest. All API calls are server-to-server over HTTPS.
 Sicon credentials are never exposed to the browser. Only owners can configure this integration.
 </p>
 </div>
 </div>
 </Card>

 <Tabs defaultValue="dashboard" className="w-full">
 <TabsList className="bg-[var(--theme-surface)] border border-white/10 mb-4">
 <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
 <TabsTrigger value="connection">Connection</TabsTrigger>
 <TabsTrigger value="mapping">Field Mapping</TabsTrigger>
 <TabsTrigger value="data-mapping">Data Mapping</TabsTrigger>
 <TabsTrigger value="sync">Sync Settings</TabsTrigger>
 <TabsTrigger value="audit" onClick={loadAuditLog}>Audit Log</TabsTrigger>
 </TabsList>

 {/* Dashboard Tab (read-side: Sicon → Pulse) */}
 <TabsContent value="dashboard">
 <SiconDashboard />
 </TabsContent>

 {/* Data Mapping Tab (reference-data + customer/site, Increment C) */}
 <TabsContent value="data-mapping">
 <SiconMappings />
 </TabsContent>

 {/* Connection Tab */}
 <TabsContent value="connection">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6 space-y-5">
 <div>
 <Label className="text-white">Sicon WebAPI URL</Label>
 <Input
 value={form.base_url}
 onChange={e => setForm({ ...form, base_url: e.target.value })}
 placeholder="https://your-server/SiconWebAPI"
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1 font-mono"
 data-testid="sicon-url-input"
 />
 <p className="text-[var(--color-text-muted)] text-xs mt-1">The URL of the Sicon WebAPI on Pulse Fitness's server</p>
 </div>

 <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
 <div>
 <Label className="text-white">Username</Label>
 <Input
 value={form.username}
 onChange={e => setForm({ ...form, username: e.target.value })}
 placeholder="API username"
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
 data-testid="sicon-username-input"
 />
 </div>
 <div>
 <Label className="text-white">Password</Label>
 <Input
 type="password"
 value={form.password}
 onChange={e => setForm({ ...form, password: e.target.value })}
 placeholder={config?.has_password ? '••••••••' : 'Enter password'}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
 data-testid="sicon-password-input"
 />
 </div>
 </div>

 <div>
 <Label className="text-white">Sage Company ID</Label>
 <Input
 value={form.company_id}
 onChange={e => setForm({ ...form, company_id: parseInt(e.target.value) || 0 })}
 placeholder="0 (default company)"
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1 w-48"
 data-testid="sicon-company-id"
 />
 </div>

 <div className="flex items-center justify-between p-4 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <div>
 <p className="text-white font-medium">Enable Integration</p>
 <p className="text-[var(--color-text-muted)] text-xs">When enabled, Pulse Fitness AI will sync data with Sicon Service</p>
 </div>
 <Switch
 checked={form.enabled}
 onCheckedChange={v => setForm({ ...form, enabled: v })}
 data-testid="sicon-enabled-switch"
 />
 </div>

 <div className="flex gap-3">
 <Button onClick={handleSave} disabled={saving} className="bg-[var(--color-brand-blue)] text-white" data-testid="sicon-save-btn">
 {saving ? <><Loader2 size={16} className="mr-2 animate-spin" /> Saving...</> : 'Save Configuration'}
 </Button>
 <Button onClick={handleTestConnection} disabled={testing || !form.base_url} variant="outline" className="border-white/10 text-white" data-testid="sicon-test-btn">
 {testing ? <><Loader2 size={16} className="mr-2 animate-spin" /> Testing...</> : <><Zap size={16} className="mr-2" /> Test Connection</>}
 </Button>
 </div>
 </Card>
 </TabsContent>

 {/* Field Mapping Tab */}
 <TabsContent value="mapping">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6 space-y-5">
 <div>
 <h3 className="text-white font-semibold mb-1">Sicon Field Mapping</h3>
 <p className="text-[var(--color-text-muted)] text-sm">Map Pulse Fitness fields to Sicon Service IDs. Get these values from your Sicon admin.</p>
 </div>

 <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
 <div>
 <Label className="text-white">Default Case Type ID</Label>
 <Input value={form.default_case_type_id} onChange={e => setForm({ ...form, default_case_type_id: parseInt(e.target.value) || 0 })}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="sicon-case-type-id" />
 </div>
 <div>
 <Label className="text-white">Case Type Name (fallback)</Label>
 <Input value={form.default_case_type_name} onChange={e => setForm({ ...form, default_case_type_name: e.target.value })}
 placeholder="e.g. Equipment Fault" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="sicon-case-type-name" />
 </div>
 <div>
 <Label className="text-white">Default Internal Team ID</Label>
 <Input value={form.default_internal_team_id} onChange={e => setForm({ ...form, default_internal_team_id: parseInt(e.target.value) || 0 })}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="sicon-internal-team" />
 </div>
 <div>
 <Label className="text-white">Default External Team ID</Label>
 <Input value={form.default_external_team_id} onChange={e => setForm({ ...form, default_external_team_id: parseInt(e.target.value) || 0 })}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="sicon-external-team" />
 </div>
 <div>
 <Label className="text-white">Assigned Sage User ID</Label>
 <Input value={form.default_assigned_user_id} onChange={e => setForm({ ...form, default_assigned_user_id: parseInt(e.target.value) || 0 })}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="sicon-assigned-user" />
 </div>
 <div>
 <Label className="text-white">Default Contract ID</Label>
 <Input value={form.default_contract_id} onChange={e => setForm({ ...form, default_contract_id: parseInt(e.target.value) || 0 })}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="sicon-contract-id" />
 </div>
 </div>

 {/* Priority Mapping */}
 <div className="border-t border-white/10 pt-4">
 <h4 className="text-white font-medium mb-3">Priority Mapping</h4>
 <p className="text-[var(--color-text-muted)] text-xs mb-3">Map Pulse Fitness severity levels to Sicon Priority IDs</p>
 <div className="grid grid-cols-3 gap-3">
 {['low', 'medium', 'critical'].map(sev => (
 <div key={sev}>
 <Label className="text-white capitalize">{sev} <ArrowRight size={12} className="inline mx-1" /> Sicon Priority ID</Label>
 <Input
 value={form.priority_mapping[sev] || 0}
 onChange={e => setForm({ ...form, priority_mapping: { ...form.priority_mapping, [sev]: parseInt(e.target.value) || 0 } })}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
 data-testid={`sicon-priority-${sev}`}
 />
 </div>
 ))}
 </div>
 </div>

 {/* Location Address */}
 <div className="border-t border-white/10 pt-4">
 <h4 className="text-white font-medium mb-3">Default Location Address</h4>
 <p className="text-[var(--color-text-muted)] text-xs mb-3">Used when creating cases in Sicon — the gym's physical address</p>
 <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
 <div>
 <Label className="text-white">Site Name</Label>
 <Input value={form.location_address.name || ''} onChange={e => setForm({ ...form, location_address: { ...form.location_address, name: e.target.value } })}
 placeholder="e.g. Pulse Fitness HQ" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" />
 </div>
 <div>
 <Label className="text-white">Address Line 1</Label>
 <Input value={form.location_address.line1 || ''} onChange={e => setForm({ ...form, location_address: { ...form.location_address, line1: e.target.value } })}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" />
 </div>
 <div>
 <Label className="text-white">City</Label>
 <Input value={form.location_address.city || ''} onChange={e => setForm({ ...form, location_address: { ...form.location_address, city: e.target.value } })}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" />
 </div>
 <div>
 <Label className="text-white">Postcode</Label>
 <Input value={form.location_address.postcode || ''} onChange={e => setForm({ ...form, location_address: { ...form.location_address, postcode: e.target.value } })}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" />
 </div>
 </div>
 </div>

 <Button onClick={handleSave} disabled={saving} className="bg-[var(--color-brand-blue)] text-white" data-testid="sicon-save-mapping-btn">
 {saving ? 'Saving...' : 'Save Field Mapping'}
 </Button>
 </Card>
 </TabsContent>

 {/* Sync Settings Tab */}
 <TabsContent value="sync">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6 space-y-5">
 <div>
 <h3 className="text-white font-semibold mb-1">Automatic Sync</h3>
 <p className="text-[var(--color-text-muted)] text-sm">Configure how Pulse Fitness AI syncs with Sicon Service</p>
 </div>

 <div className="space-y-4">
 <div className="flex items-center justify-between p-4 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <div>
 <p className="text-white font-medium">Auto-sync new faults to Sicon</p>
 <p className="text-[var(--color-text-muted)] text-xs">When a fault is logged in Pulse Fitness (engineer escalation), automatically create a case in Sicon</p>
 </div>
 <Switch checked={form.auto_sync_faults} onCheckedChange={v => setForm({ ...form, auto_sync_faults: v })} data-testid="sicon-auto-sync-faults" />
 </div>

 <div className="flex items-center justify-between p-4 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <div>
 <p className="text-white font-medium">Auto-sync status updates</p>
 <p className="text-[var(--color-text-muted)] text-xs">When a status changes in Pulse Fitness, push a tracking note to the Sicon case</p>
 </div>
 <Switch checked={form.auto_sync_status} onCheckedChange={v => setForm({ ...form, auto_sync_status: v })} data-testid="sicon-auto-sync-status" />
 </div>
 </div>

 {/* Data Flow Diagram */}
 <div className="border-t border-white/10 pt-4">
 <h4 className="text-white font-medium mb-3">Data Flow</h4>
 <div className="space-y-2">
 {[
 { from: 'Log a Fault (Engineer)', to: 'Sicon Service Case', icon: Zap },
 { from: 'Pulse Fitness Severity', to: 'Sicon Priority ID', icon: ArrowRight },
 { from: 'Equipment (Serial No)', to: 'Sicon Equipment IDs', icon: ArrowRight },
 { from: 'Resolution Notes', to: 'Sicon Tracking Notes', icon: ArrowRight },
 { from: 'AI Triage Summary', to: 'Case Description', icon: ArrowRight },
 ].map((flow, i) => (
 <div key={i} className="flex items-center gap-3 p-2 rounded bg-[var(--color-ink-alt)]">
 <flow.icon size={14} className="text-[var(--color-brand-blue)] flex-shrink-0" />
 <span className="text-white text-sm">{flow.from}</span>
 <ArrowRight size={14} className="text-[var(--color-text-muted)] flex-shrink-0" />
 <span className="text-[var(--color-brand-blue)] text-sm">{flow.to}</span>
 </div>
 ))}
 </div>
 </div>

 <Button onClick={handleSave} disabled={saving} className="bg-[var(--color-brand-blue)] text-white" data-testid="sicon-save-sync-btn">
 {saving ? 'Saving...' : 'Save Sync Settings'}
 </Button>

 {config?.last_sync_at && (
 <p className="text-[var(--color-text-muted)] text-xs flex items-center gap-1">
 <Clock size={12} /> Last sync: {new Date(config.last_sync_at).toLocaleString()}
 </p>
 )}
 </Card>
 </TabsContent>

 {/* Audit Log Tab */}
 <TabsContent value="audit">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6">
 <div className="flex items-center justify-between mb-4">
 <h3 className="text-white font-semibold">Integration Audit Log</h3>
 <Button size="sm" variant="outline" className="border-white/10 text-white" onClick={loadAuditLog} data-testid="refresh-audit-log">
 <RefreshCw size={14} className="mr-1" /> Refresh
 </Button>
 </div>
 {auditLogs.length > 0 ? (
 <div className="space-y-2 max-h-[400px] overflow-y-auto">
 {auditLogs.map((log, i) => (
 <div key={i} className="flex items-start gap-3 p-3 bg-[var(--color-ink-alt)] rounded-lg">
 <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${log.success ? 'bg-green-400' : 'bg-red-400'}`} />
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-2 flex-wrap">
 <span className="text-white text-sm font-medium">{log.action}</span>
 <Badge className={log.success ? 'bg-green-500/20 text-green-400 text-xs' : 'bg-red-500/20 text-red-400 text-xs'}>
 {log.success ? 'Success' : 'Failed'}
 </Badge>
 </div>
 <p className="text-[var(--color-text-muted)] text-xs mt-0.5 truncate">{log.details}</p>
 <p className="text-[var(--color-text-muted)] text-xs mt-0.5">{log.timestamp ? new Date(log.timestamp).toLocaleString() : ''}</p>
 </div>
 </div>
 ))}
 </div>
 ) : (
 <div className="text-center p-8">
 <ScrollText size={32} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
 <p className="text-[var(--color-text-muted)] text-sm">No audit logs yet. Activity will appear here when syncing starts.</p>
 </div>
 )}
 </Card>
 </TabsContent>
 </Tabs>
 </div>
 );
};

export default SiconIntegrationTab;
