/**
 * Marketing → Brand Kit tab.
 *
 * Single source of truth for the operator's brand:
 *   • Logo (inline data URL — used by AI Director for brand-locked posters)
 *   • Primary + secondary colours
 *   • Heading + body fonts
 *   • Voice ("warm, energetic, inclusive")
 *   • Banned phrases (the AI will steer clear)
 *
 * Also surfaces a one-tap shortcut from a banner that other tabs render
 * when the kit is empty (`configured: false`) so users coming from
 * onboarding never miss it.
 */
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import {
  Palette, Loader2, CheckCircle2, Upload, Image as ImageIcon, Type,
  Volume2, ShieldAlert, X,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import BrandDiscoveryPanel from './BrandDiscoveryPanel';
import StarterPackPanel from './StarterPackPanel';
import { useTranslation } from 'react-i18next';

export default function BrandKitTab({ API, headers }) {
  const { t } = useTranslation();
  const [kit, setKit] = useState(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const load = () => {
    axios.get(`${API}/api/marketing/brand-kit`, { headers })
      .then((r) => setKit(r.data.brand_kit))
      .catch(() => notify.error(t('mkt.bk_load_err', 'Failed to load brand kit')));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  useEffect(() => { load();   }, []);

  const save = async (patch) => {
    setBusy(true);
    try {
      const r = await axios.put(`${API}/api/marketing/brand-kit`, patch, { headers });
      setKit(r.data.brand_kit);
      notify.success(t('mkt.bk_saved', 'Brand kit saved'));
    } catch (e) {
      notifyApiError(notify, e, t('mkt.bk_save_err', 'Save failed'));
    }
    setBusy(false);
  };

  const onLogoUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      notify.error(t('mkt.bk_logo_size', 'Logo must be under 2 MB'));
      return;
    }
    setUploading(true);
    try {
      // Iter 216h59 — also upload to the org-level logo endpoint so the
      // navbar picks up the new logo automatically AND we get the
      // auto-extracted brand palette back. We then auto-populate the
      // BrandKit's primary + secondary colours from the dominant
      // colours pulled out of the image — operator no longer has to
      // hand-pick colours that match their logo.
      const fd = new FormData();
      fd.append('file', file);
      let extracted = [];
      try {
        const orgRes = await axios.post(`${API}/api/account/logo`, fd, {
          headers: { ...headers, 'Content-Type': 'multipart/form-data' },
        });
        extracted = orgRes.data?.brand_palette || [];
      } catch (orgErr) {
        // Org-level upload failure doesn't block the BrandKit upload —
        // operator can still hand-pick colours below.
         
        console.warn('Org logo sync failed (non-fatal):', orgErr);
      }

      const reader = new FileReader();
      reader.onload = async () => {
        const dataUrl = reader.result;
        const patch = { primary_logo_data_url: dataUrl };
        // Auto-apply extracted palette only when the operator hasn't
        // already set custom colours (i.e. they're still the Pulse Fitness
        // defaults). This avoids stomping on a brand they've curated.
        const defaults = ['#19CDFF', '#5B8CFF', '#66CCFF', '#0055FF', '#000000', '#ffffff', '#FFFFFF'];
        const primaryIsDefault = !kit?.primary_color || defaults.includes((kit.primary_color || '').toUpperCase()) || defaults.includes((kit.primary_color || '').toLowerCase());
        const secondaryIsDefault = !kit?.secondary_color || defaults.includes((kit.secondary_color || '').toUpperCase()) || defaults.includes((kit.secondary_color || '').toLowerCase());
        if (extracted[0] && primaryIsDefault) patch.primary_color = extracted[0];
        if (extracted[1] && secondaryIsDefault) patch.secondary_color = extracted[1];
        await save(patch);
        if (extracted.length > 0 && (patch.primary_color || patch.secondary_color)) {
          notify.success(
            t('mkt.bk_colours_detected', 'Brand colours auto-detected: {{colours}}', { colours: [patch.primary_color, patch.secondary_color].filter(Boolean).join(' + ') }),
          );
        }
        setUploading(false);
      };
      reader.onerror = () => { notify.error(t('mkt.bk_read_err', 'Could not read file')); setUploading(false); };
      reader.readAsDataURL(file);
    } catch (err) {
      notify.error(t('mkt.bk_upload_err', 'Upload failed'));
      setUploading(false);
    }
  };

  if (!kit) {
    return (
      <div className="flex items-center justify-center py-20 text-zinc-500 dark:text-zinc-400 text-sm gap-2">
        <Loader2 size={14} className="animate-spin" /> {t('mkt.bk_loading', 'Loading brand kit…')}
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="brand-kit-tab">
      {/* Iter 216h70 — Brand auto-discovery from website. Crawls the
          customer's site in the background and proposes a brand draft
          (colours, fonts, logos, marketing images + intelligence). */}
      <BrandDiscoveryPanel API={API} headers={headers} onApplied={load} />

      {/* Iter 216h71 — once they have a voice/tone (manually set or
          from brand discovery), let them one-click draft a starter
          pack of 3 emails + 3 social posts in their tone. */}
      <StarterPackPanel API={API} headers={headers} />

      {/* Logo */}
      <Section icon={ImageIcon} title={t('mkt.bk_logo', 'Logo')}
        hint={t('mkt.bk_logo_hint', 'Used at the top of Director posters and email headers. PNG with transparency works best.')}>
        <div className="flex items-start gap-4 flex-wrap">
          <div className="w-28 h-28 rounded-xl border-2 border-dashed border-zinc-300 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/40 flex items-center justify-center overflow-hidden">
            {kit.primary_logo_data_url ? (
              <img src={kit.primary_logo_data_url} alt="Logo" className="max-w-full max-h-full object-contain" />
            ) : kit.primary_logo_url ? (
              <img src={kit.primary_logo_url} alt="Logo (from onboarding)" className="max-w-full max-h-full object-contain" />
            ) : (
              <ImageIcon size={32} className="text-zinc-300 dark:text-zinc-600" />
            )}
          </div>
          <div className="flex-1 min-w-0 space-y-2">
            {!kit.primary_logo_data_url && kit.primary_logo_url && (
              <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-500 inline-flex items-center gap-1">
                <CheckCircle2 size={10}/> {t('mkt.bk_from_onboarding', 'Pulled from onboarding — replace any time')}
              </p>
            )}
            <input ref={fileRef} type="file" accept="image/*"
              onChange={onLogoUpload} className="hidden"
              data-testid="brand-logo-input"/>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="px-3 py-2 rounded-md bg-violet-500 text-white text-xs font-extrabold inline-flex items-center gap-1.5 disabled:opacity-50"
              data-testid="brand-logo-upload"
            >
              {uploading ? <Loader2 size={11} className="animate-spin"/> : <Upload size={11}/>}
              {kit.primary_logo_data_url ? t('mkt.bk_replace_logo', 'Replace logo') : t('mkt.bk_upload_logo', 'Upload logo')}
            </button>
            {kit.primary_logo_data_url && (
              <button onClick={() => save({ primary_logo_data_url: null, primary_logo_asset_id: null })}
                className="ml-2 text-xs font-bold text-rose-500 inline-flex items-center gap-1"
                data-testid="brand-logo-remove">
                <X size={11}/> {t('mkt.bk_remove', 'Remove')}
              </button>
            )}
            <p className="text-[10px] text-zinc-400 dark:text-zinc-500 max-w-sm">{t('mkt.bk_logo_note', 'PNG, JPG or SVG · under 2 MB · ideally transparent background.')}</p>
          </div>
        </div>
      </Section>

      {/* Colours */}
      <Section icon={Palette} title={t('mkt.bk_colours', 'Colours')}
        hint={t('mkt.bk_colours_hint', 'Primary lands on CTAs and emphasis. Secondary balances accents.')}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <ColourField label={t('mkt.bk_primary', 'Primary')}  value={kit.primary_color}   testId="brand-color-primary"
            onChange={(v) => save({ primary_color: v })}/>
          <ColourField label={t('mkt.bk_secondary', 'Secondary')} value={kit.secondary_color} testId="brand-color-secondary"
            onChange={(v) => save({ secondary_color: v })}/>
        </div>
      </Section>

      {/* Fonts */}
      <Section icon={Type} title={t('mkt.bk_fonts', 'Fonts')}
        hint={t('mkt.bk_fonts_hint', 'Names of Google or system fonts. Director uses these in posters; Marketing emails fall back to web-safe stack.')}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <TextField label={t('mkt.bk_font_heading', 'Heading font')} value={kit.font_heading || ''} placeholder={t('mkt.bk_font_heading_ph', 'e.g. Bricolage Grotesque')}
            testId="brand-font-heading"
            onCommit={(v) => save({ font_heading: v.trim() || null })}/>
          <TextField label={t('mkt.bk_font_body', 'Body font')} value={kit.font_body || ''} placeholder={t('mkt.bk_font_body_ph', 'e.g. Inter')}
            testId="brand-font-body"
            onCommit={(v) => save({ font_body: v.trim() || null })}/>
        </div>
      </Section>

      {/* Voice */}
      <Section icon={Volume2} title={t('mkt.bk_voice', 'Voice')}
        hint={t('mkt.bk_voice_hint', 'One-line description of your brand voice — Director feeds this directly to the LLM.')}>
        <TextField label={t('mkt.bk_voice_label', 'Voice description')} value={kit.voice || ''} placeholder={t('mkt.bk_voice_ph', 'warm, energetic, inclusive — never pushy')}
          testId="brand-voice"
          onCommit={(v) => save({ voice: v.trim() || null })}/>
      </Section>

      {/* Banned phrases */}
      <Section icon={ShieldAlert} title={t('mkt.bk_banned', 'Banned phrases')}
        hint={t('mkt.bk_banned_hint', 'Phrases the AI must never use. Add one per line.')}>
        <BannedPhrasesEditor phrases={kit.banned_phrases || []}
          placeholder={t('mkt.bk_banned_ph', 'no fluff\nno hard sell\nno emojis in subject lines')}
          onCommit={(arr) => save({ banned_phrases: arr })}/>
      </Section>

      {busy && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 px-3 py-2 rounded-md bg-zinc-900 text-white text-xs font-bold inline-flex items-center gap-2 shadow-lg z-40">
          <Loader2 size={11} className="animate-spin"/> {t('mkt.bk_saving', 'Saving brand kit…')}
        </div>
      )}
    </div>
  );
}


function Section({ icon: Icon, title, hint, children }) {
  return (
    <section className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
      <div className="flex items-start gap-2 mb-3">
        <Icon size={14} className="text-violet-500 mt-1" />
        <div>
          <h3 className="text-sm font-extrabold text-zinc-900 dark:text-zinc-100">{title}</h3>
          {hint && <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-0.5">{hint}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}


function ColourField({ label, value, onChange, testId }) {
  return (
    <label className="flex items-center gap-3 rounded-md border border-zinc-200 dark:border-zinc-800 p-2.5">
      <input type="color" value={value} onChange={(e) => onChange(e.target.value)}
        className="w-12 h-12 rounded-md cursor-pointer border-0 p-0"
        data-testid={testId}/>
      <div className="flex-1 min-w-0">
        <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 dark:text-zinc-400">{label}</p>
        <p className="font-mono text-sm font-bold text-zinc-900 dark:text-zinc-100">{value}</p>
      </div>
    </label>
  );
}


function TextField({ label, value, placeholder, testId, onCommit }) {
  const [v, setV] = useState(value);
  useEffect(() => { setV(value); }, [value]);
  return (
    <div>
      <label className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 dark:text-zinc-400 mb-1 block">{label}</label>
      <input type="text" value={v} placeholder={placeholder}
        onChange={(e) => setV(e.target.value)}
        onBlur={() => v !== value && onCommit(v)}
        onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
        className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 bg-transparent rounded-md text-sm text-zinc-900 dark:text-zinc-100"
        data-testid={testId}/>
    </div>
  );
}


function BannedPhrasesEditor({ phrases, onCommit, placeholder }) {
  const [text, setText] = useState((phrases || []).join('\n'));
  useEffect(() => { setText((phrases || []).join('\n')); }, [phrases]);

  const commit = () => {
    const arr = text.split('\n').map((s) => s.trim()).filter(Boolean);
    if (JSON.stringify(arr) !== JSON.stringify(phrases)) onCommit(arr);
  };
  return (
    <textarea value={text} onChange={(e) => setText(e.target.value)} onBlur={commit}
      rows={4}
      placeholder={placeholder}
      className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 bg-transparent rounded-md text-xs font-mono text-zinc-900 dark:text-zinc-100"
      data-testid="brand-banned-phrases"/>
  );
}


export { BrandKitTab };
