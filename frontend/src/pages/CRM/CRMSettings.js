import { useState, useEffect, useCallback, useRef } from 'react';
import { useCRM } from './CRMApp';
import {
  Upload, FileSpreadsheet, Shield, Clock, User, ChevronRight, Loader2,
  CheckCircle, AlertTriangle, Link2, RefreshCw, ArrowLeftRight, UserPlus, Copy, Trash2, X, Lock, Key, Smartphone, Edit2, Ban, Package
} from 'lucide-react';
import axios from 'axios';
import CRMPermissions from './CRMPermissions';
import CRMPicklistsSection from './CRMPicklistsSection';
import CRMProductsSection from './CRMProductsSection';

const ROLE_COLORS = { owner: 'var(--color-accent-amber)', admin: 'var(--color-danger-alt)', manager: 'var(--color-info-ios)', sales_rep: 'var(--color-success-alt)' };

function TeamSection({ API, headers, user, c, isDark }) {
  const [crmUsers, setCrmUsers] = useState([]);
  const [showInvite, setShowInvite] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: '', full_name: '', role: 'sales_rep' });
  const [inviting, setInviting] = useState(false);
  const [inviteResult, setInviteResult] = useState(null);
  const [showEdit, setShowEdit] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [savingEdit, setSavingEdit] = useState(false);
  const canManage = ['admin', 'owner', 'manager'].includes(user.role);

  const fetchUsers = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/users`, { headers: headers() });
      setCrmUsers(res.data.users);
    } catch (e) { console.error(e); }
  }, [API, headers]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleInvite = async (e) => {
    e.preventDefault();
    setInviting(true); setInviteResult(null);
    try {
      const res = await axios.post(`${API}/crm/users/invite`, inviteForm, { headers: headers() });
      setInviteResult(res.data);
      setInviteForm({ email: '', full_name: '', role: 'sales_rep' });
      fetchUsers();
    } catch (err) {
      setInviteResult({ error: err.response?.data?.detail || 'Failed to invite' });
    }
    setInviting(false);
  };

  const handleRemove = async (userId) => {
    if (!window.confirm('Remove this team member? This cannot be undone.')) return;
    try { await axios.delete(`${API}/crm/users/${userId}`, { headers: headers() }); fetchUsers(); } catch (e) { alert(e.response?.data?.detail || 'Failed to remove'); }
  };

  const openEdit = (u) => {
    setEditForm({ full_name: u.full_name || '', email: u.email || '', role: u.role || 'sales_rep', status: u.status || 'active' });
    setShowEdit(u);
  };

  const handleSaveEdit = async () => {
    setSavingEdit(true);
    try {
      await axios.put(`${API}/crm/users/${showEdit.id}`, editForm, { headers: headers() });
      setShowEdit(null);
      fetchUsers();
    } catch (e) { alert(e.response?.data?.detail || 'Failed to update'); }
    setSavingEdit(false);
  };

  // Determine what the current user can edit
  const canEditUser = (target) => {
    if (!canManage) return false;
    if (target.id === user.id) return false;
    if (target.role === 'owner') return false;
    if (user.role === 'manager' && target.role !== 'sales_rep') return false;
    return true;
  };

  return (
    <div className="rounded-lg border p-5" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="crm-team-section">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold" style={{ color: c.text }}>Team Members ({crmUsers.length})</h3>
        {canManage && (
          <button onClick={() => { setShowInvite(true); setInviteResult(null); }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md" data-testid="team-invite-btn">
            <UserPlus size={12} /> Invite
          </button>
        )}
      </div>
      <div className="space-y-2">
        {crmUsers.map(u => {
          const roleColor = ROLE_COLORS[u.role] || 'var(--color-text-faint-alt)';
          const isInactive = u.status === 'inactive';
          return (
            <div key={u.id} className={`flex items-center justify-between p-3 rounded-md border ${isInactive ? 'opacity-50' : ''}`} style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`team-member-${u.id}`}>
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: `${roleColor}15`, color: roleColor }}>
                  {u.full_name?.charAt(0)?.toUpperCase()}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium" style={{ color: c.text }}>{u.full_name}</p>
                    {u.id === user.id && <span className="text-[9px] px-1.5 py-0.5 rounded bg-[rgb(var(--rgb-info-ios)/0.1)] text-[var(--color-info-ios)] font-medium">You</span>}
                    {isInactive && <span className="text-[9px] px-1.5 py-0.5 rounded bg-[rgb(var(--rgb-danger-alt)/0.1)] text-[var(--color-danger-alt)] font-medium">Inactive</span>}
                  </div>
                  <p className="text-[11px]" style={{ color: c.textDim }}>{u.email}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded" style={{ background: `${roleColor}12`, color: roleColor }}>{u.role?.replace('_', ' ')}</span>
                {canEditUser(u) && (
                  <>
                    <button onClick={() => openEdit(u)} className="p-1 rounded hover:bg-black/5" style={{ color: c.textDim }} data-testid={`edit-user-${u.id}`} title="Edit"><Edit2 size={12} /></button>
                    <button onClick={() => handleRemove(u.id)} className="p-1 rounded hover:bg-[rgb(var(--rgb-danger-alt)/0.1)]" style={{ color: 'var(--color-danger-alt)' }} data-testid={`delete-user-${u.id}`} title="Remove"><Trash2 size={12} /></button>
                  </>
                )}
              </div>
            </div>
          );
        })}
        {crmUsers.length === 0 && <p className="text-sm text-center py-4" style={{ color: c.textDim }}>No team members</p>}
      </div>

      {/* Edit User Dialog */}
      {showEdit && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowEdit(null)}>
          <div className="w-full max-w-md mx-4 rounded-xl p-6 shadow-2xl" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="edit-user-dialog">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>Edit Team Member</h2>
              <button onClick={() => setShowEdit(null)} className="p-1" style={{ color: c.textDim }}><X size={16} /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Full Name</label>
                <input value={editForm.full_name} onChange={e => setEditForm({ ...editForm, full_name: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="edit-user-name" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Email</label>
                <input type="email" value={editForm.email} onChange={e => setEditForm({ ...editForm, email: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="edit-user-email" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Role</label>
                <select value={editForm.role} onChange={e => setEditForm({ ...editForm, role: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="edit-user-role"
                  disabled={showEdit.role === 'owner'}>
                  <option value="sales_rep">Sales Rep</option>
                  <option value="manager">Manager</option>
                  {user.role === 'owner' && <option value="admin">Admin</option>}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Status</label>
                <div className="flex gap-2 mt-1">
                  {['active', 'inactive'].map(s => (
                    <button key={s} type="button" onClick={() => setEditForm({ ...editForm, status: s })}
                      className={`flex-1 px-3 py-2 text-xs font-medium rounded-md capitalize ${editForm.status === s ? '' : ''}`}
                      style={editForm.status === s
                        ? { background: s === 'active' ? 'var(--color-success-alt)15' : 'var(--color-danger-alt)15', color: s === 'active' ? 'var(--color-success-alt)' : 'var(--color-danger-alt)', border: `1px solid ${s === 'active' ? 'var(--color-success-alt)40' : 'var(--color-danger-alt)40'}` }
                        : { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted, border: '1px solid transparent' }
                      } data-testid={`edit-user-status-${s}`}>
                      {s === 'active' ? <><CheckCircle size={11} className="inline mr-1" />{s}</> : <><Ban size={11} className="inline mr-1" />{s}</>}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex gap-2 mt-5 justify-end">
              <button onClick={() => setShowEdit(null)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleSaveEdit} disabled={savingEdit} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="save-user-edit-btn">
                {savingEdit ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showInvite && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowInvite(false)}>
          <div className="w-full max-w-md mx-4 rounded-xl p-6 shadow-2xl" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="team-invite-dialog">
            <h2 className="text-lg font-semibold mb-4" style={{ color: c.text }}>Invite Team Member</h2>
            <form onSubmit={handleInvite} className="space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Full Name</label>
                <input value={inviteForm.full_name} onChange={e => setInviteForm({ ...inviteForm, full_name: e.target.value })} required
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Email</label>
                <input type="email" value={inviteForm.email} onChange={e => setInviteForm({ ...inviteForm, email: e.target.value })} required
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Role</label>
                <select value={inviteForm.role} onChange={e => setInviteForm({ ...inviteForm, role: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  <option value="sales_rep">Sales Rep</option>
                  <option value="manager">Manager</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              {inviteResult && !inviteResult.error && (
                <div className="p-3 rounded-md" style={{ background: 'var(--color-success-alt)10', border: '1px solid var(--color-success-alt)20' }}>
                  <p className="text-sm font-medium" style={{ color: 'var(--color-success-alt)' }}>Invited: {inviteResult.full_name}</p>
                  <div className="flex items-center gap-2 mt-1 text-xs" style={{ color: c.textDim }}>
                    <span>Temp password:</span>
                    <code className="px-2 py-0.5 rounded text-xs font-mono" style={{ background: isDark ? 'var(--color-ink-alt)' : 'var(--color-neutral-100)', color: c.text }}>{inviteResult.temp_password}</code>
                    <button type="button" onClick={() => navigator.clipboard.writeText(inviteResult.temp_password)} style={{ color: 'var(--color-info-ios)' }}><Copy size={12} /></button>
                  </div>
                </div>
              )}
              {inviteResult?.error && (
                <div className="p-3 rounded-md text-sm" style={{ background: 'var(--color-danger-alt)10', border: '1px solid var(--color-danger-alt)20', color: 'var(--color-danger-alt)' }}>
                  {inviteResult.error}
                </div>
              )}
              <div className="flex gap-2 justify-end pt-2">
                <button type="button" onClick={() => setShowInvite(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
                <button type="submit" disabled={inviting} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50">
                  {inviting ? 'Inviting...' : 'Invite'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function SecuritySection({ API, headers, user, c, isDark }) {
  const [twoFAStatus, setTwoFAStatus] = useState(null);
  const [setupData, setSetupData] = useState(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [disablePassword, setDisablePassword] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [message, setMessage] = useState(null);

  const loadStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/auth/2fa/status`, { headers: headers() });
      setTwoFAStatus(res.data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [API, headers]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const startSetup = async () => {
    setActionLoading(true); setMessage(null);
    try {
      const res = await axios.post(`${API}/crm/auth/2fa/setup`, {}, { headers: headers() });
      setSetupData(res.data);
    } catch (e) { setMessage({ type: 'error', text: 'Failed to start setup' }); }
    setActionLoading(false);
  };

  const verifySetup = async () => {
    setActionLoading(true); setMessage(null);
    try {
      await axios.post(`${API}/crm/auth/2fa/verify-setup`, { code: verifyCode }, { headers: headers() });
      setMessage({ type: 'success', text: '2FA enabled successfully!' });
      setSetupData(null); setVerifyCode('');
      loadStatus();
    } catch (e) { setMessage({ type: 'error', text: e.response?.data?.detail || 'Invalid code' }); }
    setActionLoading(false);
  };

  const disable2FA = async () => {
    setActionLoading(true); setMessage(null);
    try {
      await axios.post(`${API}/crm/auth/2fa/disable`, { password: disablePassword }, { headers: headers() });
      setMessage({ type: 'success', text: '2FA disabled' });
      setDisablePassword('');
      loadStatus();
    } catch (e) { setMessage({ type: 'error', text: e.response?.data?.detail || 'Invalid password' }); }
    setActionLoading(false);
  };

  if (loading) return <div className="flex justify-center py-8"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="rounded-lg border p-5" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="crm-security-section">
      <div className="flex items-center gap-2 mb-1">
        <Lock size={16} style={{ color: 'var(--color-info-ios)' }} />
        <h3 className="text-sm font-semibold" style={{ color: c.text }}>Two-Factor Authentication</h3>
      </div>
      <p className="text-xs mb-5" style={{ color: c.textDim }}>Add an extra layer of security to your account using an authenticator app</p>

      {message && (
        <div className="mb-4 px-3 py-2 rounded-md text-sm" style={{ background: message.type === 'success' ? 'var(--color-success-alt)10' : 'var(--color-danger-alt)10', border: `1px solid ${message.type === 'success' ? 'var(--color-success-alt)20' : 'var(--color-danger-alt)20'}`, color: message.type === 'success' ? 'var(--color-success-alt)' : 'var(--color-danger-alt)' }}>
          {message.type === 'success' ? <CheckCircle size={12} className="inline mr-1" /> : <AlertTriangle size={12} className="inline mr-1" />}
          {message.text}
        </div>
      )}

      {/* Current status */}
      <div className="flex items-center gap-3 p-4 rounded-lg mb-4" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', border: `1px solid ${twoFAStatus?.enabled ? 'var(--color-success-alt)30' : (isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)')}` }}>
        <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: twoFAStatus?.enabled ? 'var(--color-success-alt)15' : 'var(--color-accent-amber)15' }}>
          <Smartphone size={20} style={{ color: twoFAStatus?.enabled ? 'var(--color-success-alt)' : 'var(--color-accent-amber)' }} />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium" style={{ color: c.text }}>{twoFAStatus?.enabled ? '2FA is enabled' : '2FA is not enabled'}</p>
          <p className="text-[11px]" style={{ color: c.textDim }}>{twoFAStatus?.enabled ? 'Your account is protected with TOTP authentication' : 'Enable 2FA for enhanced security'}</p>
        </div>
        <span className="text-[9px] font-bold uppercase px-2 py-1 rounded" style={{ background: twoFAStatus?.enabled ? 'var(--color-success-alt)20' : 'var(--color-accent-amber)20', color: twoFAStatus?.enabled ? 'var(--color-success-alt)' : 'var(--color-accent-amber)' }}>
          {twoFAStatus?.enabled ? 'Active' : 'Inactive'}
        </span>
      </div>

      {/* Setup flow */}
      {!twoFAStatus?.enabled && !setupData && (
        <button onClick={startSetup} disabled={actionLoading}
          className="flex items-center gap-2 px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="enable-2fa-btn">
          {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
          Enable 2FA
        </button>
      )}

      {setupData && (
        <div className="space-y-4" data-testid="2fa-setup-flow">
          <div className="flex flex-col items-center p-4 rounded-lg" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', border: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }}>
            <p className="text-xs font-medium mb-3" style={{ color: c.text }}>Scan this QR code with your authenticator app</p>
            <img src={setupData.qr_code} alt="2FA QR Code" className="w-40 h-40 rounded-lg" />
            <div className="mt-3 w-full">
              <p className="text-[10px] uppercase tracking-wider text-center" style={{ color: c.textDim }}>Manual key</p>
              <div className="flex items-center justify-center gap-2 mt-1">
                <code className="text-xs font-mono px-2 py-1 rounded" style={{ background: isDark ? 'var(--color-ink-alt)' : 'var(--color-neutral-100)', color: c.text }}>{setupData.secret}</code>
                <button onClick={() => navigator.clipboard.writeText(setupData.secret)} style={{ color: 'var(--color-info-ios)' }}><Copy size={12} /></button>
              </div>
            </div>
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Enter verification code</label>
            <input type="text" value={verifyCode} onChange={e => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="000000" className="w-full mt-1 px-3 py-2 text-sm font-mono text-center tracking-widest rounded-md"
              style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
              data-testid="2fa-verify-input" />
          </div>

          <div className="flex gap-2">
            <button onClick={() => setSetupData(null)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
            <button onClick={verifySetup} disabled={actionLoading || verifyCode.length < 6}
              className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="2fa-confirm-btn">
              {actionLoading ? 'Verifying...' : 'Verify & Enable'}
            </button>
          </div>

          {/* Backup codes */}
          <div className="p-3 rounded-lg" style={{ background: 'var(--color-accent-amber)10', border: '1px solid var(--color-accent-amber)20' }}>
            <div className="flex items-center gap-2 mb-2">
              <Key size={12} style={{ color: 'var(--color-accent-amber)' }} />
              <span className="text-xs font-medium" style={{ color: 'var(--color-accent-amber)' }}>Backup Codes — Save these!</span>
            </div>
            <div className="grid grid-cols-4 gap-1.5">
              {setupData.backup_codes.map((code, i) => (
                <code key={i} className="text-[11px] font-mono text-center py-1 rounded" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', color: c.text }}>{code}</code>
              ))}
            </div>
            <p className="text-[10px] mt-2" style={{ color: c.textDim }}>Each backup code can only be used once. Store them securely.</p>
          </div>
        </div>
      )}

      {/* Disable flow */}
      {twoFAStatus?.enabled && (
        <div className="mt-4 pt-4" style={{ borderTop: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }}>
          <p className="text-xs font-medium mb-2" style={{ color: c.text }}>Disable 2FA</p>
          <div className="flex gap-2">
            <input type="password" value={disablePassword} onChange={e => setDisablePassword(e.target.value)}
              placeholder="Enter your password to disable"
              className="flex-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
              data-testid="2fa-disable-password" />
            <button onClick={disable2FA} disabled={actionLoading || !disablePassword}
              className="px-4 py-2 text-sm font-medium rounded-md border disabled:opacity-50" style={{ borderColor: 'var(--color-danger-alt)30', color: 'var(--color-danger-alt)' }}
              data-testid="disable-2fa-btn">
              {actionLoading ? 'Disabling...' : 'Disable'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function CRMSettings() {
  const { API, headers, user, c, isDark } = useCRM();
  const [activeSection, setActiveSection] = useState('import');
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef(null);

  // Sage 200
  const [sageConfig, setSageConfig] = useState(null);
  const [sageLoading, setSageLoading] = useState(false);
  const [sageSaving, setSageSaving] = useState(false);
  const [sageSyncing, setSageSyncing] = useState(null);
  const [sageSyncResult, setSageSyncResult] = useState(null);
  const [sageForm, setSageForm] = useState({ edition: 'standard', client_id: '', client_secret: '', site_id: '', company_id: '', company_name: '' });

  const fetchAuditLogs = useCallback(async () => {
    setAuditLoading(true);
    try {
      const res = await axios.get(`${API}/crm/audit-log`, { headers: headers(), params: { limit: 50 } });
      setAuditLogs(res.data.logs);
    } catch (e) { console.error(e); }
    setAuditLoading(false);
  }, [API, headers]);

  const fetchSageConfig = useCallback(async () => {
    setSageLoading(true);
    try {
      const res = await axios.get(`${API}/crm/sage200/config`, { headers: headers() });
      setSageConfig(res.data);
      if (res.data.configured) {
        setSageForm(prev => ({ ...prev, edition: res.data.edition || 'standard', site_id: res.data.site_id || '', company_id: res.data.company_id || '', company_name: res.data.company_name || '' }));
      }
    } catch (e) { console.error(e); }
    setSageLoading(false);
  }, [API, headers]);

  useEffect(() => {
    if (activeSection === 'audit') fetchAuditLogs();
    if (activeSection === 'sage200') fetchSageConfig();
  }, [activeSection, fetchAuditLogs, fetchSageConfig]);

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true); setImportResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await axios.post(`${API}/crm/import/contacts`, formData, { headers: { ...headers(), 'Content-Type': 'multipart/form-data' } });
      setImportResult(res.data);
    } catch (err) {
      setImportResult({ error: err.response?.data?.detail || 'Import failed' });
    }
    setImporting(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  const saveSageConfig = async (e) => {
    e.preventDefault();
    setSageSaving(true);
    try { await axios.post(`${API}/crm/sage200/config`, sageForm, { headers: headers() }); await fetchSageConfig(); } catch (e) { console.error(e); }
    setSageSaving(false);
  };

  const runSageSync = async (direction) => {
    setSageSyncing(direction); setSageSyncResult(null);
    try {
      const endpoint = direction === 'pull' ? '/crm/sage200/sync/customers' : '/crm/sage200/sync/customers-to-sage';
      const res = await axios.post(`${API}${endpoint}`, {}, { headers: headers() });
      setSageSyncResult({ direction, ...res.data }); await fetchSageConfig();
    } catch (err) { setSageSyncResult({ direction, error: err.response?.data?.detail || 'Sync failed' }); }
    setSageSyncing(null);
  };

  const sections = [
    { id: 'import', label: 'Data Import', icon: Upload },
    { id: 'team', label: 'Team', icon: User },
    { id: 'permissions', label: 'Permissions', icon: Lock, jumpTo: 'permissions' },
    { id: 'picklists', label: 'Picklists', icon: Edit2 },
    { id: 'products', label: 'Price List', icon: Package },
    { id: 'security', label: 'Security', icon: Lock },
    { id: 'sage200', label: 'Sage 200', icon: Link2 },
    { id: 'audit', label: 'Audit Log', icon: Shield },
  ];

  return (
    <div data-testid="crm-settings">
      <div className="mb-5">
        <h1 className="text-xl font-bold tracking-tight" style={{ color: c.text }}>Settings</h1>
        <p className="text-xs mt-0.5" style={{ color: c.textDim }}>Configure your CRM workspace</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
        {/* Sidebar */}
        <div className="space-y-1">
          {sections.map(s => {
            const Icon = s.icon;
            const active = activeSection === s.id;
            return (
              <button key={s.id} onClick={() => setActiveSection(s.id)}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm rounded-md transition-all"
                style={{
                  background: active ? 'rgba(0,122,255,0.1)' : 'transparent',
                  color: active ? 'var(--color-info-ios)' : c.textMuted,
                }}
                data-testid={`settings-tab-${s.id}`}>
                <Icon size={16} /> {s.label} <ChevronRight size={14} className="ml-auto opacity-40" />
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div className="lg:col-span-3">
          {/* Import */}
          {activeSection === 'import' && (
            <div className="rounded-lg border p-5" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="settings-import">
              <h3 className="text-sm font-semibold mb-1" style={{ color: c.text }}>Data Import</h3>
              <p className="text-xs mb-5" style={{ color: c.textDim }}>Import contacts from CSV files</p>
              <div className="border-2 border-dashed rounded-lg p-8 text-center" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <FileSpreadsheet size={28} className="mx-auto mb-3" style={{ color: c.textDim }} />
                <p className="text-sm mb-3" style={{ color: c.textMuted }}>Upload a CSV file with contact data</p>
                <input type="file" accept=".csv" onChange={handleImport} ref={fileRef} className="hidden" id="csv-upload" data-testid="import-file-input" />
                <label htmlFor="csv-upload" className="inline-flex items-center gap-2 px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md cursor-pointer hover:bg-[var(--color-brand-blue-deep)]">
                  {importing ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                  {importing ? 'Importing...' : 'Select CSV'}
                </label>
              </div>
              {importResult && (
                <div className="mt-4 p-3 rounded-md" style={{ background: importResult.error ? 'var(--color-danger-alt)10' : 'var(--color-success-alt)10', border: `1px solid ${importResult.error ? 'var(--color-danger-alt)20' : 'var(--color-success-alt)20'}` }} data-testid="import-result">
                  {importResult.error ? (
                    <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-danger-alt)' }}><AlertTriangle size={14} />{importResult.error}</div>
                  ) : (
                    <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-success-alt)' }}><CheckCircle size={14} />{importResult.imported} imported</div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Team */}
          {activeSection === 'team' && (
            <TeamSection API={API} headers={headers} user={user} c={c} isDark={isDark} />
          )}

          {/* Permissions */}
          {activeSection === 'permissions' && (
            <CRMPermissions />
          )}

          {/* Picklists — Iter 216h223 */}
          {activeSection === 'picklists' && (
            <CRMPicklistsSection API={API} headers={headers} user={user} c={c} isDark={isDark} />
          )}

          {/* Products / Master Price List — Iter 216h224 */}
          {activeSection === 'products' && (
            <CRMProductsSection API={API} headers={headers} c={c} isDark={isDark} />
          )}

          {/* Security / 2FA */}
          {activeSection === 'security' && (
            <SecuritySection API={API} headers={headers} user={user} c={c} isDark={isDark} />
          )}

          {/* Sage 200 */}
          {activeSection === 'sage200' && (
            <div className="rounded-lg border p-5" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="settings-sage200">
              <h3 className="text-sm font-semibold mb-1" style={{ color: c.text }}>Sage 200 Integration</h3>
              <p className="text-xs mb-5" style={{ color: c.textDim }}>Bi-directional sync with your accounting system</p>
              {sageLoading ? (
                <div className="flex justify-center py-8"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>
              ) : (
                <form onSubmit={saveSageConfig} className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Edition</label>
                      <select value={sageForm.edition} onChange={e => setSageForm({ ...sageForm, edition: e.target.value })}
                        className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                        <option value="standard">Sage 200 Standard</option>
                        <option value="professional">Sage 200 Professional</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Company Name</label>
                      <input value={sageForm.company_name} onChange={e => setSageForm({ ...sageForm, company_name: e.target.value })}
                        className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Client ID</label>
                      <input value={sageForm.client_id} onChange={e => setSageForm({ ...sageForm, client_id: e.target.value })} placeholder="Sage API Client ID"
                        className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    </div>
                    <div>
                      <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Client Secret</label>
                      <input type="password" value={sageForm.client_secret} onChange={e => setSageForm({ ...sageForm, client_secret: e.target.value })}
                        className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                    </div>
                  </div>
                  <button type="submit" disabled={sageSaving} className="flex items-center gap-2 px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50">
                    {sageSaving ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle size={14} />}
                    {sageSaving ? 'Saving...' : 'Save Configuration'}
                  </button>
                </form>
              )}
              {sageConfig?.configured && (
                <div className="mt-5 pt-5" style={{ borderTop: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }}>
                  <p className="text-xs font-medium mb-3" style={{ color: c.text }}>Sync Actions</p>
                  <div className="flex gap-2">
                    <button onClick={() => runSageSync('pull')} disabled={sageSyncing}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.textMuted }}>
                      {sageSyncing === 'pull' ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />} Pull from Sage
                    </button>
                    <button onClick={() => runSageSync('push')} disabled={sageSyncing}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.textMuted }}>
                      {sageSyncing === 'push' ? <Loader2 size={12} className="animate-spin" /> : <ArrowLeftRight size={12} />} Push to Sage
                    </button>
                  </div>
                  {sageSyncResult && (
                    <div className="mt-3 p-3 rounded-md text-sm" style={{ background: sageSyncResult.error ? 'var(--color-danger-alt)10' : 'var(--color-success-alt)10', border: `1px solid ${sageSyncResult.error ? 'var(--color-danger-alt)20' : 'var(--color-success-alt)20'}` }}>
                      {sageSyncResult.error ? (
                        <span style={{ color: 'var(--color-danger-alt)' }}>{sageSyncResult.error}</span>
                      ) : (
                        <span style={{ color: 'var(--color-success-alt)' }}>
                          <CheckCircle size={12} className="inline mr-1" />
                          {sageSyncResult.direction === 'pull' ? `${sageSyncResult.created || 0} created, ${sageSyncResult.updated || 0} updated` : `${sageSyncResult.pushed || 0} pushed`}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Audit Log */}
          {activeSection === 'audit' && (
            <div className="rounded-lg border p-5" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="settings-audit">
              <h3 className="text-sm font-semibold mb-4" style={{ color: c.text }}>Audit Log</h3>
              {auditLoading ? (
                <div className="flex justify-center py-8"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>
              ) : auditLogs.length === 0 ? (
                <p className="text-sm text-center py-6" style={{ color: c.textDim }}>No audit entries</p>
              ) : (
                <div className="space-y-2 max-h-[500px] overflow-y-auto">
                  {auditLogs.map(log => (
                    <div key={log.id} className="flex items-start gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                      <Clock size={14} className="mt-0.5 shrink-0" style={{ color: c.textDim }} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm" style={{ color: c.text }}>
                          <span className="font-medium">{log.user_name}</span>{' '}
                          <span style={{ color: c.textMuted }}>{log.action}</span>{' '}
                          <span style={{ color: 'var(--color-info-ios)' }}>{log.entity_type}</span>
                        </p>
                        <p className="text-[10px] mt-0.5" style={{ color: c.textDim }}>{new Date(log.created_at).toLocaleString()}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
