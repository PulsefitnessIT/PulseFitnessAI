/* Master Admin — Onboarding Packets
 * Create / review / provision customer onboarding packets.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/App';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import {
  UserPlus, Clipboard, CheckCircle2, XCircle, Loader2, Send,
  Trash2, Copy, Building2, MapPin, Users, Wrench, Truck, FileText,
  ExternalLink, RefreshCw, Mail,
} from 'lucide-react';
import PreviewPanel from './PacketPreviewPanel';

const STATUS_META = {
  draft: { label: 'Draft', classes: 'bg-zinc-100 text-zinc-600' },
  submitted: { label: 'Submitted', classes: 'bg-amber-100 text-amber-700' },
  approved: { label: 'Approved', classes: 'bg-blue-100 text-blue-700' },
  provisioned: { label: 'Provisioned', classes: 'bg-emerald-100 text-emerald-700' },
  rejected: { label: 'Rejected', classes: 'bg-red-100 text-red-700' },
};

export default function AdminOnboardingPackets() {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [packets, setPackets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState(null);
  const [filterStatus, setFilterStatus] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/onboarding-packets`, { headers });
      setPackets(res.data.packets || []);
    } catch (e) {
      notify.error('Failed to load packets');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API]);

  useEffect(() => { load(); }, [load]);

  // Deep-link from "Review now" on the funnel: focus the targeted packet
  // immediately when it arrives in the list.
  useEffect(() => {
    const onFocus = (e) => {
      const id = e.detail?.packet_id;
      if (!id) return;
      const found = packets.find(p => p.id === id);
      if (found) {
        setSelected(found);
      } else {
        // Wait for next refresh to pick it up.
        load();
      }
    };
    window.addEventListener('onboarding-focus-packet', onFocus);
    return () => window.removeEventListener('onboarding-focus-packet', onFocus);
  }, [packets, load]);

  const filtered = filterStatus === 'all' ? packets : packets.filter(p => p.status === filterStatus);

  return (
    <div className="space-y-5" data-testid="admin-onboarding-packets">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold text-zinc-900">Customer Onboarding Packets</h2>
          <p className="text-sm text-zinc-500 mt-1">Create a self-service packet for a prospective customer. Share the link, they fill it in, you review and provision everything in one click.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={load} data-testid="btn-refresh-packets">
            <RefreshCw size={12} className="mr-1" /> Refresh
          </Button>
          <Button size="sm" onClick={() => setShowCreate(true)} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="btn-new-packet">
            <UserPlus size={14} className="mr-1" /> New Packet
          </Button>
        </div>
      </div>

      {/* Status filter */}
      <div className="flex gap-1">
        {['all', 'draft', 'submitted', 'approved', 'provisioned', 'rejected'].map(s => (
          <button key={s} onClick={() => setFilterStatus(s)}
            data-testid={`filter-${s}`}
            className={`px-3 py-1 rounded-md text-xs font-medium capitalize transition-colors ${filterStatus === s ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200'}`}>
            {s} {s === 'all' ? `(${packets.length})` : `(${packets.filter(p => p.status === s).length})`}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20"><Loader2 className="animate-spin text-zinc-400" /></div>
      ) : filtered.length === 0 ? (
        <Card className="p-10 text-center border-zinc-200">
          <Clipboard size={28} className="text-zinc-300 mx-auto mb-2" />
          <p className="text-sm text-zinc-500">No packets {filterStatus !== 'all' && `with status "${filterStatus}"`}.</p>
        </Card>
      ) : (
        <div className="grid gap-3">
          {filtered.map(p => (
            <PacketCard key={p.id} packet={p} onOpen={() => setSelected(p)} />
          ))}
        </div>
      )}

      {showCreate && <CreatePacketDialog API={API} headers={headers} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
      {selected && <PacketDetailDialog API={API} headers={headers} packet={selected} onClose={() => setSelected(null)} onChanged={() => { setSelected(null); load(); }} />}
    </div>
  );
}

function PacketCard({ packet, onOpen }) {
  const meta = STATUS_META[packet.status] || STATUS_META.draft;
  const c = packet.counts || {};
  return (
    <Card className="p-5 border-zinc-200 hover:border-zinc-300 transition-colors" data-testid={`packet-card-${packet.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-zinc-900 truncate">{packet.customer_display_name || packet.organisation?.legal_name || 'Untitled'}</h3>
            <Badge className={meta.classes}>{meta.label}</Badge>
            <Badge className="bg-blue-100 text-blue-700 capitalize">{packet.target_tier}</Badge>
            {packet.crm_company_id && <Badge className="bg-violet-100 text-violet-700">CRM linked</Badge>}
            {packet.last_sent_at && <Badge className="bg-sky-100 text-sky-700"><Mail size={10} className="mr-1 inline" />Invite sent</Badge>}
          </div>
          <p className="text-xs text-zinc-500 mt-1">Created {new Date(packet.created_at).toLocaleString()} by {packet.created_by_name}</p>
          <div className="flex items-center gap-4 mt-2 text-xs text-zinc-600">
            <span className="flex items-center gap-1"><MapPin size={10} /> {c.sites || 0} sites</span>
            <span className="flex items-center gap-1"><Users size={10} /> {c.staff || 0} staff</span>
            <span className="flex items-center gap-1"><Wrench size={10} /> {c.equipment || 0} equipment</span>
            <span className="flex items-center gap-1"><Truck size={10} /> {c.suppliers || 0} suppliers</span>
            <span className="flex items-center gap-1"><FileText size={10} /> {c.contracts || 0} contracts</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => { navigator.clipboard.writeText(packet.share_url); notify.success('Share link copied'); }} data-testid={`btn-copy-link-${packet.id}`}>
            <Copy size={12} className="mr-1" /> Link
          </Button>
          <Button size="sm" onClick={onOpen} data-testid={`btn-open-packet-${packet.id}`}>Open</Button>
        </div>
      </div>
    </Card>
  );
}

function CreatePacketDialog({ API, headers, onClose, onCreated }) {
  const [name, setName] = useState('');
  const [tier, setTier] = useState('pro');
  const [crmCompanies, setCrmCompanies] = useState([]);
  const [selectedCompany, setSelectedCompany] = useState('');
  const [creating, setCreating] = useState(false);
  const [isTrial, setIsTrial] = useState(true);
  const [trialDuration, setTrialDuration] = useState(14);

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${API}/onboarding-packets/crm/companies`, { headers });
        setCrmCompanies(res.data.companies || []);
      } catch { /* optional */ }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, []);

  const submit = async () => {
    setCreating(true);
    try {
      const res = await axios.post(`${API}/onboarding-packets`, {
        customer_display_name: name,
        target_tier: tier,
        crm_company_id: selectedCompany || null,
        is_trial: isTrial,
        trial_duration_days: isTrial ? trialDuration : null,
      }, { headers });
      notify.success('Packet created');
      // Copy link to clipboard
      if (res.data.share_url) navigator.clipboard.writeText(res.data.share_url);
      onCreated();
    } catch (e) {
      notifyApiError(notify, e, 'Creation failed');
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent data-testid="create-packet-dialog">
        <DialogHeader><DialogTitle>New onboarding packet</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div>
            <Label className="text-xs font-semibold uppercase tracking-wider">Customer name</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Tottenham Green Leisure Centre" data-testid="create-packet-name" />
          </div>
          <div>
            <Label className="text-xs font-semibold uppercase tracking-wider">Target tier</Label>
            <select className="w-full h-10 rounded-md border border-zinc-200 px-3 text-sm mt-1" value={tier} onChange={e => setTier(e.target.value)} data-testid="create-packet-tier">
              <option value="starter">Pulse Fitness Starter</option>
              <option value="pro">Pulse Fitness Pro</option>
              <option value="enterprise">Pulse Fitness Enterprise</option>
            </select>
          </div>
          <div>
            <Label className="text-xs font-semibold uppercase tracking-wider">Prefill from CRM company (optional)</Label>
            <select className="w-full h-10 rounded-md border border-zinc-200 px-3 text-sm mt-1" value={selectedCompany} onChange={e => setSelectedCompany(e.target.value)} data-testid="create-packet-crm">
              <option value="">— None —</option>
              {crmCompanies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <p className="text-[11px] text-zinc-400 mt-1">Pulls org details, sites and contacts from the matching CRM record.</p>
          </div>

          {/* Trial */}
          <div className="border-t border-zinc-200 pt-3">
            <label className="flex items-start gap-2 cursor-pointer">
              <input type="checkbox" checked={isTrial} onChange={e => setIsTrial(e.target.checked)} className="mt-1" data-testid="create-packet-trial" />
              <div className="flex-1">
                <p className="text-sm font-medium text-zinc-900">Start as free trial</p>
                <p className="text-[11px] text-zinc-500">Customer gets full Pro access for a fixed period, then hard-locks until they upgrade.</p>
              </div>
            </label>
            {isTrial && (
              <div className="mt-2 flex items-center gap-2" data-testid="trial-duration-block">
                <Label className="text-xs text-zinc-600">Duration:</Label>
                <Input type="number" min={1} max={90} value={trialDuration}
                  onChange={e => setTrialDuration(Number(e.target.value))}
                  className="w-20 h-8 text-xs" data-testid="create-packet-trial-days" />
                <span className="text-xs text-zinc-500">days (max 90)</span>
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={creating} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="btn-submit-create">
            {creating ? <Loader2 size={14} className="animate-spin mr-1" /> : <Send size={14} className="mr-1" />}
            Create & copy link
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PacketDetailDialog({ API, headers, packet: initialPacket, onClose, onChanged }) {
  const [packet, setPacket] = useState(initialPacket);
  const [provisioning, setProvisioning] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showReject, setShowReject] = useState(false);
  const [showSendEmail, setShowSendEmail] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailRecipient, setEmailRecipient] = useState('');
  const [emailRecipientName, setEmailRecipientName] = useState('');
  const [previewReady, setPreviewReady] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/onboarding-packets/${packet.id}`, { headers });
      setPacket(res.data);
    } catch { /* noop */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [packet.id]);

  useEffect(() => { refresh(); }, [refresh]);

  const doProvision = async () => {
    setProvisioning(true);
    try {
      const res = await axios.post(`${API}/onboarding-packets/${packet.id}/provision`, {}, { headers });
      notify.success(`Provisioned! Org ID: ${res.data.organization_id?.slice(0, 8)}…`);
      onChanged();
    } catch (e) {
      const d = e.response?.data?.detail;
      const msg = typeof d === 'object' ? (d.errors || []).join(' • ') : (d || 'Provision failed');
      notify.error(msg);
    } finally {
      setProvisioning(false);
    }
  };

  const doReject = async () => {
    try {
      await axios.post(`${API}/onboarding-packets/${packet.id}/reject`, { reason: rejectReason }, { headers });
      notify.success('Rejected');
      onChanged();
    } catch { notify.error('Reject failed'); }
  };

  const doDelete = async () => {
    if (!window.confirm('Delete this packet?')) return;
    try {
      await axios.delete(`${API}/onboarding-packets/${packet.id}`, { headers });
      notify.success('Deleted');
      onChanged();
    } catch (e) { notifyApiError(notify, e, 'Delete failed'); }
  };

  const doSendEmail = async () => {
    setSendingEmail(true);
    try {
      const res = await axios.post(`${API}/onboarding-packets/${packet.id}/send-email`,
        { email: emailRecipient || undefined, recipient_name: emailRecipientName || undefined },
        { headers });
      notify.success(`Sent to ${res.data.sent_to}`);
      setShowSendEmail(false);
      setEmailRecipient(''); setEmailRecipientName('');
      await refresh();
    } catch (e) {
      notifyApiError(notify, e, 'Email send failed');
    } finally {
      setSendingEmail(false);
    }
  };

  const openSendEmail = () => {
    setEmailRecipient(packet.organisation?.primary_contact_email || '');
    setEmailRecipientName(packet.organisation?.primary_contact_name || '');
    setShowSendEmail(true);
  };

  const meta = STATUS_META[packet.status] || STATUS_META.draft;
  const canProvision = packet.status === 'submitted' || packet.status === 'approved' || packet.status === 'draft';

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="packet-detail-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Building2 size={18} />
            {packet.customer_display_name || packet.organisation?.legal_name || 'Untitled'}
            <Badge className={meta.classes}>{meta.label}</Badge>
          </DialogTitle>
        </DialogHeader>

        {/* Share link */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-center gap-2">
          <Mail size={14} className="text-blue-600 flex-shrink-0" />
          <code className="flex-1 text-[11px] font-mono text-blue-900 truncate" data-testid="packet-share-url">{packet.share_url}</code>
          <Button size="sm" variant="outline" onClick={() => { navigator.clipboard.writeText(packet.share_url); notify.success('Copied'); }}>
            <Copy size={12} />
          </Button>
          <Button size="sm" variant="outline" onClick={() => window.open(packet.share_url, '_blank')}>
            <ExternalLink size={12} />
          </Button>
          {packet.status !== 'provisioned' && (
            <Button size="sm" onClick={openSendEmail} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="btn-send-to-customer">
              <Send size={12} className="mr-1" /> Send to customer
            </Button>
          )}
        </div>

        {/* Send-email panel */}
        {showSendEmail && (
          <div className="mt-3 border border-blue-200 bg-blue-50/50 rounded-lg p-4" data-testid="send-email-panel">
            <div className="flex items-center gap-2 mb-3">
              <Send size={14} className="text-blue-600" />
              <h4 className="text-sm font-semibold text-zinc-900">Send onboarding invitation</h4>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs font-semibold uppercase tracking-wider text-zinc-600">Recipient email</Label>
                <Input type="email" value={emailRecipient} onChange={e => setEmailRecipient(e.target.value)} placeholder="contact@customer.com" className="mt-1" data-testid="send-email-recipient" />
              </div>
              <div>
                <Label className="text-xs font-semibold uppercase tracking-wider text-zinc-600">Recipient name (optional)</Label>
                <Input value={emailRecipientName} onChange={e => setEmailRecipientName(e.target.value)} placeholder="Jane Doe" className="mt-1" />
              </div>
            </div>
            <p className="text-[11px] text-zinc-500 mt-2">A branded invite with the onboarding link will be sent via Resend. Recipient sees the email as from your sender domain.</p>
            <div className="flex justify-end gap-2 mt-3">
              <Button size="sm" variant="outline" onClick={() => setShowSendEmail(false)}>Cancel</Button>
              <Button size="sm" onClick={doSendEmail} disabled={sendingEmail || !emailRecipient} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="btn-send-email-confirm">
                {sendingEmail ? <Loader2 size={12} className="animate-spin mr-1" /> : <Send size={12} className="mr-1" />}
                Send invitation
              </Button>
            </div>
          </div>
        )}

        {/* Last sent status */}
        {packet.last_sent_at && !showSendEmail && (
          <div className="mt-2 text-xs text-zinc-500 flex items-center gap-2" data-testid="last-sent-status">
            <CheckCircle2 size={12} className="text-emerald-500" />
            Last sent to <strong className="text-zinc-700">{packet.last_sent_to}</strong> on {new Date(packet.last_sent_at).toLocaleString()}
            {(packet.email_sends?.length || 0) > 1 && <span>· {packet.email_sends.length} total sends</span>}
          </div>
        )}

        {/* Summary */}
        <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mt-3">
          <SummaryPill icon={MapPin} label="Sites" count={(packet.sites || []).length} />
          <SummaryPill icon={Users} label="Staff" count={(packet.staff || []).length} />
          <SummaryPill icon={Wrench} label="Equipment" count={(packet.equipment || []).length} />
          <SummaryPill icon={Truck} label="Suppliers" count={(packet.suppliers || []).length} />
          <SummaryPill icon={FileText} label="Contracts" count={(packet.contracts || []).length} />
          <SummaryPill icon={Building2} label="Tier" textValue={packet.target_tier} />
        </div>

        {/* Provision result */}
        {packet.status === 'provisioned' && packet.provision_summary && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 mt-3 text-sm text-emerald-800">
            <p className="font-semibold flex items-center gap-2"><CheckCircle2 size={14} /> Provisioned</p>
            <p className="mt-1">Organization ID: <code className="text-xs font-mono">{packet.provisioned_organization_id}</code></p>
            <p className="mt-1 text-xs">Created: {Object.entries(packet.provision_summary).map(([k, v]) => `${v} ${k.replace('_ids', '')}`).join(' · ')}</p>
          </div>
        )}

        {/* Detail preview */}
        <div className="mt-4 space-y-3">
          <DetailSection title="Organisation" items={[
            { label: 'Legal name', value: packet.organisation?.legal_name || '—' },
            { label: 'Trading name', value: packet.organisation?.trading_name || '—' },
            { label: 'VAT number', value: packet.organisation?.vat_number || '—' },
            { label: 'Contact', value: `${packet.organisation?.primary_contact_name || ''} (${packet.organisation?.primary_contact_email || '—'})` },
            { label: 'Billing postcode', value: packet.organisation?.billing_postcode || '—' },
          ]} />
          {(packet.sites || []).length > 0 && (
            <DetailListSection title={`Sites (${packet.sites.length})`} rows={packet.sites.map(s => `${s.name} — ${s.postcode}`)} />
          )}
          {(packet.staff || []).length > 0 && (
            <DetailListSection title={`Staff (${packet.staff.length})`} rows={packet.staff.map(m => `${m.full_name} <${m.email}> — ${m.role}`)} />
          )}
          {(packet.equipment || []).length > 0 && (
            <DetailListSection title={`Equipment (${packet.equipment.length})`} rows={packet.equipment.slice(0, 10).map(e => `${e.equipment_type || e.name} — ${e.brand} ${e.model} (${e.serial_number})`)} more={packet.equipment.length - 10} />
          )}
        </div>

        {showReject && (
          <div className="mt-3 border border-red-200 rounded-lg p-3 bg-red-50">
            <Label className="text-xs">Reason for rejection</Label>
            <Textarea rows={2} value={rejectReason} onChange={e => setRejectReason(e.target.value)} data-testid="reject-reason" />
            <div className="flex justify-end gap-2 mt-2">
              <Button size="sm" variant="outline" onClick={() => setShowReject(false)}>Cancel</Button>
              <Button size="sm" onClick={doReject} className="bg-red-600 hover:bg-red-700 text-white">Confirm reject</Button>
            </div>
          </div>
        )}

        {/* Ready-to-go preview panel */}
        {packet.status !== 'provisioned' && packet.status !== 'rejected' && (
          <div className="mt-4">
            <PreviewPanel API={API} headers={headers} packetId={packet.id} status={packet.status} onReadyChange={setPreviewReady} />
          </div>
        )}

        <DialogFooter className="gap-2 flex-wrap">
          {packet.status !== 'provisioned' && (
            <Button variant="outline" onClick={doDelete} size="sm" data-testid="btn-delete-packet">
              <Trash2 size={12} className="mr-1 text-red-500" /> Delete
            </Button>
          )}
          {packet.status !== 'provisioned' && packet.status !== 'rejected' && (
            <Button variant="outline" onClick={() => setShowReject(true)} size="sm">
              <XCircle size={12} className="mr-1" /> Reject
            </Button>
          )}
          {canProvision && packet.status !== 'provisioned' && (
            <Button onClick={doProvision} disabled={provisioning || !previewReady}
              className="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white"
              data-testid="btn-provision"
              title={!previewReady ? 'Fix validation errors first' : ''}>
              {provisioning ? <Loader2 size={14} className="animate-spin mr-1" /> : <CheckCircle2 size={14} className="mr-1" />}
              Provision workspace
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SummaryPill({ icon: Icon, label, count, textValue }) {
  return (
    <div className="border border-zinc-200 rounded-md px-2 py-1.5 bg-zinc-50 flex items-center gap-1.5">
      <Icon size={12} className="text-zinc-400" />
      <span className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</span>
      <span className="ml-auto text-sm font-bold text-zinc-900 tabular-nums">{textValue || count || 0}</span>
    </div>
  );
}

function DetailSection({ title, items }) {
  return (
    <div className="border border-zinc-200 rounded-lg p-3">
      <h4 className="text-xs font-semibold text-zinc-700 uppercase tracking-wider mb-2">{title}</h4>
      <dl className="grid grid-cols-2 gap-2 text-xs">
        {items.map(i => (
          <React.Fragment key={i.label}>
            <dt className="text-zinc-500">{i.label}</dt>
            <dd className="text-zinc-900 font-medium truncate">{i.value}</dd>
          </React.Fragment>
        ))}
      </dl>
    </div>
  );
}

function DetailListSection({ title, rows, more }) {
  return (
    <div className="border border-zinc-200 rounded-lg p-3">
      <h4 className="text-xs font-semibold text-zinc-700 uppercase tracking-wider mb-2">{title}</h4>
      <ul className="text-xs text-zinc-700 space-y-1 list-disc list-inside">
        {rows.map((r, i) => <li key={i}>{r}</li>)}
        {more > 0 && <li className="text-zinc-400">…and {more} more</li>}
      </ul>
    </div>
  );
}
