/**
 * GymAxis Memberships — Setup Wizard (Iter 216h252 redesign).
 *
 * Step plan (operator-first, dance-studio friendly):
 *   1. Studio          — name (pre-filled), app address (auto-derived +
 *                        live availability), timezone (dropdown), logo
 *                        drag-and-drop, address + contact, currency,
 *                        brand colour.
 *   2. Payment         — Manual / Direct Debit (soon) / Stripe Connect
 *                        (soon). Dark-mode safe.
 *   3. Plans           — 3 starter plan templates.
 *   4. Instructor      — add your first instructor (functional).
 *   5. Class           — first class with instructor dropdown.
 *   6. Done            — your app URL.
 *
 * Progress persists on the org doc (setup_step + setup_completed).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
  CheckCircle2, ChevronRight, ChevronLeft, Sparkles, Link as LinkIcon,
  Copy, CreditCard, Banknote, Check, Loader2, Upload, Image as ImageIcon,
  AlertCircle, UserPlus,
} from 'lucide-react';
import { useAuth } from '@/App';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const STEPS = [
  { id: 'basics',     label: 'Studio' },
  { id: 'payment',    label: 'Payment' },
  { id: 'plans',      label: 'Plans' },
  { id: 'instructor', label: 'Instructor' },
  { id: 'class',      label: 'Class' },
  { id: 'done',       label: 'Done' },
];

export default function SetupWizard() {
  useAuth();
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const navigate = useNavigate();
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [status, setStatus] = useState(null);
  const [stepIdx, setStepIdx] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/memberships/setup/status`, { headers });
      setStatus(data);
      const cursor = data.organization.setup_step || 'basics';
      const idx = Math.max(0, STEPS.findIndex((s) => s.id === cursor));
      setStepIdx(idx);
    } catch { notify.error('Failed to load setup status'); }
  }, [headers]);
  useEffect(() => { refresh(); }, [refresh]);

  if (!status) return <FullPageLoader />;
  const current = STEPS[stepIdx];

  return (
    <div className="min-h-screen text-white" style={{ background: '#07090E' }} data-testid="mbr-setup">
      <header className="border-b" style={{ borderColor: 'rgba(255,255,255,0.1)', background: '#0a0c10' }}>
        <div className="max-w-4xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.25em]" style={{ color: 'var(--color-brand-cyan)' }}>Setup</div>
            <div className="text-lg font-extrabold mt-0.5">Welcome to Memberships</div>
          </div>
          <button onClick={() => navigate('/memberships')} className="text-xs font-bold" style={{ color: 'rgba(255,255,255,0.6)' }} data-testid="mbr-setup-skip">
            Skip for now
          </button>
        </div>
        <StepBar stepIdx={stepIdx} setStepIdx={(i) => i < stepIdx && setStepIdx(i)} />
      </header>
      <main className="max-w-xl mx-auto px-6 py-10">
        {current.id === 'basics'     && <StudioBasics  headers={headers} status={status} onNext={refreshThen(setStepIdx, 1, refresh)} />}
        {current.id === 'payment'    && <PaymentMethod headers={headers} status={status} onNext={() => setStepIdx(2)} onBack={() => setStepIdx(0)} />}
        {current.id === 'plans'      && <StarterPlans  headers={headers} status={status} onNext={refreshThen(setStepIdx, 3, refresh)} onBack={() => setStepIdx(1)} />}
        {current.id === 'instructor' && <InstructorStep headers={headers} status={status} onNext={refreshThen(setStepIdx, 4, refresh)} onBack={() => setStepIdx(2)} />}
        {current.id === 'class'      && <FirstClass    headers={headers} status={status} onNext={refreshThen(setStepIdx, 5, refresh)} onBack={() => setStepIdx(3)} />}
        {current.id === 'done'       && <AllDone       headers={headers} status={status} onFinish={() => navigate('/memberships')} />}
      </main>
    </div>
  );
}

function refreshThen(setStepIdx, target, refresh) {
  return async () => { await refresh(); setStepIdx(target); };
}

/* ─────────────────── Step bar ─────────────────── */

function StepBar({ stepIdx, setStepIdx }) {
  return (
    <div className="max-w-4xl mx-auto px-6 pb-4">
      <ol className="flex items-center gap-2 overflow-x-auto">
        {STEPS.map((s, i) => {
          const done = i < stepIdx;
          const active = i === stepIdx;
          return (
            <li key={s.id} className="flex-1 flex items-center gap-2 min-w-0">
              <button onClick={() => setStepIdx(i)} data-testid={`mbr-setup-step-${s.id}`}
                className={`flex items-center gap-2 transition ${done || active ? 'opacity-100' : 'opacity-40'}`}
                disabled={!done}>
                <span className="w-6 h-6 rounded-full grid place-items-center text-[10px] font-extrabold"
                  style={{
                    background: done ? '#10b981' : active ? 'var(--color-brand-cyan)' : 'rgba(255,255,255,0.1)',
                    color: done || active ? '#000' : '#fff',
                  }}>
                  {done ? <Check size={12} /> : i + 1}
                </span>
                <span className="text-[10px] font-extrabold uppercase tracking-wider whitespace-nowrap" style={{ color: active ? '#fff' : 'rgba(255,255,255,0.6)' }}>{s.label}</span>
              </button>
              {i < STEPS.length - 1 && <div className="h-px flex-1" style={{ background: 'rgba(255,255,255,0.1)' }} />}
            </li>
          );
        })}
      </ol>
    </div>
  );
}


/* ─────────────────── Step 1 — Basics (redesigned) ─────────────────── */

// A common-zones list. The full IANA list is overkill for a studio
// operator; these cover 99% of the studios GymAxis targets (UK,
// Europe, North America, Australia, New Zealand).
const TIMEZONES = [
  'Europe/London', 'Europe/Dublin', 'Europe/Paris', 'Europe/Berlin',
  'Europe/Madrid', 'Europe/Rome', 'Europe/Amsterdam', 'Europe/Zurich',
  'Europe/Stockholm', 'Europe/Copenhagen', 'Europe/Lisbon', 'Europe/Warsaw',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Toronto', 'America/Vancouver', 'America/Mexico_City',
  'Australia/Sydney', 'Australia/Melbourne', 'Australia/Perth',
  'Pacific/Auckland', 'Asia/Singapore', 'Asia/Dubai',
];

const COUNTRIES = [
  'United Kingdom', 'Ireland', 'United States', 'Canada', 'Australia',
  'New Zealand', 'France', 'Germany', 'Spain', 'Italy', 'Netherlands',
  'Other',
];

function StudioBasics({ headers, status, onNext }) {
  const org = status.organization;
  const [f, setF] = useState({
    name: org.name || '',
    slug: org.slug || '',
    primary_brand_colour: org.primary_brand_colour || '#19CDFF',
    timezone: org.timezone || 'Europe/London',
    currency: org.currency || 'GBP',
    logo_url: org.logo_url || '',
    address_line1: org.address_line1 || '',
    address_line2: org.address_line2 || '',
    city: org.city || '',
    postcode: org.postcode || '',
    country: org.country || 'United Kingdom',
    contact_email: org.contact_email || '',
    contact_phone: org.contact_phone || '',
  });
  const [saving, setSaving] = useState(false);
  // Iter 216h252 — slug auto-derive + live availability.
  const slugifyClient = (s) => (s || '').toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
  const slugTouched = useRef(Boolean(org.slug));
  const [slugStatus, setSlugStatus] = useState({ checking: false, available: null, suggestion: null });

  const up = (k) => (v) => setF((p) => ({ ...p, [k]: v }));

  // Auto-derive slug from name until the operator types their own.
  const onName = (v) => {
    setF((p) => {
      const next = { ...p, name: v };
      if (!slugTouched.current) next.slug = slugifyClient(v);
      return next;
    });
  };
  const onSlugEdit = (v) => {
    slugTouched.current = true;
    up('slug')(slugifyClient(v));
  };

  // Live availability check (debounced 400ms).
  useEffect(() => {
    if (!f.slug || f.slug.length < 3) {
      setSlugStatus({ checking: false, available: false, suggestion: null });
      return undefined;
    }
    let cancelled = false;
    setSlugStatus((p) => ({ ...p, checking: true }));
    const t = setTimeout(async () => {
      try {
        const { data } = await axios.get(`${API}/memberships/setup/check-slug`, { params: { slug: f.slug }, headers });
        if (cancelled) return;
        setSlugStatus({ checking: false, available: Boolean(data.available), suggestion: data.suggestion || null });
      } catch {
        if (cancelled) return;
        setSlugStatus({ checking: false, available: null, suggestion: null });
      }
    }, 400);
    return () => { cancelled = true; clearTimeout(t); };
  }, [f.slug, headers]);

  const submit = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { notify.error('Studio name required'); return; }
    if (!f.slug.trim()) { notify.error('App address required'); return; }
    if (slugStatus.available === false) { notify.error('App address is taken — try the suggestion below'); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/setup/basics`, f, { headers });
      notify.success('Studio saved');
      onNext();
    } catch (err) { notifyApiError(notify, err, 'Failed'); }
    finally { setSaving(false); }
  };

  return (
    <StepShell title="Tell us about your studio" subtitle="This shapes your member-facing app.">
      <form onSubmit={submit} className="space-y-4" data-testid="mbr-setup-basics">
        <Input label="Studio name" value={f.name} onChange={onName} required testid="mbr-setup-name" placeholder="e.g. Bella Dance Academy" />

        {/* App address — friendlier than "slug" */}
        <SlugField
          value={f.slug}
          onChange={onSlugEdit}
          status={slugStatus}
          onUseSuggestion={(s) => { slugTouched.current = true; up('slug')(s); }}
        />

        {/* Logo drag-and-drop */}
        <LogoDropzone
          headers={headers}
          value={f.logo_url}
          onChange={up('logo_url')}
        />

        <div className="grid grid-cols-2 gap-3">
          <Select label="Timezone" value={f.timezone} onChange={up('timezone')} options={TIMEZONES} testid="mbr-setup-timezone" />
          <Select label="Currency" value={f.currency} onChange={up('currency')} options={['GBP', 'EUR', 'USD', 'AUD', 'CAD', 'NZD']} testid="mbr-setup-currency" />
        </div>

        <SectionLabel>Studio address</SectionLabel>
        <Input label="Address line 1" value={f.address_line1} onChange={up('address_line1')} testid="mbr-setup-addr1" placeholder="123 Studio Way" />
        <Input label="Address line 2 (optional)" value={f.address_line2} onChange={up('address_line2')} testid="mbr-setup-addr2" />
        <div className="grid grid-cols-2 gap-3">
          <Input label="City / Town" value={f.city} onChange={up('city')} testid="mbr-setup-city" />
          <Input label="Postcode" value={f.postcode} onChange={up('postcode')} testid="mbr-setup-postcode" />
        </div>
        <Select label="Country" value={f.country} onChange={up('country')} options={COUNTRIES} testid="mbr-setup-country" />

        <SectionLabel>Contact for members</SectionLabel>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Email" type="email" value={f.contact_email} onChange={up('contact_email')} testid="mbr-setup-contact-email" placeholder="hello@studio.com" />
          <Input label="Phone" value={f.contact_phone} onChange={up('contact_phone')} testid="mbr-setup-contact-phone" placeholder="+44 1234 567890" />
        </div>

        <SectionLabel>Brand</SectionLabel>
        <div className="flex items-center gap-3">
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.75)' }}>Brand colour</span>
            <input type="color" value={f.primary_brand_colour} onChange={(e) => up('primary_brand_colour')(e.target.value)} className="mt-1 h-10 w-16 rounded cursor-pointer bg-transparent" data-testid="mbr-setup-colour" />
          </label>
          <div className="flex-1 text-xs" style={{ color: 'rgba(255,255,255,0.55)' }}>
            Used for buttons + accents on your member app.
          </div>
        </div>

        <StepActions primaryLabel="Save & continue" saving={saving} testId="mbr-setup-basics-next" />
      </form>
    </StepShell>
  );
}

function SlugField({ value, onChange, status, onUseSuggestion }) {
  const portal = typeof window !== 'undefined' ? window.location.origin : '';
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'rgba(255,255,255,0.75)' }}>Your member app address</span>
      <div className="mt-1 flex rounded-lg overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.18)' }}>
        <span className="px-3 py-2.5 text-xs font-mono whitespace-nowrap" style={{ color: 'rgba(255,255,255,0.5)', background: 'rgba(255,255,255,0.04)' }}>
          {portal.replace(/^https?:\/\//, '')}/m/
        </span>
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 px-3 py-2.5 text-sm focus:outline-none"
          style={{ background: 'transparent', color: '#fff' }}
          data-testid="mbr-setup-slug"
          placeholder="your-studio"
        />
        <span className="px-3 py-2.5 grid place-items-center" style={{ background: 'rgba(255,255,255,0.04)' }} data-testid="mbr-setup-slug-status">
          {status.checking ? <Loader2 size={14} className="animate-spin" style={{ color: 'rgba(255,255,255,0.4)' }} />
            : status.available === true ? <Check size={14} style={{ color: '#10b981' }} />
            : status.available === false ? <AlertCircle size={14} style={{ color: '#f59e0b' }} />
            : null}
        </span>
      </div>
      <span className="text-[11px] mt-1 block" style={{ color: 'rgba(255,255,255,0.55)' }}>
        Members will visit this URL to book, pay and check in. Use letters, numbers and hyphens.
      </span>
      {status.available === false && status.suggestion && (
        <button
          type="button"
          onClick={() => onUseSuggestion(status.suggestion)}
          className="text-[11px] font-bold mt-1 underline"
          style={{ color: 'var(--color-brand-cyan)' }}
          data-testid="mbr-setup-slug-use-suggestion"
        >
          That one&apos;s taken — use &ldquo;{status.suggestion}&rdquo; instead
        </button>
      )}
    </label>
  );
}

function LogoDropzone({ headers, value, onChange }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);

  const handleFile = async (file) => {
    if (!file) return;
    if (!/^image\/(png|jpe?g|svg\+xml|webp)/.test(file.type)) {
      notify.error('Please choose a PNG, JPEG, SVG or WEBP image.');
      return;
    }
    setUploading(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const { data } = await axios.post(`${API}/account/logo`, fd, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      });
      const url = data?.logo_url || data?.url || '';
      if (url) onChange(url);
      notify.success('Logo uploaded');
    } catch (e) {
      notifyApiError(notify, e, 'Logo upload failed');
    } finally { setUploading(false); }
  };

  return (
    <div>
      <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'rgba(255,255,255,0.75)' }}>Studio logo</span>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files?.[0]); }}
        onClick={() => inputRef.current?.click()}
        className="mt-1 rounded-xl p-4 cursor-pointer transition flex items-center gap-3"
        style={{
          background: dragging ? 'rgba(25,205,255,0.08)' : 'rgba(255,255,255,0.04)',
          border: `1.5px dashed ${dragging ? 'var(--color-brand-cyan)' : 'rgba(255,255,255,0.22)'}`,
        }}
        data-testid="mbr-setup-logo-drop"
      >
        {value ? (
          <img src={value.startsWith('http') ? value : `${BACKEND_URL}${value}`} alt="logo" className="h-14 w-14 rounded-lg object-cover" style={{ background: '#fff' }} />
        ) : (
          <div className="h-14 w-14 rounded-lg grid place-items-center" style={{ background: 'rgba(255,255,255,0.08)' }}>
            <ImageIcon size={20} style={{ color: 'rgba(255,255,255,0.5)' }} />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold" style={{ color: '#fff' }}>
            {value ? 'Replace logo' : 'Drop your logo here or click to choose'}
          </p>
          <p className="text-[11px] mt-0.5" style={{ color: 'rgba(255,255,255,0.55)' }}>
            PNG, JPEG, SVG or WEBP. Square works best — appears on your portal, emails and invoices.
          </p>
        </div>
        {uploading
          ? <Loader2 size={16} className="animate-spin" style={{ color: 'var(--color-brand-cyan)' }} />
          : <Upload size={16} style={{ color: 'rgba(255,255,255,0.6)' }} />}
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/svg+xml,image/webp"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
          data-testid="mbr-setup-logo-input"
        />
      </div>
    </div>
  );
}


/* ─────────────────── Step 2 — Payment Method (dark-mode safe) ─────────────────── */

function PaymentMethod({ headers, status, onNext, onBack }) {
  const [choice, setChoice] = useState(status.organization.payment_method || 'manual');
  const [saving, setSaving] = useState(false);
  const options = [
    { id: 'manual',         label: 'Manual / Cash / Invoice',   icon: Banknote,     desc: 'Collect any way you like. Staff record payments in the app. Available now.', soon: false },
    { id: 'direct_debit',   label: 'Direct Debit (GoCardless)', icon: LinkIcon,     desc: 'Auto-collect monthly DD mandates. Recurring, bank-level fees.',             soon: true },
    { id: 'stripe_connect', label: 'Stripe Connect',            icon: CreditCard,   desc: 'Members pay card — funds land in YOUR Stripe account, not ours.',         soon: true },
  ];
  const save = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/setup/payment-method`, { payment_method: choice }, { headers });
      notify.success('Payment method saved');
      onNext();
    } catch (err) { notifyApiError(notify, err, 'Failed'); }
    finally { setSaving(false); }
  };
  return (
    <StepShell title="How will you collect from members?" subtitle="You can change this any time.">
      <div className="space-y-2" data-testid="mbr-setup-payment">
        {options.map((o) => {
          const active = choice === o.id;
          // Iter 216h252 — explicit rgba colours so the cards stay dark
          // even when the surrounding tenant runs the Pulse-light theme.
          return (
            <button
              key={o.id}
              onClick={() => setChoice(o.id)}
              data-testid={`mbr-setup-pay-${o.id}`}
              className="w-full text-left rounded-xl p-4 transition flex items-start gap-3"
              style={{
                background: active ? 'rgba(25,205,255,0.10)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${active ? 'var(--color-brand-cyan)' : 'rgba(255,255,255,0.14)'}`,
              }}
            >
              <o.icon size={18} style={{ color: active ? 'var(--color-brand-cyan)' : 'rgba(255,255,255,0.65)' }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-sm" style={{ color: '#fff' }}>{o.label}</span>
                  {o.soon && (
                    <span className="text-[9px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded" style={{ background: 'rgba(245,158,11,0.18)', color: '#fcd34d' }}>
                      Soon
                    </span>
                  )}
                </div>
                <div className="text-xs mt-0.5" style={{ color: 'rgba(255,255,255,0.65)' }}>{o.desc}</div>
              </div>
            </button>
          );
        })}
      </div>
      <StepActions onBack={onBack} primaryLabel="Save & continue" onPrimary={save} saving={saving} testId="mbr-setup-payment-next" />
    </StepShell>
  );
}


/* ─────────────────── Step 3 — Starter plans ─────────────────── */

const STARTER_PLANS = [
  { name: 'Monthly Unlimited', kind: 'recurring',  billing_cycle: 'monthly', price_pence: 5000, included_classes: 'unlimited', colour: 'var(--color-brand-cyan)', display_order: 1 },
  { name: '10-Class Pack',     kind: 'class_pack', billing_cycle: 'one_off', price_pence: 9000, included_classes: 10,          colour: '#a855f7',                  display_order: 2 },
  { name: 'Drop-in',           kind: 'drop_in',    billing_cycle: 'one_off', price_pence: 1200, included_classes: 1,           colour: '#f59e0b',                  display_order: 3 },
];

function StarterPlans({ headers, status: _s, onNext, onBack }) {
  const [selected, setSelected] = useState([0, 1, 2]);
  const [saving, setSaving] = useState(false);
  const toggle = (idx) => setSelected((p) => p.includes(idx) ? p.filter((x) => x !== idx) : [...p, idx]);
  const save = async () => {
    setSaving(true);
    try {
      const plans = selected.map((i) => STARTER_PLANS[i]);
      await axios.post(`${API}/memberships/setup/plans`, { plans }, { headers });
      notify.success(`${plans.length} plans created`);
      onNext();
    } catch (err) { notifyApiError(notify, err, 'Failed'); }
    finally { setSaving(false); }
  };
  return (
    <StepShell title="Pick starter plans" subtitle="Tick what you'd like to offer. Edit prices any time.">
      <div className="space-y-2" data-testid="mbr-setup-plans">
        {STARTER_PLANS.map((p, idx) => {
          const on = selected.includes(idx);
          return (
            <div key={p.name} onClick={() => toggle(idx)} data-testid={`mbr-setup-plan-${idx}`}
              className="cursor-pointer rounded-xl p-4 flex items-center gap-3 transition"
              style={{
                background: on ? 'rgba(25,205,255,0.10)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${on ? 'var(--color-brand-cyan)' : 'rgba(255,255,255,0.14)'}`,
              }}>
              <span className="w-3 h-3 rounded-full" style={{ background: p.colour }} />
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm" style={{ color: '#fff' }}>{p.name}</div>
                <div className="text-xs" style={{ color: 'rgba(255,255,255,0.6)' }}>£{(p.price_pence / 100).toFixed(2)} · {p.kind.replace('_', ' ')} · {p.billing_cycle}</div>
              </div>
            </div>
          );
        })}
      </div>
      <StepActions onBack={onBack} primaryLabel={selected.length ? `Create ${selected.length} plans` : 'Skip'}
        onPrimary={save} saving={saving} testId="mbr-setup-plans-next" />
    </StepShell>
  );
}


/* ─────────────────── Step 4 — Instructor (NEW, functional) ─────────────────── */

function InstructorStep({ headers, status: _s, onNext, onBack }) {
  const [f, setF] = useState({
    name: '', email: '', phone: '', headline: 'Lead instructor', specialties: '',
    gdpr_consent: false,
  });
  const [saving, setSaving] = useState(false);
  const up = (k) => (v) => setF((p) => ({ ...p, [k]: v }));

  const skip = () => onNext();
  const save = async () => {
    if (!f.name.trim()) { notify.error('Instructor name required'); return; }
    if (!f.email.trim()) { notify.error('Email required'); return; }
    if (!f.phone.trim()) { notify.error('Phone required'); return; }
    if (!f.gdpr_consent) { notify.error('GDPR consent required to add an instructor'); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/instructors`, {
        name: f.name.trim(),
        email: f.email.trim(),
        phone: f.phone.trim(),
        headline: f.headline.trim() || null,
        specialties: f.specialties.split(',').map((s) => s.trim()).filter(Boolean),
        is_published: true,
        gdpr_consent: true,
      }, { headers });
      notify.success('Instructor added');
      onNext();
    } catch (err) { notifyApiError(notify, err, 'Failed'); }
    finally { setSaving(false); }
  };

  return (
    <StepShell title="Add your first instructor" subtitle="They'll appear on your member-app's class screens. You can invite more later.">
      <div className="space-y-3" data-testid="mbr-setup-instructor">
        <Input label="Full name" value={f.name} onChange={up('name')} required testid="mbr-setup-instructor-name" placeholder="e.g. Bella Carter" />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Email" type="email" value={f.email} onChange={up('email')} required testid="mbr-setup-instructor-email" />
          <Input label="Phone" value={f.phone} onChange={up('phone')} required testid="mbr-setup-instructor-phone" />
        </div>
        <Input label="Headline" value={f.headline} onChange={up('headline')} testid="mbr-setup-instructor-headline" placeholder="e.g. Ballet & Contemporary lead" />
        <Input label="Specialties (comma-separated)" value={f.specialties} onChange={up('specialties')} testid="mbr-setup-instructor-specialties" placeholder="Ballet, Contemporary, Jazz" />
        <label className="flex items-start gap-2 mt-2 cursor-pointer" data-testid="mbr-setup-instructor-gdpr-row">
          <input type="checkbox" checked={f.gdpr_consent} onChange={(e) => up('gdpr_consent')(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[color:var(--color-brand-cyan)]" data-testid="mbr-setup-instructor-gdpr" />
          <span className="text-[11px]" style={{ color: 'rgba(255,255,255,0.7)' }}>
            I confirm this instructor consents to having their name, photo and contact details
            processed for payroll, member-app display and class scheduling.
          </span>
        </label>
      </div>
      <div className="flex items-center justify-between gap-3 mt-6">
        <button onClick={onBack} className="text-xs font-bold" style={{ color: 'rgba(255,255,255,0.6)' }}><ChevronLeft size={12} className="inline" /> Back</button>
        <div className="flex gap-2">
          <button onClick={skip} className="rounded-lg px-3 py-2 text-xs font-bold" style={{ border: '1px solid rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.8)' }} data-testid="mbr-setup-instructor-skip">Skip</button>
          <button onClick={save} disabled={saving} className="rounded-lg px-4 py-2 text-xs font-extrabold uppercase tracking-wider disabled:opacity-50"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="mbr-setup-instructor-next">
            {saving ? '…' : 'Add instructor'} <ChevronRight size={12} className="inline ml-1" />
          </button>
        </div>
      </div>
    </StepShell>
  );
}


/* ─────────────────── Step 5 — First class (with instructor dropdown) ─────────────────── */

const DAYS = [{ v: 0, l: 'Mon' }, { v: 1, l: 'Tue' }, { v: 2, l: 'Wed' }, { v: 3, l: 'Thu' }, { v: 4, l: 'Fri' }, { v: 5, l: 'Sat' }, { v: 6, l: 'Sun' }];

function FirstClass({ headers, _status, onNext, onBack }) {
  const [instructors, setInstructors] = useState([]);
  const [f, setF] = useState({
    name: '', category: 'Group', duration_min: 45, capacity: 20,
    recurs_days: [0, 2, 4], start_time: '18:00', colour: '#ef4444',
    instructor_id: '', instructor_name: '', room_name: 'Studio 1', credits_to_book: 1,
    waitlist_enabled: true, max_waitlist: 10,
    booking_opens_hours_before: 168, cancellation_cutoff_hours_before: 12,
  });
  const [saving, setSaving] = useState(false);
  const up = (k) => (v) => setF((p) => ({ ...p, [k]: v }));

  // Iter 216h252 — load instructors so the class step exposes them as
  // a dropdown rather than a free-text field. Same UX as the
  // ClassTemplateEditor in the Studio Builder tab.
  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/memberships/instructors`, { headers })
      .then((r) => {
        if (cancelled) return;
        const list = r.data?.instructors || r.data || [];
        setInstructors(list);
        // Pre-select the first instructor if exactly one exists (likely
        // the one just added in Step 4).
        if (list.length === 1) {
          setF((p) => ({ ...p, instructor_id: list[0].id, instructor_name: list[0].name }));
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [headers]);

  const onInstructorChange = (val) => {
    if (val === '__custom__') {
      setF((p) => ({ ...p, instructor_id: '', instructor_name: '' }));
      return;
    }
    const match = instructors.find((i) => i.id === val);
    setF((p) => ({ ...p, instructor_id: val, instructor_name: match?.name || '' }));
  };

  const toggleDay = (d) => up('recurs_days')(f.recurs_days.includes(d) ? f.recurs_days.filter((x) => x !== d) : [...f.recurs_days, d].sort());
  const skip = () => onNext();
  const save = async () => {
    if (!f.name.trim()) { notify.error('Class name required'); return; }
    if (f.recurs_days.length === 0) { notify.error('Pick at least one day'); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/classes/templates`, {
        ...f,
        duration_min: Number(f.duration_min), capacity: Number(f.capacity),
        credits_to_book: Number(f.credits_to_book),
      }, { headers });
      notify.success('Class created · 8 weeks of occurrences generated');
      onNext();
    } catch (err) { notifyApiError(notify, err, 'Failed'); }
    finally { setSaving(false); }
  };

  return (
    <StepShell title="Add your first class" subtitle="Optional — you can add classes any time from the timetable.">
      <div className="space-y-3" data-testid="mbr-setup-class">
        <Input label="Class name" value={f.name} onChange={up('name')} testid="mbr-setup-class-name" placeholder="e.g. Ballet — Intermediate" />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Category" value={f.category} onChange={up('category')} testid="mbr-setup-class-category" />
          <Input label="Start time" type="time" value={f.start_time} onChange={up('start_time')} testid="mbr-setup-class-time" />
        </div>
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.75)' }}>Days</span>
          <div className="flex gap-1.5 mt-1 flex-wrap">
            {DAYS.map((d) => {
              const on = f.recurs_days.includes(d.v);
              return (
                <button key={d.v} type="button" onClick={() => toggleDay(d.v)}
                  className="px-3 py-1.5 rounded-lg text-xs font-extrabold uppercase transition"
                  style={{
                    background: on ? 'var(--color-brand-cyan)' : 'transparent',
                    color: on ? 'var(--color-surface-darker)' : 'rgba(255,255,255,0.65)',
                    border: on ? 'none' : '1px solid rgba(255,255,255,0.15)',
                  }}
                  data-testid={`mbr-setup-class-day-${d.v}`}>
                  {d.l}
                </button>
              );
            })}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Input label="Duration (min)" type="number" value={f.duration_min} onChange={up('duration_min')} testid="mbr-setup-class-dur" />
          <Input label="Capacity" type="number" value={f.capacity} onChange={up('capacity')} testid="mbr-setup-class-cap" />
          <Input label="Credits" type="number" value={f.credits_to_book} onChange={up('credits_to_book')} testid="mbr-setup-class-credits" />
        </div>

        {/* Iter 216h252 — instructor DROPDOWN with "Other / custom" escape hatch. */}
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'rgba(255,255,255,0.75)' }}>Instructor</span>
          <select
            value={f.instructor_id || (f.instructor_name ? '__custom__' : '')}
            onChange={(e) => onInstructorChange(e.target.value)}
            className="mt-1 w-full rounded-lg px-3 py-2.5 text-sm focus:outline-none"
            style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.18)', color: '#fff' }}
            data-testid="mbr-setup-class-instructor-select"
          >
            <option value="" style={{ background: '#0a0c10' }}>— Select instructor —</option>
            {instructors.map((i) => (
              <option key={i.id} value={i.id} style={{ background: '#0a0c10' }}>{i.name}</option>
            ))}
            <option value="__custom__" style={{ background: '#0a0c10' }}>Type custom name…</option>
          </select>
          {f.instructor_id === '' && (f.instructor_name !== '' || (!instructors.length)) && (
            <input
              value={f.instructor_name}
              onChange={(e) => up('instructor_name')(e.target.value)}
              placeholder="Instructor name"
              className="mt-2 w-full rounded-lg px-3 py-2.5 text-sm focus:outline-none"
              style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.18)', color: '#fff' }}
              data-testid="mbr-setup-class-instructor-custom"
            />
          )}
        </label>
      </div>
      <div className="flex items-center justify-between gap-3 mt-6">
        <button onClick={onBack} className="text-xs font-bold" style={{ color: 'rgba(255,255,255,0.6)' }}><ChevronLeft size={12} className="inline" /> Back</button>
        <div className="flex gap-2">
          <button onClick={skip} className="rounded-lg px-3 py-2 text-xs font-bold" style={{ border: '1px solid rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.8)' }} data-testid="mbr-setup-class-skip">Skip</button>
          <button onClick={save} disabled={saving} className="rounded-lg px-4 py-2 text-xs font-extrabold uppercase tracking-wider disabled:opacity-50"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="mbr-setup-class-next">
            {saving ? '…' : 'Save & continue'} <ChevronRight size={12} className="inline ml-1" />
          </button>
        </div>
      </div>
    </StepShell>
  );
}


/* ─────────────────── Step 6 — Done ─────────────────── */

function AllDone({ headers, status, onFinish }) {
  const org = status.organization;
  const appUrl = `${window.location.origin}/m/${org.slug}`;
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (done) return;
    axios.post(`${API}/memberships/setup/complete`, {}, { headers })
      .then(() => setDone(true)).catch(() => {});
  }, [headers, done]);
  const copy = async () => {
    try { await navigator.clipboard.writeText(appUrl); notify.success('Link copied'); }
    catch { window.prompt('Share your app URL:', appUrl); }
  };
  return (
    <StepShell title="You're live." subtitle="Share the link below with your members — they'll land on your branded app.">
      <div className="rounded-2xl p-6 text-center" style={{ background: 'rgba(25,205,255,0.06)', border: '1px solid rgba(25,205,255,0.3)' }} data-testid="mbr-setup-done">
        <div className="w-16 h-16 rounded-full mx-auto grid place-items-center mb-4" style={{ background: 'rgba(16,185,129,0.2)' }}>
          <CheckCircle2 style={{ color: '#6ee7b7' }} size={32} />
        </div>
        <h3 className="text-2xl font-extrabold tracking-tight" style={{ color: '#fff' }}>All set, {org.name}</h3>
        <p className="text-sm mt-2" style={{ color: 'rgba(255,255,255,0.6)' }}>Your members can book, pay, and check in — all from the link below.</p>
        <div className="mt-5 rounded-xl p-4" style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.1)' }}>
          <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold mb-1" style={{ color: 'var(--color-brand-cyan)' }}>Your app URL</div>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-left text-sm font-mono truncate" style={{ color: '#fff' }} data-testid="mbr-setup-app-url">{appUrl}</code>
            <button onClick={copy} className="p-2 rounded-lg" style={{ color: 'rgba(255,255,255,0.7)' }} data-testid="mbr-setup-copy"><Copy size={14} /></button>
          </div>
        </div>
      </div>
      <StepActions primaryLabel="Open my dashboard" onPrimary={onFinish} testId="mbr-setup-finish" />
    </StepShell>
  );
}


/* ─────────────────── Step shell & helpers ─────────────────── */

function StepShell({ title, subtitle, children }) {
  return (
    <div>
      <h1 className="text-3xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.025em', color: '#ffffff' }}>{title}</h1>
      {subtitle && <p className="text-sm mt-2" style={{ color: 'rgba(255,255,255,0.7)' }}>{subtitle}</p>}
      <div className="mt-6">{children}</div>
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div className="pt-2 mt-2 border-t" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
      <span className="text-[9px] font-extrabold uppercase tracking-[0.3em]" style={{ color: 'rgba(255,255,255,0.45)' }}>{children}</span>
    </div>
  );
}

function StepActions({ onBack, primaryLabel, onPrimary, saving, testId }) {
  return (
    <div className="flex items-center justify-between gap-3 mt-6">
      {onBack ? (
        <button onClick={onBack} className="text-xs font-bold" style={{ color: 'rgba(255,255,255,0.6)' }} data-testid="mbr-setup-back">
          <ChevronLeft size={12} className="inline" /> Back
        </button>
      ) : <span />}
      <button
        {...(onPrimary ? { onClick: onPrimary } : { type: 'submit' })}
        disabled={saving}
        className="rounded-lg px-5 py-2.5 text-xs font-extrabold uppercase tracking-wider disabled:opacity-50"
        style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
        data-testid={testId}
      >
        {saving ? '…' : primaryLabel} <ChevronRight size={12} className="inline ml-1" />
      </button>
    </div>
  );
}

function Input({ label, value, onChange, type = 'text', required, testid, hint, placeholder }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'rgba(255,255,255,0.75)' }}>{label}{required ? ' *' : ''}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        placeholder={placeholder}
        className="mt-1 w-full rounded-lg px-3 py-2.5 text-sm focus:outline-none"
        style={{
          background: 'rgba(255,255,255,0.06)',
          border: '1px solid rgba(255,255,255,0.18)',
          color: '#ffffff',
        }}
        data-testid={testid}
      />
      {hint && <span className="text-[10px] mt-1 block" style={{ color: 'rgba(255,255,255,0.5)' }}>{hint}</span>}
    </label>
  );
}

function Select({ label, value, onChange, options, testid }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'rgba(255,255,255,0.75)' }}>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testid}
        className="mt-1 w-full rounded-lg px-3 py-2.5 text-sm focus:outline-none"
        style={{
          background: 'rgba(255,255,255,0.06)',
          border: '1px solid rgba(255,255,255,0.18)',
          color: '#ffffff',
        }}
      >
        {options.map((o) => <option key={o} value={o} style={{ background: '#0a0c10', color: '#fff' }}>{o}</option>)}
      </select>
    </label>
  );
}

function FullPageLoader() {
  return (
    <div className="min-h-screen grid place-items-center" style={{ background: '#07090E' }}>
      <Loader2 className="animate-spin" style={{ color: 'var(--color-brand-cyan)' }} />
    </div>
  );
}

// Sparkles / UserPlus / Banknote are imported above for potential future
// step illustrations. Keeping the imports avoids a lint regression if a
// future iteration re-introduces them.
export const _ICON_USAGES = { Sparkles, UserPlus, Banknote };
