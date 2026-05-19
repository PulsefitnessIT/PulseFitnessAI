import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Building2, Users, AlertTriangle, PoundSterling, Wrench,
  RefreshCw, ArrowUpRight, Eye
} from 'lucide-react';

const PULSE_BLUE = 'var(--color-brand-blue-dark)';

const STATUS_STYLES = {
  active: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  trial: 'bg-blue-50 text-blue-700 border-blue-200',
  suspended: 'bg-amber-50 text-amber-700 border-amber-200',
  cancelled: 'bg-red-50 text-red-700 border-red-200',
};

const PULSE_TYPE_STYLES = {
  lite: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  pulse_pro: 'bg-indigo-50 text-indigo-700 border-indigo-200',
};

const AdminPulse = ({ pulseData, onRefresh, organizations, onSelectOrg, onUpgrade, headers, API }) => {
  const [activeTab, setActiveTab] = useState('sites');

  if (!pulseData) return <div className="flex items-center justify-center h-64"><RefreshCw className="animate-spin text-zinc-400" size={24} /></div>;

  const { total_sites, lite_sites, pro_sites, total_users, total_equipment, open_faults, mrr, sites } = pulseData;

  return (
    <div className="space-y-6">
      {/* Pulse Branding Header */}
      <Card className="border-0 shadow-md p-6" style={{ background: `linear-gradient(135deg, ${PULSE_BLUE} 0%, #0052CC 100%)` }} data-testid="pulse-admin-header">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-white flex items-center justify-center">
              <Wrench size={24} className="text-white" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">Pulse Fitness Self-Service Portal</h2>
              <p className="text-blue-200 text-sm mt-0.5">White-label partner management · {total_sites} active site{total_sites !== 1 ? 's' : ''}</p>
            </div>
          </div>
          <a href="/pulse" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 bg-white hover:bg-white text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors" data-testid="pulse-view-portal">
            View Portal <ArrowUpRight size={14} />
          </a>
        </div>
      </Card>

      {/* Sub-tabs (Sites only — Spec Sheets & Equipment Images live in Image Catalogue) */}
      <div className="flex gap-1 border-b border-zinc-200" data-testid="pulse-sub-tabs">
        <button
          onClick={() => setActiveTab('sites')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${activeTab === 'sites' ? 'border-[var(--color-brand-blue-dark)] text-[var(--color-brand-blue-dark)]' : 'border-transparent text-zinc-500 hover:text-zinc-700'}`}
          data-testid="pulse-tab-sites"
        >
          <Building2 size={14} className="inline mr-1.5 -mt-0.5" /> Sites
        </button>
      </div>

      <>
      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {[
          { label: 'Total Sites', value: total_sites, icon: Building2, color: 'text-blue-600', bg: 'bg-blue-50' },
          { label: 'Pulse Users', value: total_users, icon: Users, color: 'text-violet-600', bg: 'bg-violet-50' },
          { label: 'Equipment', value: total_equipment, icon: Wrench, color: 'text-teal-600', bg: 'bg-teal-50' },
          { label: 'Open Faults', value: open_faults, icon: AlertTriangle, color: 'text-amber-600', bg: 'bg-amber-50' },
          { label: 'Pulse MRR', value: `£${mrr}`, icon: PoundSterling, color: 'text-emerald-600', bg: 'bg-emerald-50' },
        ].map(k => (
          <Card key={k.label} className="bg-white border-zinc-200 shadow-sm p-5" data-testid={`pulse-kpi-${k.label.toLowerCase().replace(/ /g, '-')}`}>
            <div className="flex items-center gap-3">
              <div className={`w-9 h-9 rounded-lg ${k.bg} flex items-center justify-center`}>
                <k.icon size={18} className={k.color} />
              </div>
              <div>
                <p className="text-xl font-semibold text-zinc-900">{k.value}</p>
                <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">{k.label}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Tier Breakdown */}
      <div className="grid grid-cols-2 gap-4">
        <Card className="bg-white border-zinc-200 shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-medium text-zinc-900">Tier Breakdown</h3>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-cyan-50 rounded-lg border border-cyan-100">
              <div className="flex items-center gap-3">
                <Badge className="bg-cyan-100 text-cyan-800 border-cyan-200">Lite</Badge>
                <span className="text-sm text-zinc-700">Basic fault logging & equipment view</span>
              </div>
              <span className="text-lg font-bold text-zinc-900">{lite_sites}</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-indigo-50 rounded-lg border border-indigo-100">
              <div className="flex items-center gap-3">
                <Badge className="bg-indigo-100 text-indigo-800 border-indigo-200">Pro</Badge>
                <span className="text-sm text-zinc-700">Full features, Pulse branded</span>
              </div>
              <span className="text-lg font-bold text-zinc-900">{pro_sites}</span>
            </div>
          </div>
        </Card>
        <Card className="bg-white border-zinc-200 shadow-sm p-5">
          <h3 className="font-medium text-zinc-900 mb-4">Revenue</h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-zinc-500">Lite Sites ({lite_sites} × £29/mo)</span>
              <span className="font-semibold text-zinc-900">£{lite_sites * 29}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-zinc-500">Pro Sites ({pro_sites} × £79/mo)</span>
              <span className="font-semibold text-zinc-900">£{pro_sites * 79}</span>
            </div>
            <div className="border-t border-zinc-200 pt-3 flex items-center justify-between">
              <span className="text-sm font-bold text-zinc-900">Total Pulse MRR</span>
              <span className="text-xl font-bold text-emerald-600">£{mrr}/mo</span>
            </div>
          </div>
        </Card>
      </div>

      {/* Sites Table */}
      <Card className="bg-white border-zinc-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-zinc-100 flex items-center justify-between">
          <h3 className="font-medium text-zinc-900">Pulse Sites ({sites.length})</h3>
          <Button size="sm" variant="outline" className="border-zinc-200 text-zinc-600 h-8" onClick={onRefresh} data-testid="pulse-refresh-btn">
            <RefreshCw size={12} className="mr-1" /> Refresh
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="pulse-sites-table">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50">
                <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Site</th>
                <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Owner</th>
                <th className="text-center p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Users</th>
                <th className="text-center p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Equipment</th>
                <th className="text-center p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Open Faults</th>
                <th className="text-center p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">30d Activity</th>
                <th className="text-center p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Files</th>
                <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Tier</th>
                <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Status</th>
                <th className="text-right p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Monthly</th>
                <th className="text-right p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sites.map(site => (
                <tr key={site.id} className="border-b border-zinc-50 hover:bg-zinc-50 transition-colors" data-testid={`pulse-site-${site.id}`}>
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-md flex items-center justify-center flex-shrink-0" style={{ background: `${PULSE_BLUE}10` }}>
                        <Wrench size={14} style={{ color: PULSE_BLUE }} />
                      </div>
                      <div>
                        <p className="font-medium text-zinc-900">{site.name}</p>
                        <p className="text-[10px] text-zinc-400">Since {site.created_at ? new Date(site.created_at).toLocaleDateString() : '—'}</p>
                      </div>
                    </div>
                  </td>
                  <td className="p-3">
                    <p className="text-xs text-zinc-700">{site.owner_name || '—'}</p>
                    <p className="text-[10px] text-zinc-400">{site.owner_email}</p>
                  </td>
                  <td className="p-3 text-center font-medium text-zinc-900">{site.user_count}</td>
                  <td className="p-3 text-center font-medium text-zinc-900">{site.equipment_count}</td>
                  <td className="p-3 text-center">
                    <span className={`font-medium ${site.open_faults > 0 ? 'text-red-600' : 'text-emerald-600'}`}>{site.open_faults}</span>
                    <span className="text-zinc-400">/{site.total_faults}</span>
                  </td>
                  <td className="p-3 text-center">
                    {site.recent_faults_30d > 0 ? (
                      <Badge className="bg-amber-50 text-amber-700 border-amber-200">{site.recent_faults_30d} new</Badge>
                    ) : (
                      <span className="text-xs text-zinc-400">None</span>
                    )}
                  </td>
                  <td className="p-3 text-center text-zinc-600">{site.file_count}</td>
                  <td className="p-3">
                    <Select value={site.account_type} onValueChange={(v) => onUpgrade(site.id, v)}>
                      <SelectTrigger className={`h-7 text-xs border w-28 ${PULSE_TYPE_STYLES[site.account_type] || 'bg-zinc-100 text-zinc-700 border-zinc-200'}`} data-testid={`pulse-tier-${site.id}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-white border-zinc-200">
                        <SelectItem value="lite">Lite</SelectItem>
                        <SelectItem value="pulse_pro">Pro</SelectItem>
                        <SelectItem value="full">Full (GymAxis)</SelectItem>
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="p-3">
                    <Badge className={STATUS_STYLES[site.status || 'active']}>{site.status || 'active'}</Badge>
                  </td>
                  <td className="p-3 text-right font-medium text-zinc-900">£{site.monthly_cost}</td>
                  <td className="p-3 text-right">
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-zinc-400 hover:text-zinc-900" onClick={() => {
                      const org = organizations.find(o => o.id === site.id);
                      if (org) onSelectOrg(org);
                    }} data-testid={`pulse-view-${site.id}`}>
                      <Eye size={14} />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {sites.length === 0 && (
          <div className="p-12 text-center">
            <Wrench size={32} className="text-zinc-300 mx-auto mb-3" />
            <p className="text-zinc-400 text-sm">No Pulse Fitness sites yet</p>
            <p className="text-zinc-400 text-xs mt-1">Set an organization's type to "Pulse" in the Organizations tab to get started</p>
          </div>
        )}
      </Card>
        </>
    </div>
  );
};

export default AdminPulse;
