import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Building2, Users, MapPin, Wrench, ScrollText, Layers, Wand2, Loader2 } from 'lucide-react';
import { Card } from '@/components/ui/card';
import AfsDocumentUploader from '../../CRM/Aftersales/AfsDocumentUploader';
import SageSiconImport from './SageSiconImport';
import ManualCustomerForm from './ManualCustomerForm';
import AdminBulkImports from '../AdminBulkImports';
import SiconOnboardingSync from '../SiconOnboardingSync';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const C = { border: '#e4e4e7', text: '#18181b', textDim: '#71717a' };

export const IMPORT_TYPES = [
  { id: 'sage_accounts', label: 'Customer Accounts', icon: Building2, hint: 'Sage customer accounts, or add one customer by hand. Creates or updates customers.' },
  { id: 'sicon_contacts', label: 'Customer Contacts', icon: Users, hint: 'Sicon contacts. Adds business contacts to existing customers; never creates logins.' },
  { id: 'sites', label: 'Customer Sites', icon: MapPin, hint: 'Gyms, leisure centres and other operational sites for existing customers.' },
  { id: 'equipment', label: 'Equipment & Assets', icon: Wrench, hint: 'Sicon equipment template or an asset register. Matched to existing equipment by serial number.' },
  { id: 'contracts', label: 'Maintenance Contracts', icon: ScrollText, hint: 'Existing Sage/Sicon maintenance contracts for existing customers.' },
  { id: 'estate', label: 'Complete Customer Estate', icon: Layers, hint: 'Messy multi-sheet workbooks and PDF invoices, with equipment matching and draft contracts.' },
];

const Detector = ({ onDetected }) => {
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const onUploaded = async (doc) => {
    setBusy(true);
    try {
      const fd = new FormData(); fd.append('file_id', doc.id);
      const { data } = await axios.post(`${API}/master-admin/customer-import/detect`, fd, { headers });
      setRes({ ...data, file_id: doc.id });
      if (data.confidence !== 'needs_choice') onDetected(data.type, ['sage_accounts', 'sicon_contacts'].includes(data.type) ? doc.id : null);
    } finally { setBusy(false); }
  };
  return (
    <Card className="p-4 rounded-xl border-dashed border-zinc-300" data-testid="ic-detector">
      <p className="text-sm font-semibold flex items-center gap-2"><Wand2 size={15} className="text-[var(--color-brand-blue)]" />Not sure which type? Upload the file and we’ll recognise it</p>
      <div className="mt-2"><AfsDocumentUploader c={C} accept=".xls,.xlsx,.csv,.pdf" typesLabel="XLS, XLSX, CSV or PDF" maxMb={50} onUploaded={onUploaded} testId="ic-detect-upload" /></div>
      {busy && <p className="text-xs text-zinc-500 mt-2 flex items-center gap-1"><Loader2 size={12} className="animate-spin" />Recognising…</p>}
      {res && (
        <p className="text-xs mt-2" data-testid="ic-detect-result">
          Detected: <b>{res.label}</b>{res.worksheet ? ` (worksheet “${res.worksheet}”)` : ''} · {res.confidence === 'certain' ? 'recognised exactly' : res.confidence === 'likely' ? 'recognised from the column names — please check' : 'please choose the record type below'}
          {res.next && <span className="block text-zinc-500">{res.next}</span>}
        </p>
      )}
    </Card>
  );
};

const EstateCard = () => (
  <Card className="p-5 rounded-xl border-zinc-200 space-y-2 text-sm" data-testid="ic-estate">
    <p className="font-semibold">Complete customer estates</p>
    <p className="text-zinc-600">Use <b>CRM → Aftersales → Estate Onboarding</b> for inherited multi-sheet workbooks and PDF invoices. It extracts equipment, applies existing or Pulse-calculated maintenance prices and creates draft contracts. It uses the same customer check as this Import Centre, so an existing customer is never duplicated.</p>
    <p className="text-zinc-600">MOD estates (HQs, overseas sites, kiosk logins) use the <b>MOD</b> specialist tabs in this Onboarding area.</p>
  </Card>
);

export default function ImportCentre({ initialType = '', initialOrg = '', openJobId = null }) {
  const [type, setType] = useState(initialType || (openJobId ? 'sage_accounts' : ''));
  const [fileId, setFileId] = useState(null);
  const [manual, setManual] = useState(false);
  const [src, setSrc] = useState('file');
  const hdrs = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);
  useEffect(() => { if (initialType) setType(initialType); }, [initialType]);
  const t = IMPORT_TYPES.find((x) => x.id === type);
  return (
    <div className="space-y-4" data-testid="import-centre">
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2">
        {IMPORT_TYPES.map((x) => (
          <button key={x.id} type="button" onClick={() => { setType(x.id); setFileId(null); setManual(false); }}
            className={`text-left rounded-xl border p-3 transition-colors ${type === x.id ? 'border-[var(--color-brand-blue)] bg-sky-50' : 'border-zinc-200 bg-white hover:bg-zinc-50'}`}
            data-testid={`ic-type-${x.id}`}>
            <x.icon size={16} className="text-[var(--color-brand-blue)]" />
            <p className="text-sm font-semibold mt-1.5">{x.label}</p>
            <p className="text-[11px] text-zinc-500 leading-snug mt-0.5">{x.hint}</p>
          </button>
        ))}
      </div>
      {!type && <Detector onDetected={(k, fid) => { setType(k); setFileId(fid); }} />}
      {t && <p className="text-xs text-zinc-500" data-testid="ic-type-caption">Importing never creates logins, sends emails or switches on paid products. New customers get Pulse Fitness LITE and stay “awaiting activation”.</p>}
      {type === 'sage_accounts' && (
        <div className="flex gap-2 text-xs">
          {[['file', 'Import a Sage file'], ['sicon', 'Read directly from Sicon'], ['manual', 'Add one customer by hand']].map(([k, l]) => (
            <button key={k} type="button" className={`px-3 py-1 rounded-full ${src === k ? 'bg-zinc-900 text-white' : 'bg-zinc-100'}`}
              onClick={() => { setSrc(k); setManual(k === 'manual'); }} data-testid={`ic-accounts-${k}`}>{l}</button>
          ))}
        </div>
      )}
      {type === 'sage_accounts' && manual && <ManualCustomerForm />}
      {type === 'sage_accounts' && src === 'sicon' && (
        <div className="space-y-2" data-testid="ic-sicon-direct">
          <p className="text-xs text-zinc-500">Reads customers from the live Sicon connection (set up in Integrations). It uses the same account numbers as the Sage file import, so customers already imported are recognised, not duplicated.</p>
          <SiconOnboardingSync API={API} headers={hdrs} />
        </div>
      )}
      {(type === 'sage_accounts' && src === 'file') && <SageSiconImport key="sage" fixedMode="sage_accounts" initialFileId={fileId} openJobId={openJobId} />}
      {type === 'sicon_contacts' && <SageSiconImport key="sicon" fixedMode="sicon_contacts" initialFileId={fileId} openJobId={openJobId} />}
      {['sites', 'equipment', 'contracts'].includes(type) && <AdminBulkImports key={type} API={API} only={type} initialOrg={initialOrg} />}
      {type === 'estate' && <EstateCard />}
    </div>
  );
}
