import { useState, useEffect } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
  Users, UserPlus, Copy, Crown, Shield, User, Trash2, Building,
  Mail, Save, Clock, X, Loader2, MapPin, QrCode, Printer, Plus, Edit, Settings2, Palette, ChevronDown, ChevronUp, Star
} from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import FaultTemplatesManager from './Dashboard/FaultTemplatesManager';
import SiteModulesOverride from '@/components/sites/SiteModulesOverride';
import SiteBrandingOverride from '@/components/sites/SiteBrandingOverride';
import LaunchReadinessPanel from '@/components/shared/LaunchReadinessPanel';
import SiteDataExportPanel from './SiteDataExportPanel';

const PulseSettingsTab = () => {
  const { user, API, sites: _globalSites, _setActiveSite, refreshSites } = useAuth();
  const [organization, setOrganization] = useState(null);
  const [staff, setStaff] = useState([]);
  const [invites, setInvites] = useState([]);
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: '', role: 'staff', full_name: '' });
  const [inviting, setInviting] = useState(false);
  const [orgAddress, setOrgAddress] = useState('');
  const [orgPhone, setOrgPhone] = useState('');
  const [orgEmail, setOrgEmail] = useState('');
  const [orgContactPerson, setOrgContactPerson] = useState('');
  const [savingOrg, setSavingOrg] = useState(false);
  const [settingsSection, setSettingsSection] = useState('team');
  const [equipmentList, setEquipmentList] = useState([]);
  const [selectedQRIds, setSelectedQRIds] = useState(new Set());
  const [sitesList, setSitesList] = useState([]);
  const [showAddSite, setShowAddSite] = useState(false);
  const [siteForm, setSiteForm] = useState({ name: '', address: '', postcode: '', is_head_office: false });
  const [savingSite, setSavingSite] = useState(false);
  const [editingSiteId, setEditingSiteId] = useState(null);
  const [moduleOverridesOpen, setModuleOverridesOpen] = useState({});
  const [brandingOverridesOpen, setBrandingOverridesOpen] = useState({});
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  useEffect(() => { loadData(); loadEquipment(); loadSites(); }, []);

  const loadSites = async () => {
    try {
      const res = await axios.get(`${API}/sites`, { headers });
      setSitesList(res.data?.sites || []);
      if (refreshSites) refreshSites();
    } catch { /* ignore */ }
  };

  const loadData = async () => {
    try {
      const [orgRes, staffRes, invitesRes, orgDetailsRes] = await Promise.all([
        axios.get(`${API}/organization`, { headers }),
        user.role !== 'staff' ? axios.get(`${API}/organization/staff`, { headers }) : Promise.resolve({ data: { staff: [] } }),
        user.role !== 'staff' ? axios.get(`${API}/organization/invites`, { headers }) : Promise.resolve({ data: { invites: [] } }),
        axios.get(`${API}/settings/org-details`, { headers }).catch(() => ({ data: {} }))
      ]);
      setOrganization(orgRes.data);
      setStaff(staffRes.data?.staff || []);
      setInvites(invitesRes.data?.invites || []);
      const od = orgDetailsRes.data || {};
      setOrgAddress(od.address || '');
      setOrgPhone(od.phone || '');
      setOrgEmail(od.email || '');
      setOrgContactPerson(od.contact_person || '');
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const handleInvite = async (e) => {
    e.preventDefault();
    if (!inviteForm.email || !inviteForm.full_name) { notify.error('Name and email required'); return; }
    setInviting(true);
    try {
      await axios.post(`${API}/organization/invite`, inviteForm, { headers });
      notify.success(`Invite sent to ${inviteForm.email}`);
      setInviteForm({ email: '', role: 'staff', full_name: '' });
      setShowInviteForm(false);
      loadData();
    } catch (e) { notifyApiError(notify, e, 'Failed to send invite'); }
    setInviting(false);
  };

  const handleCopyCode = () => {
    navigator.clipboard.writeText(organization?.company_code || '');
    notify.success('Company code copied!');
  };

  const loadEquipment = async () => {
    try {
      const res = await axios.get(`${API}/equipment`, { headers });
      const eq = res.data?.equipment || [];
      setEquipmentList(eq);
      setSelectedQRIds(new Set(eq.map(e => e.id)));
    } catch { /* ignore */ }
  };

  const toggleQR = (id) => {
    setSelectedQRIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handlePrintQRCodes = () => {
    const selected = equipmentList.filter(e => selectedQRIds.has(e.id));
    if (!selected.length) { notify.error('Select at least one machine'); return; }
    const printWindow = window.open('', '_blank');
    if (!printWindow) return;
    const origin = window.location.origin;
    const logoUrl = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg';
    const rows = selected.map(eq => {
      const url = `${origin}/scan/${eq.id}`;
      const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(url)}`;
      const itemCode = eq.model || eq.equipment_type || '';
      const fullName = eq.name || 'Unknown';
      const name = fullName.includes(',') ? fullName.split(',')[0].trim() : (fullName.length > 35 ? fullName.slice(0, 35) + '...' : fullName);
      const serial = eq.serial_number || '';
      return `<div style="width:200px;text-align:center;page-break-inside:avoid;margin:8px;border:1px dashed #ccc;border-radius:8px;padding:10px 6px 8px;">
        <img src="${qrUrl}" width="140" height="140" style="display:block;margin:0 auto;" />
        <img src="${logoUrl}" width="70" style="display:block;margin:6px auto 2px;" />
        ${itemCode ? `<p style="font-size:11px;color:#000;margin:4px 0 0;font-family:sans-serif;font-weight:800;letter-spacing:0.3px;">${itemCode}</p>` : ''}
        <p style="font-size:9px;color:#000;margin:2px 0 0;font-family:sans-serif;font-weight:600;line-height:1.2;">${name}</p>
        ${serial ? `<p style="font-size:8px;color:#000;font-family:monospace;margin:3px 0 0;background:#f0f0f0;display:inline-block;padding:1px 6px;border-radius:3px;">S/N: ${serial}</p>` : ''}
      </div>`;
    }).join('');
    printWindow.document.write(`<!DOCTYPE html><html><head><title>QR Codes</title>
      <style>@media print{body{margin:0}}body{font-family:sans-serif}</style></head>
      <body><div style="display:flex;flex-wrap:wrap;justify-content:center;gap:4px;padding:12px;">${rows}</div>
      <script>setTimeout(()=>window.print(),1500)</script></body></html>`);
    printWindow.document.close();
  };

  const handleChangeRole = async (staffId, newRole) => {
    try {
      await axios.patch(`${API}/organization/staff/${staffId}/role?role=${newRole}`, {}, { headers });
      notify.success('Role updated');
      loadData();
    } catch { notify.error('Failed to update role'); }
  };

  const handleRemoveStaff = async (member) => {
    if (!window.confirm(`Remove ${member.full_name} from the team?`)) return;
    try {
      await axios.delete(`${API}/organization/staff/${member.id}`, { headers });
      notify.success('Member removed');
      loadData();
    } catch { notify.error('Failed to remove member'); }
  };

  const handleCancelInvite = async (inviteId) => {
    try {
      await axios.delete(`${API}/organization/invite/${inviteId}`, { headers });
      notify.success('Invite cancelled');
      loadData();
    } catch { notify.error('Failed to cancel invite'); }
  };

  const handleUpdatePermissions = async (staffId, patch) => {
    try {
      await axios.patch(`${API}/organization/staff/${staffId}/permissions`, patch, { headers });
      notify.success('Permissions updated');
      loadData();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to update permissions');
    }
  };

  const handleSaveOrgDetails = async () => {
    setSavingOrg(true);
    try {
      await axios.put(`${API}/settings/org-details`, {
        address: orgAddress, phone: orgPhone, email: orgEmail, contact_person: orgContactPerson
      }, { headers });
      notify.success('Organisation details saved');
    } catch { notify.error('Failed to save details'); }
    setSavingOrg(false);
  };

  const getRoleIcon = (role) => {
    if (role === 'owner') return <Crown className="text-yellow-400" size={16} />;
    if (role === 'manager') return <Shield className="text-blue-400" size={16} />;
    return <User className="text-[var(--color-text-muted)]" size={16} />;
  };

  const getRoleBadge = (role) => {
    if (role === 'owner') return 'bg-yellow-500/20 text-yellow-400';
    if (role === 'manager') return 'bg-blue-500/20 text-blue-400';
    return 'bg-gray-500/20 text-gray-400';
  };

  const sections = user.role === 'staff' ? ['org-details', 'templates'] : ['team', 'staff', 'sites', 'org-details', 'qr-codes', 'templates', 'data-export', 'launch'];

  const sectionLabels = {
    team: 'Team & Organisation', staff: 'Staff', sites: 'Sites', 'org-details': 'Organisation Details', 'qr-codes': 'QR Codes', templates: 'Fault Templates', 'data-export': 'Data export', launch: 'Launch readiness',
  };

  return (
    <div className="space-y-6" data-testid="pulse-settings-tab">
      <div>
        <h2 className="text-2xl font-semibold text-white">Settings</h2>
        <p className="text-[var(--color-text-muted)]">Manage your organisation and team</p>
      </div>

      <div className="flex items-center gap-2 border-b border-white/10 pb-4">
        {sections.map(s => {
          const active = settingsSection === s;
          return (
            <Button key={s} size="sm" variant="outline"
              className={`flex-shrink-0 ${active ? 'bg-[var(--pulse-primary-hover)] text-white border-transparent' : 'border-white/10 text-[var(--color-text-muted)]'}`}
              style={active ? { color: 'var(--color-white)' } : undefined}
              onClick={() => setSettingsSection(s)} data-testid={`pulse-settings-section-${s}`}>
              {sectionLabels[s] || s}
            </Button>
          );
        })}
      </div>

      {settingsSection === 'templates' && (
        <FaultTemplatesManager API={API} user={user} />
      )}

      {settingsSection === 'launch' && user.role !== 'staff' && (
        <div data-testid="pulse-settings-launch">
          <LaunchReadinessPanel />
        </div>
      )}

      {settingsSection === 'data-export' && user.role !== 'staff' && (
        <div data-testid="pulse-settings-data-export">
          <SiteDataExportPanel />
        </div>
      )}

      {/* Team Section */}
      {settingsSection === 'team' && user.role !== 'staff' && (
        <div className="space-y-6">
          {/* Org Info */}
          {organization && (
            <Card className="bg-[var(--color-surface-dark-alt)] border-white/10 p-6" data-testid="pulse-org-info">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2"><Building size={18} /> Organisation</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label className="text-[var(--color-text-muted)]">Organisation Name</Label>
                  <p className="text-white text-lg">{organization.name}</p>
                </div>
                <div>
                  <Label className="text-[var(--color-text-muted)]">Company Code</Label>
                  <div className="flex items-center gap-2 mt-1">
                    <code className="text-white text-lg font-mono bg-[var(--color-ink-alt)] px-3 py-1 rounded border border-white/10" data-testid="pulse-settings-company-code">
                      {organization.company_code}
                    </code>
                    <Button size="sm" variant="outline" onClick={handleCopyCode} className="border-white/10 text-[var(--color-text-muted)] hover:text-white" data-testid="pulse-settings-copy-code">
                      <Copy size={14} className="mr-1" /> Copy
                    </Button>
                  </div>
                  <p className="text-xs text-[var(--color-text-muted)] mt-1">Share this code with team members to join during signup</p>
                </div>
              </div>
            </Card>
          )}

          {/* Team Members */}
          <Card className="bg-[var(--color-surface-dark-alt)] border-white/10 p-6" data-testid="pulse-team-members-card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2"><Users size={18} /> Team Members</h3>
              {user.role === 'owner' && (
                <Button size="sm" onClick={() => setShowInviteForm(!showInviteForm)} className="bg-[var(--pulse-primary-hover)] hover:bg-[var(--pulse-primary-light)] text-white" data-testid="pulse-settings-invite-btn">
                  <UserPlus size={14} className="mr-1" /> Invite
                </Button>
              )}
            </div>

            {/* Invite Form */}
            {showInviteForm && (
              <form onSubmit={handleInvite} className="mb-4 p-4 rounded-lg bg-[var(--color-ink-alt)] border border-white/10 space-y-3" data-testid="pulse-invite-form">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <Input placeholder="Full name" value={inviteForm.full_name} onChange={e => setInviteForm({...inviteForm, full_name: e.target.value})} className="bg-[var(--color-surface-dark-alt)] border-white/10 text-white" data-testid="pulse-invite-name" />
                  <Input type="email" placeholder="Email address" value={inviteForm.email} onChange={e => setInviteForm({...inviteForm, email: e.target.value})} className="bg-[var(--color-surface-dark-alt)] border-white/10 text-white" data-testid="pulse-invite-email" />
                  <select value={inviteForm.role} onChange={e => setInviteForm({...inviteForm, role: e.target.value})} className="px-3 py-2 rounded-lg bg-[var(--color-surface-dark-alt)] border border-white/10 text-white text-sm" data-testid="pulse-invite-role">
                    <option value="staff">Staff</option>
                    <option value="manager">Manager</option>
                  </select>
                </div>
                <div className="flex gap-2">
                  <Button type="submit" disabled={inviting} className="bg-[var(--pulse-primary-hover)] hover:bg-[var(--pulse-primary-light)] text-white" data-testid="pulse-invite-submit">
                    {inviting ? <Loader2 size={14} className="animate-spin mr-1" /> : <Mail size={14} className="mr-1" />} Send Invite
                  </Button>
                  <Button type="button" variant="outline" onClick={() => setShowInviteForm(false)} className="border-white/10 text-[var(--color-text-muted)]">Cancel</Button>
                </div>
              </form>
            )}

            {/* Members List */}
            <div className="space-y-2">
              {staff.map(member => {
                const overrides = member.module_overrides || {};
                const canEditPerms = ['owner', 'manager'].includes(user.role)
                  && member.role !== 'owner'
                  && member.id !== user.id;
                return (
                <div key={member.id} className="rounded-lg bg-[var(--color-ink-alt)] border border-white/10" data-testid={`pulse-settings-member-${member.id}`}>
                  <div className="flex items-center gap-3 p-3">
                    <div className="w-9 h-9 rounded-full bg-[rgb(var(--rgb-pulse-primary-hover)/0.2)] flex items-center justify-center flex-shrink-0">
                      <span className="text-sm font-semibold text-[var(--pulse-primary-hover)]">{(member.full_name || '?')[0].toUpperCase()}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white">{member.full_name}</p>
                      <p className="text-xs text-[var(--color-text-muted)]">{member.email}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {getRoleIcon(member.role)}
                      {member.id === user?.id ? (
                        <Badge className="bg-[rgb(var(--rgb-pulse-primary-hover)/0.2)] text-[var(--pulse-primary-hover)] text-xs">You</Badge>
                      ) : user.role === 'owner' ? (
                        <>
                          <select value={member.role || 'staff'} onChange={e => handleChangeRole(member.id, e.target.value)}
                            className="text-xs border border-white/10 rounded px-2 py-1.5 bg-[var(--color-ink-alt)] text-white" data-testid={`pulse-settings-role-${member.id}`}>
                            <option value="staff">Staff</option>
                            <option value="manager">Manager</option>
                            <option value="owner">Owner</option>
                          </select>
                          <Button variant="outline" size="sm" className="border-red-500/30 text-red-400 hover:bg-red-500/10 h-7 px-2"
                            onClick={() => handleRemoveStaff(member)} data-testid={`pulse-settings-remove-${member.id}`}>
                            <Trash2 size={12} />
                          </Button>
                        </>
                      ) : (
                        <Badge className={`${getRoleBadge(member.role)} text-xs capitalize`}>{member.role}</Badge>
                      )}
                    </div>
                  </div>

                  {canEditPerms && (
                    <div className="border-t border-white/5 px-3 py-3 space-y-3" data-testid={`pulse-settings-perms-${member.id}`}>
                      <p className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-text-faint)]">Module access · per-staff overrides</p>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                        {[
                          { key: 'memberships', label: 'Memberships' },
                          { key: 'marketing',   label: 'Marketing' },
                          { key: 'crm',         label: 'CRM' },
                        ].map(mod => {
                          const enabled = mod.key in overrides ? !!overrides[mod.key] : true;
                          return (
                            <div key={mod.key} className="flex items-center justify-between p-2 bg-[var(--color-surface-dark-alt)] rounded-md border border-white/5">
                              <span className="text-xs text-white">{mod.label}</span>
                              <Switch
                                checked={enabled}
                                onCheckedChange={(val) => handleUpdatePermissions(member.id, {
                                  module_overrides: { ...overrides, [mod.key]: val },
                                })}
                                data-testid={`pulse-staff-${member.id}-mod-${mod.key}`}
                              />
                            </div>
                          );
                        })}
                      </div>
                      <div className="flex items-center justify-between p-2 bg-[var(--color-surface-dark-alt)] rounded-md border border-white/5">
                        <div>
                          <p className="text-xs text-white font-medium">Group Fitness timetable — view only</p>
                          <p className="text-[10px] text-[var(--color-text-muted)]">Blocks creating, editing or cancelling classes &amp; sessions.</p>
                        </div>
                        <Switch
                          checked={!!member.timetable_view_only}
                          onCheckedChange={(val) => handleUpdatePermissions(member.id, { timetable_view_only: val })}
                          data-testid={`pulse-staff-${member.id}-view-only`}
                        />
                      </div>

                      {/* Iter 216bk — site-locking. Owners and master admins always see every site,
                          so we only render this control for staff/manager rows. Empty selection = unrestricted (legacy default). */}
                      {sitesList.length > 1 && (
                        <div className="p-2 bg-[var(--color-surface-dark-alt)] rounded-md border border-white/5">
                          <p className="text-xs text-white font-medium">Sites this staff can see</p>
                          <p className="text-[10px] text-[var(--color-text-muted)] mb-2">
                            Tick one or more sites to lock this user to those sites only. Leave all unticked for unrestricted access (default).
                          </p>
                          <div className="flex flex-wrap gap-1.5" data-testid={`pulse-staff-${member.id}-sites`}>
                            {sitesList.map(s => {
                              const allowed = member.allowed_site_ids || [];
                              const ticked = allowed.includes(s.id);
                              return (
                                <button
                                  key={s.id}
                                  type="button"
                                  onClick={() => {
                                    const next = ticked
                                      ? allowed.filter(x => x !== s.id)
                                      : [...allowed, s.id];
                                    handleUpdatePermissions(member.id, { allowed_site_ids: next });
                                  }}
                                  className={`text-[11px] px-2 py-1 rounded-full border transition-colors ${ticked
                                    ? 'bg-[var(--pulse-primary-hover)] text-white border-transparent'
                                    : 'bg-transparent text-[var(--color-text-muted)] border-white/10 hover:border-white/30'}`}
                                  data-testid={`pulse-staff-${member.id}-site-${s.id}`}
                                >
                                  {s.is_head_office ? '★ ' : ''}{s.name}
                                </button>
                              );
                            })}
                            {(member.allowed_site_ids || []).length > 0 && (
                              <button
                                type="button"
                                onClick={() => handleUpdatePermissions(member.id, { allowed_site_ids: [] })}
                                className="text-[10px] px-2 py-1 rounded-full border border-white/10 text-[var(--color-text-muted)] hover:text-white"
                                data-testid={`pulse-staff-${member.id}-site-clear`}
                              >
                                Clear · all sites
                              </button>
                            )}
                          </div>
                        </div>
                      )}

                      <p className="text-[10px] text-[var(--color-text-faint)]">
                        Per-staff toggles can only restrict — they cannot grant access the organisation doesn't already have.
                      </p>
                    </div>
                  )}
                </div>
                );
              })}
              {staff.length === 0 && <p className="text-sm text-[var(--color-text-muted)] text-center py-4">No team members yet</p>}
            </div>
          </Card>

          {/* Pending Invites */}
          {invites.length > 0 && (
            <Card className="bg-[var(--color-surface-dark-alt)] border-white/10 p-6" data-testid="pulse-pending-invites">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2"><Clock size={18} /> Pending Invites</h3>
              <div className="space-y-2">
                {invites.map(inv => (
                  <div key={inv.id} className="flex items-center gap-3 p-3 rounded-lg bg-[var(--color-ink-alt)] border border-white/10" data-testid={`pulse-settings-invite-${inv.id}`}>
                    <div className="w-9 h-9 rounded-full bg-amber-500/20 flex items-center justify-center flex-shrink-0">
                      <Mail size={14} className="text-amber-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white">{inv.email}</p>
                      <p className="text-xs text-[var(--color-text-muted)]">Role: {inv.role} · Sent {inv.created_at ? new Date(inv.created_at).toLocaleDateString() : ''}</p>
                    </div>
                    <Button variant="outline" size="sm" className="border-white/10 text-[var(--color-text-muted)] h-7 px-2"
                      onClick={() => handleCancelInvite(inv.id)} data-testid={`pulse-settings-cancel-invite-${inv.id}`}>
                      <X size={12} className="mr-1" /> Cancel
                    </Button>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Sites Section */}
      {settingsSection === 'sites' && user.role !== 'staff' && (
        <div className="space-y-4" data-testid="sites-settings">
          {/* Iter 216bn — Head Office discoverability prompt. Lee's
              feedback: he expected HO in the site selector but it's
              opt-in (operators tick the checkbox when adding a site).
              Surface this once at the top of the Sites page so the
              Head Office concept is obvious to new orgs. */}
          {sitesList.length > 0 && !sitesList.some(s => s.is_head_office) && (
            <Card className="border-amber-500/30 bg-amber-500/5 p-4 flex items-start gap-3" data-testid="head-office-prompt">
              <Star size={16} className="text-amber-400 shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white font-semibold">No Head Office set</p>
                <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                  Sales, admin, marketing &amp; service-management staff who don&apos;t belong to a single gym site should be assigned to a Head Office. Tick the <em>Head Office</em> box when you add a site, or edit any existing site to flag it.
                </p>
              </div>
              <Button
                size="sm"
                onClick={() => { setShowAddSite(true); setEditingSiteId(null); setSiteForm({ name: 'Head Office', address: '', postcode: '', is_head_office: true }); }}
                className="bg-amber-600 hover:bg-amber-700 text-white text-xs whitespace-nowrap"
                data-testid="head-office-create-btn"
              >
                <Plus size={12} className="mr-1" /> Create Head Office
              </Button>
            </Card>
          )}

          <Card className="bg-[var(--color-surface-dark-alt)] border-white/10 p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-white font-semibold flex items-center gap-2"><MapPin size={18} className="text-[var(--pulse-primary-hover)]" /> Your Sites</h3>
                <p className="text-xs text-[var(--color-text-muted)] mt-1">Manage locations within your organisation. Equipment and faults can be filtered per site.</p>
              </div>
              <Button size="sm" className="bg-[var(--pulse-primary-hover)] hover:bg-[var(--pulse-primary-light)] text-white"
                onClick={() => { setShowAddSite(true); setEditingSiteId(null); setSiteForm({ name: '', address: '', postcode: '', is_head_office: false }); }}
                data-testid="add-site-btn">
                <Plus size={14} className="mr-1" /> Add Site
              </Button>
            </div>

            {sitesList.length === 0 ? (
              <p className="text-sm text-[var(--color-text-muted)] text-center py-6">No sites configured yet. Add your first site.</p>
            ) : (
              <div className="space-y-2">
                {sitesList.map(site => {
                  const showModules = !!moduleOverridesOpen[site.id];
                  const showBranding = !!brandingOverridesOpen[site.id];
                  return (
                  <div key={site.id} className="rounded-lg bg-[var(--color-ink-alt)] border border-white/10" data-testid={`site-row-${site.id}`}>
                  <div className="flex items-center justify-between p-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <MapPin size={16} className="text-[var(--pulse-primary-hover)] shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm text-white font-medium truncate">{site.name}</p>
                        {site.address && <p className="text-[10px] text-[var(--color-text-muted)] truncate">{site.address}{site.postcode ? ` · ${site.postcode}` : ''}</p>}
                        <div className="flex items-center gap-3 mt-0.5 text-[10px] text-[#555]">
                          <span>{site.equipment_count ?? 0} machines</span>
                          <span>{site.issue_count ?? 0} faults</span>
                          {site.is_default && <Badge className="bg-amber-500/15 text-amber-400 border-0 text-[8px]">Default</Badge>}
                          {site.is_head_office && <Badge className="bg-amber-500/15 text-amber-400 border-0 text-[8px]" data-testid={`site-hq-badge-${site.id}`}>HQ</Badge>}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {!site.is_default && (
                        <Button size="sm" variant="ghost" className="text-[var(--color-text-muted)] hover:text-white h-7 px-2 text-[11px]"
                          onClick={() => setModuleOverridesOpen(s => ({ ...s, [site.id]: !s[site.id] }))}
                          data-testid={`toggle-site-modules-${site.id}`}>
                          <Settings2 size={12} className="mr-1" /> Modules
                          {showModules ? <ChevronUp size={12} className="ml-1"/> : <ChevronDown size={12} className="ml-1"/>}
                        </Button>
                      )}
                      {!site.is_default && (
                        <Button size="sm" variant="ghost" className="text-[var(--color-text-muted)] hover:text-white h-7 px-2 text-[11px]"
                          onClick={() => setBrandingOverridesOpen(s => ({ ...s, [site.id]: !s[site.id] }))}
                          data-testid={`toggle-site-branding-${site.id}`}>
                          <Palette size={12} className="mr-1" /> Branding
                          {showBranding ? <ChevronUp size={12} className="ml-1"/> : <ChevronDown size={12} className="ml-1"/>}
                        </Button>
                      )}
                      {!site.is_default && (
                        <Button size="sm" variant="ghost" className="text-[var(--color-text-muted)] h-7 w-7 p-0"
                          onClick={() => { setEditingSiteId(site.id); setSiteForm({ name: site.name, address: site.address || '', postcode: site.postcode || '', is_head_office: !!site.is_head_office }); setShowAddSite(true); }}
                          data-testid={`edit-site-${site.id}`}><Edit size={13}/></Button>
                      )}
                      {!site.is_default && (
                        <Button size="sm" variant="ghost" className="text-red-400 h-7 w-7 p-0"
                          onClick={async () => {
                            if (!window.confirm(`Delete site "${site.name}"? Equipment will be unlinked, not deleted.`)) return;
                            try { await axios.delete(`${API}/sites/${site.id}`, { headers }); notify.success('Site deleted'); loadSites(); } catch { notify.error('Failed to delete site'); }
                          }}
                          data-testid={`delete-site-${site.id}`}><Trash2 size={13}/></Button>
                      )}
                    </div>
                  </div>
                  {!site.is_default && showModules && (
                    <div className="px-3 pb-3">
                      <SiteModulesOverride siteId={site.id} siteName={site.name} theme="dark" />
                    </div>
                  )}
                  {!site.is_default && showBranding && (
                    <div className="px-3 pb-3 pt-1 border-t border-white/5">
                      <SiteBrandingOverride siteId={site.id} theme="dark" />
                    </div>
                  )}
                  </div>
                  );
                })}
              </div>
            )}

            {showAddSite && (
              <div className="mt-4 p-4 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg" data-testid="site-form">
                <h4 className="text-white text-sm font-medium mb-3">{editingSiteId ? 'Edit Site' : 'Add New Site'}</h4>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                  <div>
                    <Label className="text-[var(--color-text-muted)] text-xs">Site Name</Label>
                    <Input value={siteForm.name} onChange={e => setSiteForm({...siteForm, name: e.target.value})} placeholder="e.g. Manchester Main" className="bg-[var(--color-surface-dark-alt)] border-white/10 text-white mt-1 h-8 text-sm" data-testid="site-name-input" />
                  </div>
                  <div>
                    <Label className="text-[var(--color-text-muted)] text-xs">Address</Label>
                    <Input value={siteForm.address} onChange={e => setSiteForm({...siteForm, address: e.target.value})} placeholder="123 High Street" className="bg-[var(--color-surface-dark-alt)] border-white/10 text-white mt-1 h-8 text-sm" data-testid="site-address-input" />
                  </div>
                  <div>
                    <Label className="text-[var(--color-text-muted)] text-xs">Postcode</Label>
                    <Input value={siteForm.postcode} onChange={e => setSiteForm({...siteForm, postcode: e.target.value})} placeholder="M1 1AA" className="bg-[var(--color-surface-dark-alt)] border-white/10 text-white mt-1 h-8 text-sm" data-testid="site-postcode-input" />
                  </div>
                </div>
                <label className="flex items-center gap-2 mb-3 text-xs text-[var(--color-text-muted)] cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={!!siteForm.is_head_office}
                    onChange={(e) => setSiteForm({ ...siteForm, is_head_office: e.target.checked })}
                    data-testid="site-head-office-checkbox"
                    className="w-4 h-4 accent-[var(--pulse-primary-hover)]"
                  />
                  <span>
                    <strong className="text-white">Head Office</strong> — for sales, admin, marketing &amp; service-management staff who don&apos;t belong to a single gym site. Only one site per organisation can be flagged as Head Office; saving this will clear the flag from any other site.
                  </span>
                </label>
                <div className="flex items-center gap-2">
                  <Button size="sm" className="bg-[var(--pulse-primary-hover)] hover:bg-[var(--pulse-primary-light)] text-white" disabled={savingSite || !siteForm.name.trim()}
                    onClick={async () => {
                      setSavingSite(true);
                      try {
                        if (editingSiteId) {
                          await axios.patch(`${API}/sites/${editingSiteId}`, siteForm, { headers });
                          notify.success('Site updated');
                        } else {
                          await axios.post(`${API}/sites`, siteForm, { headers });
                          notify.success('Site created');
                        }
                        setShowAddSite(false); setSiteForm({ name: '', address: '', postcode: '', is_head_office: false }); setEditingSiteId(null); loadSites();
                      } catch (err) { notifyApiError(notify, err, 'Failed to save site'); }
                      setSavingSite(false);
                    }}
                    data-testid="save-site-btn">
                    {savingSite ? <Loader2 size={13} className="animate-spin mr-1" /> : <Save size={13} className="mr-1" />}
                    {editingSiteId ? 'Update' : 'Create'}
                  </Button>
                  <Button size="sm" variant="outline" className="border-white/10 text-[var(--color-text-muted)]" onClick={() => { setShowAddSite(false); setEditingSiteId(null); }}>Cancel</Button>
                </div>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Org Details Section */}
      {settingsSection === 'org-details' && (
        <Card className="bg-[var(--color-surface-dark-alt)] border-white/10 p-6" data-testid="pulse-org-details">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2"><Building size={18} /> Organisation Details</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label className="text-[var(--color-text-muted)]">Address</Label>
              <Input value={orgAddress} onChange={e => setOrgAddress(e.target.value)} placeholder="123 High Street..." className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="pulse-org-address" />
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)]">Phone</Label>
              <Input value={orgPhone} onChange={e => setOrgPhone(e.target.value)} placeholder="+44 20 1234 5678" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="pulse-org-phone" />
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)]">Email</Label>
              <Input value={orgEmail} onChange={e => setOrgEmail(e.target.value)} placeholder="info@yourgym.com" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="pulse-org-email" />
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)]">Contact Person</Label>
              <Input value={orgContactPerson} onChange={e => setOrgContactPerson(e.target.value)} placeholder="John Smith" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="pulse-org-contact" />
            </div>
          </div>
          <Button onClick={handleSaveOrgDetails} disabled={savingOrg} className="mt-4 bg-[var(--pulse-primary-hover)] hover:bg-[var(--pulse-primary-light)] text-white" data-testid="pulse-org-save">
            {savingOrg ? <Loader2 size={14} className="animate-spin mr-1" /> : <Save size={14} className="mr-1" />} Save Details
          </Button>
        </Card>
      )}

      {/* QR Codes Section */}
      {settingsSection === 'qr-codes' && (
        <Card className="bg-[var(--color-surface-dark-alt)] border-white/10 p-5 space-y-4" data-testid="qr-codes-settings">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-white font-semibold flex items-center gap-2"><QrCode size={18} className="text-[var(--pulse-primary-hover)]" /> Print QR Codes</h3>
              <p className="text-xs text-[var(--color-text-muted)] mt-1">Select machines and print QR labels with Pulse Fitness branding.</p>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" className="border-white/10 text-[var(--color-text-muted)] text-xs" onClick={() => setSelectedQRIds(new Set(equipmentList.map(e => e.id)))} data-testid="qr-select-all">Select All</Button>
              <Button size="sm" variant="outline" className="border-white/10 text-[var(--color-text-muted)] text-xs" onClick={() => setSelectedQRIds(new Set())} data-testid="qr-deselect-all">Deselect All</Button>
            </div>
          </div>

          <div className="bg-[var(--color-ink-alt)] rounded-lg p-3 border border-white/10">
            <p className="text-xs text-[var(--pulse-primary-hover)] font-semibold mb-1">Recommended Printer Setup</p>
            <ul className="text-xs text-[var(--color-text-muted)] space-y-0.5">
              <li>Brother QL-820NWB or DYMO LabelWriter 450</li>
              <li>62mm x 62mm die-cut labels (laminated for gym environments)</li>
              <li>Set printer to "Fit to page" for best sizing</li>
            </ul>
          </div>

          <div className="max-h-[300px] overflow-y-auto space-y-1 pr-1">
            {equipmentList.map(eq => (
              <label key={eq.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 cursor-pointer" data-testid={`qr-equip-${eq.id}`}>
                <Checkbox
                  checked={selectedQRIds.has(eq.id)}
                  onCheckedChange={() => toggleQR(eq.id)}
                  className="border-white/30 data-[state=checked]:bg-[var(--pulse-primary-hover)] data-[state=checked]:border-[var(--pulse-primary-hover)]"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white truncate">{(eq.name || '').split(',')[0].trim()}</p>
                  <p className="text-[10px] text-[var(--color-text-muted)]">{eq.serial_number || 'No serial'}</p>
                </div>
              </label>
            ))}
            {equipmentList.length === 0 && <p className="text-sm text-[var(--color-text-muted)] text-center py-4">No equipment found</p>}
          </div>

          <Button onClick={handlePrintQRCodes} disabled={selectedQRIds.size === 0} className="w-full bg-[var(--pulse-primary-hover)] hover:bg-[var(--pulse-primary-light)] text-white h-11" data-testid="qr-print-selected">
            <Printer size={16} className="mr-2" /> Print {selectedQRIds.size} QR Code{selectedQRIds.size !== 1 ? 's' : ''}
          </Button>
        </Card>
      )}
    </div>
  );
};

export default PulseSettingsTab;
