import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Archive, RotateCcw, Trash2, AlertTriangle, Clock, ShieldCheck, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';

import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const DeletionBadge = ({ days }) => {
  if (days == null) return <Badge className="bg-zinc-100 text-zinc-600 border-zinc-200">No schedule</Badge>;
  if (days <= 7) return <Badge className="bg-red-50 text-red-700 border-red-200 font-medium"><AlertTriangle size={11} className="mr-1" />{days}d left</Badge>;
  if (days <= 30) return <Badge className="bg-amber-50 text-amber-700 border-amber-200 font-medium"><Clock size={11} className="mr-1" />{days}d left</Badge>;
  return <Badge className="bg-zinc-50 text-zinc-700 border-zinc-200"><Clock size={11} className="mr-1" />{days}d left</Badge>;
};

const AdminArchive = () => {
  const [orgs, setOrgs] = useState([]);
  const [retentionDays, setRetentionDays] = useState(365);
  const [warningLeadDays, setWarningLeadDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  // Hard-delete confirmation modal
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/master-admin/archive`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setOrgs(res.data.organizations || []);
      setRetentionDays(res.data.retention_days || 365);
      setWarningLeadDays(res.data.warning_lead_days || 7);
    } catch (err) {
      notifyApiError(notify, err, 'Failed to load archive');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRestore = async (org) => {
    setBusyId(org.id);
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/master-admin/archive/${org.id}/restore`, {}, {
        headers: { Authorization: `Bearer ${token}` },
      });
      notify.success(`${org.name} restored — now active`);
      await load();
    } catch (err) {
      notifyApiError(notify, err, 'Restore failed');
    } finally {
      setBusyId(null);
    }
  };

  const handleHardDelete = async () => {
    if (!deleteTarget) return;
    if (deleteConfirmText !== deleteTarget.name) {
      notify.error('Name does not match — deletion aborted');
      return;
    }
    setBusyId(deleteTarget.id);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.delete(`${API}/master-admin/archive/${deleteTarget.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const totalPurged = Object.values(res.data.purged || {}).reduce((a, b) => a + b, 0);
      notify.success(`${deleteTarget.name} permanently deleted (${totalPurged} records purged)`);
      setDeleteTarget(null);
      setDeleteConfirmText('');
      await load();
    } catch (err) {
      notifyApiError(notify, err, 'Hard delete failed');
    } finally {
      setBusyId(null);
    }
  };

  const handleRunSweep = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/master-admin/archive/sweep`, {}, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const { scanned = 0, warnings_sent = 0, deleted = 0 } = res.data;
      notify.success(`Sweep complete — scanned ${scanned}, warned ${warnings_sent}, deleted ${deleted}`);
      await load();
    } catch (err) {
      notifyApiError(notify, err, 'Sweep failed');
    }
  };

  return (
    <div className="space-y-6" data-testid="admin-archive-section">
      {/* GDPR explainer banner */}
      <Card className="bg-gradient-to-br from-indigo-50 to-white border-indigo-200 p-5" data-testid="archive-policy-banner">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0">
            <ShieldCheck size={20} className="text-indigo-600" />
          </div>
          <div className="flex-1">
            <h3 className="text-base font-semibold text-zinc-900 mb-1">GDPR Right-to-Erasure Policy</h3>
            <p className="text-sm text-zinc-600 leading-relaxed">
              Archived organisations are permanently deleted after <strong>{retentionDays} days</strong>.
              The primary contact is notified by email <strong>{warningLeadDays} days</strong> before deletion.
              You can <strong>restore</strong> an organisation any time before the deadline, or trigger an
              <strong> immediate hard-delete</strong> to satisfy an urgent data-erasure request.
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={handleRunSweep}
            disabled={loading}
            className="border-indigo-200 text-indigo-700 hover:bg-indigo-50"
            data-testid="archive-sweep-btn"
          >
            <RefreshCw size={14} className={`mr-1 ${loading ? 'animate-spin' : ''}`} />
            Run sweep
          </Button>
        </div>
      </Card>

      {/* Empty state */}
      {!loading && orgs.length === 0 && (
        <Card className="p-12 text-center bg-white border-zinc-200" data-testid="archive-empty-state">
          <Archive size={40} className="mx-auto text-zinc-400 mb-3" />
          <h3 className="text-lg font-medium text-zinc-900 mb-1">No archived organisations</h3>
          <p className="text-sm text-zinc-500 max-w-md mx-auto">
            When you archive an organisation from the Organisations tab it will appear here
            with a countdown to permanent deletion.
          </p>
        </Card>
      )}

      {/* Archive list */}
      {orgs.length > 0 && (
        <div className="space-y-3" data-testid="archive-list">
          {orgs.map((org) => (
            <Card key={org.id} className="bg-white border-zinc-200 p-5" data-testid={`archived-org-${org.id}`}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <h4 className="text-base font-semibold text-zinc-900 truncate">{org.name}</h4>
                    <DeletionBadge days={org.days_until_deletion} />
                    {org.warning_sent_at && (
                      <Badge className="bg-amber-50 text-amber-700 border-amber-200 text-[10px]">
                        Warning email sent
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs text-zinc-500 space-y-0.5">
                    <div>
                      Archived <strong className="text-zinc-700">{org.archived_at?.slice(0, 10) || '—'}</strong>
                      {' '}by {org.archived_by || 'unknown'}
                    </div>
                    {org.scheduled_deletion_at && (
                      <div>
                        Scheduled for deletion on <strong className="text-zinc-700">{org.scheduled_deletion_at.slice(0, 10)}</strong>
                      </div>
                    )}
                    {(org.primary_contact_email || org.admin_email) && (
                      <div className="text-zinc-400">Contact: {org.primary_contact_email || org.admin_email}</div>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleRestore(org)}
                    disabled={busyId === org.id}
                    className="border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                    data-testid={`archive-restore-${org.id}`}
                  >
                    <RotateCcw size={13} className="mr-1" />
                    Restore
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => { setDeleteTarget(org); setDeleteConfirmText(''); }}
                    disabled={busyId === org.id}
                    className="border-red-200 text-red-700 hover:bg-red-50"
                    data-testid={`archive-delete-${org.id}`}
                  >
                    <Trash2 size={13} className="mr-1" />
                    Delete now
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Hard-delete confirmation dialog — typed confirmation */}
      <Dialog open={!!deleteTarget} onOpenChange={(v) => { if (!v) { setDeleteTarget(null); setDeleteConfirmText(''); } }}>
        <DialogContent className="max-w-md bg-white" data-testid="archive-delete-dialog">
          <DialogHeader>
            <DialogTitle className="text-red-700 flex items-center gap-2">
              <AlertTriangle size={18} /> Permanent deletion
            </DialogTitle>
            <DialogDescription className="text-zinc-600 pt-2">
              This will <strong>irrecoverably delete</strong> all data for{' '}
              <strong className="text-zinc-900">{deleteTarget?.name}</strong>: users, equipment,
              fault history, documents, suppliers, and all CRM records. This satisfies the
              GDPR right-to-erasure.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2 pt-2">
            <label className="text-sm font-medium text-zinc-700">
              Type the organisation name to confirm:
            </label>
            <Input
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              placeholder={deleteTarget?.name}
              className="border-zinc-300"
              data-testid="archive-delete-confirm-input"
            />
          </div>

          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => { setDeleteTarget(null); setDeleteConfirmText(''); }}
              data-testid="archive-delete-cancel"
            >
              Cancel
            </Button>
            <Button
              className="bg-red-600 hover:bg-red-700 text-white"
              onClick={handleHardDelete}
              disabled={deleteConfirmText !== deleteTarget?.name || busyId === deleteTarget?.id}
              data-testid="archive-delete-confirm"
            >
              <Trash2 size={13} className="mr-1" />
              Permanently delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AdminArchive;
