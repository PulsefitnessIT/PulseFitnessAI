import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Users, User, Trash2, Bookmark, Zap } from 'lucide-react';

import { notify } from '@/components/notifications';
import { can } from '@/utils/capabilities';
/**
 * Settings-panel view over the fault templates the current user can see.
 * - Org-scoped templates can only be deleted by owner/manager/master_admin.
 * - Personal templates are deletable by their creator.
 *
 * Editing is intentionally out-of-scope for MVP: delete + re-create is simpler
 * and avoids a second dialog. Usage analytics (`usage_count`, `last_used_at`)
 * help admins identify which templates deserve to be promoted site-wide.
 */
const FaultTemplatesManager = ({ API, user }) => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);

  const privileged = can(user, 'manage_fault_templates');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/fault-templates`, { headers: { Authorization: `Bearer ${token}` } });
      setTemplates(res.data.templates || []);
    } catch {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (tpl) => {
     
    if (!window.confirm(`Delete template "${tpl.name}"?`)) return;
    setDeletingId(tpl.id);
    try {
      const token = localStorage.getItem('token');
      await axios.delete(`${API}/fault-templates/${tpl.id}`, { headers: { Authorization: `Bearer ${token}` } });
      notify.success('Template deleted');
      setTemplates(prev => prev.filter(t => t.id !== tpl.id));
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Failed to delete';
      notify.error(msg);
    } finally {
      setDeletingId(null);
    }
  };

  const canDelete = (tpl) =>
    tpl.scope === 'personal'
      ? tpl.created_by_user_id === user?.id || user?.is_master_admin
      : privileged;

  return (
    <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-6" data-testid="fault-templates-manager">
      <div className="flex items-center gap-2 mb-4">
        <Bookmark size={18} className="text-[var(--color-brand-blue)]" />
        <h3 className="text-xl font-semibold text-white">Fault Templates</h3>
      </div>
      <p className="text-[var(--color-text-muted)] text-sm mb-4">
        Quick-log shortcuts for recurring fault patterns. Site-wide templates are shared with
        everyone in your gym; personal templates are yours alone. Most-used templates surface
        as one-click suggestions at the top of the fault-log dialog.
      </p>

      {loading && (
        <p className="text-[var(--color-text-muted)] text-sm" data-testid="templates-loading">Loading templates…</p>
      )}

      {!loading && templates.length === 0 && (
        <div className="rounded-lg border border-dashed border-[var(--theme-border)] p-6 text-center" data-testid="templates-empty">
          <p className="text-[var(--color-text-muted)] text-sm mb-1">No templates yet.</p>
          <p className="text-[var(--color-text-muted)] text-xs">
            Use the &ldquo;Save as template&rdquo; button inside the Log-a-Fault dialog to capture a pattern.
          </p>
        </div>
      )}

      {!loading && templates.length > 0 && (
        <div className="space-y-2" data-testid="templates-list">
          {templates.map(tpl => (
            <div
              key={tpl.id}
              className="flex items-center justify-between gap-3 p-3 rounded-lg border border-[var(--theme-border)] bg-[var(--theme-surface)]"
              data-testid={`template-row-${tpl.id}`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-white text-sm font-medium truncate">{tpl.name}</p>
                  {tpl.scope === 'org' ? (
                    <Badge className="bg-blue-500/20 text-blue-300 border-transparent text-[10px] gap-1">
                      <Users size={10} /> Site-wide
                    </Badge>
                  ) : (
                    <Badge className="bg-zinc-500/20 text-zinc-300 border-transparent text-[10px] gap-1">
                      <User size={10} /> Personal
                    </Badge>
                  )}
                  {tpl.fault_code && (
                    <Badge className="bg-amber-500/20 text-amber-300 border-transparent text-[10px]">
                      {tpl.fault_code}
                    </Badge>
                  )}
                  {tpl.usage_count > 0 && (
                    <span className="flex items-center gap-1 text-[10px] text-[var(--color-brand-blue)]">
                      <Zap size={10} /> {tpl.usage_count}× used
                    </span>
                  )}
                </div>
                <p className="text-[var(--color-text-muted)] text-xs mt-0.5 truncate">
                  {tpl.machine_type} · {tpl.issue_description?.slice(0, 100)}
                  {tpl.issue_description?.length > 100 ? '…' : ''}
                </p>
                <p className="text-[var(--color-ink-muted)] text-[10px] mt-0.5">
                  By {tpl.created_by_name || 'unknown'} · {tpl.severity}
                </p>
              </div>
              {canDelete(tpl) && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleDelete(tpl)}
                  disabled={deletingId === tpl.id}
                  className="border-[var(--theme-border)] text-red-400 hover:bg-red-500/10 flex-shrink-0"
                  data-testid={`template-delete-${tpl.id}`}
                >
                  <Trash2 size={14} />
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};

export default FaultTemplatesManager;
