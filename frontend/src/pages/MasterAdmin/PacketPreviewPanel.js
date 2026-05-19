/* PreviewPanel — pre-provision readiness check + validation report. */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { XCircle, AlertTriangle, Users, MapPin,
  Wrench, Truck, FileText, Building2, Mail, Shield,
  Loader2, Sparkles,
} from 'lucide-react';

export default function PreviewPanel({ API, headers, packetId, status, onReadyChange }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/onboarding-packets/${packetId}/preview`, { headers });
      setData(res.data);
      if (onReadyChange) onReadyChange(res.data?.ready !== false);
    } catch { /* panel hides on error */ }
    finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API, packetId]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-4 text-zinc-400 text-sm">
        <Loader2 size={14} className="animate-spin mr-2" /> Generating preview…
      </div>
    );
  }
  if (!data) return null;
  if (data.already_provisioned) return null;

  const { ready, errors = [], warnings = [], plan = {}, conflicts = [] } = data;

  return (
    <div className="space-y-3" data-testid="packet-preview-panel">
      {/* Status banner */}
      <Card className={`p-3 border-2 ${ready ? 'bg-emerald-50 border-emerald-300' : 'bg-red-50 border-red-300'}`}
        data-testid="preview-status-banner">
        <div className="flex items-center gap-2">
          {ready ? (
            <>
              <Sparkles size={18} className="text-emerald-600" />
              <div>
                <p className="font-semibold text-emerald-900">Ready to provision</p>
                <p className="text-xs text-emerald-700">All required fields complete. {warnings.length > 0 && `${warnings.length} advisory note${warnings.length === 1 ? '' : 's'} below.`}</p>
              </div>
            </>
          ) : (
            <>
              <XCircle size={18} className="text-red-600" />
              <div>
                <p className="font-semibold text-red-900">Cannot provision yet</p>
                <p className="text-xs text-red-700">{errors.length} issue{errors.length === 1 ? '' : 's'} must be fixed first.</p>
              </div>
            </>
          )}
        </div>
      </Card>

      {/* Errors */}
      {errors.length > 0 && (
        <Card className="p-5 border-red-200" data-testid="preview-errors">
          <div className="flex items-center gap-2 mb-2">
            <XCircle size={14} className="text-red-600" />
            <h5 className="text-xs font-semibold uppercase tracking-wider text-red-700">Must fix ({errors.length})</h5>
          </div>
          <ul className="text-sm text-zinc-800 space-y-1 ml-5 list-disc">
            {errors.map((e, i) => <li key={i} data-testid={`preview-error-${i}`}>{e}</li>)}
          </ul>
        </Card>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <Card className="p-5 border-amber-200 bg-amber-50/40" data-testid="preview-warnings">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={14} className="text-amber-600" />
            <h5 className="text-xs font-semibold uppercase tracking-wider text-amber-700">Advisory ({warnings.length})</h5>
          </div>
          <ul className="text-sm text-zinc-700 space-y-1 ml-5 list-disc">
            {warnings.map((w, i) => <li key={i} data-testid={`preview-warning-${i}`}>{w.message}</li>)}
          </ul>
        </Card>
      )}

      {/* Provision plan */}
      <Card className="p-5 border-zinc-200" data-testid="preview-plan">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles size={14} className="text-blue-600" />
          <h5 className="text-xs font-semibold uppercase tracking-wider text-zinc-700">What will be created</h5>
        </div>

        {/* Org line */}
        <div className="text-sm text-zinc-800 mb-3 pb-3 border-b border-zinc-100">
          <div className="flex items-start gap-2">
            <Building2 size={14} className="text-blue-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-semibold">{plan.organization?.name}</p>
              <p className="text-xs text-zinc-500">
                {plan.organization?.postcode} · {plan.organization?.primary_contact || 'no primary email'}
              </p>
              <div className="flex items-center gap-2 mt-1">
                <Badge className="bg-blue-100 text-blue-700 capitalize text-[10px]">{plan.organization?.tier}</Badge>
                {plan.organization?.is_trial && (
                  <Badge className="bg-purple-100 text-purple-700 text-[10px]">
                    Trial ({plan.organization?.trial_duration_days}d)
                  </Badge>
                )}
                <Badge className="bg-violet-100 text-violet-700 text-[10px]">
                  CRM: {plan.crm_action === 'link' ? 'linked' : 'auto-create'}
                </Badge>
              </div>
            </div>
          </div>
        </div>

        {/* Count tiles */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2" data-testid="preview-counts">
          <CountTile icon={MapPin} label="Sites" value={plan.counts?.sites} testid="preview-count-sites" />
          <CountTile icon={Users} label="Staff" value={plan.counts?.staff} testid="preview-count-staff" />
          <CountTile icon={Wrench} label="Equipment" value={plan.counts?.equipment} testid="preview-count-equipment" />
          <CountTile icon={Truck} label="Suppliers" value={plan.counts?.suppliers} testid="preview-count-suppliers" />
          <CountTile icon={FileText} label="Contracts" value={plan.counts?.contracts} testid="preview-count-contracts" />
        </div>

        {/* Role breakdown */}
        {plan.role_breakdown && Object.keys(plan.role_breakdown).length > 0 && (
          <div className="mt-3 pt-3 border-t border-zinc-100">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">Staff roles</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(plan.role_breakdown).map(([role, n]) => (
                <span key={role} className="text-xs px-2 py-0.5 bg-zinc-100 text-zinc-700 rounded-md capitalize" data-testid={`role-${role}`}>
                  {n} × {role}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Per-site equipment breakdown */}
        {(plan.sites_breakdown?.length || 0) > 0 && (plan.counts?.equipment || 0) > 0 && (
          <div className="mt-3 pt-3 border-t border-zinc-100">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">Equipment per site</p>
            <ul className="text-xs text-zinc-700 space-y-0.5">
              {plan.sites_breakdown.map((s, i) => (
                <li key={i} className="flex justify-between">
                  <span>{s.name}{s.postcode ? ` · ${s.postcode}` : ''}</span>
                  <span className="tabular-nums font-medium">{s.equipment_count}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Magic-link email list */}
        {(plan.will_send_magic_links_to?.length || 0) > 0 && (
          <div className="mt-3 pt-3 border-t border-zinc-100 text-xs text-zinc-600">
            <Mail size={11} className="inline mr-1" />
            <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">Password-setup emails to:</span>
            <span className="ml-2 text-zinc-700">
              {plan.will_send_magic_links_to.slice(0, 3).join(', ')}
              {plan.will_send_magic_links_to.length > 3 && ` +${plan.will_send_magic_links_to.length - 3} more`}
            </span>
          </div>
        )}

        {/* Conflict hint */}
        {conflicts?.length > 0 && (
          <div className="mt-3 pt-3 border-t border-zinc-100 text-xs text-amber-700 flex items-start gap-1.5" data-testid="preview-conflicts">
            <Shield size={11} className="flex-shrink-0 mt-0.5" />
            <span>{conflicts.length} email{conflicts.length === 1 ? '' : 's'} already in system — these users will be skipped.</span>
          </div>
        )}
      </Card>
    </div>
  );
}

function CountTile({ icon: Icon, label, value = 0, testid }) {
  return (
    <div className="border border-zinc-200 rounded-md p-2 bg-zinc-50 text-center" data-testid={testid}>
      <Icon size={14} className="text-zinc-400 mx-auto mb-1" />
      <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">{label}</p>
      <p className="text-xl font-bold text-zinc-900 tabular-nums">{value}</p>
    </div>
  );
}
