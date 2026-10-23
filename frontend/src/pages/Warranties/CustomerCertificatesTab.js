import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { FileCheck2, Loader2, Search, FileDown, CalendarClock } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const fmtDate = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return String(iso).slice(0, 10); }
};

export default function CustomerCertificatesTab() {
  const [data, setData] = useState(null);
  const [search, setSearch] = useState('');
  const [contractId, setContractId] = useState('');
  const [downloading, setDownloading] = useState('');

  const load = useCallback(() => {
    const params = new URLSearchParams({ search, contract_id: contractId });
    axios.get(`${API}/customer/certificates?${params}`, authHeaders())
      .then((r) => setData(r.data)).catch(() => setData({ certificates: [], count: 0 }));
  }, [search, contractId]);

  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  const download = (cert) => {
    setDownloading(cert.id);
    axios.get(`${API}/customer/certificates/${cert.id}/download`, { ...authHeaders(), responseType: 'blob' })
      .then((res) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
        a.download = cert.filename || 'certificate.pdf'; a.click(); URL.revokeObjectURL(a.href);
      })
      .catch(() => alert('Sorry, that certificate could not be downloaded. Please try again.'))
      .finally(() => setDownloading(''));
  };

  if (!data) return <div className="flex items-center justify-center py-16"><Loader2 className="animate-spin text-slate-400" /></div>;

  const certs = data.certificates || [];
  return (
    <div className="space-y-4" data-testid="customer-certificates-tab">
      {data.next_service_due && (
        <div className="flex items-start justify-end gap-3 flex-wrap">
          <div className="rounded-xl bg-blue-50 ring-1 ring-blue-200 px-4 py-2 text-center" data-testid="cert-next-due">
            <div className="text-[11px] text-blue-600 uppercase tracking-wide flex items-center gap-1"><CalendarClock size={12} /> Next service due</div>
            <div className="text-sm font-bold text-blue-800">{fmtDate(data.next_service_due)}</div>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input data-testid="cert-search" value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by station…"
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-200 focus:ring-2 focus:ring-blue-200 outline-none" />
        </div>
        {(data.contracts || []).length > 1 && (
          <select data-testid="cert-contract-filter" value={contractId} onChange={(e) => setContractId(e.target.value)}
            className="px-3 py-2 text-sm rounded-lg border border-slate-200">
            <option value="">All contracts</option>
            {data.contracts.map((c) => <option key={c.id} value={c.id}>{c.contract_number || c.title}</option>)}
          </select>
        )}
      </div>

      {certs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-200 py-14 text-center text-slate-400" data-testid="certs-empty">
          <FileCheck2 size={32} className="mx-auto mb-2 opacity-50" />
          No certificates found yet. They appear here once a station service is completed.
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {certs.map((cert) => (
            <div key={cert.id} className="rounded-xl border border-slate-200 bg-white p-4 flex items-center justify-between gap-3"
              data-testid={`cert-card-${cert.id}`}>
              <div className="flex items-center gap-3 min-w-0">
                {cert.logo_url && (
                  <img src={/^(https?:|data:)/.test(cert.logo_url) ? cert.logo_url : `${process.env.REACT_APP_BACKEND_URL}${cert.logo_url}`}
                    alt="" data-testid={`cert-logo-${cert.id}`}
                    className="h-10 w-10 rounded-md object-contain bg-white border border-slate-100 flex-shrink-0"
                    onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                )}
                <div className="min-w-0">
                  <div className="font-semibold text-slate-800 truncate">{cert.station_name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {cert.contract_number && <span>{cert.contract_number} · </span>}
                    Serviced {fmtDate(cert.service_date)}
                  </div>
                  {cert.next_service_due && <div className="text-xs text-slate-400 mt-0.5">Next due {fmtDate(cert.next_service_due)}</div>}
                </div>
              </div>
              <button onClick={() => download(cert)} disabled={downloading === cert.id}
                data-testid={`cert-download-${cert.id}`}
                className="flex-shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 text-white text-sm font-medium px-3 py-2 hover:bg-blue-700 disabled:opacity-50">
                {downloading === cert.id ? <Loader2 size={15} className="animate-spin" /> : <FileDown size={15} />} PDF
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
