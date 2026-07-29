/**
 * LocaleLanguageNudge — tiny, dismissible one-time banner.
 *
 * When an operator switches the UI to French or German but their org is still
 * billing in a non-EUR currency, we offer a one-tap switch to the matching
 * market (France / Germany → EUR + DD/MM/YYYY date formatting via the org
 * localization system). Owners / master admins only. Copy is inlined per
 * language because the banner only ever renders in that language.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { Globe, X, Check, Loader2 } from 'lucide-react';
import { invalidateLocalization } from '@/utils/localization';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

// UI language → target org market.
const TARGET = { fr: { code: 'FR' }, de: { code: 'DE' } };

const COPY = {
  fr: {
    text: "Vous utilisez l'application en français. Passer la tarification en € et les dates au format JJ/MM/AAAA (France) ?",
    apply: 'Passer en €',
    dismiss: 'Plus tard',
    done: 'Marché défini sur la France — prix en € et dates en JJ/MM/AAAA.',
    err: "Impossible de mettre à jour le marché.",
  },
  de: {
    text: 'Sie nutzen die App auf Deutsch. Preise auf € und Datum auf TT.MM.JJJJ (Deutschland) umstellen?',
    apply: 'Auf € umstellen',
    dismiss: 'Später',
    done: 'Markt auf Deutschland gesetzt — Preise in € und Datum als TT.MM.JJJJ.',
    err: 'Markt konnte nicht aktualisiert werden.',
  },
};

export default function LocaleLanguageNudge() {
  const { i18n } = useTranslation();
  const lng = (i18n.resolvedLanguage || i18n.language || 'en').slice(0, 2);
  const target = TARGET[lng];
  const dismissKey = `locale_nudge_dismissed_${lng}`;

  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    if (!target) { setShow(false); return; }
    if (localStorage.getItem(dismissKey) === '1') { setShow(false); return; }
    const token = localStorage.getItem('token');
    if (!token) { setShow(false); return; }
    (async () => {
      try {
        const { data } = await axios.get(`${API}/org/localization`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const loc = data?.localization || {};
        // Only nudge editors whose org isn't already on EUR / the target country.
        const eligible = Boolean(data?.can_edit)
          && (loc.currency || '').toUpperCase() !== 'EUR'
          && (loc.country_code || '').toUpperCase() !== target.code;
        if (alive) setShow(eligible);
      } catch {
        if (alive) setShow(false);
      }
    })();
    return () => { alive = false; };
  }, [target, dismissKey]);

  if (!show || !target) return null;
  const copy = COPY[lng];

  const dismiss = () => {
    localStorage.setItem(dismissKey, '1');
    setShow(false);
  };

  const apply = async () => {
    setBusy(true);
    try {
      const token = localStorage.getItem('token');
      await axios.put(`${API}/org/localization`, { country_code: target.code }, {
        headers: { Authorization: `Bearer ${token}` },
      });
      invalidateLocalization();
      localStorage.setItem(dismissKey, '1');
      notify.success(copy.done);
      // Reload so cached money/date formatters pick up the new market everywhere.
      setTimeout(() => window.location.reload(), 900);
    } catch {
      notify.error(copy.err);
      setBusy(false);
    }
  };

  return (
    <div
      className="flex items-center gap-3 px-4 py-2.5 text-sm border-b"
      style={{ background: 'rgba(25,205,255,0.08)', borderColor: 'var(--theme-border, #e2e8f0)', color: 'var(--theme-text, #0f172a)' }}
      data-testid="locale-language-nudge"
    >
      <Globe size={16} className="shrink-0" style={{ color: 'var(--color-brand-cyan, #19CDFF)' }} />
      <span className="flex-1 leading-snug">{copy.text}</span>
      <button
        type="button"
        onClick={apply}
        disabled={busy}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold disabled:opacity-60"
        style={{ background: 'var(--color-brand-cyan, #19CDFF)', color: 'var(--color-ink, #0b1220)' }}
        data-testid="locale-nudge-apply"
      >
        {busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} {copy.apply}
      </button>
      <button
        type="button"
        onClick={dismiss}
        className="inline-flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-semibold opacity-70 hover:opacity-100"
        data-testid="locale-nudge-dismiss"
        aria-label={copy.dismiss}
      >
        <X size={14} />
      </button>
    </div>
  );
}
