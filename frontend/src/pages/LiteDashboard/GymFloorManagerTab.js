/**
 * Manager-side view of the Gym Floor module.
 *
 * Two panels:
 *  1. Setup — create/rotate the shared credentials + manage the staff roster
 *     and topic taxonomy.
 *  2. Diary — same entries the floor staff see, with delete rights for the
 *     manager. Flagged entries are highlighted for moderation review.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Users, KeyRound, ShieldAlert, Trash2, Plus, CopyIcon, Tag, Eye, EyeOff,
} from 'lucide-react';
import { useInlineBanner, useConfirm } from '@/components/notifications';

const GymFloorManagerTab = () => {
  const { API, user } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };
  // Managers/owners (or master admin, or MOD PRO users) see Setup + Diary.
  // Pulse Pro staff see only the Diary (read-only).
  const userRole = (user?.role || '').toLowerCase();
  const modPro = ['mod_branch', 'mod_org'].includes(user?.account_type || '');
  const isManager = userRole === 'owner' || userRole === 'manager' || user?.is_master_admin || modPro;

  const [cred, setCred] = useState(null);
  const [staff, setStaff] = useState([]);
  const [topics, setTopics] = useState([]);
  const [entries, setEntries] = useState([]);
  const [form, setForm] = useState({
    username: '', password: '',
    newStaff: '', newStaffEmail: '', newStaffMobile: '',
    newTopic: '',
  });
  const [editingStaffId, setEditingStaffId] = useState(null);
  const [staffEdit, setStaffEdit] = useState({ name: '', email: '', mobile: '' });
  const [panel, setPanel] = useState('diary');
  const [busy, setBusy] = useState(false);
  // Show/hide toggle so managers can verify the shared password before
  // distributing it to staff (the most common cause of login failures
  // is a typo introduced when setting the password silently).
  const [showPwd, setShowPwd] = useState(false);
  const { banner, show, clear } = useInlineBanner();
  const confirm = useConfirm();

  const load = useCallback(async () => {
    try {
      const s = await axios.get(`${API}/gym-floor/status`, { headers });
      setCred(s.data.credential || null);
    } catch {}
    try {
      const [st, tp, en] = await Promise.all([
        axios.get(`${API}/gym-floor/staff`, { headers }),
        axios.get(`${API}/gym-floor/topics`, { headers }),
        axios.get(`${API}/gym-floor/handover`, { headers }),
      ]);
      setStaff(st.data.staff || []);
      setTopics(tp.data.topics || []);
      setEntries(en.data.entries || []);
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API]);
  useEffect(() => { load(); }, [load]);

  const submitSetup = async (e) => {
    e.preventDefault();
    clear();
    if (!form.username || !form.password) {
      show({ tone: 'error', title: 'Credentials required' });
      return;
    }
    setBusy(true);
    try {
      await axios.post(`${API}/gym-floor/setup`, {
        username: form.username,
        password: form.password,
        staff_names: [],
      }, { headers });
      show({
        tone: 'success',
        title: 'Gym Floor login saved',
        detail: `Share these credentials with your staff. Login URL: ${window.location.origin}/gym-floor`,
      });
      load();
    } catch (err) {
      show({ tone: 'error', title: 'Couldn\'t save', detail: err.response?.data?.detail });
    }
    setBusy(false);
  };

  const addStaff = async () => {
    const nm = form.newStaff.trim();
    const em = form.newStaffEmail.trim();
    if (!nm) { show({ tone: 'error', title: 'Name required' }); return; }
    if (!em) { show({ tone: 'error', title: 'Email required', detail: 'Suppliers will use this to reach the staff member when a fault is logged.' }); return; }
    try {
      await axios.post(`${API}/gym-floor/staff`, {
        name: nm,
        email: em,
        mobile: form.newStaffMobile.trim() || null,
      }, { headers });
      setForm({ ...form, newStaff: '', newStaffEmail: '', newStaffMobile: '' });
      load();
    } catch (err) {
      show({ tone: 'error', title: 'Couldn\'t add staff', detail: err.response?.data?.detail });
    }
  };
  const startEditStaff = (s) => {
    setEditingStaffId(s.id);
    setStaffEdit({ name: s.name || '', email: s.email || '', mobile: s.mobile || '' });
  };
  const saveStaffEdit = async () => {
    if (!editingStaffId) return;
    try {
      await axios.patch(`${API}/gym-floor/staff/${editingStaffId}`, {
        name: staffEdit.name.trim(),
        email: staffEdit.email.trim(),
        mobile: staffEdit.mobile.trim(),
      }, { headers });
      setEditingStaffId(null);
      load();
    } catch (err) {
      show({ tone: 'error', title: 'Couldn\'t save', detail: err.response?.data?.detail });
    }
  };
  const removeStaff = async (s) => {
    const ok = await confirm({ title: `Remove ${s.name}?`, tone: 'danger', confirmLabel: 'Remove' });
    if (!ok) return;
    await axios.delete(`${API}/gym-floor/staff/${s.id}`, { headers });
    load();
  };

  const addTopic = async () => {
    const lb = form.newTopic.trim();
    if (!lb) return;
    await axios.post(`${API}/gym-floor/topics`, { label: lb }, { headers });
    setForm({ ...form, newTopic: '' });
    load();
  };
  const removeTopic = async (t) => {
    await axios.delete(`${API}/gym-floor/topics/${t.id}`, { headers });
    load();
  };

  const removeEntry = async (e) => {
    const ok = await confirm({
      title: 'Delete this diary entry?',
      detail: `By ${e.staff_name} · ${new Date(e.created_at).toLocaleString()}`,
      tone: 'danger',
      confirmLabel: 'Delete',
    });
    if (!ok) return;
    await axios.delete(`${API}/gym-floor/handover/${e.id}`, { headers });
    load();
  };

  const copyUrl = () => {
    navigator.clipboard.writeText(`${window.location.origin}/gym-floor`);
    show({ tone: 'info', title: 'Link copied', detail: `${window.location.origin}/gym-floor` });
  };

  const topicLabel = (id) => topics.find((t) => t.id === id)?.label || id;

  return (
    <div className="space-y-4" data-testid="gym-floor-manager-tab">
      {banner && <div>{banner}</div>}

      <div className={`subtab-bar ${isManager ? '' : 'hidden'}`} role="tablist">
        {[{ id: 'diary', label: `Diary (${entries.length})` }, { id: 'setup', label: 'Setup' }].map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => setPanel(p.id)}
            className={`subtab-pill ${panel === p.id ? 'is-active' : ''}`}
            data-testid={`gym-floor-panel-${p.id}`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {panel === 'setup' && isManager && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card className="p-5 rounded-xl" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><KeyRound size={14} /> Shared credentials</h3>
            {cred ? (
              <div className="p-3 rounded-lg mb-3 flex items-center justify-between gap-3" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }}>
                <div>
                  <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Active username</p>
                  <p className="text-sm font-mono font-semibold">{cred.username}</p>
                </div>
                <Button variant="outline" size="sm" onClick={copyUrl} className="rounded-full text-xs" data-testid="gym-floor-copy-link">
                  <CopyIcon size={12} className="mr-1" /> Copy login URL
                </Button>
              </div>
            ) : (
              <p className="text-sm mb-3" style={{ color: 'var(--theme-text-muted)' }}>No shared login yet — create one below.</p>
            )}
            <form onSubmit={submitSetup} className="space-y-2">
              <div>
                <Label className="text-xs">Username</Label>
                <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="e.g. studio-floor" data-testid="gym-floor-setup-username" />
              </div>
              <div>
                <Label className="text-xs">{cred ? 'New password' : 'Password'}</Label>
                <div className="relative">
                  <Input
                    type={showPwd ? 'text' : 'password'}
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    placeholder="Set a shareable password"
                    className="pr-10"
                    data-testid="gym-floor-setup-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPwd((v) => !v)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-black/5 dark:hover:bg-white/10 dark:bg-zinc-900"
                    aria-label={showPwd ? 'Hide password' : 'Show password'}
                    data-testid="gym-floor-setup-password-toggle"
                  >
                    {showPwd ? <EyeOff size={14} className="text-zinc-500" /> : <Eye size={14} className="text-zinc-500" />}
                  </button>
                </div>
              </div>
              <Button type="submit" disabled={busy} className="w-full rounded-full bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)]" data-testid="gym-floor-setup-submit">
                {busy ? 'Saving…' : cred ? 'Rotate credentials' : 'Create gym-floor login'}
              </Button>
            </form>
          </Card>

          <Card className="p-5 rounded-xl" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
            <h3 className="text-sm font-semibold mb-1 flex items-center gap-2"><Users size={14} /> Staff roster ({staff.length})</h3>
            <p className="text-[11px] mb-3" style={{ color: 'var(--theme-text-muted)' }}>
              Email is required so the supplier can reach the right person when a fault is logged from the gym floor.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-2">
              <Input value={form.newStaff} onChange={(e) => setForm({ ...form, newStaff: e.target.value })} placeholder="Full name" data-testid="gym-floor-new-staff" />
              <Input type="email" value={form.newStaffEmail} onChange={(e) => setForm({ ...form, newStaffEmail: e.target.value })} placeholder="Email *" data-testid="gym-floor-new-staff-email" />
              <Input value={form.newStaffMobile} onChange={(e) => setForm({ ...form, newStaffMobile: e.target.value })} placeholder="Mobile (optional)" data-testid="gym-floor-new-staff-mobile" />
            </div>
            <Button onClick={addStaff} size="sm" className="w-full mb-3 rounded-full bg-[var(--color-brand-blue)] text-white" data-testid="gym-floor-add-staff">
              <Plus size={13} className="mr-1" /> Add staff member
            </Button>
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {staff.map((s) => (
                <div key={s.id} className="px-3 py-2 rounded-lg" style={{ background: 'var(--theme-bg)' }}>
                  {editingStaffId === s.id ? (
                    <div className="space-y-1.5" data-testid={`gym-floor-edit-staff-${s.id}`}>
                      <Input className="h-8 text-sm" value={staffEdit.name} onChange={(e) => setStaffEdit({ ...staffEdit, name: e.target.value })} placeholder="Name" />
                      <Input className="h-8 text-sm" value={staffEdit.email} onChange={(e) => setStaffEdit({ ...staffEdit, email: e.target.value })} placeholder="Email" />
                      <Input className="h-8 text-sm" value={staffEdit.mobile} onChange={(e) => setStaffEdit({ ...staffEdit, mobile: e.target.value })} placeholder="Mobile (optional)" />
                      <div className="flex gap-2 pt-1">
                        <Button size="sm" onClick={saveStaffEdit} className="flex-1 h-8 rounded-full bg-[var(--color-brand-blue)] text-white text-xs" data-testid={`gym-floor-save-staff-${s.id}`}>Save</Button>
                        <Button size="sm" variant="outline" onClick={() => setEditingStaffId(null)} className="flex-1 h-8 rounded-full text-xs">Cancel</Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{s.name}</p>
                        <p className="text-[11px] truncate" style={{ color: 'var(--theme-text-muted)' }}>
                          {s.email || <span className="text-amber-600 dark:text-amber-400">⚠ no email</span>}
                          {s.mobile ? ` · ${s.mobile}` : ''}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button onClick={() => startEditStaff(s)} className="text-[var(--color-brand-blue)] hover:underline text-[11px] font-semibold" data-testid={`gym-floor-edit-staff-btn-${s.id}`}>Edit</button>
                        <button onClick={() => removeStaff(s)} className="text-red-500 hover:text-red-700" data-testid={`gym-floor-remove-staff-${s.id}`}><Trash2 size={12} /></button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
              {staff.length === 0 && <p className="text-xs text-center py-3" style={{ color: 'var(--theme-text-muted)' }}>Add your first staff member.</p>}
            </div>
          </Card>

          <Card className="lg:col-span-2 p-5 rounded-xl" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><Tag size={14} /> Topics ({topics.length})</h3>
            <div className="flex gap-2 mb-3">
              <Input value={form.newTopic} onChange={(e) => setForm({ ...form, newTopic: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTopic())} placeholder="e.g. Pool maintenance…" data-testid="gym-floor-new-topic" />
              <Button onClick={addTopic} size="sm" className="rounded-full bg-[var(--color-brand-blue)] text-white" data-testid="gym-floor-add-topic"><Plus size={13} /></Button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {topics.map((t) => (
                <span key={t.id} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }}>
                  {t.label}
                  <button onClick={() => removeTopic(t)} className="text-red-500 hover:text-red-700 ml-1" data-testid={`gym-floor-remove-topic-${t.id}`}><Trash2 size={10} /></button>
                </span>
              ))}
            </div>
          </Card>
        </div>
      )}

      {panel === 'diary' && (
        <div className="space-y-3">
          {entries.length === 0 ? (
            <div className="p-8 text-center text-sm rounded-xl border" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>
              No diary entries yet. Once you've set up the shared login and staff sign in at <code>/gym-floor</code>, entries will appear here.
            </div>
          ) : entries.map((e) => (
            <Card key={e.id} className="p-5 rounded-xl" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid={`gym-floor-entry-${e.id}`}>
              <div className="flex items-center justify-between gap-3 mb-1.5">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[var(--color-brand-cyan)] grid place-items-center text-xs font-bold">
                    {(e.staff_name || '?').split(' ').map((p) => p[0]).join('').slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <p className="text-sm font-semibold">{e.staff_name}</p>
                    <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
                      {new Date(e.created_at).toLocaleString()} · {topicLabel(e.topic_id)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {e.flagged && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-500/20 text-amber-700 dark:text-amber-400" title={e.moderation?.reason}>
                      <ShieldAlert size={11} /> Flagged · {e.moderation?.severity || 'review'}
                    </span>
                  )}
                  {isManager && (
                    <button onClick={() => removeEntry(e)} className="text-red-500 hover:text-red-700" data-testid={`gym-floor-delete-${e.id}`}>
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              </div>
              <p className="text-sm whitespace-pre-wrap leading-relaxed" style={{ color: 'var(--theme-text)' }}>{e.notes}</p>
              {e.moderation?.reason && (
                <p className="text-[11px] mt-2 text-amber-700 dark:text-amber-400">⚠ Moderation note: {e.moderation.reason}</p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default GymFloorManagerTab;
