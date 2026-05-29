/**
 * Profile-completion form fields — Iter 220bz / Iter 220cb.
 *
 * Shared by the post-signup `TrialSignupModal` step-2 and the
 * standalone `CompleteProfilePage` (backward-compat gate for trials
 * that signed up before this iter landed).
 *
 * Iter 220cb — competitor-defense layer. The "Company" section now
 * opens with a Companies House typeahead. Picking a CH match
 *   - auto-fills the company number + officially-registered address
 *   - stamps ``companies_house_verified=true``
 * Choosing "Can't find your company" reveals the manual address
 * inputs and flags the org as ``pending_review`` so master admin
 * can vet sole-trader / foreign-company / freshly-incorporated
 * signups before unlocking the dashboard.
 *
 * Pure presentational — the caller owns the state + submit. We just
 * render two labelled groups ("Primary contact" and "Company") with
 * a conditional "Company has a different phone number" checkbox.
 *
 * Required keys mirror `_PROFILE_REQUIRED_FIELDS` in
 * `backend/routes/account.py` so the client-side validation
 * (HTML `required` + this list) tracks the server.
 */
import { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import { User, Building2, MapPin, Search, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const PROFILE_REQUIRED_FIELDS = [
  'primary_contact_name', 'primary_contact_phone',
  'primary_contact_address_line1', 'primary_contact_city',
  'primary_contact_postcode', 'primary_contact_country',
  'address_line1', 'city', 'postcode', 'country',
];

export const COUNTRY_OPTIONS = [
  { value: 'GB', label: 'United Kingdom' },
  { value: 'IE', label: 'Ireland' },
  { value: 'US', label: 'United States' },
  { value: 'CA', label: 'Canada' },
  { value: 'AU', label: 'Australia' },
  { value: 'NZ', label: 'New Zealand' },
  { value: 'OTHER', label: 'Other (specify in line 3)' },
];

function Lbl({ children, required }) {
  return (
    <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">
      {children}{required ? ' *' : ''}
    </label>
  );
}

function Inp({ name, value, onChange, type = 'text', placeholder, required = false, testid }) {
  return (
    <input
      type={type}
      name={name}
      value={value || ''}
      onChange={onChange}
      placeholder={placeholder}
      required={required}
      className="w-full h-11 px-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 transition dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
      data-testid={testid}
    />
  );
}

function Sel({ name, value, onChange, options, required = false, testid }) {
  return (
    <select
      name={name}
      value={value || ''}
      onChange={onChange}
      required={required}
      className="w-full h-11 px-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-slate-400 transition appearance-none dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
      data-testid={testid}
    >
      <option value="">Select…</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

// ─── Iter 220cb · Companies House typeahead ──────────────────────────
//
// Renders a search input that calls /api/account/companies-house/search
// on debounce. When the operator clicks a result we fetch the full
// profile, auto-fill the company section's address, and stamp
// companies_house_verified / company_number on the form.
//
// "Can't find your company?" reveals the manual entry path + flips
// pending_review on the form so the backend can quarantine the org.

function CompaniesHouseSearch({ form, setForm }) {
  const [enabled, setEnabled] = useState(null); // null = unchecked, true/false
  const [query, setQuery] = useState(form.company_search_query || '');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [manualMode, setManualMode] = useState(false);
  const debounceRef = useRef(null);

  // Check whether CH is enabled on mount.
  useEffect(() => {
    let cancelled = false;
    const token = localStorage.getItem('token');
    axios.get(`${API}/account/companies-house/status`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then((r) => { if (!cancelled) setEnabled(!!r.data?.enabled); })
      .catch(() => { if (!cancelled) setEnabled(false); });
    return () => { cancelled = true; };
  }, []);

  // Debounced search.
  useEffect(() => {
    if (!enabled || manualMode) return undefined;
    if (form.companies_house_verified) return undefined;
    if (query.trim().length < 2) { setResults([]); return undefined; }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const token = localStorage.getItem('token');
        const { data } = await axios.get(`${API}/account/companies-house/search`, {
          params: { q: query.trim(), limit: 8 },
          headers: { Authorization: `Bearer ${token}` },
        });
        setResults(data?.items || []);
        setOpen(true);
      } catch (e) {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, enabled, manualMode, form.companies_house_verified]);

  // Pick a CH match → fetch the full profile and auto-fill.
  const pickCompany = async (item) => {
    setOpen(false);
    setProfileLoading(true);
    try {
      const token = localStorage.getItem('token');
      const { data } = await axios.get(`${API}/account/companies-house/company/${item.company_number}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setForm((f) => ({
        ...f,
        company_number: data.company_number,
        companies_house_verified: true,
        pending_review: false,
        pending_review_reason: '',
        address_line1: data.address_line1 || '',
        address_line2: data.address_line2 || '',
        address_line3: data.address_line3 || '',
        city: data.city || '',
        postcode: data.postcode || '',
        country: 'GB',
        company_search_query: data.company_name || item.company_name,
      }));
      setQuery(data.company_name || item.company_name);
    } catch (e) {
      // Fall through silently — operator can re-pick or switch modes.
    } finally {
      setProfileLoading(false);
    }
  };

  // Switch to manual entry — flags the org for review.
  const switchToManual = () => {
    setManualMode(true);
    setForm((f) => ({
      ...f,
      company_number: '',
      companies_house_verified: false,
      pending_review: true,
      pending_review_reason: 'manual_company_entry',
    }));
  };

  // Reset the verified state when the user wants to re-search.
  const clearVerified = () => {
    setForm((f) => ({
      ...f,
      company_number: '',
      companies_house_verified: false,
      pending_review: false,
      pending_review_reason: '',
    }));
    setQuery('');
    setResults([]);
  };

  if (enabled === false) return null; // CH not configured → fall back to plain address entry.
  if (manualMode) {
    return (
      <div className="mb-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 flex items-start gap-2" data-testid="profile-co-manual-banner">
        <AlertCircle size={14} className="mt-0.5 shrink-0" />
        <div>
          <p className="font-semibold">Manual entry — pending review</p>
          <p className="mt-0.5">Sole traders and freshly-incorporated businesses are welcome. Your account will be marked for a quick review by our team (usually within 1 business hour) before all modules unlock.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="profile-co-ch-section">
      <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">
        Find your company on Companies House *
      </label>
      {form.companies_house_verified ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 flex items-center justify-between gap-2" data-testid="profile-co-verified">
          <div className="flex items-center gap-2 min-w-0">
            <CheckCircle2 size={16} className="shrink-0 text-emerald-600" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-emerald-900 truncate">{query}</p>
              <p className="text-[11px] text-emerald-700">Co. №&nbsp;{form.company_number} · address auto-filled below</p>
            </div>
          </div>
          <button type="button" onClick={clearVerified} className="text-[11px] font-semibold text-emerald-700 hover:text-emerald-900 underline shrink-0" data-testid="profile-co-clear">
            Change
          </button>
        </div>
      ) : (
        <div className="relative">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => results.length && setOpen(true)}
              placeholder="Start typing your company name…"
              className="w-full h-11 pl-9 pr-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-slate-400 transition dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
              data-testid="profile-co-ch-search"
            />
            {loading || profileLoading ? (
              <Loader2 size={14} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-slate-400" />
            ) : null}
          </div>
          {open && results.length > 0 ? (
            <ul
              className="absolute z-30 mt-1 w-full max-h-64 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-lg dark:bg-zinc-950 dark:border-zinc-800"
              data-testid="profile-co-ch-results"
            >
              {results.map((it) => (
                <li key={it.company_number}>
                  <button
                    type="button"
                    onClick={() => pickCompany(it)}
                    className="w-full text-left px-3 py-2 hover:bg-slate-50 transition border-b border-slate-100 last:border-0 dark:hover:bg-zinc-900 dark:border-zinc-800"
                    data-testid={`profile-co-ch-pick-${it.company_number}`}
                  >
                    <p className="text-sm font-semibold text-slate-900 dark:text-zinc-100">{it.company_name}</p>
                    <p className="text-[11px] text-slate-500">
                      Co. №&nbsp;{it.company_number}
                      {it.company_status ? ` · ${it.company_status}` : ''}
                      {(it.address && it.address.locality) ? ` · ${it.address.locality}` : ''}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <button
            type="button"
            onClick={switchToManual}
            className="mt-2 text-[11px] font-semibold text-slate-600 hover:text-slate-900 underline"
            data-testid="profile-co-ch-no-match"
          >
            Can&apos;t find your company? Enter manually (sole trader / foreign / new business)
          </button>
        </div>
      )}
    </div>
  );
}


export default function ProfileCompletionFields({ form, setForm }) {
  const update = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const toggle = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.checked }));

  return (
    <div className="space-y-6" data-testid="profile-completion-fields">
      {/* ── Primary contact ─────────────────────────────────────── */}
      <fieldset className="rounded-2xl border border-slate-200 bg-white p-5 dark:bg-zinc-950 dark:border-zinc-800">
        <legend className="flex items-center gap-1.5 px-2 -ml-2 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
          <User size={12} /> Primary contact
        </legend>
        <div className="space-y-3 mt-2">
          <div>
            <Lbl required>Full name</Lbl>
            <Inp
              name="primary_contact_name"
              value={form.primary_contact_name}
              onChange={update('primary_contact_name')}
              placeholder="Jane Smith"
              required
              testid="profile-pc-name"
            />
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <Lbl required>Phone</Lbl>
              <Inp
                name="primary_contact_phone"
                value={form.primary_contact_phone}
                onChange={update('primary_contact_phone')}
                placeholder="+44 7700 900123"
                type="tel"
                required
                testid="profile-pc-phone"
              />
            </div>
            <div>
              <Lbl>Email</Lbl>
              <Inp
                name="primary_contact_email"
                value={form.primary_contact_email}
                onChange={update('primary_contact_email')}
                placeholder="(your login email)"
                type="email"
                testid="profile-pc-email"
              />
            </div>
          </div>
          <div>
            <Lbl required>Address line 1</Lbl>
            <Inp
              name="primary_contact_address_line1"
              value={form.primary_contact_address_line1}
              onChange={update('primary_contact_address_line1')}
              placeholder="Street address"
              required
              testid="profile-pc-line1"
            />
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <Inp
              name="primary_contact_address_line2"
              value={form.primary_contact_address_line2}
              onChange={update('primary_contact_address_line2')}
              placeholder="Unit / building (optional)"
              testid="profile-pc-line2"
            />
            <Inp
              name="primary_contact_address_line3"
              value={form.primary_contact_address_line3}
              onChange={update('primary_contact_address_line3')}
              placeholder="Neighbourhood (optional)"
              testid="profile-pc-line3"
            />
          </div>
          <div className="grid sm:grid-cols-3 gap-3">
            <div>
              <Lbl required>City</Lbl>
              <Inp
                name="primary_contact_city"
                value={form.primary_contact_city}
                onChange={update('primary_contact_city')}
                placeholder="London"
                required
                testid="profile-pc-city"
              />
            </div>
            <div>
              <Lbl required>Post code</Lbl>
              <Inp
                name="primary_contact_postcode"
                value={form.primary_contact_postcode}
                onChange={update('primary_contact_postcode')}
                placeholder="SW1A 1AA"
                required
                testid="profile-pc-postcode"
              />
            </div>
            <div>
              <Lbl required>Country</Lbl>
              <Sel
                name="primary_contact_country"
                value={form.primary_contact_country}
                onChange={update('primary_contact_country')}
                options={COUNTRY_OPTIONS}
                required
                testid="profile-pc-country"
              />
            </div>
          </div>
        </div>
      </fieldset>

      {/* ── Company ─────────────────────────────────────────────── */}
      <fieldset className="rounded-2xl border border-slate-200 bg-white p-5 dark:bg-zinc-950 dark:border-zinc-800">
        <legend className="flex items-center gap-1.5 px-2 -ml-2 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
          <Building2 size={12} /> Company
        </legend>
        <div className="space-y-3 mt-2">
          <CompaniesHouseSearch form={form} setForm={setForm} />
          <div>
            <Lbl required>Address line 1</Lbl>
            <Inp
              name="address_line1"
              value={form.address_line1}
              onChange={update('address_line1')}
              placeholder="Trading address"
              required
              testid="profile-co-line1"
            />
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <Inp
              name="address_line2"
              value={form.address_line2}
              onChange={update('address_line2')}
              placeholder="Unit / building (optional)"
              testid="profile-co-line2"
            />
            <Inp
              name="address_line3"
              value={form.address_line3}
              onChange={update('address_line3')}
              placeholder="Neighbourhood (optional)"
              testid="profile-co-line3"
            />
          </div>
          <div className="grid sm:grid-cols-3 gap-3">
            <div>
              <Lbl required>City</Lbl>
              <Inp
                name="city"
                value={form.city}
                onChange={update('city')}
                placeholder="London"
                required
                testid="profile-co-city"
              />
            </div>
            <div>
              <Lbl required>Post code</Lbl>
              <Inp
                name="postcode"
                value={form.postcode}
                onChange={update('postcode')}
                placeholder="EC1A 1BB"
                required
                testid="profile-co-postcode"
              />
            </div>
            <div>
              <Lbl required>Country</Lbl>
              <Sel
                name="country"
                value={form.country}
                onChange={update('country')}
                options={COUNTRY_OPTIONS}
                required
                testid="profile-co-country"
              />
            </div>
          </div>
          {/* Company phone toggle */}
          <div className="pt-2">
            <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-700 dark:text-zinc-200">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-400"
                checked={!!form.has_different_company_phone}
                onChange={toggle('has_different_company_phone')}
                data-testid="profile-co-phone-toggle"
              />
              Company has a different phone number
            </label>
            {form.has_different_company_phone ? (
              <div className="mt-3">
                <Lbl required>Company phone</Lbl>
                <Inp
                  name="company_phone"
                  value={form.company_phone}
                  onChange={update('company_phone')}
                  placeholder="+44 20 1234 5678"
                  type="tel"
                  required
                  testid="profile-co-phone"
                />
              </div>
            ) : null}
          </div>
        </div>
      </fieldset>

      <p className="flex items-start gap-2 text-[11px] text-slate-400 dark:text-zinc-500">
        <MapPin size={11} className="mt-0.5 shrink-0" />
        <span>
          We need this to keep your account compliant and for support / billing.
          You won&apos;t be charged during the 3-day trial.
          Stored under our <a href="/privacy" target="_blank" rel="noreferrer" className="underline hover:text-slate-700">privacy policy</a>.
        </span>
      </p>
    </div>
  );
}

/** Returns a list of missing-required-field keys for the current form. */
export function findMissingRequired(form) {
  return PROFILE_REQUIRED_FIELDS.filter((k) => !((form[k] || '').toString().trim()));
}

/** Empty initial state — keeps the controlled-input contract happy. */
export function emptyProfileForm() {
  return {
    primary_contact_name: '',
    primary_contact_phone: '',
    primary_contact_email: '',
    primary_contact_address_line1: '',
    primary_contact_address_line2: '',
    primary_contact_address_line3: '',
    primary_contact_city: '',
    primary_contact_postcode: '',
    primary_contact_country: 'GB',
    address_line1: '',
    address_line2: '',
    address_line3: '',
    city: '',
    postcode: '',
    country: 'GB',
    has_different_company_phone: false,
    company_phone: '',
    // Iter 220cb — Companies House verification.
    company_number: '',
    companies_house_verified: false,
    pending_review: false,
    pending_review_reason: '',
    company_search_query: '',
  };
}
