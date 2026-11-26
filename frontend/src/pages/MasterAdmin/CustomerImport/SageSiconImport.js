import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Building2, Users, Info } from 'lucide-react';
import { Card } from '@/components/ui/card';
import AfsDocumentUploader from '../../CRM/Aftersales/AfsDocumentUploader';
import ImportJobPanel from './ImportJobPanel';
import ReviewQueues from './ReviewQueues';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/master-admin/customer-import`;
const C = { border: '#e4e4e7', text: '#18181b', textDim: '#71717a' };
const MODES = [
  { id: 'sage_accounts', label: 'Sage Customer Accounts', icon: Building2, hint: 'Creates or updates customer organisations from the Sage CustomerAccounts export (XLS, XLSX or CSV).' },
  { id: 'sicon_contacts', label: 'Sicon Customer Contacts', icon: Users, hint: 'Adds business contacts to customers by CustomerCode = Sage AccountNumber. Unmatched contacts wait until the account is imported.' },
];

const Overview = ({ o }) => (
  <div className="grid grid-cols-3 md:grid-cols-9 gap-2" data-testid="ci-overview">
    {[['Sage customers', o.customer_organisations], ['Account refs', o.sage_account_references], ['Awaiting activation', o.awaiting_activation],
      ['LITE only', o.lite_only], ['Business contacts', o.imported_contacts], ['Unmatched contacts', o.unmatched_contacts],
      ['Hidden in Sage', o.hidden_sage_accounts], ['On hold', o.accounts_on_hold], ['Proposed sites', o.proposed_sites]].map(([k, v]) => (
      <div key={k} className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
        <p className="text-[10px] text-zinc-500">{k}</p><p className="text-base font-bold tabular-nums">{v ?? '—'}</p>
      </div>
    ))}
  </div>
);

export default function SageSiconImport({ fixedMode = null, initialFileId = null, openJobId = null }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);
  const [mode, setMode] = useState(fixedMode || 'sage_accounts');
  const [job, setJob] = useState(null);
  const [company, setCompany] = useState('');
  useEffect(() => {
    axios.get(`${process.env.REACT_APP_BACKEND_URL}/api/master-admin/customer-import/config`, { headers })
      .then((r) => setCompany((c) => c || r.data.default_sage_company || '')).catch(() => {});
  }, [headers]);
  const [ov, setOv] = useState({});
  const [history, setHistory] = useState([]);
  const [tick, setTick] = useState(0);
  const refresh = useCallback(async () => {
    const [a, b] = await Promise.all([axios.get(`${API}/overview`, { headers }), axios.get(`${API}/jobs`, { headers, params: { kind: mode } })]);
    setOv(a.data); setHistory(b.data.jobs || []); setTick((t) => t + 1);
  }, [headers, mode]);
  useEffect(() => { refresh().catch(() => {}); }, [refresh]);

  useEffect(() => {
    if (initialFileId) onUploaded({ id: initialFileId }).catch(() => {});
    if (openJobId) axios.get(`${API}/jobs/${openJobId}`, { headers }).then((r) => { setJob(r.data); setMode(r.data.kind); }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialFileId, openJobId]);

  const onUploaded = async (doc) => {
    const fd = new FormData();
    fd.append('file_id', doc.id); fd.append('expected', mode); fd.append('source_company', company);
    let { data } = await axios.post(`${API}/analyze`, fd, { headers });
    setJob(data);
    while (data.status === 'analysing') {
      await new Promise((r) => setTimeout(r, 1200));
      ({ data } = await axios.get(`${API}/jobs/${data.id}`, { headers }));
    }
    setJob(data);
    refresh();
  };
  const active = MODES.find((m) => m.id === mode);

  return (
    <div className="space-y-4" data-testid="customer-import-centre">
      {!fixedMode && <Overview o={ov} />}
      {!fixedMode && <div className="flex flex-wrap gap-2" role="tablist">
        {MODES.map((m) => (
          <button key={m.id} type="button" onClick={() => { setMode(m.id); setJob(null); }} role="tab" aria-selected={mode === m.id}
            className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold transition-colors ${mode === m.id ? 'seg-active' : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200'}`}
            data-testid={`ci-mode-${m.id}`}><m.icon size={14} />{m.label}</button>
        ))}
      </div>}
      <Card className="p-5 rounded-xl border-zinc-200 space-y-3">
        <p className="text-sm text-zinc-600">{active.hint}</p>
        <p className="text-xs text-zinc-500 flex items-start gap-1.5"><Info size={13} className="mt-0.5 shrink-0" />
          Importing never creates logins, sends emails or switches on paid products. New customers get Pulse Fitness LITE and stay
          “awaiting activation” until you invite named people.</p>
        <label className="text-xs text-zinc-600 flex items-center gap-2">Sage company these accounts belong to
          <input className="border rounded px-2 py-1 w-48 uppercase" maxLength={40} value={company} onChange={(e) => setCompany(e.target.value)} data-testid="ci-company-input" />
        </label>
        <AfsDocumentUploader c={C} accept=".xls,.xlsx,.csv" typesLabel="XLS, XLSX or CSV" maxMb={50} onUploaded={onUploaded} testId="ci-upload" />
      </Card>
      {job && <ImportJobPanel job={job} setJob={setJob} headers={headers} onDone={refresh} />}
      {history.length > 0 && (
        <Card className="p-4 rounded-xl border-zinc-200" data-testid="ci-history">
          <p className="text-xs font-semibold text-zinc-700 mb-2">Previous {active.label} imports</p>
          {history.slice(0, 10).map((h) => (
            <button key={h.id} type="button" className="w-full text-left text-xs flex gap-3 py-1.5 border-t border-zinc-100 hover:bg-zinc-50"
              onClick={async () => setJob((await axios.get(`${API}/jobs/${h.id}`, { headers })).data)} data-testid={`ci-history-${h.id}`}>
              <span className="w-40 text-zinc-500">{(h.created_at || '').slice(0, 16).replace('T', ' ')}</span>
              <span className="flex-1 truncate">{h.filename}</span><span className="font-medium">{h.status}</span>
            </button>
          ))}
        </Card>
      )}
      {!fixedMode && <ReviewQueues headers={headers} onChange={refresh} tick={tick} />}
    </div>
  );
}
