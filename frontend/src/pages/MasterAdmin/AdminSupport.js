import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Users } from 'lucide-react';

const AdminSupport = ({ stats, onGoUsers }) => (
  <div className="space-y-4">
    <Card className="bg-white border-zinc-200 shadow-sm p-6">
      <h3 className="font-medium text-zinc-900 mb-3">Impersonate User</h3>
      <p className="text-sm text-zinc-500 mb-4">Log in as any user to debug issues or provide support. Go to <strong>Users</strong> tab and click the eye icon on any user.</p>
      <Button onClick={onGoUsers} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" data-testid="go-to-users-btn">
        <Users size={14} className="mr-2" /> Go to Users
      </Button>
    </Card>

    <Card className="bg-white border-zinc-200 shadow-sm p-6">
      <h3 className="font-medium text-zinc-900 mb-3">Quick Stats</h3>
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div className="p-3 bg-zinc-50 rounded-md">
          <p className="text-zinc-400 text-xs uppercase tracking-wider">Open Cases</p>
          <p className="text-2xl font-semibold text-zinc-900">{stats?.open_issues || 0}</p>
        </div>
        <div className="p-3 bg-zinc-50 rounded-md">
          <p className="text-zinc-400 text-xs uppercase tracking-wider">Supplier Cases</p>
          <p className="text-2xl font-semibold text-zinc-900">{stats?.total_supplier_cases || 0}</p>
        </div>
      </div>
    </Card>
  </div>
);

export default AdminSupport;
