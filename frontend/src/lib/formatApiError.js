/**
 * formatApiError(err, fallback) — one place to translate an Axios error
 * into a user-actionable {title, detail} pair. Iter 234.
 *
 * Why: every action-hook in the app used to swallow errors with
 * `notify.error('Failed')`. Users got a red toast and no idea what to
 * do next. This helper:
 *   • Decodes the HTTP status + server `detail` into a friendly title
 *   • Surfaces the *exact* server message in the `detail` line so users
 *     can copy-paste it back to support
 *   • Suggests next steps for the common 401/403/404/409/422/5xx cases
 *   • Survives network failures (no `err.response`)
 *
 * Usage:
 *   try { ... }
 *   catch (err) {
 *     const { title, detail } = formatApiError(err, 'Failed to update tier');
 *     notify.error(title, detail, { duration: 7000 });
 *   }
 */

const NETWORK_FALLBACK = 'Network unreachable — check your connection and retry.';

function _stringify(value) {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(_stringify).join(' · ');
  if (typeof value === 'object') {
    // FastAPI 422 sometimes returns {detail: [{loc, msg, type}, ...]}
    if (value.msg && value.loc) return `${value.loc.slice(-1)[0]}: ${value.msg}`;
    if (value.message) return String(value.message);
    try { return JSON.stringify(value); } catch { return ''; }
  }
  return String(value);
}

export function formatApiError(err, fallback = 'Something went wrong') {
  // Iter 216bh — a real JS bug (e.g. ReferenceError from an undefined
  // variable in a template literal, TypeError from .foo on undefined)
  // would otherwise hit the no-status fallback below and be reported
  // as "Network unreachable" — wildly misleading. Detect and surface
  // the actual error name + message so the operator can paste it
  // straight to support instead of chasing wifi signal.
  if (err instanceof ReferenceError || err instanceof TypeError || err instanceof SyntaxError) {
    const msg = (err && err.message) ? String(err.message) : err.name;
     
    console.error('[formatApiError] caught client-side bug:', err);
    return {
      title: fallback,
      detail: `Unexpected client error — share this with support: ${err.name}: ${msg}`,
      status: null,
    };
  }

  // Network-layer failure (no response received).
  if (err && err.code === 'ERR_NETWORK') {
    return {
      title: fallback,
      detail: NETWORK_FALLBACK,
      status: null,
    };
  }
  if (err && err.code === 'ECONNABORTED') {
    return {
      title: fallback,
      detail: 'Request timed out — the server took too long to respond.',
      status: null,
    };
  }

  const resp = err && err.response;
  const status = resp && resp.status;
  const data = resp && resp.data;
  const serverDetail = _stringify(
    (data && (data.detail || data.message || data.error)) || data,
  );
  const url = err && err.config && err.config.url;
  const ref = `Ref ${new Date().toISOString().slice(0, 19).replace('T', ' ')}`;

  // Status-coded UX strings — short, actionable, and surface the server
  // message verbatim so users can paste it back to support.
  switch (status) {
    case 400:
      return {
        title: fallback,
        detail: serverDetail
          ? `${serverDetail}`
          : 'The request was rejected. Check the form values and try again.',
        status,
      };
    case 401:
      return {
        title: 'Session expired',
        detail: 'Sign out and back in, then retry. Your previous changes were not saved.',
        status,
      };
    case 403:
      return {
        title: 'Permission denied',
        detail: serverDetail || 'You don\'t have access to this action — ask a master admin.',
        status,
      };
    case 404:
      return {
        title: fallback,
        detail: serverDetail
          ? `Not found: ${serverDetail}`
          : 'Resource not found — it may have been deleted by another admin. Refresh and retry.',
        status,
      };
    case 409:
      return {
        title: 'Conflict',
        detail: serverDetail || 'Another change conflicts with this one. Refresh and retry.',
        status,
      };
    case 413:
      return {
        title: fallback,
        detail: 'The upload is too large. Try a smaller file (under 25 MB).',
        status,
      };
    case 422:
      return {
        title: 'Validation error',
        detail: serverDetail || 'One or more fields are invalid.',
        status,
      };
    case 429:
      return {
        title: 'Slow down',
        detail: 'Too many requests in a short window. Wait a moment and retry.',
        status,
      };
    case 500:
    case 502:
    case 503:
    case 504:
      return {
        title: fallback,
        detail: serverDetail
          ? `Server error (${status}): ${serverDetail} · ${ref}`
          : `Server error (${status}). ${ref} — share this reference if it persists.`,
        status,
      };
    default:
      if (status) {
        return {
          title: fallback,
          detail: serverDetail
            ? `(${status}) ${serverDetail}`
            : `Unexpected error (${status}) at ${url || 'the server'}. ${ref}`,
          status,
        };
      }
      // No status, no recognised code — last-resort fallback.
      // Iter 216bh — distinguish "no response" (likely network) from
      // an Error with a message (likely a client bug we didn't catch
      // earlier). Surfacing the message helps support triage.
      if (err && err.message && !err.response && !err.code) {
        return {
          title: fallback,
          detail: `Unexpected error — share with support: ${err.message}`,
          status: null,
        };
      }
      return {
        title: fallback,
        detail: serverDetail || NETWORK_FALLBACK,
        status: null,
      };
  }
}

/**
 * Convenience wrapper for hooks that want a one-liner toast.
 * Returns the formatted error so the caller can also bubble it up.
 */
export function notifyApiError(notify, err, fallback) {
  const formatted = formatApiError(err, fallback);
  notify.error(formatted.title, formatted.detail, { duration: 8000 });
  return formatted;
}

export default formatApiError;
