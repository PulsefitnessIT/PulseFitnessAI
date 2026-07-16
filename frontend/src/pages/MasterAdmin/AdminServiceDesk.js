import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { UserPlus, UserMinus, HeadphonesIcon, Mail, Loader2, Copy } from 'lucide-react';

function authConfig() {
  const token = localStorage.getItem('token');
  return { headers: token ? { Authorization: `Bearer ${token}` } : {} };
}

const BRAND_BADGE = {
  gymaxis: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  pulse:   'bg-blue-50 text-blue-700 border-blue-200',
};

export default function AdminServiceDesk({ API, isPulseAdmin = false }) {
  const [members, setMembers] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  // Create-new form
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ email: '', full_name: '', brand: 'gymaxis' });
  const [creating, setCreating] = useState(false);
  const [lastCreated, setLastCreated] = useState(null); // {email, temp_password, brand} when email failed

  // Grant existing form — pick from a dropdown of current staff
  const [grantEmail, setGrantEmail] = useState('');
  const [people, setPeople] = useState([]);
  const grantBrand = isPulseAdmin ? 'pulse' : 'gymaxis';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/service-desk/members`, authConfig());
      setMembers(r.data.members || []);
      setTotal(r.data.total || 0);
    } catch {
      notify.error('Failed to load Service Desk members');
    } finally { setLoading(false); }
  }, [API]);

  const loadPeople = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/master-admin/users`, authConfig());
      setPeople(r.data.users || []);
    } catch { /* dropdown just stays empty */ }
  }, [API]);

  useEffect(() => { load(); loadPeople(); }, [load, loadPeople]);

  const createUser = async () => {
    const email = createForm.email.trim().toLowerCase();
    const full_name = createForm.full_name.trim();
    if (!email || !full_name) return;
    setCreating(true);
    try {
      const r = await axios.post(`${API}/master-admin/service-desk/users`,
        { email, full_name, brand: createForm.brand }, authConfig());
      const sent = r.data.email_sent;
      notify.success(
        sent
          ? `Created ${createForm.brand === 'pulse' ? 'Pulse' : 'Pulse Fitness'} Service Desk user · welcome email sent to ${email}`
          : `Created ${email} — share the temp password manually below (email failed)`,
        { duration: 8000 },
      );
      if (!sent) {
        setLastCreated({ email, temp_password: r.data.temp_password, brand: createForm.brand });
      }
      setCreateForm({ email: '', full_name: '', brand: createForm.brand });
      setCreateOpen(false);
      await load();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to create Service Desk user');
    } finally { setCreating(false); }
  };

  const grantExisting = async () => {
    const email = grantEmail.trim().toLowerCase();
    if (!email) return;
    try {
      await axios.post(`${API}/master-admin/service-desk/members/grant`,
        { email, brand: grantBrand }, authConfig());
      notify.success(`Granted Service Desk access to ${email}`);
      setGrantEmail('');
      await load(); await loadPeople();
    } catch (e) {
      notifyApiError(notify, e, 'Grant failed');
    }
  };

  const revoke = async (email) => {
    if (!window.confirm(`Revoke Service Desk access from ${email}?`)) return;
    try {
      await axios.post(`${API}/master-admin/service-desk/members/revoke`, { email }, authConfig());
      notify.success(`Revoked Service Desk role from ${email}`);
      await load(); await loadPeople();
    } catch (e) {
      notifyApiError(notify, e, 'Revoke failed');
    }
  };

  // Staff who don't already have Service Desk access — the grant dropdown options
  const memberEmails = new Set(members.map((m) => (m.email || '').toLowerCase()));
  const candidates = people
    .filter((p) => p.email && !memberEmails.has(p.email.toLowerCase()) && !p.is_service_desk)
    .sort((a, b) => (a.full_name || a.email).localeCompare(b.full_name || b.email));

  return (
    <div className="space-y-4" data-testid="admin-service-desk">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900 flex items-center gap-2">
            <HeadphonesIcon className="w-5 h-5 text-orange-600" /> Service Desk Members
          </h2>
          <p className="text-sm text-zinc-500 mt-1">
            {total} {total === 1 ? 'person has' : 'people have'} Service Desk access.{' '}
            Nominate Pulse Fitness Ltd staff — they’re routed straight to the Service Desk when they sign in.
          </p>
        </div>
        <Button
          onClick={() => setCreateOpen((v) => !v)}
          className="bg-orange-600 hover:bg-orange-700 text-white"
          data-testid="desk-create-toggle"
        >
          <UserPlus className="w-4 h-4 mr-1" /> Create Service Desk user
        </Button>
      </div>

      {/* Create-new card */}
      {createOpen && (
        <Card className="p-5 border-orange-200 bg-orange-50/40" data-testid="desk-create-card">
          <div className="text-sm font-medium text-zinc-900 mb-3">
            New Service Desk user — temp password emailed automatically
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
            <Input
              placeholder="Full name"
              value={createForm.full_name}
              onChange={(e) => setCreateForm((f) => ({ ...f, full_name: e.target.value }))}
              data-testid="desk-create-name"
            />
            <Input
              type="email"
              placeholder="agent@email.com"
              value={createForm.email}
              onChange={(e) => setCreateForm((f) => ({ ...f, email: e.target.value }))}
              data-testid="desk-create-email"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={creating} data-testid="desk-create-cancel">Cancel</Button>
            <Button
              onClick={createUser}
              disabled={creating || !createForm.email.trim() || !createForm.full_name.trim()}
              className="bg-orange-600 hover:bg-orange-700 text-white"
              data-testid="desk-create-submit"
            >
              {creating ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Mail className="w-4 h-4 mr-1" />}
              Create &amp; email temp password
            </Button>
          </div>
          <p className="text-[11px] text-zinc-500 mt-2">
            Service Desk users are routed <strong>straight to the Service Desk</strong> when they sign in. They can view tickets across all clients in their brand, reply, change status, assign, and import equipment.
          </p>
        </Card>
      )}

      {/* If email delivery failed, show fallback temp password once */}
      {lastCreated && (
        <Card className="p-5 border-amber-300 bg-amber-50" data-testid="desk-temp-pwd-fallback">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm">
              Welcome email failed to send to <strong>{lastCreated.email}</strong>. Share this temp password manually:
              <div className="font-mono text-base font-semibold text-amber-900 mt-1">{lastCreated.temp_password}</div>
            </div>
            <Button
              size="sm" variant="outline"
              onClick={() => { navigator.clipboard.writeText(lastCreated.temp_password); notify.success('Copied'); }}
              data-testid="desk-temp-pwd-copy"
            >
              <Copy className="w-3.5 h-3.5 mr-1" /> Copy
            </Button>
          </div>
          <button onClick={() => setLastCreated(null)} className="text-xs text-amber-700 underline mt-2">Dismiss</button>
        </Card>
      )}

      {/* Grant-existing card */}
      <Card className="p-5">
        <div className="text-sm font-medium text-zinc-900 mb-2">Grant Service Desk role to an existing user</div>
        <div className="flex flex-wrap gap-2 items-center">
          <select
            value={grantEmail}
            onChange={(e) => setGrantEmail(e.target.value)}
            className="flex-1 min-w-[300px] text-sm border border-zinc-200 rounded-md px-3 py-2 bg-white"
            data-testid="desk-grant-user"
          >
            <option value="">Select a staff member…</option>
            {candidates.map((p) => (
              <option key={p.id || p.email} value={p.email}>
                {(p.full_name || p.email)}{p.full_name ? ` — ${p.email}` : ''}{p.job_title ? ` · ${p.job_title}` : ''}
              </option>
            ))}
          </select>
          <Button
            onClick={grantExisting}
            disabled={!grantEmail.trim()}
            className="bg-zinc-800 hover:bg-zinc-900 text-white"
            data-testid="desk-grant-btn"
          >
            <UserPlus className="w-4 h-4 mr-1" /> Grant access
          </Button>
        </div>
        {candidates.length === 0 && (
          <p className="text-xs text-zinc-500 mt-2">All staff already have Service Desk access, or no other staff exist yet.</p>
        )}
      </Card>

      {/* Members list */}
      <Card className="p-5">
        <div className="text-sm font-medium text-zinc-900 mb-3">Current Members</div>
        {loading ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : members.length === 0 ? (
          <div className="text-xs text-zinc-500">No Service Desk members yet.</div>
        ) : (
          <div className="space-y-1">
            {members.map((m) => (
              <div
                key={m.id}
                className="flex items-center justify-between py-2 border-b border-zinc-100 last:border-0 text-sm"
                data-testid={`desk-member-${m.id}`}
              >
                <div className="min-w-0">
                  <div className="text-zinc-900 truncate">{m.full_name || m.email}</div>
                  <div className="text-xs text-zinc-500 truncate">{m.email}</div>
                </div>
                <div className="flex items-center gap-2 flex-wrap justify-end">
                  <Badge variant="outline" className="text-[10px] bg-orange-50 text-orange-700 border-orange-200">Service Desk</Badge>
                  {m.must_change_password && (
                    <Badge variant="outline" className="text-[10px] bg-amber-50 text-amber-700 border-amber-200">Pending first sign-in</Badge>
                  )}
                  {m.is_master_admin && (
                    <Badge variant="outline" className="text-[10px] bg-purple-50 text-purple-700 border-purple-200">Master Admin</Badge>
                  )}
                  {m.disabled && (
                    <Badge variant="outline" className="text-[10px] bg-red-50 text-red-700 border-red-200">Disabled</Badge>
                  )}
                  {!m.is_master_admin && (
                    <Button
                      size="sm" variant="outline"
                      onClick={() => revoke(m.email)}
                      className="text-red-600 border-red-200 hover:bg-red-50"
                      data-testid={`desk-revoke-${m.id}`}
                    >
                      <UserMinus className="w-3 h-3 mr-1" /> Revoke
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
