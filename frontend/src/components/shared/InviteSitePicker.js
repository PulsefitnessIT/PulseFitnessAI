import { useEffect, useState } from 'react';
import axios from 'axios';

// Release C — choose which sites an invited person can access. None ticked = all sites (owners only).
export default function InviteSitePicker({ API, value, onChange, restricted, restrictedTo }) {
  const [sites, setSites] = useState([]);
  useEffect(() => {
    axios.get(`${API}/sites`, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })
      .then((r) => {
        const list = (r.data.sites || []).filter((s) => !restricted || !restrictedTo?.length || restrictedTo.includes(s.id));
        setSites(list);
        if (restricted && list.length === 1 && !value.length) onChange([list[0].id]);
      }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API, restricted]);
  if (sites.length < 2 && !restricted) return null;
  const toggle = (id) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  return (
    <div data-testid="invite-site-picker">
      <p className="text-sm text-[var(--theme-text)]">Sites they can access</p>
      <p className="text-xs text-[var(--color-text-muted)] mb-2">{restricted ? 'Choose at least one of your sites.' : 'Leave all unticked to give access to every site.'}</p>
      <div className="max-h-40 overflow-auto space-y-1">
        {sites.map((s) => (
          <label key={s.id} className="flex items-center gap-2 text-sm text-[var(--theme-text)]">
            <input type="checkbox" checked={value.includes(s.id)} onChange={() => toggle(s.id)} data-testid={`invite-site-${s.id}`} />{s.name}
          </label>
        ))}
      </div>
    </div>
  );
}
