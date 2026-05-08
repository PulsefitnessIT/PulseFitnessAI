/** Shared axios config helper for authenticated requests.
 *  Usage:  axios.get(url, authConfig())
 *  Keeps call sites clean and avoids repeating Bearer-header wiring. */
export function authConfig(extraHeaders = {}) {
  const token = localStorage.getItem('token');
  return {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...extraHeaders,
    },
  };
}
