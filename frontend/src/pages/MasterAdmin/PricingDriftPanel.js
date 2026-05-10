/**
 * PricingDriftPanel — Master Admin pricing-drift audit (Iter 216g · Plan D).
 *
 * Read-only. Calls /api/master-admin/pricing/audit-drift and surfaces any
 * pricing inconsistency between the master pricing engine, the legacy
 * marketing_plans collection, and the public PricingPage homepage.
 */
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ShieldCheck, AlertTriangle, RefreshCw, ExternalLink } from 'lucide-react';
import { notify } from '@/components/notifications';

const PricingDriftPanel = () => {
  const { API } = useAuth();
  const [data, setData] = useState({ items: [], compared_surfaces: [] });
  const [loading, setLoading] = useState(true);

  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/pricing/audit-drift`, { headers: headers() });
      setData(r.data || { items: [] });
    } catch (e) {
      notify.error('Could not run drift audit', e.response?.data?.detail);
    }
    setLoading(false);
  }, [API]);
  useEffect(() => { load(); }, [load]);

  const driftCount = data.items?.length || 0;
  const allClean = !loading && driftCount === 0;

  return (
    <Card className="p-4 border-zinc-200" data-testid="pricing-drift-panel">
      <div className="flex items-start justify-between mb-3 gap-3 flex-wrap">
        <div>
          <h4 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
            {allClean ? <ShieldCheck size={15} className="text-emerald-600" /> : <AlertTriangle size={15} className="text-amber-600" />}
            Pricing drift audit
          </h4>
          <p className="text-[11px] text-zinc-500 mt-0.5">
            Compares the engine ({data.compared_surfaces?.[0] || 'pricing_plans'}) against legacy and homepage surfaces.
            Catches stale numbers before they hit a customer screen.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={load} disabled={loading} data-testid="drift-refresh">
          <RefreshCw size={12} className={`mr-1 ${loading ? 'animate-spin' : ''}`} /> Re-run
        </Button>
      </div>

      <div className="flex items-center gap-2 mb-3 flex-wrap" data-testid="drift-surfaces">
        {(data.compared_surfaces || []).map((s) => (
          <Badge key={s} className="bg-zinc-100 text-zinc-700 border border-zinc-200 text-[10px] font-mono">{s}</Badge>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-zinc-400 py-4">Auditing…</p>
      ) : allClean ? (
        <div className="p-4 rounded-lg bg-emerald-50 border border-emerald-200" data-testid="drift-clean">
          <p className="text-sm font-semibold text-emerald-800 flex items-center gap-2">
            <ShieldCheck size={14} /> Zero drift detected.
          </p>
          <p className="text-[11px] text-emerald-700 mt-1">All pricing surfaces are aligned with the master engine.</p>
        </div>
      ) : (
        <div className="space-y-2" data-testid="drift-items">
          <p className="text-xs text-zinc-600 mb-2">
            <span className="font-semibold text-amber-700">{driftCount}</span> drift item{driftCount === 1 ? '' : 's'} found.
          </p>
          {data.items.map((it, idx) => (
            <div key={idx} className={`p-3 rounded-lg border ${it.severity === 'warning' ? 'bg-amber-50 border-amber-200' : 'bg-blue-50 border-blue-200'}`} data-testid={`drift-item-${idx}`}>
              <div className="flex items-start gap-3">
                <AlertTriangle size={14} className={it.severity === 'warning' ? 'text-amber-600' : 'text-blue-600'} />
                <div className="flex-1">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-zinc-900">{it.field}</p>
                    <Badge className={`text-[10px] uppercase ${it.severity === 'warning' ? 'bg-amber-200 text-amber-800' : 'bg-blue-200 text-blue-800'}`}>
                      {it.severity}
                    </Badge>
                  </div>
                  <p className="text-[11px] text-zinc-500 mt-0.5">on <span className="font-mono">{it.surface}</span></p>
                  <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                    <div className="p-2 rounded bg-white border border-zinc-100">
                      <p className="text-[10px] uppercase text-zinc-400 font-semibold">Engine</p>
                      <p className="font-mono text-zinc-700">{it.engine_value}</p>
                    </div>
                    <div className="p-2 rounded bg-white border border-zinc-100">
                      <p className="text-[10px] uppercase text-zinc-400 font-semibold">Drift surface</p>
                      <p className="font-mono text-amber-700">{it.drift_value}</p>
                    </div>
                  </div>
                  {it.fix && (
                    <p className="mt-2 text-[11px] text-zinc-600 flex items-start gap-1.5">
                      <ExternalLink size={10} className="mt-0.5" /> <span>{it.fix}</span>
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};

export default PricingDriftPanel;
