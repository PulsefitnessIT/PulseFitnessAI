/**
 * Pulse Upgrade Requests Strip — Master Admin overview.
 *
 * Shows incoming upgrade requests from the Pulse landing page alongside
 * the existing Trial Funnel strip. Lets the admin move records through
 * the funnel (new → contacted → quoted → converted/lost).
 */
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/App';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Building2, Sparkles, ArrowRight, Mail, Phone, MessageSquare, Clock,
  CheckCircle2, XCircle, RefreshCw,
} from 'lucide-react';

import { notify } from '@/components/notifications';
const STATUSES = [
  { value: 'new', label: 'New', tone: 'bg-blue-50 border-blue-200 text-blue-700' },
  { value: 'contacted', label: 'Contacted', tone: 'bg-violet-50 border-violet-200 text-violet-700' },
  { value: 'quoted', label: 'Quoted', tone: 'bg-amber-50 border-amber-200 text-amber-700' },
  { value: 'converted', label: 'Converted', tone: 'bg-emerald-50 border-emerald-200 text-emerald-700' },
  { value: 'lost', label: 'Lost', tone: 'bg-zinc-50 border-zinc-200 text-zinc-500' },
];

const METHOD_ICON = { email: Mail, phone: Phone, either: MessageSquare };

export default function PulseUpgradeRequestsStrip() {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/master-admin/pulse-upgrade-requests`, { headers });
      setData(res.data);
    } catch {
      setData({ total: 0, new_last_7d: 0, by_status: {}, items: [] });
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const updateStatus = async (reqId, status) => {
    try {
      await axios.patch(`${API}/master-admin/pulse-upgrade-requests/${reqId}`,
        { status }, { headers });
      notify.success(`Marked as ${status}`);
      load();
    } catch {
      notify.error('Could not update status');
    }
  };

  if (loading || !data) return null;
  if (data.total === 0) return null;

  const byStatus = data.by_status || {};
  const newCount = byStatus.new || 0;

  return (
    <Card className="bg-white border-zinc-200 shadow-sm p-5 lg:p-5" data-testid="pulse-upgrade-strip">
      <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
        <div>
          <h3 className="text-base font-medium text-zinc-900 flex items-center gap-2">
            <Sparkles size={16} className="text-[var(--color-brand-cyan)]" />
            Pulse Pro — Upgrade Requests
          </h3>
          <p className="text-xs text-zinc-500 mt-0.5">
            {data.total} total · {data.new_last_7d || 0} in last 7 days · {newCount} awaiting contact
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={load} data-testid="pulse-upgrade-refresh">
            <RefreshCw size={12} className="mr-1" /> Refresh
          </Button>
          <Button
            size="sm"
            variant={expanded ? 'default' : 'outline'}
            onClick={() => setExpanded((v) => !v)}
            data-testid="pulse-upgrade-toggle"
          >
            {expanded ? 'Collapse' : 'Review'} <ArrowRight size={12} className="ml-1" />
          </Button>
        </div>
      </div>

      {/* Status tiles */}
      <div className="grid grid-cols-3 lg:grid-cols-5 gap-2">
        {STATUSES.map((s) => (
          <div
            key={s.value}
            className={`border rounded-lg p-3 ${s.tone}`}
            data-testid={`pulse-upgrade-tile-${s.value}`}
          >
            <div className="text-[10px] uppercase tracking-widest font-semibold opacity-80">{s.label}</div>
            <div className="mt-1 text-2xl font-bold tabular-nums">{byStatus[s.value] || 0}</div>
          </div>
        ))}
      </div>

      {/* Expandable list */}
      {expanded && (
        <div className="mt-4 border-t border-zinc-100 pt-4 space-y-3" data-testid="pulse-upgrade-list">
          {data.items.length === 0 ? (
            <div className="text-sm text-zinc-500 text-center py-6">No upgrade requests yet.</div>
          ) : (
            data.items.slice(0, 50).map((r) => {
              const MethodIcon = METHOD_ICON[r.contact_method] || MessageSquare;
              const status = r.status || 'new';
              const tone = STATUSES.find((s) => s.value === status)?.tone || '';
              return (
                <div
                  key={r.id}
                  className="border border-zinc-200 rounded-lg p-3 hover:border-zinc-300 transition-colors"
                  data-testid={`pulse-upgrade-item-${r.id}`}
                >
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Building2 size={14} className="text-zinc-400 shrink-0" />
                        <span className="font-semibold text-zinc-900 text-sm">{r.gym_name}</span>
                        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${tone}`}>
                          {status}
                        </span>
                      </div>
                      <div className="text-xs text-zinc-500 mt-1 flex items-center gap-3 flex-wrap">
                        <span className="flex items-center gap-1">
                          <Mail size={10} />
                          <a href={`mailto:${r.email}`} className="hover:text-[var(--color-brand-cyan)]">{r.email}</a>
                        </span>
                        {r.phone && (
                          <span className="flex items-center gap-1">
                            <Phone size={10} />
                            <a href={`tel:${r.phone}`} className="hover:text-[var(--color-brand-cyan)]">{r.phone}</a>
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <MethodIcon size={10} />
                          prefers {r.contact_method}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock size={10} />
                          {new Date(r.created_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      <div className="text-xs text-zinc-600 mt-1">
                        {r.full_name} · {r.site_count} site{r.site_count > 1 ? 's' : ''}
                        {r.equipment_count ? ` · ${r.equipment_count} pieces` : ''}
                      </div>
                      {r.notes && (
                        <div className="mt-2 px-3 py-2 bg-zinc-50 border-l-2 border-[var(--color-brand-cyan)] rounded text-xs text-zinc-700 leading-relaxed">
                          {r.notes}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      {status === 'new' && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => updateStatus(r.id, 'contacted')}
                          data-testid={`pulse-upgrade-contact-${r.id}`}
                        >
                          Mark contacted
                        </Button>
                      )}
                      {status === 'contacted' && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => updateStatus(r.id, 'quoted')}
                          data-testid={`pulse-upgrade-quote-${r.id}`}
                        >
                          Mark quoted
                        </Button>
                      )}
                      {(status === 'new' || status === 'contacted' || status === 'quoted') && (
                        <div className="flex gap-1">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => updateStatus(r.id, 'converted')}
                            className="border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                            data-testid={`pulse-upgrade-win-${r.id}`}
                          >
                            <CheckCircle2 size={11} className="mr-1" /> Win
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => updateStatus(r.id, 'lost')}
                            className="border-zinc-300 text-zinc-500 hover:bg-zinc-50"
                            data-testid={`pulse-upgrade-lost-${r.id}`}
                          >
                            <XCircle size={11} className="mr-1" /> Lost
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </Card>
  );
}
