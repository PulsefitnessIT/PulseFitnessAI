import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { AlertTriangle, Activity } from 'lucide-react';

/**
 * UsageMeterCard (iter 215c0)
 * Shows current-period usage for the org with progress bars per metric.
 * Drop-in for dashboards & account panels.
 */
const LEVEL_COLOUR = {
  ok: 'bg-emerald-500',
  warning: 'bg-amber-500',
  critical: 'bg-orange-500',
  exceeded: 'bg-red-600',
};

const METRIC_LABEL = {
  members: 'Members',
  ai_tokens: 'AI tokens',
  sms: 'SMS sent',
  api_calls: 'API calls',
  emails: 'Emails sent',
};

const UsageMeterCard = ({ compact = false }) => {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    const run = async () => {
      const token = localStorage.getItem('token');
      try {
        const res = await axios.get(`${API}/usage/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!cancel) setData(res.data);
      } catch {
        if (!cancel) setData(null);
      } finally {
        if (!cancel) setLoading(false);
      }
    };
    run();
    return () => { cancel = true; };
  }, [API]);

  if (loading) {
    return (
      <div data-testid="usage-meter-loading" className="rounded-2xl bg-[var(--theme-surface)] border border-[var(--theme-border)] p-5 animate-pulse">
        <div className="h-4 w-32 bg-slate-200 dark:bg-slate-700 rounded mb-4" />
        <div className="space-y-3">
          {[0,1,2,3].map(i => <div key={i} className="h-2 bg-slate-200 dark:bg-slate-700 rounded" />)}
        </div>
      </div>
    );
  }
  if (!data) return null;

  const period = data.period
    ? `${data.period.slice(0,4)}-${data.period.slice(4,6)}`
    : '';

  return (
    <div data-testid="usage-meter-card" className="rounded-2xl bg-[var(--theme-surface)] border border-[var(--theme-border)] p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-[var(--color-text-muted)]" />
          <h3 className="text-sm font-semibold text-[var(--theme-text)]">Usage this month</h3>
        </div>
        <span className="text-xs text-[var(--color-text-muted)]">{period}</span>
      </div>

      {data.has_warning && (
        <div data-testid="usage-warning-banner" className="flex items-start gap-2 mb-4 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800">
          <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-amber-900 dark:text-amber-200">
            You're approaching limits on one or more metrics. Consider upgrading your plan.
          </p>
        </div>
      )}

      <ul className="space-y-3">
        {data.metrics.map(m => {
          if (compact && m.level === 'ok' && m.used === 0) return null;
          const pct = Math.min(100, m.pct || 0);
          return (
            <li key={m.metric} data-testid={`usage-row-${m.metric}`}>
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-[var(--theme-text)] font-medium">{METRIC_LABEL[m.metric] || m.metric}</span>
                <span className="text-[var(--color-text-muted)] tabular-nums">
                  {m.used.toLocaleString()} / {m.limit.toLocaleString()}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                <div
                  data-testid={`usage-bar-${m.metric}`}
                  className={`h-full transition-all ${LEVEL_COLOUR[m.level] || 'bg-slate-400'}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default UsageMeterCard;
