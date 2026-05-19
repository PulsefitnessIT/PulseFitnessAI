import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Search, Crown, User, Eye, KeyRound, Ban } from 'lucide-react';

const AdminUsers = ({
  filteredUsers, search, onSearchChange,
  onImpersonate, onResetPassword, onDisableUser,
}) => (
  <div className="space-y-4">
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" size={16} />
      <Input value={search} onChange={e => onSearchChange(e.target.value)} placeholder="Search by name, email, or organization..." className="bg-white border-zinc-200 text-zinc-900 pl-10 h-9" data-testid="user-search" />
    </div>

    <Card className="bg-white border-zinc-200 shadow-sm overflow-hidden">
      <div className="overflow-x-auto">
      <table className="w-full text-sm min-w-[640px]" data-testid="user-table">
        <thead>
          <tr className="border-b border-zinc-100 bg-zinc-50">
            <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">User</th>
            <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Organisation</th>
            <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Role</th>
            <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Status</th>
            <th className="text-left p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Joined</th>
            <th className="text-right p-3 text-xs font-bold uppercase tracking-wider text-zinc-400">Actions</th>
          </tr>
        </thead>
        <tbody>
          {filteredUsers.map(u => (
            <tr key={u.id} className="border-b border-zinc-50 hover:bg-zinc-50 transition-colors" data-testid={`user-row-${u.id}`}>
              <td className="p-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-zinc-100 flex items-center justify-center flex-shrink-0">
                    {u.is_master_admin ? <Crown size={14} className="text-amber-500" /> : <User size={14} className="text-zinc-500" />}
                  </div>
                  <div>
                    <p className="font-medium text-zinc-900">{u.full_name || 'Unnamed'}</p>
                    <p className="text-zinc-400 text-xs">{u.email}</p>
                  </div>
                </div>
              </td>
              <td className="p-3 text-zinc-600 text-xs">{u.organization_name}</td>
              <td className="p-3">
                <Badge className={u.role === 'owner' ? 'bg-amber-50 text-amber-700 border-amber-200' : u.role === 'manager' ? 'bg-blue-50 text-blue-700 border-blue-200' : 'bg-zinc-100 text-zinc-600'}>
                  {u.role || 'member'}
                </Badge>
              </td>
              <td className="p-3">
                {u.disabled ? (
                  <Badge className="bg-red-50 text-red-600 border-red-200">Disabled</Badge>
                ) : (
                  <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">Active</Badge>
                )}
              </td>
              <td className="p-3 text-zinc-400 text-xs">{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
              <td className="p-3 text-right">
                <div className="flex items-center justify-end gap-1">
                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-zinc-400 hover:text-blue-600" onClick={() => onImpersonate(u.id)} title="Impersonate" data-testid={`user-impersonate-${u.id}`}>
                    <Eye size={14} />
                  </Button>
                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-zinc-400 hover:text-amber-600" onClick={() => onResetPassword(u.id)} title="Reset Password" data-testid={`user-reset-pwd-${u.id}`}>
                    <KeyRound size={14} />
                  </Button>
                  <Button size="sm" variant="ghost" className={`h-7 w-7 p-0 ${u.disabled ? 'text-green-500 hover:text-green-700' : 'text-zinc-400 hover:text-red-600'}`} onClick={() => onDisableUser(u.id, !u.disabled)} title={u.disabled ? 'Enable' : 'Disable'} data-testid={`user-disable-${u.id}`}>
                    <Ban size={14} />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {filteredUsers.length === 0 && <p className="text-center text-zinc-400 py-12 text-sm">No users found</p>}
    </Card>
  </div>
);

export default AdminUsers;
