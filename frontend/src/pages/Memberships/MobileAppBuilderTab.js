/**
 * Mobile App Builder — drag-drop the cards your members see in the app.
 *
 * Owners and managers can:
 *   • Re-order cards (HTML5 native drag-and-drop, no extra deps).
 *   • Toggle cards on/off.
 *   • Tweak per-card settings (bool / number / text / select).
 *   • See a live mobile-frame preview that mirrors the saved layout.
 *
 * Persists via /api/member-app/* endpoints (router: member_app_builder.py).
 * The MemberPortal reads the same layout to render the actual mobile app.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
  GripVertical, Plus, Eye, EyeOff, Settings as SettingsIcon, RotateCcw, Save,
  Smartphone, ChevronDown, ChevronUp, Trash2, Copy, ExternalLink, Link2,
  // Card icons (must mirror CARD_REGISTRY.icon strings on the backend)
  CalendarDays, ClipboardList, Dumbbell, Wrench, Trophy, Activity,
  ShoppingBag, BarChart3, Megaphone, QrCode, Share2, Sparkles,
} from 'lucide-react';
import EmptyState from '@/components/shared/EmptyState';
import QRCode from 'qrcode';

const ICONS = {
  CalendarDays, ClipboardList, Dumbbell, Wrench, Trophy, Activity,
  ShoppingBag, BarChart3, Megaphone, QrCode, Share2, Sparkles,
};

const CardIcon = ({ name, className }) => {
  const Cmp = ICONS[name] || Sparkles;
  return <Cmp className={className} />;
};

export default function MobileAppBuilderTab({ API, headers }) {
  const [registry, setRegistry] = useState([]);
  const [cards, setCards] = useState([]);
  const [accountType, setAccountType] = useState(null);
  const [appSlug, setAppSlug] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [expandedKey, setExpandedKey] = useState(null);
  const dragIndex = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [reg, lay] = await Promise.all([
        axios.get(`${API}/member-app/cards`, { headers }),
        axios.get(`${API}/member-app/layout`, { headers }),
      ]);
      setRegistry(reg.data?.cards || []);
      setCards(lay.data?.layout?.cards || []);
      setAccountType(lay.data?.account_type || null);
      setAppSlug(lay.data?.app_slug || null);
      setDirty(false);
    } catch (e) {
      notify.error('Failed to load mobile app layout');
    } finally {
      setLoading(false);
    }
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const registryById = useMemo(() => {
    const m = {};
    registry.forEach((c) => { m[c.id] = c; });
    return m;
  }, [registry]);

  const availableToAdd = useMemo(() => {
    const used = new Set(cards.map((c) => c.type));
    return registry.filter((c) => !used.has(c.id));
  }, [registry, cards]);

  const updateCard = (idx, patch) => {
    setCards((prev) => prev.map((c, i) => (i === idx ? { ...c, ...patch } : c)));
    setDirty(true);
  };

  const updateSetting = (idx, key, value) => {
    setCards((prev) => prev.map((c, i) => (
      i === idx ? { ...c, settings: { ...(c.settings || {}), [key]: value } } : c
    )));
    setDirty(true);
  };

  const removeCard = (idx) => {
    setCards((prev) => prev.filter((_, i) => i !== idx));
    setDirty(true);
  };

  const addCard = (type) => {
    const spec = registryById[type];
    if (!spec) return;
    const defaults = {};
    (spec.settings_schema || []).forEach((s) => { defaults[s.key] = s.default; });
    setCards((prev) => [...prev, { type, enabled: true, settings: defaults, position: prev.length }]);
    setDirty(true);
  };

  // ── HTML5 drag-and-drop ──
  const onDragStart = (idx) => (e) => {
    dragIndex.current = idx;
    e.dataTransfer.effectAllowed = 'move';
    // Firefox needs data set on the drag event
    try { e.dataTransfer.setData('text/plain', String(idx)); } catch {}
  };
  const onDragOver = (_idx) => (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };
  const onDrop = (idx) => (e) => {
    e.preventDefault();
    const from = dragIndex.current;
    dragIndex.current = null;
    if (from == null || from === idx) return;
    setCards((prev) => {
      const copy = [...prev];
      const [moved] = copy.splice(from, 1);
      copy.splice(idx, 0, moved);
      return copy;
    });
    setDirty(true);
  };

  const move = (idx, dir) => {
    const target = idx + dir;
    if (target < 0 || target >= cards.length) return;
    setCards((prev) => {
      const copy = [...prev];
      [copy[idx], copy[target]] = [copy[target], copy[idx]];
      return copy;
    });
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/member-app/layout`, { name: 'Default', cards }, { headers });
      notify.success('Mobile layout saved');
      setDirty(false);
    } catch (e) {
      notifyApiError(notify, e, 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    if (!window.confirm('Reset to the platform default layout? Your customisations will be lost.')) return;
    setSaving(true);
    try {
      const r = await axios.post(`${API}/member-app/layout/reset`, {}, { headers });
      setCards(r.data?.layout?.cards || []);
      setDirty(false);
      notify.success('Layout reset');
    } catch {
      notify.error('Reset failed');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-sm" style={{ color: 'var(--theme-text-muted)' }}>Loading…</div>;
  }

  return (
    <div data-testid="mobile-app-builder" className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* ── Header / actions ── */}
      <div className="lg:col-span-12 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)' }}>
            Member experience
          </div>
          <h2 className="text-2xl font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>
            Mobile App Builder
          </h2>
          <p className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>
            Drag the cards your members see when they open your mobile app. Toggle, re-order, configure.
            {accountType ? ` · Plan: ${accountType}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={reset}
            disabled={saving}
            data-testid="mab-reset-btn"
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm border"
            style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
          >
            <RotateCcw className="w-4 h-4" /> Reset
          </button>
          <button
            onClick={save}
            disabled={saving || !dirty}
            data-testid="mab-save-btn"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-50"
            style={{ background: dirty ? 'var(--color-brand-cyan)' : 'var(--theme-surface)', color: dirty ? 'var(--color-ink)' : 'var(--theme-text-muted)', border: dirty ? 'none' : '1px solid var(--theme-border)' }}
          >
            <Save className="w-4 h-4" /> {saving ? 'Saving…' : (dirty ? 'Save layout' : 'Saved')}
          </button>
        </div>
      </div>

      {/* ── App address (public member-app link) ── */}
      <div className="lg:col-span-12">
        <AppAddressCard slug={appSlug} />
      </div>

      {/* ── Layout list ── */}
      <div className="lg:col-span-7 space-y-3">
        <div className="text-xs font-medium uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)' }}>
          Layout · {cards.length} card{cards.length === 1 ? '' : 's'}
        </div>
        {cards.length === 0 && (
          <EmptyState
            icon={Smartphone}
            title="Your members' home screen is blank"
            hint="Pick a card below — Timetable, Live faults, Class league — and drag to reorder. Members see this exact layout on iOS, Android and the web app."
            testId="mab-empty-state"
          />
        )}
        {cards.map((card, idx) => {
          const spec = registryById[card.type];
          if (!spec) return null;
          const isOpen = expandedKey === card.type;
          return (
            <div
              key={card.type}
              draggable
              onDragStart={onDragStart(idx)}
              onDragOver={onDragOver(idx)}
              onDrop={onDrop(idx)}
              className="rounded-xl border transition-shadow hover:shadow-md"
              style={{
                background: 'var(--theme-surface)',
                borderColor: 'var(--theme-border)',
                opacity: card.enabled ? 1 : 0.55,
              }}
              data-testid={`mab-card-${card.type}`}
            >
              <div className="flex items-center gap-3 p-3">
                <div className="cursor-grab active:cursor-grabbing touch-none p-1" title="Drag to reorder">
                  <GripVertical className="w-5 h-5" style={{ color: 'var(--theme-text-muted)' }} />
                </div>
                <div
                  className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                  style={{ background: 'rgba(25,205,255,0.1)', color: 'var(--color-brand-cyan)' }}
                >
                  <CardIcon name={spec.icon} className="w-5 h-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate" style={{ color: 'var(--theme-text)' }}>
                    {spec.title}
                  </div>
                  <div className="text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>
                    {spec.description}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => move(idx, -1)}
                    disabled={idx === 0}
                    className="p-2 rounded-md disabled:opacity-30"
                    title="Move up"
                    data-testid={`mab-up-${card.type}`}
                  >
                    <ChevronUp className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => move(idx, 1)}
                    disabled={idx === cards.length - 1}
                    className="p-2 rounded-md disabled:opacity-30"
                    title="Move down"
                    data-testid={`mab-down-${card.type}`}
                  >
                    <ChevronDown className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => updateCard(idx, { enabled: !card.enabled })}
                    className="p-2 rounded-md"
                    title={card.enabled ? 'Disable card' : 'Enable card'}
                    data-testid={`mab-toggle-${card.type}`}
                  >
                    {card.enabled ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                  </button>
                  {(spec.settings_schema || []).length > 0 && (
                    <button
                      onClick={() => setExpandedKey(isOpen ? null : card.type)}
                      className="p-2 rounded-md"
                      title="Settings"
                      data-testid={`mab-settings-${card.type}`}
                    >
                      <SettingsIcon className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={() => removeCard(idx)}
                    className="p-2 rounded-md hover:text-red-500"
                    title="Remove"
                    data-testid={`mab-remove-${card.type}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              {isOpen && (spec.settings_schema || []).length > 0 && (
                <div
                  className="border-t px-4 py-3 space-y-3"
                  style={{ borderColor: 'var(--theme-border)' }}
                >
                  {spec.settings_schema.map((s) => (
                    <SettingField
                      key={s.key}
                      schema={s}
                      value={card.settings?.[s.key] ?? s.default}
                      onChange={(v) => updateSetting(idx, s.key, v)}
                      testid={`mab-${card.type}-${s.key}`}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {/* ── Add card picker ── */}
        {availableToAdd.length > 0 && (
          <div
            className="rounded-xl border p-4"
            style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
          >
            <div className="text-xs font-medium uppercase tracking-wide mb-3" style={{ color: 'var(--theme-text-muted)' }}>
              Add a card
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {availableToAdd.map((c) => (
                <button
                  key={c.id}
                  onClick={() => addCard(c.id)}
                  className="flex items-start gap-3 p-3 rounded-lg border text-left hover:border-[var(--color-brand-cyan)]"
                  style={{ borderColor: 'var(--theme-border)' }}
                  data-testid={`mab-add-${c.id}`}
                >
                  <div
                    className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: 'rgba(25,205,255,0.1)', color: 'var(--color-brand-cyan)' }}
                  >
                    <CardIcon name={c.icon} className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-medium" style={{ color: 'var(--theme-text)' }}>
                      {c.title}
                      {c.pulse_only && (
                        <span className="ml-2 text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded" style={{ background: 'rgba(25,205,255,0.15)', color: 'var(--color-brand-cyan)' }}>
                          Pulse
                        </span>
                      )}
                    </div>
                    <div className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                      {c.description}
                    </div>
                  </div>
                  <Plus className="w-4 h-4 ml-auto flex-shrink-0" style={{ color: 'var(--theme-text-muted)' }} />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Live preview ── */}
      <div className="lg:col-span-5">
        <div className="sticky top-24">
          <div className="text-xs font-medium uppercase tracking-wide mb-3 flex items-center gap-2" style={{ color: 'var(--theme-text-muted)' }}>
            <Smartphone className="w-3.5 h-3.5" /> Live preview
          </div>
          <PhoneFrame>
            <div className="space-y-3" data-testid="mab-preview">
              {cards.filter((c) => c.enabled).length === 0 && (
                <div className="text-center text-xs py-12" style={{ color: '#64748b' }}>
                  Empty home screen.<br />Add and enable cards to see them here.
                </div>
              )}
              {cards.filter((c) => c.enabled).map((card) => {
                const spec = registryById[card.type];
                if (!spec) return null;
                return (
                  <div
                    key={card.type}
                    className="rounded-xl p-3"
                    style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}
                    data-testid={`mab-preview-${card.type}`}
                  >
                    <div className="flex items-center gap-2.5">
                      <div
                        className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                        style={{ background: 'rgba(25,205,255,0.15)', color: 'var(--color-brand-cyan)' }}
                      >
                        <CardIcon name={spec.icon} className="w-4 h-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-semibold text-white truncate">{spec.title}</div>
                        <div className="text-[10px] truncate" style={{ color: 'rgba(255,255,255,0.5)' }}>
                          {spec.description}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </PhoneFrame>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────── App address (public member-app link) ─────────────────── */

function AppAddressCard({ slug }) {
  const [qr, setQr] = useState(null);
  const [copied, setCopied] = useState(false);
  const url = slug ? `${window.location.origin}/m/${slug}` : null;

  useEffect(() => {
    if (!url) { setQr(null); return; }
    QRCode.toDataURL(url, { width: 220, margin: 1 }).then(setQr).catch(() => setQr(null));
  }, [url]);

  const copy = async () => {
    if (!url) return;
    let ok = false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
        ok = true;
      }
    } catch { /* fall through to legacy copy */ }
    if (!ok) {
      try {
        const ta = document.createElement('textarea');
        ta.value = url;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        ok = document.execCommand('copy');
        ta.remove();
      } catch { ok = false; }
    }
    if (ok) {
      setCopied(true);
      notify.success('App link copied');
      setTimeout(() => setCopied(false), 1800);
    } else {
      notify.error('Could not copy');
    }
  };

  return (
    <div
      className="rounded-xl border p-4 sm:p-5"
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
      data-testid="mab-app-address"
    >
      <div className="flex items-center gap-2 mb-1">
        <Link2 className="w-4 h-4" style={{ color: 'var(--color-brand-cyan)' }} />
        <div className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Your app address</div>
      </div>
      {!slug ? (
        <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }} data-testid="mab-app-address-unset">
          Set your studio&apos;s app URL in <span className="font-semibold">Memberships → Setup → App URL</span> to get a shareable member-app link and QR code.
        </p>
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="min-w-0 flex-1">
            <p className="text-xs mb-2" style={{ color: 'var(--theme-text-muted)' }}>
              Share this link (or the QR code) with your members — it opens your branded mobile app.
            </p>
            <div
              className="rounded-lg border px-3 py-2 text-sm font-mono truncate"
              style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="mab-app-address-url"
            >
              {url}
            </div>
            <div className="flex items-center gap-2 mt-2">
              <button
                onClick={copy}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
                style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}
                data-testid="mab-app-address-copy"
              >
                <Copy className="w-3.5 h-3.5" /> {copied ? 'Copied' : 'Copy link'}
              </button>
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="mab-app-address-open"
              >
                <ExternalLink className="w-3.5 h-3.5" /> Open
              </a>
            </div>
          </div>
          {qr && (
            <img
              src={qr}
              alt="App QR code"
              className="w-28 h-28 rounded-lg bg-white p-1.5 flex-shrink-0"
              data-testid="mab-app-address-qr"
            />
          )}
        </div>
      )}
    </div>
  );
}

/* ─────────────────── Phone frame ─────────────────── */

function PhoneFrame({ children }) {
  return (
    <div
      className="mx-auto rounded-[2rem] p-4 shadow-xl"
      style={{
        width: 280,
        background: '#ffffff',
        border: '8px solid #0f172a',
        minHeight: 540,
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] font-semibold text-slate-900">9:41</div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-1.5 rounded-sm bg-slate-900/70" />
          <div className="w-3 h-1.5 rounded-sm bg-slate-900/70" />
          <div className="w-4 h-2 rounded-sm border border-slate-900/70" />
        </div>
      </div>
      <div className="text-slate-900 text-sm font-semibold mb-3">My gym</div>
      {children}
    </div>
  );
}

/* ─────────────────── Setting field ─────────────────── */

function SettingField({ schema, value, onChange, testid }) {
  const inputStyle = {
    background: 'var(--theme-bg)',
    border: '1px solid var(--theme-border)',
    color: 'var(--theme-text)',
  };
  if (schema.type === 'bool') {
    return (
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
          data-testid={testid}
        />
        <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{schema.label}</span>
      </label>
    );
  }
  if (schema.type === 'number') {
    return (
      <label className="block">
        <span className="text-xs block mb-1" style={{ color: 'var(--theme-text-muted)' }}>{schema.label}</span>
        <input
          type="number"
          value={value ?? ''}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full px-3 py-1.5 rounded text-sm"
          style={inputStyle}
          data-testid={testid}
        />
      </label>
    );
  }
  if (schema.type === 'select') {
    return (
      <label className="block">
        <span className="text-xs block mb-1" style={{ color: 'var(--theme-text-muted)' }}>{schema.label}</span>
        <select
          value={value ?? schema.default}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-3 py-1.5 rounded text-sm"
          style={inputStyle}
          data-testid={testid}
        >
          {(schema.options || []).map((o) => (<option key={o} value={o}>{o}</option>))}
        </select>
      </label>
    );
  }
  // text fallback
  return (
    <label className="block">
      <span className="text-xs block mb-1" style={{ color: 'var(--theme-text-muted)' }}>{schema.label}</span>
      <input
        type="text"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-1.5 rounded text-sm"
        style={inputStyle}
        data-testid={testid}
      />
    </label>
  );
}
