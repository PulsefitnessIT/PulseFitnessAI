/**
 * Currency-aware icon. Renders the lucide glyph that matches the org's
 * resolved currency (£ / $ / €) instead of a hardcoded dollar sign.
 * Self-resolves from the shared localization cache, so it can be dropped
 * into icon config arrays without threading `loc` through every call site.
 * Pair the host page with a `useLocalization()` call so the cache warms
 * and the subtree re-renders once the real market loads.
 */
import { PoundSterling, DollarSign, Euro, Banknote } from 'lucide-react';
import { getCachedLocalization } from '../../utils/localization';

const ICON_BY_CURRENCY = {
  GBP: PoundSterling,
  USD: DollarSign,
  EUR: Euro,
  CAD: DollarSign,
  AUD: DollarSign,
};

export function currencyIconFor(currency) {
  return ICON_BY_CURRENCY[(currency || '').toUpperCase()] || Banknote;
}

export default function CurrencyIcon(props) {
  const cur = (getCachedLocalization().currency || 'GBP').toUpperCase();
  const Icon = ICON_BY_CURRENCY[cur] || Banknote;
  return <Icon {...props} />;
}
