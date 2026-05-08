import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import {
  BarChart3, TrendingUp, Clock, PoundSterling, AlertTriangle,
  Wrench, Package, Activity
} from 'lucide-react';

const OperationalReportsTab = () => {
  const { t } = useTranslation();
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('30d');

  useEffect(() => {
    loadData();
  }, [period]);

  const loadData = async () => {
    setLoading(true);
    const token = localStorage.getItem('token');
    try {
      const res = await axios.get(`${API}/reports/operational?period=${period}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setData(res.data);
    } catch (err) {
      console.error('Failed to load operational reports:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="text-[var(--color-text-muted)] text-center py-16">Loading operational data...</div>;
  if (!data) return <div className="text-[var(--color-text-muted)] text-center py-16">No data available</div>;

  const maxEquipCount = Math.max(...Object.values(data.by_equipment || {}), 1);
  const maxSupplierCount = Math.max(...Object.values(data.by_supplier || {}), 1);

  return (
    <div className="space-y-6" data-testid="operational-reports-tab">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-[color:var(--theme-text)]">Operational Reports</h2>
          <p className="text-[var(--color-text-muted)]">Analytics on faults, resolution times, and purchase orders</p>
        </div>
        <div className="flex gap-2">
          {['7d', '30d', '90d', '365d', 'all'].map(p => (
            <Button
              key={p} size="sm"
              variant={period === p ? 'default' : 'outline'}
              className={period === p ? 'bg-[var(--color-brand-blue)] text-white' : 'border-[color:var(--theme-border)] text-[color:var(--theme-text)]'}
              onClick={() => setPeriod(p)}
              data-testid={`period-${p}`}
            >
              {p === '7d' ? '7 Days' : p === '30d' ? '30 Days' : p === '90d' ? '90 Days' : p === '365d' ? '1 Year' : 'All Time'}
            </Button>
          ))}
        </div>
      </div>

      {/* Top Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card className="bg-[var(--theme-surface)] border-[color:var(--theme-border)] p-5" data-testid="op-total-faults">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle size={16} className="text-[var(--color-brand-blue)]" />
            <span className="text-[var(--color-text-muted)] text-xs">Total Faults</span>
          </div>
          <p className="text-2xl font-bold text-[color:var(--theme-text)]">{data.total_faults}</p>
        </Card>
        <Card className="bg-[var(--theme-surface)] border-[color:var(--theme-border)] p-5" data-testid="op-open-faults">
          <div className="flex items-center gap-2 mb-1">
            <Activity size={16} className="text-red-400" />
            <span className="text-[var(--color-text-muted)] text-xs">Open</span>
          </div>
          <p className="text-2xl font-bold text-red-500">{data.open_faults}</p>
        </Card>
        <Card className="bg-[var(--theme-surface)] border-[color:var(--theme-border)] p-5" data-testid="op-resolved-faults">
          <div className="flex items-center gap-2 mb-1">
            <Wrench size={16} className="text-green-400" />
            <span className="text-[var(--color-text-muted)] text-xs">Resolved</span>
          </div>
          <p className="text-2xl font-bold text-green-600">{data.resolved_faults}</p>
        </Card>
        <Card className="bg-[var(--theme-surface)] border-[color:var(--theme-border)] p-5" data-testid="op-avg-resolution">
          <div className="flex items-center gap-2 mb-1">
            <Clock size={16} className="text-yellow-400" />
            <span className="text-[var(--color-text-muted)] text-xs">Avg Resolution</span>
          </div>
          <p className="text-2xl font-bold text-yellow-400">{data.avg_resolution_hours}h</p>
        </Card>
        <Card className="bg-[var(--theme-surface)] border-[color:var(--theme-border)] p-5" data-testid="op-po-value">
          <div className="flex items-center gap-2 mb-1">
            <PoundSterling size={16} className="text-emerald-400" />
            <span className="text-[var(--color-text-muted)] text-xs">PO Value</span>
          </div>
          <p className="text-2xl font-bold text-emerald-400">{"\u00A3"}{data.total_po_value.toLocaleString()}</p>
          <p className="text-[var(--color-text-muted)] text-xs">{data.po_count} orders</p>
        </Card>
      </div>

      {/* Severity Breakdown */}
      <Card className="bg-[var(--theme-surface)] border-[color:var(--theme-border)] p-6" data-testid="op-severity-card">
        <h3 className="text-lg font-semibold text-[color:var(--theme-text)] mb-4">Faults by Severity</h3>
        <div className="grid grid-cols-3 gap-4">
          {Object.entries(data.severity_counts || {}).map(([sev, count]) => {
            const colorMap = { critical: { bg: 'bg-red-500', text: 'text-red-400', light: 'bg-red-500/20' }, medium: { bg: 'bg-yellow-500', text: 'text-yellow-400', light: 'bg-yellow-500/20' }, low: { bg: 'bg-green-500', text: 'text-green-400', light: 'bg-green-500/20' } };
            const c = colorMap[sev] || colorMap.medium;
            const pct = data.total_faults > 0 ? Math.round((count / data.total_faults) * 100) : 0;
            return (
              <div key={sev} className={`p-4 ${c.light} rounded-lg text-center`}>
                <p className={`text-3xl font-bold ${c.text}`}>{count}</p>
                <p className="text-[color:var(--theme-text)] text-sm capitalize mt-1">{sev}</p>
                <p className="text-[var(--color-text-muted)] text-xs">{pct}% of total</p>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* By Equipment Type */}
        <Card className="bg-[var(--theme-surface)] border-[color:var(--theme-border)] p-6" data-testid="op-by-equipment">
          <h3 className="text-lg font-semibold text-[color:var(--theme-text)] mb-4 flex items-center gap-2">
            <BarChart3 size={18} className="text-[var(--color-brand-blue)]" /> Faults by Equipment
          </h3>
          {Object.keys(data.by_equipment || {}).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(data.by_equipment).map(([type, count]) => (
                <div key={type}>
                  <div className="flex justify-between mb-1">
                    <span className="text-[color:var(--theme-text)] text-sm">{type}</span>
                    <span className="text-[var(--color-text-muted)] text-sm font-medium">{count}</span>
                  </div>
                  <div className="w-full bg-[var(--color-ink-alt)] rounded-full h-2.5">
                    <div className="bg-[var(--color-brand-blue)] h-2.5 rounded-full transition-all" style={{ width: `${(count / maxEquipCount) * 100}%` }}></div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[var(--color-text-muted)] text-center py-6">No equipment fault data yet</p>
          )}
        </Card>

        {/* By Supplier */}
        <Card className="bg-[var(--theme-surface)] border-[color:var(--theme-border)] p-6" data-testid="op-by-supplier">
          <h3 className="text-lg font-semibold text-[color:var(--theme-text)] mb-4 flex items-center gap-2">
            <Package size={18} className="text-[var(--color-brand-blue)]" /> Faults by Supplier
          </h3>
          {Object.keys(data.by_supplier || {}).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(data.by_supplier).map(([sup, count]) => (
                <div key={sup}>
                  <div className="flex justify-between mb-1">
                    <span className="text-[color:var(--theme-text)] text-sm">{sup}</span>
                    <span className="text-[var(--color-text-muted)] text-sm font-medium">{count}</span>
                  </div>
                  <div className="w-full bg-[var(--color-ink-alt)] rounded-full h-2.5">
                    <div className="bg-orange-500 h-2.5 rounded-full transition-all" style={{ width: `${(count / maxSupplierCount) * 100}%` }}></div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[var(--color-text-muted)] text-center py-6">No supplier fault data yet</p>
          )}
        </Card>
      </div>

      {/* Weekly Trend */}
      {Object.keys(data.weekly_trend || {}).length > 0 && (
        <Card className="bg-[var(--theme-surface)] border-[color:var(--theme-border)] p-6" data-testid="op-weekly-trend">
          <h3 className="text-lg font-semibold text-[color:var(--theme-text)] mb-4 flex items-center gap-2">
            <TrendingUp size={18} className="text-[var(--color-brand-blue)]" /> Weekly Self-Fix Rate Trend
          </h3>
          <div className="space-y-2">
            {Object.entries(data.weekly_trend).map(([week, wData]) => {
              const rate = wData.total > 0 ? Math.round((wData.self_fix / wData.total) * 100) : 0;
              return (
                <div key={week} className="flex items-center gap-4">
                  <span className="text-[var(--color-text-muted)] text-sm w-24 flex-shrink-0">{week}</span>
                  <div className="flex-1 bg-[var(--color-ink-alt)] rounded-full h-3 relative">
                    <div className="bg-green-500 h-3 rounded-full transition-all" style={{ width: `${rate}%` }}></div>
                  </div>
                  <span className="text-[color:var(--theme-text)] text-sm w-16 text-right">{rate}% ({wData.total})</span>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Resolution Times */}
      {data.resolution_times && data.resolution_times.length > 0 && (
        <Card className="bg-[var(--theme-surface)] border-[color:var(--theme-border)] p-6" data-testid="op-resolution-times">
          <h3 className="text-lg font-semibold text-[color:var(--theme-text)] mb-4 flex items-center gap-2">
            <Clock size={18} className="text-yellow-400" /> Resolution Times
          </h3>
          <div className="space-y-2">
            {data.resolution_times.map((r, idx) => (
              <div key={idx} className="flex items-center justify-between p-3 bg-[var(--color-ink-alt)] border border-[color:var(--theme-border)] rounded-lg">
                <div>
                  <p className="text-[color:var(--theme-text)] text-sm font-medium">{r.issue}</p>
                  <Badge className={r.type === 'self_fix' ? 'bg-green-500/20 text-green-400 text-xs' : 'bg-orange-500/20 text-orange-400 text-xs'}>
                    {r.type === 'self_fix' ? 'Self-fix' : r.type === 'engineer' ? 'Engineer' : r.type}
                  </Badge>
                </div>
                <span className={`font-bold ${r.hours < 24 ? 'text-green-400' : r.hours < 72 ? 'text-yellow-400' : 'text-red-400'}`}>
                  {r.hours < 24 ? `${r.hours}h` : `${Math.round(r.hours / 24)}d`}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* PO Summary */}
      {data.po_count > 0 && (
        <Card className="bg-[var(--theme-surface)] border-[color:var(--theme-border)] p-6" data-testid="op-po-summary">
          <h3 className="text-lg font-semibold text-[color:var(--theme-text)] mb-4 flex items-center gap-2">
            <PoundSterling size={18} className="text-emerald-400" /> Purchase Order Summary
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="p-4 bg-[var(--color-ink-alt)] border border-[color:var(--theme-border)] rounded-lg text-center">
              <p className="text-2xl font-bold text-[color:var(--theme-text)]">{data.po_count}</p>
              <p className="text-[var(--color-text-muted)] text-sm">Total POs</p>
            </div>
            <div className="p-4 bg-[var(--color-ink-alt)] border border-[color:var(--theme-border)] rounded-lg text-center">
              <p className="text-2xl font-bold text-emerald-400">{"\u00A3"}{data.total_po_value.toLocaleString()}</p>
              <p className="text-[var(--color-text-muted)] text-sm">Total Value</p>
            </div>
            {Object.entries(data.po_by_status || {}).map(([st, cnt]) => (
              <div key={st} className="p-4 bg-[var(--color-ink-alt)] border border-[color:var(--theme-border)] rounded-lg text-center">
                <p className="text-2xl font-bold text-[color:var(--theme-text)]">{cnt}</p>
                <p className="text-[var(--color-text-muted)] text-sm capitalize">{st}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};

export default OperationalReportsTab;
