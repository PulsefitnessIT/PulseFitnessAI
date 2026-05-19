/**
 * AddressFields — reusable 8-field address block (Iter 215en + 215eq, Feb 2026)
 *
 * Renders the canonical UK address shape:
 *   • Address 1 *  (street line 1, required)
 *   • Address 2     (optional — flat / unit / building)
 *   • Address 3     (optional — neighbourhood / locality)
 *   • City
 *   • County
 *   • Post code (with postcodes.io autocomplete + auto-fill, iter 215eq)
 *   • Country (defaults to "United Kingdom")
 *
 * 215eq — the postcode field now talks to /api/integrations/postcode/* :
 *   • Autocomplete dropdown while typing (≥2 chars).
 *   • On commit (selecting a suggestion OR blurring a valid postcode)
 *     we fetch the lookup and auto-fill City + County + Country if
 *     they're empty. We deliberately don't overwrite values the user
 *     has already typed manually.
 *   • Visual validity: green tick when the postcode resolves,
 *     amber dot when invalid. Both are tooltip-style and don't block
 *     submit (some legacy data has weird formats).
 *
 * Note on Company Name: it lives outside this block because every form
 * already has its own canonical name field (org_name / site name / account
 * name). The user's "8 fields" requirement is satisfied at the form level:
 * the form's own name field + the 7 fields rendered here.
 *
 * Backwards compatibility:
 *   The legacy `address` (single string) field is still written by callers
 *   for downstream Sage/Sicon outboxes. The parent form is responsible for
 *   composing it from the structured fields (see composeLegacyAddress).
 */
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

/** Compose a single-line legacy-format address from the structured shape. */
export const composeLegacyAddress = (a = {}) => {
  const parts = [
    a.address_line1, a.address_line2, a.address_line3,
    a.city, a.county, a.postcode, a.country,
  ].map((p) => (p || '').trim()).filter(Boolean);
  return parts.join(', ');
};

/** Default empty address shape. */
export const blankAddress = () => ({
  address_line1: '',
  address_line2: '',
  address_line3: '',
  city: '',
  county: '',
  postcode: '',
  country: 'United Kingdom',
});

/** Migrate a legacy single-string `address` into the new shape. */
export const splitLegacyAddress = (legacy = '') => {
  const out = blankAddress();
  if (!legacy) return out;
  const parts = legacy.split(',').map((s) => s.trim()).filter(Boolean);
  if (parts.length === 0) return out;
  out.address_line1 = parts[0] || '';
  if (parts.length >= 2) out.city = parts[1] || '';
  if (parts.length >= 3) out.postcode = parts[2] || '';
  if (parts.length >= 4) out.country = parts[3] || 'United Kingdom';
  return out;
};

/** Postcode input with autocomplete + auto-fill via postcodes.io. */
const PostcodeInput = ({ value, onChange, onResolve, testId, inputClassName }) => {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [valid, setValid] = useState(null); // null | true | false
  const [busy, setBusy] = useState(false);
  const debRef = useRef(null);
  const wrapRef = useRef(null);

  // Close dropdown on outside-click.
  useEffect(() => {
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const fetchSuggestions = async (q) => {
    if (!q || q.replace(/\s+/g, '').length < 2) { setSuggestions([]); return; }
    try {
      const r = await axios.get(`${API}/integrations/postcode/autocomplete`, {
        ...auth(),
        params: { q, limit: 8 },
      });
      setSuggestions(r.data?.suggestions || []);
    } catch { setSuggestions([]); }
  };

  const onType = (v) => {
    onChange(v);
    setValid(null);
    setOpen(true);
    if (debRef.current) clearTimeout(debRef.current);
    debRef.current = setTimeout(() => fetchSuggestions(v), 200);
  };

  const commit = async (postcode) => {
    if (!postcode || postcode.replace(/\s+/g, '').length < 5) {
      setValid(null);
      return;
    }
    setBusy(true);
    try {
      const r = await axios.get(`${API}/integrations/postcode/lookup`, {
        ...auth(),
        params: { postcode },
      });
      if (r.data?.found) {
        setValid(true);
        // Pass the canonical postcode + lookup result up to the parent
        // so it can fill City / County / Country only if those are empty.
        onResolve?.(r.data);
      } else {
        setValid(false);
      }
    } catch {
      setValid(null);
    } finally {
      setBusy(false);
    }
  };

  const pickSuggestion = (p) => {
    onChange(p);
    setOpen(false);
    setSuggestions([]);
    commit(p);
  };

  return (
    <div className="relative" ref={wrapRef}>
      <Input
        value={value || ''}
        onChange={(e) => onType(e.target.value)}
        onFocus={() => { if (suggestions.length > 0) setOpen(true); }}
        onBlur={() => commit(value)}
        placeholder="N15 4QT"
        className={inputClassName}
        data-testid={testId}
        autoComplete="postal-code"
      />
      {/* Validity indicator */}
      <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true">
        {busy ? <Loader2 size={13} className="text-zinc-400 animate-spin" />
          : valid === true ? <CheckCircle2 size={13} className="text-emerald-500" data-testid={`${testId}-valid`} />
          : valid === false ? <AlertCircle size={13} className="text-amber-500" data-testid={`${testId}-invalid`} />
          : null}
      </div>
      {open && suggestions.length > 0 ? (
        <div
          className="absolute z-30 left-0 right-0 mt-1 max-h-60 overflow-auto rounded-lg border border-zinc-200 bg-white shadow-xl dark:bg-zinc-900 dark:border-zinc-800"
          data-testid={`${testId}-suggestions`}
        >
          {suggestions.map((s) => (
            <button
              type="button"
              key={s}
              onClick={() => pickSuggestion(s)}
              className="w-full text-left px-3 py-1.5 text-xs font-mono hover:bg-zinc-50 border-b border-zinc-100 last:border-b-0 dark:bg-zinc-900 dark:border-zinc-800"
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
};

/**
 * @param {Object}   props
 * @param {Object}   props.value    — full address object (see blankAddress)
 * @param {Function} props.onChange — (next) => void
 * @param {string}   props.testIdPrefix — e.g. "ho-billing"
 * @param {boolean}  props.required — mark Address 1 as required (default true)
 * @param {string}   props.bg — extra Tailwind classes (e.g. "bg-white")
 * @param {boolean}  props.compact — denser spacing for nested cards
 */
export const AddressFields = ({
  value = {},
  onChange,
  testIdPrefix = 'address',
  required = true,
  bg = '',
  compact = false,
}) => {
  const v = { ...blankAddress(), ...value };
  const set = (patch) => onChange?.({ ...v, ...patch });
  const labelCls = 'text-zinc-500 text-[10px] uppercase tracking-wider';
  const inputCls = `mt-1 ${bg} h-9 text-sm`;
  const gap = compact ? 'gap-2' : 'gap-3';

  // Iter 215eq — auto-fill city/county/country from a postcodes.io lookup.
  // Only fills empty fields so we never clobber values the user has
  // typed manually.
  const onPostcodeResolved = (lookup) => {
    const patch = { postcode: lookup.postcode || v.postcode };
    if (!v.city && lookup.city) patch.city = lookup.city;
    if (!v.county && lookup.county) patch.county = lookup.county;
    if (!v.country || v.country === 'United Kingdom') {
      // Always overwrite the default "United Kingdom" with the actual
      // country (England / Wales / Scotland / Northern Ireland) so we
      // get more accurate territory routing.
      patch.country = lookup.country || v.country;
    }
    onChange?.({ ...v, ...patch });
  };

  return (
    <div className={`grid grid-cols-1 sm:grid-cols-2 ${gap}`} data-testid={`${testIdPrefix}-block`}>
      <div className="sm:col-span-2">
        <Label className={labelCls}>Address 1{required ? ' *' : ''}</Label>
        <Input
          value={v.address_line1}
          onChange={(e) => set({ address_line1: e.target.value })}
          placeholder="Street address"
          className={inputCls}
          data-testid={`${testIdPrefix}-line1`}
        />
      </div>
      <div className="sm:col-span-2">
        <Label className={labelCls}>Address 2</Label>
        <Input
          value={v.address_line2}
          onChange={(e) => set({ address_line2: e.target.value })}
          placeholder="Unit / building (optional)"
          className={inputCls}
          data-testid={`${testIdPrefix}-line2`}
        />
      </div>
      <div className="sm:col-span-2">
        <Label className={labelCls}>Address 3</Label>
        <Input
          value={v.address_line3}
          onChange={(e) => set({ address_line3: e.target.value })}
          placeholder="Neighbourhood / locality (optional)"
          className={inputCls}
          data-testid={`${testIdPrefix}-line3`}
        />
      </div>
      <div>
        <Label className={labelCls}>Post code</Label>
        <PostcodeInput
          value={v.postcode}
          onChange={(p) => set({ postcode: p })}
          onResolve={onPostcodeResolved}
          testId={`${testIdPrefix}-postcode`}
          inputClassName={`${inputCls} pr-7 font-mono`}
        />
      </div>
      <div>
        <Label className={labelCls}>City</Label>
        <Input
          value={v.city}
          onChange={(e) => set({ city: e.target.value })}
          placeholder="London"
          className={inputCls}
          data-testid={`${testIdPrefix}-city`}
        />
      </div>
      <div>
        <Label className={labelCls}>County</Label>
        <Input
          value={v.county}
          onChange={(e) => set({ county: e.target.value })}
          placeholder="Greater London"
          className={inputCls}
          data-testid={`${testIdPrefix}-county`}
        />
      </div>
      <div>
        <Label className={labelCls}>Country</Label>
        <Input
          value={v.country}
          onChange={(e) => set({ country: e.target.value })}
          placeholder="United Kingdom"
          className={inputCls}
          data-testid={`${testIdPrefix}-country`}
        />
      </div>
    </div>
  );
};

export default AddressFields;
