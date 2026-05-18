/**
 * DigestPreferencesCard — sits in AccountPanel. Lets owners/managers control:
 *   - master enable toggle
 *   - frequency (off / daily / weekly / monthly)
 *   - day of week (for weekly)
 *   - hour of day (UTC)
 *   - per-channel checkboxes (warranty / PPM / supplier drift)
 * + "Send me a test" button.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Mail, Bell, MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const DAYS = [
  { v: 0, label: 'Monday' }, { v: 1, label: 'Tuesday' }, { v: 2, label: 'Wednesday' },
  { v: 3, label: 'Thursday' }, { v: 4, label: 'Friday' }, { v: 5, label: 'Saturday' }, { v: 6, label: 'Sunday' },
];

const CHANNELS = [
  { key: 'warranty_expiring', label: 'Warranty expiring', desc: 'Equipment with warranty inside 30 days' },
  { key: 'ppm_overdue', label: 'Planned maintenance overdue', desc: 'Any scheduled PPM task past due' },
  { key: 'supplier_sla_drift', label: 'Supplier performance drift', desc: 'Suppliers trending below 3.0 / 5' },
];

export default function DigestPreferencesCard() {
  const [prefs, setPrefs] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [teamsUrlInput, setTeamsUrlInput] = useState('');
  const [testingTeams, setTestingTeams] = useState(false);

  const headers = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('token')}`,
  }), []);

  useEffect(() => {
    axios.get(`${API}/digest/preferences`, { headers: headers() })
      .then((res) => {
        setPrefs(res.data);
        setTeamsUrlInput(res.data?.teams_webhook_url || '');
      })
      .catch(() => setPrefs(null));
  }, [headers]);

  if (!prefs) return null;

  const save = async (next) => {
    setBusy(true);
    try {
      const res = await axios.put(`${API}/digest/preferences`, next, { headers: headers() });
      setPrefs(res.data);
      notify.success('Digest preferences saved');
    } catch (e) {
      notifyApiError(notify, e, 'Failed to save');
    }
    setBusy(false);
  };

  const sendTest = async () => {
    setSending(true);
    try {
      const res = await axios.post(`${API}/digest/send-now`, null, { headers: headers() });
      if (res.data?.sent) {
        const channels = [res.data.email && 'email', res.data.teams && 'Teams'].filter(Boolean).join(' + ');
        notify.success(`Test digest sent via ${channels}`);
      } else {
        notify.info('No open nudges to include — nothing was sent');
      }
    } catch (e) {
      notifyApiError(notify, e, 'Failed to send test');
    }
    setSending(false);
  };

  const saveTeamsUrl = async () => {
    try {
      const res = await axios.put(
        `${API}/digest/preferences`,
        { teams_webhook_url: teamsUrlInput.trim() },
        { headers: headers() },
      );
      setPrefs(res.data);
      notify.success(teamsUrlInput.trim() ? 'Teams webhook saved' : 'Teams webhook cleared');
    } catch (e) {
      notifyApiError(notify, e, 'Invalid Teams webhook URL');
    }
  };

  const testTeams = async () => {
    setTestingTeams(true);
    try {
      const res = await axios.post(`${API}/digest/test-teams`, null, { headers: headers() });
      if (res.data?.delivered) {
        notify.success('Test card delivered to Teams — check the channel!');
      } else {
        notify.error('Teams rejected the card. Check the webhook URL is still active.');
      }
    } catch (e) {
      notifyApiError(notify, e, 'Test failed');
    }
    setTestingTeams(false);
  };

  const toggleChannel = (key) => {
    save({ channels: { ...prefs.channels, [key]: !prefs.channels[key] } });
  };

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-5" data-testid="digest-card">
      <div className="flex items-start gap-3 mb-4">
        <Mail className="text-sky-400 flex-shrink-0 mt-0.5" size={20} />
        <div className="flex-1">
          <h3 className="text-base font-semibold text-white">Digest email</h3>
          <p className="text-xs text-white/60">
            Roll up open proactive nudges into a tidy inbox-ready summary. Off by default.
          </p>
        </div>
        <Switch
          checked={!!prefs.enabled}
          onCheckedChange={(v) => save({ enabled: v })}
          disabled={busy}
          data-testid="digest-enabled-switch"
        />
      </div>

      {prefs.enabled && (
        <div className="space-y-5 mt-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-white/50 mb-1 block">Frequency</label>
              <Select
                value={prefs.frequency}
                onValueChange={(v) => save({ frequency: v })}
                disabled={busy}
              >
                <SelectTrigger className="bg-black/30 border-white/10" data-testid="digest-frequency">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                  <SelectItem value="monthly">Monthly (1st of each)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {prefs.frequency === 'weekly' && (
              <div>
                <label className="text-xs text-white/50 mb-1 block">Day of week</label>
                <Select
                  value={String(prefs.day_of_week)}
                  onValueChange={(v) => save({ day_of_week: parseInt(v, 10) })}
                  disabled={busy}
                >
                  <SelectTrigger className="bg-black/30 border-white/10" data-testid="digest-day">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DAYS.map((d) => (
                      <SelectItem key={d.v} value={String(d.v)}>{d.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div>
              <label className="text-xs text-white/50 mb-1 block">Hour (UTC)</label>
              <Select
                value={String(prefs.hour_of_day)}
                onValueChange={(v) => save({ hour_of_day: parseInt(v, 10) })}
                disabled={busy}
              >
                <SelectTrigger className="bg-black/30 border-white/10" data-testid="digest-hour">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Array.from({ length: 24 }, (_, i) => (
                    <SelectItem key={i} value={String(i)}>{String(i).padStart(2, '0')}:00</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-2 text-xs text-white/50">
              <Bell size={12} /> Include these alert types
            </div>
            <div className="space-y-2">
              {CHANNELS.map((ch) => (
                <label
                  key={ch.key}
                  className="flex items-start gap-3 rounded p-2 hover:bg-white/5 cursor-pointer"
                  data-testid={`digest-channel-${ch.key}`}
                >
                  <Checkbox
                    checked={!!prefs.channels?.[ch.key]}
                    onCheckedChange={() => toggleChannel(ch.key)}
                    disabled={busy}
                    className="mt-0.5"
                  />
                  <div className="flex-1 text-sm">
                    <div className="text-white">{ch.label}</div>
                    <div className="text-xs text-white/50">{ch.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="space-y-3 border-t border-white/5 pt-4">
            <div className="flex items-center gap-2 text-xs text-white/50">
              <Mail size={12} /> Email delivery
            </div>
            <div className="flex items-center justify-between pl-1">
              <span className="text-sm text-white/80">Send to {prefs.email_override || 'my email'}</span>
              <Switch
                checked={prefs.email_enabled !== false}
                onCheckedChange={(v) => save({ email_enabled: v })}
                disabled={busy}
                data-testid="digest-email-switch"
              />
            </div>
          </div>

          <div className="space-y-3 border-t border-white/5 pt-4">
            <div className="flex items-center gap-2 text-xs text-white/50">
              <MessageSquare size={12} /> Microsoft Teams delivery
            </div>
            <div className="flex items-center justify-between pl-1">
              <span className="text-sm text-white/80">Post to Teams channel</span>
              <Switch
                checked={!!prefs.teams_enabled}
                onCheckedChange={(v) => save({ teams_enabled: v })}
                disabled={busy || !prefs.teams_webhook_url}
                data-testid="digest-teams-switch"
              />
            </div>
            <div className="space-y-2 pl-1">
              <label className="text-xs text-white/50 block">
                Teams incoming-webhook URL
                <span className="block text-[11px] text-white/40 mt-0.5">
                  Teams → channel → ⋯ → Workflows → "Post to a channel when a webhook request is received".
                  Copy the generated URL.
                </span>
              </label>
              <div className="flex gap-2">
                <Input
                  type="url"
                  placeholder="https://prod-XX.westeurope.logic.azure.com/workflows/..."
                  value={teamsUrlInput}
                  onChange={(e) => setTeamsUrlInput(e.target.value)}
                  className="bg-black/30 border-white/10 text-xs"
                  data-testid="digest-teams-url-input"
                />
                <Button
                  size="sm"
                  onClick={saveTeamsUrl}
                  data-testid="digest-teams-save-btn"
                >
                  Save
                </Button>
              </div>
              {prefs.teams_webhook_url && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={testTeams}
                  disabled={testingTeams}
                  data-testid="digest-teams-test-btn"
                >
                  {testingTeams ? 'Sending…' : 'Send test card to Teams'}
                </Button>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-white/5">
            <div className="text-xs text-white/50">
              {prefs.last_sent_at ? (
                <>Last sent: {new Date(prefs.last_sent_at).toLocaleString()}</>
              ) : 'Never sent yet'}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={sendTest}
              disabled={sending}
              data-testid="digest-send-test-btn"
            >
              {sending ? 'Sending…' : 'Send me a test'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
