/**
 * CompanyAutocomplete — reusable Companies House + internal-org name picker.
 * Iter 215er (Feb 2026) — extracted from HeadOfficeOnboardingWizard so the
 * Master Admin Create-Organisation dialog (and any future master-admin
 * surface) gets the same dual-source auto-search behaviour.
 *
 * Usage:
 *   <CompanyAutocomplete
 *     value={form.name}
 *     onChange={(v) => setForm({...form, name: v})}
 *     onPick={(picked) => applyPick(picked)}
 *     testIdPrefix="org-create-name"
 *     includeInternal // search existing GymAxis orgs alongside CH
 *   />
 *
 * `picked` callback shape:
 *   { source: 'internal' | 'companies_house', ...all the fields the
 *     respective endpoint returned including the structured 7-field
 *     address }
 */
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Input } from '@/components/ui/input';
import { Search, Loader2, Building2 } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

export const CompanyAutocomplete = ({
  value,
  onChange,
  onPick,
  testIdPrefix = 'company-autocomplete',
  placeholder = '',
  includeInternal = true,
  className = '',
  inputClassName = '',
}) => {
  const [internal, setInternal] = useState([]);
  const [external, setExternal] = useState([]);
  const [chEnabled, setChEnabled] = useState(false);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [picking, setPicking] = useState(null);
  const debRef = useRef(null);
  const wrapRef = useRef(null);

  // One-shot probe: is Companies House lookup configured?
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/master-admin/companies-house/status`, auth());
        if (!cancel) setChEnabled(!!r.data?.enabled);
      } catch { /* silent */ }
    })();
    return () => { cancel = true; };
  }, []);

  useEffect(() => {
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const runSearch = async (q) => {
    setLoading(true);
    try {
      const promises = [];
      if (includeInternal) {
        promises.push(
          axios.get(`${API}/master-admin/organizations/search`, { ...auth(), params: { q: q || '', limit: 6 } })
            .then((r) => r.data?.organizations || []).catch(() => []),
        );
      } else {
        promises.push(Promise.resolve([]));
      }
      if (chEnabled && q && q.length >= 2) {
        promises.push(
          axios.get(`${API}/master-admin/companies-house/search`, { ...auth(), params: { q, limit: 6 } })
            .then((r) => r.data?.items || []).catch(() => []),
        );
      } else {
        promises.push(Promise.resolve([]));
      }
      const [intRes, extRes] = await Promise.all(promises);
      setInternal(intRes);
      setExternal(extRes);
    } finally {
      setLoading(false);
    }
  };

  const onType = (v) => {
    onChange(v);
    setOpen(true);
    if (debRef.current) clearTimeout(debRef.current);
    debRef.current = setTimeout(() => runSearch(v), 250);
  };

  const pickInternal = (o) => {
    onPick?.({ source: 'internal', ...o });
    setOpen(false);
  };

  const pickExternal = async (o) => {
    setPicking(o.company_number);
    try {
      const r = await axios.get(`${API}/master-admin/companies-house/company/${o.company_number}`, auth());
      onPick?.({ source: 'companies_house', ...r.data });
    } catch {
      onPick?.({ source: 'companies_house', ...o });
    } finally {
      setPicking(null);
      setOpen(false);
    }
  };

  const hasResults = internal.length > 0 || external.length > 0;
  const computedPlaceholder = placeholder
    || (chEnabled ? 'Start typing — searches existing orgs + Companies House (UK)' : 'Start typing to search existing organisations');

  return (
    <div className={`relative ${className}`} ref={wrapRef}>
      <div className="relative">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none" />
        <Input
          value={value || ''}
          onChange={(e) => onType(e.target.value)}
          onFocus={() => { setOpen(true); if (!hasResults) runSearch(value); }}
          placeholder={computedPlaceholder}
          className={`pl-9 ${inputClassName}`}
          data-testid={`${testIdPrefix}-input`}
        />
      </div>
      {open && (hasResults || loading) ? (
        <div
          className="absolute z-30 left-0 right-0 mt-1 max-h-96 overflow-auto rounded-lg border border-zinc-200 bg-white shadow-xl"
          data-testid={`${testIdPrefix}-suggestions`}
        >
          {loading && !hasResults ? (
            <div className="px-3 py-3 text-xs text-zinc-400 flex items-center gap-2">
              <Loader2 size={12} className="animate-spin" /> Searching…
            </div>
          ) : null}

          {internal.length > 0 ? (
            <div data-testid={`${testIdPrefix}-section-internal`}>
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider font-bold text-zinc-400 bg-zinc-50 border-b border-zinc-100">
                Existing organisations · {internal.length}
              </div>
              {internal.map((o) => (
                <button
                  type="button"
                  key={o.id}
                  onClick={() => pickInternal(o)}
                  className="w-full text-left px-3 py-2 hover:bg-zinc-50 border-b border-zinc-100 last:border-b-0"
                  data-testid={`${testIdPrefix}-internal-${o.id}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-sm text-zinc-900">{o.name || '(unnamed)'}</span>
                    <span className="text-[10px] uppercase tracking-wider font-bold text-zinc-400">
                      {o.account_type === 'pulse_pro' || o.account_type === 'lite' ? 'Pulse' : 'GymAxis'}
                    </span>
                  </div>
                  <div className="text-[11px] text-zinc-500 mt-0.5 flex items-center gap-2 flex-wrap">
                    {o.company_number ? <span>Co. {o.company_number}</span> : null}
                    {o.postcode ? <span>· {o.postcode}</span> : null}
                    {o.is_multi_site ? <span className="text-amber-600 font-bold">· {o.site_count} sites</span> : null}
                  </div>
                </button>
              ))}
            </div>
          ) : null}

          {external.length > 0 ? (
            <div data-testid={`${testIdPrefix}-section-companies-house`}>
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider font-bold text-emerald-700 bg-emerald-50 border-b border-emerald-100 flex items-center gap-1.5">
                <Building2 size={11} /> Companies House (UK) · {external.length}
              </div>
              {external.map((o) => (
                <button
                  type="button"
                  key={o.company_number}
                  onClick={() => pickExternal(o)}
                  disabled={picking === o.company_number}
                  className="w-full text-left px-3 py-2 hover:bg-emerald-50 border-b border-zinc-100 last:border-b-0 disabled:opacity-60"
                  data-testid={`${testIdPrefix}-ch-${o.company_number}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-sm text-zinc-900">
                      {picking === o.company_number ? <Loader2 size={11} className="inline animate-spin mr-1" /> : null}
                      {o.company_name || '(unnamed)'}
                    </span>
                    <span className={`text-[10px] uppercase tracking-wider font-bold ${o.company_status === 'active' ? 'text-emerald-700' : 'text-zinc-400'}`}>
                      {o.company_status || 'unknown'}
                    </span>
                  </div>
                  <div className="text-[11px] text-zinc-500 mt-0.5 flex items-center gap-2 flex-wrap">
                    <span className="font-mono">Co. {o.company_number}</span>
                    {o.address_snippet ? <span className="truncate">· {o.address_snippet}</span> : null}
                  </div>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

export default CompanyAutocomplete;
