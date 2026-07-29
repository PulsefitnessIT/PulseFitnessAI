/**
 * Brand Auto-Discovery panel — iter 216h70.
 *
 * Lives at the top of Marketing → Brand Kit. Lets the operator point
 * us at their existing website and we crawl it in the background to
 * build the brand kit (colours, fonts, logos, marketing images) plus
 * a one-page intelligence pack (tone-of-voice, audience segments,
 * current campaigns, social handles).
 *
 * Flow:
 *   1. Idle — show "Discover your brand from your website" CTA.
 *   2. Running — show progress card with stage label + visited count.
 *   3. Ready — show extracted draft (colour swatches, fonts, logo /
 *      image grids, intelligence list, socials) with Apply / Discard.
 *   4. Applied/Failed — show last-run summary and offer "Re-run".
 *
 * Polls /status every 2 s while running. Stops as soon as state is
 * `ready` / `applied` / `failed`.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import {
  Sparkles, Globe, Loader2, CheckCircle2, AlertTriangle, RefreshCw,
  Palette, Type, Image as ImageIcon, Megaphone, Users, Heart, X,
  Award, MousePointerClick, Video, Search, Layout,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { useTranslation } from 'react-i18next';

const STATUS = {
  IDLE: 'idle',
  RUNNING: 'running',
  READY: 'ready',
  APPLIED: 'applied',
  FAILED: 'failed',
};

export default function BrandDiscoveryPanel({ API, headers, onApplied }) {
  const { t } = useTranslation();
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [websiteUrl, setWebsiteUrl] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/marketing/brand-discovery/status`, { headers });
      setDoc(r.data || null);
      if (r.data?.website_url && !websiteUrl) setWebsiteUrl(r.data.website_url);
    } catch (e) {
      // 404 is fine — means no draft yet
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  // Poll while the crawl is running
  useEffect(() => {
    if (doc?.status === STATUS.RUNNING) {
      pollRef.current = setInterval(load, 2000);
      return () => clearInterval(pollRef.current);
    }
    return undefined;
  }, [doc?.status, load]);

  const start = async () => {
    if (!websiteUrl.trim()) {
      notify.error(t('mkt.bd_url_required', 'Enter your website URL first'));
      return;
    }
    let url = websiteUrl.trim();
    if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
    setSubmitting(true);
    try {
      await axios.post(`${API}/api/marketing/brand-discovery/start`, { website_url: url }, { headers });
      notify.success(t('mkt.bd_started', 'Brand discovery started — we will learn from your website in the background.'));
      load();
    } catch (e) {
      notifyApiError(notify, e, t('mkt.bd_start_err', 'Could not start brand discovery'));
    } finally {
      setSubmitting(false);
    }
  };

  const apply = async () => {
    setSubmitting(true);
    try {
      await axios.post(`${API}/api/marketing/brand-discovery/apply`, {
        apply_colours: true, apply_fonts: true, apply_primary_logo: true, apply_voice: true,
      }, { headers });
      notify.success(t('mkt.bd_applied', 'Applied to your brand kit ✨'));
      load();
      onApplied?.();
    } catch (e) {
      notifyApiError(notify, e, t('mkt.bd_apply_err', 'Apply failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const discard = async () => {
    setSubmitting(true);
    try {
      await axios.post(`${API}/api/marketing/brand-discovery/discard`, {}, { headers });
      setDoc(null);
      notify.success(t('mkt.bd_discarded', 'Discovery draft discarded.'));
    } catch (e) {
      notifyApiError(notify, e, t('mkt.bd_discard_err', 'Could not discard'));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return null;

  // ── States ─────────────────────────────────────────────
  const status = doc?.status || STATUS.IDLE;
  const draft = doc?.draft;
  const progress = doc?.progress || {};

  return (
    <div
      className="rounded-2xl border p-5 mb-5"
      style={{
        background: 'linear-gradient(135deg, rgba(99,102,241,0.06), rgba(34,211,238,0.06))',
        borderColor: 'rgba(99,102,241,0.25)',
      }}
      data-testid="brand-discovery-panel"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="text-[10px] uppercase tracking-wider font-extrabold text-indigo-500 flex items-center gap-1.5">
            <Sparkles size={11} /> {t('mkt.bd_eyebrow', 'Brand auto-discovery')}
          </div>
          <h3 className="text-base font-bold mt-1">{t('mkt.bd_heading', 'Learn your brand from your existing website')}</h3>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 max-w-xl">
            {t('mkt.bd_intro', 'Drop in your website URL and we will crawl the homepage + key pages to extract your colours, fonts, logos, tone-of-voice, audience segments, current campaigns and social handles — saving you hours of setup.')}
          </p>
        </div>
        {(status === STATUS.APPLIED || status === STATUS.FAILED) && (
          <button
            onClick={() => { setDoc({ ...doc, status: STATUS.IDLE }); }}
            className="text-[10px] font-bold uppercase tracking-wider text-indigo-500 hover:text-indigo-700 flex items-center gap-1"
            data-testid="brand-discovery-rerun"
          >
            <RefreshCw size={10} /> {t('mkt.bd_rerun', 'Re-run')}
          </button>
        )}
      </div>

      {/* ── IDLE / re-run state ── */}
      {(status === STATUS.IDLE || (!doc && !loading)) && (
        <div className="flex gap-2 flex-wrap">
          <div className="flex-1 min-w-[260px] relative">
            <Globe size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
            <input
              type="url"
              value={websiteUrl}
              onChange={(e) => setWebsiteUrl(e.target.value)}
              placeholder="https://your-gym.com"
              className="w-full pl-9 pr-3 py-2.5 text-sm rounded-md border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900"
              data-testid="brand-discovery-url-input"
            />
          </div>
          <button
            onClick={start}
            disabled={submitting || !websiteUrl.trim()}
            className="px-5 py-2.5 text-sm font-bold rounded-md bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 flex items-center gap-1.5"
            data-testid="brand-discovery-start"
          >
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {t('mkt.bd_discover_btn', 'Discover my brand')}
          </button>
        </div>
      )}

      {/* ── RUNNING ── */}
      {status === STATUS.RUNNING && (
        <div className="rounded-md border border-indigo-200 dark:border-indigo-800 bg-white/60 dark:bg-zinc-900/40 p-3 flex items-center gap-3" data-testid="brand-discovery-running">
          <Loader2 size={18} className="animate-spin text-indigo-500" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold">{t('mkt.bd_learning', 'Learning your brand…')}</p>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 truncate">
              {progress.stage || t('mkt.bd_starting', 'starting up')}
              {progress.visited != null && progress.queued ? ` · ${t('mkt.bd_page', 'page')} ${progress.visited}/${progress.queued}` : ''}
            </p>
          </div>
        </div>
      )}

      {/* ── READY — draft preview ── */}
      {status === STATUS.READY && draft && (
        <div className="space-y-4" data-testid="brand-discovery-draft">
          <div className="rounded-md bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-900 p-3 text-xs flex items-start gap-2">
            <CheckCircle2 size={14} className="text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
            <span className="text-emerald-700 dark:text-emerald-200">
              <strong>{t('mkt.bd_draft_ready', 'Brand draft ready.')}</strong> {t('mkt.bd_draft_ready_body', 'Review what we found below, then click Apply to brand kit to commit. Re-run any time to refresh after a redesign.')}
            </span>
          </div>

          {/* Colours */}
          {draft.colours?.length > 0 && (
            <Section title={t('mkt.bd_colours', 'Colours')} icon={Palette}>
              <div className="flex flex-wrap gap-2">
                {draft.colours.map((c) => (
                  <div key={c} className="flex items-center gap-1.5 px-2 py-1 rounded-md border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-xs">
                    <span className="w-4 h-4 rounded shrink-0" style={{ background: c }} />
                    <span className="font-mono">{c}</span>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Fonts */}
          {(draft.fonts?.heading || draft.fonts?.body) && (
            <Section title={t('mkt.bd_fonts', 'Fonts')} icon={Type}>
              <div className="text-xs space-y-0.5">
                {draft.fonts.heading && <div><span className="text-zinc-500 dark:text-zinc-400">{t('mkt.bd_heading_lbl', 'Heading:')}</span> <strong>{draft.fonts.heading}</strong></div>}
                {draft.fonts.body && <div><span className="text-zinc-500 dark:text-zinc-400">{t('mkt.bd_body_lbl', 'Body:')}</span> <strong>{draft.fonts.body}</strong></div>}
              </div>
            </Section>
          )}

          {/* Logos */}
          {draft.logos?.length > 0 && (
            <Section title={t('mkt.bd_logo_candidates', 'Logo candidates')} icon={ImageIcon}>
              <div className="flex flex-wrap gap-2">
                {draft.logos.map((l, i) => (
                  <div key={i} className="w-20 h-20 rounded-md border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 flex items-center justify-center overflow-hidden p-1">
                    <img src={l.stored_url} alt="" className="max-w-full max-h-full object-contain" />
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-zinc-500 dark:text-zinc-400 mt-1">{t('mkt.bd_logo_note', 'The first logo will become your primary on apply.')}</p>
            </Section>
          )}

          {/* Marketing images */}
          {draft.images?.length > 0 && (
            <Section title={t('mkt.bd_imagery', 'Marketing imagery ({{n}})', { n: draft.images.length })} icon={ImageIcon}>
              <div className="grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-8 gap-2">
                {draft.images.map((img, i) => (
                  <img key={i} src={img.stored_url} alt=""
                    className="aspect-square object-cover rounded-md border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900" />
                ))}
              </div>
              <p className="text-[10px] text-zinc-500 dark:text-zinc-400 mt-1">
                {t('mkt.bd_imagery_note', 'Mirrored to your library (compressed, ≤2000 px, quality 85). Available in the Creative Studio.')}
              </p>
            </Section>
          )}

          {/* Iter 216h73 — Homepage headlines (hero H1 + value-prop H2s) */}
          {(draft.headlines?.h1 || draft.headlines?.h2s?.length > 0) && (
            <Section title={t('mkt.bd_homepage_copy', 'Homepage copy')} icon={Layout}>
              {draft.headlines.h1 && (
                <div className="mb-2">
                  <div className="text-[10px] uppercase tracking-wider font-semibold text-zinc-400 mb-0.5">{t('mkt.bd_hero_headline', 'Hero headline')}</div>
                  <p className="text-sm font-semibold leading-snug" data-testid="brand-discovery-hero-h1">{draft.headlines.h1}</p>
                </div>
              )}
              {draft.headlines.h2s?.length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider font-semibold text-zinc-400 mb-0.5">{t('mkt.bd_value_props_h2', 'Value props (H2)')}</div>
                  <ul className="text-xs space-y-0.5 list-disc pl-4 text-zinc-700 dark:text-zinc-300">
                    {draft.headlines.h2s.map((h, i) => <li key={i}>{h}</li>)}
                  </ul>
                </div>
              )}
            </Section>
          )}

          {/* Iter 216h73 — Homepage meta (page title, og, meta description) */}
          {draft.homepage_meta && Object.keys(draft.homepage_meta).length > 0 && (
            <Section title={t('mkt.bd_seo', 'SEO & sharing')} icon={Search}>
              <div className="text-xs space-y-1.5">
                {draft.homepage_meta.page_title && <Row label={t('mkt.bd_page_title', 'Page title')}>{draft.homepage_meta.page_title}</Row>}
                {draft.homepage_meta.meta_description && <Row label={t('mkt.bd_meta_desc', 'Meta description')}>{draft.homepage_meta.meta_description}</Row>}
                {(draft.homepage_meta.og_title || draft.homepage_meta.og_description) && (
                  <Row label={t('mkt.bd_og', 'Open Graph (Facebook / LinkedIn share)')}>
                    {draft.homepage_meta.og_title && <div className="font-semibold">{draft.homepage_meta.og_title}</div>}
                    {draft.homepage_meta.og_description && <div className="text-zinc-500 dark:text-zinc-400">{draft.homepage_meta.og_description}</div>}
                  </Row>
                )}
              </div>
            </Section>
          )}

          {/* Iter 216h73 — Primary CTAs */}
          {draft.ctas?.length > 0 && (
            <Section title={t('mkt.bd_ctas', 'Primary CTAs')} icon={MousePointerClick}>
              <div className="flex flex-wrap gap-1.5">
                {draft.ctas.map((cta, i) => (
                  <span key={i} className="px-2 py-1 rounded-md border border-indigo-200 dark:border-indigo-900 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-200 text-xs font-semibold">
                    {cta.label}
                  </span>
                ))}
              </div>
              <p className="text-[10px] text-zinc-500 dark:text-zinc-400 mt-1">{t('mkt.bd_ctas_note', 'CTAs match the brand voice — copy / replicate in your own campaigns.')}</p>
            </Section>
          )}

          {/* Iter 216h73 — Social proof */}
          {draft.social_proof?.length > 0 && (
            <Section title={t('mkt.bd_social_proof', 'Social proof')} icon={Award}>
              <ul className="text-xs space-y-0.5 list-disc pl-4 text-zinc-700 dark:text-zinc-300">
                {draft.social_proof.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </Section>
          )}

          {/* Iter 216h73 — Hero video */}
          {draft.hero_video && draft.hero_video.src && (
            <Section title={t('mkt.bd_hero_video', 'Hero video')} icon={Video}>
              <a href={draft.hero_video.src} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 dark:text-indigo-300 hover:underline break-all">
                <Video size={11} /> {draft.hero_video.src}
              </a>
            </Section>
          )}

          {/* Intelligence */}
          {draft.intelligence && Object.keys(draft.intelligence).length > 0 && (
            <Section title={t('mkt.bd_intel', 'Marketing intelligence')} icon={Sparkles}>
              <div className="space-y-3 text-xs">
                {draft.intelligence.vertical && (
                  <Row label={t('mkt.bd_vertical', 'Detected vertical')}>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200">{draft.intelligence.vertical}</span>
                  </Row>
                )}
                {draft.intelligence.tone_of_voice && (
                  <Row icon={Heart} label={t('mkt.bd_tone', 'Tone of voice')}>{draft.intelligence.tone_of_voice}</Row>
                )}
                {draft.intelligence.value_propositions?.length > 0 && (
                  <Row label={t('mkt.bd_value_props', 'Value propositions')}>
                    <ul className="list-disc pl-4 space-y-0.5">
                      {draft.intelligence.value_propositions.map((v, i) => <li key={i}>{v}</li>)}
                    </ul>
                  </Row>
                )}
                {draft.intelligence.audiences?.length > 0 && (
                  <Row icon={Users} label={t('mkt.bd_audiences', 'Audiences')}>
                    {draft.intelligence.audiences.map((a, i) => (
                      <span key={i} className="inline-block mr-1 mb-1 px-1.5 py-0.5 rounded text-[10px] bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-200">{a}</span>
                    ))}
                  </Row>
                )}
                {draft.intelligence.current_campaigns?.length > 0 && (
                  <Row icon={Megaphone} label={t('mkt.bd_current_promos', 'Current promos')}>
                    <ul className="list-disc pl-4 space-y-0.5">
                      {draft.intelligence.current_campaigns.map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                  </Row>
                )}
                {draft.intelligence.pricing_model && (
                  <Row label={t('mkt.bd_pricing_model', 'Pricing model')}>{draft.intelligence.pricing_model}</Row>
                )}
                {draft.intelligence.competitor_mentions?.length > 0 && (
                  <Row label={t('mkt.bd_competitors', 'Competitors mentioned')}>
                    {draft.intelligence.competitor_mentions.map((c, i) => (
                      <span key={i} className="inline-block mr-1 mb-1 px-1.5 py-0.5 rounded text-[10px] bg-zinc-100 dark:bg-zinc-800">{c}</span>
                    ))}
                  </Row>
                )}
              </div>
            </Section>
          )}

          {/* Socials */}
          {draft.socials && Object.keys(draft.socials).length > 0 && (
            <Section title={t('mkt.bd_socials', 'Social handles')} icon={Megaphone}>
              <div className="flex flex-wrap gap-2 text-xs">
                {Object.entries(draft.socials).map(([k, v]) => (
                  <a key={k} href={v} target="_blank" rel="noopener noreferrer"
                    className="px-2 py-1 rounded-md border border-zinc-200 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-800">
                    <span className="capitalize font-medium">{k}</span>
                  </a>
                ))}
              </div>
            </Section>
          )}

          {/* Pages */}
          {draft.pages_visited?.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-zinc-500 dark:text-zinc-400">{t('mkt.bd_pages_crawled', '{{n}} pages crawled', { n: draft.pages_visited.length })}</summary>
              <ul className="mt-2 space-y-0.5 list-disc pl-5 text-zinc-500 dark:text-zinc-400">
                {draft.pages_visited.map((p, i) => <li key={i}>{p.title || p.url}</li>)}
              </ul>
            </details>
          )}

          {/* Actions */}
          <div className="flex gap-2 justify-end pt-2 border-t border-indigo-100 dark:border-indigo-900/40">
            <button onClick={discard} disabled={submitting}
              className="px-3 py-2 text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-md flex items-center gap-1.5 disabled:opacity-50"
              data-testid="brand-discovery-discard">
              <X size={12} /> {t('mkt.bd_discard', 'Discard')}
            </button>
            <button onClick={apply} disabled={submitting}
              className="px-4 py-2 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-md flex items-center gap-1.5 disabled:opacity-50"
              data-testid="brand-discovery-apply">
              {submitting ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
              {t('mkt.bd_apply_btn', 'Apply to brand kit')}
            </button>
          </div>
        </div>
      )}

      {/* ── APPLIED — confirmation card ── */}
      {status === STATUS.APPLIED && (
        <div className="rounded-md border border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-900/20 p-3 text-xs flex items-center gap-2">
          <CheckCircle2 size={14} className="text-emerald-600 dark:text-emerald-400" />
          <span>{t('mkt.bd_applied_card', 'Discovery applied. Re-run any time after a website redesign.')}</span>
        </div>
      )}

      {/* ── FAILED ── */}
      {status === STATUS.FAILED && (
        <div className="rounded-md border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-900/20 p-3 text-xs flex items-start gap-2" data-testid="brand-discovery-failed">
          <AlertTriangle size={14} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <span>
            {t('mkt.bd_failed', 'We could not finish learning your brand:')} <strong>{doc?.error || t('mkt.bd_unknown_err', 'unknown error')}</strong>.
            {' '}{t('mkt.bd_failed_hint', 'Double-check the URL and try again.')}
          </span>
        </div>
      )}
    </div>
  );
}

function Section({ title, icon: Icon, children }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5 mb-1.5">
        {Icon && <Icon size={11} />} {title}
      </div>
      {children}
    </div>
  );
}

function Row({ icon: Icon, label, children }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider font-semibold text-zinc-400 flex items-center gap-1 mb-0.5">
        {Icon && <Icon size={10} />} {label}
      </div>
      <div>{children}</div>
    </div>
  );
}
