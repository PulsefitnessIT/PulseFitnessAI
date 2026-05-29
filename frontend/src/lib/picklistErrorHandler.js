/**
 * extractPicklistError(err) — surfaces the structured 400 payload
 * shipped by the backend's `validate_picklist_value` helper (Iter 220bs).
 *
 * Returns a normalised object the UI can render, or `null` if the
 * error isn't a picklist-validation rejection. Includes a fuzzy
 * "did you mean?" suggestion based on simple casing + substring
 * matching — no heavy Levenshtein dependency.
 *
 * Backend payload shape (see routes/crm_picklists.py):
 *   {
 *     detail: {
 *       error: "invalid_picklist_value",
 *       key: "lead_source",
 *       field_label: "Lead Source",
 *       received: "Supreme Overlord",
 *       valid_examples: ["Inbound Website", "Referral", "LinkedIn", ...],
 *       hint: "Pick one of the values from /api/crm/picklists/lead_source..."
 *     }
 *   }
 */

function _suggestClosest(received, examples) {
  if (!received || !Array.isArray(examples) || examples.length === 0) {
    return null;
  }
  const needle = String(received).toLowerCase().trim();
  // Exact case-insensitive match — shouldn't happen (backend would
  // have accepted it) but defensive.
  for (const ex of examples) {
    if (ex.toLowerCase() === needle) return ex;
  }
  // Substring match either way — handles "linkdn" → "LinkedIn",
  // "tradeshow" → "Trade Show", etc.
  for (const ex of examples) {
    if (ex.toLowerCase().includes(needle) || needle.includes(ex.toLowerCase())) {
      return ex;
    }
  }
  // Token overlap — count how many words from needle appear in each.
  const needleTokens = needle.split(/\s+/).filter(Boolean);
  let best = null;
  let bestScore = 0;
  for (const ex of examples) {
    const exLower = ex.toLowerCase();
    const score = needleTokens.filter((t) => exLower.includes(t)).length;
    if (score > bestScore) {
      bestScore = score;
      best = ex;
    }
  }
  return bestScore > 0 ? best : null;
}

export function extractPicklistError(err) {
  const detail = err?.response?.data?.detail;
  if (!detail || typeof detail !== 'object') return null;
  if (detail.error !== 'invalid_picklist_value') return null;
  const suggestion = _suggestClosest(detail.received, detail.valid_examples);
  return {
    fieldLabel: detail.field_label || detail.key || 'this field',
    key: detail.key,
    received: detail.received,
    examples: Array.isArray(detail.valid_examples) ? detail.valid_examples : [],
    hint: detail.hint || '',
    suggestion, // string|null — "Did you mean: X?"
  };
}

/**
 * notifyPicklistError(err, notify) — convenience that surfaces a
 * rich toast/banner when the error matches and returns true; otherwise
 * returns false so callers can fall through to their normal error
 * handler.
 *
 * Usage:
 *   import { notify } from '@/components/notifications';
 *   import { notifyPicklistError } from '@/lib/picklistErrorHandler';
 *
 *   try { await axios.post(...) }
 *   catch (e) {
 *     if (notifyPicklistError(e, notify)) return;
 *     notify.error('Save failed', e.message);
 *   }
 */
export function notifyPicklistError(err, notify) {
  const p = extractPicklistError(err);
  if (!p) return false;
  const title = `${p.fieldLabel} value is not allowed`;
  const lines = [`Received: "${p.received}".`];
  if (p.suggestion) lines.push(`Did you mean: "${p.suggestion}"?`);
  else if (p.examples.length) lines.push(`Try one of: ${p.examples.slice(0, 5).join(', ')}.`);
  if (p.hint) lines.push(p.hint);
  notify.error(title, lines.join('\n'));
  return true;
}

export default extractPicklistError;
