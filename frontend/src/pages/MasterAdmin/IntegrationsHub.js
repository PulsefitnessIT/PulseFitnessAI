/**
 * Iter 216h22 — Master Admin Integrations Hub (P5 redesign).
 *
 * Single page that consolidates the 4 integration surfaces operators
 * deal with daily:
 *   • Stripe Connect — platform-level OAuth + per-customer onboarding
 *   • Sicon Service  — Sage 200 ledger bridge (cases + invoices)
 *   • Orbit 4        — stock / equipment master
 *   • Sage 200       — per-org customer ledger numbers (rides Sicon)
 *
 * Layout:
 *   ┌────────────────────────────────────────────────────────┐
 *   │ Title + summary pills (X connected · Y degraded · …)   │
 *   ├──────────┬──────────┬──────────┬───────────────────────┤
 *   │ Stripe   │ Sicon    │ Orbit 4  │ Sage 200              │
 *   │  card    │  card    │  card    │  card                 │
 *   └──────────┴──────────┴──────────┴───────────────────────┘
 *
 * Each card carries: status pill · brand badge · last sync · events 24h
 * · org coverage (X of Y orgs configured). Clicking the card opens a
 * right-hand drawer with the FULL existing configuration page embedded
 * — mappings, logs, config, per-org table all preserved.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { ArrowLeftRight, Banknote, Plug, ShieldCheck, RefreshCw, AlertTriangle, CheckCircle2, Clock, XCircle, ExternalLink, Settings } from 'lucide-react';
import Button from '@/components/shared/Button';
import SiconIntegrationPage from './SiconIntegrationPage';
import IntegrationAdminPanel from '../IntegrationAdminPanel';
import AdminStripeConnect from './AdminStripeConnect';
import { useBrandContext } from './BrandContext';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_TONES = {
  connected:      { label: 'Connected',      bg: '#ECFDF5', fg: '#047857', border: '#A7F3D0', icon: CheckCircle2 },
  degraded:       { label: 'Degraded',       bg: '#FFFBEB', fg: '#B45309', border: '#FDE68A', icon: AlertTriangle },
  not_configured: { label: 'Not configured', bg: '#FAFAFA', fg: '#52525B', border: '#E4E4E7', icon: XCircle },
  down:           { label: 'Down',           bg: '#FEF2F2', fg: '#B91C1C', border: '#FECACA', icon: XCircle },
};

const ICONS = {
  stripe_connect: Banknote,
  sicon:          ArrowLeftRight,
  orbit4:         Plug,
  sage200:        ShieldCheck,
};

const BRAND_TONES = {
  pulse:   { label: 'Pulse Fitness', bg: 'rgba(0,85,255,0.08)', fg: '#1D4ED8' },
  gymaxis: { label: 'GymAxis',       bg: 'rgba(16,185,129,0.10)', fg: '#047857' },
  all:     { label: 'Both brands',   bg: 'rgba(63,63,70,0.08)', fg: '#3F3F46' },
};

const formatSince = (iso) => {
  if (!iso) return 'No events recorded';
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return iso;
  const ms = Date.now() - then.getTime();
  const mins = Math.round(ms / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
};

const StatusPill = ({ status, testId }) => {
  const tone = STATUS_TONES[status] || STATUS_TONES.not_configured;
  const Icon = tone.icon;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
      style={{ background: tone.bg, color: tone.fg, borderColor: tone.border }}
      data-testid={testId}
    >
      <Icon size={10} />
      {tone.label}
    </span>
  );
};

const BrandBadge = ({ brand }) => {
  const tone = BRAND_TONES[brand] || BRAND_TONES.all;
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold"
      style={{ background: tone.bg, color: tone.fg }}
      data-testid={`integrations-hub-brand-${brand}`}
    >
      {tone.label}
    </span>
  );
};

const IntegrationCard = ({ row, brand, onOpen }) => {
  const Icon = ICONS[row.key] || Plug;
  const coveragePct = row.orgs_total > 0 ? Math.round((row.orgs_configured / row.orgs_total) * 100) : 0;

  return (
    <button
      type="button"
      onClick={() => onOpen(row.key)}
      className="text-left rounded-xl border bg-white p-4 hover:shadow-md transition-shadow group focus:outline-none focus:ring-2 focus:ring-blue-200"
      style={{ borderColor: '#E4E4E7' }}
      data-testid={`integrations-hub-card-${row.key}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-9 h-9 rounded-md flex items-center justify-center bg-zinc-50 flex-shrink-0">
            <Icon size={16} className="text-zinc-700" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-bold text-zinc-900 truncate">{row.label}</p>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mt-0.5">{row.key.replace(/_/g, ' ')}</p>
          </div>
        </div>
        <StatusPill status={row.status} testId={`integrations-hub-status-${row.key}`} />
      </div>

      <div className="flex items-center gap-1.5 flex-wrap mb-3">
        <BrandBadge brand={brand} />
        {row.platform_fee_pct != null && (
          <span className="text-[10px] text-zinc-500">Fee {row.platform_fee_pct}%</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 text-[11px] mb-3">
        <div className="rounded-md bg-zinc-50 px-2 py-1.5">
          <div className="text-[9px] uppercase tracking-wider font-bold text-zinc-400">Org coverage</div>
          <div className="font-bold text-zinc-900 mt-0.5">
            {row.orgs_configured}
            <span className="text-zinc-400 font-normal"> / {row.orgs_total}</span>
            <span className="text-[10px] text-zinc-500 ml-1">({coveragePct}%)</span>
          </div>
        </div>
        <div className="rounded-md bg-zinc-50 px-2 py-1.5">
          <div className="text-[9px] uppercase tracking-wider font-bold text-zinc-400">Last 24 h</div>
          <div className="font-bold text-zinc-900 mt-0.5">
            {row.events_24h} <span className="text-zinc-400 font-normal">events</span>
            {row.errors_24h > 0 && (
              <span className="ml-1 text-red-600">· {row.errors_24h} err</span>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between text-[10px] text-zinc-500">
        <span className="inline-flex items-center gap-1">
          <Clock size={9} /> {formatSince(row.last_event_at)}
        </span>
        <span className="inline-flex items-center gap-1 font-semibold text-blue-700 group-hover:text-blue-900">
          Open <Settings size={10} />
        </span>
      </div>
    </button>
  );
};

const IntegrationsHub = ({ isPulseAdmin = false }) => {
  const { brand, brandLabel } = useBrandContext();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [openKey, setOpenKey] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const token = localStorage.getItem('token');
      const { data: payload } = await axios.get(
        `${API_BASE}/master-admin/integrations-hub`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setData(payload);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to load integrations hub');
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load, brand]);

  const summary = data?.summary || { connected: 0, degraded: 0, not_configured: 0, total: 0 };
  const rows = data?.integrations || [];
  const effectiveBrand = isPulseAdmin ? 'pulse' : brand;

  const renderDrawerBody = () => {
    if (openKey === 'sicon') return <SiconIntegrationPage />;
    if (openKey === 'orbit4') return <IntegrationAdminPanel integrationId="orbit4" title="Orbit 4" icon={Plug} color="bg-blue-600" hideHeader />;
    if (openKey === 'stripe_connect') return <AdminStripeConnect API={API_BASE} isMasterAdmin={!isPulseAdmin} />;
    if (openKey === 'sage200') {
      return (
        <div className="space-y-4" data-testid="integrations-hub-sage-panel">
          <div className="rounded-lg border bg-zinc-50 p-4" style={{ borderColor: '#E4E4E7' }}>
            <h4 className="text-sm font-bold text-zinc-900 mb-2">Sage 200 customer ledger</h4>
            <p className="text-xs text-zinc-600 leading-relaxed">
              Sage 200 customer numbers are stored per-organisation. Posting to Sage is handled by the Sicon Service bridge — so the configuration lives in two places:
            </p>
            <ol className="text-xs text-zinc-700 list-decimal list-inside mt-2 space-y-1">
              <li>Each organisation gets a <strong>Sage customer number</strong> on its Billing tab.</li>
              <li>The Sicon Service integration must be <strong>Connected</strong> for posts to actually reach Sage.</li>
            </ol>
          </div>
          <div className="rounded-lg border p-4" style={{ borderColor: '#E4E4E7' }}>
            <h5 className="text-xs font-bold uppercase tracking-wider text-zinc-500 mb-2">Field mapping (read-only)</h5>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-zinc-500">
                  <th className="text-left py-1 font-semibold">GymAxis field</th>
                  <th className="text-left py-1 font-semibold">Sage 200 field</th>
                </tr>
              </thead>
              <tbody className="text-zinc-700">
                <tr className="border-t" style={{ borderColor: '#F4F4F5' }}><td className="py-1.5"><code>organisation.sage_customer_number</code></td><td><code>SLCustomerAccountID</code></td></tr>
                <tr className="border-t" style={{ borderColor: '#F4F4F5' }}><td className="py-1.5"><code>organisation.sage_customer_reference</code></td><td><code>CustomerReference</code></td></tr>
                <tr className="border-t" style={{ borderColor: '#F4F4F5' }}><td className="py-1.5"><code>invoice.total</code></td><td><code>NetAmount + VATAmount</code></td></tr>
                <tr className="border-t" style={{ borderColor: '#F4F4F5' }}><td className="py-1.5"><code>invoice.line_items[].sku</code></td><td><code>StockCode</code></td></tr>
              </tbody>
            </table>
          </div>
          <div className="rounded-lg border p-4 bg-blue-50" style={{ borderColor: '#BFDBFE' }}>
            <p className="text-xs text-blue-900">
              <strong>Coverage:</strong> {rows.find(r => r.key === 'sage200')?.orgs_configured || 0} of {rows.find(r => r.key === 'sage200')?.orgs_total || 0} orgs have a Sage customer number configured.
              To add or edit, go to <strong>Organisations → row → Billing tab</strong>.
            </p>
          </div>
        </div>
      );
    }
    return null;
  };

  const openLabel = rows.find(r => r.key === openKey)?.label || '';

  return (
    <div className="space-y-5" data-testid="integrations-hub">
      {/* Summary strip */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-zinc-900 tracking-tight">Integrations hub</h2>
          <p className="text-sm text-zinc-500 mt-0.5">
            One screen for every third-party connection. Brand context: <span className="font-semibold text-zinc-700">{brandLabel}</span>. Click any card to manage.
          </p>
        </div>
        <Button
          variant="secondary" size="sm" icon={RefreshCw}
          loading={loading}
          onClick={load}
          disabled={loading}
          data-testid="integrations-hub-refresh"
        >
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="integrations-hub-summary">
        <div className="rounded-lg border bg-white p-3" style={{ borderColor: '#E4E4E7' }}>
          <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Connected</div>
          <div className="text-2xl font-bold text-emerald-700 mt-0.5">{summary.connected}<span className="text-zinc-400 font-normal text-base"> / {summary.total}</span></div>
        </div>
        <div className="rounded-lg border bg-white p-3" style={{ borderColor: '#E4E4E7' }}>
          <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Degraded</div>
          <div className="text-2xl font-bold mt-0.5" style={{ color: summary.degraded > 0 ? '#B45309' : '#71717A' }}>{summary.degraded}</div>
        </div>
        <div className="rounded-lg border bg-white p-3" style={{ borderColor: '#E4E4E7' }}>
          <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Not configured</div>
          <div className="text-2xl font-bold text-zinc-700 mt-0.5">{summary.not_configured}</div>
        </div>
        <div className="rounded-lg border bg-white p-3" style={{ borderColor: '#E4E4E7' }}>
          <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Brand scope</div>
          <div className="text-sm font-bold text-zinc-900 mt-1">{brandLabel}</div>
          {isPulseAdmin && <div className="text-[10px] text-blue-700 mt-0.5">Locked (Pulse Master Admin)</div>}
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4" data-testid="integrations-hub-grid">
        {rows.map((row) => (
          <IntegrationCard
            key={row.key}
            row={row}
            brand={effectiveBrand}
            onOpen={setOpenKey}
          />
        ))}
      </div>

      <p className="text-[10px] text-zinc-400 italic">
        Card data refreshes when you click Refresh. Drawer pages refresh independently using the existing console flows — every mapping field is editable in-drawer.
      </p>

      <Sheet open={!!openKey} onOpenChange={(o) => { if (!o) setOpenKey(null); }}>
        <SheetContent
          side="right"
          className="bg-white w-full sm:max-w-3xl overflow-y-auto"
          data-testid={`integrations-hub-drawer-${openKey || 'closed'}`}
        >
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <ExternalLink size={14} className="text-zinc-400" />
              {openLabel || 'Integration'}
            </SheetTitle>
          </SheetHeader>
          <div className="mt-4">
            {renderDrawerBody()}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
};

export default IntegrationsHub;
