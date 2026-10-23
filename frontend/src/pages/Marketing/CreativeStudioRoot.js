/**
 * Creative Studio entry — switches between the new AI Director (default)
 * and the original single-asset builder.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Sparkles, ImagePlus, HeartCrack } from 'lucide-react';
import AIDirectorPanel from './AIDirectorPanel';
import ChurnRescuePanel from './ChurnRescuePanel';
import { LegacyCreativeStudioTab } from './CreativeStudioTab';

const CreativeStudioRoot = ({ API, headers, entitlement }) => {
  const { t } = useTranslation();
  const [view, setView] = useState('director');
  const [seedBriefId, setSeedBriefId] = useState(null);
  // Only Owners / Managers / Master Admins create images; others get the gallery only.
  const [canCreate, setCanCreate] = useState(true);
  useEffect(() => {
    axios.get(`${API}/api/marketing/creative/permissions`, { headers })
      .then((r) => {
        const ok = r.data?.can_create !== false;
        setCanCreate(ok);
        if (!ok) setView((v) => (v === 'director' ? 'asset' : v));
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount
  }, []);

  // Phase 4 — when the legacy "Single Asset" tab fires director:open-brief
  // (after Expand-to-Campaign), auto-switch to the Director tab and load it
  useEffect(() => {
    const handler = (e) => {
      const id = e?.detail?.briefId;
      if (id) {
        setSeedBriefId(id);
        setView('director');
      }
    };
    window.addEventListener('director:open-brief', handler);
    return () => window.removeEventListener('director:open-brief', handler);
  }, []);

  return (
    <div className="space-y-3" data-testid="creative-studio-root">
      <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-900/60 px-3 py-2 flex items-center justify-between flex-wrap gap-2">
        <div className="flex w-full sm:w-auto sm:inline-flex rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-0.5 overflow-hidden">
          {canCreate && (
          <button onClick={() => setView('director')}
            title={t('mkt.csr_director_tip', 'Recommended: one prompt → strategy, multi-format copy, brand-locked poster, segment variants and AI scheduling')}
            className={`flex-1 sm:flex-initial min-w-0 px-2 sm:px-3 py-1.5 rounded-md text-[11px] sm:text-xs font-semibold flex items-center justify-center gap-1 sm:gap-1.5 transition ${
              view === 'director'
                ? 'bg-[var(--color-brand-blue)] text-white shadow-sm'
                : 'text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-100'
            }`}
            data-testid="cs-tab-director">
            <Sparkles size={12} className="flex-shrink-0"/>
            <span className="truncate">{t('mkt.csr_director', 'AI Director')}</span>
            <span className="hidden sm:inline ml-1 text-[9px] uppercase tracking-wider px-1 rounded bg-emerald-500/15 text-emerald-500">{t('mkt.csr_recommended', 'Recommended')}</span>
          </button>
          )}
          <button onClick={() => setView('asset')}
            title={t('mkt.csr_asset_tip', 'One-off image generator — use when you only need a poster, not a full campaign')}
            className={`flex-1 sm:flex-initial min-w-0 px-2 sm:px-3 py-1.5 rounded-md text-[11px] sm:text-xs font-semibold flex items-center justify-center gap-1 sm:gap-1.5 transition ${
              view === 'asset'
                ? 'bg-[var(--color-brand-blue)] text-white shadow-sm'
                : 'text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-100'
            }`}
            data-testid="cs-tab-asset">
            <ImagePlus size={12} className="flex-shrink-0"/>
            <span className="truncate">{t('mkt.csr_quick_poster', 'Quick Poster')}</span>
          </button>
          <button onClick={() => setView('churn')}
            title={t('mkt.csr_churn_tip', "True 1:1 win-back: detect each at-risk member's exact exit signal and write bespoke rescue copy")}
            className={`flex-1 sm:flex-initial min-w-0 px-2 sm:px-3 py-1.5 rounded-md text-[11px] sm:text-xs font-semibold flex items-center justify-center gap-1 sm:gap-1.5 transition ${
              view === 'churn'
                ? 'bg-rose-500 text-white shadow-sm'
                : 'text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-100'
            }`}
            data-testid="cs-tab-churn">
            <HeartCrack size={12} className="flex-shrink-0"/>
            <span className="truncate">{t('mkt.csr_churn_rescue', 'Churn Rescue')}</span>
            <span className="hidden sm:inline ml-1 text-[9px] uppercase tracking-wider px-1 rounded bg-rose-500/20 text-rose-100">{t('mkt.csr_1to1', '1:1')}</span>
          </button>
        </div>
        <p className="text-[10px] text-zinc-500 dark:text-zinc-400 max-w-md">
          {view === 'director'
            ? t('mkt.csr_help_director', '✨ Full campaign — strategy, copy across every channel, brand-locked image, segment variants & auto-scheduling. Start here.')
            : view === 'asset'
              ? t('mkt.csr_help_asset', '🖼️ Quick one-off poster only. For a full campaign with email + IG + SMS + push copy, use AI Director.')
              : t('mkt.csr_help_churn', "💔 True 1:1 win-back — detect each lapsing member's exact exit signal and let Claude write a bespoke rescue message that names their behaviour.")}
        </p>
      </div>

      {view === 'director' && canCreate
        ? <AIDirectorPanel API={API} headers={headers} entitlement={entitlement} seedBriefId={seedBriefId} onSeedConsumed={() => setSeedBriefId(null)}/>
        : view === 'asset'
          ? <LegacyCreativeStudioTab API={API} headers={headers} entitlement={entitlement}/>
          : <ChurnRescuePanel API={API} headers={headers} entitlement={entitlement}/>
      }
    </div>
  );
};

export default CreativeStudioRoot;
