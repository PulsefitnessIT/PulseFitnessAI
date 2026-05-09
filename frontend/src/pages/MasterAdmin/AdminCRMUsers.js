import React, { useState, useEffect } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Users, Plus, Edit, Trash2, Loader2, Shield, Save, Mail, Key } from 'lucide-react';

const AdminCRMUsers = () => {
 const { API } = useAuth();
 const [users, setUsers] = useState([]);
 const [loading, setLoading] = useState(true);
 const [showForm, setShowForm] = useState(false);
 const [editingId, setEditingId] = useState(null);
 const [saving, setSaving] = useState(false);
 const [form, setForm] = useState({ email: '', full_name: '', password: '', role: 'user' });
 const token = localStorage.getItem('token');
 const headers = { Authorization: `Bearer ${token}` };

 const load = async () => {
 try {
 const res = await axios.get(`${API}/master-admin/crm-users`, { headers });
 setUsers(res.data.users || []);
 } catch { notify.error('Failed to load CRM users'); }
 setLoading(false);
 };

 useEffect(() => { load(); }, []);

 const openCreate = () => { setEditingId(null); setForm({ email: '', full_name: '', password: '', role: 'user' }); setShowForm(true); };
 const openEdit = (u) => { setEditingId(u.id); setForm({ email: u.email, full_name: u.full_name || '', password: '', role: u.role || 'user' }); setShowForm(true); };

 const handleSave = async () => {
 setSaving(true);
 try {
 if (editingId) {
 const payload = { full_name: form.full_name, role: form.role };
 if (form.password) payload.password = form.password;
 await axios.patch(`${API}/master-admin/crm-users/${editingId}`, payload, { headers });
 notify.success('CRM user updated');
 } else {
 await axios.post(`${API}/master-admin/crm-users`, form, { headers });
 notify.success('CRM user created');
 }
 setShowForm(false); load();
 } catch (err) { notifyApiError(notify, err, 'Failed to save'); }
 setSaving(false);
 };

 const handleDelete = async (id, email) => {
 if (!window.confirm(`Delete CRM user ${email}?`)) return;
 try { await axios.delete(`${API}/master-admin/crm-users/${id}`, { headers }); notify.success('Deleted'); load(); }
 catch { notify.error('Failed to delete'); }
 };

 const roleBadge = (role) => {
 const styles = { admin: 'bg-purple-500/15 text-purple-400', manager: 'bg-blue-500/15 text-blue-400', user: 'bg-gray-500/15 text-gray-400' };
 return <Badge className={`${styles[role] || styles.user} border-0 text-[10px]`}>{role}</Badge>;
 };

 if (loading) return <div className="flex justify-center py-16"><Loader2 className="animate-spin text-[var(--color-brand-blue)]" size={24} /></div>;

 return (
 <div className="space-y-4" data-testid="admin-crm-users">
 <div className="flex items-center justify-between">
 <div>
 <h3 className="text-white font-semibold text-lg flex items-center gap-2"><Users size={20} className="text-[var(--color-brand-blue)]" /> CRM Users</h3>
 <p className="text-[var(--color-text-muted)] text-sm">{users.length} users in the CRM system</p>
 </div>
 <Button className="" onClick={openCreate} data-testid="crm-add-user-btn">
 <Plus size={14} className="mr-1" /> Add CRM User
 </Button>
 </div>

 <div className="space-y-2">
 {users.map(u => (
 <Card key={u.id} className="bg-[var(--theme-surface)] border-white/10 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3" data-testid={`crm-user-${u.id}`}>
 <div className="flex items-center gap-3 min-w-0">
 <div className="w-9 h-9 rounded-full bg-[rgb(var(--rgb-brand-blue)/0.15)] flex items-center justify-center text-[var(--color-brand-blue)] font-bold text-sm shrink-0">
 {(u.full_name || u.email || '?')[0].toUpperCase()}
 </div>
 <div className="min-w-0 flex-1">
 <p className="text-white text-sm font-medium truncate" data-testid={`crm-user-name-${u.id}`}>{u.full_name || 'No Name'}</p>
 <p className="text-[var(--color-text-muted)] text-xs truncate flex items-center gap-1" data-testid={`crm-user-email-${u.id}`}><Mail size={10} /> {u.email}</p>
 </div>
 </div>
 <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap sm:shrink-0">
 <Select value={u.role || 'user'} onValueChange={async (v) => {
 try {
 await axios.patch(`${API}/master-admin/crm-users/${u.id}`, { full_name: u.full_name, role: v }, { headers });
 notify.success(`Role updated to ${v}`);
 load();
 } catch { notify.error('Failed to update role'); }
 }}>
 <SelectTrigger className={`h-7 text-xs border-0 w-24 ${u.role === 'admin' ? 'bg-violet-50 text-violet-700' : u.role === 'manager' ? 'bg-blue-50 text-blue-700' : 'bg-zinc-100 text-zinc-600'}`} data-testid={`crm-role-${u.id}`}><SelectValue /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 <SelectItem value="admin">Admin</SelectItem>
 <SelectItem value="manager">Manager</SelectItem>
 <SelectItem value="user">User</SelectItem>
 </SelectContent>
 </Select>
 <Button size="sm" variant="ghost" className="text-[var(--color-text-muted)] h-7 w-7 p-0" onClick={() => openEdit(u)} data-testid={`crm-edit-${u.id}`}><Edit size={13} /></Button>
 <Button size="sm" variant="ghost" className="text-red-400 h-7 w-7 p-0" onClick={() => handleDelete(u.id, u.email)} data-testid={`crm-delete-${u.id}`}><Trash2 size={13} /></Button>
 </div>
 </Card>
 ))}
 {users.length === 0 && <p className="text-[var(--color-text-muted)] text-sm text-center py-8">No CRM users found</p>}
 </div>

 <Dialog open={showForm} onOpenChange={setShowForm}>
 <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white" data-testid="crm-user-dialog">
 <DialogHeader>
 <DialogTitle>{editingId ? 'Edit CRM User' : 'Add CRM User'}</DialogTitle>
 </DialogHeader>
 <div className="space-y-3 mt-2">
 {!editingId && (
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Email</Label>
 <Input value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} placeholder="user@company.com" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="crm-user-email" />
 </div>
 )}
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Full Name</Label>
 <Input value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} placeholder="John Doe" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="crm-user-name" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">{editingId ? 'New Password (leave blank to keep)' : 'Password'}</Label>
 <Input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} placeholder={editingId ? '••••••••' : 'Strong password'} className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="crm-user-password" />
 </div>
 <div>
 <Label className="text-[var(--color-text-muted)] text-xs">Role</Label>
 <Select value={form.role} onValueChange={v => setForm({ ...form, role: v })}>
 <SelectTrigger className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="crm-user-role"><SelectValue /></SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-white/10">
 <SelectItem value="admin" className="text-white">Admin</SelectItem>
 <SelectItem value="manager" className="text-white">Manager</SelectItem>
 <SelectItem value="user" className="text-white">User</SelectItem>
 </SelectContent>
 </Select>
 </div>
 <Button className="w-full mt-2" onClick={handleSave} disabled={saving || (!editingId && (!form.email || !form.password))} data-testid="crm-user-save">
 {saving ? <Loader2 size={14} className="animate-spin mr-1" /> : <Save size={14} className="mr-1" />}
 {editingId ? 'Update User' : 'Create User'}
 </Button>
 </div>
 </DialogContent>
 </Dialog>
 </div>
 );
};

export default AdminCRMUsers;
