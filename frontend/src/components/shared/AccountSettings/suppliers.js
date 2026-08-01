/**
 * Account Settings → Suppliers section.
 * (Iter 216h113j).
 *
 * Lets owners/managers maintain the org's supplier directory:
 *   name · primary contact · email · phone · manufacturer-match
 *
 * Supplier records auto-link to equipment by manufacturer. When a
 * fault is logged on a machine whose manufacturer matches a supplier
 * `manufacturer_keywords` entry, the fault notification routes to
 * that supplier automatically. MOD managers in particular need this
 * — different installations have different DIO / DEFCON suppliers.
 *
 * Hits `/api/suppliers` (existing routes — POST, GET, PUT, DELETE).
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Plus, Trash2, Pencil, X, Loader2, Truck, Mail, Phone, User, Tag,
  AlertTriangle, CheckCircle2, Lock, BarChart3, ChevronRight, TrendingUp,
} from 'lucide-react';
import { API, useAuthHeaders } from './shared';

const fmtResolution = (hours) => {
  if (hours == null) return '—';
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 48) return `${hours < 10 ? hours.toFixed(1) : Math.round(hours)}h`;
  return `${(hours / 24).toFixed(1)}d`;
};

const Sparkline = ({ data = [], rising = false, width = 76, height = 20 }) => {
  if (!data.length) return null;
  const max = Math.max(...data, 1);
  const stroke = rising ? '#f59e0b' : 'var(--color-brand-blue)';
  const stepX = data.length > 1 ? width / (data.length - 1) : 0;
  const pts = data.map((v, i) => {
    const x = i * stepX;
    const y = height - 2 - (v / max) * (height - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const areaPath = `M0,${height} L${pts.join(' L')} L${(width).toFixed(1)},${height} Z`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible" aria-hidden="true">
      <path d={areaPath} fill={stroke} opacity="0.12" />
      <polyline points={pts.join(' ')} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={(data.length - 1) * stepX} cy={height - 2 - (data[data.length - 1] / max) * (height - 4)} r="1.8" fill={stroke} />
    </svg>
  );
};

const BLANK = {
  name: '', contact_name: '', email: '', phone: '',
  manufacturer_keywords: '',
};

export default function SuppliersSection() {
  const { t } = useTranslation();
  const headers = useAuthHeaders();
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(BLANK);
  const [submitting, setSubmitting] = useState(false);
  // Iter 220ea·40 — dispatch readiness: which machines won't auto-email a
  // supplier on fault submit (supplier has no email / isn't in directory).
  const [readiness, setReadiness] = useState(null);
  const [canAdd, setCanAdd] = useState(true);
  const [insights, setInsights] = useState(null);
  const [expandedKey, setExpandedKey] = useState(null);
  const [faultsByKey, setFaultsByKey] = useState({});
  const [loadingFaults, setLoadingFaults] = useState(false);

  const toggleFaults = useCallback(async (row) => {
    const key = row.is_unassigned ? '__unassigned__' : row.supplier;
    if (expandedKey === key) { setExpandedKey(null); return; }
    setExpandedKey(key);
    if (faultsByKey[key]) return;
    setLoadingFaults(true);
    try {
      const params = row.is_unassigned
        ? { unassigned: true }
        : { supplier: row.supplier };
      const r = await axios.get(`${API}/suppliers/insights/faults`, { headers: headers(), params });
      setFaultsByKey((m) => ({ ...m, [key]: r.data?.faults || [] }));
    } catch { setFaultsByKey((m) => ({ ...m, [key]: [] })); }
    finally { setLoadingFaults(false); }
  }, [expandedKey, faultsByKey, headers]);

  const loadReadiness = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/suppliers/dispatch-readiness`, { headers: headers() });
      setReadiness(r.data || null);
    } catch { /* non-blocking */ }
  }, [headers]);

  const loadInsights = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/suppliers/insights`, { headers: headers() });
      setInsights(r.data || null);
    } catch { setInsights(null); /* Lite orgs get 403 — panel hidden */ }
  }, [headers]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/suppliers`, { headers: headers() });
      setList(r.data?.suppliers || r.data || []);
      if (typeof r.data?.can_add_suppliers === 'boolean') setCanAdd(r.data.can_add_suppliers);
    } catch (e) {
      toast.error(t('settings.sup_load_failed', 'Could not load suppliers'));
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); loadReadiness(); loadInsights(); }, [load, loadReadiness, loadInsights]);

  const openNew = () => { setEditing({}); setForm(BLANK); };
  const openEdit = (s) => {
    setEditing(s);
    setForm({
      name: s.name || '',
      contact_name: s.contact_name || '',
      email: s.email || '',
      phone: s.phone || '',
      manufacturer_keywords: Array.isArray(s.manufacturer_keywords)
        ? s.manufacturer_keywords.join(', ')
        : (s.manufacturer_keywords || ''),
    });
  };
  const close = () => { setEditing(null); setForm(BLANK); };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!form.name?.trim()) { toast.error(t('settings.sup_name_required', 'Name is required')); return; }
    setSubmitting(true);
    try {
      const body = {
        name: form.name.trim(),
        contact_name: form.contact_name.trim() || undefined,
        email: form.email.trim() || undefined,
        phone: form.phone.trim() || undefined,
        manufacturer_keywords: form.manufacturer_keywords
          ? form.manufacturer_keywords.split(',').map((s) => s.trim()).filter(Boolean)
          : [],
      };
      if (editing && editing.id) {
        await axios.put(`${API}/suppliers/${editing.id}`, body, { headers: headers() });
        toast.success(t('settings.sup_updated', 'Supplier updated'));
      } else {
        await axios.post(`${API}/suppliers`, body, { headers: headers() });
        toast.success(t('settings.sup_added', 'Supplier added'));
      }
      close(); load(); loadReadiness();
    } catch (e) {
      const msg = e?.response?.data?.detail || t('settings.sup_save_failed', 'Save failed');
      toast.error(typeof msg === 'string' ? msg : t('settings.sup_save_failed', 'Save failed'));
    } finally { setSubmitting(false); }
  };

  // Quick-fix a blocked supplier: open its editor (add email) or, if the
  // machine references a supplier not in the directory, pre-fill Add.
  const fixBlocked = (b) => {
    if (b.supplier_id) {
      const s = list.find((x) => x.id === b.supplier_id);
      if (s) { openEdit(s); return; }
    }
    setEditing({}); setForm({ ...BLANK, name: b.name || '' });
  };

  const remove = async (s) => {
    if (!window.confirm(t('settings.sup_remove_confirm', 'Remove supplier "{{name}}"?\n\nEquipment currently linked to this supplier will be left unassigned.', { name: s.name }))) return;
    try {
      await axios.delete(`${API}/suppliers/${s.id}`, { headers: headers() });
      toast.success(t('settings.sup_removed', 'Supplier removed'));
      load(); loadReadiness();
    } catch (e) {
      toast.error(e?.response?.data?.detail || t('settings.sup_remove_failed', 'Could not remove'));
    }
  };

  return (
    <section className="space-y-4" data-testid="account-suppliers-section">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold" style={{ color: 'var(--theme-text)' }}>{t('settings.sup_title', 'Suppliers')}</h3>
          <p className="text-sm mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
            {t('settings.sup_sub', "Manage equipment suppliers — fault notifications route to the matching supplier automatically when a machine's manufacturer matches one of their keywords. Any machine without its own supplier is handled by Pulse Fitness Ltd by default.")}
          </p>
        </div>
        {canAdd ? (
          <button type="button" onClick={openNew} className="account-btn-primary inline-flex items-center gap-1.5" data-testid="account-suppliers-add">
            <Plus size={14} /> {t('settings.sup_add', 'Add supplier')}
          </button>
        ) : null}
      </header>

      {/* Iter 220ea·40 — fault auto-dispatch readiness. */}
      {readiness && (readiness.machines_blocked > 0 || (readiness.blocked_suppliers || []).length > 0) ? (
        <div className="rounded-xl border p-4" style={{ background: 'rgba(245,158,11,0.08)', borderColor: 'rgba(245,158,11,0.3)' }} data-testid="supplier-dispatch-readiness-warning">
          <div className="flex items-start gap-2.5">
            <AlertTriangle size={18} className="shrink-0 mt-0.5" style={{ color: '#f59e0b' }} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>
                {t('settings.sup_wont_dispatch', "{{n}} machine(s) won't auto-dispatch faults", { n: readiness.machines_blocked, count: readiness.machines_blocked })}
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                {t('settings.sup_wont_dispatch_hint', "When a fault is logged on these machines, no supplier is emailed because the linked supplier has no email address (or isn't in your directory). Add an email to fix it.")}
              </p>
              <ul className="mt-3 space-y-1.5">
                {(readiness.blocked_suppliers || []).map((b) => (
                  <li key={`${b.supplier_id || b.name}`} className="flex items-center justify-between gap-3 text-xs rounded-lg px-3 py-2" style={{ background: 'var(--theme-surface)' }} data-testid={`blocked-supplier-${b.supplier_id || b.name}`}>
                    <span className="min-w-0 truncate" style={{ color: 'var(--theme-text)' }}>
                      <strong>{b.name}</strong>
                      <span style={{ color: 'var(--theme-text-muted)' }}> · {t('settings.sup_machine_count', '{{n}} machine(s)', { n: b.machine_count, count: b.machine_count })} · {b.reason === 'not_in_directory' ? t('settings.sup_not_in_directory', 'not in directory') : t('settings.sup_no_email', 'no email')}</span>
                    </span>
                    <button type="button" onClick={() => fixBlocked(b)} className="account-btn-secondary inline-flex items-center gap-1 shrink-0 text-xs" data-testid={`fix-blocked-supplier-${b.supplier_id || b.name}`}>
                      <Mail size={11} /> {b.reason === 'not_in_directory' ? t('settings.sup_add_supplier', 'Add supplier') : t('settings.sup_add_email', 'Add email')}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      ) : readiness && readiness.total_machines > 0 ? (
        <div className="rounded-xl border p-3 flex items-center gap-2.5" style={{ background: 'rgba(16,185,129,0.08)', borderColor: 'rgba(16,185,129,0.25)' }} data-testid="supplier-dispatch-readiness-ok">
          <CheckCircle2 size={16} className="shrink-0" style={{ color: '#10b981' }} />
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
            <strong style={{ color: 'var(--theme-text)' }}>{t('settings.sup_machines_ready', '{{n}} machine(s)', { n: readiness.machines_ready, count: readiness.machines_ready })}</strong> {t('settings.sup_will_auto_email', 'will auto-email their supplier on fault submit.')}
            {readiness.machines_no_supplier > 0 && ` ${t('settings.sup_no_supplier_route', '{{n}} with no supplier of their own route to Pulse Fitness Ltd.', { n: readiness.machines_no_supplier })}`}
          </p>
        </div>
      ) : null}

      {/* Supplier Insights (Pro/Full only) — fault load + responsiveness. */}
      {insights && (insights.suppliers || []).length > 0 ? (
        <div className="rounded-xl border overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid="supplier-insights-panel">
          <div className="px-4 py-3 border-b flex items-center justify-between gap-2" style={{ borderColor: 'var(--theme-border)' }}>
            <div className="flex items-center gap-2">
              <BarChart3 size={15} style={{ color: 'var(--color-brand-blue)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{t('settings.sup_insights', 'Supplier insights')}</span>
            </div>
            <span className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{t('settings.sup_window_faults', 'Last {{d}} days · {{n}} fault(s)', { d: insights.window_days, n: insights.total_faults })}</span>
          </div>
          <div className="grid grid-cols-[auto_1fr_auto_auto_auto] gap-x-3 px-4 py-2 text-[11px] uppercase tracking-wider font-semibold" style={{ color: 'var(--theme-text-muted)' }}>
            <span className="w-3.5" /><span>{t('settings.sup_col_supplier', 'Supplier')}</span><span className="text-center">{t('settings.sup_col_trend', '90-day trend')}</span><span className="text-right">{t('settings.sup_col_faults', 'Faults')}</span><span className="text-right">{t('settings.sup_col_resolution', 'Avg. resolution')}</span>
          </div>
          {insights.suppliers.map((r) => {
            const key = r.is_unassigned ? '__unassigned__' : r.supplier;
            const isOpen = expandedKey === key;
            const faults = faultsByKey[key];
            return (
            <div key={r.supplier} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
              <button
                type="button"
                onClick={() => toggleFaults(r)}
                className="w-full grid grid-cols-[auto_1fr_auto_auto_auto] gap-x-3 px-4 py-2.5 items-center text-left transition-colors hover:bg-white/[0.03]"
                data-testid={`supplier-insight-row-${r.is_unassigned ? 'unassigned' : r.supplier}`}
              >
                <ChevronRight size={14} className="transition-transform" style={{ color: 'var(--theme-text-muted)', transform: isOpen ? 'rotate(90deg)' : 'none' }} />
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate flex items-center gap-1.5" style={{ color: r.is_unassigned ? 'var(--theme-text-muted)' : 'var(--theme-text)' }}>
                    {r.is_unassigned ? <><AlertTriangle size={12} style={{ color: '#f59e0b' }} /> {t('settings.sup_unassigned', 'Unassigned')}</> : r.supplier}
                  </div>
                  {r.is_unassigned ? (
                    <div className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{t('settings.sup_unassigned_hint', "No supplier set — assign one so it isn't routed to Pulse by default.")}</div>
                  ) : null}
                </div>
                <div className="flex items-center justify-center gap-1.5" data-testid={`supplier-insight-trend-${r.is_unassigned ? 'unassigned' : r.supplier}`}>
                  <Sparkline data={r.trend || []} rising={r.rising} />
                  {r.rising ? <TrendingUp size={12} style={{ color: '#f59e0b' }} title={t('settings.sup_rising', 'Rising fault volume')} /> : null}
                </div>
                <div className="text-right text-sm" style={{ color: 'var(--theme-text)' }}>
                  {r.total_faults}
                  <span className="text-[11px] ml-1" style={{ color: 'var(--theme-text-muted)' }}>({t('settings.sup_n_open', '{{n}} open', { n: r.open_faults })})</span>
                </div>
                <div className="text-right text-sm tabular-nums" style={{ color: 'var(--theme-text)' }}>{fmtResolution(r.avg_resolution_hours)}</div>
              </button>
              {isOpen ? (
                <div className="px-4 pb-3 pt-1" data-testid={`supplier-insight-faults-${r.is_unassigned ? 'unassigned' : r.supplier}`}>
                  {loadingFaults && !faults ? (
                    <div className="flex items-center gap-2 text-xs py-2" style={{ color: 'var(--theme-text-muted)' }}>
                      <Loader2 size={13} className="animate-spin" /> {t('settings.sup_loading_faults', 'Loading faults…')}
                    </div>
                  ) : (faults && faults.length > 0) ? (
                    <ul className="space-y-1.5">
                      {faults.map((f) => (
                        <li key={f.id} className="rounded-lg px-3 py-2 flex items-start justify-between gap-3" style={{ background: 'var(--theme-bg, rgba(0,0,0,0.15))' }} data-testid={`insight-fault-${f.id}`}>
                          <div className="min-w-0">
                            <div className="text-xs font-medium truncate" style={{ color: 'var(--theme-text)' }}>{f.machine_name}</div>
                            <div className="text-[11px] truncate" style={{ color: 'var(--theme-text-muted)' }}>{f.issue_description}</div>
                          </div>
                          <div className="text-right shrink-0">
                            <span className="text-[10px] uppercase tracking-wide font-bold px-1.5 py-0.5 rounded" style={{ background: (f.status === 'open' || f.status === 'in_progress') ? 'rgba(245,158,11,0.15)' : 'rgba(16,185,129,0.15)', color: (f.status === 'open' || f.status === 'in_progress') ? '#f59e0b' : '#10b981' }}>
                              {(f.status || '').replace('_', ' ') || '—'}
                            </span>
                            <div className="text-[10px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                              {f.resolution_hours != null ? t('settings.sup_resolved_in', 'resolved in {{time}}', { time: fmtResolution(f.resolution_hours) }) : t('settings.sup_open', 'open')}
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="text-xs py-2" style={{ color: 'var(--theme-text-muted)' }}>{t('settings.sup_no_faults_window', 'No faults in this window.')}</div>
                  )}
                </div>
              ) : null}
            </div>
            );
          })}
        </div>
      ) : null}

      <div className="rounded-xl border overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        {loading ? (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--theme-text-muted)' }}>
            <Loader2 size={16} className="animate-spin inline mr-2" /> {t('settings.sup_loading', 'Loading suppliers…')}
          </div>
        ) : list.length === 0 ? (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--theme-text-muted)' }} data-testid="account-suppliers-empty">
            <Truck size={28} className="mx-auto mb-2 opacity-50" />
            {t('settings.sup_empty', 'No suppliers yet. Click Add supplier above.')}
          </div>
        ) : (
          <ul className="divide-y" style={{ borderColor: 'var(--theme-border)' }}>
            {list.map((s) => (
              <li key={s.id} className="p-4 flex items-start gap-3" data-testid={`account-supplier-row-${s.id}`}>
                <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'var(--theme-bg)', color: 'var(--color-brand-blue)' }}>
                  <Truck size={16} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm flex items-center gap-2 flex-wrap" style={{ color: 'var(--theme-text)' }}>
                    {s.name}
                    {s.is_default_pulse ? (
                      <span className="text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded inline-flex items-center gap-1" style={{ background: 'rgba(102,204,255,0.14)', color: 'var(--color-brand-blue)' }} data-testid={`supplier-default-badge-${s.id}`}>
                        <Lock size={9} /> {t('settings.sup_default', 'Default')}
                      </span>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                    {s.contact_name && <span className="inline-flex items-center gap-1"><User size={11} /> {s.contact_name}</span>}
                    {s.email && <span className="inline-flex items-center gap-1"><Mail size={11} /> {s.email}</span>}
                    {s.phone && <span className="inline-flex items-center gap-1"><Phone size={11} /> {s.phone}</span>}
                  </div>
                  {s.is_default_pulse ? (
                    <p className="text-[11px] mt-1.5" style={{ color: 'var(--theme-text-muted)' }}>
                      {t('settings.sup_builtin', 'Built-in Pulse Fitness service contact — every fault on a machine with no other supplier is emailed here automatically.')}
                    </p>
                  ) : null}
                  {Array.isArray(s.manufacturer_keywords) && s.manufacturer_keywords.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 mt-2">
                      <Tag size={11} style={{ color: 'var(--theme-text-muted)' }} />
                      {s.manufacturer_keywords.map((kw) => (
                        <span key={kw} className="text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(102,204,255,0.10)', color: 'var(--color-brand-blue)' }}>
                          {kw}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {s.is_default_pulse ? (
                    <span className="p-1.5 rounded-md" style={{ color: 'var(--theme-text-muted)', opacity: 0.6 }} title={t('settings.sup_locked_default', 'Locked default supplier')} data-testid={`account-supplier-locked-${s.id}`}>
                      <Lock size={14} />
                    </span>
                  ) : (
                    <>
                      <button type="button" onClick={() => openEdit(s)} className="p-1.5 rounded-md" style={{ color: 'var(--theme-text-muted)' }} data-testid={`account-supplier-edit-${s.id}`} aria-label={t('settings.sup_edit', 'Edit')}>
                        <Pencil size={14} />
                      </button>
                      <button type="button" onClick={() => remove(s)} className="p-1.5 rounded-md" style={{ color: 'var(--color-status-error, #DC2626)' }} data-testid={`account-supplier-delete-${s.id}`} aria-label={t('settings.sup_remove', 'Remove')}>
                        <Trash2 size={14} />
                      </button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {editing !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.55)' }} data-testid="account-supplier-modal">
          <form onSubmit={submit} className="rounded-2xl w-full max-w-lg p-6 relative" style={{ background: 'var(--theme-surface)' }}>
            <button type="button" onClick={close} className="absolute right-4 top-4 p-1.5 rounded-full" aria-label="Close" data-testid="account-supplier-close">
              <X size={16} />
            </button>
            <h4 className="text-base font-bold mb-4" style={{ color: 'var(--theme-text)' }}>
              {editing.id ? t('settings.sup_edit_name', 'Edit {{name}}', { name: editing.name }) : t('settings.sup_add', 'Add supplier')}
            </h4>
            <div className="space-y-3">
              <SupField label={t('settings.sup_name_label', 'Supplier name *')} testid="supplier-field-name">
                <input className="account-input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Technogym UK" />
              </SupField>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <SupField label={t('settings.sup_contact_label', 'Primary contact')} testid="supplier-field-contact-name">
                  <input className="account-input" value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} placeholder="John Smith" />
                </SupField>
                <SupField label={t('settings.sup_phone_label', 'Phone')} testid="supplier-field-phone">
                  <input className="account-input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+44 …" />
                </SupField>
              </div>
              <SupField label={t('settings.sup_email_label', 'Email')} testid="supplier-field-email">
                <input className="account-input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="service@…" />
              </SupField>
              <SupField label={t('settings.sup_keywords_label', 'Manufacturer keywords (auto-match equipment)')} testid="supplier-field-keywords">
                <input className="account-input" value={form.manufacturer_keywords} onChange={(e) => setForm({ ...form, manufacturer_keywords: e.target.value })} placeholder="Technogym, Skill Line, Selection" />
                <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                  {t('settings.sup_keywords_hint', 'Comma-separated. Any equipment whose manufacturer matches one of these keywords (case-insensitive) will route its fault notifications to this supplier.')}
                </p>
              </SupField>
            </div>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button type="button" onClick={close} className="account-btn-secondary" data-testid="account-supplier-cancel">{t('settings.sup_cancel', 'Cancel')}</button>
              <button type="submit" disabled={submitting} className="account-btn-primary inline-flex items-center gap-2 disabled:opacity-50" data-testid="account-supplier-save">
                {submitting ? <Loader2 size={14} className="animate-spin" /> : null}
                {editing.id ? t('settings.sup_save_changes', 'Save changes') : t('settings.sup_add', 'Add supplier')}
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}

function SupField({ label, testid, children }) {
  return (
    <label className="block" data-testid={testid}>
      <span className="text-[11px] font-semibold uppercase tracking-wide mb-1.5 block" style={{ color: 'var(--theme-text-muted)' }}>{label}</span>
      {children}
    </label>
  );
}
