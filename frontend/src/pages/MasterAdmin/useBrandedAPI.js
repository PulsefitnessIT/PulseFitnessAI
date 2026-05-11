/**
 * Iter 216h18 — Master Admin branded-API hook.
 *
 * Returns a small `apiUrl(path)` helper that auto-appends the current
 * brand filter (`?brand=pulse` etc.) to any Master Admin endpoint.
 *
 * Usage:
 *   const apiUrl = useBrandedAPI();
 *   const { data } = await axios.get(apiUrl('/master-admin/organizations'),
 *                                    { headers: headers() });
 *
 * The hook also exposes `brand` itself so callers can include it in
 * the React-query / SWR key, ensuring a fresh fetch fires the moment
 * the operator flips the brand picker.
 */
import { useCallback } from 'react';
import { useBrandContext } from './BrandContext';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const useBrandedAPI = () => {
  const { brand } = useBrandContext();

  const apiUrl = useCallback((path, extraParams = null) => {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const sep = cleanPath.includes('?') ? '&' : '?';
    const params = new URLSearchParams(extraParams || {});
    if (brand && brand !== 'all') params.set('brand', brand);
    const qs = params.toString();
    return `${API_BASE}${cleanPath}${qs ? `${sep}${qs}` : ''}`;
  }, [brand]);

  return { apiUrl, brand };
};

export default useBrandedAPI;
