/**
 * queuedMutation — tiny axios/fetch wrapper (iter 215da).
 *
 * Attempts the network request. If the user is offline OR the network
 * throws at the transport layer (fetch TypeError, axios ERR_NETWORK),
 * the mutation is enqueued to the offline queue and the caller gets a
 * sentinel `{ queued: true, entry }` back so it can toast "saved
 * locally, will sync when online" and optimistically update its UI.
 *
 * Successful responses are returned as-is so existing callers see the
 * same shape they do today.
 */
import axios from 'axios';
import { enqueueMutation } from './offlineQueue';

function isNetworkError(err) {
  if (!err) return false;
  // axios
  if (err.code === 'ERR_NETWORK' || err.code === 'ECONNABORTED') return true;
  if (err.message === 'Network Error') return true;
  // fetch
  if (err instanceof TypeError && /fetch|network/i.test(err.message)) return true;
  return false;
}

export async function queuedMutation({ method = 'POST', url, body = null, headers = {}, label, kind }) {
  const isOffline = typeof navigator !== 'undefined' && navigator.onLine === false;

  if (isOffline) {
    const entry = await enqueueMutation({ method, url, body, headers, label, kind });
    return { queued: true, entry };
  }

  try {
    const res = await axios.request({
      method,
      url,
      data: body,
      headers,
    });
    return res.data;
  } catch (err) {
    if (isNetworkError(err)) {
      const entry = await enqueueMutation({ method, url, body, headers, label, kind });
      return { queued: true, entry };
    }
    throw err;
  }
}
