import React from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '@/components/ui/dialog';

const STATUS_STYLES = {
  active: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  trial: 'bg-blue-50 text-blue-700 border-blue-200',
  suspended: 'bg-amber-50 text-amber-700 border-amber-200',
  cancelled: 'bg-red-50 text-red-700 border-red-200',
};

const AdminDialogs = ({
  featuresDialog, setFeaturesDialog, onUpdateFeatures,
  impersonateDialog, setImpersonateDialog,
  selectedOrg, setSelectedOrg,
}) => (
  <>
    {/* Features Dialog */}
    <Dialog open={!!featuresDialog} onOpenChange={() => setFeaturesDialog(null)}>
      <DialogContent className="bg-white border-zinc-200 text-zinc-900 max-w-md">
        <DialogHeader>
          <DialogTitle>Feature Control — {featuresDialog?.name}</DialogTitle>
        </DialogHeader>
        {featuresDialog && (
          <div className="space-y-4 pt-2">
            {[
              { key: 'ai_audits', label: 'AI Audit Reports' },
              { key: 'qr_scanning', label: 'QR Scanning' },
              { key: 'multi_site', label: 'Multi-Site Dashboard' },
              { key: 'api_access', label: 'API Access' },
              { key: 'white_label', label: 'White Labeling' },
            ].map(feat => (
              <div key={feat.key} className="flex items-center justify-between">
                <span className="text-sm text-zinc-700">{feat.label}</span>
                <Switch
                  checked={(featuresDialog.features || {})[feat.key] !== false}
                  onCheckedChange={(val) => {
                    const updated = { ...(featuresDialog.features || {}), [feat.key]: val };
                    setFeaturesDialog({ ...featuresDialog, features: updated });
                    onUpdateFeatures(featuresDialog.id, updated);
                  }}
                />
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>

    {/* Impersonate Dialog */}
    <Dialog open={!!impersonateDialog} onOpenChange={() => setImpersonateDialog(null)}>
      <DialogContent className="bg-white border-zinc-200 text-zinc-900 max-w-md">
        <DialogHeader>
          <DialogTitle>Impersonate User</DialogTitle>
        </DialogHeader>
        {impersonateDialog && (
          <div className="space-y-4 pt-2">
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-md text-sm text-amber-700">
              You are about to log in as <strong>{impersonateDialog.user.full_name || impersonateDialog.user.email}</strong>. This will open a new session.
            </div>
            <div className="text-xs text-zinc-500">
              <p>Email: {impersonateDialog.user.email}</p>
              <p>Org: {impersonateDialog.user.organization_id}</p>
              <p>Role: {impersonateDialog.user.role}</p>
            </div>
            <Button className="w-full bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" onClick={() => {
              localStorage.setItem('impersonate_token', impersonateDialog.token);
              window.open(`${window.location.origin}?impersonate=true`, '_blank');
              setImpersonateDialog(null);
            }} data-testid="confirm-impersonate-btn">
              Open as {impersonateDialog.user.full_name || 'User'}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>

    {/* Org Detail Dialog */}
    <Dialog open={!!selectedOrg} onOpenChange={() => setSelectedOrg(null)}>
      <DialogContent className="bg-white border-zinc-200 text-zinc-900 max-w-lg">
        <DialogHeader>
          <DialogTitle>{selectedOrg?.name}</DialogTitle>
        </DialogHeader>
        {selectedOrg && (
          <div className="space-y-4 pt-2 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-zinc-50 rounded-md">
                <p className="text-zinc-400 text-xs uppercase">Owner</p>
                <p className="text-zinc-900 font-medium">{selectedOrg.owner_name || selectedOrg.owner_email || '—'}</p>
              </div>
              <div className="p-3 bg-zinc-50 rounded-md">
                <p className="text-zinc-400 text-xs uppercase">Plan</p>
                <p className="text-zinc-900 font-medium capitalize">{selectedOrg.subscription_tier || 'Free'}</p>
              </div>
              <div className="p-3 bg-zinc-50 rounded-md">
                <p className="text-zinc-400 text-xs uppercase">Status</p>
                <Badge className={STATUS_STYLES[selectedOrg.status || 'active']}>{selectedOrg.status || 'active'}</Badge>
              </div>
              <div className="p-3 bg-zinc-50 rounded-md">
                <p className="text-zinc-400 text-xs uppercase">Test Account</p>
                <p className="text-zinc-900 font-medium">{selectedOrg.is_test ? 'Yes' : 'No'}</p>
              </div>
            </div>
            <div className="grid grid-cols-4 gap-3 text-center">
              <div className="p-2 bg-zinc-50 rounded-md">
                <p className="text-lg font-semibold text-zinc-900">{selectedOrg.user_count}</p>
                <p className="text-[10px] text-zinc-400 uppercase">Users</p>
              </div>
              <div className="p-2 bg-zinc-50 rounded-md">
                <p className="text-lg font-semibold text-zinc-900">{selectedOrg.equipment_count}</p>
                <p className="text-[10px] text-zinc-400 uppercase">Equipment</p>
              </div>
              <div className="p-2 bg-zinc-50 rounded-md">
                <p className="text-lg font-semibold text-zinc-900">{selectedOrg.issue_count}</p>
                <p className="text-[10px] text-zinc-400 uppercase">Issues</p>
              </div>
              <div className="p-2 bg-zinc-50 rounded-md">
                <p className="text-lg font-semibold text-zinc-900">{selectedOrg.ai_calls}</p>
                <p className="text-[10px] text-zinc-400 uppercase">AI Calls</p>
              </div>
            </div>
            {selectedOrg.created_at && (
              <p className="text-xs text-zinc-400">Created: {new Date(selectedOrg.created_at).toLocaleDateString()}</p>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  </>
);

export default AdminDialogs;
