import { useEffect, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Users, Building2, Clock, Archive, ScrollText, FileText, Download } from 'lucide-react';
import { authConfig } from './authConfig';

export default function DeskSummary({ API, onJumpToCustomers }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  const downloadPdf = async (endpoint, filename, setBusy) => {
    setBusy(true);
    try {
      const r = await axios.get(`${API}${endpoint}`, {
        ...authConfig(),
        responseType: 'blob',
      });
      const blob = new Blob([r.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error(`${filename} download failed:`, e);
      alert(`Failed to download ${filename}. Check console for details.`);
    } finally {
      setBusy(false);
    }
  };

  const downloadBriefing = () =>
    downloadPdf('/admin-docs/security-briefing', 'Pulse_Fitness_Security_Briefing.pdf', setDownloading);

  useEffect(() => {
    const run = async () => {
      try {
        const r = await axios.get(`${API}/service-desk/summary`, authConfig());
        setData(r.data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [API]);

  if (loading) return <div className="text-zinc-500">Loading…</div>;
  if (!data) return <div className="text-red-500">Failed to load summary</div>;

  const { organizations, recent_actions_7d } = data;
  // Iter 253 — self-serve providers see their OWN desk's numbers, not the
  // platform customer-org estate (and none of the Pulse-specific copy).
  const isProvider = data.desk_kind === 'provider';
  const stats = isProvider
    ? [
        { label: 'Open Cases', value: data.provider.open_cases, icon: Clock, colour: 'bg-orange-50 text-orange-700' },
        { label: 'Total Cases', value: data.provider.total_cases, icon: ScrollText, colour: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800' },
        { label: 'Engineers', value: data.provider.engineers, icon: Users, colour: 'bg-emerald-50 text-emerald-700' },
        { label: 'Customers', value: data.provider.customers, icon: Building2, colour: 'bg-blue-50 text-blue-700' },
      ]
    : [
        { label: 'Total Customers', value: organizations.total, icon: Building2, colour: 'bg-orange-50 text-orange-700' },
        { label: 'Active', value: organizations.active, icon: Users, colour: 'bg-emerald-50 text-emerald-700' },
        { label: 'Pending Invite', value: organizations.pending_invite, icon: Clock, colour: 'bg-amber-50 text-amber-700' },
        { label: 'Archived', value: organizations.archived, icon: Archive, colour: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800' },
      ];

  return (
    <div className="space-y-6" data-testid="desk-summary">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Service Desk</h1>
        <p className="text-sm text-zinc-500 mt-1">
          {isProvider
            ? 'Cases, engineers and customers for your service operation.'
            : 'Customer operations, imports, and staff management for Pulse Fitness.'}
        </p>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {stats.map(({ label, value, icon: Icon, colour }) => (
          <Card key={label} className="p-5">
            <div className={`w-8 h-8 rounded ${colour} flex items-center justify-center mb-3`}>
              <Icon className="w-4 h-4" />
            </div>
            <div className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{value.toLocaleString()}</div>
            <div className="text-xs text-zinc-500 mt-1">{label}</div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <ScrollText className="w-4 h-4 text-zinc-500" />
            <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">Recent Activity</div>
          </div>
          <div className="text-3xl font-semibold text-zinc-900 dark:text-zinc-100">{recent_actions_7d}</div>
          <div className="text-xs text-zinc-500 mt-1">Service Desk actions in the last 7 days</div>
        </Card>
        <Card className="p-5 bg-gradient-to-br from-orange-50 to-amber-50 dark:from-orange-950/30 dark:to-amber-950/30 border-orange-100 dark:border-orange-900/40">
          <div className="text-sm font-medium text-zinc-900 mb-2 dark:text-zinc-100">Quick Actions</div>
          <Button
            size="sm" onClick={onJumpToCustomers}
            className="bg-orange-600 hover:bg-orange-700 text-white"
            data-testid="desk-quick-manage-customers"
          >
            Manage Customers
          </Button>
          <div className="text-xs text-zinc-500 mt-3">
            {isProvider ? 'Add engineers and raise cases from the tabs on the left.' : 'Bulk imports launch in Sprint 3.'}
          </div>
        </Card>
      </div>

      {!isProvider && (
      <Card className="p-5 border-blue-100 dark:border-blue-900/40 bg-gradient-to-br from-blue-50 to-sky-50 dark:from-blue-950/30 dark:to-sky-950/30">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <FileText className="w-4 h-4 text-blue-600" />
              <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Customer Security Briefing</div>
            </div>
            <div className="text-xs text-zinc-600 max-w-md">
              A printable 2-page document explaining how we keep Pulse Fitness data and the Sicon link secure.
              Hand to Directors, finance teams, or compliance reviewers.
            </div>
          </div>
          <Button
            size="sm"
            onClick={downloadBriefing}
            disabled={downloading}
            className="bg-blue-600 hover:bg-blue-700 text-white flex-shrink-0"
            data-testid="desk-download-security-briefing"
          >
            <Download className="w-4 h-4 mr-1" /> {downloading ? 'Preparing…' : 'Download PDF'}
          </Button>
        </div>
      </Card>
      )}
    </div>
  );
}
