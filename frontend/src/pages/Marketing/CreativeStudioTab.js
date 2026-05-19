/* Creative Studio — Multi-input Poster Builder
 *
 * What's new vs the prompt-only version:
 *   • Resolution picker (presets + custom dims)
 *   • Headline / sub-headline / CTA text inputs that render onto the poster
 *   • Asset library tabs for logos / faces / equipment with category-aware uploads
 *   • Selected references are passed to the AI as "use this as composition reference"
 *   • Mood + style controls
 *
 * The user can:
 *   1. Build a kit (upload logos, faces, equipment shots once)
 *   2. Select which to combine for THIS poster
 *   3. Type the headline + describe the look in the AI prompt
 *   4. Pick the resolution and Generate
 *
 * The AI describes references in its prompt; this gives 80% of the
 * "composite multiple inputs" value with a single round-trip to gpt-image-1.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Sparkles, Loader2, Upload, Trash2, Image as ImageIcon, Wand2, Building2, User, Dumbbell, Camera, Maximize2, Check, X, Megaphone,
} from 'lucide-react';
import { notify, useConfirm } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const TYPES = [
  { id: 'social_post', label: 'Social post' },
  { id: 'poster', label: 'Poster' },
  { id: 'email_hero', label: 'Email hero' },
];

const STYLES = [
  { id: 'photorealistic', label: 'Photorealistic' },
  { id: 'editorial', label: 'Editorial / magazine' },
  { id: 'cinematic', label: 'Cinematic film still' },
  { id: 'illustrated', label: 'Bold illustrated' },
  { id: 'minimal', label: 'Minimal flat design' },
  { id: 'duotone', label: 'Duotone print' },
];

const MOODS = [
  'Energetic', 'Calm & welcoming', 'Premium / aspirational',
  'Bold & confident', 'Playful', 'Disciplined',
];

const PROMPT_IDEAS = [
  'High-energy spin class promotion for Saturday morning',
  'Empowering kettlebell workout — natural light, motivational',
  'Premium 1-on-1 PT session — clean studio, deliberate lighting',
  'Welcome new members — warm, inviting gym lobby',
];

const CATEGORY_META = {
  logo:      { label: 'Logos',     icon: Building2 },
  face:      { label: 'Faces',     icon: User },
  equipment: { label: 'Equipment', icon: Dumbbell },
  photo:     { label: 'Photos',    icon: Camera },
  brand:     { label: 'Brand library', icon: Megaphone, readOnly: true },
};

const CreativeStudioTab = ({ API, headers, entitlement }) => {
  const confirm = useConfirm();
  const locked = entitlement && !entitlement.features?.ai_creative_studio;

  // Generation form
  const [prompt, setPrompt] = useState('');
  const [headline, setHeadline] = useState('');
  const [subheadline, setSubheadline] = useState('');
  const [cta, setCta] = useState('');
  const [type, setType] = useState('poster');
  const [n, setN] = useState(2);
  const [style, setStyle] = useState('photorealistic');
  const [mood, setMood] = useState('Energetic');
  const [busy, setBusy] = useState(false);

  // Resolution
  const [resolutions, setResolutions] = useState([]);
  const [resolutionPreset, setResolutionPreset] = useState('poster_vertical');
  const [customW, setCustomW] = useState('');
  const [customH, setCustomH] = useState('');
  const [useCustomRes, setUseCustomRes] = useState(false);

  // Brand kit lock
  const [brandLock, setBrandLock] = useState(false);

  // Library + selection
  const [assets, setAssets] = useState([]);
  const [activeCategory, setActiveCategory] = useState('logo');
  const [selectedRefs, setSelectedRefs] = useState([]); // asset ids
  const [uploading, setUploading] = useState(false);
  const [uploadCategory, setUploadCategory] = useState('logo');
  // Iter 238g — master-admin curated marketing image library for any
  // tenant with the Marketing bolt-on. Read-only from this view; the
  // "Brand library" tab below renders these images and clicking one
  // imports it into the operator's own asset library before selecting.
  const [brandLibrary, setBrandLibrary] = useState([]);
  const [importingBrand, setImportingBrand] = useState(null);
  // Full-screen poster preview state. {url, headline, dims, style} or null.
  const [lightbox, setLightbox] = useState(null);
  const fileRef = useRef(null);

  const load = () => axios.get(`${API}/api/marketing/creative`, { headers })
    .then((r) => setAssets(r.data.assets || []))
    .catch(() => {});

  useEffect(() => {
    load();
    axios.get(`${API}/api/marketing/creative/resolutions`, { headers })
      .then((r) => setResolutions(r.data.presets || []))
      .catch(() => {});
    axios.get(`${API}/api/marketing/image-library`, { headers })
      .then((r) => setBrandLibrary(r.data?.rows || []))
      .catch(() => {}); // 403 for orgs that lost marketing — silent
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, []);

  const libraryByCategory = useMemo(() => {
    const result = { logo: [], face: [], equipment: [], photo: [] };
    for (const a of assets) {
      // Place every user upload in some bucket so nothing silently
      // disappears from the gallery (e.g. legacy 'other' uploads).
      let cat = a.category;
      if (!result[cat]) {
        cat = a.source === 'user_upload' ? 'photo' : null;
      }
      if (cat && result[cat]) result[cat].push(a);
    }
    return result;
  }, [assets]);

  // AI-generated outputs (anything that isn't user_upload)
  const generatedAssets = useMemo(
    () => assets.filter((a) => a.source !== 'user_upload'),
    [assets],
  );

  const currentDims = useMemo(() => {
    if (useCustomRes && customW && customH) {
      return `${customW} × ${customH}`;
    }
    const p = resolutions.find((r) => r.id === resolutionPreset);
    return p ? `${p.width} × ${p.height}` : '—';
  }, [useCustomRes, customW, customH, resolutionPreset, resolutions]);

  const toggleRef = (id) =>
    setSelectedRefs((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const generate = async () => {
    if (!prompt.trim() && !headline.trim()) {
      notify.error('Add at least a prompt or headline');
      return;
    }
    setBusy(true);
    try {
      const payload = {
        prompt: prompt.trim() || `${headline} ${mood ? `, ${mood.toLowerCase()}` : ''}`,
        type, n,
        headline: headline.trim() || null,
        subheadline: subheadline.trim() || null,
        call_to_action: cta.trim() || null,
        style, mood,
        resolution_preset: useCustomRes ? null : resolutionPreset,
        custom_width: useCustomRes ? Number(customW) || null : null,
        custom_height: useCustomRes ? Number(customH) || null : null,
        reference_asset_ids: selectedRefs,
        brand_lock: brandLock,
      };
      const { data } = await axios.post(`${API}/api/marketing/creative/generate`, payload, { headers });
      if (data.asset?.source === 'fallback_svg') {
        notify.warning('Using preview fallback', 'AI service is busy — placeholder shown. Try again or contact support if this persists.');
      } else {
        notify.success(`Generated ${n} ${n === 1 ? 'variant' : 'variants'} at ${data.asset?.width}×${data.asset?.height}`);
      }
      setPrompt('');
      load();
    } catch (err) {
      notifyApiError(notify, err, 'Generation failed');
    } finally { setBusy(false); }
  };

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { notify.error('Image too large', 'Max 5 MB.'); return; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('category', uploadCategory);
      await axios.post(`${API}/api/marketing/creative/upload`, fd, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      });
      notify.success('Image uploaded', `Added to ${CATEGORY_META[uploadCategory].label.toLowerCase()}.`);
      setActiveCategory(uploadCategory);
      load();
    } catch (err) {
      notifyApiError(notify, err, 'Upload failed');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const remove = async (assetId, label) => {
    const ok = await confirm({
      title: 'Delete this asset?',
      detail: `"${label}" will be removed from the gallery and from any campaigns referencing it.`,
      confirmLabel: 'Delete',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await axios.delete(`${API}/api/marketing/creative/${assetId}`, { headers });
      notify.success('Deleted');
      setSelectedRefs((s) => s.filter((id) => id !== assetId));
      load();
    } catch (err) {
      notifyApiError(notify, err, 'Delete failed');
    }
  };

  if (locked) {
    return (
      <div className="rounded-xl border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 p-6 text-center" data-testid="creative-locked">
        <Sparkles className="mx-auto text-amber-500 mb-2" size={32} />
        <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">AI Creative Studio is a Pro feature</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">Upgrade to Pro to generate posters, social posts, and email heroes with AI.</p>
      </div>
    );
  }

  const activeLib = libraryByCategory[activeCategory] || [];
  const ActiveIcon = (CATEGORY_META[activeCategory] || {}).icon || ImageIcon;
  const isBrandTab = activeCategory === 'brand';

  // Iter 238g — clicking a master-admin brand-library image first
  // imports it into this org's asset library, then selects it as a
  // reference. The import is idempotent (server reuses existing rows).
  const importBrandImage = async (libRow) => {
    if (importingBrand) return;
    setImportingBrand(libRow.id);
    try {
      const { data } = await axios.post(
        `${API}/api/marketing/creative/import-brand-asset`,
        { library_id: libRow.id }, { headers },
      );
      const asset = data?.asset;
      if (asset?.id) {
        setAssets((prev) => (prev.find((a) => a.id === asset.id) ? prev : [asset, ...prev]));
        setSelectedRefs((s) => (s.includes(asset.id) ? s : [...s, asset.id]));
        if (!data.reused) notify.success('Pinned to your library', `"${asset.label || libRow.label}" is now selectable as a reference.`);
      }
    } catch (e) {
      notifyApiError(notify, e, 'Could not import brand library image');
    }
    setImportingBrand(null);
  };

  return (
    <div className="space-y-4" data-testid="marketing-creative-tab">
      {/* Two-column workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-4">
        {/* Left: Builder form */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5 space-y-4 shadow-sm">

          {/* Headline + subheadline + CTA */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Headline (overlaid on poster)">
              <input value={headline} onChange={(e) => setHeadline(e.target.value)}
                placeholder="JOIN FREE THIS WEEKEND"
                className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-sm focus:outline-none focus:border-[var(--color-brand-blue)]"
                data-testid="creative-headline" />
            </Field>
            <Field label="Sub-headline">
              <input value={subheadline} onChange={(e) => setSubheadline(e.target.value)}
                placeholder="No commitment — just bring trainers"
                className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-sm focus:outline-none focus:border-[var(--color-brand-blue)]"
                data-testid="creative-subheadline" />
            </Field>
            <Field label="Call-to-action">
              <input value={cta} onChange={(e) => setCta(e.target.value)}
                placeholder="Book your trial →"
                className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-sm focus:outline-none focus:border-[var(--color-brand-blue)]"
                data-testid="creative-cta" />
            </Field>
            <Field label="Asset format">
              <select value={type} onChange={(e) => setType(e.target.value)}
                className="w-full px-2 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-sm"
                data-testid="creative-type-select">
                {TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
              </select>
            </Field>
          </div>

          {/* AI prompt */}
          <Field label="Describe the look & feel for the AI">
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. dramatic side-lit gym at golden hour, athletes mid-action, deep shadows, brand colours pop"
              rows={3}
              className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-sm focus:outline-none focus:border-[var(--color-brand-blue)]"
              data-testid="creative-prompt-input" />
            <div className="flex flex-wrap gap-1.5 mt-2">
              {PROMPT_IDEAS.map((idea, i) => (
                <button key={i} onClick={() => setPrompt(idea)}
                  className="px-2.5 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 text-[10px] font-medium hover:bg-[rgb(var(--rgb-brand-blue)/0.1)] hover:text-[var(--color-brand-blue)] transition"
                  data-testid={`creative-idea-${i}`}>
                  <Wand2 size={9} className="inline mr-1" /> {idea}
                </button>
              ))}
            </div>
          </Field>

          {/* Style + mood */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Visual style">
              <select value={style} onChange={(e) => setStyle(e.target.value)}
                className="w-full px-2 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-sm"
                data-testid="creative-style">
                {STYLES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
            </Field>
            <Field label="Mood">
              <select value={mood} onChange={(e) => setMood(e.target.value)}
                className="w-full px-2 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-sm"
                data-testid="creative-mood">
                {MOODS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </Field>
          </div>

          {/* Resolution */}
          <Field label="Resolution">
            <div className="flex flex-wrap items-center gap-2">
              <select value={useCustomRes ? '__custom' : resolutionPreset}
                onChange={(e) => {
                  if (e.target.value === '__custom') { setUseCustomRes(true); }
                  else { setUseCustomRes(false); setResolutionPreset(e.target.value); }
                }}
                className="px-2 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-sm flex-1 min-w-0 sm:min-w-[200px]"
                data-testid="creative-resolution-preset">
                {resolutions.map((r) => (
                  <option key={r.id} value={r.id}>{r.label} · {r.width}×{r.height}</option>
                ))}
                <option value="__custom">Custom dimensions…</option>
              </select>
              {useCustomRes && (
                <div className="flex items-center gap-1.5">
                  <input type="number" min="256" max="4096" value={customW} onChange={(e) => setCustomW(e.target.value)}
                    placeholder="width" className="w-24 px-2 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-sm" data-testid="creative-custom-w" />
                  <span className="text-zinc-400">×</span>
                  <input type="number" min="256" max="4096" value={customH} onChange={(e) => setCustomH(e.target.value)}
                    placeholder="height" className="w-24 px-2 py-2 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-sm" data-testid="creative-custom-h" />
                </div>
              )}
              <span className="text-[11px] text-zinc-500 dark:text-zinc-400 ml-1 inline-flex items-center gap-1">
                <Maximize2 size={10} /> {currentDims}
              </span>
            </div>
          </Field>

          {/* Brand Kit Lock */}
          <button
            type="button"
            onClick={() => setBrandLock((v) => !v)}
            className={`w-full flex items-center justify-between gap-3 rounded-md p-3 border-2 text-left transition ${brandLock
              ? 'border-violet-500 bg-violet-50 dark:bg-violet-900/30'
              : 'border-zinc-200 dark:border-zinc-700 hover:border-violet-300 bg-white dark:bg-zinc-950'}`}
            data-testid="creative-brand-lock"
          >
            <div className="flex items-center gap-2">
              <div className={`w-9 h-9 rounded-md flex items-center justify-center ${brandLock ? 'bg-violet-500 text-white' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500'}`}>
                <Sparkles size={16} />
              </div>
              <div>
                <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">Brand kit lock</p>
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
                  {brandLock ? 'Every poster will use your logo + palette + brand fonts.' : 'Off — AI is free to interpret palette/typography loosely.'}
                </p>
              </div>
            </div>
            <span className={`relative inline-flex w-9 h-5 rounded-full transition-colors ${brandLock ? 'bg-violet-600' : 'bg-zinc-300 dark:bg-zinc-700'}`}>
              <span className={`absolute top-0.5 ${brandLock ? 'right-0.5' : 'left-0.5'} w-4 h-4 rounded-full bg-white transition-all`} />
            </span>
          </button>

          {/* Variants count + Generate */}
          <div className="flex items-center justify-between gap-2 pt-2 border-t border-zinc-100 dark:border-zinc-800">
            <div className="flex items-center gap-2">
              <span className="text-xs text-zinc-500 dark:text-zinc-400">Generate</span>
              {[1, 2, 3, 4].map((v) => (
                <button key={v} onClick={() => setN(v)}
                  className={`w-7 h-7 rounded-md text-xs font-bold transition ${n === v
                    ? 'bg-[var(--color-brand-blue)] text-white'
                    : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:bg-[rgb(var(--rgb-brand-blue)/0.1)]'}`}
                  data-testid={`creative-n-${v}`}>{v}</button>
              ))}
              <span className="text-xs text-zinc-500 dark:text-zinc-400">{n === 1 ? 'variant' : 'variants'}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-zinc-500 dark:text-zinc-400">
                {selectedRefs.length} reference{selectedRefs.length === 1 ? '' : 's'}
              </span>
              <button onClick={generate} disabled={busy || (!prompt.trim() && !headline.trim())}
                className="px-4 py-2 rounded-md bg-gradient-to-r from-[var(--color-brand-blue)] to-[var(--color-brand-cyan-hover)] text-white text-xs font-semibold disabled:opacity-50 inline-flex items-center gap-1.5 shadow-sm hover:shadow-md transition"
                data-testid="creative-generate-btn">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                {busy ? 'Generating (~30s)…' : 'Generate poster'}
              </button>
            </div>
          </div>
        </div>

        {/* Right: Asset library */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4 space-y-3 shadow-sm">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-zinc-900 dark:text-zinc-100">Asset library</h3>
            {!isBrandTab && (
              <div className="flex items-center gap-1">
                <select value={uploadCategory} onChange={(e) => setUploadCategory(e.target.value)}
                  className="text-[11px] px-2 py-1 rounded border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-700 dark:text-zinc-300"
                  data-testid="creative-upload-category">
                  {Object.entries(CATEGORY_META).filter(([k]) => k !== 'brand').map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
                <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={onUpload} className="hidden" data-testid="creative-upload-input" />
                <button onClick={() => fileRef.current?.click()} disabled={uploading}
                  className="px-2 py-1 rounded bg-[var(--color-brand-blue)] text-white text-[11px] font-semibold inline-flex items-center gap-1 disabled:opacity-50"
                  data-testid="creative-upload-btn">
                  {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                  Upload
                </button>
              </div>
            )}
            {isBrandTab && (
              <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-fuchsia-50 text-fuchsia-700 border border-fuchsia-200" data-testid="creative-brand-readonly-badge">
                Curated · Read-only
              </span>
            )}
          </div>

          {/* Category tabs */}
          <div className="flex gap-1 border-b border-zinc-100 dark:border-zinc-800 -mx-1 px-1">
            {Object.entries(CATEGORY_META).map(([k, meta]) => {
              const Icon = meta.icon;
              const count = k === 'brand' ? brandLibrary.length : (libraryByCategory[k] || []).length;
              const active = activeCategory === k;
              return (
                <button key={k} onClick={() => setActiveCategory(k)}
                  className={`px-2.5 py-1.5 text-[11px] font-bold inline-flex items-center gap-1.5 -mb-px border-b-2 transition ${active
                    ? 'border-[var(--color-brand-blue)] text-[var(--color-brand-blue)]'
                    : 'border-transparent text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200'}`}
                  data-testid={`creative-tab-${k}`}>
                  <Icon size={11} /> {meta.label}
                  {count > 0 && <span className="px-1.5 py-0.5 rounded-full text-[9px] bg-zinc-100 dark:bg-zinc-800">{count}</span>}
                </button>
              );
            })}
          </div>

          {/* Asset grid for active category */}
          {isBrandTab ? (
            brandLibrary.length === 0 ? (
              <div className="rounded-md border border-dashed border-zinc-200 dark:border-zinc-700 p-6 text-center" data-testid="creative-brand-empty">
                <Megaphone className="mx-auto text-zinc-300 dark:text-zinc-600 mb-1.5" size={22} />
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
                  Master admin hasn't published any shared images yet.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-2 max-h-[340px] overflow-y-auto pr-1" data-testid="creative-brand-grid">
                {brandLibrary.map((row) => {
                  const importing = importingBrand === row.id;
                  // If the operator has already imported this image, the
                  // matching asset row will be in `assets` with the same
                  // `library_id` — show it as already-selectable.
                  const alreadyImported = assets.find((a) => a.library_id === row.id);
                  const selected = alreadyImported && selectedRefs.includes(alreadyImported.id);
                  return (
                    <button
                      key={row.id}
                      type="button"
                      disabled={importing}
                      onClick={() => alreadyImported ? toggleRef(alreadyImported.id) : importBrandImage(row)}
                      className={`relative aspect-square rounded-md overflow-hidden border-2 transition ${selected
                        ? 'border-[var(--color-brand-blue)] ring-2 ring-[rgb(var(--rgb-brand-blue)/0.3)]'
                        : 'border-zinc-200 dark:border-zinc-800 hover:border-fuchsia-400'}`}
                      title={row.label || 'Brand library image'}
                      data-testid={`creative-brand-${row.id}`}
                    >
                      <img src={row.url} alt="" className="w-full h-full object-cover" loading="lazy" />
                      {selected && (
                        <div className="absolute top-1 right-1 w-5 h-5 rounded-full bg-[var(--color-brand-blue)] text-white flex items-center justify-center">
                          <Check size={11} />
                        </div>
                      )}
                      {importing && (
                        <div className="absolute inset-0 bg-white/70 flex items-center justify-center dark:bg-zinc-900">
                          <Loader2 size={16} className="animate-spin text-[var(--color-brand-blue)]" />
                        </div>
                      )}
                      <div className="absolute bottom-0 inset-x-0 px-1 py-0.5 bg-gradient-to-t from-black/70 to-transparent">
                        <p className="text-[9px] text-white font-medium truncate">{row.label}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            )
          ) : activeLib.length === 0 ? (
            <div className="rounded-md border border-dashed border-zinc-200 dark:border-zinc-700 p-6 text-center" data-testid="creative-cat-empty">
              <ActiveIcon className="mx-auto text-zinc-300 dark:text-zinc-600 mb-1.5" size={22} />
              <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
                No {CATEGORY_META[activeCategory].label.toLowerCase()} yet. Upload one to use as a reference.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2 max-h-[340px] overflow-y-auto pr-1" data-testid="creative-cat-grid">
              {activeLib.map((a) => {
                const v = (a.variants || [])[0];
                const selected = selectedRefs.includes(a.id);
                return (
                  <button key={a.id} onClick={() => toggleRef(a.id)}
                    className={`relative aspect-square rounded-md overflow-hidden border-2 transition ${selected
                      ? 'border-[var(--color-brand-blue)] ring-2 ring-[rgb(var(--rgb-brand-blue)/0.3)]'
                      : 'border-zinc-200 dark:border-zinc-800 hover:border-[rgb(var(--rgb-brand-blue)/0.5)]'}`}
                    title={a.label || a.filename || 'Reference asset'}
                    data-testid={`creative-ref-${a.id}`}>
                    {v?.url ? (
                      <img src={v.url} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-zinc-100 dark:bg-zinc-800">
                        <ImageIcon size={16} className="text-zinc-400" />
                      </div>
                    )}
                    {selected && (
                      <div className="absolute top-1 right-1 w-5 h-5 rounded-full bg-[var(--color-brand-blue)] text-white flex items-center justify-center">
                        <Check size={11} />
                      </div>
                    )}
                    <button onClick={(e) => { e.stopPropagation(); remove(a.id, a.label || a.filename || 'Asset'); }}
                      className="absolute bottom-0.5 right-0.5 p-0.5 rounded bg-black/50 text-white opacity-0 hover:opacity-100 group-hover:opacity-100"
                      data-testid={`creative-ref-delete-${a.id}`}>
                      <Trash2 size={9} />
                    </button>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Generated outputs gallery */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4 shadow-sm">
        <h3 className="text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-3 flex items-center gap-2">
          <Sparkles size={14} className="text-[var(--color-brand-blue)]" /> Generated posters
        </h3>
        {generatedAssets.length === 0 ? (
          <div className="rounded-md border border-dashed border-zinc-300 dark:border-zinc-700 p-10 text-center bg-zinc-50/50 dark:bg-zinc-900/50" data-testid="creative-empty">
            <ImageIcon className="mx-auto text-zinc-300 dark:text-zinc-600 mb-2" size={32} />
            <p className="text-sm text-zinc-500 dark:text-zinc-400">No posters yet — fill in the form above and click Generate.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3" data-testid="creative-gallery">
            {generatedAssets.flatMap((a) => (a.variants || []).map((v, idx) => (
              <div key={`${a.id}-${idx}`} className="aspect-square rounded-lg overflow-hidden border border-zinc-200 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-800 relative group cursor-pointer" data-testid={`creative-asset-${a.id}-${idx}`}
                onClick={() => setLightbox({ url: v.url, headline: a.headline || a.prompt, dims: `${a.width}×${a.height}`, style: a.style })}>
                <img src={v.url} alt={a.prompt} className="w-full h-full object-cover" />
                <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition flex flex-col justify-end p-3">
                  <p className="text-white text-[10px] line-clamp-3 mb-1">{a.headline || a.prompt}</p>
                  <p className="text-white/70 text-[9px] mb-2">{a.width}×{a.height}{a.style ? ` · ${a.style}` : ''}</p>
                  <div className="flex gap-1.5">
                    {a.source === 'fallback_svg' && (
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-amber-500/80 text-white">Preview</span>
                    )}
                    <a href={v.url} download className="ml-auto p-1 rounded hover:bg-white/20 text-white" title="Download" onClick={(e) => e.stopPropagation()}>
                      <Upload size={11} className="rotate-180" />
                    </a>
                    <button onClick={async (e) => {
                      e.stopPropagation();
                      try {
                        const r = await axios.post(
                          `${API}/api/marketing/creative/director/expand-from-asset/${a.id}`,
                          {}, { headers, timeout: 90000 }
                        );
                        notify.success('Expanded to full campaign — switch to AI Director tab to view');
                        try {
                          window.dispatchEvent(new CustomEvent('director:open-brief', { detail: { briefId: r.data?.id } }));
                        } catch {}
                      } catch (e2) {
                        notifyApiError(notify, e2, 'Expand failed');
                      }
                    }} className="p-1 rounded hover:bg-white/20 text-white" title="Expand to full campaign" data-testid={`creative-expand-${a.id}`}>
                      <Wand2 size={11} />
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); remove(a.id, a.headline || a.prompt); }} className="p-1 rounded hover:bg-white/20 text-white" data-testid={`creative-delete-${a.id}`} aria-label="Delete">
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>
              </div>
            )))}
          </div>
        )}
      </div>

      {lightbox && (
        <div
          className="fixed inset-0 z-[60] bg-black/90 flex items-center justify-center p-4"
          onClick={() => setLightbox(null)}
          data-testid="creative-lightbox"
        >
          <button
            onClick={() => setLightbox(null)}
            className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 text-white grid place-items-center"
            aria-label="Close"
            data-testid="creative-lightbox-close"
          >
            <X size={18}/>
          </button>
          <div className="max-w-[95vw] max-h-[90vh] flex flex-col items-center" onClick={(e) => e.stopPropagation()}>
            <img
              src={lightbox.url}
              alt={lightbox.headline}
              className="max-w-full max-h-[80vh] object-contain rounded-lg shadow-2xl"
            />
            <div className="mt-3 text-center">
              <p className="text-white font-semibold text-sm max-w-2xl">{lightbox.headline}</p>
              <p className="text-white/50 text-xs mt-1">
                {lightbox.dims}{lightbox.style ? ` · ${lightbox.style}` : ''}
              </p>
              <a
                href={lightbox.url}
                download
                className="inline-flex items-center gap-1.5 mt-3 px-4 py-2 rounded-md bg-white/10 hover:bg-white/20 text-white text-xs font-bold"
                onClick={(e) => e.stopPropagation()}
              >
                <Upload size={11} className="rotate-180"/> Download
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const Field = ({ label, children }) => (
  <div>
    <label className="text-[11px] font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-1 block">{label}</label>
    {children}
  </div>
);

export default CreativeStudioTab;
export { CreativeStudioTab as LegacyCreativeStudioTab };
