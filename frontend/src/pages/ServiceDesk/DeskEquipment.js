/**
 * Service Desk → Equipment (Iter 216h49)
 *
 * Pulse Fitness asked for parity with Sicon Service: one global search
 * box across every customer's kit, so a desk operator can type a serial
 * number or model and pinpoint exactly which gym a machine lives at.
 *
 * Read-only on purpose — Service Desk staff do NOT impersonate the
 * customer to inspect kit; the org name + site name are surfaced inline
 * on every row so the desk operator has full context without entering
 * the customer's account. Mutations (move/delete) still go through the
 * customer's own owner/manager via the Pulse Equipment tab.
 */
import { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { Search, Wrench, Building2, MapPin, Calendar, Hash, ClipboardList } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import ServiceDeskIntakeForm from '@/pages/ServiceOps/ServiceDeskIntakeForm';

const DeskEquipment = ({ API }) => {
  const { t } = useTranslation();
  const [q, setQ] = useState('');
  const [equipment, setEquipment] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const search = useCallback(async (query) => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/service-desk/equipment`, {
        params: { q: query, limit: 50 },
        headers: { Authorization: `Bearer ${token}` },
      });
      setEquipment(res.data?.equipment || []);
      setTotal(res.data?.total || 0);
    } catch {
      setEquipment([]); setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [API]);

  // Debounce 300ms so per-keystroke requests don't flood the API.
  useEffect(() => {
    const timer = setTimeout(() => { search(q); }, q ? 300 : 0);
    return () => clearTimeout(timer);
  }, [q, search]);

  // ── Site-first browse: pick a customer + site to view/select machines
  const [customers, setCustomers] = useState([]);
  const [custOrg, setCustOrg] = useState('');
  const [sitesList, setSitesList] = useState([]);
  const [siteSel, setSiteSel] = useState('');
  const [siteEquip, setSiteEquip] = useState([]);
  const [selected, setSelected] = useState([]);
  const [intakeInitial, setIntakeInitial] = useState(null);
  const authH = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

  useEffect(() => {
    (async () => {
      try { const r = await axios.get(`${API}/svc/desk/customers`, authH()); setCustomers(r.data?.customers || []); }
      catch { /* non-blocking */ }
    })();
  }, [API]);
  useEffect(() => {
    setSitesList([]); setSiteSel(''); setSiteEquip([]); setSelected([]);
    if (!custOrg) return;
    (async () => {
      try { const r = await axios.get(`${API}/svc/desk/customer-sites`, { params: { organization_id: custOrg }, ...authH() }); setSitesList(r.data?.sites || []); }
      catch { setSitesList([]); }
    })();
  }, [custOrg, API]);
  useEffect(() => {
    setSiteEquip([]); setSelected([]);
    if (!custOrg || !siteSel) return;
    (async () => {
      try { const r = await axios.get(`${API}/svc/desk/customer-equipment`, { params: { organization_id: custOrg, site_id: siteSel }, ...authH() }); setSiteEquip(r.data?.equipment || []); }
      catch { setSiteEquip([]); }
    })();
  }, [custOrg, siteSel, API]);

  const toggleSel = (id) => setSelected((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const openCase = () => { if (selected.length) setIntakeInitial({ customerOrgId: custOrg, siteId: siteSel, equipmentIds: selected }); };

  return (
    <div className="space-y-5" data-testid="desk-equipment">
      <header>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-zinc-100">{t('service.eq_title', 'Equipment')}</h2>
        <p className="text-sm text-slate-500 mt-1">
          {t('service.eq_subtitle', "Search every customer's kit by name, model, manufacturer or serial number. Read-only view — use the customer's own console to make changes.")}
        </p>
      </header>

      {/* Site-first: choose a customer + site to view and select machines */}
      <Card className="p-4 bg-white border-slate-200 dark:bg-zinc-900 dark:border-zinc-800" data-testid="desk-equipment-sitefirst">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-semibold text-slate-500">{t('service.eq_customer', 'Customer')}</label>
            <select value={custOrg} onChange={(e) => setCustOrg(e.target.value)}
              className="w-full mt-1 h-10 rounded-lg border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 text-sm" data-testid="desk-eq-customer">
              <option value="">{t('service.eq_select_customer', '— Select customer —')}</option>
              {customers.map((c) => <option key={c.organization_id} value={c.organization_id}>{c.name}{c.is_operator ? ' (my org)' : ''}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-500">{t('service.eq_site', 'Site')}</label>
            <select value={siteSel} onChange={(e) => setSiteSel(e.target.value)} disabled={!custOrg}
              className="w-full mt-1 h-10 rounded-lg border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 text-sm" data-testid="desk-eq-site">
              <option value="">{sitesList.length ? t('service.eq_select_site', '— Select site —') : t('service.eq_no_sites', 'No sites')}</option>
              {sitesList.map((s) => <option key={s.id} value={s.id}>{s.name}{s.equipment_count != null ? ` · ${s.equipment_count} machines` : ''}</option>)}
            </select>
          </div>
        </div>
        {siteSel && (
          <div className="mt-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500">{siteEquip.length} machines · {selected.length} selected</span>
              <Button size="sm" disabled={!selected.length} onClick={openCase} data-testid="desk-eq-logcase"
                className="bg-[var(--color-brand-cyan)] text-[var(--color-ink)] hover:opacity-90">
                <ClipboardList size={13} className="mr-1.5" /> {t('service.eq_log_case_for', 'Log case for {{n}} machine(s)', { n: selected.length || '' })}
              </Button>
            </div>
            <div className="max-h-56 overflow-auto rounded-lg border border-slate-200 dark:border-zinc-800 divide-y divide-slate-100 dark:divide-zinc-800" data-testid="desk-eq-machinelist">
              {siteEquip.length === 0 ? <p className="p-3 text-xs text-slate-400">{t('service.eq_none_site', 'No equipment on this site')}</p> : siteEquip.map((e) => (
                <label key={e.id} className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-slate-50 dark:hover:bg-zinc-800" data-testid={`desk-eq-machine-${e.id}`}>
                  <input type="checkbox" checked={selected.includes(e.id)} onChange={() => toggleSel(e.id)} />
                  <span className="flex-1 truncate">{e.name || 'Unnamed'}{e.manufacturer ? ` · ${e.manufacturer}` : ''}{e.model ? ` ${e.model}` : ''}</span>
                  {e.serial_number && <span className="text-[11px] font-mono text-slate-400">{e.serial_number}</span>}
                </label>
              ))}
            </div>
          </div>
        )}
      </Card>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t('service.eq_search_ph', 'Search equipment across all customers (e.g. Matrix T75, 12345-A, treadmill)…')}
          className="pl-10 h-11 bg-white dark:bg-zinc-900"
          data-testid="desk-equipment-search"
        />
      </div>

      {loading && (
        <p className="text-sm text-slate-500" data-testid="desk-equipment-loading">{t('service.eq_searching', 'Searching…')}</p>
      )}

      {!loading && equipment.length === 0 && (
        <Card className="p-12 text-center bg-white border-slate-200 dark:bg-zinc-900 dark:border-zinc-800" data-testid="desk-equipment-empty">
          <Wrench size={36} className="mx-auto mb-3 text-slate-300" />
          <p className="text-sm font-medium text-slate-600">
            {q ? t('service.eq_no_match', 'No matching equipment') : t('service.eq_start_typing', "Start typing to search every customer's kit")}
          </p>
          <p className="text-xs text-slate-400 mt-1">
            {q ? t('service.eq_try_diff', 'Try a different model name or serial number.') : t('service.eq_context_hint', 'Org and site context appear inline on every result.')}
          </p>
        </Card>
      )}

      {!loading && equipment.length > 0 && (
        <p className="text-xs text-slate-500">{t('service.eq_showing', 'Showing {{n}} of {{total}} matching items', { n: equipment.length, total })}</p>
      )}

      <div className="space-y-2">
        {equipment.map((eq) => (
          <Card
            key={eq.id}
            className="p-4 bg-white border-slate-200 hover:border-slate-300 transition-colors dark:bg-zinc-900 dark:border-zinc-800"
            data-testid={`desk-equipment-row-${eq.id}`}
          >
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0 bg-slate-100 dark:bg-zinc-800">
                <Wrench size={18} className="text-slate-500" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-semibold text-slate-900 truncate dark:text-zinc-100">{eq.name || t('service.eq_unnamed', 'Unnamed equipment')}</p>
                  {eq.equipment_type && (
                    <Badge variant="outline" className="text-[10px] border-slate-200 text-slate-500 dark:border-zinc-800">
                      {eq.equipment_type}
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-4 flex-wrap mt-1 text-xs text-slate-500">
                  {eq.organization_name && (
                    <span className="flex items-center gap-1">
                      <Building2 size={11} className="text-slate-400" />
                      {eq.organization_name}
                    </span>
                  )}
                  {eq.site_name && (
                    <span className="flex items-center gap-1">
                      <MapPin size={11} className="text-slate-400" />
                      {eq.site_name}
                    </span>
                  )}
                  {eq.manufacturer && (
                    <span>
                      {eq.manufacturer}{eq.model ? ` · ${eq.model}` : ''}
                    </span>
                  )}
                  {eq.serial_number && (
                    <span className="flex items-center gap-1 font-mono">
                      <Hash size={10} className="text-slate-400" />
                      {eq.serial_number}
                    </span>
                  )}
                  {eq.warranty_expiry && (
                    <span className="flex items-center gap-1">
                      <Calendar size={11} className="text-slate-400" />
                      {t('service.eq_warranty', 'Warranty')} {new Date(eq.warranty_expiry).toLocaleDateString('en-GB')}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {intakeInitial && (
        <ServiceDeskIntakeForm
          initial={intakeInitial}
          onClose={() => setIntakeInitial(null)}
          onCreated={() => { setIntakeInitial(null); setSelected([]); }}
        />
      )}
    </div>
  );
};

export default DeskEquipment;
