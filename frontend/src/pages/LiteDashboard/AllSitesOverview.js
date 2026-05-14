/**
 * AllSitesOverview — Owner / Manager multi-site KPI roll-up
 * (Iter 216i).
 *
 * Renders aggregated KPIs across every site in the org plus a sorted
 * "best-performing-sites" leaderboard. Powered by GET /api/sites/overview
 * which returns a per-site score (0–100) computed from open faults,
 * overdue faults, and check-sheet completion rate.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Loader2, Trophy, AlertTriangle, Wrench, MapPin, Star, ArrowRight, TrendingUp, TrendingDown, Globe2, KeyRound, Copy, Check, Mail, X } from 'lucide-react';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import KpiTile from '@/components/shared/KpiTile';
import PageHeader from '@/components/shared/PageHeader';

const scoreColor = (s) => {
  if (s >= 80) return { bg: 'bg-emerald-100 dark:bg-emerald-500/15', text: 'text-emerald-700 dark:text-emerald-300' };
  if (s >= 50) return { bg: 'bg-amber-100 dark:bg-amber-500/15', text: 'text-amber-700 dark:text-amber-300' };
  return { bg: 'bg-red-100 dark:bg-red-500/15', text: 'text-red-700 dark:text-red-300' };
};

const AllSitesOverview = ({ onPickSite }) => {
  const { API, setActiveSite, user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // Iter 216h114 — MOD HQ users (mod_branch / mod_org) can generate or
  // rotate the shared site login for each of their child sites.
  const isModHQ = ['mod_branch', 'mod_org'].includes(user?.account_type || '');
  const [siteLoginTarget, setSiteLoginTarget] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await axios.get(`${API}/sites/overview`, {
          headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
        });
        if (alive) setData(r.data);
      } catch (e) {
        if (alive) setError(e?.response?.data?.detail || 'Could not load multi-site overview');
      } finally {
        if (alive) setLoading(false);
      }
    };
    load();
    return () => { alive = false; };
  }, [API]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16" data-testid="all-sites-loading">
        <Loader2 className="animate-spin" size={20} style={{ color: 'var(--theme-text-muted)' }} />
      </div>
    );
  }
  if (error || !data) {
    return (
      <Card className="p-6 text-center" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>{error || 'No data yet.'}</p>
      </Card>
    );
  }

  const { sites = [], totals = {}, best_site, worst_site } = data;
  const goToSite = (site) => {
    setActiveSite(site);
    onPickSite?.(site);
  };

  return (
    <div className="space-y-6" data-testid="all-sites-overview">
      <PageHeader
        title="All Operations Sites — Estate Overview"
        subtitle="Aggregated KPIs and per-site rankings across every Pulse site"
        icon={Globe2}
        testId="all-sites-header"
      />

      {/* Aggregate KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="all-sites-kpis">
        <KpiTile icon={MapPin}        label="Sites"            value={totals.sites || 0}              testId="kpi-sites" />
        <KpiTile icon={Wrench}        label="Equipment total"  value={totals.equipment || 0}          testId="kpi-equipment" />
        <KpiTile icon={AlertTriangle} label="Open faults"      value={totals.open_faults || 0}        trend={totals.overdue_faults ? `${totals.overdue_faults} overdue` : 'no overdue'} testId="kpi-open-faults" />
        <KpiTile icon={TrendingUp}    label="Faults this week" value={totals.faults_this_week || 0}   testId="kpi-faults-week" />
      </div>

      {/* Best / worst spotlight */}
      <div className="grid md:grid-cols-2 gap-3">
        {best_site ? (
          <Card className="p-4 border" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid="all-sites-best">
            <div className="flex items-center gap-2 mb-2">
              <Trophy size={16} className="text-emerald-500" />
              <span className="text-[10px] uppercase tracking-wider font-bold" style={{ color: 'var(--theme-text-muted)' }}>Best performing</span>
            </div>
            <div className="flex items-baseline gap-3">
              <span className="text-lg font-bold" style={{ color: 'var(--theme-text)' }}>{best_site.name}</span>
              <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${scoreColor(best_site.score).bg} ${scoreColor(best_site.score).text}`}>{best_site.score}/100</span>
            </div>
            <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
              {best_site.open_faults} open · {best_site.equipment_count} machines
            </p>
          </Card>
        ) : null}
        {worst_site && worst_site.id !== best_site?.id ? (
          <Card className="p-4 border" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid="all-sites-worst">
            <div className="flex items-center gap-2 mb-2">
              <TrendingDown size={16} className="text-red-500" />
              <span className="text-[10px] uppercase tracking-wider font-bold" style={{ color: 'var(--theme-text-muted)' }}>Needs attention</span>
            </div>
            <div className="flex items-baseline gap-3">
              <span className="text-lg font-bold" style={{ color: 'var(--theme-text)' }}>{worst_site.name}</span>
              <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${scoreColor(worst_site.score).bg} ${scoreColor(worst_site.score).text}`}>{worst_site.score}/100</span>
            </div>
            <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
              {worst_site.open_faults} open · {worst_site.overdue_faults} overdue
            </p>
          </Card>
        ) : null}
      </div>

      {/* Leaderboard */}
      <Card className="p-0 border overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid="all-sites-leaderboard">
        <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: 'var(--theme-border-soft)' }}>
          <h3 className="text-sm font-bold tracking-tight" style={{ color: 'var(--theme-text)' }}>Site Leaderboard</h3>
          <span className="text-[10px] uppercase tracking-wider font-bold" style={{ color: 'var(--theme-text-muted)' }}>{sites.length} sites</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: 'var(--theme-surface-2)' }}>
                <th className="text-left px-4 py-2 font-semibold text-xs" style={{ color: 'var(--theme-text-muted)' }}>#</th>
                <th className="text-left px-4 py-2 font-semibold text-xs" style={{ color: 'var(--theme-text-muted)' }}>Site</th>
                <th className="text-right px-3 py-2 font-semibold text-xs" style={{ color: 'var(--theme-text-muted)' }}>Score</th>
                <th className="text-right px-3 py-2 font-semibold text-xs hidden sm:table-cell" style={{ color: 'var(--theme-text-muted)' }}>Open</th>
                <th className="text-right px-3 py-2 font-semibold text-xs hidden md:table-cell" style={{ color: 'var(--theme-text-muted)' }}>Overdue</th>
                <th className="text-right px-3 py-2 font-semibold text-xs hidden md:table-cell" style={{ color: 'var(--theme-text-muted)' }}>Equipment</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {sites.map((s) => {
                const sc = scoreColor(s.score);
                return (
                  <tr key={s.id} className="border-t" style={{ borderColor: 'var(--theme-border-soft)' }} data-testid={`leaderboard-row-${s.id}`}>
                    <td className="px-4 py-2.5 font-bold" style={{ color: 'var(--theme-text-muted)' }}>{s.rank}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        {s.is_head_office ? <Star size={12} className="text-amber-500 shrink-0" /> : null}
                        <span className="font-semibold truncate" style={{ color: 'var(--theme-text)' }}>{s.name}</span>
                      </div>
                      {s.address ? <span className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{s.address}</span> : null}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${sc.bg} ${sc.text}`} data-testid={`leaderboard-score-${s.id}`}>{s.score}</span>
                    </td>
                    <td className="px-3 py-2.5 text-right hidden sm:table-cell" style={{ color: 'var(--theme-text)' }}>{s.open_faults}</td>
                    <td className="px-3 py-2.5 text-right hidden md:table-cell" style={{ color: s.overdue_faults > 0 ? '#dc2626' : 'var(--theme-text)' }}>{s.overdue_faults}</td>
                    <td className="px-3 py-2.5 text-right hidden md:table-cell" style={{ color: 'var(--theme-text)' }}>{s.equipment_count}</td>
                    <td className="px-3 py-2.5 text-right">
                      <div className="inline-flex items-center gap-1.5">
                        {isModHQ && (
                          <button
                            type="button"
                            onClick={() => setSiteLoginTarget(s)}
                            className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded border border-[var(--theme-border)] hover:bg-[var(--theme-hover-bg)]"
                            style={{ color: 'var(--color-brand-cyan-hover)' }}
                            data-testid={`leaderboard-site-login-${s.id}`}
                            title="Generate / rotate this site's login"
                          >
                            <KeyRound size={11} /> Site login
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => goToSite(s)}
                          className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded hover:bg-[var(--theme-hover-bg)]"
                          style={{ color: 'var(--color-brand-blue)' }}
                          data-testid={`leaderboard-go-${s.id}`}
                        >
                          Open <ArrowRight size={11} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {sites.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--theme-text-muted)' }}>No sites yet.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Iter 216h114 — Site Login generator modal (MOD HQ only) */}
      {isModHQ && siteLoginTarget && (
        <SiteLoginModal
          site={siteLoginTarget}
          API={API}
          onClose={() => setSiteLoginTarget(null)}
        />
      )}
    </div>
  );
};

export default AllSitesOverview;


/* ─────────── Iter 216h114 — MOD HQ Site Login provisioning ─────────── */
function SiteLoginModal({ site, API, onClose }) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : '';
  const headers = { Authorization: `Bearer ${token}` };
  const [step, setStep] = useState('confirm');
  const [notifyEmail, setNotifyEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  const generate = async () => {
    setSubmitting(true);
    try {
      const r = await axios.post(
        `${API}/mod/pro/sites/${site.id}/provision-credentials`,
        { notify_email: notifyEmail.trim() || null, rotate_if_exists: true },
        { headers },
      );
      setResult(r.data);
      setStep('result');
      if (r.data?.notified_email) notify.success(`Credentials emailed to ${r.data.notified_email}`);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not generate site login');
    } finally {
      setSubmitting(false);
    }
  };

  const copyCreds = async () => {
    if (!result) return;
    const text = `Site: ${result.site_name}\nUsername: ${result.username}\nSite code: ${result.password}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    } catch { /* ignore */ }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" data-testid="mod-site-login-modal">
      <div className="w-full max-w-md rounded-2xl border overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <header className="px-5 py-4 border-b flex items-start justify-between gap-3" style={{ borderColor: 'var(--theme-border-soft)' }}>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--color-brand-cyan-hover)' }}>
              Pulse Fitness · MOD Site Login
            </div>
            <h3 className="text-base font-extrabold tracking-tight mt-1" style={{ color: 'var(--theme-text)' }} data-testid="mod-site-login-title">
              {site.name}
            </h3>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1.5 rounded-full hover:bg-[var(--theme-hover-bg)]" data-testid="mod-site-login-close">
            <X size={16} style={{ color: 'var(--theme-text-muted)' }} />
          </button>
        </header>

        <div className="p-5 space-y-4">
          {step === 'confirm' && (
            <>
              <p className="text-sm" style={{ color: 'var(--theme-text)' }}>
                Generate (or rotate) the shared site login for this MOD site.
                The new password is shown once — copy it now and share securely
                with the on-site PTI.
              </p>
              <div className="space-y-1.5">
                <label className="block text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>
                  Email credentials to (optional)
                </label>
                <div className="flex items-center gap-2">
                  <Mail size={14} className="shrink-0" style={{ color: 'var(--theme-text-muted)' }} />
                  <input
                    type="email"
                    placeholder="ops.lead@army.mod.local"
                    value={notifyEmail}
                    onChange={(e) => setNotifyEmail(e.target.value)}
                    className="flex-1 rounded-md px-3 py-2 text-sm focus:outline-none"
                    style={{ background: 'var(--theme-surface-2)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}
                    data-testid="mod-site-login-notify-email"
                  />
                </div>
                <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
                  Leave blank to view + copy from this dialog only.
                </p>
              </div>
              <div className="flex items-center justify-end gap-2 pt-1">
                <button type="button" onClick={onClose} className="px-3 py-2 text-xs font-bold rounded-md hover:bg-[var(--theme-hover-bg)]" style={{ color: 'var(--theme-text-muted)' }} data-testid="mod-site-login-cancel">
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={generate}
                  className="inline-flex items-center gap-2 px-3 py-2 text-xs font-extrabold uppercase tracking-wider rounded-md text-white disabled:opacity-50"
                  style={{ background: 'var(--color-brand-cyan-hover)' }}
                  data-testid="mod-site-login-generate"
                >
                  {submitting ? <Loader2 size={13} className="animate-spin" /> : <KeyRound size={13} />}
                  Generate
                </button>
              </div>
            </>
          )}

          {step === 'result' && result && (
            <>
              <div className="rounded-lg border p-3 text-xs" style={{ borderColor: 'rgba(245,158,11,0.35)', background: 'rgba(245,158,11,0.10)', color: 'var(--theme-text)' }} data-testid="mod-site-login-once-warning">
                {result.note || 'This password is shown once — copy it now.'}
              </div>
              <div className="space-y-2">
                <div className="rounded-md p-3" style={{ background: 'var(--theme-surface-2)', border: '1px solid var(--theme-border)' }}>
                  <div className="text-[10px] uppercase tracking-wider font-bold" style={{ color: 'var(--theme-text-muted)' }}>Username</div>
                  <code className="block mt-1 text-sm font-mono" style={{ color: 'var(--theme-text)' }} data-testid="mod-site-login-username">{result.username}</code>
                </div>
                <div className="rounded-md p-3" style={{ background: '#0A0B10', border: '1px solid var(--color-brand-cyan-hover)' }}>
                  <div className="text-[10px] uppercase tracking-wider font-bold" style={{ color: 'var(--color-brand-cyan-hover)' }}>Site code</div>
                  <code className="block mt-1 text-sm font-mono break-all" style={{ color: '#fff' }} data-testid="mod-site-login-password">{result.password}</code>
                </div>
              </div>
              <div className="flex items-center justify-between gap-2 pt-1">
                <button
                  type="button"
                  onClick={copyCreds}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-md border hover:bg-[var(--theme-hover-bg)]"
                  style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                  data-testid="mod-site-login-copy"
                >
                  {copied ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
                  {copied ? 'Copied' : 'Copy both'}
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3 py-2 text-xs font-extrabold uppercase tracking-wider rounded-md text-white"
                  style={{ background: 'var(--color-brand-cyan-hover)' }}
                  data-testid="mod-site-login-done"
                >
                  Done
                </button>
              </div>
              {result.rotated ? (
                <p className="text-[11px] pt-1" style={{ color: 'var(--theme-text-muted)' }}>Previous code has been invalidated immediately.</p>
              ) : (
                <p className="text-[11px] pt-1" style={{ color: 'var(--theme-text-muted)' }}>New site account created — ready to use straight away.</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
