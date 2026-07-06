/**
 * Orbit 4 onboarding wizard — one screen, four guided steps for a new
 * service provider:
 *   1. Paste API token (+ optional ticket URL)  →  auto-test
 *   2. Generate / copy the webhook secret + unique URL, paste into Orbit 4
 *   3. Go live + wait for the first ticket to arrive (polled)
 *   4. Done — jump to the first case
 * Uses the existing /svc/orbit4 endpoints; no new backend required.
 */
import { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Check, Copy, Loader2, Zap, KeyRound, Webhook, Rocket, PartyPopper,
  ArrowRight, RefreshCw, AlertTriangle,
} from 'lucide-react';

const BACKEND = process.env.REACT_APP_BACKEND_URL || '';
const STEPS = ['Connect', 'Webhook', 'Go live', 'Done'];

function randomSecret() {
  const a = new Uint8Array(24);
  (window.crypto || {}).getRandomValues?.(a);
  return btoa(String.fromCharCode(...a)).replace(/[^a-zA-Z0-9]/g, '').slice(0, 28);
}

function CopyField({ value, testid }) {
  const [done, setDone] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <code className="flex-1 text-xs bg-slate-50 border border-slate-200 rounded px-3 py-2 break-all" data-testid={testid}>{value}</code>
      <Button variant="outline" size="sm" onClick={() => { navigator.clipboard.writeText(value); setDone(true); setTimeout(() => setDone(false), 1600); toast.success('Copied'); }} data-testid={`${testid}-copy`}>
        {done ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
      </Button>
    </div>
  );
}

export default function Orbit4Wizard({ open, onClose, conn, onConnUpdate, onFinished }) {
  const [step, setStep] = useState(0);
  const [apiToken, setApiToken] = useState('');
  const [webUrl, setWebUrl] = useState(conn?.web_base_url || '');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [casesTotal, setCasesTotal] = useState(0);
  const [firstCase, setFirstCase] = useState(null);
  const pollRef = useRef(null);

  const webhookUrl = conn?.webhook_path ? `${BACKEND}${conn.webhook_path}` : (conn?.webhook_url || '');

  useEffect(() => {
    if (open) {
      setStep(0); setApiToken(''); setSecret(''); setTestResult(null);
      setWebUrl(conn?.web_base_url || '');
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [open]); // eslint-disable-line

  // Poll for the first ticket while on the "Go live" step.
  useEffect(() => {
    if (step !== 2) { if (pollRef.current) clearInterval(pollRef.current); return; }
    const tick = async () => {
      try {
        const r = await api.get('/svc/orbit4/connection/activity');
        setCasesTotal(r.data?.cases_total || 0);
        if ((r.data?.cases_total || 0) > 0) {
          setFirstCase(r.data.recent_cases?.[0] || null);
          clearInterval(pollRef.current);
          setStep(3);
          toast.success('First Orbit 4 ticket received!');
        }
      } catch { /* keep polling */ }
    };
    tick();
    pollRef.current = setInterval(tick, 4000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [step]);

  const saveAndTest = async () => {
    setBusy(true);
    try {
      const patch = { web_base_url: webUrl };
      if (apiToken) patch.api_token = apiToken;
      const r = await api.put('/svc/orbit4/connection', patch);
      onConnUpdate?.(r.data);
      const t = await api.post('/svc/orbit4/connection/test');
      setTestResult(t.data);
      setStep(1);
    } catch {
      toast.error('Could not save the connection');
    } finally {
      setBusy(false);
    }
  };

  const generateSecret = async () => {
    const s = randomSecret();
    setBusy(true);
    try {
      const r = await api.put('/svc/orbit4/connection', { webhook_secret: s });
      onConnUpdate?.(r.data);
      setSecret(s);
      toast.success('Secret generated — copy it into Orbit 4');
    } catch {
      toast.error('Could not save the secret');
    } finally {
      setBusy(false);
    }
  };

  const goLive = async () => {
    setBusy(true);
    try {
      const r = await api.put('/svc/orbit4/connection', { enabled: true });
      onConnUpdate?.(r.data);
      setStep(2);
      toast.success('Connection is live — waiting for your first ticket');
    } catch {
      toast.error('Could not enable the connection');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose?.(); }}>
      <DialogContent className="max-w-xl" data-testid="orbit4-wizard">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Rocket size={18} className="text-indigo-600" /> Connect Orbit 4
          </DialogTitle>
          <DialogDescription>
            Link your Orbit 4 account so customer faults flow into your Service Desk.
          </DialogDescription>
        </DialogHeader>

        {/* Stepper */}
        <div className="flex items-center gap-2 mb-2" data-testid="orbit4-wizard-steps">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2 flex-1">
              <div className={`h-7 w-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${i < step ? 'bg-emerald-500 text-white' : i === step ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-500'}`}>
                {i < step ? <Check size={14} /> : i + 1}
              </div>
              <span className={`text-xs ${i === step ? 'text-slate-900 font-semibold' : 'text-slate-400'}`}>{s}</span>
              {i < STEPS.length - 1 && <div className="h-px flex-1 bg-slate-200" />}
            </div>
          ))}
        </div>

        {/* Step 0 — Connect */}
        {step === 0 && (
          <div className="space-y-4" data-testid="orbit4-wizard-step-connect">
            <p className="text-sm text-slate-600">Paste your Orbit 4 API token. This lets us push case progress back to Orbit 4 and verify the connection.</p>
            <div>
              <Label htmlFor="wiz-token" className="text-sm font-medium flex items-center gap-1"><KeyRound size={14} /> Orbit 4 API token</Label>
              <Input id="wiz-token" type="password" placeholder={conn?.api_token ? '•••••• (already set)' : 'Paste API token'} value={apiToken} onChange={(e) => setApiToken(e.target.value)} className="mt-1" data-testid="orbit4-wizard-token-input" />
            </div>
            <div>
              <Label htmlFor="wiz-url" className="text-sm font-medium">Orbit 4 ticket URL (optional)</Label>
              <Input id="wiz-url" placeholder="https://app.orbit4.org/tickets" value={webUrl} onChange={(e) => setWebUrl(e.target.value)} className="mt-1" data-testid="orbit4-wizard-weburl-input" />
              <p className="text-xs text-slate-400 mt-1">Used for "View in Orbit 4" links on cases.</p>
            </div>
            <div className="flex justify-end">
              <Button onClick={saveAndTest} disabled={busy} data-testid="orbit4-wizard-connect-btn">
                {busy ? <Loader2 size={14} className="mr-2 animate-spin" /> : <Zap size={14} className="mr-2" />}
                Save & test
              </Button>
            </div>
          </div>
        )}

        {/* Step 1 — Webhook */}
        {step === 1 && (
          <div className="space-y-4" data-testid="orbit4-wizard-step-webhook">
            {testResult && (
              <div className={`text-sm rounded-lg px-3 py-2 flex items-center gap-2 ${testResult.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`} data-testid="orbit4-wizard-test-result">
                {testResult.ok ? <Check size={15} /> : <AlertTriangle size={15} />}
                {testResult.ok ? 'Connected to Orbit 4.' : (testResult.message || 'Could not verify outbound — you can still receive tickets.')}
              </div>
            )}
            <p className="text-sm text-slate-600 flex items-center gap-1"><Webhook size={14} /> In Orbit 4 → Settings → Webhooks, add this endpoint:</p>
            <div>
              <Label className="text-xs text-slate-500">Webhook URL</Label>
              <CopyField value={webhookUrl} testid="orbit4-wizard-webhook-url" />
            </div>
            <div>
              <Label className="text-xs text-slate-500">Webhook secret</Label>
              {secret ? (
                <CopyField value={secret} testid="orbit4-wizard-secret" />
              ) : (
                <Button variant="outline" size="sm" onClick={generateSecret} disabled={busy} className="mt-1" data-testid="orbit4-wizard-gen-secret-btn">
                  {busy ? <Loader2 size={14} className="mr-2 animate-spin" /> : <RefreshCw size={14} className="mr-2" />}
                  Generate a secret to paste into Orbit 4
                </Button>
              )}
            </div>
            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep(0)}>Back</Button>
              <Button onClick={goLive} disabled={busy} data-testid="orbit4-wizard-golive-btn">
                {busy ? <Loader2 size={14} className="mr-2 animate-spin" /> : null}
                I've added it — go live <ArrowRight size={14} className="ml-2" />
              </Button>
            </div>
          </div>
        )}

        {/* Step 2 — Waiting for first ticket */}
        {step === 2 && (
          <div className="space-y-4 text-center py-4" data-testid="orbit4-wizard-step-waiting">
            <Loader2 size={32} className="animate-spin text-indigo-600 mx-auto" />
            <p className="text-sm font-medium text-slate-800">Connection is live — waiting for your first ticket…</p>
            <p className="text-sm text-slate-500">Log a test fault in Orbit 4 for one of your customers. It'll appear here as a Service Desk case within seconds.</p>
            <p className="text-xs text-slate-400">Cases received so far: {casesTotal}</p>
            <Button variant="ghost" size="sm" onClick={() => onClose?.()}>Close — I'll check later</Button>
          </div>
        )}

        {/* Step 3 — Done */}
        {step === 3 && (
          <div className="space-y-4 text-center py-4" data-testid="orbit4-wizard-step-done">
            <PartyPopper size={32} className="text-emerald-500 mx-auto" />
            <p className="text-base font-semibold text-slate-900">You're connected!</p>
            {firstCase && (
              <p className="text-sm text-slate-600">First case created: <span className="font-medium">{firstCase.reference}</span> — {firstCase.title}</p>
            )}
            <p className="text-sm text-slate-500">Orbit 4 tickets now flow straight into your Service Desk, and case progress flows back automatically.</p>
            <Button onClick={() => { onFinished?.(); onClose?.(); }} data-testid="orbit4-wizard-finish-btn">Done</Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
