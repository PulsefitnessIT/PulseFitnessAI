/**
 * OrgLinkedSitesTab — Iter 215br
 *
 * Lists all sites belonging to the current org, plus the ability to
 * MOVE / RE-LINK any of them to another organisation in the same
 * Master Admin scope. Used inside the Master Admin OrgDrawer so
 * multi-site groups can be rolled up under the right HQ org.
 */
import React from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { notify } from '@/components/notifications';
import { Building2, MapPin, Link2, ArrowRightLeft, Crown, Loader2 } from 'lucide-react';

const OrgLinkedSitesTab = ({ orgId, orgName }) => {
  const { API } = useAuth();
  const [sites, setSites] = React.useState([]);
  const [orgs, setOrgs] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [moving, setMoving] = React.useState(null); // siteId currently being moved
  const [targetByRow, setTargetByRow] = React.useState({});

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const load = React.useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const [sitesRes, orgsRes] = await Promise.all([
        axios.get(`${API}/master-admin/organizations/${orgId}/sites`, { headers }),
        axios.get(`${API}/master-admin/organizations`, { headers }),
      ]);
      setSites(sitesRes.data?.sites || []);
      const allOrgs = orgsRes.data?.organizations || orgsRes.data || [];
      setOrgs(allOrgs.filter((o) => o.id !== orgId));
    } catch (e) {
      console.error('Linked sites load failed', e);
      notify.error('Failed to load linked sites');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API, orgId]);

  React.useEffect(() => { load(); }, [load]);

  const moveSite = async (site) => {
    const target = targetByRow[site.id];
    if (!target) {
      notify.error('Pick a target organisation first');
      return;
    }
    setMoving(site.id);
    try {
      const r = await axios.post(
        `${API}/master-admin/organizations/${orgId}/sites/${site.id}/move`,
        { target_organization_id: target },
        { headers },
      );
      notify.success(`"${site.name}" moved to ${r.data.target_organization_name}`);
      setTargetByRow((p) => { const n = { ...p }; delete n[site.id]; return n; });
      await load();
    } catch (e) {
      notify.error('Move failed', e.response?.data?.detail || 'Try again.');
    } finally {
      setMoving(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-zinc-500" data-testid="org-linked-sites-loading">
        <Loader2 className="animate-spin mr-2" size={16} /> Loading sites…
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="org-linked-sites-tab">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
            <Link2 size={14} /> Linked sites · {orgName}
          </h4>
          <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-0.5">
            Move a site into another organisation to roll multi-site groups under the right head office.
          </p>
        </div>
        <span className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 dark:text-zinc-400">
          {sites.length} site{sites.length === 1 ? '' : 's'}
        </span>
      </div>

      {sites.length === 0 ? (
        <p className="text-xs text-zinc-500 dark:text-zinc-400 py-6 text-center">No sites set up for this organisation yet.</p>
      ) : (
        <div className="space-y-2">
          {sites.map((s) => (
            <div
              key={s.id}
              className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white/50 p-3"
              data-testid={`org-linked-site-${s.id}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Building2 size={13} className="text-zinc-400" />
                    <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">{s.name}</p>
                    {s.is_head_office && (
                      <span className="inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
                        <Crown size={9} /> HQ
                      </span>
                    )}
                    {s.is_default && (
                      <span className="text-[9px] font-bold uppercase tracking-wider bg-zinc-100 text-zinc-600 px-1.5 py-0.5 rounded">Default</span>
                    )}
                  </div>
                  {s.address && (
                    <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-1 flex items-center gap-1">
                      <MapPin size={10} /> {s.address}{s.postcode ? `, ${s.postcode}` : ''}
                    </p>
                  )}
                  <div className="flex gap-3 mt-1.5 text-[10px] text-zinc-500 dark:text-zinc-400">
                    <span>{s.equipment_count || 0} equipment</span>
                    <span>·</span>
                    <span>{s.issue_count || 0} issues</span>
                  </div>
                </div>
              </div>

              {!s.is_default && (
                <div className="mt-3 pt-3 border-t border-zinc-100 dark:border-zinc-800 flex items-end gap-2">
                  <div className="flex-1 min-w-0">
                    <Label className="text-[10px] uppercase tracking-wider text-zinc-500">Move to organisation</Label>
                    <select
                      value={targetByRow[s.id] || ''}
                      onChange={(e) => setTargetByRow((p) => ({ ...p, [s.id]: e.target.value }))}
                      className="w-full mt-1 px-2 py-1.5 text-xs rounded-md border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
                      data-testid={`org-site-move-target-${s.id}`}
                    >
                      <option value="">— select target —</option>
                      {orgs.map((o) => (
                        <option key={o.id} value={o.id}>{o.name}</option>
                      ))}
                    </select>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => moveSite(s)}
                    disabled={moving === s.id || !targetByRow[s.id]}
                    className="bg-blue-600 hover:bg-blue-700 text-white h-8 text-xs"
                    data-testid={`org-site-move-btn-${s.id}`}
                  >
                    {moving === s.id ? (
                      <><Loader2 size={11} className="animate-spin mr-1" /> Moving…</>
                    ) : (
                      <><ArrowRightLeft size={11} className="mr-1" /> Move</>
                    )}
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default OrgLinkedSitesTab;
