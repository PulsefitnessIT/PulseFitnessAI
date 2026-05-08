/**
 * Stripe Connect — wizard + status panel.
 *
 * Pulse Master Admins kick off the OAuth handshake here, returning to
 * /master-admin?stripe=connected once Stripe redirects back. The platform
 * (GymAxis) admin can also set the per-customer pricing / dynamic platform
 * fee from this tab.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
 CreditCard, ExternalLink, RefreshCw, CheckCircle2, AlertTriangle, Settings,
 Banknote, TrendingUp, ShieldCheck, Link2, Unlink,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useInlineBanner, useConfirm } from '@/components/notifications';

const AdminStripeConnect = ({ API, isMasterAdmin }) => {
 const token = localStorage.getItem('token');
 const headers = { Authorization: `Bearer ${token}` };
 const [status, setStatus] = useState(null);
 const [pricing, setPricing] = useState(null);
 const [analytics, setAnalytics] = useState(null);
 const [loading, setLoading] = useState(true);
 const [busy, setBusy] = useState(false);
 const [pricingForm, setPricingForm] = useState({
 price_per_customer: '', platform_fee_per_customer: '', platform_fee_pct: '', currency: 'GBP',
 });
 const { banner, show, clear } = useInlineBanner();
 const confirm = useConfirm();

 const loadAll = useCallback(async () => {
 setLoading(true);
 try {
 const [s, p, a] = await Promise.all([
 axios.get(`${API}/stripe-connect/status`, { headers }),
 axios.get(`${API}/stripe-connect/pricing`, { headers }),
 axios.get(`${API}/stripe-connect/analytics`, { headers }).catch(() => ({ data: null })),
 ]);
 setStatus(s.data);
 setPricing(p.data.pricing);
 setAnalytics(a.data);
 setPricingForm({
 price_per_customer: String(p.data.pricing.price_per_customer ?? ''),
 platform_fee_per_customer: String(p.data.pricing.platform_fee_per_customer ?? ''),
 platform_fee_pct: String(p.data.pricing.platform_fee_pct ?? ''),
 currency: p.data.pricing.currency || 'GBP',
 });
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t load Stripe state', detail: err.response?.data?.detail });
 }
 setLoading(false);
 }, [API]);
 useEffect(() => { loadAll(); }, [loadAll]);

 // Read OAuth callback result if Stripe redirected us back here
 useEffect(() => {
 const params = new URLSearchParams(window.location.search);
 if (params.get('stripe') === 'connected') {
 show({ tone: 'success', title: 'Connected to Stripe', detail: 'Charges and payouts will activate once Stripe finishes verifying the account.' });
 window.history.replaceState({}, '', window.location.pathname);
 loadAll();
 } else if (params.get('stripe') === 'error') {
 show({ tone: 'error', title: 'Connection failed', detail: params.get('error_description') || 'Try again or contact support.' });
 window.history.replaceState({}, '', window.location.pathname);
 }
 }, [loadAll]); // eslint-disable-line

 const startOnboard = async () => {
 clear();
 setBusy(true);
 try {
 const { data } = await axios.get(`${API}/stripe-connect/onboard-url`, { headers });
 window.location.href = data.url;
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t start Stripe onboarding', detail: err.response?.data?.detail });
 setBusy(false);
 }
 };

 const disconnect = async () => {
 const ok = await confirm({
 title: 'Disconnect Stripe?',
 body: 'Pulse will no longer be able to take payments through this connection. You can reconnect any time.',
 tone: 'danger',
 confirmLabel: 'Disconnect',
 });
 if (!ok) return;
 try {
 await axios.post(`${API}/stripe-connect/disconnect`, {}, { headers });
 show({ tone: 'success', title: 'Disconnected from Stripe' });
 loadAll();
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t disconnect', detail: err.response?.data?.detail });
 }
 };

 const savePricing = async (e) => {
 e.preventDefault();
 clear();
 try {
 await axios.put(`${API}/stripe-connect/pricing`, {
 price_per_customer: parseFloat(pricingForm.price_per_customer || 0),
 platform_fee_per_customer: parseFloat(pricingForm.platform_fee_per_customer || 0),
 platform_fee_pct: parseFloat(pricingForm.platform_fee_pct || 0),
 currency: pricingForm.currency || 'GBP',
 }, { headers });
 show({ tone: 'success', title: 'Pricing saved' });
 loadAll();
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t save pricing', detail: err.response?.data?.detail });
 }
 };

 if (loading) return <div className="py-12 text-center text-zinc-400 text-sm">Loading Stripe Connect state…</div>;

 // ── Step indicator at the top of the wizard ──
 const steps = [
 { id: 'configure', label: 'Server configured', done: status?.configured },
 { id: 'connect', label: 'Stripe connected', done: status?.connected },
 { id: 'verify', label: 'Charges enabled', done: status?.charges_enabled },
 ];
 const completedSteps = steps.filter((s) => s.done).length;

 return (
 <div className="space-y-6" data-testid="admin-stripe-connect">
 {banner}

 {/* Wizard progress */}
 <Card className="p-5 rounded-xl border-zinc-200">
 <div className="flex items-center gap-2 mb-4">
 <CreditCard size={18} className="text-[var(--color-brand-blue)]" />
 <h2 className="text-base font-semibold">Connect Pulse Fitness to Stripe</h2>
 </div>
 <div className="flex items-center gap-3 mb-4" data-testid="stripe-wizard-steps">
 {steps.map((s, i) => (
 <React.Fragment key={s.id}>
 <div className="flex items-center gap-2">
 <div
 className={`w-7 h-7 rounded-full grid place-items-center text-xs font-bold ${
 s.done ? 'bg-emerald-100 text-emerald-700' : i === completedSteps ? 'bg-[var(--color-brand-blue)] text-white' : 'bg-zinc-100 text-zinc-400'
 }`}
 >
 {s.done ? <CheckCircle2 size={14} /> : i + 1}
 </div>
 <span className={`text-xs font-medium ${s.done ? 'text-zinc-700' : i === completedSteps ? 'text-[var(--color-brand-blue)]' : 'text-zinc-400'}`}>{s.label}</span>
 </div>
 {i < steps.length - 1 && <div className={`flex-1 h-px ${s.done ? 'bg-emerald-200' : 'bg-zinc-200'}`} />}
 </React.Fragment>
 ))}
 </div>

 {/* Step 1 — Server config */}
 {!status?.configured && (
 <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 flex gap-3" data-testid="stripe-step-configure">
 <AlertTriangle size={18} className="text-amber-700 shrink-0 mt-0.5" />
 <div className="flex-1">
 <p className="text-sm font-semibold text-amber-900">Stripe Connect server config missing</p>
 <p className="text-xs text-amber-800 mt-1 leading-relaxed">
 Before the wizard can run, the platform admin must set these in the backend <code className="font-mono">.env</code>:
 </p>
 <ul className="mt-2 text-xs text-amber-800 font-mono space-y-0.5 list-disc list-inside">
 <li>STRIPE_SECRET_KEY (already set if other Stripe features work)</li>
 <li>STRIPE_CONNECT_CLIENT_ID — from <a className="underline" href="https://dashboard.stripe.com/settings/connect/onboarding-options/oauth" target="_blank" rel="noreferrer">Stripe Dashboard → Connect → OAuth settings</a></li>
 <li>STRIPE_CONNECT_REDIRECT_URI — must exactly match the OAuth redirect URI configured in Stripe</li>
 </ul>
 <p className="text-xs text-amber-800 mt-2">
 After setting these, restart the backend (or the platform owner can hit the "Hot reload .env" toggle) and refresh this page.
 </p>
 </div>
 </div>
 )}

 {/* Step 2 — Connect */}
 {status?.configured && !status?.connected && (
 <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4" data-testid="stripe-step-connect">
 <p className="text-sm text-zinc-700 mb-3 leading-relaxed">
 Stripe will ask Pulse Fitness to authorise GymAxis to take application fees on Pulse's
 charges. This uses Stripe's standard <strong>Connect with Stripe</strong> OAuth — Pulse
 keeps full control of their own Stripe Dashboard.
 </p>
 <Button onClick={startOnboard} disabled={busy} className="bg-[#635BFF] hover:bg-[#4F46E5] text-white rounded-full" data-testid="stripe-connect-start">
 {busy ? 'Redirecting…' : <><Link2 size={14} className="mr-1.5" /> Connect with Stripe</>}
 <ExternalLink size={12} className="ml-1.5 opacity-70" />
 </Button>
 </div>
 )}

 {/* Step 3 — Connected */}
 {status?.connected && (
 <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 space-y-3" data-testid="stripe-step-connected">
 <div className="flex items-center gap-2">
 <CheckCircle2 size={18} className="text-emerald-700" />
 <p className="text-sm font-semibold text-emerald-900">Connected to Stripe</p>
 {status.livemode && <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-200">live mode</span>}
 {!status.livemode && <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200">test mode</span>}
 </div>
 <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
 <div><dt className="text-emerald-800 font-semibold">Account ID</dt><dd className="font-mono text-emerald-900 truncate">{status.account_id}</dd></div>
 <div><dt className="text-emerald-800 font-semibold">Country</dt><dd className="text-emerald-900">{status.country?.toUpperCase() || '—'}</dd></div>
 <div><dt className="text-emerald-800 font-semibold">Charges enabled</dt><dd className={status.charges_enabled ? 'text-emerald-900' : 'text-amber-700'}>{status.charges_enabled ? 'Yes' : 'Pending Stripe verification'}</dd></div>
 <div><dt className="text-emerald-800 font-semibold">Payouts enabled</dt><dd className={status.payouts_enabled ? 'text-emerald-900' : 'text-amber-700'}>{status.payouts_enabled ? 'Yes' : 'Pending'}</dd></div>
 </dl>
 <div className="flex flex-wrap gap-2 pt-1">
 <Button size="sm" variant="outline" onClick={loadAll}><RefreshCw size={12} className="mr-1" /> Refresh status</Button>
 <Button size="sm" variant="outline" className="text-red-600 border-red-200 hover:bg-red-50" onClick={disconnect} data-testid="stripe-disconnect">
 <Unlink size={12} className="mr-1" /> Disconnect
 </Button>
 </div>
 </div>
 )}
 </Card>

 {/* Pricing config */}
 <Card className="p-5 rounded-xl border-zinc-200">
 <div className="flex items-center gap-2 mb-4">
 <Banknote size={18} className="text-[var(--color-brand-blue)]" />
 <h2 className="text-base font-semibold">Per-customer pricing & platform fee</h2>
 {!isMasterAdmin && <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-zinc-100 text-zinc-500 border border-zinc-200">read-only</span>}
 </div>
 <p className="text-xs text-zinc-500 leading-relaxed mb-4">
 The platform fee is calculated per charge as <code className="font-mono">platform_fee_per_customer + platform_fee_pct%</code>.
 Only the GymAxis Master Admin can change these values.
 </p>
 <form onSubmit={savePricing} className="grid grid-cols-1 md:grid-cols-4 gap-3">
 <div>
 <Label className="text-xs">Price per customer</Label>
 <Input type="number" step="0.01" value={pricingForm.price_per_customer} onChange={(e) => setPricingForm({ ...pricingForm, price_per_customer: e.target.value })} disabled={!isMasterAdmin} className="mt-1" data-testid="pricing-price" />
 </div>
 <div>
 <Label className="text-xs">Platform fee (flat)</Label>
 <Input type="number" step="0.01" value={pricingForm.platform_fee_per_customer} onChange={(e) => setPricingForm({ ...pricingForm, platform_fee_per_customer: e.target.value })} disabled={!isMasterAdmin} className="mt-1" data-testid="pricing-fee" />
 </div>
 <div>
 <Label className="text-xs">Platform fee (%)</Label>
 <Input type="number" step="0.01" min="0" max="100" value={pricingForm.platform_fee_pct} onChange={(e) => setPricingForm({ ...pricingForm, platform_fee_pct: e.target.value })} disabled={!isMasterAdmin} className="mt-1" data-testid="pricing-pct" />
 </div>
 <div>
 <Label className="text-xs">Currency</Label>
 <Input value={pricingForm.currency} onChange={(e) => setPricingForm({ ...pricingForm, currency: e.target.value.toUpperCase() })} disabled={!isMasterAdmin} maxLength={3} className="mt-1 font-mono" data-testid="pricing-currency" />
 </div>
 {isMasterAdmin && (
 <div className="md:col-span-4">
 <Button type="submit" className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white rounded-full" data-testid="pricing-save">
 <Settings size={14} className="mr-1.5" /> Save pricing
 </Button>
 </div>
 )}
 </form>
 {pricing && pricingForm.price_per_customer && (
 <div className="mt-4 rounded-lg p-3 bg-blue-50 border border-blue-200 flex items-start gap-2.5" data-testid="pricing-preview">
 <TrendingUp size={14} className="text-blue-700 mt-0.5" />
 <div className="text-xs text-blue-900 leading-relaxed">
 <strong>Preview:</strong> on a {pricingForm.currency} {Number(pricingForm.price_per_customer).toFixed(2)} charge,
 GymAxis takes {pricingForm.currency} {(parseFloat(pricingForm.platform_fee_per_customer || 0) + parseFloat(pricingForm.price_per_customer || 0) * parseFloat(pricingForm.platform_fee_pct || 0) / 100).toFixed(2)}{' '}
 ({pricingForm.platform_fee_pct || 0}% + {pricingForm.currency} {pricingForm.platform_fee_per_customer || '0.00'} flat).
 Pulse keeps the rest.
 </div>
 </div>
 )}
 </Card>

 {/* Why Connect Standard */}
 <Card className="p-5 rounded-xl border-zinc-200 bg-zinc-50">
 <div className="flex items-center gap-2 mb-3">
 <ShieldCheck size={16} className="text-zinc-500" />
 <h3 className="text-sm font-semibold text-zinc-700">Why Stripe Connect Standard?</h3>
 </div>
 <ul className="text-xs text-zinc-600 space-y-1.5 leading-relaxed">
 <li>• Pulse Fitness keeps their own Stripe Dashboard, payouts, refunds, and tax handling.</li>
 <li>• GymAxis only takes the configured application fee per charge — never holds Pulse's money.</li>
 <li>• Pulse's Stripe account stays portable: if they ever leave the platform, it goes with them.</li>
 <li>• PCI compliance, fraud screening, and chargebacks are Stripe's problem, not ours.</li>
 </ul>
 </Card>

 {/* Profit-per-customer analytics */}
 <ProfitAnalyticsCard
 analytics={analytics}
 currency={pricing?.currency || 'GBP'}
 connected={!!status?.connected}
 isDevFake={!!status?.account_id?.startsWith('acct_dev_')}
 onSeed={async () => {
 try {
 // If no connection yet, fake one so the seeder has somewhere to attach.
 if (!status?.connected) {
 await axios.post(`${API}/stripe-connect/dev/fake-connection`, {}, { headers });
 }
 const { data } = await axios.post(`${API}/stripe-connect/dev/seed-events`, {}, { headers });
 show({ tone: 'success', title: `Seeded ${data.seeded} dev charges` });
 loadAll();
 } catch (err) {
 show({ tone: 'error', title: 'Seed failed', detail: err.response?.data?.detail });
 }
 }}
 onTestCharge={async (charge) => {
 try {
 const { data } = await axios.post(`${API}/stripe-connect/charges`, charge, { headers });
 const fee = (data.application_fee_amount / 100).toFixed(2);
 const amt = (data.amount / 100).toFixed(2);
 show({
 tone: 'success',
 title: `Charge ${data.simulated ? 'simulated' : 'created'}: ${data.charge_id}`,
 detail: `${charge.currency || pricing?.currency || 'GBP'} ${amt} charged · platform fee ${charge.currency || pricing?.currency || 'GBP'} ${fee}.`,
 });
 loadAll();
 } catch (err) {
 show({ tone: 'error', title: 'Charge failed', detail: err.response?.data?.detail });
 }
 }}
 onRefresh={loadAll}
 />
 </div>
 );
};

// ── Profit-per-customer analytics ────────────────────────────────────────
const ProfitAnalyticsCard = ({ analytics, currency, connected, isDevFake, onSeed, onTestCharge, onRefresh }) => {
 const fmt = (n) => `${currency === 'gbp' ? '£' : currency.toUpperCase() + ' '}${Number(n || 0).toFixed(2)}`;
 const totals = analytics?.totals || {};
 const customers = analytics?.customers || [];
 const hasData = customers.length > 0;
 const [showTest, setShowTest] = useState(false);
 const [testForm, setTestForm] = useState({
 amount: '99', customer_email: '', customer_name: '', payment_method: 'pm_card_visa',
 });
 const [testBusy, setTestBusy] = useState(false);

 const submitTest = async (e) => {
 e.preventDefault();
 if (!testForm.customer_email || !testForm.amount) return;
 setTestBusy(true);
 await onTestCharge({
 amount: parseFloat(testForm.amount),
 currency: currency.toUpperCase(),
 customer_email: testForm.customer_email,
 customer_name: testForm.customer_name,
 payment_method: testForm.payment_method,
 description: `Test charge from Master Admin · ${testForm.customer_email}`,
 metadata: { source: 'master_admin_test_charge' },
 });
 setTestBusy(false);
 setTestForm({ ...testForm, customer_email: '', customer_name: '' });
 };

 return (
 <Card className="p-5 rounded-xl border-zinc-200" data-testid="stripe-analytics">
 <div className="flex items-center justify-between mb-4">
 <div className="flex items-center gap-2">
 <TrendingUp size={18} className="text-[var(--color-brand-blue)]" />
 <h2 className="text-base font-semibold">Profit per customer</h2>
 </div>
 <div className="flex gap-2">
 <Button size="sm" variant="outline" onClick={onRefresh} className="text-zinc-600">
 <RefreshCw size={12} className="mr-1" /> Refresh
 </Button>
 {connected && (
 <Button size="sm" variant="outline" onClick={() => setShowTest((v) => !v)} className="text-[var(--color-brand-blue)]" data-testid="stripe-test-charge-toggle">
 <Banknote size={12} className="mr-1" /> {showTest ? 'Hide' : 'Test charge'}
 </Button>
 )}
 {!hasData && (
 <Button size="sm" variant="outline" onClick={onSeed} className="text-zinc-600" data-testid="stripe-analytics-seed">
 Seed dev data
 </Button>
 )}
 </div>
 </div>

 {/* Test charge panel */}
 {showTest && connected && (
 <div className="mb-5 rounded-lg border border-blue-200 bg-blue-50 p-4" data-testid="stripe-test-charge-panel">
 <p className="text-xs font-semibold text-blue-900 uppercase tracking-wider mb-2">
 {isDevFake ? 'Simulated test charge (dev account)' : 'Test charge (live Stripe account)'}
 </p>
 <p className="text-[11px] text-blue-800 mb-3 leading-relaxed">
 {isDevFake
 ? 'Bypasses Stripe entirely — inserts a charge row directly so you can verify the fee maths and analytics. Use \'Seed dev data\' for bulk seeding.'
 : 'Uses Stripe\'s test PaymentMethod (pm_card_visa) against the connected account. Charges are real but reversible from the Stripe Dashboard.'}
 </p>
 <form onSubmit={submitTest} className="grid grid-cols-1 md:grid-cols-4 gap-2 items-end">
 <div>
 <Label className="text-xs text-blue-900">Amount ({currency.toUpperCase()})</Label>
 <Input type="number" step="0.01" min="0.01" value={testForm.amount} onChange={(e) => setTestForm({ ...testForm, amount: e.target.value })} className="mt-1 h-9" data-testid="test-charge-amount" required />
 </div>
 <div>
 <Label className="text-xs text-blue-900">Customer email</Label>
 <Input type="email" value={testForm.customer_email} onChange={(e) => setTestForm({ ...testForm, customer_email: e.target.value })} placeholder="customer@gym.com" className="mt-1 h-9" data-testid="test-charge-email" required />
 </div>
 <div>
 <Label className="text-xs text-blue-900">Customer name</Label>
 <Input value={testForm.customer_name} onChange={(e) => setTestForm({ ...testForm, customer_name: e.target.value })} placeholder="Cardio Studio" className="mt-1 h-9" data-testid="test-charge-name" />
 </div>
 <div>
 <Button type="submit" disabled={testBusy} className="w-full h-9 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white rounded-full" data-testid="test-charge-submit">
 {testBusy ? 'Charging…' : 'Run test charge'}
 </Button>
 </div>
 {!isDevFake && (
 <div className="md:col-span-4">
 <Label className="text-xs text-blue-900">PaymentMethod id</Label>
 <Input value={testForm.payment_method} onChange={(e) => setTestForm({ ...testForm, payment_method: e.target.value })} className="mt-1 h-9 font-mono" data-testid="test-charge-pm" />
 <p className="text-[10px] text-blue-700 mt-1">
 Default <code>pm_card_visa</code> is Stripe's universal test card. Replace with a real PaymentMethod id for production charges.
 </p>
 </div>
 )}
 </form>
 </div>
 )}

 {!hasData ? (
 <div className="py-10 text-center text-zinc-400 text-sm" data-testid="stripe-analytics-empty">
 {connected
 ? 'No charges yet — once Pulse takes their first payment, this dashboard fills in.'
 : 'Connect Stripe (or click "Seed dev data" above to preview the dashboard with fake numbers).'}
 </div>
 ) : (
 <>
 {/* Headline KPIs */}
 <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5" data-testid="stripe-analytics-totals">
 <KPI label="Customers" value={totals.customers} />
 <KPI label="Charges" value={totals.charges} />
 <KPI label="Gross revenue" value={fmt(totals.gross_revenue)} />
 <KPI label="Refunded" value={fmt(totals.refunded)} tone="warn" />
 <KPI label="Platform fees" value={fmt(totals.platform_fees)} tone="info" />
 <KPI label="Platform profit" value={fmt(totals.platform_profit)} tone="success" highlight />
 <KPI label="Pulse take-home" value={fmt(totals.pulse_take_home)} tone="info" />
 <KPI label="Avg per customer" value={fmt((totals.platform_profit || 0) / Math.max(totals.customers || 1, 1))} />
 </div>

 {/* Per-customer table */}
 <div className="overflow-x-auto -mx-2">
 <table className="w-full text-xs border-collapse" data-testid="stripe-analytics-table">
 <thead>
 <tr className="text-left text-zinc-500 border-b border-zinc-200">
 <th className="px-2 py-2 font-medium">Customer</th>
 <th className="px-2 py-2 font-medium text-right">Charges</th>
 <th className="px-2 py-2 font-medium text-right">Gross</th>
 <th className="px-2 py-2 font-medium text-right">Refunded</th>
 <th className="px-2 py-2 font-medium text-right">Fees</th>
 <th className="px-2 py-2 font-medium text-right">Platform profit</th>
 <th className="px-2 py-2 font-medium text-right">Last charge</th>
 </tr>
 </thead>
 <tbody>
 {customers.map((c, i) => (
 <tr key={i} className="border-b border-zinc-100 hover:bg-zinc-50">
 <td className="px-2 py-2">
 <p className="font-medium text-zinc-900 truncate max-w-[220px]">{c.customer_name || c.customer_email}</p>
 {c.customer_name && <p className="text-zinc-400 text-[11px] truncate">{c.customer_email}</p>}
 </td>
 <td className="px-2 py-2 text-right text-zinc-700">{c.charges_count}</td>
 <td className="px-2 py-2 text-right text-zinc-700">{fmt(c.gross_revenue)}</td>
 <td className="px-2 py-2 text-right">{c.refunded > 0 ? <span className="text-amber-600">{fmt(c.refunded)}</span> : <span className="text-zinc-400">—</span>}</td>
 <td className="px-2 py-2 text-right text-blue-600">{fmt(c.platform_fees)}</td>
 <td className="px-2 py-2 text-right text-emerald-600 font-semibold">{fmt(c.platform_profit)}</td>
 <td className="px-2 py-2 text-right text-zinc-500 text-[11px]">{c.last_charge ? new Date(c.last_charge).toLocaleDateString() : '—'}</td>
 </tr>
 ))}
 </tbody>
 </table>
 </div>
 </>
 )}
 </Card>
 );
};

const KPI = ({ label, value, tone = 'default', highlight = false }) => {
 const tones = {
 default: 'text-zinc-900',
 info: 'text-blue-700',
 success: 'text-emerald-700',
 warn: 'text-amber-700',
 };
 return (
 <div className={`rounded-lg p-3 border ${highlight ? 'bg-emerald-50 border-emerald-200' : 'bg-zinc-50 border-zinc-200'}`}>
 <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">{label}</p>
 <p className={`text-base font-bold mt-0.5 ${tones[tone]}`}>{value}</p>
 </div>
 );
};

export default AdminStripeConnect;
