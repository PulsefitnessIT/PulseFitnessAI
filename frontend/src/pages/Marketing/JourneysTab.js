/* Journeys — list + visual SVG canvas builder */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Plus, Save, Loader2, Edit2, Send, X, CheckCircle2, AlertCircle } from 'lucide-react';  
import JourneyCanvas from './JourneyCanvas';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const JourneysTab = ({ API, headers }) => {
  const [journeys, setJourneys] = useState([]);
  const [editing, setEditing] = useState(null);
  const [name, setName] = useState('');
  const [trigger, setTrigger] = useState('member_signed_up');
  const [nodes, setNodes] = useState([]);
  const [busy, setBusy] = useState(false);
  const [testSendFor, setTestSendFor] = useState(null);
  const [testContacts, setTestContacts] = useState([]);
  const [testContactId, setTestContactId] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [testBusy, setTestBusy] = useState(false);

  const load = () => axios.get(`${API}/api/marketing/journeys`, { headers }).then((r) => setJourneys(r.data.journeys)).catch(() => {});
  useEffect(() => { load();   }, []);

  const startNew = () => {
    setEditing('new');
    setName(''); setTrigger('member_signed_up');
    setNodes([
      { id: 'n1', type: 'wait', duration_h: 24 },
      { id: 'n2', type: 'send_email', subject: 'Welcome aboard, {{first_name}}', body: '<p>Glad you joined.</p>' },
    ]);
  };

  const startEdit = (j) => {
    setEditing(j.id); setName(j.name);
    setTrigger(j.trigger?.event || 'member_signed_up');
    setNodes(j.nodes || []);
  };

  const save = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const edges = nodes.length > 0 ? [
        { from: 'trigger', to: nodes[0].id },
        ...nodes.slice(1).map((n, i) => ({ from: nodes[i].id, to: n.id })),
      ] : [];
      await axios.post(`${API}/api/marketing/journeys`, {
        id: editing === 'new' ? undefined : editing,
        name, trigger: { event: trigger }, nodes, edges, status: 'draft',
      }, { headers });
      setEditing(null); load();
    } finally { setBusy(false); }
  };

  const openTestSend = async (j) => {
    setTestSendFor(j);
    setTestResult(null);
    setTestContactId('');
    try {
      // Reuse the audiences preview endpoint with empty rules to sample contacts.
      const r = await axios.post(
        `${API}/api/marketing/audiences/preview`,
        { rules: { op: 'and', conditions: [] } },
        { headers },
      );
      setTestContacts(r.data.sample_contacts || []);
    } catch {
      setTestContacts([]);
    }
  };

  const sendTest = async () => {
    if (!testSendFor || !testContactId) return;
    setTestBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/api/marketing/journeys/${testSendFor.id}/test-send`,
        { contact_id: testContactId },
        { headers },
      );
      setTestResult(data);
      notify.success(`Test dispatched — ${data.sent} sent, ${data.failed} failed, ${data.skipped} skipped`);
    } catch (e) {
      notifyApiError(notify, e, 'Test send failed');
      setTestResult({ error: e.response?.data?.detail || 'Test send failed' });
    } finally { setTestBusy(false); }
  };

  return (
    <div className="space-y-4" data-testid="marketing-journeys-tab">
      <div className="flex items-start justify-end flex-wrap gap-2">
        {!editing && (
          <button type="button" onClick={startNew} className="btn-primary" data-testid="journey-new-btn">
            <Plus size={12} /> New journey
          </button>
        )}
      </div>

      {editing && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5 space-y-4" data-testid="journey-builder">
          <div className="flex items-center gap-2 flex-wrap">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Journey name" className="flex-1 min-w-0 sm:min-w-[14rem] px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm" data-testid="journey-name-input" />
            <button onClick={save} disabled={busy || !name.trim()} className="px-4 py-2 rounded-md bg-[var(--color-brand-blue)] text-white text-sm font-semibold disabled:opacity-50 inline-flex items-center gap-1.5" data-testid="journey-save-btn">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Save journey
            </button>
            <button onClick={() => setEditing(null)} className="px-3 py-2 text-zinc-500 dark:text-zinc-400 dark:text-zinc-500 hover:text-zinc-900 dark:text-zinc-100 text-sm" data-testid="journey-cancel-btn">Cancel</button>
          </div>

          <JourneyCanvas trigger={trigger} setTrigger={setTrigger} nodes={nodes} setNodes={setNodes} />
        </div>
      )}

      {!editing && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900" data-testid="journey-list">
          {journeys.length === 0 ? (
            <p className="p-5 text-sm text-zinc-400 dark:text-zinc-500 text-center">No journeys yet — create one to start automating.</p>
          ) : (
            <ul>
              {journeys.map((j) => (
                <li key={j.id} className="p-4 border-b border-zinc-50 last:border-b-0 flex items-center justify-between" data-testid={`journey-row-${j.id}`}>
                  <div>
                    <p className="font-medium text-zinc-900 dark:text-zinc-100 text-sm">{j.name}</p>
                    <p className="text-[11px] text-zinc-400 dark:text-zinc-500">Trigger: <code className="font-mono">{j.trigger?.event}</code> · {j.nodes?.length || 0} steps</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${j.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 dark:text-zinc-500'}`}>{j.status}</span>
                    <button onClick={() => openTestSend(j)} className="text-zinc-400 dark:text-zinc-500 hover:text-fuchsia-500" title="Test send" data-testid={`journey-test-send-${j.id}`}>
                      <Send size={12} />
                    </button>
                    <button onClick={() => startEdit(j)} className="text-zinc-400 dark:text-zinc-500 hover:text-[var(--color-brand-blue)]" data-testid={`journey-edit-${j.id}`}>
                      <Edit2 size={13} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {testSendFor && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setTestSendFor(null)}
          data-testid="journey-test-send-dialog"
        >
          <div onClick={(e) => e.stopPropagation()} className="bg-white dark:bg-zinc-900 rounded-xl shadow-2xl border border-zinc-200 dark:border-zinc-800 max-w-md w-full p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold text-zinc-900 dark:text-zinc-100 inline-flex items-center gap-2">
                <Send size={14} className="text-fuchsia-500" /> Test send: {testSendFor.name}
              </h3>
              <button onClick={() => setTestSendFor(null)} className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200">
                <X size={14} />
              </button>
            </div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3">
              Pick a contact — the journey's email/SMS/push/in-app steps will fire immediately to them. Wait + branch nodes are skipped during test send.
            </p>
            <select
              value={testContactId}
              onChange={(e) => setTestContactId(e.target.value)}
              className="w-full px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 mb-3"
              data-testid="journey-test-contact-select"
            >
              <option value="">— Choose a contact —</option>
              {testContacts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.first_name} {c.last_name} {c.email ? `· ${c.email}` : ''}
                </option>
              ))}
            </select>
            <button
              onClick={sendTest}
              disabled={!testContactId || testBusy}
              className="w-full px-3 py-2 rounded-md bg-[var(--color-brand-blue)] text-white text-sm font-semibold disabled:opacity-50 inline-flex items-center justify-center gap-1.5"
              data-testid="journey-test-send-confirm"
            >
              {testBusy ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
              Dispatch test
            </button>

            {testResult && !testResult.error && (
              <div className="mt-4 rounded-lg border border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950/40 p-3" data-testid="journey-test-result">
                <p className="text-xs font-semibold text-emerald-800 dark:text-emerald-200 inline-flex items-center gap-1.5">
                  <CheckCircle2 size={12} /> {testResult.sent} sent · {testResult.failed} failed · {testResult.skipped} skipped
                </p>
                <ul className="mt-2 text-[11px] space-y-1 text-emerald-900 dark:text-emerald-100">
                  {(testResult.history || []).map((h, i) => (
                    <li key={i} className="flex items-center gap-1.5" data-testid={`journey-test-history-${i}`}>
                      <span className="text-[9px] uppercase tracking-wider opacity-70">{h.type}</span>
                      <span>·</span>
                      <span className="font-semibold">{h.status}</span>
                      {h.channel && <span className="opacity-70">via {h.channel}{h.provider && h.provider !== h.channel ? ` (${h.provider})` : ''}</span>}
                      {h.error && <span className="text-rose-600 dark:text-rose-300">— {h.error}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {testResult?.error && (
              <div className="mt-4 rounded-lg border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 p-3 text-xs text-rose-700 dark:text-rose-200 inline-flex items-center gap-1.5">
                <AlertCircle size={12} /> {testResult.error}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default JourneysTab;
