import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
 PoundSterling, Shield, TrendingUp, AlertTriangle, Wallet, ArrowUpRight,
 ArrowDownRight, Loader2, CheckCircle, Bell, Zap, Server,
 Brain, Settings, CreditCard, Info
} from 'lucide-react';

const HEALTH_CONFIG = {
 healthy: { color: 'var(--color-success-alt-2)', bg: 'bg-green-500/15', text: 'text-green-400', label: 'Healthy' },
 warning: { color: 'var(--color-orange)', bg: 'bg-orange-500/15', text: 'text-orange-400', label: 'Warning' },
 critical: { color: 'var(--color-danger)', bg: 'bg-red-500/15', text: 'text-red-400', label: 'Critical' },
};

const fmt = (n) => n != null ? `£${Number(n).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';

/* ─── Reserve Health Indicator ─── */
const ReserveHealth = ({ dashboard }) => {
 const h = HEALTH_CONFIG[dashboard.health] || HEALTH_CONFIG.healthy;
 return (
 <Card className="bg-[var(--color-ink-alt)] border-white/10 p-6 col-span-full" data-testid="finops-reserve-health">
 <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
 <div className="flex items-center gap-4">
 <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ${h.bg}`}>
 <Shield size={28} className={h.text} />
 </div>
 <div>
 <div className="flex items-center gap-2">
 <h3 className="text-xl font-bold text-white">Operations Reserve</h3>
 <Badge className={`${h.bg} ${h.text} text-xs`}>{h.label}</Badge>
 </div>
 <p className="text-[var(--color-text-muted)] text-sm mt-0.5">
 {dashboard.runway_months} months runway · {fmt(dashboard.monthly_burn)}/month burn rate
 </p>
 </div>
 </div>
 <div className="text-right">
 <p className="text-3xl font-bold text-white" data-testid="finops-reserve-balance">{fmt(dashboard.reserve_balance)}</p>
 <p className="text-[var(--color-text-muted)] text-xs">Reserve Balance</p>
 </div>
 </div>
 </Card>
 );
};

/* ─── Metric Cards ─── */
const MetricCards = ({ dashboard }) => (
 <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="finops-metrics">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5">
 <div className="flex items-center gap-2 mb-2">
 <PoundSterling size={14} className="text-[var(--color-brand-blue)]" />
 <p className="text-[var(--color-text-muted)] text-xs" title="Sum of Stripe-recorded payments for the current calendar month">Monthly Revenue · Stripe</p>
 </div>
 <p className="text-2xl font-bold text-white" data-testid="finops-monthly-revenue">{fmt(dashboard.monthly_revenue)}</p>
 <p className="text-[10px] text-white/40 mt-1">Sourced from Stripe payment events</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5">
 <div className="flex items-center gap-2 mb-2">
 <ArrowDownRight size={14} className="text-red-400" />
 <p className="text-[var(--color-text-muted)] text-xs">Monthly Burn</p>
 </div>
 <p className="text-2xl font-bold text-white" data-testid="finops-monthly-burn">{fmt(dashboard.monthly_burn)}</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5">
 <div className="flex items-center gap-2 mb-2">
 <TrendingUp size={14} className="text-green-400" />
 <p className="text-[var(--color-text-muted)] text-xs">Runway</p>
 </div>
 <p className="text-2xl font-bold text-white" data-testid="finops-runway">{dashboard.runway_months} months</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5">
 <div className="flex items-center gap-2 mb-2">
 <Bell size={14} className="text-yellow-400" />
 <p className="text-[var(--color-text-muted)] text-xs">Unread Alerts</p>
 </div>
 <p className="text-2xl font-bold text-white" data-testid="finops-alerts-count">{dashboard.unread_alerts}</p>
 </Card>
 </div>
);

/* ─── How It Works Section ─── */
const RevenueFlowDiagram = ({ config }) => (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="finops-revenue-flow">
 <h3 className="text-lg font-semibold text-white mb-4">Revenue Flow Model</h3>
 <div className="flex flex-col md:flex-row items-stretch gap-3">
 <div className="flex-1 bg-white/5 rounded-xl p-4 text-center border border-white/10">
 <CreditCard size={24} className="text-[var(--color-brand-blue)] mx-auto mb-2" />
 <p className="text-white font-semibold text-sm">Customer Payment</p>
 <p className="text-[var(--color-text-muted)] text-xs mt-1">Subscription or one-off</p>
 </div>
 <div className="flex items-center justify-center text-[var(--color-text-muted)]">
 <ArrowUpRight size={20} className="rotate-90 md:rotate-0" />
 </div>
 <div className="flex-1 bg-green-500/10 rounded-xl p-4 text-center border border-green-500/20">
 <Shield size={24} className="text-green-400 mx-auto mb-2" />
 <p className="text-green-400 font-semibold text-sm">{config?.reserve_percentage || 15}% Reserve</p>
 <p className="text-[var(--color-text-muted)] text-xs mt-1">Operations fund</p>
 </div>
 <div className="flex items-center justify-center text-[var(--color-text-muted)]">
 <ArrowUpRight size={20} className="rotate-90 md:rotate-0" />
 </div>
 <div className="flex-1 bg-[rgb(var(--rgb-brand-blue)/0.1)] rounded-xl p-4 text-center border border-[rgb(var(--rgb-brand-blue)/0.2)]">
 <Wallet size={24} className="text-[var(--color-brand-blue)] mx-auto mb-2" />
 <p className="text-[var(--color-brand-blue)] font-semibold text-sm">{100 - (config?.reserve_percentage || 15)}% Distributed</p>
 <p className="text-[var(--color-text-muted)] text-xs mt-1">To cost centre</p>
 </div>
 </div>
 <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
 <div className="bg-white/5 rounded-lg p-3 flex items-center gap-3">
 <Brain size={16} className="text-purple-400 flex-shrink-0" />
 <div>
 <p className="text-white text-xs font-medium">LLM Credits</p>
 <p className="text-[var(--color-text-muted)] text-[10px]">Auto-topped from reserve</p>
 </div>
 </div>
 <div className="bg-white/5 rounded-lg p-3 flex items-center gap-3">
 <Server size={16} className="text-blue-400 flex-shrink-0" />
 <div>
 <p className="text-white text-xs font-medium">Infrastructure</p>
 <p className="text-[var(--color-text-muted)] text-[10px]">Hosting & database</p>
 </div>
 </div>
 <div className="bg-white/5 rounded-lg p-3 flex items-center gap-3">
 <Zap size={16} className="text-amber-400 flex-shrink-0" />
 <div>
 <p className="text-white text-xs font-medium">Email & APIs</p>
 <p className="text-[var(--color-text-muted)] text-[10px]">Resend, external services</p>
 </div>
 </div>
 </div>
 </Card>
);

/* ─── Cost Centres ─── */
const CostCentres = ({ config, onUpdate, saving }) => {
 const centres = config?.cost_centres || {};
 return (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="finops-cost-centres">
 <h3 className="text-lg font-semibold text-white mb-4">Cost Centres</h3>
 <div className="grid md:grid-cols-2 gap-4">
 {Object.entries(centres).map(([key, centre]) => (
 <div key={key} className="bg-white/5 rounded-xl p-5 border border-white/10">
 <div className="flex items-center justify-between mb-3">
 <div className="flex items-center gap-2">
 <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${key === 'gymaxis' ? 'bg-[rgb(var(--rgb-brand-blue)/0.2)]' : 'bg-[rgb(var(--rgb-brand-cyan-hover)/0.2)]'}`}>
 <PoundSterling size={16} className={key === 'gymaxis' ? 'text-[var(--color-brand-blue)]' : 'text-[var(--color-brand-cyan-hover)]'} />
 </div>
 <div>
 <p className="text-white font-semibold text-sm">{centre.name}</p>
 <p className="text-[var(--color-text-muted)] text-[10px] uppercase tracking-wide">{centre.type} charges</p>
 </div>
 </div>
 <Badge className={key === 'gymaxis' ? 'bg-[rgb(var(--rgb-brand-blue)/0.15)] text-[var(--color-brand-blue)]' : 'bg-[rgb(var(--rgb-brand-cyan-hover)/0.15)] text-[var(--color-brand-cyan-hover)]'}>
 {key === 'gymaxis' ? 'Primary' : 'Connected'}
 </Badge>
 </div>
 {centre.type === 'destination' && (
 <div className="space-y-3 mt-4">
 <div>
 <label className="text-[var(--color-text-muted)] text-xs mb-1 block">Stripe Connected Account ID</label>
 <Input
 value={centre.stripe_connected_account_id || ''}
 placeholder="acct_xxxxxxxxxxxxxx"
 onChange={e => onUpdate(key, 'stripe_connected_account_id', e.target.value)}
 className="bg-black/30 border-white/10 text-white h-9 text-sm"
 data-testid={`finops-${key}-connected-id`}
 />
 </div>
 <div>
 <label className="text-[var(--color-text-muted)] text-xs mb-1 block">Platform Fee %</label>
 <Input
 type="number"
 value={centre.platform_fee_percentage || 0}
 onChange={e => onUpdate(key, 'platform_fee_percentage', Number(e.target.value))}
 className="bg-black/30 border-white/10 text-white h-9 text-sm w-24"
 data-testid={`finops-${key}-fee`}
 />
 </div>
 </div>
 )}
 {centre.type === 'direct' && (
 <div className="mt-3 flex items-center gap-2 text-green-400 text-xs">
 <CheckCircle size={14} />
 <span>Payments received directly to your Stripe account</span>
 </div>
 )}
 </div>
 ))}
 </div>
 <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg flex items-start gap-2">
 <Info size={14} className="text-blue-400 mt-0.5 flex-shrink-0" />
 <p className="text-blue-300 text-xs">
 <strong>Stripe Connect (Scaffolded):</strong> When live Stripe keys are configured, Pulse payments will automatically route to their connected account using destination charges. The platform fee % is deducted before forwarding.
 </p>
 </div>
 </Card>
 );
};

/* ─── Configuration Panel ─── */
const ConfigPanel = ({ config, onConfigChange, onSave, saving }) => (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="finops-config">
 <div className="flex items-center justify-between mb-4">
 <h3 className="text-lg font-semibold text-white">Reserve Configuration</h3>
 <Button size="sm" onClick={onSave} disabled={saving} className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-alt)]" data-testid="finops-save-config">
 {saving ? <Loader2 className="animate-spin mr-2" size={14} /> : <Settings size={14} className="mr-2" />}
 Save
 </Button>
 </div>
 <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
 <div>
 <label className="text-[var(--color-text-muted)] text-xs mb-1 block">Reserve %</label>
 <Input
 type="number"
 value={config?.reserve_percentage ?? 15}
 onChange={e => onConfigChange('reserve_percentage', Number(e.target.value))}
 className="bg-black/30 border-white/10 text-white h-10"
 data-testid="finops-reserve-pct"
 />
 </div>
 <div>
 <label className="text-[var(--color-text-muted)] text-xs mb-1 block">LLM Top-Up Amount</label>
 <Input
 type="number"
 value={config?.llm_top_up_amount ?? 50}
 onChange={e => onConfigChange('llm_top_up_amount', Number(e.target.value))}
 className="bg-black/30 border-white/10 text-white h-10"
 data-testid="finops-llm-topup-amount"
 />
 </div>
 <div>
 <label className="text-[var(--color-text-muted)] text-xs mb-1 block">LLM Low Threshold</label>
 <Input
 type="number"
 value={config?.llm_low_threshold ?? 10}
 onChange={e => onConfigChange('llm_low_threshold', Number(e.target.value))}
 className="bg-black/30 border-white/10 text-white h-10"
 data-testid="finops-llm-low"
 />
 </div>
 <div>
 <label className="text-[var(--color-text-muted)] text-xs mb-1 block">Infrastructure (£/mo)</label>
 <Input
 type="number"
 value={config?.infrastructure_monthly_estimate ?? 50}
 onChange={e => onConfigChange('infrastructure_monthly_estimate', Number(e.target.value))}
 className="bg-black/30 border-white/10 text-white h-10"
 data-testid="finops-infra-estimate"
 />
 </div>
 </div>
 <div className="flex items-center gap-3 mt-4 p-3 bg-white/5 rounded-lg">
 <Switch
 checked={config?.auto_top_up_enabled ?? true}
 onCheckedChange={v => onConfigChange('auto_top_up_enabled', v)}
 data-testid="finops-auto-topup-toggle"
 />
 <div>
 <p className="text-white text-sm font-medium">Auto LLM Top-Up</p>
 <p className="text-[var(--color-text-muted)] text-xs">Automatically charge Stripe and top up LLM credits when balance is low</p>
 </div>
 </div>
 </Card>
);

/* ─── Alerts Panel ─── */
const AlertsPanel = ({ alerts, onDismiss }) => (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="finops-alerts">
 <h3 className="text-lg font-semibold text-white mb-4">Alerts</h3>
 {alerts.length > 0 ? (
 <div className="space-y-2 max-h-64 overflow-y-auto">
 {alerts.map(a => (
 <div key={a.id} className={`flex items-start gap-3 p-3 rounded-lg ${a.read ? 'bg-white/5' : 'bg-orange-500/10 border border-orange-500/20'}`}>
 <AlertTriangle size={16} className={a.severity === 'critical' ? 'text-red-400' : 'text-orange-400'} />
 <div className="flex-1 min-w-0">
 <p className="text-white text-sm font-medium">{a.title}</p>
 <p className="text-[var(--color-text-muted)] text-xs">{a.message}</p>
 <p className="text-[#666] text-[10px] mt-1">{new Date(a.created_at).toLocaleString()}</p>
 </div>
 {!a.read && (
 <button onClick={() => onDismiss(a.id)} className="text-[var(--color-text-muted)] hover:text-white text-xs">Dismiss</button>
 )}
 </div>
 ))}
 </div>
 ) : (
 <p className="text-[var(--color-text-muted)] text-sm text-center py-8">No alerts — everything is running smoothly</p>
 )}
 </Card>
);

/* ─── Recent Transactions ─── */
const TransactionsPanel = ({ reserve }) => (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="finops-transactions">
 <h3 className="text-lg font-semibold text-white mb-4">Recent Reserve Transactions</h3>
 {reserve?.recent_transactions?.length > 0 ? (
 <div className="space-y-1 max-h-64 overflow-y-auto">
 {reserve.recent_transactions.map(t => (
 <div key={t.id} className="flex items-center justify-between py-2 border-b border-white/5">
 <div className="flex items-center gap-2">
 {t.amount >= 0 ? <ArrowUpRight size={14} className="text-green-400" /> : <ArrowDownRight size={14} className="text-red-400" />}
 <div>
 <p className="text-white text-sm">{t.description}</p>
 <p className="text-[#666] text-[10px]">{new Date(t.created_at).toLocaleString()}</p>
 </div>
 </div>
 <p className={`font-mono text-sm font-semibold ${t.amount >= 0 ? 'text-green-400' : 'text-red-400'}`}>
 {t.amount >= 0 ? '+' : ''}{fmt(t.amount)}
 </p>
 </div>
 ))}
 </div>
 ) : (
 <p className="text-[var(--color-text-muted)] text-sm text-center py-8">No transactions yet — reserve fund is empty</p>
 )}
 </Card>
);


/* ─── Main Component ─── */
const FinancialOpsPanel = () => {
 const { API } = useAuth();
 const [dashboard, setDashboard] = useState(null);
 const [reserve, setReserve] = useState(null);
 const [alerts, setAlerts] = useState([]);
 const [config, setConfig] = useState(null);
 const [loading, setLoading] = useState(true);
 const [saving, setSaving] = useState(false);
 const [depositAmount, setDepositAmount] = useState('');
 const [topUpAmount, setTopUpAmount] = useState('');
 const token = localStorage.getItem('token');
 const headers = { Authorization: `Bearer ${token}` };

 const load = useCallback(async () => {
 setLoading(true);
 try {
 const [dashRes, resRes, alertRes, configRes] = await Promise.all([
 axios.get(`${API}/financial-ops/dashboard`, { headers }),
 axios.get(`${API}/financial-ops/reserve`, { headers }),
 axios.get(`${API}/financial-ops/alerts`, { headers }),
 axios.get(`${API}/financial-ops/config`, { headers }),
 ]);
 setDashboard(dashRes.data);
 setReserve(resRes.data);
 setAlerts(alertRes.data.alerts || []);
 setConfig(configRes.data);
 } catch (err) {
 notify.error('Failed to load financial data');
 } finally {
 setLoading(false);
 }
 }, [API]);

 useEffect(() => { load(); }, [load]);

 const saveConfig = async () => {
 setSaving(true);
 try {
 await axios.put(`${API}/financial-ops/config`, config, { headers });
 notify.success('Configuration saved');
 load();
 } catch { notify.error('Failed to save'); }
 setSaving(false);
 };

 const updateCostCentre = async (portalId, field, value) => {
 setConfig(prev => ({
 ...prev,
 cost_centres: {
 ...prev.cost_centres,
 [portalId]: { ...prev.cost_centres[portalId], [field]: value },
 },
 }));
 };

 const saveCostCentre = async (portalId) => {
 try {
 await axios.put(`${API}/financial-ops/cost-centres/${portalId}`, config.cost_centres[portalId], { headers });
 notify.success(`${portalId} cost centre updated`);
 } catch { notify.error('Failed to update cost centre'); }
 };

 const handleDeposit = async () => {
 const amt = parseFloat(depositAmount);
 if (!amt || amt <= 0) return notify.error('Enter a valid amount');
 try {
 const res = await axios.post(`${API}/financial-ops/reserve/manual-deposit`, { amount: amt, description: 'Manual deposit' }, { headers });
 notify.success(`Deposited ${fmt(amt)}. New balance: ${fmt(res.data.new_reserve_balance)}`);
 setDepositAmount('');
 load();
 } catch { notify.error('Deposit failed'); }
 };

 const handleLlmTopUp = async () => {
 const amt = parseFloat(topUpAmount) || config?.llm_top_up_amount || 50;
 try {
 const res = await axios.post(`${API}/financial-ops/llm-top-up`, { amount: amt }, { headers });
 notify.success(`LLM top-up of ${fmt(amt)} processed. Reserve: ${fmt(res.data.new_reserve_balance)}`);
 setTopUpAmount('');
 load();
 } catch (err) {
 notifyApiError(notify, err, 'Top-up failed');
 }
 };

 const dismissAlert = async (id) => {
 try {
 await axios.put(`${API}/financial-ops/alerts/${id}/read`, {}, { headers });
 setAlerts(prev => prev.map(a => a.id === id ? { ...a, read: true } : a));
 } catch {}
 };

 const onConfigChange = (key, value) => setConfig(prev => ({ ...prev, [key]: value }));

 const purgeTestData = async () => {
 const yes = window.confirm(
 'Purge all test/seed platform-activity data?\n\n' +
 'This wipes revenue_distributions, reserve_transactions, financial_alerts, llm_top_up_log ' +
 'plus any faults/equipment/jobs/contracts flagged as test/seed/demo.\n\n' +
 'Users, organisations, Stripe webhook events and audit logs are preserved. Continue?'
 );
 if (!yes) return;
 try {
 const res = await axios.post(`${API}/master-admin/test-data/purge`, {}, { headers });
 notify.success(`Purged test data — flagged: ${res.data.flagged_total}`);
 load();
 } catch { notify.error('Purge failed'); }
 };

 if (loading) return <div className="text-[var(--color-text-muted)] text-center py-16"><Loader2 className="animate-spin mx-auto mb-2" size={24} />Loading financial operations...</div>;
 if (!dashboard) return <div className="text-[var(--color-text-muted)] text-center py-16">Unable to load financial data</div>;

 return (
 <div className="space-y-6" data-testid="financial-ops-panel">
 {/* Reserve Health */}
 <ReserveHealth dashboard={dashboard} />

 {/* Metrics */}
 <MetricCards dashboard={dashboard} />

 {/* Revenue Flow */}
 <RevenueFlowDiagram config={config} />

 {/* Cost Centres */}
 <CostCentres config={config} onUpdate={updateCostCentre} saving={saving} />
 <div className="flex gap-2">
 <Button size="sm" onClick={() => saveCostCentre('pulse')} className="bg-[var(--color-brand-cyan-hover)] text-white" data-testid="finops-save-pulse-centre">
 Save Pulse Cost Centre
 </Button>
 </div>

 {/* Quick Actions */}
 <div className="grid md:grid-cols-2 gap-4">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="finops-manual-deposit">
 <h3 className="text-white font-semibold mb-3">Manual Reserve Deposit</h3>
 <div className="flex gap-2">
 <Input
 type="number"
 placeholder="Amount (£)"
 value={depositAmount}
 onChange={e => setDepositAmount(e.target.value)}
 className="bg-black/30 border-white/10 text-white h-10 flex-1"
 data-testid="finops-deposit-amount"
 />
 <Button onClick={handleDeposit} className="bg-green-600 text-white hover:bg-green-500 h-10" data-testid="finops-deposit-btn">
 <ArrowUpRight size={16} className="mr-1" /> Deposit
 </Button>
 </div>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="finops-llm-topup">
 <h3 className="text-white font-semibold mb-3">LLM Credit Top-Up</h3>
 <p className="text-[var(--color-text-muted)] text-xs mb-3">Deducted from operations reserve</p>
 <div className="flex gap-2">
 <Input
 type="number"
 placeholder={`Default: £${config?.llm_top_up_amount || 50}`}
 value={topUpAmount}
 onChange={e => setTopUpAmount(e.target.value)}
 className="bg-black/30 border-white/10 text-white h-10 flex-1"
 data-testid="finops-topup-amount"
 />
 <Button onClick={handleLlmTopUp} className="bg-purple-600 text-white hover:bg-purple-500 h-10" data-testid="finops-topup-btn">
 <Brain size={16} className="mr-1" /> Top Up
 </Button>
 </div>
 </Card>
 </div>

 {/* Config */}
 <ConfigPanel config={config} onConfigChange={onConfigChange} onSave={saveConfig} saving={saving} />

 {/* Alerts + Transactions side by side */}
 <div className="grid md:grid-cols-2 gap-4">
 <AlertsPanel alerts={alerts} onDismiss={dismissAlert} />
 <TransactionsPanel reserve={reserve} />
 </div>

 {/* Test Data Purge — danger zone */}
 <Card className="bg-red-500/5 border-red-500/30 p-5" data-testid="finops-test-data-purge">
 <div className="flex items-center justify-between gap-3 flex-wrap">
 <div>
 <h3 className="text-white font-semibold flex items-center gap-2">
 <AlertTriangle size={16} className="text-red-400" /> Test Data Purge
 </h3>
 <p className="text-[var(--color-text-muted)] text-xs mt-1">
 Clear seeded/demo revenue and flagged jobs. Real Stripe payments and customer data are preserved.
 </p>
 </div>
 <Button onClick={purgeTestData} className="bg-red-600 text-white hover:bg-red-500 h-9" data-testid="finops-purge-btn">
 Purge Test Data
 </Button>
 </div>
 </Card>
 </div>
 );
};

export default FinancialOpsPanel;
