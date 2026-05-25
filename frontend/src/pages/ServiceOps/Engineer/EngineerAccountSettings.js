/**
 * EngineerAccountSettings — Iter 217a.
 *
 * Slide-out account settings drawer for the Engineer App. Triggered from the
 * hamburger menu in `EngineerHomeV2`. Houses one-off onboarding tasks and
 * housekeeping items that previously cluttered the main dashboard / customers
 * page:
 *   • Connect Stripe (payouts) — moved from the home dashboard amber banner.
 *   • Import customers from CSV (+ download template) — moved from
 *     `EngineerCustomers.js` header.
 *   • Support link.
 *   • Sign out.
 *
 * Receives the latest payouts/Stripe-connect status from the parent so the
 * banner copy stays consistent, and exposes an `onChanged` callback that the
 * parent can fire to refresh dashboard data after an import.
 */
import { useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  X, CreditCard, Upload, Download, LifeBuoy, LogOut,
  Loader2, ChevronRight, CheckCircle2, AlertTriangle, FileSpreadsheet,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const Row = ({ icon: Icon, title, subtitle, onClick, accent = '#1d4ed8', testid, right, disabled, danger }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    className={`w-full text-left flex items-center gap-3 px-4 py-3 rounded-xl border transition-colors disabled:opacity-50 ${
      danger
        ? 'border-rose-200 bg-rose-50 hover:bg-rose-100'
        : 'border-slate-200 bg-white hover:bg-slate-50'
    }`}
    data-testid={testid}
  >
    <div
      className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
      style={{ background: danger ? '#fee2e2' : `${accent}15` }}
    >
      <Icon size={18} style={{ color: danger ? '#b91c1c' : accent }} />
    </div>
    <div className="flex-1 min-w-0">
      <p className={`text-sm font-bold truncate ${danger ? 'text-rose-900' : 'text-slate-900'}`}>{title}</p>
      {subtitle ? (
        <p className={`text-xs truncate ${danger ? 'text-rose-700' : 'text-slate-500'}`}>{subtitle}</p>
      ) : null}
    </div>
    {right || <ChevronRight size={16} className="text-slate-400 flex-shrink-0" />}
  </button>
);

export default function EngineerAccountSettings({ open, onClose, payouts, onChanged }) {
  const navigate = useNavigate();
  const [importing, setImporting] = useState(false);
  const importRef = useRef(null);

  if (!open) return null;

  const handleDownloadTemplate = async () => {
    try {
      const r = await axios.get(`${API}/svc/engineer/customers/template.csv`, {
        ...auth(),
        responseType: 'blob',
      });
      const blob = new Blob([r.data], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'engineer-customers-template.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      notify.error('Could not download template', err?.response?.data?.detail || err?.message);
    }
  };

  const handleImportClick = () => importRef.current?.click();

  const handleImportFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const r = await axios.post(`${API}/svc/engineer/customers/import-csv`, fd, {
        ...auth(),
        headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
      });
      const d = r.data || {};
      const summary = `${d.imported || 0} new · ${d.merged || 0} merged · ${(d.skipped || []).length} skipped`;
      notify.success('Import complete', summary);
      if ((d.errors || []).length) {
        notify.error(
          `${d.errors.length} row(s) failed`,
          d.errors.slice(0, 3).map((er) => `Row ${er.row}: ${er.error}`).join('\n')
        );
      }
      if (onChanged) onChanged();
    } catch (err) {
      notify.error('Import failed', err?.response?.data?.detail || err?.message);
    } finally {
      setImporting(false);
      if (importRef.current) importRef.current.value = '';
    }
  };

  const handleSignOut = () => {
    try {
      localStorage.removeItem('token');
    } catch {
      /* ignore */
    }
    navigate('/login');
  };

  const stripeReady = !!payouts?.ready;
  const stripeConnected = !!payouts?.connected;

  return (
    <div
      className="fixed inset-0 z-40 bg-black/50 flex justify-end"
      onClick={onClose}
      data-testid="engineer-settings-backdrop"
    >
      <aside
        className="bg-white w-full sm:max-w-md h-full shadow-2xl overflow-y-auto flex flex-col"
        onClick={(e) => e.stopPropagation()}
        data-testid="engineer-settings-drawer"
      >
        <header className="sticky top-0 z-10 bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">
              GymAxis · Engineer
            </p>
            <h2 className="text-base font-extrabold text-slate-900">Account settings</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50"
            aria-label="Close settings"
            data-testid="engineer-settings-close"
          >
            <X size={16} />
          </button>
        </header>

        <div className="p-4 space-y-5 flex-1">
          {/* Payouts / Stripe */}
          <section data-testid="engineer-settings-section-payouts">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">Payouts</p>
            <Row
              icon={CreditCard}
              accent="#7c3aed"
              title={
                stripeReady
                  ? 'Stripe connected'
                  : stripeConnected
                    ? 'Finish Stripe onboarding'
                    : 'Connect Stripe to take card payments'
              }
              subtitle={
                stripeReady
                  ? 'Payouts are enabled on your invoices.'
                  : stripeConnected
                    ? 'A few details still needed — usually ID or bank account.'
                    : 'Connect your Stripe (≈3 min) so customers can pay invoices by card.'
              }
              onClick={() => { onClose(); navigate('/svc/engineer/payouts'); }}
              testid="engineer-settings-stripe-row"
              right={
                stripeReady
                  ? <CheckCircle2 size={18} className="text-emerald-500 flex-shrink-0" />
                  : <AlertTriangle size={18} className="text-amber-500 flex-shrink-0" />
              }
            />
          </section>

          {/* Customers — import */}
          <section data-testid="engineer-settings-section-customers">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">Customers</p>
            <div className="space-y-2">
              <Row
                icon={Upload}
                accent="#1d4ed8"
                title={importing ? 'Importing customers…' : 'Import customers from CSV'}
                subtitle="Bulk-add or merge customer records from a CSV file."
                onClick={handleImportClick}
                disabled={importing}
                testid="engineer-settings-import-row"
                right={
                  importing
                    ? <Loader2 size={16} className="animate-spin text-blue-600 flex-shrink-0" />
                    : <ChevronRight size={16} className="text-slate-400 flex-shrink-0" />
                }
              />
              <Row
                icon={Download}
                accent="#0891b2"
                title="Download CSV template"
                subtitle="Get the import template with example rows."
                onClick={handleDownloadTemplate}
                testid="engineer-settings-template-row"
              />
              <input
                type="file"
                ref={importRef}
                accept=".csv,text/csv"
                onChange={handleImportFile}
                className="hidden"
                data-testid="engineer-settings-import-input"
              />
              <Row
                icon={FileSpreadsheet}
                accent="#0f766e"
                title="Open my customers"
                subtitle="View and edit saved customer records."
                onClick={() => { onClose(); navigate('/svc/engineer/customers'); }}
                testid="engineer-settings-customers-row"
              />
            </div>
          </section>

          {/* Support */}
          <section data-testid="engineer-settings-section-support">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">Help</p>
            <Row
              icon={LifeBuoy}
              accent="#0284c7"
              title="Support"
              subtitle="Chat with the GymAxis team or browse the help centre."
              onClick={() => { onClose(); navigate('/support'); }}
              testid="engineer-settings-support-row"
            />
          </section>

          {/* Account */}
          <section data-testid="engineer-settings-section-account">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">Account</p>
            <Row
              icon={LogOut}
              danger
              title="Sign out"
              subtitle="End your session on this device."
              onClick={handleSignOut}
              testid="engineer-settings-signout-row"
              right={<ChevronRight size={16} className="text-rose-400 flex-shrink-0" />}
            />
          </section>
        </div>

        <footer className="px-4 py-3 border-t border-slate-200 text-[11px] text-slate-400 text-center">
          GymAxis Engineer · v2
        </footer>
      </aside>
    </div>
  );
}
