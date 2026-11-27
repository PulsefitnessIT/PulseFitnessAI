import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Copy as CopyIcon, Power, LogOut, MapPin } from 'lucide-react';

// Release C — one gym-floor device login per site. Disabling or re-keying signs devices out at once.
export default function GymFloorDevices({ API, headers, creds, onCopy, onChanged }) {
  const act = async (id, what) => {
    await axios.post(`${API}/gym-floor/devices/${encodeURIComponent(id)}/${what}`, {}, { headers });
    onChanged();
  };
  if (!creds.length) {
    return <p className="text-sm mb-3" style={{ color: 'var(--theme-text-muted)' }} data-testid="gym-floor-no-devices">No gym-floor device login yet. Create one below.</p>;
  }
  return (
    <div className="space-y-2 mb-3" data-testid="gym-floor-devices">
      {creds.map((c) => (
        <div key={c.id} className="p-3 rounded-lg flex flex-wrap items-center justify-between gap-2" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }} data-testid={`gym-floor-device-${c.id}`}>
          <div className="min-w-0">
            <p className="text-xs flex items-center gap-1" style={{ color: 'var(--theme-text-muted)' }}>
              <MapPin size={11} /> {c.site_name || (c.org_wide_legacy ? 'All sites (older login — replace with a site login)' : 'Site')}
            </p>
            <p className="text-sm font-mono font-semibold">{c.username}</p>
            <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }} data-testid={`gym-floor-device-state-${c.id}`}>
              {c.enabled === false ? 'Disabled' : `${c.active_sessions || 0} device(s) signed in`}
            </p>
          </div>
          <div className="flex gap-1.5">
            <Button variant="outline" size="sm" onClick={onCopy} className="rounded-full text-xs" data-testid={`gym-floor-copy-${c.id}`}><CopyIcon size={12} className="mr-1" />Login URL</Button>
            {c.enabled !== false && <Button variant="outline" size="sm" onClick={() => act(c.id, 'sign-out')} className="rounded-full text-xs" data-testid={`gym-floor-signout-${c.id}`}><LogOut size={12} className="mr-1" />Sign out devices</Button>}
            <Button variant="outline" size="sm" onClick={() => act(c.id, c.enabled === false ? 'enable' : 'disable')} className="rounded-full text-xs" data-testid={`gym-floor-toggle-${c.id}`}>
              <Power size={12} className="mr-1" />{c.enabled === false ? 'Enable' : 'Disable'}
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
