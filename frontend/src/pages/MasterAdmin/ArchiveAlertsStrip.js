/* Archive Alerts Tile — Master Admin Overview */
import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/App';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Archive, AlertTriangle, Clock, ArrowRight } from 'lucide-react';

export default function ArchiveAlertsStrip({ onOpen }) {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/master-admin/archive`, { headers: { Authorization: `Bearer ${token}` } });
      setData(res.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [API]);

  useEffect(() => { load(); }, [load]);

  if (loading || !data || data.count === 0) return null;

  const orgs = data.organizations || [];
  const critical = orgs.filter(o => (o.days_until_deletion ?? 999) <= 7).length;
  const warning = orgs.filter(o => {
    const d = o.days_until_deletion ?? 999;
    return d > 7 && d <= 30;
  }).length;
  const hasUrgent = critical > 0 || warning > 0;

  return (
    <Card
      className={`p-4 border ${hasUrgent ? 'border-red-200 bg-gradient-to-br from-red-50 to-white' : 'border-zinc-200 bg-white'}`}
      data-testid="archive-alerts-strip"
    >
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${hasUrgent ? 'bg-red-100' : 'bg-zinc-100'}`}>
            <Archive size={16} className={hasUrgent ? 'text-red-600' : 'text-zinc-600'} />
          </div>
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wider text-zinc-500 font-semibold">Archive (GDPR Retention)</p>
            <p className="text-sm text-zinc-700">
              <strong>{data.count}</strong> archived {data.count === 1 ? 'org' : 'orgs'}
              {critical > 0 && (
                <>
                  {' · '}<span className="text-red-700 font-semibold" data-testid="archive-critical-count">
                    <AlertTriangle size={11} className="inline -mt-0.5 mr-0.5" />
                    {critical} deleting in ≤7 days
                  </span>
                </>
              )}
              {warning > 0 && (
                <>
                  {' · '}<span className="text-amber-700" data-testid="archive-warning-count">
                    <Clock size={11} className="inline -mt-0.5 mr-0.5" />
                    {warning} within 30 days
                  </span>
                </>
              )}
            </p>
          </div>
        </div>
        <Button
          size="sm"
          variant={hasUrgent ? 'default' : 'outline'}
          onClick={onOpen}
          className={hasUrgent ? 'bg-red-600 hover:bg-red-700 text-white' : 'border-zinc-300 text-zinc-700'}
          data-testid="archive-alerts-open-btn"
        >
          Review archive <ArrowRight size={13} className="ml-1" />
        </Button>
      </div>
    </Card>
  );
}
