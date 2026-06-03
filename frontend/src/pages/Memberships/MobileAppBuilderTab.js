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
  Smartphone, ChevronDown, ChevronUp, Trash2, Copy, ExternalLink, Link2, Printer, Download,
  Palette, Image as ImageIcon, RefreshCw, Loader2, X, Upload,
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
  const [branding, setBranding] = useState({ primary_brand_colour: '#19CDFF', logo_url: null, hero_image_url: null });
  const [previewMode, setPreviewMode] = useState('live');
  const [previewKey, setPreviewKey] = useState(0);
  const bumpPreview = useCallback(() => setPreviewKey((k) => k + 1), []);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [expandedKey, setExpandedKey] = useState(null);
  const [sharePackOpen, setSharePackOpen] = useState(false);
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
      setBranding(lay.data?.branding || { primary_brand_colour: '#19CDFF', logo_url: null, hero_image_url: null });
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
      bumpPreview();
    } catch (e) {
      notifyApiError(notify, e, 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  // ── Branding & theme (Iter 220q/220r) ──
  const saveBrandField = useCallback(async (patch) => {
    setBranding((b) => ({ ...b, ...patch }));
    try {
      await axios.put(`${API}/member-app/branding`, patch, { headers });
      bumpPreview();
    } catch (e) {
      notifyApiError(notify, e, 'Could not save branding');
    }
  }, [API, headers, bumpPreview]);

  const uploadImage = useCallback(async (kind, file) => {
    if (!file) return;
    if (!/^image\//.test(file.type)) { notify.error('Please choose an image file'); return; }
    const fd = new FormData();
    fd.append('file', file);
    const endpoint = kind === 'logo' ? `${API}/account/logo` : `${API}/member-app/hero-image`;
    try {
      const { data } = await axios.post(endpoint, fd, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      });
      setBranding((b) => ({
        ...b,
        logo_url: kind === 'logo' ? data.logo_url : b.logo_url,
        brand_palette: kind === 'logo' && Array.isArray(data.brand_palette) && data.brand_palette.length
          ? data.brand_palette
          : b.brand_palette,
        hero_image_url: kind === 'hero' ? data.hero_image_url : b.hero_image_url,
      }));
      bumpPreview();
      notify.success(kind === 'logo' ? 'Logo updated' : 'Hero image updated');
    } catch (e) {
      notifyApiError(notify, e, 'Upload failed');
    }
  }, [API, headers, bumpPreview]);

  const removeHero = useCallback(async () => {
    try {
      await axios.delete(`${API}/member-app/hero-image`, { headers });
      setBranding((b) => ({ ...b, hero_image_url: null }));
      bumpPreview();
    } catch (e) {
      notifyApiError(notify, e, 'Could not remove image');
    }
  }, [API, headers, bumpPreview]);

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
        <AppAddressCard slug={appSlug} onSharePack={() => setSharePackOpen(true)} />
      </div>

      {sharePackOpen && (
        <SharePackModal
          onClose={() => setSharePackOpen(false)}
          url={appSlug ? `${window.location.origin}/m/${appSlug}` : null}
          slug={appSlug}
          gymName={branding?.name || 'Your studio'}
          brandColour={branding?.primary_brand_colour || '#19CDFF'}
          logoUrl={branding?.logo_url || null}
          apiOrigin={API.replace(/\/api\/?$/, '')}
        />
      )}

      {/* ── Layout list ── */}
      <div className="lg:col-span-7 space-y-3">
        <BrandingPanel
          branding={branding}
          onField={saveBrandField}
          onUpload={uploadImage}
          onRemoveHero={removeHero}
          apiOrigin={API.replace(/\/api\/?$/, '')}
        />
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
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-medium uppercase tracking-wide flex items-center gap-2" style={{ color: 'var(--theme-text-muted)' }}>
              <Smartphone className="w-3.5 h-3.5" /> Live preview
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={bumpPreview}
                title="Refresh preview"
                data-testid="mab-preview-refresh"
                className="p-1.5 rounded-md border"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
              {appSlug && (
                <a
                  href={`${window.location.origin}/m/${appSlug}`}
                  target="_blank"
                  rel="noreferrer"
                  title="Open full-screen"
                  data-testid="mab-preview-open"
                  className="p-1.5 rounded-md border"
                  style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </div>
          </div>

          {/* Segmented toggle: real live app vs themed home-cards mock */}
          <div className="flex p-1 rounded-lg mb-3" style={{ background: 'var(--theme-surface-2)', border: '1px solid var(--theme-border)' }} data-testid="mab-preview-toggle">
            {[{ id: 'live', label: 'Live app' }, { id: 'home', label: 'Home screen' }].map((m) => (
              <button
                key={m.id}
                onClick={() => setPreviewMode(m.id)}
                data-testid={`mab-preview-mode-${m.id}`}
                className="flex-1 text-xs font-bold uppercase tracking-wider py-1.5 rounded-md transition"
                style={previewMode === m.id
                  ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
                  : { background: 'transparent', color: 'var(--theme-text-muted)' }}
              >
                {m.label}
              </button>
            ))}
          </div>

          {previewMode === 'live' ? (
            <LiveAppPreview slug={appSlug} previewKey={previewKey} />
          ) : (
            <PhoneFrame brand={branding} apiOrigin={API.replace(/\/api\/?$/, '')}>
              <div className="space-y-3" data-testid="mab-preview">
                {cards.filter((c) => c.enabled).length === 0 && (
                  <div className="text-center text-xs py-12" style={{ color: '#64748b' }}>
                    Empty home screen.<br />Add and enable cards to see them here.
                  </div>
                )}
                {cards.filter((c) => c.enabled).map((card) => {
                  const spec = registryById[card.type];
                  if (!spec) return null;
                  const accent = branding.primary_brand_colour || '#19CDFF';
                  return (
                    <div
                      key={card.type}
                      className="rounded-xl p-3"
                      style={{ background: '#F8FAFC', border: '1px solid #E2E8F0' }}
                      data-testid={`mab-preview-${card.type}`}
                    >
                      <div className="flex items-center gap-2.5">
                        <div
                          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                          style={{ background: `${accent}22`, color: accent }}
                        >
                          <CardIcon name={spec.icon} className="w-4 h-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="text-xs font-semibold text-slate-900 truncate">{spec.title}</div>
                          <div className="text-[10px] truncate text-slate-500">
                            {spec.description}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </PhoneFrame>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─────────────────── App address (public member-app link) ─────────────────── */

function AppAddressCard({ slug, onSharePack }) {
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

  const downloadPng = () => {
    if (!qr) return;
    const a = document.createElement('a');
    a.href = qr;
    a.download = `${slug || 'member-app'}-qr.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const printQr = () => {
    if (!qr || !url) return;
    const w = window.open('', '_blank', 'width=480,height=680');
    if (!w) { notify.error('Allow pop-ups to print the QR code'); return; }
    w.document.write(
      '<html><head><title>Member app QR</title><style>'
      + 'body{font-family:system-ui,-apple-system,sans-serif;text-align:center;padding:48px 24px;color:#0f172a}'
      + 'h1{font-size:22px;margin:0 0 6px}p{color:#475569;margin:0 0 24px}'
      + 'img{width:340px;height:340px}.u{margin-top:18px;font-family:monospace;font-size:14px;word-break:break-all}'
      + '</style></head><body><h1>Scan to open our app</h1><p>Point your phone camera at the code</p>'
      + '<img src="' + qr + '" alt="QR code"/><div class="u">' + url + '</div>'
      + '<scr' + 'ipt>window.onload=function(){setTimeout(function(){window.print();window.close();},300);}</scr' + 'ipt>'
      + '</body></html>',
    );
    w.document.close();
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
              <button
                onClick={printQr}
                disabled={!qr}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border disabled:opacity-40"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="mab-app-address-print"
              >
                <Printer className="w-3.5 h-3.5" /> Print QR
              </button>
              <button
                onClick={downloadPng}
                disabled={!qr}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border disabled:opacity-40"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="mab-app-address-download"
              >
                <Download className="w-3.5 h-3.5" /> Download
              </button>
              <button
                type="button"
                onClick={onSharePack}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border"
                style={{ borderColor: 'var(--color-brand-cyan)', color: 'var(--color-brand-cyan)' }}
                data-testid="mab-app-address-sharepack"
              >
                <Share2 className="w-3.5 h-3.5" /> Share pack
              </button>
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

/* ─────────────────── Share pack (social-ready card) ─────────────────── */

const SHARE_FORMATS = [
  { id: 'square', label: 'Square (post)', w: 1080, h: 1080 },
  { id: 'story', label: 'Story', w: 1080, h: 1920 },
];

function _hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || '').trim());
  if (!m) return { r: 25, g: 205, b: 255 };
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
function _shade({ r, g, b }, f) {
  // f<1 darken, f>1 lighten (clamped)
  const c = (v) => Math.max(0, Math.min(255, Math.round(v * f)));
  return `rgb(${c(r)},${c(g)},${c(b)})`;
}
function _readableOn({ r, g, b }) {
  // YIQ contrast — pick dark or white text over the brand colour
  return (r * 299 + g * 587 + b * 114) / 1000 >= 150 ? '#0F172A' : '#FFFFFF';
}
function _loadImg(src) {
  return new Promise((res) => {
    if (!src) { res(null); return; }
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => res(img);
    img.onerror = () => res(null);
    img.src = src;
  });
}
function _roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function SharePackModal({ onClose, url, slug, gymName, brandColour, logoUrl, apiOrigin }) {
  const canvasRef = useRef(null);
  const [format, setFormat] = useState('square');
  const [rendering, setRendering] = useState(true);

  const draw = useCallback(async () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    setRendering(true);
    const fmt = SHARE_FORMATS.find((f) => f.id === format) || SHARE_FORMATS[0];
    const W = fmt.w, H = fmt.h;
    canvas.width = W; canvas.height = H;
    const ctx = canvas.getContext('2d');
    const rgb = _hexToRgb(brandColour);
    const ink = _readableOn(rgb);
    const sub = ink === '#FFFFFF' ? 'rgba(255,255,255,0.78)' : 'rgba(15,23,42,0.72)';

    // Brand gradient background
    const grad = ctx.createLinearGradient(0, 0, W, H);
    grad.addColorStop(0, _shade(rgb, 1.12));
    grad.addColorStop(1, _shade(rgb, 0.62));
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    const cx = W / 2;
    let y = H === 1920 ? 320 : 150;

    // Logo (optional)
    const logoSrc = logoUrl
      ? (logoUrl.startsWith('http') || logoUrl.startsWith('data:') ? logoUrl : `${apiOrigin}${logoUrl}`)
      : null;
    const logoImg = await _loadImg(logoSrc);
    if (logoImg) {
      const box = 200;
      const ratio = Math.min(box / logoImg.width, box / logoImg.height);
      const lw = logoImg.width * ratio, lh = logoImg.height * ratio;
      ctx.save();
      ctx.fillStyle = '#ffffff';
      _roundRect(ctx, cx - box / 2 - 24, y - 24, box + 48, box + 48, 36);
      ctx.fill();
      ctx.drawImage(logoImg, cx - lw / 2, y + (box - lh) / 2, lw, lh);
      ctx.restore();
      y += box + 70;
    }

    ctx.textAlign = 'center';
    // Gym name
    ctx.fillStyle = ink;
    ctx.font = "800 78px Inter, system-ui, sans-serif";
    const name = (gymName || 'Your studio').slice(0, 28);
    ctx.fillText(name, cx, y);
    y += 70;
    // Tagline
    ctx.fillStyle = sub;
    ctx.font = "600 38px Inter, system-ui, sans-serif";
    ctx.fillText('Book classes · Check in · Manage your plan', cx, y);
    y += H === 1920 ? 150 : 90;

    // White QR panel
    const qrSize = H === 1920 ? 560 : 460;
    const panel = qrSize + 120;
    const px = cx - panel / 2;
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,0.18)';
    ctx.shadowBlur = 40;
    ctx.shadowOffsetY = 16;
    ctx.fillStyle = '#ffffff';
    _roundRect(ctx, px, y, panel, panel + 90, 44);
    ctx.fill();
    ctx.restore();

    const qrDataUrl = await QRCode.toDataURL(url, { width: qrSize, margin: 1, color: { dark: '#0F172A', light: '#FFFFFF' } });
    const qrImg = await _loadImg(qrDataUrl);
    if (qrImg) ctx.drawImage(qrImg, cx - qrSize / 2, y + 60, qrSize, qrSize);
    ctx.fillStyle = '#0F172A';
    ctx.font = "800 34px Inter, system-ui, sans-serif";
    ctx.fillText('SCAN TO GET THE APP', cx, y + qrSize + 130);
    y += panel + 130;

    // App URL chip
    ctx.fillStyle = ink;
    ctx.font = "700 36px Inter, system-ui, sans-serif";
    const shortUrl = (url || '').replace(/^https?:\/\//, '');
    ctx.fillText(shortUrl, cx, y);

    setRendering(false);
  }, [format, url, gymName, brandColour, logoUrl, apiOrigin]);

  useEffect(() => { draw(); }, [draw]);

  const getBlob = () => new Promise((res) => canvasRef.current?.toBlob(res, 'image/png', 0.95));

  const download = async () => {
    const blob = await getBlob();
    if (!blob) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${slug || 'gym'}-app-card-${format}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    notify.success('Card downloaded');
  };

  const share = async () => {
    const blob = await getBlob();
    if (!blob) return;
    const file = new File([blob], `${slug || 'gym'}-app-card.png`, { type: 'image/png' });
    const text = `Download the ${gymName} app — book classes, check in and manage your plan: ${url}`;
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      try { await navigator.share({ files: [file], title: `${gymName} app`, text }); return; } catch { /* cancelled */ }
    }
    download();
  };

  const canNativeShare = typeof navigator !== 'undefined' && !!navigator.canShare;

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center p-4"
      style={{ background: 'rgba(2,6,23,0.6)' }}
      data-testid="mab-sharepack-modal"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="rounded-2xl w-full max-w-md max-h-[92vh] overflow-y-auto"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: 'var(--theme-border)' }}>
          <div className="flex items-center gap-2">
            <Share2 className="w-4 h-4" style={{ color: 'var(--color-brand-cyan)' }} />
            <div className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>Share pack</div>
          </div>
          <button onClick={onClose} data-testid="mab-sharepack-close" className="p-1.5 rounded-lg" style={{ color: 'var(--theme-text-muted)' }}><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
            A ready-to-post image with your logo, colour and QR code — share it on Instagram, Facebook or WhatsApp to get members onto your app.
          </p>
          <div className="flex p-1 rounded-lg" style={{ background: 'var(--theme-surface-2)', border: '1px solid var(--theme-border)' }} data-testid="mab-sharepack-format">
            {SHARE_FORMATS.map((f) => (
              <button
                key={f.id}
                onClick={() => setFormat(f.id)}
                data-testid={`mab-sharepack-format-${f.id}`}
                className="flex-1 text-xs font-bold uppercase tracking-wider py-2 rounded-md transition"
                style={format === f.id ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' } : { background: 'transparent', color: 'var(--theme-text-muted)' }}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="rounded-xl overflow-hidden grid place-items-center" style={{ background: 'var(--theme-surface-2)', border: '1px solid var(--theme-border)', minHeight: 260 }}>
            <canvas
              ref={canvasRef}
              data-testid="mab-sharepack-canvas"
              className="max-w-full"
              style={{ maxHeight: format === 'story' ? 460 : 320, width: 'auto', opacity: rendering ? 0.5 : 1, transition: 'opacity 150ms' }}
            />
          </div>
          <div className="flex gap-2">
            {canNativeShare && (
              <button onClick={share} disabled={rendering} className="flex-1 inline-flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-bold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="mab-sharepack-share">
                <Share2 className="w-4 h-4" /> Share
              </button>
            )}
            <button onClick={download} disabled={rendering} className={`${canNativeShare ? '' : 'flex-1'} inline-flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-sm font-bold border disabled:opacity-50`} style={canNativeShare ? { borderColor: 'var(--theme-border)', color: 'var(--theme-text)' } : { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', border: 'none' }} data-testid="mab-sharepack-download">
              <Download className="w-4 h-4" /> Download PNG
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────── Phone frame ─────────────────── */

function PhoneFrame({ children, brand, apiOrigin }) {
  const accent = brand?.primary_brand_colour || '#19CDFF';
  const hero = brand?.hero_image_url || null;
  const logo = brand?.logo_url || null;
  const heroSrc = hero && (hero.startsWith('http') || hero.startsWith('data:')) ? hero : (hero ? `${apiOrigin}${hero}` : null);
  const logoSrc = logo && (logo.startsWith('http') || logo.startsWith('data:')) ? logo : (logo ? `${apiOrigin}${logo}` : null);
  return (
    <div
      className="mx-auto rounded-[2rem] overflow-hidden shadow-xl"
      style={{
        width: 280,
        background: '#ffffff',
        border: '8px solid #0f172a',
        minHeight: 540,
      }}
    >
      {/* Hero banner */}
      <div className="relative" style={{ height: heroSrc ? 96 : 0 }}>
        {heroSrc && <img src={heroSrc} alt="" className="w-full h-full object-cover" />}
      </div>
      <div className="px-4 pb-4">
        <div className="flex items-center justify-between pt-3 mb-3">
          <div className="text-[10px] font-semibold text-slate-900">9:41</div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-1.5 rounded-sm bg-slate-900/70" />
            <div className="w-3 h-1.5 rounded-sm bg-slate-900/70" />
            <div className="w-4 h-2 rounded-sm border border-slate-900/70" />
          </div>
        </div>
        <div className="flex items-center gap-2 mb-3">
          {logoSrc
            ? <img src={logoSrc} alt="" className="h-7 w-7 rounded object-contain bg-white" style={{ border: `1.5px solid ${accent}` }} />
            : <div className="h-7 w-7 rounded grid place-items-center" style={{ background: `${accent}22` }}><Sparkles className="w-3.5 h-3.5" style={{ color: accent }} /></div>}
          <div className="text-slate-900 text-sm font-semibold truncate">My gym</div>
        </div>
        {children}
      </div>
    </div>
  );
}

/* ─────────────────── Live app iframe preview ─────────────────── */

function LiveAppPreview({ slug, previewKey }) {
  if (!slug) {
    return (
      <div
        className="mx-auto rounded-[2rem] shadow-xl grid place-items-center text-center p-6"
        style={{ width: 280, minHeight: 540, background: '#0f172a', border: '8px solid #0f172a' }}
        data-testid="mab-live-preview-empty"
      >
        <div>
          <Smartphone className="w-8 h-8 mx-auto mb-3 text-white/40" />
          <p className="text-sm font-semibold text-white">Set your app address first</p>
          <p className="text-xs text-white/50 mt-1.5">Add your app URL in Memberships → Setup to see your real member app here.</p>
        </div>
      </div>
    );
  }
  const src = `${window.location.origin}/m/${slug}?preview=${previewKey}`;
  return (
    <div
      className="mx-auto rounded-[2rem] overflow-hidden shadow-xl"
      style={{ width: 280, height: 560, background: '#0f172a', border: '8px solid #0f172a' }}
      data-testid="mab-live-preview"
    >
      <iframe
        key={previewKey}
        src={src}
        title="Member app live preview"
        className="w-full h-full"
        style={{ border: 'none', background: '#0f172a' }}
        loading="lazy"
      />
    </div>
  );
}

/* ─────────────────── Branding & theme panel ─────────────────── */

const COLOUR_PRESETS = ['#19CDFF', '#7C3AED', '#EC4899', '#F59E0B', '#10B981', '#EF4444', '#0EA5E9', '#0F172A'];
const FONT_OPTIONS = [
  { id: 'inter', label: 'Clean', css: "'Inter', system-ui, sans-serif" },
  { id: 'poppins', label: 'Friendly', css: "'Poppins', system-ui, sans-serif" },
  { id: 'manrope', label: 'Modern', css: "'Manrope', system-ui, sans-serif" },
  { id: 'nunito', label: 'Rounded', css: "'Nunito', system-ui, sans-serif" },
  { id: 'space', label: 'Techy', css: "'Space Grotesk', system-ui, sans-serif" },
];
const BUTTON_OPTIONS = [
  { id: 'soft', label: 'Soft', radius: 8 },
  { id: 'pill', label: 'Pill', radius: 999 },
  { id: 'sharp', label: 'Sharp', radius: 0 },
];

function BrandingPanel({ branding, onField, onUpload, onRemoveHero, apiOrigin }) {
  const logoRef = useRef(null);
  const heroRef = useRef(null);
  const [busy, setBusy] = useState(null); // 'logo' | 'hero' | null
  // Iter 220ed — member-app display name (what members see on login).
  const [displayName, setDisplayName] = useState(branding?.display_name || '');
  useEffect(() => { setDisplayName(branding?.display_name || ''); }, [branding?.display_name]);
  const colour = branding?.primary_brand_colour || '#19CDFF';
  const font = branding?.font || 'inter';
  const buttonStyle = branding?.button_style || 'soft';
  const palette = Array.isArray(branding?.brand_palette) ? branding.brand_palette.slice(0, 6) : [];
  const hero = branding?.hero_image_url;
  const heroSrc = hero && (hero.startsWith('http') || hero.startsWith('data:')) ? hero : (hero ? `${apiOrigin}${hero}` : null);
  const logo = branding?.logo_url;
  const logoSrc = logo && (logo.startsWith('http') || logo.startsWith('data:')) ? logo : (logo ? `${apiOrigin}${logo}` : null);

  const pick = (kind, ref) => async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setBusy(kind);
    await onUpload(kind, file);
    setBusy(null);
  };

  return (
    <div className="rounded-xl border p-4" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid="mab-branding-panel">
      <div className="flex items-center gap-2 mb-3">
        <Palette className="w-4 h-4" style={{ color: 'var(--color-brand-cyan)' }} />
        <div className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Branding &amp; theme</div>
      </div>

      {/* Iter 220ed — Gym name shown to members on the login screen */}
      <div className="mb-4">
        <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--theme-text-muted)' }}>Gym name shown to members</span>
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          onBlur={(e) => onField({ display_name: e.target.value.trim() })}
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
          placeholder="e.g. Third Space"
          maxLength={80}
          className="w-full mt-1.5 text-sm rounded-lg border px-3 py-2"
          style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
          data-testid="mab-display-name"
        />
        <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
          Appears on the member login &amp; welcome screen. Leave blank to use your account name.
        </p>
      </div>

      {/* Brand colour */}
      <div className="mb-4">
        <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--theme-text-muted)' }}>Brand colour</span>
        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
          {COLOUR_PRESETS.map((c) => (
            <button
              key={c}
              onClick={() => onField({ primary_brand_colour: c })}
              title={c}
              data-testid={`mab-colour-${c.replace('#', '')}`}
              className="w-7 h-7 rounded-full transition"
              style={{ background: c, outline: colour.toUpperCase() === c.toUpperCase() ? '2px solid var(--theme-text)' : 'none', outlineOffset: 2 }}
            />
          ))}
          <label className="relative w-7 h-7 rounded-full overflow-hidden cursor-pointer" style={{ border: '1px solid var(--theme-border)' }} title="Custom colour">
            <input
              type="color"
              value={colour}
              onChange={(e) => onField({ primary_brand_colour: e.target.value })}
              className="absolute inset-0 w-[200%] h-[200%] -left-1/2 -top-1/2 cursor-pointer"
              data-testid="mab-colour-custom"
            />
          </label>
          <span className="text-xs font-mono" style={{ color: 'var(--theme-text-muted)' }}>{colour}</span>
        </div>
        {palette.length > 0 && (
          <div className="mt-2.5 flex items-center gap-2 flex-wrap" data-testid="mab-logo-palette">
            <span className="text-[10px] font-semibold inline-flex items-center gap-1" style={{ color: 'var(--theme-text-muted)' }}>
              <Sparkles className="w-3 h-3" style={{ color: 'var(--color-brand-cyan)' }} /> From your logo:
            </span>
            {palette.map((c) => (
              <button
                key={c}
                onClick={() => onField({ primary_brand_colour: c })}
                title={`Apply ${c}`}
                data-testid={`mab-logo-colour-${c.replace('#', '')}`}
                className="w-6 h-6 rounded-md transition"
                style={{ background: c, outline: colour.toUpperCase() === c.toUpperCase() ? '2px solid var(--theme-text)' : '1px solid var(--theme-border)', outlineOffset: 1 }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Typography */}
      <div className="mb-4">
        <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--theme-text-muted)' }}>Typography</span>
        <div className="flex flex-wrap gap-1.5 mt-1.5" data-testid="mab-font-options">
          {FONT_OPTIONS.map((f) => {
            const active = font === f.id;
            return (
              <button
                key={f.id}
                onClick={() => onField({ font: f.id })}
                data-testid={`mab-font-${f.id}`}
                className="px-3 py-1.5 rounded-lg text-sm transition"
                style={{
                  fontFamily: f.css,
                  background: active ? 'var(--color-brand-cyan)' : 'var(--theme-surface-2)',
                  color: active ? 'var(--color-ink)' : 'var(--theme-text)',
                  border: active ? 'none' : '1px solid var(--theme-border)',
                  fontWeight: 700,
                }}
              >
                {f.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Button style */}
      <div className="mb-4">
        <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--theme-text-muted)' }}>Button style</span>
        <div className="flex gap-1.5 mt-1.5" data-testid="mab-button-options">
          {BUTTON_OPTIONS.map((b) => {
            const active = buttonStyle === b.id;
            return (
              <button
                key={b.id}
                onClick={() => onField({ button_style: b.id })}
                data-testid={`mab-button-${b.id}`}
                className="flex-1 py-2 text-xs font-bold uppercase tracking-wider transition"
                style={{
                  borderRadius: b.radius,
                  background: active ? 'var(--color-brand-cyan)' : 'var(--theme-surface-2)',
                  color: active ? 'var(--color-ink)' : 'var(--theme-text-muted)',
                  border: active ? 'none' : '1px solid var(--theme-border)',
                }}
              >
                {b.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {/* Logo */}
        <div>
          <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--theme-text-muted)' }}>Logo</span>
          <button
            onClick={() => logoRef.current?.click()}
            data-testid="mab-logo-upload"
            className="mt-1.5 w-full rounded-lg p-3 flex items-center gap-2 transition"
            style={{ background: 'var(--theme-surface-2)', border: '1.5px dashed var(--theme-border)' }}
          >
            {logoSrc
              ? <img src={logoSrc} alt="logo" className="h-9 w-9 rounded object-contain bg-white" />
              : <div className="h-9 w-9 rounded grid place-items-center" style={{ background: 'var(--theme-surface-3)' }}><ImageIcon className="w-4 h-4" style={{ color: 'var(--theme-text-muted)' }} /></div>}
            <span className="text-xs font-semibold flex-1 text-left" style={{ color: 'var(--theme-text)' }}>{logoSrc ? 'Replace' : 'Upload'}</span>
            {busy === 'logo' ? <Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--color-brand-cyan)' }} /> : <Upload className="w-4 h-4" style={{ color: 'var(--theme-text-muted)' }} />}
          </button>
          <input ref={logoRef} type="file" accept="image/*" className="hidden" onChange={pick('logo', logoRef)} data-testid="mab-logo-input" />
        </div>

        {/* Hero banner */}
        <div>
          <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: 'var(--theme-text-muted)' }}>Hero banner</span>
          <div className="mt-1.5 relative">
            <button
              onClick={() => heroRef.current?.click()}
              data-testid="mab-hero-upload"
              className="w-full rounded-lg overflow-hidden flex items-center justify-center transition"
              style={{ height: 60, background: heroSrc ? 'transparent' : 'var(--theme-surface-2)', border: '1.5px dashed var(--theme-border)' }}
            >
              {heroSrc
                ? <img src={heroSrc} alt="hero" className="w-full h-full object-cover" />
                : (busy === 'hero'
                    ? <Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--color-brand-cyan)' }} />
                    : <span className="text-xs font-semibold flex items-center gap-1.5" style={{ color: 'var(--theme-text-muted)' }}><Upload className="w-3.5 h-3.5" /> Upload banner</span>)}
            </button>
            {heroSrc && (
              <button
                onClick={onRemoveHero}
                title="Remove banner"
                data-testid="mab-hero-remove"
                className="absolute -top-2 -right-2 w-5 h-5 rounded-full grid place-items-center"
                style={{ background: '#ef4444', color: '#fff' }}
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
          <input ref={heroRef} type="file" accept="image/*" className="hidden" onChange={pick('hero', heroRef)} data-testid="mab-hero-input" />
        </div>
      </div>
      <p className="text-[11px] mt-3" style={{ color: 'var(--theme-text-muted)' }}>
        Your colour, fonts, buttons, logo and banner appear on the member app instantly — switch the preview to <strong>Live app</strong> to see exactly what members see.
      </p>
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
