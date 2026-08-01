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
import { Search, Wrench, Building2, MapPin, Calendar, Hash } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';

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

  return (
    <div className="space-y-5" data-testid="desk-equipment">
      <header>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-zinc-100">{t('service.eq_title', 'Equipment')}</h2>
        <p className="text-sm text-slate-500 mt-1">
          {t('service.eq_subtitle', "Search every customer's kit by name, model, manufacturer or serial number. Read-only view — use the customer's own console to make changes.")}
        </p>
      </header>

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
    </div>
  );
};

export default DeskEquipment;
