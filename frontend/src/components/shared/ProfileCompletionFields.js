/**
 * Profile-completion form fields — Iter 220bz.
 *
 * Shared by the post-signup `TrialSignupModal` step-2 and the
 * standalone `CompleteProfilePage` (backward-compat gate for trials
 * that signed up before this iter landed).
 *
 * Pure presentational — the caller owns the state + submit. We just
 * render two labelled groups ("Primary contact" and "Company") with
 * a conditional "Company has a different phone number" checkbox so
 * the operator can either reuse their personal phone or capture a
 * distinct one for the business.
 *
 * Required keys mirror `_PROFILE_REQUIRED_FIELDS` in
 * `backend/routes/account.py` so the client-side validation
 * (HTML `required` + this list) tracks the server.
 */
import { User, Building2, Phone, MapPin } from 'lucide-react';

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
  };
}
