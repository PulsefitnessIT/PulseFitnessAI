/**
 * SiteStaffManager — commercial "Site Staff & Shared Site Login".
 *
 * Managers/owners use this to:
 *   • enable a shared site login (one username + password for the site)
 *   • maintain the authorised site-staff list (name, job title, email, phone)
 *   • deactivate / reactivate / transfer staff between sites
 *   • configure whether staff selection is mandatory before logging a fault
 *
 * Site staff then sign in on the normal landing page with the shared login
 * and must pick their name from the mandatory dropdown when logging a fault.
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import {
  KeyRound, Loader2, Copy, Check, Plus, Pencil, UserX, UserCheck,
  ArrowRightLeft, RefreshCw, Power, Users, Phone, Mail, ShieldCheck, Download,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useAuth } from '@/App';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const EMPTY_STAFF = {
  first_name: '', last_name: '', job_title: '', email: '', phone: '',
  department: '', notes: '', receive_job_updates: true, pin: '',
};

export default function SiteStaffManager({ headers }) {
  const { t } = useTranslation();
  const { sites } = useAuth();
  const siteList = useMemo(() => sites || [], [sites]);
  const [siteId, setSiteId] = useState('');
  const [staff, setStaff] = useState([]);
  const [shared, setShared] = useState(null);
  const [loading, setLoading] = useState(false);

  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_STAFF);
  const [transferring, setTransferring] = useState(null);
  const [transferTo, setTransferTo] = useState('');
  const [credential, setCredential] = useState(null); // {username,password}
  const [copied, setCopied] = useState(false);
  // Phase 3 — bulk import + usage report
  const [importOpen, setImportOpen] = useState(false);
  const [importPreview, setImportPreview] = useState(null);
  const [importing, setImporting] = useState(false);
  const importRef = React.useRef(null);
  const [report, setReport] = useState(null);
  const [reportOpen, setReportOpen] = useState(false);

  useEffect(() => {
    if (!siteId && siteList.length) setSiteId(siteList[0].id);
  }, [siteList, siteId]);

  const load = useCallback(async () => {
    if (!siteId) return;
    setLoading(true);
    try {
      const [s, sl] = await Promise.all([
        axios.get(`${API}/site-staff?site_id=${siteId}`, { headers }),
        axios.get(`${API}/sites/${siteId}/shared-login`, { headers }),
      ]);
      setStaff(s.data.staff || []);
      setShared(sl.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || t('staffing.ssm_load_failed', 'Could not load site staff'));
    }
    setLoading(false);
  }, [siteId, headers, t]);

  useEffect(() => { load(); }, [load]);

  const saveStaff = async () => {
    if (!form.first_name || !form.last_name || !form.job_title || !form.email || !form.phone) {
      toast.error(t('staffing.ssm_required', 'First name, last name, job title, email and phone are required'));
      return;
    }
    try {
      const payload = { ...form };
      if (!payload.pin) delete payload.pin; // don't clear an existing PIN on edit
      if (editing) {
        await axios.patch(`${API}/site-staff/${editing.id}`, payload, { headers });
        toast.success(t('staffing.ssm_updated', 'Staff updated'));
      } else {
        await axios.post(`${API}/site-staff`, { ...payload, site_id: siteId }, { headers });
        toast.success(t('staffing.ssm_added', 'Staff added'));
      }
      setShowAdd(false); setEditing(null); setForm(EMPTY_STAFF);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('staffing.ssm_save_failed', 'Save failed'));
    }
  };

  const toggleActive = async (s) => {
    const action = s.is_active === false ? 'reactivate' : 'deactivate';
    try {
      await axios.post(`${API}/site-staff/${s.id}/${action}`, {}, { headers });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || t('staffing.ssm_failed', 'Failed')); }
  };

  const doTransfer = async () => {
    if (!transferTo) { toast.error(t('staffing.ssm_pick_dest', 'Pick a destination site')); return; }
    try {
      await axios.post(`${API}/site-staff/${transferring.id}/transfer`, { to_site_id: transferTo }, { headers });
      toast.success(t('staffing.ssm_transferred', 'Staff transferred'));
      setTransferring(null); setTransferTo('');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || t('staffing.ssm_transfer_failed', 'Transfer failed')); }
  };

  const provision = async (rotate) => {
    try {
      const r = await axios.post(`${API}/sites/${siteId}/shared-login/provision`, { rotate }, { headers });
      setCredential(r.data);
      toast.success(rotate ? t('staffing.ssm_pw_rotated', 'Password rotated') : t('staffing.ssm_login_created', 'Shared login created'));
      load();
    } catch (e) { toast.error(e.response?.data?.detail || t('staffing.ssm_provision_failed', 'Provision failed')); }
  };

  const disableLogin = async () => {
    try {
      await axios.post(`${API}/sites/${siteId}/shared-login/disable`, {}, { headers });
      toast.success(t('staffing.ssm_login_disabled', 'Shared login disabled'));
      load();
    } catch (e) { toast.error(e.response?.data?.detail || t('staffing.ssm_failed', 'Failed')); }
  };

  const updateSetting = async (key, value) => {
    try {
      const r = await axios.patch(`${API}/sites/${siteId}/shared-login/settings`, { [key]: value }, { headers });
      setShared((p) => ({ ...p, settings: r.data.settings }));
    } catch (e) { toast.error(e.response?.data?.detail || t('staffing.ssm_failed', 'Failed')); }
  };

  const settings = shared?.settings || {};

  const downloadStaffTemplate = async () => {
    try {
      const res = await axios.get(`${API}/site-staff/import/template`, { headers, responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a'); a.href = url; a.download = 'site-staff-template.csv';
      document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
    } catch { toast.error(t('staffing.ssm_template_failed', 'Template download failed')); }
  };

  const previewImport = async (file) => {
    if (!file) return;
    setImporting(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const res = await axios.post(`${API}/site-staff/import/preview?site_id=${siteId}`, fd, { headers });
      setImportPreview(res.data);
    } catch (e) { toast.error(e.response?.data?.detail || t('staffing.ssm_read_failed', 'Could not read file')); }
    setImporting(false);
  };

  const confirmImport = async () => {
    setImporting(true);
    try {
      const res = await axios.post(`${API}/site-staff/import/confirm`, { site_id: siteId, rows: importPreview.rows }, { headers });
      toast.success(`${t('staffing.ssm_imported', 'Imported')} ${res.data.created} ${t('staffing.ssm_staff_word', 'staff')} (${res.data.skipped} ${t('staffing.ssm_skipped', 'skipped')})`);
      setImportOpen(false); setImportPreview(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || t('staffing.ssm_import_failed', 'Import failed')); }
    setImporting(false);
  };

  const loadReport = async () => {
    try {
      const res = await axios.get(`${API}/site-staff/reports/usage?site_id=${siteId}`, { headers });
      setReport(res.data); setReportOpen(true);
    } catch (e) { toast.error(e.response?.data?.detail || t('staffing.ssm_report_failed', 'Could not load report')); }
  };

  return (
    <div className="space-y-6" data-testid="site-staff-manager">
      {/* Site selector */}
      <div className="flex items-center gap-3">
        <Label className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ssm_site', 'Site')}</Label>
        <Select value={siteId} onValueChange={setSiteId}>
          <SelectTrigger className="w-72" data-testid="site-staff-site-select"><SelectValue placeholder={t('staffing.ssm_choose_site', 'Choose a site')} /></SelectTrigger>
          <SelectContent>
            {siteList.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
          </SelectContent>
        </Select>
        {loading && <Loader2 className="animate-spin" size={16} />}
      </div>

      {/* Shared login panel */}
      <div className="rounded-xl border p-5" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="shared-login-panel">
        <div className="flex items-center gap-2 mb-1">
          <KeyRound size={18} className="text-indigo-500" />
          <h3 className="font-semibold" style={{ color: 'var(--theme-text)' }}>{t('staffing.ssm_shared_login', 'Shared Site Login')}</h3>
          {shared?.enabled && <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700" data-testid="shared-login-status">{t('staffing.ssm_enabled', 'Enabled')}</span>}
        </div>
        <p className="text-xs mb-4" style={{ color: 'var(--theme-text-muted)' }}>
          {t('staffing.ssm_shared_desc', 'One username & password for general site staff. Staff still pick their name when logging a fault, so your service team knows who to contact.')}
        </p>

        {shared?.enabled ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm" style={{ color: 'var(--theme-text)' }}>
              <span><b>{t('staffing.ssm_username', 'Username')}:</b> <code data-testid="shared-login-username">{shared.username}</code></span>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => provision(true)} data-testid="shared-login-rotate"><RefreshCw size={14} className="mr-1.5" />{t('staffing.ssm_reset_pw', 'Reset password')}</Button>
              <Button size="sm" variant="outline" className="text-red-600 border-red-200" onClick={disableLogin} data-testid="shared-login-disable"><Power size={14} className="mr-1.5" />{t('staffing.ssm_disable', 'Disable')}</Button>
            </div>
            <div className="border-t pt-4 space-y-3" style={{ borderColor: 'var(--theme-border)' }}>
              <SettingRow label={t('staffing.ssm_set_require_staff', 'Require staff selection before logging a fault')} testid="setting-require-staff"
                checked={settings.require_staff_selection !== false} onChange={(v) => updateSetting('require_staff_selection', v)} />
              <SettingRow label={t('staffing.ssm_set_allow_other', 'Allow an "Other staff member" option (manual name + contact)')} testid="setting-allow-other"
                checked={!!settings.allow_other_staff} onChange={(v) => updateSetting('allow_other_staff', v)} />
              <SettingRow label={t('staffing.ssm_set_require_pin', 'Require a staff PIN before logging a fault')} testid="setting-require-pin"
                checked={!!settings.require_staff_pin} onChange={(v) => updateSetting('require_staff_pin', v)} />
              <SettingRow label={t('staffing.ssm_set_notify_manager', 'Notify site manager when a fault is logged')} testid="setting-notify-manager"
                checked={!!settings.notify_manager} onChange={(v) => updateSetting('notify_manager', v)} />
              <SettingRow label={t('staffing.ssm_set_notify_staff', 'Notify the selected staff member (confirmation email)')} testid="setting-notify-staff"
                checked={!!settings.notify_staff} onChange={(v) => updateSetting('notify_staff', v)} />
              <SettingRow label={t('staffing.ssm_set_notify_desk', 'Notify the service desk')} testid="setting-notify-servicedesk"
                checked={!!settings.notify_service_desk} onChange={(v) => updateSetting('notify_service_desk', v)} />
              <SettingRow label={t('staffing.ssm_set_notify_supplier', 'Notify the supplier')} testid="setting-notify-supplier"
                checked={!!settings.notify_supplier} onChange={(v) => updateSetting('notify_supplier', v)} />
            </div>
          </div>
        ) : (
          <Button size="sm" onClick={() => provision(false)} disabled={!siteId} data-testid="shared-login-enable">
            <KeyRound size={14} className="mr-1.5" />{t('staffing.ssm_enable_login', 'Enable shared login')}
          </Button>
        )}
      </div>

      {/* Staff list */}
      <div className="rounded-xl border p-5" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Users size={18} className="text-[var(--color-brand-blue)]" />
            <h3 className="font-semibold" style={{ color: 'var(--theme-text)' }}>{t('staffing.ssm_site_staff', 'Site Staff')}</h3>
            <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>({staff.filter((s) => s.is_active !== false).length} {t('staffing.ssm_active', 'active')})</span>
          </div>
          <Button size="sm" onClick={() => { setEditing(null); setForm(EMPTY_STAFF); setShowAdd(true); }} disabled={!siteId} data-testid="site-staff-add">
            <Plus size={14} className="mr-1.5" />{t('staffing.ssm_add_staff', 'Add staff')}
          </Button>
        </div>
        <div className="flex items-center gap-2 mb-4">
          <Button size="sm" variant="outline" onClick={() => { setImportPreview(null); setImportOpen(true); }} disabled={!siteId} data-testid="site-staff-import-open"><Plus size={14} className="mr-1.5" />{t('staffing.ssm_bulk_import', 'Bulk import')}</Button>
          <Button size="sm" variant="outline" onClick={loadReport} disabled={!siteId} data-testid="site-staff-report-open"><Users size={14} className="mr-1.5" />{t('staffing.ssm_usage_report', 'Usage report')}</Button>
        </div>

        {staff.length === 0 ? (
          <p className="text-sm py-6 text-center" style={{ color: 'var(--theme-text-muted)' }} data-testid="site-staff-empty">
            {t('staffing.ssm_empty', 'No site staff yet. Add the people who work at this site so they can log faults.')}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="site-staff-table">
              <thead>
                <tr className="text-left" style={{ color: 'var(--theme-text-muted)' }}>
                  <th className="py-2 pr-3 font-medium">{t('staffing.ssm_col_name', 'Name')}</th>
                  <th className="py-2 pr-3 font-medium">{t('staffing.ssm_col_job', 'Job title')}</th>
                  <th className="py-2 pr-3 font-medium">{t('staffing.ssm_col_contact', 'Contact')}</th>
                  <th className="py-2 pr-3 font-medium">{t('staffing.ssm_col_faults', 'Faults')}</th>
                  <th className="py-2 pr-3 font-medium text-right">{t('staffing.ssm_col_actions', 'Actions')}</th>
                </tr>
              </thead>
              <tbody>
                {staff.map((s) => (
                  <tr key={s.id} className="border-t" style={{ borderColor: 'var(--theme-border)', opacity: s.is_active === false ? 0.5 : 1 }} data-testid={`site-staff-row-${s.id}`}>
                    <td className="py-2 pr-3" style={{ color: 'var(--theme-text)' }}>{s.full_name}{s.is_active === false && <span className="ml-2 text-xs text-red-500">{t('staffing.ssm_inactive', 'inactive')}</span>}</td>
                    <td className="py-2 pr-3" style={{ color: 'var(--theme-text-muted)' }}>{s.job_title}</td>
                    <td className="py-2 pr-3" style={{ color: 'var(--theme-text-muted)' }}>
                      <div className="flex items-center gap-1"><Mail size={11} />{s.email}</div>
                      <div className="flex items-center gap-1"><Phone size={11} />{s.phone}</div>
                    </td>
                    <td className="py-2 pr-3" style={{ color: 'var(--theme-text-muted)' }}>{s.fault_count || 0}</td>
                    <td className="py-2 pr-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button size="icon" variant="ghost" title={t('staffing.ssm_edit', 'Edit')} onClick={() => { setEditing(s); setForm({ ...EMPTY_STAFF, ...s }); setShowAdd(true); }} data-testid={`site-staff-edit-${s.id}`}><Pencil size={14} /></Button>
                        <Button size="icon" variant="ghost" title={t('staffing.ssm_transfer', 'Transfer')} onClick={() => { setTransferring(s); setTransferTo(''); }} data-testid={`site-staff-transfer-${s.id}`}><ArrowRightLeft size={14} /></Button>
                        <Button size="icon" variant="ghost" title={s.is_active === false ? t('staffing.ssm_reactivate', 'Reactivate') : t('staffing.ssm_deactivate', 'Deactivate')} onClick={() => toggleActive(s)} data-testid={`site-staff-toggle-${s.id}`}>
                          {s.is_active === false ? <UserCheck size={14} className="text-green-600" /> : <UserX size={14} className="text-red-500" />}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add/Edit dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent data-testid="site-staff-dialog">
          <DialogHeader><DialogTitle>{editing ? t('staffing.ssm_edit_member', 'Edit staff member') : t('staffing.ssm_add_member', 'Add staff member')}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>{t('staffing.ssm_first_name', 'First name')}</Label><Input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} data-testid="staff-first-name" /></div>
            <div><Label>{t('staffing.ssm_last_name', 'Last name')}</Label><Input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} data-testid="staff-last-name" /></div>
            <div className="col-span-2"><Label>{t('staffing.ssm_col_job', 'Job title')}</Label><Input value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} data-testid="staff-job-title" /></div>
            <div><Label>{t('staffing.ssm_email', 'Email')}</Label><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="staff-email" /></div>
            <div><Label>{t('staffing.ssm_phone', 'Phone')}</Label><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} data-testid="staff-phone" /></div>
            <div className="col-span-2"><Label>{t('staffing.ssm_department', 'Department (optional)')}</Label><Input value={form.department || ''} onChange={(e) => setForm({ ...form, department: e.target.value })} data-testid="staff-department" /></div>
            <div className="col-span-2">
              <Label>{t('staffing.ssm_pin', 'Staff PIN (optional, 4–8 digits)')}</Label>
              <Input value={form.pin || ''} onChange={(e) => setForm({ ...form, pin: e.target.value.replace(/\D/g, '').slice(0, 8) })} placeholder={editing?.has_pin ? t('staffing.ssm_pin_set', '•••• (set — leave blank to keep)') : t('staffing.ssm_pin_ph', 'e.g. 1234')} data-testid="staff-pin" />
              <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ssm_pin_note', 'Used when this site requires PIN confirmation before logging a fault.')}</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}>{t('staffing.ssm_cancel', 'Cancel')}</Button>
            <Button onClick={saveStaff} data-testid="staff-save">{editing ? t('staffing.ssm_save_changes', 'Save changes') : t('staffing.ssm_add_staff', 'Add staff')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Transfer dialog */}
      <Dialog open={!!transferring} onOpenChange={(o) => !o && setTransferring(null)}>
        <DialogContent data-testid="site-staff-transfer-dialog">
          <DialogHeader><DialogTitle>{t('staffing.ssm_transfer', 'Transfer')} {transferring?.full_name}</DialogTitle></DialogHeader>
          <Label>{t('staffing.ssm_move_to', 'Move to site')}</Label>
          <Select value={transferTo} onValueChange={setTransferTo}>
            <SelectTrigger data-testid="transfer-site-select"><SelectValue placeholder={t('staffing.ssm_choose_dest', 'Choose destination site')} /></SelectTrigger>
            <SelectContent>
              {siteList.filter((s) => s.id !== transferring?.site_id).map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTransferring(null)}>{t('staffing.ssm_cancel', 'Cancel')}</Button>
            <Button onClick={doTransfer} data-testid="transfer-confirm">{t('staffing.ssm_transfer', 'Transfer')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk import dialog */}
      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="max-w-2xl" data-testid="site-staff-import-dialog">
          <DialogHeader><DialogTitle>{t('staffing.ssm_bulk_import_title', 'Bulk import site staff')}</DialogTitle></DialogHeader>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={downloadStaffTemplate} data-testid="site-staff-template"><Download size={14} className="mr-1.5" />{t('staffing.ssm_download_template', 'Download template')}</Button>
            <input ref={importRef} type="file" accept=".csv,.xlsx,.xlsm" className="hidden" data-testid="site-staff-import-input"
              onChange={(e) => { previewImport(e.target.files?.[0]); e.target.value = ''; }} />
            <Button size="sm" onClick={() => importRef.current?.click()} disabled={importing} data-testid="site-staff-import-upload">{t('staffing.ssm_upload', 'Upload CSV/Excel')}</Button>
            {importing && <Loader2 className="animate-spin" size={16} />}
          </div>
          {importPreview && (
            <div className="mt-3" data-testid="site-staff-import-preview">
              <p className="text-sm mb-2" style={{ color: 'var(--theme-text-muted)' }}>
                {importPreview.summary.new} {t('staffing.ssm_to_import', 'to import')} · {importPreview.summary.duplicate} {t('staffing.ssm_duplicate', 'duplicate')} · {importPreview.summary.invalid} {t('staffing.ssm_invalid', 'invalid')}
              </p>
              <div className="max-h-72 overflow-y-auto border rounded-lg" style={{ borderColor: 'var(--theme-border)' }}>
                <table className="w-full text-xs">
                  <tbody>
                    {importPreview.rows.map((r, i) => (
                      <tr key={i} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                        <td className="px-2 py-1.5" style={{ color: 'var(--theme-text)' }}>{r.first_name} {r.last_name}</td>
                        <td className="px-2 py-1.5" style={{ color: 'var(--theme-text-muted)' }}>{r.job_title}</td>
                        <td className="px-2 py-1.5" style={{ color: 'var(--theme-text-muted)' }}>{r.email}</td>
                        <td className="px-2 py-1.5 font-medium" style={{ color: r.status === 'new' ? '#16a34a' : r.status === 'duplicate' ? '#d97706' : '#dc2626' }}>{r.status}{r.reason ? ` — ${r.reason}` : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportOpen(false)}>{t('staffing.ssm_cancel', 'Cancel')}</Button>
            <Button onClick={confirmImport} disabled={!importPreview || importPreview.summary.new === 0 || importing} data-testid="site-staff-import-confirm">
              {t('staffing.ssm_import', 'Import')} {importPreview ? importPreview.summary.new : 0} {t('staffing.ssm_staff_word', 'staff')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Usage report dialog */}
      <Dialog open={reportOpen} onOpenChange={setReportOpen}>
        <DialogContent className="max-w-2xl" data-testid="site-staff-report-dialog">
          <DialogHeader><DialogTitle>{t('staffing.ssm_usage_title', 'Shared login usage')}</DialogTitle></DialogHeader>
          {report && (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-3 text-center">
                {[[t('staffing.ssm_total_faults', 'Total faults'), report.summary.total_faults], [t('staffing.ssm_via_shared', 'Via shared login'), report.summary.via_shared_login], [t('staffing.ssm_active_reporters', 'Active reporters'), report.summary.active_reporters], [t('staffing.ssm_staff_word', 'Staff'), report.summary.staff_count]].map(([l, v]) => (
                  <div key={l} className="rounded-lg border p-3" style={{ borderColor: 'var(--theme-border)' }}>
                    <p className="text-2xl font-bold" style={{ color: 'var(--theme-text)' }} data-testid={`report-${l}`}>{v}</p>
                    <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{l}</p>
                  </div>
                ))}
              </div>
              <div>
                <p className="text-sm font-medium mb-1" style={{ color: 'var(--theme-text)' }}>{t('staffing.ssm_faults_by_member', 'Faults logged by staff member')}</p>
                <div className="border rounded-lg overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
                  <table className="w-full text-sm" data-testid="report-by-staff">
                    <tbody>
                      {report.by_staff.map((b) => (
                        <tr key={b.staff_id} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                          <td className="px-3 py-1.5" style={{ color: 'var(--theme-text)' }}>{b.name}{!b.is_active && <span className="ml-1 text-xs text-red-500">{t('staffing.ssm_inactive', 'inactive')}</span>}</td>
                          <td className="px-3 py-1.5" style={{ color: 'var(--theme-text-muted)' }}>{b.job_title}</td>
                          <td className="px-3 py-1.5 text-right font-medium" style={{ color: 'var(--theme-text)' }}>{b.count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              {report.no_activity.length > 0 && (
                <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ssm_no_faults_yet', 'No faults yet')}: {report.no_activity.map((n) => n.name).join(', ')}</p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Credential reveal dialog (shown once) */}
      <Dialog open={!!credential} onOpenChange={(o) => !o && setCredential(null)}>
        <DialogContent data-testid="shared-login-credential-dialog">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><ShieldCheck size={18} className="text-green-600" />{t('staffing.ssm_credentials', 'Shared login credentials')}</DialogTitle></DialogHeader>
          <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.ssm_creds_note', 'Share these with your site staff. The password is shown only once.')}</p>
          <div className="rounded-lg border p-4 space-y-2 font-mono text-sm" style={{ borderColor: 'var(--theme-border)' }}>
            <div>{t('staffing.ssm_username', 'Username')}: <b data-testid="credential-username">{credential?.username}</b></div>
            <div>{t('staffing.ssm_password', 'Password')}: <b data-testid="credential-password">{credential?.password}</b></div>
          </div>
          <DialogFooter>
            <Button onClick={() => {
              navigator.clipboard?.writeText(`${t('staffing.ssm_username', 'Username')}: ${credential.username}\n${t('staffing.ssm_password', 'Password')}: ${credential.password}`);
              setCopied(true); setTimeout(() => setCopied(false), 1500);
            }} data-testid="credential-copy">
              {copied ? <Check size={14} className="mr-1.5" /> : <Copy size={14} className="mr-1.5" />}{t('staffing.ssm_copy', 'Copy')}
            </Button>
            <Button variant="outline" onClick={() => setCredential(null)}>{t('staffing.ssm_done', 'Done')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SettingRow({ label, checked, onChange, testid }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{label}</span>
      <Switch checked={checked} onCheckedChange={onChange} data-testid={testid} />
    </div>
  );
}
