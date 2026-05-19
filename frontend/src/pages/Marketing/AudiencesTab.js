/* Audiences tab — rule builder, save, list */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Users, Plus, Sparkles, Loader2, Trash2, Save, Upload } from 'lucide-react';  
import { Link } from 'react-router-dom';
import HelpHint from '@/components/HelpHint';
import EmptyState from '@/components/shared/EmptyState';

const BASE_FIELDS = [
  { id: 'lifetime_value_gbp', label: 'Lifetime value (£)', type: 'number' },
  { id: 'churn_risk_score', label: 'Churn risk score', type: 'number' },
  { id: 'attendance_30d', label: 'Visits in last 30 days', type: 'number' },
  { id: 'last_attended_at', label: 'Last attended', type: 'days_ago' },
  { id: 'signup_at', label: 'Signed up', type: 'days_ago' },
  { id: 'class_preference', label: 'Class preference', type: 'enum', options: ['spin', 'hiit', 'pt', 'yoga', 'strength'] },
  { id: 'subscription_tier', label: 'Subscription tier', type: 'enum', options: ['free', 'pro', 'premium'] },
  { id: 'payment_status', label: 'Payment status', type: 'enum', options: ['active', 'failed', 'cancelled'] },
];
const FIELD_TYPE_TO_RB = (ft) => {
  if (ft === 'number') return 'number';
  if (ft === 'date') return 'days_ago';
  if (ft === 'select' || ft === 'multi_select') return 'enum';
  return 'text';
};
const OPS = [
  { id: '>=', label: '≥' }, { id: '<=', label: '≤' }, { id: '==', label: '=' }, { id: '!=', label: '≠' },
];

const AudiencesTab = ({ API, headers }) => {
  const [audiences, setAudiences] = useState([]);
  const [conditions, setConditions] = useState([]);
  const [name, setName] = useState('');
  const [aiPrompt, setAiPrompt] = useState('');
  const [preview, setPreview] = useState({ size: 0, sample: [] });
  const [busy, setBusy] = useState(false);
  const [customFields, setCustomFields] = useState([]);
  const [dataSrc, setDataSrc] = useState(null);

  const FIELDS = React.useMemo(() => [...BASE_FIELDS, ...customFields], [customFields]);

  const load = () => axios.get(`${API}/api/marketing/audiences`, { headers }).then((r) => setAudiences(r.data.audiences)).catch(() => {});
  const loadDataSrc = () => axios.get(`${API}/api/marketing/audiences/data-sources`, { headers }).then((r) => setDataSrc(r.data)).catch(() => {});
  const loadCustomProps = () => axios.get(`${API}/api/custom-properties?entity_type=contact`, { headers })
    .then((r) => {
      const cf = (r.data.properties || []).map((p) => ({
        id: `custom_fields.${p.key}`,
        label: `${p.label} (custom)`,
        type: FIELD_TYPE_TO_RB(p.field_type),
        options: (p.options || []).map((o) => o.value),
      }));
      setCustomFields(cf);
    })
    .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps -- todo: review missing dep(s) 'load', 'loadCustomProps', and 'loadDataSrc'; pre-existing as of iter 216h226-polish-5.
  useEffect(() => { load(); loadCustomProps(); loadDataSrc();   }, []);

  const refreshPreview = async (rules) => {
    try {
      const { data } = await axios.post(`${API}/api/marketing/audiences/preview`, { rules }, { headers });
      setPreview({ size: data.estimated_size, sample: data.sample_contacts });
    } catch { /* ignore */ }
  };

  useEffect(() => {
    refreshPreview({ op: 'and', conditions });
    // eslint-disable-next-line
  }, [conditions]);

  const addCondition = () => setConditions((c) => [...c, { field: 'lifetime_value_gbp', op: '>=', value: 100 }]);
  const updateCondition = (i, patch) => setConditions((c) => c.map((x, idx) => idx === i ? { ...x, ...patch } : x));
  const removeCondition = (i) => setConditions((c) => c.filter((_, idx) => idx !== i));

  const aiSuggest = async () => {
    if (!aiPrompt.trim()) return;
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/api/marketing/audiences/ai-suggest`, { description: aiPrompt }, { headers });
      setConditions(data.rules.conditions || []);
      setPreview({ size: data.estimated_size, sample: [] });
    } finally { setBusy(false); }
  };

  const save = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await axios.post(`${API}/api/marketing/audiences`, { name, rules: { op: 'and', conditions } }, { headers });
      setName(''); setConditions([]);
      load();
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5" data-testid="marketing-audiences-tab">
      {dataSrc?.needs_data_import && (
        <div
          className="rounded-xl border border-amber-300 dark:border-amber-700/60 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/30 dark:to-orange-950/30 p-4 flex items-start gap-3"
          data-testid="audiences-empty-state-import"
        >
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center text-white shrink-0">
            <Upload size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">
              No contacts to segment yet
            </p>
            <p className="text-xs text-zinc-700 dark:text-zinc-300 mt-1">
              Audiences pull from your members or CRM contacts — but you have neither bolted on. Import a contact CSV to get started, or add Memberships / CRM to sync a live contact source.
            </p>
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              <Link
                to="/marketing?tab=contacts&import=1"
                className="px-3 py-2 rounded-md bg-gradient-to-r from-amber-500 to-orange-500 text-white text-xs font-bold inline-flex items-center gap-1.5"
                data-testid="audiences-import-csv-btn"
              >
                <Upload size={12} /> Import contact CSV
              </Link>
              <Link
                to="/memberships"
                className="px-3 py-2 rounded-md border border-amber-300 dark:border-amber-700 text-xs font-semibold text-amber-700 dark:text-amber-300 inline-flex items-center gap-1.5"
                data-testid="audiences-add-memberships-btn"
              >
                Try Memberships
              </Link>
              <Link
                to="/crm"
                className="px-3 py-2 rounded-md border border-amber-300 dark:border-amber-700 text-xs font-semibold text-amber-700 dark:text-amber-300 inline-flex items-center gap-1.5"
                data-testid="audiences-add-crm-btn"
              >
                Try CRM
              </Link>
            </div>
          </div>
        </div>
      )}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5">
        <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-2 flex items-center gap-1">
          <Sparkles size={12} className="text-amber-500" /> Describe your audience in plain English
          <HelpHint guideId="mkt-segments" testId="help-hint-audiences" className="ml-auto" />
        </p>
        <div className="flex gap-2">
          <input
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            placeholder="e.g. high spenders at risk of churning"
            className="flex-1 px-3 py-2 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm"
            data-testid="audience-ai-input"
          />
          <button
            onClick={aiSuggest}
            disabled={busy || !aiPrompt.trim()}
            className="px-3 py-2 rounded-md bg-gradient-to-r from-[var(--color-brand-blue)] to-[var(--color-brand-cyan-hover)] text-white text-sm font-semibold disabled:opacity-50 inline-flex items-center gap-1.5"
            data-testid="audience-ai-suggest-btn"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} AI suggest
          </button>
        </div>

        <div className="mt-5 space-y-2">
          {conditions.map((c, i) => {
            const f = FIELDS.find((x) => x.id === c.field) || FIELDS[0];
            return (
              <div key={i} className="flex items-center gap-2" data-testid={`audience-condition-${i}`}>
                <select value={c.field} onChange={(e) => updateCondition(i, { field: e.target.value })} className="px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-xs flex-1">
                  {FIELDS.map((fld) => <option key={fld.id} value={fld.id}>{fld.label}</option>)}
                </select>
                <select value={c.op} onChange={(e) => updateCondition(i, { op: e.target.value })} className="px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-xs w-16">
                  {OPS.map((op) => <option key={op.id} value={op.id}>{op.label}</option>)}
                </select>
                {f.type === 'enum' ? (
                  <select value={c.value} onChange={(e) => updateCondition(i, { value: e.target.value })} className="px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-xs flex-1">
                    {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : f.type === 'days_ago' ? (
                  <input type="text" value={c.value} onChange={(e) => updateCondition(i, { value: e.target.value })} placeholder="30d_ago" className="px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-xs flex-1" />
                ) : (
                  <input type="number" value={c.value} onChange={(e) => updateCondition(i, { value: parseFloat(e.target.value) || 0 })} className="px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-xs flex-1" />
                )}
                <button onClick={() => removeCondition(i)} className="p-1 text-zinc-400 dark:text-zinc-500 hover:text-red-500"><Trash2 size={13} /></button>
              </div>
            );
          })}
          <button onClick={addCondition} className="inline-flex items-center gap-1 text-xs text-[var(--color-brand-blue)] font-semibold mt-1" data-testid="audience-add-condition">
            <Plus size={12} /> Add condition
          </button>
        </div>

        <div className="mt-5 p-3 rounded-lg bg-zinc-50 dark:bg-zinc-900/50 flex items-center justify-between" data-testid="audience-preview">
          <p className="text-xs text-zinc-600 dark:text-zinc-400 dark:text-zinc-500">
            <span className="font-bold text-zinc-900 dark:text-zinc-100 text-sm">{preview.size.toLocaleString()}</span> contacts match this audience
          </p>
          <div className="flex items-center gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Audience name…" className="px-2 py-1.5 border border-zinc-200 dark:border-zinc-800 rounded-md text-xs" data-testid="audience-name-input" />
            <button onClick={save} disabled={busy || !name.trim()} className="px-3 py-1.5 rounded-md bg-[var(--color-brand-blue)] text-white text-xs font-semibold disabled:opacity-50 inline-flex items-center gap-1" data-testid="audience-save-btn">
              <Save size={11} /> Save
            </button>
          </div>
        </div>
      </div>

      {audiences.length > 0 && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5" data-testid="audience-list">
          <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-3 uppercase tracking-wider">Saved audiences</p>
          <div className="space-y-2">
            {audiences.map((a) => (
              <div key={a.id} className="flex items-center justify-between py-2 border-b border-zinc-100 dark:border-zinc-800 last:border-b-0">
                <p className="text-sm text-zinc-900 dark:text-zinc-100 font-medium">{a.name}</p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 dark:text-zinc-500">{a.estimated_size?.toLocaleString() || 0} contacts</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {audiences.length === 0 && !dataSrc?.needs_data_import && (
        <EmptyState
          icon={Users}
          title="No saved audiences yet"
          hint="Build your first one above — describe it in plain English, or stack a few rules. Saved audiences power campaigns, automations and the AI churn radar."
          testId="audiences-empty-saved"
        />
      )}
    </div>
  );
};

export default AudiencesTab;
