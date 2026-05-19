/**
 * MODDIOContractModal — HQ-side DIO (Defence Infrastructure Organisation)
 * contract drawer.
 *
 * MOD HQ users (mod_org / mod_branch) set or update the DIO contract
 * reference + escalation contact for a specific child site. Once set,
 * site-level users can flag faults with the "Report to DIO" button on
 * the fault card and the fault is auto-emailed to the configured
 * contact.
 *
 * Endpoints used:
 *   • GET  /api/mod/pro/sites/{site_id}/dio-contract
 *   • PUT  /api/mod/pro/sites/{site_id}/dio-contract
 *
 * Iter 216h117 — Closing P1.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { X, ShieldCheck, Loader2, Save } from 'lucide-react';
import { notify } from '@/components/notifications';

export default function MODDIOContractModal({ site, API, onClose }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [contract, setContract] = useState({
    dio_contract_ref: '',
    dio_contact_name: '',
    dio_contact_email: '',
  });
  const [updatedAt, setUpdatedAt] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(
          `${API}/mod/pro/sites/${site.id}/dio-contract`,
          { headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } },
        );
        if (!alive) return;
        setContract({
          dio_contract_ref: r.data.dio_contract_ref || '',
          dio_contact_name: r.data.dio_contact_name || '',
          dio_contact_email: r.data.dio_contact_email || '',
        });
        setUpdatedAt(r.data.dio_updated_at || null);
      } catch (e) {
        notify.error('Could not load DIO contract', e?.response?.data?.detail || 'Network error');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [API, site.id]);

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        dio_contract_ref: contract.dio_contract_ref.trim() || null,
        dio_contact_name: contract.dio_contact_name.trim() || null,
        dio_contact_email: contract.dio_contact_email.trim() || null,
      };
      const r = await axios.put(
        `${API}/mod/pro/sites/${site.id}/dio-contract`,
        payload,
        { headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } },
      );
      setUpdatedAt(r.data.dio_updated_at || new Date().toISOString());
      notify.success('DIO contract saved', `${site.name} can now escalate faults to DIO.`);
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || 'Could not update contract');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"
      data-testid="mod-dio-contract-modal"
    >
      <div
        className="w-full max-w-lg rounded-2xl border shadow-2xl"
        style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
      >
        <div
          className="flex items-start justify-between gap-3 px-5 py-4 border-b"
          style={{ borderColor: 'var(--theme-border)' }}
        >
          <div>
            <div
              className="text-[10px] font-extrabold uppercase tracking-[0.2em]"
              style={{ color: 'var(--color-brand-cyan-hover)' }}
            >
              <ShieldCheck size={11} className="inline mr-1" /> DIO escalation contract
            </div>
            <h3
              className="text-base font-extrabold tracking-tight mt-1"
              style={{ color: 'var(--theme-text)' }}
              data-testid="mod-dio-modal-title"
            >
              {site.name}
            </h3>
            <p
              className="text-[11px] mt-0.5"
              style={{ color: 'var(--theme-text-muted)' }}
            >
              Set the Defence Infrastructure Organisation contract reference and the named contact who receives escalated faults.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-full hover:bg-[var(--theme-hover-bg)]"
            data-testid="mod-dio-modal-close"
          >
            <X size={16} style={{ color: 'var(--theme-text-muted)' }} />
          </button>
        </div>

        {loading ? (
          <div className="py-12 grid place-items-center" data-testid="mod-dio-loading">
            <Loader2 className="animate-spin" size={20} style={{ color: 'var(--theme-text-muted)' }} />
          </div>
        ) : (
          <div className="p-5 space-y-4">
            <div>
              <label
                className="block text-[11px] font-extrabold uppercase tracking-wider mb-1.5"
                style={{ color: 'var(--theme-text-muted)' }}
              >
                Contract reference
              </label>
              <input
                type="text"
                value={contract.dio_contract_ref}
                maxLength={120}
                onChange={(e) => setContract({ ...contract, dio_contract_ref: e.target.value })}
                placeholder="e.g. DIO/NHE/2026/14887"
                className="w-full px-3 py-2 rounded-md border text-sm font-mono"
                style={{
                  background: 'var(--theme-bg)',
                  borderColor: 'var(--theme-border)',
                  color: 'var(--theme-text)',
                }}
                data-testid="mod-dio-contract-ref"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label
                  className="block text-[11px] font-extrabold uppercase tracking-wider mb-1.5"
                  style={{ color: 'var(--theme-text-muted)' }}
                >
                  Contact name
                </label>
                <input
                  type="text"
                  value={contract.dio_contact_name}
                  maxLength={120}
                  onChange={(e) => setContract({ ...contract, dio_contact_name: e.target.value })}
                  placeholder="e.g. Maj. Lewis Banks"
                  className="w-full px-3 py-2 rounded-md border text-sm"
                  style={{
                    background: 'var(--theme-bg)',
                    borderColor: 'var(--theme-border)',
                    color: 'var(--theme-text)',
                  }}
                  data-testid="mod-dio-contact-name"
                />
              </div>
              <div>
                <label
                  className="block text-[11px] font-extrabold uppercase tracking-wider mb-1.5"
                  style={{ color: 'var(--theme-text-muted)' }}
                >
                  Contact email
                </label>
                <input
                  type="email"
                  value={contract.dio_contact_email}
                  onChange={(e) => setContract({ ...contract, dio_contact_email: e.target.value })}
                  placeholder="dio.estates@mod.gov.uk"
                  className="w-full px-3 py-2 rounded-md border text-sm"
                  style={{
                    background: 'var(--theme-bg)',
                    borderColor: 'var(--theme-border)',
                    color: 'var(--theme-text)',
                  }}
                  data-testid="mod-dio-contact-email"
                />
              </div>
            </div>

            <div
              className="rounded-md border p-3 text-[11px] leading-relaxed"
              style={{
                background: 'rgba(25,205,255,0.06)',
                borderColor: 'rgba(25,205,255,0.25)',
                color: 'var(--theme-text-muted)',
              }}
            >
              Once a contact email is saved, site users see a <strong>Report to DIO</strong> button on every fault card. The fault is emailed to <code>{contract.dio_contact_email || 'the configured contact'}</code> with full ticket detail, asset serial, and any escalation note.
            </div>

            {updatedAt ? (
              <div className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }} data-testid="mod-dio-updated-at">
                Last updated {new Date(updatedAt).toLocaleString()}
              </div>
            ) : null}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-2 text-xs font-bold rounded-md hover:bg-[var(--theme-hover-bg)]"
                style={{ color: 'var(--theme-text-muted)' }}
                data-testid="mod-dio-cancel"
              >
                Close
              </button>
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-extrabold rounded-md disabled:opacity-60"
                style={{ background: 'var(--color-brand-cyan)', color: '#001119' }}
                data-testid="mod-dio-save"
              >
                {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                Save contract
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
