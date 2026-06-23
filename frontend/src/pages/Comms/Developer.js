/**
 * Developer — webhooks, API keys and public API reference for the Comms Centre.
 * Self-hosted automation: subscribe endpoints to comms events and call the
 * /api/v1/comms REST API with an X-API-Key.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Webhook, KeyRound, Plus, Trash2, Send, Copy, Power, Code2, CheckCircle2 } from 'lucide-react';

export function DeveloperView({ API, headers }) {
  const apiRoot = useMemo(() => (API || process.env.REACT_APP_BACKEND_URL || '').replace(/\/api\/?$/, ''), [API]);
  const [tab, setTab] = useState('webhooks');
  const card = { background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' };

  return (
    <div data-testid="comms-developer">
      <div className="flex items-center gap-1.5 mb-4">
        {[['webhooks', 'Webhooks', Webhook], ['keys', 'API keys', KeyRound], ['docs', 'API reference', Code2]].map(([id, label, Icon]) => (
          <button key={id} onClick={() => setTab(id)} className={`flex items-center gap-1.5 px-3.5 py-2 rounded-full text-sm font-semibold border ${tab === id ? '' : 'opacity-70'}`} style={{ borderColor: 'var(--theme-border)', background: tab === id ? 'var(--color-brand-cyan)' : 'transparent', color: tab === id ? 'var(--color-ink, #03212b)' : 'var(--theme-text)' }} data-testid={`dev-tab-${id}`}>
            <Icon size={14} />{label}
          </button>
        ))}
      </div>
      {tab === 'webhooks' && <Webhooks apiRoot={apiRoot} headers={headers} card={card} />}
      {tab === 'keys' && <ApiKeys apiRoot={apiRoot} headers={headers} card={card} />}
      {tab === 'docs' && <ApiDocs apiRoot={apiRoot} card={card} />}
    </div>
  );
}

function Webhooks({ apiRoot, headers, card }) {
  const [hooks, setHooks] = useState([]);
  const [events, setEvents] = useState([]);
  const [creating, setCreating] = useState(false);
  const [url, setUrl] = useState('');
  const [sel, setSel] = useState([]);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${apiRoot}/api/comms/webhooks`, { headers });
      setHooks(r.data.webhooks || []); setEvents(r.data.events || []);
    } catch { toast.error('Failed to load webhooks'); }
  }, [apiRoot, headers]);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!url.startsWith('http')) { toast.error('Enter a valid https URL'); return; }
    try {
      await axios.post(`${apiRoot}/api/comms/webhooks`, { url, events: sel.length ? sel : events }, { headers });
      toast.success('Webhook added'); setUrl(''); setSel([]); setCreating(false); load();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed'); }
  };
  const toggle = async (h) => { await axios.put(`${apiRoot}/api/comms/webhooks/${h.id}`, { active: !h.active }, { headers }); load(); };
  const remove = async (h) => { await axios.delete(`${apiRoot}/api/comms/webhooks/${h.id}`, { headers }); load(); };
  const test = async (h) => { await axios.post(`${apiRoot}/api/comms/webhooks/${h.id}/test`, {}, { headers }); toast.success('Test event sent'); };

  return (
    <div>
      <div className="flex justify-between items-center mb-3">
        <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Get notified at your endpoint when comms events happen (HMAC-signed).</p>
        <button onClick={() => setCreating((v) => !v)} className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }} data-testid="webhook-add-btn"><Plus size={15} />Add endpoint</button>
      </div>
      {creating && (
        <div className="rounded-2xl border p-4 mb-3" style={card} data-testid="webhook-form">
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://your-app.com/webhooks/pulse" className="w-full px-3 py-2 rounded-lg border text-sm mb-3" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="webhook-url" />
          <div className="flex flex-wrap gap-2 mb-3">
            {events.map((e) => (
              <button key={e} onClick={() => setSel((s) => s.includes(e) ? s.filter((x) => x !== e) : [...s, e])} className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${sel.includes(e) ? 'bg-cyan-500/15 border-cyan-400 text-cyan-600' : ''}`} style={!sel.includes(e) ? { borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' } : {}}>{e}</button>
            ))}
          </div>
          <p className="text-xs mb-2" style={{ color: 'var(--theme-text-muted)' }}>No events selected = all events.</p>
          <button onClick={create} className="px-4 py-2 rounded-full text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }} data-testid="webhook-save">Create webhook</button>
        </div>
      )}
      <div className="space-y-2">
        {hooks.length === 0 && <div className="rounded-2xl border p-8 text-center text-sm" style={{ ...card, color: 'var(--theme-text-muted)' }}>No webhooks yet.</div>}
        {hooks.map((h) => (
          <div key={h.id} className="rounded-2xl border p-4" style={card} data-testid={`webhook-row-${h.id}`}>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="font-semibold text-sm truncate flex items-center gap-2" style={{ color: 'var(--theme-text)' }}><Webhook size={14} />{h.url}</div>
                <div className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>{(h.events || []).length} events · {h.active ? 'active' : 'paused'}{h.last_delivery ? ` · last ${h.last_delivery.status_code}` : ''}</div>
                <div className="text-[11px] mt-1 font-mono" style={{ color: 'var(--theme-text-muted)' }}>{h.secret}</div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={() => test(h)} className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5" title="Send test" style={{ color: 'var(--theme-text-muted)' }} data-testid={`webhook-test-${h.id}`}><Send size={15} /></button>
                <button onClick={() => toggle(h)} className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5" title="Toggle" style={{ color: h.active ? '#10b981' : 'var(--theme-text-muted)' }}><Power size={15} /></button>
                <button onClick={() => remove(h)} className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 text-rose-500" data-testid={`webhook-delete-${h.id}`}><Trash2 size={15} /></button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ApiKeys({ apiRoot, headers, card }) {
  const [keys, setKeys] = useState([]);
  const [name, setName] = useState('');
  const [fresh, setFresh] = useState(null);

  const load = useCallback(async () => {
    try { const r = await axios.get(`${apiRoot}/api/comms/api-keys`, { headers }); setKeys(r.data.api_keys || []); } catch { toast.error('Failed to load keys'); }
  }, [apiRoot, headers]);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    try { const r = await axios.post(`${apiRoot}/api/comms/api-keys`, { name }, { headers }); setFresh(r.data.key); setName(''); load(); }
    catch { toast.error('Failed'); }
  };
  const revoke = async (k) => { await axios.delete(`${apiRoot}/api/comms/api-keys/${k.id}`, { headers }); load(); };
  const copy = (t) => { navigator.clipboard?.writeText(t); toast.success('Copied'); };

  return (
    <div>
      {fresh && (
        <div className="rounded-2xl border p-4 mb-3" style={{ background: 'var(--theme-bg)', borderColor: 'var(--color-brand-cyan)' }} data-testid="apikey-fresh">
          <div className="flex items-center gap-2 mb-2 text-sm font-bold" style={{ color: 'var(--theme-text)' }}><CheckCircle2 size={15} className="text-emerald-500" />Copy your key now — it won't be shown again</div>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs font-mono px-3 py-2 rounded-lg break-all" style={{ background: 'var(--theme-surface)', color: 'var(--theme-text)' }}>{fresh}</code>
            <button onClick={() => copy(fresh)} className="p-2 rounded-lg" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }}><Copy size={15} /></button>
          </div>
          <button onClick={() => setFresh(null)} className="mt-2 text-xs underline" style={{ color: 'var(--theme-text-muted)' }}>Done</button>
        </div>
      )}
      <div className="rounded-2xl border p-4 mb-3 flex items-center gap-2" style={card}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Key name (e.g. Zapier)" className="flex-1 px-3 py-2 rounded-lg border text-sm" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="apikey-name" />
        <button onClick={create} className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }} data-testid="apikey-create"><Plus size={15} />Generate</button>
      </div>
      <div className="space-y-2">
        {keys.length === 0 && <div className="rounded-2xl border p-8 text-center text-sm" style={{ ...card, color: 'var(--theme-text-muted)' }}>No API keys yet.</div>}
        {keys.map((k) => (
          <div key={k.id} className="rounded-2xl border p-4 flex items-center justify-between" style={card} data-testid={`apikey-row-${k.id}`}>
            <div>
              <div className="font-semibold text-sm flex items-center gap-2" style={{ color: 'var(--theme-text)' }}><KeyRound size={14} />{k.name}</div>
              <div className="text-xs mt-1 font-mono" style={{ color: 'var(--theme-text-muted)' }}>{k.key_masked} · {k.active ? 'active' : 'revoked'}</div>
            </div>
            {k.active && <button onClick={() => revoke(k)} className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 text-rose-500" data-testid={`apikey-revoke-${k.id}`}><Trash2 size={15} /></button>}
          </div>
        ))}
      </div>
    </div>
  );
}

function ApiDocs({ apiRoot, card }) {
  const base = `${apiRoot}/api/v1/comms`;
  const block = (s) => (
    <pre className="text-xs font-mono p-3 rounded-lg overflow-x-auto" style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)' }}>{s}</pre>
  );
  return (
    <div className="rounded-2xl border p-5 space-y-5" style={card} data-testid="api-docs">
      <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Authenticate every request with <code className="font-mono">X-API-Key: pfa_…</code></p>
      <div>
        <h4 className="font-bold text-sm mb-1" style={{ color: 'var(--theme-text)' }}>Create / update a contact</h4>
        {block(`POST ${base}/contacts\n{\n  "email": "member@example.com",\n  "first_name": "Alex",\n  "last_name": "Doe"\n}`)}
      </div>
      <div>
        <h4 className="font-bold text-sm mb-1" style={{ color: 'var(--theme-text)' }}>Unsubscribe / resubscribe</h4>
        {block(`POST ${base}/suppression\n{ "email": "x@y.com", "action": "unsubscribe" }`)}
      </div>
      <div>
        <h4 className="font-bold text-sm mb-1" style={{ color: 'var(--theme-text)' }}>Send a transactional email</h4>
        {block(`POST ${base}/send\n{ "to": "x@y.com", "subject": "Receipt", "html": "<p>Thanks!</p>" }`)}
      </div>
      <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Webhook payloads are signed: verify <code className="font-mono">X-Signature: sha256=…</code> using your endpoint's <code className="font-mono">whsec_</code> secret.</p>
    </div>
  );
}
