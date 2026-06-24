import { useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  ClipboardCheck, BarChart3, Brain, CheckCircle, Shield,
  ArrowRight, Star, Loader2, CheckCircle2, Crown, Lock
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL;

const PRO_FEATURES = [
  {
    icon: ClipboardCheck,
    title: 'Check Sheets',
    desc: 'Create and manage daily, weekly, and monthly equipment check sheets with auto-generated templates per machine type.',
    highlights: ['Auto-generated templates', 'Staff tracking', 'Completion reports'],
  },
  {
    icon: BarChart3,
    title: 'Operational Reports',
    desc: 'Full operational reporting with self-fix rates, engineer callout tracking, cost savings, and severity breakdowns.',
    highlights: ['Self-fix rate analytics', 'Cost savings tracking', 'Equipment fault trends'],
  },
  {
    icon: Brain,
    title: 'AI Fault Diagnosis',
    desc: 'AI-powered fault diagnosis chat and automated audit report generation for any equipment type.',
    highlights: ['AI repair suggestions', 'Audit report generation', 'Equipment-specific knowledge'],
  },
  {
    icon: Shield,
    title: 'Risk Assessments',
    desc: 'Generate and manage comprehensive risk assessments for all gym equipment with automated scoring and recommendations.',
    highlights: ['Auto risk scoring', 'Mitigation tracking', 'Compliance-ready reports'],
  },
];

const COMPARISON = [
  { feature: 'Equipment Management', standard: true, pro: true },
  { feature: 'Fault Logging', standard: true, pro: true },
  { feature: 'Document Storage', standard: true, pro: true },
  { feature: 'Dashboard Overview', standard: true, pro: true },
  { feature: 'Check Sheets', standard: false, pro: true },
  { feature: 'Operational Reports', standard: false, pro: true },
  { feature: 'AI Fault Diagnosis', standard: false, pro: true },
  { feature: 'Audit Report Generation', standard: false, pro: true },
  { feature: 'Risk Assessments', standard: false, pro: true },
  { feature: 'Gym Layout Designer', standard: false, pro: true },
  { feature: 'Supplier Management', standard: false, pro: true },
  { feature: 'Weekly Digest Emails', standard: false, pro: true },
  { feature: 'Staff Performance Tracking', standard: false, pro: true },
  { feature: 'Cost Savings Analytics', standard: false, pro: true },
];

const PulseUpgradePage = ({ onDismiss }) => {
  const { user, refreshMe } = useAuth();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const isOwner = (user?.role || '').toLowerCase() === 'owner';
  const isMaster = user?.is_master_admin === true;
  const canUpgrade = isOwner || isMaster;
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;

  const handleUpgrade = async () => {
    if (!canUpgrade) {
      notify.error('Owner-only', 'Ask the organisation owner to upgrade your portal to Pulse Pro.');
      return;
    }
    setBusy(true);
    try {
      // Stage 1 of the two-step plan: unlock the full Pro version of
      // Operations. Bolt-ons (Memberships / CRM / Marketing) are added
      // separately afterwards, so we intentionally send no start_trials.
      await axios.post(
        `${API}/api/me/upgrade-to-pro`,
        {},
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setDone(true);
      notify.success(
        'Welcome to Pulse Pro',
        'Operations is now fully unlocked — AI Diagnosis, Check Sheets, Reports, Staffing and more. Reloading…',
        { duration: 7000 },
      );
      try { await refreshMe?.(); } catch (_) { /* fall back to reload */ }
      setTimeout(() => { window.location.reload(); }, 1200);
    } catch (e) {
      notifyApiError(notify, e, 'Could not complete your upgrade');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-8" data-testid="pulse-upgrade-page" data-portal="pulse">
      {/* Hero */}
      <div className="text-center max-w-2xl mx-auto">
        <Badge className="bg-[rgb(var(--rgb-pulse-primary-hover)/0.1)] text-[var(--pulse-primary-hover)] border-[rgb(var(--rgb-pulse-primary-hover)/0.2)] mb-4 px-3 py-1 text-xs font-semibold pulse-font-body">
          <Star size={12} className="mr-1" /> Pulse Fitness Pro
        </Badge>
        <h2 className="text-2xl sm:text-3xl font-bold text-zinc-900 mb-3 pulse-font-heading">
          Unlock the Full Power of Your Portal
        </h2>
        <p className="text-zinc-500 text-sm sm:text-base leading-relaxed">
          Upgrade to Pulse Fitness Pro and get AI-powered diagnostics, automated check sheets, 
          and detailed operational reports — everything you need to reduce downtime and cut costs.
        </p>
      </div>

      {/* Feature Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {PRO_FEATURES.map((feat) => (
          <Card
            key={feat.title}
            className="bg-white border-zinc-200 shadow-sm p-6 hover:shadow-md hover:border-blue-200 transition-all"
            data-testid={`upgrade-feature-${feat.title.toLowerCase().replace(/ /g, '-')}`}
          >
            <div className="w-11 h-11 rounded-xl bg-[rgb(var(--rgb-pulse-primary-hover)/0.1)] flex items-center justify-center mb-4">
              <feat.icon size={22} className="text-[var(--pulse-primary-hover)]" />
            </div>
            <h3 className="font-semibold text-zinc-900 mb-2 pulse-font-heading">{feat.title}</h3>
            <p className="text-sm text-zinc-500 mb-4 leading-relaxed pulse-font-body">{feat.desc}</p>
            <ul className="space-y-2">
              {feat.highlights.map((h) => (
                <li key={h} className="flex items-center gap-2 text-sm text-zinc-700">
                  <CheckCircle size={14} className="text-emerald-500 flex-shrink-0" />
                  {h}
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>

      {/* Comparison Table */}
      <Card className="bg-white border-zinc-200 shadow-sm overflow-hidden" data-testid="upgrade-comparison-table">
        <div className="p-5 border-b border-zinc-100">
          <h3 className="font-semibold text-zinc-900">Standard vs Pro</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50">
                <th className="text-left px-5 py-3 font-medium text-zinc-500">Feature</th>
                <th className="text-center px-5 py-3 font-medium text-zinc-500 w-28">Standard</th>
                <th className="text-center px-5 py-3 font-medium text-[var(--pulse-primary-hover)] w-28">Pro</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON.map((row) => (
                <tr key={row.feature} className="border-b border-zinc-50 hover:bg-zinc-50/50">
                  <td className="px-5 py-3 text-zinc-700">{row.feature}</td>
                  <td className="text-center px-5 py-3">
                    {row.standard ? (
                      <CheckCircle size={16} className="text-emerald-500 mx-auto" />
                    ) : (
                      <span className="text-zinc-300">—</span>
                    )}
                  </td>
                  <td className="text-center px-5 py-3">
                    {row.pro ? (
                      <CheckCircle size={16} className="text-blue-600 mx-auto" />
                    ) : (
                      <span className="text-zinc-300">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* CTA — real in-app, one-click Lite → Pro Operations upgrade. */}
      <Card className="bg-gradient-to-r from-blue-600 to-blue-700 border-0 shadow-lg p-8 text-center" data-testid="upgrade-cta">
        <Crown size={28} className="text-amber-300 mx-auto mb-3" />
        <h3 className="text-xl font-bold text-white mb-2">
          {done ? 'You\'re on Pulse Pro 🎉' : 'Upgrade to Pulse Pro'}
        </h3>
        <p className="text-blue-100 text-sm mb-6 max-w-md mx-auto">
          {done
            ? 'Your Operations portal is now fully unlocked. Reloading your dashboard…'
            : 'Unlock the full Pro version of Operations instantly — AI Fault Diagnosis, Check Sheets, Reports, Risk Assessments, Staffing and more. Memberships, CRM and Marketing can be added as bolt-ons afterwards.'}
        </p>
        <div className="flex items-center justify-center gap-3 flex-wrap">
          {canUpgrade ? (
            <Button
              className="bg-white text-blue-700 hover:bg-blue-50 font-semibold px-6 h-11 disabled:opacity-60"
              onClick={handleUpgrade}
              disabled={busy || done}
              data-testid="upgrade-now-btn"
            >
              {busy ? (
                <><Loader2 size={16} className="mr-2 animate-spin" /> Upgrading…</>
              ) : done ? (
                <><CheckCircle2 size={16} className="mr-2" /> Pro activated</>
              ) : (
                <>Upgrade to Pro <ArrowRight size={16} className="ml-2" /></>
              )}
            </Button>
          ) : (
            <Button
              className="bg-white/15 text-white border border-white/25 font-semibold px-6 h-11 cursor-not-allowed"
              disabled
              data-testid="upgrade-owner-only-btn"
            >
              <Lock size={14} className="mr-2" /> Owner can upgrade
            </Button>
          )}
          {onDismiss && !done && (
            <Button
              variant="outline"
              className="border-white/30 text-white hover:bg-white/10 px-6 h-11"
              onClick={onDismiss}
              data-testid="upgrade-dismiss-btn"
            >
              Maybe Later
            </Button>
          )}
        </div>
        <p className="text-[11px] text-blue-200/80 mt-4 inline-flex items-center justify-center gap-1.5">
          <Lock size={9} /> Instant unlock · cancel or adjust bolt-ons anytime
        </p>
      </Card>
    </div>
  );
};

export default PulseUpgradePage;
