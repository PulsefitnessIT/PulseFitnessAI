import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Label } from '@/components/ui/label';

/**
 * Grouped searchable dropdown for selecting a fault code.
 * Codes are fetched once per mount from GET /fault-codes and cached in module state.
 */
let _cachedCategories = null;

const FaultCodeSelect = ({ value, onChange, API, disabled = false, showLabel = true }) => {
  const [categories, setCategories] = useState(_cachedCategories || []);
  const [loading, setLoading] = useState(!_cachedCategories);

  useEffect(() => {
    if (_cachedCategories) return;
    const token = localStorage.getItem('token');
    axios.get(`${API}/fault-codes`, { headers: { Authorization: `Bearer ${token}` } })
      .then(res => {
        _cachedCategories = res.data.categories || [];
        setCategories(_cachedCategories);
      })
      .catch(() => setCategories([]))
      .finally(() => setLoading(false));
  }, [API]);

  return (
    <div data-testid="fault-code-select-wrapper">
      {showLabel && (
        <Label className="text-xs font-medium mb-1 block" style={{ color: 'var(--theme-text-muted)' }}>
          Fault Code (for trend reporting)
        </Label>
      )}
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value || null)}
        disabled={disabled || loading}
        className="w-full rounded-md border px-3 py-2 text-sm"
        style={{
          background: 'var(--theme-surface)',
          color: 'var(--theme-text)',
          borderColor: 'var(--theme-border)',
        }}
        data-testid="fault-code-select"
      >
        <option value="">— Select a fault code (optional) —</option>
        {categories.map(cat => (
          <optgroup key={cat.category} label={cat.label}>
            {cat.codes.map(([code, label]) => (
              <option key={code} value={code}>{`${code} · ${label}`}</option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
};

export default FaultCodeSelect;
