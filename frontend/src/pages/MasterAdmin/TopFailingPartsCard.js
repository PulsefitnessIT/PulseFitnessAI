import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, TrendingUp, TrendingDown, Sparkles, Wrench } from 'lucide-react';

/**
 * Reusable Master-Admin card surfacing the most frequently logged fault codes
 * across the entire customer base. Powered by /api/master-admin/analytics/faults
 * which returns `by_fault_code` (with MoM trend deltas), `by_fault_category`,
 * and `coded_fault_count`.
 *
 * Variants control DENSITY only — theming is always light (Master Admin console):
 *   - 'overview' (default): compact top-5 list + actionable Insight row
 *   - 'detail': top-10 list + category-totals badge row
 *
 * Reuses already-loaded data via optional `data` prop to avoid duplicate requests.
 */

const CATEGORY_BADGE = {
  mechanical: 'bg-red-100 text-red-700',
  electrical: 'bg-amber-100 text-amber-700',
  hydraulic: 'bg-sky-100 text-sky-700',
  structural: 'bg-orange-100 text-orange-700',
  weight_stack: 'bg-indigo-100 text-indigo-700',
  safety: 'bg-rose-100 text-rose-700',
  software: 'bg-violet-100 text-violet-700',
  wear: 'bg-emerald-100 text-emerald-700',
  other: 'bg-zinc-100 text-zinc-600',
};

/** Month-on-month trend pill. Hidden when trend is 'flat' or missing. */
const TrendBadge = ({ trend, deltaPct, testid }) => {
  if (!trend || trend === 'flat') return null;
  const pillConfig = {
    up:   { Icon: TrendingUp,   label: `+${deltaPct}%`, cls: 'bg-red-50 text-red-700' },
    down: { Icon: TrendingDown, label: `${deltaPct}%`,  cls: 'bg-emerald-50 text-emerald-700' },
    new:  { Icon: Sparkles,     label: 'new',           cls: 'bg-sky-50 text-sky-700' },
  }[trend];
  if (!pillConfig) return null;
  const { Icon, label, cls } = pillConfig;
  return (
    <span
      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold ${cls}`}
      data-testid={testid}
      title={`Month-on-month: ${label}`}
    >
      <Icon size={10} />
      {label}
    </span>
  );
};

const TopFailingPartsCard = ({ API, variant = 'overview', data: providedData = null }) => {
  const [data, setData] = useState(providedData);
  const [loading, setLoading] = useState(!providedData);

  useEffect(() => {
    if (providedData) { setData(providedData); return; }
    const load = async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await axios.get(`${API}/master-admin/analytics/faults`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setData(res.data);
      } catch {
        setData(null);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [API, providedData]);

  const topLimit = variant === 'detail' ? 10 : 5;
  const codes = (data?.by_fault_code || []).slice(0, topLimit);
  const categories = data?.by_fault_category || [];
  const codedCount = data?.coded_fault_count || 0;
  const totalFaults = data?.total_faults || 0;
  const codedPct = totalFaults > 0 ? Math.round((codedCount / totalFaults) * 100) : 0;
  const maxCount = Math.max(1, ...codes.map(c => c.count));

  if (loading) {
    return (
      <Card className="bg-white border-zinc-200 shadow-sm p-5" data-testid="top-failing-parts-loading">
        <div className="flex items-center justify-center h-32">
          <span className="text-xs text-zinc-400">Loading fault-code analytics…</span>
        </div>
      </Card>
    );
  }

  if (!data || codes.length === 0) {
    return (
      <Card className="bg-white border-zinc-200 shadow-sm p-5" data-testid="top-failing-parts-empty">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-8 h-8 rounded-lg bg-red-50 flex items-center justify-center">
            <Wrench size={16} className="text-red-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-zinc-900">Top Failing Parts</h3>
            <p className="text-[11px] text-zinc-400">
              No fault codes captured yet. As users log faults, the AI will auto-tag them for trend analysis.
            </p>
          </div>
        </div>
      </Card>
    );
  }

  const topCode = codes[0];
  const insightTrend = topCode.trend === 'up' && topCode.delta_pct !== null
    ? ` — up ${topCode.delta_pct}% month-on-month`
    : topCode.trend === 'new'
      ? ' — a new trend this month'
      : '';

  return (
    <Card className="bg-white border-zinc-200 shadow-sm p-5" data-testid="top-failing-parts-card">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-red-50 flex items-center justify-center">
            <Wrench size={16} className="text-red-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-zinc-900">Top Failing Parts</h3>
            <p className="text-[11px] text-zinc-400">
              {codedCount} of {totalFaults} faults tagged ({codedPct}% coverage)
            </p>
          </div>
        </div>
        <Badge className="bg-red-100 text-red-700 border-transparent">
          <TrendingUp size={10} className="mr-1" /> Trend insights
        </Badge>
      </div>

      {/* Ranked fault-code bars */}
      <div className="space-y-2.5" data-testid="top-failing-parts-list">
        {codes.map((c, idx) => {
          const pct = Math.round((c.count / maxCount) * 100);
          const categoryBadgeCls = CATEGORY_BADGE[c.category] || CATEGORY_BADGE.other;
          return (
            <div key={c.code} className="space-y-1" data-testid={`failing-part-${c.code}`}>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="inline-flex items-center justify-center w-5 h-5 rounded text-[10px] font-bold bg-red-50 text-red-800">
                    {idx + 1}
                  </span>
                  <span className="text-xs font-mono font-semibold text-red-700">{c.code}</span>
                  <span className="text-xs text-zinc-900 truncate">{c.label}</span>
                  {c.category && (
                    <Badge className={`${categoryBadgeCls} text-[9px] border-transparent flex-shrink-0`}>
                      {c.category.replace('_', ' ')}
                    </Badge>
                  )}
                  <TrendBadge trend={c.trend} deltaPct={c.delta_pct} testid={`trend-badge-${c.code}`} />
                </div>
                <span className="text-xs font-medium text-zinc-900 flex-shrink-0">{c.count}</span>
              </div>
              <div className="h-1.5 rounded-full overflow-hidden bg-zinc-100">
                <div
                  className="h-full rounded-full transition-all bg-red-600"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Category totals — detail variant only */}
      {variant === 'detail' && categories.length > 0 && (
        <div className="mt-5 pt-4 border-t border-zinc-100" data-testid="fault-category-totals">
          <p className="text-[10px] uppercase tracking-wider mb-2 text-zinc-400">By category</p>
          <div className="flex flex-wrap gap-1.5">
            {categories.map(cat => (
              <Badge key={cat.category} className="bg-zinc-50 text-xs border border-zinc-200">
                <span className="mr-1 text-zinc-500">{cat.category.replace('_', ' ')}</span>
                <span className="font-semibold text-zinc-900">{cat.count}</span>
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Insight — overview variant only */}
      {variant === 'overview' && (
        <div className="mt-4 pt-3 border-t border-zinc-100 flex items-start gap-2" data-testid="top-failing-parts-insight">
          <AlertTriangle size={13} className="text-amber-500 flex-shrink-0 mt-0.5" />
          <p className="text-[11px] text-zinc-500 leading-snug">
            <span className="font-medium text-zinc-700">Insight:</span>{' '}
            <span className="font-mono text-red-700">{topCode.code}</span>{' '}
            ({topCode.label}) is the most common fault across your fleet ({topCode.count} reports{insightTrend}).
            Consider negotiating bulk spares or preventive-maintenance contracts.
          </p>
        </div>
      )}
    </Card>
  );
};

export default TopFailingPartsCard;
