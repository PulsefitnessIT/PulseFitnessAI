import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { notify } from '@/components/notifications';
import {
  ShieldCheck, CheckCircle2, AlertTriangle, XCircle, Loader2,
  RefreshCw, Rocket, Building2, Server,
} from 'lucide-react';

const STATUS = {
  pass: { icon: CheckCircle2, cls: 'text-emerald-600', badge: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  warn: { icon: AlertTriangle, cls: 'text-amber-600', badge: 'bg-amber-50 text-amber-700 border-amber-200' },
  fail: { icon: XCircle, cls: 'text-red-600', badge: 'bg-red-50 text-red-700 border-red-200' },
};

function CheckRow({ check }) {
  const s = STATUS[check.status] || STATUS.warn;
  const Icon = s.icon;
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-zinc-100 last:border-0" data-testid={`sicon-readiness-check-${check.id}`}>
      <Icon size={16} className={`${s.cls} mt-0.5 shrink-0`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-zinc-900">{check.label}</span>
          <Badge className={`text-[10px] border ${s.badge}`}>{check.status.toUpperCase()}</Badge>
        </div>
        <p className="text-xs text-zinc-600 mt-0.5">{check.detail}</p>
        {check.fix && check.status !== 'pass' && (
          <p className="text-xs text-zinc-500 mt-1 flex items-start gap-1">
            <span className="font-semibold text-zinc-700">Fix:</span> {check.fix}
          </p>
        )}
      </div>
    </div>
  );
}

function ScorePill({ score }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px]">
      <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 size={12} />{score.pass}</span>
      <span className="inline-flex items-center gap-1 text-amber-700"><AlertTriangle size={12} />{score.warn}</span>
      <span className="inline-flex items-center gap-1 text-red-700"><XCircle size={12} />{score.fail}</span>
    </div>
  );
}

export default function SiconReadinessPanel() {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/master-admin/sicon/readiness`, { headers });
      setData(res.data);
    } catch (err) {
      notify.error('Failed to load Sicon readiness');
      console.error(err);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin text-zinc-400" size={20} />
      </div>
    );
  }
  if (!data) return null;

  const { summary = {}, platform_checks = [], organizations = [] } = data;
  const allReady = summary.orgs_configured > 0 && summary.orgs_ready === summary.orgs_configured;

  return (
    <div className="space-y-5" data-testid="sicon-readiness-panel">
      {/* Header + overall verdict */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-lg font-semibold text-zinc-900 flex items-center gap-2">
            <ShieldCheck size={18} className="text-violet-600" />
            Go-Live Readiness
          </h3>
          <p className="text-sm text-zinc-500 mt-0.5">
            Everything that must be in place before flipping Sicon live. Re-run any time.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={load} data-testid="sicon-readiness-refresh">
          <RefreshCw size={12} className="mr-1" /> Re-check
        </Button>
      </div>

      {/* Verdict banner */}
      {summary.orgs_configured === 0 ? (
        <Card className="p-5 border-amber-200 bg-amber-50" data-testid="sicon-readiness-verdict">
          <div className="flex items-center gap-3">
            <AlertTriangle size={20} className="text-amber-600" />
            <div>
              <p className="font-semibold text-amber-800">No organisation has Sicon configured yet</p>
              <p className="text-sm text-amber-700">Add credentials in the Configuration tab to begin the readiness check.</p>
            </div>
          </div>
        </Card>
      ) : (
        <Card className={`p-5 border ${allReady ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'}`} data-testid="sicon-readiness-verdict">
          <div className="flex items-center gap-3">
            <Rocket size={20} className={allReady ? 'text-emerald-600' : 'text-amber-600'} />
            <div>
              <p className={`font-semibold ${allReady ? 'text-emerald-800' : 'text-amber-800'}`} data-testid="sicon-readiness-verdict-text">
                {allReady
                  ? `Ready to go live — ${summary.orgs_ready}/${summary.orgs_configured} organisation(s) have no blockers.`
                  : `${summary.orgs_ready}/${summary.orgs_configured} organisation(s) ready — resolve the red items below.`}
              </p>
              <p className={`text-sm ${allReady ? 'text-emerald-700' : 'text-amber-700'}`}>
                Red = blocker · Amber = recommended before go-live · Green = good.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Platform-level checks */}
      <Card className="p-5 border-zinc-200">
        <div className="flex items-center gap-2 mb-2">
          <Server size={15} className="text-zinc-500" />
          <h4 className="text-sm font-semibold text-zinc-800">Platform</h4>
        </div>
        <div>
          {platform_checks.map((c) => <CheckRow key={c.id} check={c} />)}
        </div>
      </Card>

      {/* Per-org checks */}
      {organizations.map((org) => (
        <Card key={org.organization_id} className="border-zinc-200 overflow-hidden" data-testid={`sicon-readiness-org-${org.organization_id}`}>
          <div className={`px-5 py-3 flex items-center justify-between gap-3 border-b ${org.ready ? 'bg-emerald-50/50 border-emerald-100' : 'bg-red-50/40 border-red-100'}`}>
            <div className="flex items-center gap-2 min-w-0">
              <Building2 size={15} className="text-zinc-500 shrink-0" />
              <span className="text-sm font-semibold text-zinc-900 truncate">{org.organization_name}</span>
              {org.ready
                ? <Badge className="bg-emerald-100 text-emerald-700 border border-emerald-200 text-[10px]">READY</Badge>
                : <Badge className="bg-red-100 text-red-700 border border-red-200 text-[10px]">BLOCKED</Badge>}
            </div>
            <ScorePill score={org.score} />
          </div>
          <div className="px-5 py-2">
            {org.checks.map((c) => <CheckRow key={c.id} check={c} />)}
          </div>
        </Card>
      ))}
    </div>
  );
}
