/**
 * Flows — automation / lifecycle journey builder for the Comms Centre.
 * Surfaces the shared marketing journeys engine (triggers + ordered nodes,
 * omnichannel dispatch) as a structured, step-based builder.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Workflow, Plus, Mail, MessageSquare, Clock, Tag, Bell, Trash2, ArrowUp, ArrowDown, Save, Send, Zap, X,
} from 'lucide-react';

const TRIGGERS = [
  { id: 'member_signed_up', label: 'Member signs up' },
  { id: 'member_renewed', label: 'Membership renewed' },
  { id: 'membership_expiring', label: 'Membership expiring soon' },
  { id: 'payment_failed', label: 'Payment failed' },
  { id: 'trial_started', label: 'Trial started' },
  { id: 'quote_sent', label: 'Quote sent' },
  { id: 'contact_created', label: 'New CRM contact' },
  { id: 'manual', label: 'Manual enrolment only' },
];

const NODE_TYPES = [
  { type: 'send_email', label: 'Send email', icon: Mail },
  { type: 'send_sms', label: 'Send SMS', icon: MessageSquare },
  { type: 'wait', label: 'Wait', icon: Clock },
  { type: 'tag', label: 'Add tag', icon: Tag },
  { type: 'notify_staff', label: 'Notify staff', icon: Bell },
];
const NODE_META = Object.fromEntries(NODE_TYPES.map((n) => [n.type, n]));
const uid = () => Math.random().toString(36).slice(2, 10);

export function FlowsView({ API, headers }) {
  const apiRoot = useMemo(() => (API || process.env.REACT_APP_BACKEND_URL || '').replace(/\/api\/?$/, ''), [API]);
  const [journeys, setJourneys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${apiRoot}/api/marketing/journeys`, { headers });
      setJourneys(r.data.journeys || []);
    } catch (e) {
      if (e?.response?.status === 403) toast.error('Flows need the Marketing module enabled.');
      else toast.error('Failed to load flows');
    } finally { setLoading(false); }
  }, [apiRoot, headers]);

  useEffect(() => { load(); }, [load]);

  const newFlow = () => setEditing({
    name: 'New flow', status: 'draft', trigger: { event: 'member_signed_up' }, nodes: [],
  });

  if (editing) {
    return <FlowEditor flow={editing} apiRoot={apiRoot} headers={headers} onClose={() => { setEditing(null); load(); }} />;
  }

  return (
    <div data-testid="comms-flows">
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Automated, trigger-based journeys across email &amp; SMS.</p>
        <button onClick={newFlow} className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }} data-testid="flow-create-btn"><Plus size={15} />New flow</button>
      </div>
      <div className="rounded-2xl border overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        {loading ? (
          <div className="p-10 text-center text-sm" style={{ color: 'var(--theme-text-muted)' }}>Loading…</div>
        ) : journeys.length === 0 ? (
          <div className="p-12 text-center">
            <Workflow size={28} className="mx-auto mb-2" style={{ color: 'var(--theme-text-muted)' }} />
            <p className="font-semibold" style={{ color: 'var(--theme-text)' }}>No flows yet</p>
            <p className="text-sm mb-4" style={{ color: 'var(--theme-text-muted)' }}>Automate welcome series, renewals and win-backs.</p>
            <button onClick={newFlow} className="px-4 py-2 rounded-full text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }} data-testid="flow-empty-create">Create flow</button>
          </div>
        ) : (
          <div>
            {journeys.map((j) => (
              <button key={j.id} onClick={() => setEditing(j)} className="w-full text-left flex items-center justify-between gap-3 px-5 py-4 border-t hover:bg-black/[0.02] dark:hover:bg-white/[0.02]" style={{ borderColor: 'var(--theme-border)' }} data-testid={`flow-row-${j.id}`}>
                <div className="min-w-0">
                  <div className="font-semibold flex items-center gap-2" style={{ color: 'var(--theme-text)' }}><Workflow size={15} />{j.name}</div>
                  <div className="text-xs mt-0.5 flex items-center gap-2" style={{ color: 'var(--theme-text-muted)' }}>
                    <Zap size={11} />{TRIGGERS.find((t) => t.id === j.trigger?.event)?.label || j.trigger?.event} · {(j.nodes || []).length} steps
                  </div>
                </div>
                <span className={`text-[11px] font-bold px-2 py-1 rounded-full ${j.status === 'active' ? 'bg-emerald-500/15 text-emerald-600' : 'bg-slate-500/15 text-slate-500'}`}>{j.status}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function FlowEditor({ flow, apiRoot, headers, onClose }) {
  const [name, setName] = useState(flow.name || '');
  const [status, setStatus] = useState(flow.status || 'draft');
  const [trigger, setTrigger] = useState(flow.trigger?.event || 'member_signed_up');
  const [nodes, setNodes] = useState(() => (flow.nodes || []).map((n) => ({ ...n, id: n.id || uid() })));
  const [saving, setSaving] = useState(false);
  const [id, setId] = useState(flow.id || null);
  const [testContact, setTestContact] = useState('');

  const addNode = (type) => setNodes((prev) => [...prev, { id: uid(), type, title: '', subject: '', body: '', hours: 24, tag: '' }]);
  const updateNode = (nid, patch) => setNodes((prev) => prev.map((n) => (n.id === nid ? { ...n, ...patch } : n)));
  const removeNode = (nid) => setNodes((prev) => prev.filter((n) => n.id !== nid));
  const move = (idx, dir) => setNodes((prev) => {
    const j = idx + dir; if (j < 0 || j >= prev.length) return prev;
    const next = [...prev]; [next[idx], next[j]] = [next[j], next[idx]]; return next;
  });

  const save = async () => {
    setSaving(true);
    try {
      const r = await axios.post(`${apiRoot}/api/marketing/journeys`, {
        id: id || undefined, name, status, trigger: { event: trigger }, nodes,
      }, { headers });
      setId(r.data.journey?.id);
      toast.success('Flow saved');
      return r.data.journey?.id;
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
      return null;
    } finally { setSaving(false); }
  };

  const testSend = async () => {
    const jid = id || await save();
    if (!jid) return;
    if (!testContact.trim()) { toast.error('Enter a CRM contact id to test'); return; }
    try {
      const r = await axios.post(`${apiRoot}/api/marketing/journeys/${jid}/test-send`, { contact_id: testContact.trim() }, { headers });
      toast.success(`Test: ${r.data.sent} sent, ${r.data.skipped} skipped`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Test send failed');
    }
  };

  const inputStyle = { background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' };
  return (
    <div data-testid="flow-editor">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <button onClick={onClose} className="flex items-center gap-1.5 text-sm font-semibold" style={{ color: 'var(--theme-text-muted)' }} data-testid="flow-back"><X size={16} />Back to flows</button>
        <div className="flex items-center gap-2">
          <input value={testContact} onChange={(e) => setTestContact(e.target.value)} placeholder="Test contact id" className="px-3 py-2 rounded-full text-sm border" style={inputStyle} data-testid="flow-test-contact" />
          <button onClick={testSend} className="flex items-center gap-1.5 px-3 py-2 rounded-full text-sm font-semibold border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="flow-test-send"><Send size={14} />Test</button>
          <button onClick={save} disabled={saving} className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }} data-testid="flow-save"><Save size={14} />{saving ? 'Saving…' : 'Save'}</button>
        </div>
      </div>

      <div className="rounded-2xl border p-5 mb-4" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <div className="grid sm:grid-cols-3 gap-3">
          <div className="sm:col-span-1">
            <label className="block text-[11px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} className="w-full px-3 py-2 rounded-xl border text-sm" style={inputStyle} data-testid="flow-name" />
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>Trigger</label>
            <select value={trigger} onChange={(e) => setTrigger(e.target.value)} className="w-full px-3 py-2 rounded-xl border text-sm" style={inputStyle} data-testid="flow-trigger">
              {TRIGGERS.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>Status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="w-full px-3 py-2 rounded-xl border text-sm" style={inputStyle} data-testid="flow-status">
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
            </select>
          </div>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-3">
        {nodes.map((n, i) => {
          const Meta = NODE_META[n.type] || { label: n.type, icon: Workflow };
          const Icon = Meta.icon;
          return (
            <div key={n.id} className="rounded-2xl border p-4" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid={`flow-node-${i}`}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 font-bold text-sm" style={{ color: 'var(--theme-text)' }}><Icon size={15} />{Meta.label}</div>
                <div className="flex items-center gap-1">
                  <button onClick={() => move(i, -1)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5" style={{ color: 'var(--theme-text-muted)' }}><ArrowUp size={14} /></button>
                  <button onClick={() => move(i, 1)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5" style={{ color: 'var(--theme-text-muted)' }}><ArrowDown size={14} /></button>
                  <button onClick={() => removeNode(n.id)} className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 text-rose-500" data-testid={`flow-node-remove-${i}`}><Trash2 size={14} /></button>
                </div>
              </div>
              {n.type === 'send_email' && (
                <div className="space-y-2">
                  <input value={n.subject || ''} onChange={(e) => updateNode(n.id, { subject: e.target.value })} placeholder="Subject line" className="w-full px-3 py-2 rounded-lg border text-sm" style={inputStyle} data-testid={`flow-node-subject-${i}`} />
                  <textarea value={n.body || ''} onChange={(e) => updateNode(n.id, { body: e.target.value })} rows={3} placeholder="Email body (HTML supported). Use {{first_name}} to personalise." className="w-full px-3 py-2 rounded-lg border text-sm" style={inputStyle} data-testid={`flow-node-body-${i}`} />
                </div>
              )}
              {n.type === 'send_sms' && (
                <textarea value={n.body || ''} onChange={(e) => updateNode(n.id, { body: e.target.value })} rows={2} placeholder="SMS message (160 chars)" className="w-full px-3 py-2 rounded-lg border text-sm" style={inputStyle} data-testid={`flow-node-body-${i}`} />
              )}
              {n.type === 'wait' && (
                <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--theme-text)' }}>Wait <input type="number" min="1" value={n.hours || 24} onChange={(e) => updateNode(n.id, { hours: Number(e.target.value) || 24 })} className="w-20 px-2 py-1.5 rounded-lg border" style={inputStyle} data-testid={`flow-node-hours-${i}`} /> hours</div>
              )}
              {n.type === 'tag' && (
                <input value={n.tag || ''} onChange={(e) => updateNode(n.id, { tag: e.target.value })} placeholder="Tag to add (e.g. engaged)" className="w-full px-3 py-2 rounded-lg border text-sm" style={inputStyle} data-testid={`flow-node-tag-${i}`} />
              )}
              {n.type === 'notify_staff' && (
                <input value={n.body || ''} onChange={(e) => updateNode(n.id, { body: e.target.value })} placeholder="Internal note for staff" className="w-full px-3 py-2 rounded-lg border text-sm" style={inputStyle} data-testid={`flow-node-note-${i}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Add step */}
      <div className="mt-4 rounded-2xl border border-dashed p-4" style={{ borderColor: 'var(--theme-border)' }}>
        <p className="text-[11px] uppercase tracking-wider font-bold mb-2" style={{ color: 'var(--theme-text-muted)' }}>Add a step</p>
        <div className="flex flex-wrap gap-2">
          {NODE_TYPES.map(({ type, label, icon: Icon }) => (
            <button key={type} onClick={() => addNode(type)} className="flex items-center gap-1.5 px-3 py-2 rounded-full text-sm font-semibold border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`flow-add-${type}`}><Icon size={14} />{label}</button>
          ))}
        </div>
      </div>
    </div>
  );
}
