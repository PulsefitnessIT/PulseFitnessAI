import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { MonitorSmartphone, Smartphone, Monitor, LogOut, ShieldCheck, Loader2 } from 'lucide-react';

const relTime = (iso) => {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
};

const DeviceIcon = ({ device }) => {
  const d = (device || '').toLowerCase();
  if (d.includes('iphone') || d.includes('android')) return <Smartphone size={16} className="text-[var(--color-brand-blue)]" />;
  return <Monitor size={16} className="text-[var(--color-brand-blue)]" />;
};

/**
 * Iter 232 — Active sessions / "Sign out everywhere" panel.
 * Lists every device with a live session; lets the user revoke a
 * single device or all other devices at once.
 *
 * `variant`: "dark" (legacy master-admin AccountPanel dialog) or
 * "light" (theme-aware AccountSettingsModal Security section).
 */
export const ActiveSessionsPanel = ({ API, variant = 'dark' }) => {
  const light = variant === 'light';
  const [sessions, setSessions] = useState(null);
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/auth/sessions`);
      setSessions(res.data?.sessions || []);
    } catch {
      setSessions([]);
    }
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const revokeOne = async (id) => {
    setBusy(id);
    try {
      await axios.post(`${API}/auth/sessions/${id}/revoke`);
      toast.success('Device signed out');
      await load();
    } catch {
      toast.error('Could not sign out that device');
    } finally {
      setBusy('');
    }
  };

  const revokeOthers = async () => {
    setBusy('all');
    try {
      const res = await axios.post(`${API}/auth/sessions/revoke-others`);
      const n = res.data?.revoked ?? 0;
      toast.success(n > 0 ? `Signed out ${n} other ${n === 1 ? 'device' : 'devices'}` : 'No other devices were signed in');
      await load();
    } catch {
      toast.error('Could not sign out other devices');
    } finally {
      setBusy('');
    }
  };

  const others = (sessions || []).filter((s) => !s.current).length;
  const mutedStyle = light ? { color: 'var(--theme-text-muted)' } : undefined;
  const mutedCls = light ? '' : 'text-[var(--color-text-muted)]';
  const titleCls = light ? '' : 'text-white';
  const titleStyle = light ? { color: 'var(--theme-text)' } : undefined;
  const rowCls = light
    ? 'flex items-center gap-3 rounded-lg border px-3 py-2.5'
    : 'flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.03] px-3 py-2.5';
  const rowStyle = light ? { borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' } : undefined;

  return (
    <Card
      className={light ? 'p-5 border' : 'bg-[var(--color-ink-alt)] border-white/10 p-5'}
      style={light ? { background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' } : undefined}
      data-testid="active-sessions-panel"
    >
      <div className="flex items-center justify-between mb-3">
        <p className={`text-xs uppercase tracking-wider flex items-center gap-2 ${mutedCls}`} style={mutedStyle}>
          <MonitorSmartphone size={14} /> Active sessions
        </p>
        {others > 0 && (
          <Button
            size="sm"
            variant="outline"
            className="border-red-500/40 text-red-400 hover:bg-red-500/10 hover:text-red-300 text-xs h-7"
            onClick={revokeOthers}
            disabled={busy === 'all'}
            data-testid="sign-out-everywhere-btn"
          >
            {busy === 'all' ? <Loader2 size={12} className="animate-spin mr-1" /> : <LogOut size={12} className="mr-1" />}
            Sign out everywhere else
          </Button>
        )}
      </div>

      {sessions === null && (
        <p className={`text-sm ${mutedCls}`} style={mutedStyle} data-testid="sessions-loading">Loading sessions…</p>
      )}

      {sessions !== null && sessions.length === 0 && (
        <p className={`text-sm ${mutedCls}`} style={mutedStyle} data-testid="sessions-empty">
          No tracked sessions yet — devices appear here the next time they sign in.
        </p>
      )}

      <div className="space-y-2">
        {(sessions || []).map((s) => (
          <div
            key={s.id}
            className={rowCls}
            style={rowStyle}
            data-testid={`session-row-${s.id}`}
          >
            <DeviceIcon device={s.device} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className={`text-sm font-medium truncate ${titleCls}`} style={titleStyle}>{s.device}</p>
                {s.current && (
                  <Badge className="bg-emerald-500/15 text-emerald-400 text-[10px] px-1.5 py-0 flex items-center gap-1" data-testid="session-current-badge">
                    <ShieldCheck size={10} /> This device
                  </Badge>
                )}
              </div>
              <p className={`text-xs truncate ${mutedCls}`} style={mutedStyle}>
                {s.ip ? `${s.ip} · ` : ''}Last active {relTime(s.last_seen_at)}
              </p>
            </div>
            {!s.current && (
              <Button
                size="sm"
                variant="ghost"
                className={`${mutedCls} hover:text-red-400 hover:bg-red-500/10 h-7 px-2 text-xs`}
                style={mutedStyle}
                onClick={() => revokeOne(s.id)}
                disabled={busy === s.id}
                data-testid={`session-revoke-${s.id}`}
              >
                {busy === s.id ? <Loader2 size={12} className="animate-spin" /> : 'Sign out'}
              </Button>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
};

export default ActiveSessionsPanel;
