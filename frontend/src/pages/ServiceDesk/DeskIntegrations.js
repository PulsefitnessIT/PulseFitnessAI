/**
 * Service Desk — Integrations (self-serve Orbit 4 connection).
 *
 * Lets a Service Desk admin connect their OWN Orbit 4 account: paste the API
 * token + webhook secret, copy a unique webhook URL into Orbit 4, and toggle
 * the connection live. Inbound Orbit 4 tickets then land as Service Desk
 * cases automatically — no Pulse Fitness admin involvement required.
 */
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import {
  Plug, Copy, Check, RefreshCw, Loader2, Zap, ListChecks,
  ExternalLink, Users, Rocket,
} from 'lucide-react';
import Orbit4Wizard from './Orbit4Wizard';

const BACKEND = process.env.REACT_APP_BACKEND_URL || '';

export default function DeskIntegrations() {
  const { t } = useTranslation();
  const [conn, setConn] = useState(null);
  const [activity, setActivity] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [copied, setCopied] = useState(false);
  const [apiToken, setApiToken] = useState('');
  const [webhookSecret, setWebhookSecret] = useState('');
  const [webBaseUrl, setWebBaseUrl] = useState('');
  const [engineers, setEngineers] = useState([]);
  const [o4Users, setO4Users] = useState([]);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [autoPrompted, setAutoPrompted] = useState(false);

  const fullWebhookUrl = conn?.webhook_path ? `${BACKEND}${conn.webhook_path}` : (conn?.webhook_url || '');

  const load = async () => {
    setLoading(true);
    try {
      const [c, a, e] = await Promise.all([
        api.get('/svc/orbit4/connection'),
        api.get('/svc/orbit4/connection/activity').catch(() => ({ data: null })),
        api.get('/svc/orbit4/engineers').catch(() => ({ data: null })),
      ]);
      setConn(c.data);
      setActivity(a.data);
      setWebBaseUrl(c.data?.web_base_url || '');
      setEngineers(e.data?.engineers || []);
      setO4Users(e.data?.orbit4_users || []);
      // Auto-launch the onboarding wizard once for a brand-new connection.
      if (!autoPrompted && !c.data?.api_token && !c.data?.enabled) {
        setAutoPrompted(true);
        setWizardOpen(true);
      }
    } catch (e) {
      toast.error(t('service.o4_load_err', 'Could not load the Orbit 4 connection'));
    } finally {
      setLoading(false);
    }
  };

  const mapEngineer = async (engineerId, orbit4UserId) => {
    try {
      await api.put(`/svc/orbit4/engineers/${engineerId}`, { orbit4_user_id: orbit4UserId || null });
      setEngineers((prev) => prev.map((x) => x.id === engineerId
        ? { ...x, orbit4_user_id: orbit4UserId ? Number(orbit4UserId) : null } : x));
      toast.success(t('service.o4_mapping_updated', 'Engineer mapping updated'));
    } catch {
      toast.error(t('service.o4_mapping_err', 'Could not update mapping'));
    }
  };

  useEffect(() => { load(); }, []);

  const save = async (patch) => {
    setSaving(true);
    try {
      const r = await api.put('/svc/orbit4/connection', patch);
      setConn(r.data);
      return r.data;
    } catch (e) {
      toast.error(t('service.o4_save_failed', 'Save failed'));
      throw e;
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (next) => {
    if (next && !conn?.api_token && !apiToken) {
      // allow enabling for inbound-only, but warn outbound needs a token
    }
    await save({ enabled: next });
    toast.success(next ? t('service.o4_now_live', 'Orbit 4 connection is live') : t('service.o4_now_paused', 'Orbit 4 connection paused'));
  };

  const handleSaveCreds = async () => {
    const patch = { web_base_url: webBaseUrl };
    if (apiToken) patch.api_token = apiToken;
    if (webhookSecret) patch.webhook_secret = webhookSecret;
    await save(patch);
    setApiToken('');
    setWebhookSecret('');
    toast.success(t('service.o4_settings_saved', 'Settings saved'));
  };

  const handleRotate = async () => {
    setSaving(true);
    try {
      const r = await api.post('/svc/orbit4/connection/rotate-key');
      setConn(r.data);
      toast.success(t('service.o4_url_regenerated', 'Webhook URL regenerated — update it in Orbit 4'));
    } catch {
      toast.error(t('service.o4_rotate_err', 'Could not rotate the key'));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const r = await api.post('/svc/orbit4/connection/test');
      if (r.data.ok) toast.success(r.data.message || t('service.o4_connected', 'Connected'));
      else toast.error(r.data.message || t('service.o4_could_not_connect', 'Could not connect'));
    } catch {
      toast.error(t('service.o4_test_failed', 'Test failed'));
    } finally {
      setTesting(false);
    }
  };

  const copyUrl = () => {
    navigator.clipboard.writeText(fullWebhookUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
    toast.success(t('service.o4_url_copied', 'Webhook URL copied'));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500 text-sm" data-testid="desk-integrations-loading">
        <Loader2 size={16} className="mr-2 animate-spin" /> {t('service.o4_loading', 'Loading…')}
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl" data-testid="desk-integrations">
      <Orbit4Wizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        conn={conn}
        onConnUpdate={(c) => setConn(c)}
        onFinished={load}
      />
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Plug size={22} className="text-indigo-600" /> {t('service.o4_title', 'Integrations')}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {t('service.o4_subtitle', 'Connect Orbit 4 so faults logged by your customers flow straight into your Service Desk.')}
          </p>
        </div>
        <Button onClick={() => setWizardOpen(true)} data-testid="orbit4-launch-wizard-btn">
          <Rocket size={15} className="mr-2" /> {t('service.o4_setup_wizard', 'Setup wizard')}
        </Button>
      </div>

      {/* Connection status card */}
      <Card data-testid="orbit4-connection-card">
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base flex items-center gap-2">
            Orbit 4
            {conn?.enabled
              ? <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100" data-testid="orbit4-status-live">{t('service.o4_live', 'Live')}</Badge>
              : <Badge variant="secondary" data-testid="orbit4-status-paused">{t('service.o4_paused', 'Paused')}</Badge>}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Label htmlFor="orbit4-enabled" className="text-sm text-slate-600">{t('service.o4_enabled', 'Enabled')}</Label>
            <Switch
              id="orbit4-enabled"
              checked={!!conn?.enabled}
              onCheckedChange={handleToggle}
              disabled={saving}
              data-testid="orbit4-enable-toggle"
            />
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Webhook URL */}
          <div>
            <Label className="text-sm font-medium text-slate-700">{t('service.o4_step1', '1. Your unique webhook URL')}</Label>
            <p className="text-xs text-slate-500 mb-2">
              {t('service.o4_step1_hint', 'Paste this into Orbit 4 → Settings → Webhooks. Orbit 4 will POST ticket, note, photo and asset events here.')}
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs bg-slate-50 border border-slate-200 rounded px-3 py-2 break-all" data-testid="orbit4-webhook-url">
                {fullWebhookUrl}
              </code>
              <Button variant="outline" size="sm" onClick={copyUrl} data-testid="orbit4-copy-url-btn">
                {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
              </Button>
              <Button variant="ghost" size="sm" onClick={handleRotate} disabled={saving} title={t('service.o4_regen_url', 'Regenerate URL')} data-testid="orbit4-rotate-key-btn">
                <RefreshCw size={14} />
              </Button>
            </div>
          </div>

          {/* Credentials */}
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="orbit4-secret" className="text-sm font-medium text-slate-700">{t('service.o4_step2', '2. Webhook secret')}</Label>
              <p className="text-xs text-slate-500 mb-2">{t('service.o4_step2_hint', 'Optional. If set, we verify the signature on every webhook.')}</p>
              <Input
                id="orbit4-secret"
                type="password"
                placeholder={conn?.webhook_secret ? t('service.o4_set', '•••••• (set)') : t('service.o4_paste_secret', 'Paste secret')}
                value={webhookSecret}
                onChange={(e) => setWebhookSecret(e.target.value)}
                data-testid="orbit4-webhook-secret-input"
              />
            </div>
            <div>
              <Label htmlFor="orbit4-token" className="text-sm font-medium text-slate-700">{t('service.o4_step3', '3. API token')}</Label>
              <p className="text-xs text-slate-500 mb-2">{t('service.o4_step3_hint', 'Lets us push case progress (status, notes, photos) back to Orbit 4.')}</p>
              <Input
                id="orbit4-token"
                type="password"
                placeholder={conn?.api_token ? t('service.o4_set', '•••••• (set)') : t('service.o4_paste_token', 'Paste API token')}
                value={apiToken}
                onChange={(e) => setApiToken(e.target.value)}
                data-testid="orbit4-api-token-input"
              />
            </div>
          </div>

          <div>
            <Label htmlFor="orbit4-web-url" className="text-sm font-medium text-slate-700">{t('service.o4_step4', '4. Orbit 4 ticket URL (optional)')}</Label>
            <p className="text-xs text-slate-500 mb-2">{t('service.o4_step4_hint', 'Base URL for "View in Orbit 4" links on cases, e.g. https://app.orbit4.org/tickets — we append the ticket id.')}</p>
            <Input
              id="orbit4-web-url"
              placeholder="https://app.orbit4.org/tickets"
              value={webBaseUrl}
              onChange={(e) => setWebBaseUrl(e.target.value)}
              data-testid="orbit4-web-url-input"
            />
          </div>

          <div className="flex items-center gap-2">
            <Button onClick={handleSaveCreds} disabled={saving} data-testid="orbit4-save-creds-btn">
              {saving ? <Loader2 size={14} className="mr-2 animate-spin" /> : null}
              {t('service.o4_save_settings', 'Save settings')}
            </Button>
            <Button variant="outline" onClick={handleTest} disabled={testing} data-testid="orbit4-test-btn">
              {testing ? <Loader2 size={14} className="mr-2 animate-spin" /> : <Zap size={14} className="mr-2" />}
              {t('service.o4_test_connection', 'Test connection')}
            </Button>
          </div>

          <div className="text-xs text-slate-400 flex items-center gap-1">
            <ExternalLink size={12} />
            {t('service.o4_last_event', 'Last event:')} {conn?.last_event_at ? new Date(conn.last_event_at).toLocaleString() : t('service.o4_none_yet', 'none yet')} · {t('service.o4_total', '{{n}} total', { n: conn?.stats?.events_total || 0 })}
          </div>
        </CardContent>
      </Card>

      {/* Connection health strip */}
      <Card data-testid="orbit4-health-strip">
        <CardContent className="py-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="rounded-lg bg-slate-50 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-slate-400">{t('service.o4_status', 'Status')}</div>
              <div className={`text-sm font-semibold ${activity?.enabled ? 'text-emerald-600' : 'text-slate-500'}`} data-testid="health-status">
                {activity?.enabled ? t('service.o4_live', 'Live') : t('service.o4_paused', 'Paused')}
              </div>
            </div>
            <div className="rounded-lg bg-slate-50 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-slate-400">{t('service.o4_last_inbound', 'Last inbound')}</div>
              <div className="text-sm font-semibold text-slate-700" data-testid="health-last-inbound">
                {activity?.last_inbound_at ? new Date(activity.last_inbound_at).toLocaleString() : '—'}
              </div>
            </div>
            <div className="rounded-lg bg-slate-50 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-slate-400">{t('service.o4_last_sync_out', 'Last sync out')}</div>
              <div className={`text-sm font-semibold ${activity?.last_outbound?.status === 'error' ? 'text-red-600' : 'text-slate-700'}`} data-testid="health-last-outbound">
                {activity?.last_outbound?.at
                  ? `${activity.last_outbound.status === 'error' ? '⚠ ' : '✓ '}${new Date(activity.last_outbound.at).toLocaleString()}`
                  : '—'}
              </div>
            </div>
            <div className="rounded-lg bg-slate-50 px-3 py-2">
              <div className="text-[11px] uppercase tracking-wide text-slate-400">{t('service.o4_cases_week', 'Cases this week')}</div>
              <div className="text-sm font-semibold text-slate-700" data-testid="health-cases-week">
                {activity?.cases_this_week ?? 0}
                {activity?.error_count > 0 && (
                  <span className="text-red-600 text-xs ml-2" data-testid="health-errors">{t('service.o4_sync_errors', '{{n}} sync error(s)', { n: activity.error_count })}</span>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Activity */}
      <Card data-testid="orbit4-activity-card">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <ListChecks size={18} className="text-slate-500" /> {t('service.o4_cases_from', 'Cases from Orbit 4')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-6 mb-4">
            <div>
              <div className="text-2xl font-bold text-slate-900" data-testid="orbit4-cases-total">{activity?.cases_total ?? 0}</div>
              <div className="text-xs text-slate-500">{t('service.o4_total_cases_created', 'Total cases created')}</div>
            </div>
          </div>
          {activity?.recent_cases?.length ? (
            <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden">
              {activity.recent_cases.map((c) => (
                <div key={c.id} className="flex items-center justify-between px-3 py-2 text-sm" data-testid={`orbit4-recent-case-${c.id}`}>
                  <div className="min-w-0">
                    <span className="font-medium text-slate-800">{c.reference}</span>
                    <span className="text-slate-500 ml-2 truncate">{c.title}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant="outline" className="uppercase text-[10px]">{c.priority}</Badge>
                    <Badge variant="secondary" className="text-[10px]">{c.status}</Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">{t('service.o4_no_cases', 'No Orbit 4 cases yet. Once connected, new faults appear here.')}</p>
          )}
        </CardContent>
      </Card>

      {/* Engineer ↔ Orbit 4 user mapping */}
      <Card data-testid="orbit4-engineer-mapping-card">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Users size={18} className="text-slate-500" /> {t('service.o4_engineer_mapping', 'Engineer mapping')}
          </CardTitle>
          <p className="text-xs text-slate-500">
            {t('service.o4_engineer_mapping_hint', 'Link your engineers to their Orbit 4 user so notes posted back to Orbit 4 are attributed correctly. Auto-matched by email when possible.')}
          </p>
        </CardHeader>
        <CardContent>
          {engineers.length === 0 ? (
            <p className="text-sm text-slate-400">{t('service.o4_no_engineers', 'No engineers in this Service Desk yet.')}</p>
          ) : (
            <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden">
              {engineers.map((eng) => (
                <div key={eng.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm" data-testid={`orbit4-engineer-row-${eng.id}`}>
                  <div className="min-w-0">
                    <span className="font-medium text-slate-800">{eng.full_name || eng.name || eng.email}</span>
                    <span className="text-slate-400 ml-2 text-xs truncate">{eng.email}</span>
                  </div>
                  <select
                    className="text-sm border border-slate-200 rounded px-2 py-1 bg-white max-w-[220px]"
                    value={eng.orbit4_user_id || ''}
                    onChange={(e) => mapEngineer(eng.id, e.target.value)}
                    data-testid={`orbit4-engineer-select-${eng.id}`}
                  >
                    <option value="">{t('service.o4_not_linked', 'Not linked')}</option>
                    {o4Users.map((u) => (
                      <option key={u.orbit4_user_id} value={u.orbit4_user_id}>
                        {`${u.first_name || ''} ${u.last_name || ''}`.trim() || u.email || t('service.o4_user_n', 'User {{n}}', { n: u.orbit4_user_id })}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          )}
          {o4Users.length === 0 && engineers.length > 0 && (
            <p className="text-xs text-slate-400 mt-3">
              {t('service.o4_no_users_synced', 'No Orbit 4 users synced yet — they appear automatically once Orbit 4 sends user events. Mapping then auto-matches by email.')}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
