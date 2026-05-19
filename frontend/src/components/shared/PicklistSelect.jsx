/**
 * PicklistSelect — Iter 216h223.
 *
 * Drop-in <select> backed by /api/crm/picklists/{key}. Lazy-loads the
 * values on first focus so we don't burn requests on forms that
 * never open the dropdown. Caches the result in a module-level Map
 * keyed by `picklistKey` so multiple instances on the same page hit
 * the network exactly once.
 *
 * The component falls back to a free-text input if the API call
 * fails — never block the user's form because a picklist couldn't
 * load.
 *
 * Usage:
 *   import PicklistSelect from '@/components/shared/PicklistSelect';
 *   <PicklistSelect
 *     pickKey="job_title"
 *     value={form.job_title}
 *     onChange={v => setForm({...form, job_title: v})}
 *     placeholder="Select a job title"
 *     headers={headers}
 *     api={API}
 *   />
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

const CACHE = new Map(); // pickKey -> values[]
const PENDING = new Map(); // pickKey -> Promise

async function loadValues(api, headers, pickKey) {
  if (CACHE.has(pickKey)) return CACHE.get(pickKey);
  if (PENDING.has(pickKey)) return PENDING.get(pickKey);
  const p = axios
    .get(`${api}/crm/picklists/${pickKey}`, { headers: headers() })
    .then(r => {
      const vals = (r.data?.values || []).filter(v => !v.deprecated);
      CACHE.set(pickKey, vals);
      PENDING.delete(pickKey);
      return vals;
    })
    .catch(() => {
      // Cache an empty array on failure so we don't hammer the API;
      // the form silently falls back to free-text entry.
      CACHE.set(pickKey, null);
      PENDING.delete(pickKey);
      return null;
    });
  PENDING.set(pickKey, p);
  return p;
}

export default function PicklistSelect({
  pickKey,
  value,
  onChange,
  placeholder,
  className,
  style,
  api,
  headers,
  disabled,
  testId,
  allowFreeText = true,
}) {
  const [values, setValues] = useState(null); // null = not-loaded, [] = loaded
  const [loaded, setLoaded] = useState(false);
  const [showFreeText, setShowFreeText] = useState(false);

  const fetchValues = useCallback(async () => {
    if (loaded) return;
    const vals = await loadValues(api, headers, pickKey);
    setValues(vals);
    setLoaded(true);
  }, [api, headers, pickKey, loaded]);

  // Always fetch on mount — keeps the UX consistent (no "select"
  // showing then suddenly becoming a dropdown after focus).
  useEffect(() => { fetchValues(); }, [fetchValues]);

  // When the current value isn't in the loaded list, surface a
  // free-text input so legacy / org-custom values still display.
  const isOther = value === '__other__';
  const valueInList = values?.some(v => v.label === value);

  if (!loaded) {
    // Render a placeholder select while we load.
    return (
      <select disabled className={className} style={style} data-testid={testId}>
        <option>Loading…</option>
      </select>
    );
  }

  // Fallback path — API failed. Render a plain text input.
  if (values === null) {
    return (
      <input
        type="text"
        value={value || ''}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={className}
        style={style}
        data-testid={testId}
      />
    );
  }

  if (showFreeText || isOther || (value && !valueInList && allowFreeText)) {
    return (
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={value === '__other__' ? '' : (value || '')}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          className={className}
          style={style}
          data-testid={testId}
          autoFocus
        />
        <button
          type="button"
          onClick={() => { setShowFreeText(false); onChange(''); }}
          className="text-[10px] opacity-60 hover:opacity-100 underline"
          data-testid={testId ? `${testId}-back` : undefined}
        >
          Pick from list
        </button>
      </div>
    );
  }

  return (
    <select
      value={value || ''}
      onChange={e => {
        const v = e.target.value;
        if (v === '__other__' && allowFreeText) {
          setShowFreeText(true);
          onChange('');
          return;
        }
        onChange(v);
      }}
      disabled={disabled}
      className={className}
      style={style}
      data-testid={testId}
    >
      <option value="">{placeholder || 'Select…'}</option>
      {values.map(v => (
        <option key={v.id} value={v.label}>{v.label}</option>
      ))}
      {allowFreeText && (
        <option value="__other__">Other (type a value)</option>
      )}
    </select>
  );
}
