import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import axios from 'axios';
import { notify } from '@/components/notifications';
import {
 FileText, Upload, Send, Plus, Trash2,
 Paperclip, ExternalLink, ShoppingCart, Clock, CheckCircle, AlertCircle, Printer, Wrench, Loader2, CalendarDays, ShieldCheck, Phone, Mail,
 ChevronDown, ChevronUp, Receipt, Timer, AlertTriangle, Users,
} from 'lucide-react';
import SiconServicePanel from './SiconServicePanel';
import { MODDIOEscalateModal } from './MODPortal/MODDIOEscalateModal';
import FaultNotifiedCard from '@/components/faults/FaultNotifiedCard';
import GymCommentBody from '@/components/faults/GymCommentBody';

const IssueDetailPanel = ({ issue: issueProp, onUpdate, suppliers = [] }) => {
 const { API, user } = useAuth();
 const { _t } = useTranslation();
 const [issue, setIssue] = useState(issueProp);
 const [supplierRef, setSupplierRef] = useState(issueProp.supplier_ref || '');
 const [attachments, setAttachments] = useState(issueProp.attachments || []);
 const [uploading, setUploading] = useState(false);
 // Iter 216h263 — dedicated quote uploader has its own busy flag so
 // the generic job-sheet button doesn't visually grey out alongside it.
 const [uploadingQuote, setUploadingQuote] = useState(false);
 // Iter 216h263 — AI Triage collapsed by default, owners can expand.
 const [showAiTriage, setShowAiTriage] = useState(false);
 const [showPODialog, setShowPODialog] = useState(false);
 const [purchaseOrders, setPurchaseOrders] = useState([]);
 const [poForm, setPOForm] = useState({
 po_number: '',
 supplier_name: issueProp.supplier || '',
 supplier_email: '',
 delivery_address: '',
 notes: '',
 items: [{ description: '', quantity: 1, unit_price: 0 }]
 });
 const [poLoading, setPOLoading] = useState(false);
 const [poDefaults, setPODefaults] = useState(null);
 const [commentText, setCommentText] = useState('');
 const [sendingComment, setSendingComment] = useState(false);
 const [showFullHistory, setShowFullHistory] = useState(false);
 const [equipmentDoc, setEquipmentDoc] = useState(null);
 const [engineerDir, setEngineerDir] = useState([]);
 // Iter 216h137 — DIO contract context for MOD site users. Lets the
 // engineer see who the escalation will go to *before* they click.
 const [dioContract, setDioContract] = useState(null);

 // Iter 216k — replace the recurring `window.prompt()` toast for
 // missing supplier email with a proper styled dialog. Operators were
 // being asked every. single. time. they sent a message — now we
 // collect the email once, persist it on the supplier_case, and never
 // ask again. The dialog also remembers the pending action so the
 // operator's typed message isn't lost.
 const [supplierEmailDialog, setSupplierEmailDialog] = useState({
   open: false,
   email: '',
   pending: null, // 'gym-comment' | 'contact-supplier'
   submitting: false,
 });
 const [dioModalOpen, setDioModalOpen] = useState(false);

 // Load full detail with supplier case data
 useEffect(() => {
 const loadFull = async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/issues/${issueProp.id}`, { headers: { Authorization: `Bearer ${token}` } });
 setIssue({ ...issueProp, ...res.data });
 setAttachments(res.data.attachments || issueProp.attachments || []);
 } catch { /* use prop data */ }
 };
 loadFull();
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: we depend on a primitive snapshot (e.g. `obj?.id`) to avoid the object-identity re-fire trap; the full object is read at call time.
 }, [issueProp.id, API]);

 // Iter 216h137 — Fetch DIO contract context for MOD site users.
 // Endpoint is read-only and scoped to the user's own site.
 useEffect(() => {
 if (user?.account_type !== 'mod_site') return;
 const token = localStorage.getItem('token');
 let alive = true;
 axios.get(`${API}/mod/site/dio-contract`,
            { headers: { Authorization: `Bearer ${token}` } })
   .then((r) => { if (alive) setDioContract(r.data); })
   .catch(() => { /* non-fatal */ });
 return () => { alive = false; };
 }, [user?.account_type, API]);

 // Pull equipment lineage + engineer directory once per card, only if Sicon linked
 useEffect(() => {
 if (!issue?.sicon_case_id) return;
 const token = localStorage.getItem('token');
 const hdr = { headers: { Authorization: `Bearer ${token}` } };
 const loadSiconContext = async () => {
 try {
 if (issue.serial_number) {
 const eqRes = await axios.get(`${API}/equipment?serial=${encodeURIComponent(issue.serial_number)}`, hdr);
 const match = (eqRes.data || []).find(e => e.serial_number === issue.serial_number);
 if (match) setEquipmentDoc(match);
 }
 } catch { /* optional */ }
 try {
 const engRes = await axios.get(`${API}/sicon/engineers`, hdr);
 setEngineerDir(engRes.data?.engineers || []);
 } catch { /* optional */ }
 };
 loadSiconContext();
 }, [issue?.sicon_case_id, issue?.serial_number, API]);

 // Fault-wizard photos (source "fault_photo") live in MOD storage and load
 // through the authenticated MOD media endpoint; uploads keep download_url.
 const attachmentUrl = (att) => {
 if (att?.source === 'fault_photo' && att.storage_path) {
 const tk = localStorage.getItem('token') || '';
 return `${API}/mod/site/attachments/serve?path=${encodeURIComponent(att.storage_path)}&token=${encodeURIComponent(tk)}`;
 }
 return att?.download_url || '';
 };

 const reloadDetail = async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/issues/${issueProp.id}`, { headers: { Authorization: `Bearer ${token}` } });
 setIssue({ ...issueProp, ...res.data });
 } catch { /* ignore */ }
 };

 useEffect(() => {
 loadPurchaseOrders();
 loadPODefaults();
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
 }, [issue.id]);

 useEffect(() => {
 // Auto-fill supplier email if supplier selected
 const match = suppliers.find(s => s.name === issue.supplier || s.name === poForm.supplier_name);
 if (match && !poForm.supplier_email) {
 setPOForm(f => ({ ...f, supplier_email: match.email || '' }));
 }
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: we depend on a primitive snapshot (e.g. `obj?.id`) to avoid the object-identity re-fire trap; the full object is read at call time.
 }, [poForm.supplier_name, suppliers]);

 const loadPurchaseOrders = async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/purchase-orders?issue_id=${issue.id}`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setPurchaseOrders(res.data.purchase_orders || []);
 } catch (err) {
 console.error('Failed to load POs:', err);
 }
 };

 const loadPODefaults = async () => {
 const token = localStorage.getItem('token');
 try {
 const [defaultsRes, orgRes, supplierRes] = await Promise.all([
 axios.get(`${API}/settings/po-defaults`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => ({ data: { defaults: {} } })),
 axios.get(`${API}/settings/org-details`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => ({ data: {} })),
 axios.get(`${API}/purchase-orders/supplier-lookup?equipment_serial=${encodeURIComponent(issue.serial_number || '')}&supplier_name=${encodeURIComponent(issue.supplier || '')}`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => ({ data: {} }))
 ]);
 const defs = defaultsRes.data?.defaults || {};
 const orgDetails = orgRes.data || {};
 const supplierLookup = supplierRes.data || {};
 setPODefaults(defs);
 // Auto-populate delivery address from org details and supplier email
 setPOForm(f => ({
 ...f,
 delivery_address: f.delivery_address || orgDetails.address || '',
 supplier_email: f.supplier_email || supplierLookup.supplier_email || '',
 supplier_name: f.supplier_name || supplierLookup.supplier_name || issue.supplier || '',
 }));
 } catch {}
 };

 // Auto-resolve the email of a supplier the fault was already dispatched to,
 // so 2-way comms is pre-wired to the notified supplier(s) and we NEVER ask
 // the operator to type an address that we already hold.
 const _resolveNotifiedSupplierEmail = () => {
   const c = issue.supplier_case?.supplier_email;
   if (c && c.includes('@')) return c;
   const recips = Array.isArray(issue.notified_recipients) ? issue.notified_recipients : [];
   const hit = recips.find((r) => (r?.email || '').includes('@'));
   if (hit) return hit.email;
   if ((issue.supplier_notified_email || '').includes('@')) return issue.supplier_notified_email;
   return '';
 };

 // Persist a resolved email onto the supplier_case (best-effort) so later
 // sends in this and future sessions don't re-resolve/re-prompt.
 const _persistCaseEmail = async (email) => {
   if (!issue.supplier_case?.token || !email) return;
   const tkn = localStorage.getItem('token');
   try {
     await axios.post(
       `${API}/supplier/case/${issue.supplier_case.token}/update-email`,
       { supplier_email: email },
       { headers: { Authorization: `Bearer ${tkn}` } },
     );
     setIssue((prev) => ({ ...prev, supplier_case: { ...(prev.supplier_case || {}), supplier_email: email } }));
   } catch { /* best effort */ }
 };

 const handleSendGymComment = async () => {
 if (!commentText.trim() || !issue.supplier_case?.token) return;

 // If the case has no email yet, auto-wire it from the supplier(s) the
 // fault was dispatched to. Only fall back to the manual dialog if we
 // genuinely hold no address anywhere.
 if (!issue.supplier_case?.supplier_email) {
   const resolved = _resolveNotifiedSupplierEmail();
   if (resolved) {
     await _persistCaseEmail(resolved);
   } else {
     setSupplierEmailDialog({ open: true, email: '', pending: 'gym-comment', submitting: false });
     return;
   }
 }
 await _sendGymComment();
 };

 const _sendGymComment = async () => {
 setSendingComment(true);
 const tkn = localStorage.getItem('token');
 try {
 const fd = new FormData();
 fd.append('message', commentText.trim());
 fd.append('author_name', issue.created_by_name || 'Site Staff');
 await axios.post(`${API}/supplier/case/${issue.supplier_case.token}/comments/gym`, fd, {
 headers: { Authorization: `Bearer ${tkn}`, 'Content-Type': 'multipart/form-data' },
 });
 setCommentText('');
 notify.success('Reply sent — supplier notified by email');
 reloadDetail();
 } catch { notify.error('Failed to send reply'); }
 setSendingComment(false);
 };

 const handleContactSupplier = async () => {
 if (!commentText.trim()) return;

 if (!issue.supplier_case?.supplier_email) {
   // Auto-wire to the supplier(s) the fault was sent to — no manual entry.
   const resolved = _resolveNotifiedSupplierEmail();
   if (resolved) {
     await _persistCaseEmail(resolved);
     await _contactSupplier(resolved);
     return;
   }
   setSupplierEmailDialog({ open: true, email: '', pending: 'contact-supplier', submitting: false });
   return;
 }
 await _contactSupplier('');
 };

 const _contactSupplier = async (overrideEmail) => {
 setSendingComment(true);
 const tkn = localStorage.getItem('token');
 try {
 const res = await axios.post(`${API}/issues/${issue.id}/contact-supplier`,
 { message: commentText.trim(), supplier_email: overrideEmail || '' },
 { headers: { Authorization: `Bearer ${tkn}` } },
 );
 setCommentText('');
 if (res.data.email_sent) {
 notify.success('Message sent — supplier notified by email');
 } else {
 notify.success('Message saved — share the Supplier Card link');
 }
 reloadDetail();
 if (onUpdate) onUpdate();
 } catch { notify.error('Failed to send message'); }
 setSendingComment(false);
 };

 const _confirmSupplierEmail = async () => {
   const email = (supplierEmailDialog.email || '').trim();
   if (!email || !email.includes('@')) {
     notify.error('Enter a valid email');
     return;
   }
   setSupplierEmailDialog((s) => ({ ...s, submitting: true }));
   const tkn = localStorage.getItem('token');
   // Persist on the supplier_case so we never ask again. Best-effort —
   // even if the persistence call fails we still let the message go
   // through with the email override.
   if (issue.supplier_case?.token) {
     try {
       await axios.post(
         `${API}/supplier/case/${issue.supplier_case.token}/update-email`,
         { supplier_email: email },
         { headers: { Authorization: `Bearer ${tkn}` } },
       );
       // Optimistic local state so subsequent sends in the same session don't re-prompt.
       setIssue((prev) => ({
         ...prev,
         supplier_case: { ...(prev.supplier_case || {}), supplier_email: email },
       }));
     } catch { /* best effort */ }
   }
   const pending = supplierEmailDialog.pending;
   setSupplierEmailDialog({ open: false, email: '', pending: null, submitting: false });
   if (pending === 'gym-comment') {
     await _sendGymComment();
   } else if (pending === 'contact-supplier') {
     await _contactSupplier(email);
   }
 };

 const handleSaveSupplierRef = async () => {
 const token = localStorage.getItem('token');
 try {
 await axios.patch(`${API}/issues/${issue.id}/details`, { supplier_ref: supplierRef }, {
 headers: { Authorization: `Bearer ${token}` }
 });
 notify.success('Supplier reference saved');
 } catch {
 notify.error('Failed to save');
 }
 };

 const handleFileUpload = async (e, kind = null) => {
 const file = e.target.files[0];
 if (!file) return;
 const isQuote = kind === 'quote';
 if (isQuote) setUploadingQuote(true); else setUploading(true);
 const token = localStorage.getItem('token');
 try {
 const formData = new FormData();
 formData.append('file', file);
 if (kind) formData.append('kind', kind);
 const res = await axios.post(`${API}/issues/${issue.id}/attachments`, formData, {
 headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
 });
 setAttachments([...attachments, res.data]);
 notify.success(isQuote ? 'Quote uploaded' : 'File uploaded');
 } catch {
 notify.error('Upload failed');
 } finally {
 if (isQuote) setUploadingQuote(false); else setUploading(false);
 e.target.value = '';
 }
 };

 const handleCreatePO = async () => {
 const validItems = poForm.items.filter(i => i.description.trim());
 if (validItems.length === 0) {
 notify.error('Add at least one line item');
 return;
 }
 setPOLoading(true);
 const token = localStorage.getItem('token');
 try {
 const res = await axios.post(`${API}/purchase-orders`, {
 issue_id: issue.id,
 ...poForm,
 items: validItems
 }, { headers: { Authorization: `Bearer ${token}` } });
 setPurchaseOrders([res.data, ...purchaseOrders]);
 setShowPODialog(false);
 notify.success(`Purchase Order ${res.data.po_number} created`);
 } catch {
 notify.error('Failed to create PO');
 } finally {
 setPOLoading(false);
 }
 };

 const handleSendPO = async (poId) => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.post(`${API}/purchase-orders/${poId}/send`, {}, {
 headers: { Authorization: `Bearer ${token}` }
 });
 notify.success(res.data.message);
 loadPurchaseOrders();
 } catch {
 notify.error('Failed to send PO');
 }
 };

 const handleViewPOPdf = async (poId) => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/purchase-orders/${poId}/pdf`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 const win = window.open('', '_blank');
 if (win) {
 win.document.write(res.data);
 win.document.close();
 }
 } catch {
 notify.error('Failed to load PO');
 }
 };

 const addLineItem = () => {
 setPOForm({ ...poForm, items: [...poForm.items, { description: '', quantity: 1, unit_price: 0 }] });
 };

 const updateLineItem = (idx, field, value) => {
 const items = [...poForm.items];
 items[idx] = { ...items[idx], [field]: value };
 setPOForm({ ...poForm, items });
 };

 const removeLineItem = (idx) => {
 setPOForm({ ...poForm, items: poForm.items.filter((_, i) => i !== idx) });
 };

 const poSubtotal = poForm.items.reduce((sum, i) => sum + (parseFloat(i.quantity) || 0) * (parseFloat(i.unit_price) || 0), 0);

 const _getSeverityColor = (sev) => {
 if (sev === 'low') return 'bg-green-500/20 text-green-400';
 if (sev === 'critical') return 'bg-red-500/20 text-red-400';
 return 'bg-yellow-500/20 text-yellow-400';
 };

 const _getStatusColor = (st) => {
 if (st === 'open') return 'bg-red-500/20 text-red-400';
 if (st === 'in_progress') return 'bg-yellow-500/20 text-yellow-400';
 if (st === 'resolved') return 'bg-green-500/20 text-green-400';
 return 'bg-gray-500/20 text-gray-400';
 };

 return (
 <div className="issue-detail-themed border-t border-[var(--theme-border)] p-5 bg-[rgb(var(--rgb-ink-alt)/0.5)] space-y-5" data-testid={`issue-detail-${issue.id}`}>
 <style>{`
 [data-portal="pulse"] .issue-detail-themed, .theme-gymaxis .issue-detail-themed { background: var(--theme-bg, var(--color-neutral-25)) !important; border-color: var(--theme-border, var(--color-border-alt)) !important; }
 [data-portal="pulse"] .issue-detail-themed .text-white, .theme-gymaxis .issue-detail-themed .text-white { color: var(--theme-text, #111) !important; }
 [data-portal="pulse"] .issue-detail-themed .text-\\[\\var(--color-text-muted)\\], .theme-gymaxis .issue-detail-themed .text-\\[\\var(--color-text-muted)\\] { color: var(--theme-text-muted, var(--color-text-faint-alt)) !important; }
 [data-portal="pulse"] .issue-detail-themed .bg-\\[\\var(--color-surface-dark-alt)\\], .theme-gymaxis .issue-detail-themed .bg-\\[\\var(--color-surface-dark-alt)\\] { background: var(--theme-surface, #fff) !important; }
 [data-portal="pulse"] .issue-detail-themed .bg-\\[\\var(--color-ink-alt)\\], .theme-gymaxis .issue-detail-themed .bg-\\[\\var(--color-ink-alt)\\] { background: var(--theme-bg, var(--color-neutral-100)) !important; }
 [data-portal="pulse"] .issue-detail-themed .bg-\\[\\var(--color-ink-alt)\\]\\/50, .theme-gymaxis .issue-detail-themed .bg-\\[\\var(--color-ink-alt)\\]\\/50 { background: var(--theme-bg, var(--color-neutral-25)) !important; }
 [data-portal="pulse"] .issue-detail-themed .border-white\\/10, .theme-gymaxis .issue-detail-themed .border-white\\/10 { border-color: var(--theme-border, var(--color-border-alt)) !important; }
 [data-portal="pulse"] .issue-detail-themed .border-white\\/5, .theme-gymaxis .issue-detail-themed .border-white\\/5 { border-color: var(--theme-border, var(--color-border-alt)) !important; }
 [data-portal="pulse"] .issue-detail-themed .border-t.border-white\\/10, .theme-gymaxis .issue-detail-themed .border-t.border-white\\/10 { border-color: var(--theme-border, var(--color-border-alt)) !important; }
 [data-portal="pulse"] .issue-detail-themed input, [data-portal="pulse"] .issue-detail-themed textarea, .theme-gymaxis .issue-detail-themed input, .theme-gymaxis .issue-detail-themed textarea { background: var(--theme-bg, #fff) !important; border-color: var(--theme-border, #d1d5db) !important; color: var(--theme-text, #111) !important; }
 `}</style>
 {/* Iter 216h263 — Supplier Reference / Job Number lifted to the
     top of the detail panel (above the Logged-by header) so it's
     the first thing the manager sees + fills in. Once populated
     it's also rendered on the fault list row. */}
 <div className="p-4 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg">
 <Label className="text-[var(--color-text-muted)] text-sm">Supplier Reference / Job Number</Label>
 <div className="flex items-center gap-2 mt-1">
 <Input
 value={supplierRef}
 onChange={(e) => setSupplierRef(e.target.value)}
 placeholder="e.g., JOB-2024-001"
 className="bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-white flex-1"
 data-testid={`supplier-ref-input-${issue.id}`}
 />
 <Button size="sm" onClick={handleSaveSupplierRef} className="bg-[var(--color-brand-blue)] text-white" data-testid={`save-ref-btn-${issue.id}`}>
 Save
 </Button>
 </div>
 </div>

 {/* Logged-by contact is intentionally NOT shown as a large card here —
     the site already knows who logged it (see the info grid below), and the
     reporter's email/phone is surfaced to suppliers/engineers on the supplier
     job card instead. */}

 {/* Info Grid */}
 <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
 <div>
 <span className="text-[var(--color-text-muted)]">Logged by</span>
 <p className="text-white font-medium">{issue.reporter_name || issue.created_by_name || 'Unknown'}</p>
 </div>
 <div>
 <span className="text-[var(--color-text-muted)]">Date & Time</span>
 <p className="text-white font-medium">{issue.created_at ? new Date(issue.created_at).toLocaleString() : 'N/A'}</p>
 </div>
 <div>
 <span className="text-[var(--color-text-muted)]">Supplier</span>
 <p className="text-white font-medium">{issue.supplier || 'Not assigned'}</p>
 </div>
 <div>
 <span className="text-[var(--color-text-muted)]">Resolution</span>
 <p className="text-white font-medium">
 {issue.status === 'resolved'
 ? (issue.resolved_by === 'gymaxis_ai' ? 'Self-fixed (AI guided)' : issue.resolved_by === 'engineer' ? 'Engineer callout' : 'Resolved')
 : issue.resolution_type === 'supplier' ? 'Awaiting supplier'
 : issue.resolution_type === 'engineer' ? 'Engineer requested'
 : issue.resolution_type === 'self_fix' ? 'Self-fix attempted'
 : 'In progress'}
 </p>
 </div>
 </div>

 {/* SLA tracker — MOD faults carry response/fix targets (different for
     overseas sites). Shows on-track / due-soon / breached at a glance. */}
 {issue.sla && (
 <div className={`p-4 rounded-xl border ${
   issue.sla.state === 'breached' ? 'bg-rose-500/5 border-rose-500/30'
   : issue.sla.state === 'due_soon' ? 'bg-amber-500/5 border-amber-500/30'
   : issue.sla.state === 'met' ? 'bg-emerald-500/5 border-emerald-500/25'
   : 'bg-sky-500/5 border-sky-500/25'
 }`} data-testid={`issue-sla-${issue.id}`}>
 <div className="flex items-center justify-between gap-2 mb-2">
 <div className="flex items-center gap-2">
 <Timer size={14} className={
   issue.sla.state === 'breached' ? 'text-rose-400'
   : issue.sla.state === 'due_soon' ? 'text-amber-400'
   : issue.sla.state === 'met' ? 'text-emerald-400' : 'text-sky-400'} />
 <span className="text-[var(--color-text-muted)] text-xs uppercase tracking-wide">SLA · {issue.sla.is_overseas ? 'Overseas' : 'UK'} target</span>
 </div>
 <Badge className={
   issue.sla.state === 'breached' ? 'bg-rose-500/20 text-rose-300'
   : issue.sla.state === 'due_soon' ? 'bg-amber-500/20 text-amber-300'
   : issue.sla.state === 'met' ? 'bg-emerald-500/20 text-emerald-300'
   : 'bg-sky-500/20 text-sky-300'} data-testid={`issue-sla-state-${issue.id}`}>
 {issue.sla.state === 'breached' ? 'SLA breached'
   : issue.sla.state === 'due_soon' ? 'Due soon'
   : issue.sla.state === 'met' ? 'Within SLA' : 'On track'}
 </Badge>
 </div>
 <div className="grid grid-cols-2 gap-3 text-sm">
 <div>
 <span className="text-[var(--color-text-muted)] text-xs">Response ({issue.sla.response_hours}h)</span>
 <p className={`font-medium ${issue.sla.response_breached ? 'text-rose-300' : 'text-white'}`} data-testid={`issue-sla-response-${issue.id}`}>
 {issue.sla.response_met ? 'Met' : issue.sla.response_remaining_label}
 </p>
 </div>
 <div>
 <span className="text-[var(--color-text-muted)] text-xs">Fix ({issue.sla.fix_hours}h)</span>
 <p className={`font-medium ${issue.sla.fix_breached ? 'text-rose-300' : 'text-white'}`} data-testid={`issue-sla-fix-${issue.id}`}>
 {issue.sla.fix_met ? 'Met' : issue.sla.fix_remaining_label}
 </p>
 </div>
 </div>
 </div>
 )}

 {/* One merged "Notified" card — every recipient with an inbox-delivery tick. */}
 <FaultNotifiedCard issue={issue} API={API} />

 {/* Iter 216h57 — Replaced the blue Supplier Fault Card deep-link
     with a prominent Engineer Visit panel. The Supplier-Card link
     still lives inside the Supplier Communication card below, so
     removing the duplicate banner here de-clutters the detail view. */}
 {issue.supplier_case?.scheduled_date && (
 <div className="flex items-center justify-between gap-3 p-4 rounded-xl bg-purple-500/10 border border-purple-500/20" data-testid={`engineer-visit-banner-${issue.id}`}>
 <div className="flex items-start gap-3 min-w-0">
 <CalendarDays size={18} className="text-purple-400 shrink-0 mt-0.5" />
 <div className="min-w-0">
 <p className="text-purple-400 text-xs font-semibold uppercase tracking-wider">Engineer Visit Scheduled</p>
 <p className="text-white text-base font-semibold mt-0.5">
 {new Date(issue.supplier_case.scheduled_date).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
 </p>
 {issue.supplier_case.engineer_name && (
 <p className="text-[var(--color-text-muted)] text-xs mt-0.5">Engineer: {issue.supplier_case.engineer_name}</p>
 )}
 </div>
 </div>
 {issue.supplier_case?.token && (
 <Button
 size="sm" variant="outline"
 onClick={() => window.open(`/supplier/case/${issue.supplier_case.token}?view=site`, '_blank', 'noopener')}
 className="border-purple-500/40 text-purple-400 hover:bg-purple-500/20 text-xs shrink-0"
 data-testid={`engineer-visit-reschedule-${issue.id}`}
 >
 Reschedule
 </Button>
 )}
 </div>
 )}

 {/* Full Description */}
 <div>
 <span className="text-[var(--color-text-muted)] text-sm">Full Description</span>
 <p className="text-white mt-1">{issue.issue_description}</p>
 </div>

 {/* QR Scan Source + Reporter Info */}
 {issue.source === 'qr_scan' && (
 <div className="flex flex-wrap items-center gap-2">
 <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)] text-xs" data-testid="qr-source-badge">Reported via QR Scan</Badge>
 {issue.reporter_name && <span className="text-[var(--color-text-muted)] text-xs">by {issue.reporter_name}</span>}
 </div>
 )}

 {/* Fault Photo */}
 {issue.photo_url && (
 <div data-testid="issue-photo-section">
 <span className="text-[var(--color-text-muted)] text-sm">Fault Photo</span>
 <div className="mt-1 rounded-lg overflow-hidden border border-[var(--theme-border)]">
 <img src={issue.photo_url} alt="Fault" className="w-full max-h-64 object-cover" />
 </div>
 </div>
 )}

 {/* Steps Taken (if present) */}
 {issue.steps_taken && (
 <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
 <span className="text-amber-400 text-sm font-medium">Steps Already Tried:</span>
 <p className="text-white text-sm mt-1">{issue.steps_taken}</p>
 </div>
 )}

 {!issue.engineer_report && issue.resolution_note && (
 <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
 <span className="text-green-400 text-sm font-medium">Fix Notes:</span>
 <p className="text-white text-sm mt-1">{issue.resolution_note}</p>
 </div>
 )}

 {issue.engineer_report && (
 <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg space-y-1" data-testid="issue-engineer-report">
 <div className="flex items-center justify-between gap-2 flex-wrap">
 <span className="text-green-600 text-sm font-bold">Engineer's report</span>
 <span className="text-[11px] text-slate-700 font-semibold" data-testid="issue-engineer-report-meta">
 {issue.engineer_report.engineer_name} · {new Date(issue.engineer_report.completed_at).toLocaleString()}
 </span>
 </div>
 <p className="text-sm whitespace-pre-wrap" data-testid="issue-engineer-report-summary">{issue.engineer_report.summary}</p>
 {(issue.engineer_report.notes || []).length > 0 && (
 <ul className="mt-1 space-y-1 border-t border-green-500/20 pt-1.5" data-testid="issue-engineer-report-notes">
 {issue.engineer_report.notes.map((n, i) => (
 <li key={`${n.at}-${i}`} className="text-xs" data-testid={`issue-engineer-note-${i}`}>
 <span className="font-semibold text-slate-700">{n.by}{n.at ? ` · ${new Date(n.at).toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}` : ''}:</span> {n.body}
 </li>
 ))}
 </ul>
 )}

 {issue.engineer_report.signed_by_name && (
 <p className="text-xs text-slate-700 font-semibold" data-testid="issue-engineer-report-signed">Signed off by {issue.engineer_report.signed_by_name}</p>
 )}
 </div>
 )}

 {(issue.timeline || []).length > 0 && (
 <div className="p-3 rounded-lg border border-[var(--theme-border)]" data-testid="issue-engineer-timeline">
 <span className="text-sm font-bold">Engineer progress</span>
 <ol className="mt-2 space-y-1.5">
 {issue.timeline.map((t, i) => (
 <li key={`${t.event}-${i}`} className="text-xs flex gap-2" data-testid={`issue-timeline-${i}`}>
 <span className="text-[var(--color-text-muted)] shrink-0 w-28">{t.timestamp ? new Date(t.timestamp).toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}</span>
 <span><b>{t.label || t.event}</b>{t.by ? ` · ${t.by}` : ''}</span>
 </li>
 ))}
 </ol>
 </div>
 )}


 {/* AI Triage — collapsible (Iter 216h263). Users wanted this
     tucked away in a dropdown so the fault card opens with the
     conversation/quotes immediately visible. */}
 {(issue.ai_triage_parsed || issue.ai_triage) && (
 <div className="rounded-lg border border-[var(--theme-border)] bg-[var(--theme-surface)] overflow-hidden" data-testid={`ai-triage-dropdown-${issue.id}`}>
 <button
 type="button"
 onClick={() => setShowAiTriage((s) => !s)}
 className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-white/[0.03]"
 data-testid={`ai-triage-toggle-${issue.id}`}
 >
 <span className="flex items-center gap-2 text-sm font-medium text-[var(--theme-text)]">
 <ShieldCheck size={14} className="text-[var(--color-brand-cyan-hover)]" />
 AI Triage Assessment
 {issue.ai_triage_parsed?.severity_assessment ? (
 <Badge className={
 issue.ai_triage_parsed.severity_assessment === 'critical' ? 'bg-red-500/20 text-red-400 ml-1' :
 issue.ai_triage_parsed.severity_assessment === 'medium' ? 'bg-yellow-500/20 text-yellow-400 ml-1' :
 'bg-green-500/20 text-green-400 ml-1'
 }>
 {(issue.ai_triage_parsed.severity_assessment || '').toUpperCase()}
 </Badge>
 ) : null}
 </span>
 {showAiTriage ? (
 <ChevronUp size={16} className="text-[var(--color-text-muted)]" />
 ) : (
 <ChevronDown size={16} className="text-[var(--color-text-muted)]" />
 )}
 </button>
 {showAiTriage && (
 <div className="px-4 pb-4 pt-1 border-t border-[var(--theme-border)]">
 {issue.ai_triage_parsed ? (
 <div data-testid="structured-triage-section">
 <div className="mt-2 space-y-3">
 {/* Severity + Status badges */}
 <div className="flex items-center gap-2 flex-wrap">
 <Badge className={
 issue.ai_triage_parsed.severity_assessment === 'critical' ? 'bg-red-500/20 text-red-400' :
 issue.ai_triage_parsed.severity_assessment === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
 'bg-green-500/20 text-green-400'
 }>
 {(issue.ai_triage_parsed.severity_assessment || '').toUpperCase()}
 </Badge>
 {issue.ai_triage_parsed.can_fix_onsite !== undefined && (
 <Badge className={issue.ai_triage_parsed.can_fix_onsite ? 'bg-green-500/20 text-green-400' : 'bg-orange-500/20 text-orange-400'}>
 {issue.ai_triage_parsed.can_fix_onsite ? 'Can Fix On-Site' : 'Needs Engineer'}
 </Badge>
 )}
 {issue.ai_triage_parsed.estimated_repair_time && (
 <Badge className="bg-white/10 text-white">
 <Clock size={10} className="mr-1" /> {issue.ai_triage_parsed.estimated_repair_time}
 </Badge>
 )}
 </div>

 {/* Diagnosis card */}
 {issue.ai_triage_parsed.diagnosis && (
 <div className="p-4 bg-[rgb(var(--rgb-brand-blue)/0.1)] border border-[rgb(var(--rgb-brand-blue)/0.2)] rounded-lg">
 <h5 className="text-[var(--color-brand-blue)] text-xs font-semibold uppercase tracking-wide mb-1">Diagnosis</h5>
 <p className="text-white text-sm">{issue.ai_triage_parsed.diagnosis}</p>
 </div>
 )}

 {/* Likely cause */}
 {issue.ai_triage_parsed.likely_cause && (
 <div className="p-3 bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-lg">
 <h5 className="text-[var(--color-text-muted)] text-xs font-semibold uppercase tracking-wide mb-1">Likely Cause</h5>
 <p className="text-white text-sm">{issue.ai_triage_parsed.likely_cause}</p>
 </div>
 )}

 {/* Selected fix — highlighted if user chose one */}
 {issue.selected_fix_title ? (
 <div className="p-4 bg-green-500/10 border border-green-500/20 rounded-lg">
 <div className="flex items-center gap-2 mb-2">
 <CheckCircle size={16} className="text-green-400" />
 <h5 className="text-green-400 text-xs font-semibold uppercase tracking-wide">Applied Fix</h5>
 </div>
 <p className="text-white text-sm font-medium">{issue.selected_fix_title}</p>
 {issue.selected_fix_step && (
 <p className="text-[var(--color-text-muted)] text-sm mt-1">{issue.selected_fix_step}</p>
 )}
 </div>
 ) : (
 /* Show all repair steps if no fix was selected */
 issue.ai_triage_parsed.repair_steps?.length > 0 && (
 <div>
 <h5 className="text-white text-xs font-semibold uppercase tracking-wide mb-2">Repair Steps</h5>
 <div className="space-y-2">
 {issue.ai_triage_parsed.repair_steps.map((s, i) => (
 <div key={i} className="flex gap-3 p-3 bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-lg">
 <div className="w-7 h-7 rounded-full bg-[rgb(var(--rgb-brand-blue)/0.2)] flex items-center justify-center flex-shrink-0">
 <span className="text-[var(--color-brand-blue)] text-xs font-bold">{s.step || i + 1}</span>
 </div>
 <div className="flex-1">
 {s.title && <p className="text-white text-sm font-medium">{s.title}</p>}
 <p className="text-[var(--color-text-muted)] text-sm">{s.instruction}</p>
 {s.safety_note && s.safety_note !== 'null' && (
 <p className="text-yellow-400 text-xs mt-1 flex items-center gap-1">
 <AlertCircle size={10} /> {s.safety_note}
 </p>
 )}
 </div>
 </div>
 ))}
 </div>
 </div>
 )
 )}

 {/* Recommended action */}
 {issue.ai_triage_parsed.recommended_action && !issue.selected_fix_title && (
 <div className="p-3 bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-lg">
 <h5 className="text-[var(--color-text-muted)] text-xs font-semibold uppercase tracking-wide mb-1">Recommended Action</h5>
 <p className="text-white text-sm">{issue.ai_triage_parsed.recommended_action}</p>
 </div>
 )}

 {/* Safety note */}
 {issue.ai_triage_parsed.safety_note && issue.ai_triage_parsed.safety_note !== 'null' && (
 <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg flex items-start gap-2">
 <AlertCircle size={14} className="text-red-400 mt-0.5 flex-shrink-0" />
 <p className="text-red-400 text-sm">{issue.ai_triage_parsed.safety_note}</p>
 </div>
 )}
 </div>
 </div>
 ) : issue.ai_triage && (
 <div>
 <div className="mt-2 p-4 bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-lg text-[var(--color-text-muted)] text-sm whitespace-pre-wrap break-words" style={{overflowWrap:'break-word'}}>{issue.ai_triage}</div>
 </div>
 )}
 </div>
 )}
 </div>
 )}

 {/* Attachments (excludes kind=quote — those have their own card below) */}
 <div className="p-4 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg">
 <div className="flex items-center justify-between mb-3">
 <h4 className="text-[var(--theme-text)] font-medium flex items-center gap-2">
 <Paperclip size={16} /> Attachments ({attachments.filter((a) => (a.kind || '').toLowerCase() !== 'quote').length})
 </h4>
 <label className="cursor-pointer">
 <input type="file" className="hidden" onChange={handleFileUpload} accept="image/*,.pdf,.doc,.docx,.xlsx" data-testid={`attachment-input-${issue.id}`} />
 <span className="flex items-center gap-1 text-sm text-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue-alt)]">
 <Upload size={14} /> {uploading ? 'Uploading...' : 'Upload Job Sheet'}
 </span>
 </label>
 </div>
 {attachments.filter((a) => (a.kind || '').toLowerCase() !== 'quote').length > 0 ? (
 <div className="space-y-2">
 {attachments.filter((a) => (a.kind || '').toLowerCase() !== 'quote').map(att => (
 <div key={att.id} className="flex items-center justify-between p-2 bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded" data-testid={`issue-attachment-${att.id}`}>
 <div className="flex items-center gap-2 min-w-0">
 {(att.content_type || '').startsWith('image/') && attachmentUrl(att) ? (
 <a href={attachmentUrl(att)} target="_blank" rel="noreferrer" className="shrink-0">
 <img src={attachmentUrl(att)} alt={att.filename} loading="lazy" className="w-12 h-12 rounded object-cover border border-[var(--theme-border)]" data-testid={`issue-attachment-thumb-${att.id}`} />
 </a>
 ) : (
 <FileText size={14} className="text-[var(--color-brand-blue)] shrink-0" />
 )}
 <span className="text-[var(--theme-text)] text-sm truncate">{att.filename}</span>
 <span className="text-[var(--color-text-muted)] text-xs shrink-0">{att.uploaded_by} - {att.uploaded_at ? new Date(att.uploaded_at).toLocaleDateString() : ''}</span>
 </div>
 {attachmentUrl(att) && (
 <a href={attachmentUrl(att)} target="_blank" rel="noreferrer" className="text-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue-alt)] shrink-0" data-testid={`issue-attachment-open-${att.id}`}>
 <ExternalLink size={14} />
 </a>
 )}
 </div>
 ))}
 </div>
 ) : (
 <p className="text-[var(--color-text-muted)] text-sm">No files attached. Upload job sheets or photos here.</p>
 )}
 </div>

 {/* Job Card — compact collapsible block with full service-management details */}
 <SiconServicePanel issue={issue} equipment={equipmentDoc} engineers={engineerDir} />

 {/* ═══ SUPPLIER COMMUNICATION — inline chat built into card ═══ */}
 <div className="p-4 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg" data-testid={`supplier-comms-${issue.id}`}>
 <div className="flex items-center justify-between mb-3">
 <h4 className="text-white font-medium flex items-center gap-2">
 <Wrench size={16} className="text-[var(--color-brand-blue)]" /> Supplier Communication
 {issue.supplier_case?.comments?.length > 0 && <span className="text-[var(--color-text-muted)] text-xs">({issue.supplier_case.comments.length})</span>}
 </h4>
 <div className="flex items-center gap-2">
 {issue.supplier_case?.comments?.length > 2 && (
 <Button size="sm" variant="ghost" className="text-[var(--color-text-muted)] hover:text-white text-xs h-6 px-2"
 onClick={() => setShowFullHistory(!showFullHistory)}
 data-testid={`toggle-history-${issue.id}`}>
 <Clock size={11} className="mr-1" /> {showFullHistory ? 'Show Latest' : 'Conversation History'}
 </Button>
 )}
 {issue.supplier_case?.token && (
 <Button size="sm" variant="ghost" className="text-[var(--color-brand-blue)] text-xs h-6 px-2"
 onClick={() => window.open(`/supplier/case/${issue.supplier_case.token}?view=site`, '_blank')}
 data-testid={`view-chat-${issue.id}`}>
 <ExternalLink size={11} className="mr-1" /> Supplier Card
 </Button>
 )}
 </div>
 </div>

 {/* Iter 216h57 — Engineer-visit banner moved up to the prominent
     position previously occupied by the Supplier Fault Card. Kept
     here is only the chat thread itself + the Supplier Card deep
     link in the header. */}

 {/* Shared thread — show every supplier notified on this fault (MOD faults
     notify Pulse + the overseas/machine provider on the same thread). */}
 {issue.supplier_case?.notify_emails?.length > 1 && (
   <div className="mb-3 flex flex-wrap items-center gap-1.5" data-testid={`supplier-notified-${issue.id}`}>
     <span className="text-[var(--color-text-muted)] text-[11px] font-semibold uppercase tracking-wide flex items-center gap-1">
       <Users size={12} /> Shared with
     </span>
     {issue.supplier_case.notify_emails.map((r, i) => (
       <span key={i} title={r.email}
         className="inline-flex items-center rounded-full bg-[var(--color-brand-blue)]/15 text-[var(--color-brand-blue)] px-2 py-0.5 text-[11px] font-semibold"
         data-testid={`supplier-notified-${issue.id}-${i}`}>
         {r.name || r.email}
       </span>
     ))}
   </div>
 )}

 {/* Chat messages */}
 <div className={`overflow-y-auto space-y-2 mb-3 rounded-lg p-2 bg-[var(--theme-surface-2)] border border-[var(--theme-border-soft)] ${showFullHistory ? 'max-h-[280px]' : ''}`} style={{ minHeight: '40px' }}>
 {/* Old-style messages fallback */}
 {!issue.supplier_case && issue.supplier_messages?.length > 0 && (() => {
 const msgs = showFullHistory ? issue.supplier_messages : issue.supplier_messages.slice(-2);
 return msgs.map((req, idx) => (
 <div key={req.id || idx} className="flex justify-start">
 <div className="max-w-[85%] rounded-2xl px-3 py-2 bg-[var(--theme-surface-3)] rounded-bl-md">
 <div className="flex items-center gap-1.5 mb-0.5">
 <span className="text-[9px] font-bold uppercase tracking-wider text-[var(--color-success-alt)]">You</span>
 <span className="text-[#555] text-[9px]">{req.sent_at ? new Date(req.sent_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}</span>
 </div>
 <p className="text-[var(--theme-text)] text-sm">{req.message}</p>
 </div>
 </div>
 ));
 })()}
 {/* Supplier case two-way comments — show last message or full history */}
 {issue.supplier_case?.comments?.length > 0 ? (() => {
 const allComments = issue.supplier_case.comments;
 const visibleComments = showFullHistory ? allComments : allComments.slice(-2);
 return visibleComments.map(c => {
 const isSupplier = c.author_role === 'supplier';
 const isSeenByRecipient = !isSupplier && c.read_at_supplier;
 return (
 <div key={c.id} className={`flex ${isSupplier ? 'justify-end' : 'justify-start'}`}>
 <div className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 ${isSupplier ? 'rounded-br-sm' : 'rounded-bl-sm'}`}
 style={{ background: isSupplier ? 'var(--color-info-ios)' : 'var(--color-success-alt)', color: '#fff' }}>
 <div className="flex items-center gap-1.5 mb-0.5">
 <span className="text-[9px] font-bold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.7)' }}>
 {c.author_name}
 </span>
 <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.5)' }}>{new Date(c.created_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
 </div>
 {isSupplier ? (c.message && <p className="text-sm leading-relaxed" style={{ color: '#fff' }}>{c.message}</p>) : (
 <GymCommentBody comment={c} caseToken={issue.supplier_case.token} API={API} user={user} onChanged={reloadDetail} />
 )}
 {(c.attachments || []).map((a, i) => (
 <div key={i} className="mt-1.5">
 {a.content_type?.startsWith('image/') ? (
 <a href={a.download_url} target="_blank" rel="noreferrer"><img src={a.download_url} alt={a.filename} className="rounded-lg max-h-28 object-cover" /></a>
 ) : (
 <a href={a.download_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-[var(--color-brand-blue)] hover:underline"><Paperclip size={11} /> {a.filename}</a>
 )}
 </div>
 ))}
 {!isSupplier && (
 <div
 className="flex justify-end mt-1 gap-1 items-center"
 data-testid={`gym-comment-receipt-${c.id}`}
 >
 <span
 className="text-[9px]"
 style={{ color: isSeenByRecipient ? 'var(--color-blue-100)' : 'rgba(255,255,255,0.55)' }}
 title={isSeenByRecipient ? `Seen by supplier ${new Date(c.read_at_supplier).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` : 'Delivered — not yet seen by supplier'}
 >
 {isSeenByRecipient ? 'Seen ✓✓' : 'Sent ✓'}
 </span>
 </div>
 )}
 </div>
 </div>
 );
 });
 })() : (
 !issue.supplier_messages?.length && <p className="text-[#555] text-xs text-center py-2">No messages yet</p>
 )}
 </div>

 {/* Inline compose — always visible, no popup */}
 <div className="flex gap-2">
 <Input
 value={commentText}
 onChange={e => setCommentText(e.target.value)}
 placeholder="Type a message to supplier..."
 className="bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)] text-sm flex-1 h-9"
 data-testid={`reply-supplier-input-${issue.id}`}
 onKeyDown={e => {
 if (e.key === 'Enter' && !e.shiftKey) {
 e.preventDefault();
 if (issue.supplier_case?.token) {
 handleSendGymComment();
 } else {
 handleContactSupplier();
 }
 }
 }}
 />
 <Button size="sm" disabled={sendingComment || !commentText.trim()} className="bg-[var(--color-brand-blue)] text-white h-9 px-3"
 onClick={() => {
 if (issue.supplier_case?.token) {
 handleSendGymComment();
 } else {
 handleContactSupplier();
 }
 }}
 data-testid={`reply-supplier-btn-${issue.id}`}>
 {sendingComment ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
 </Button>
 </div>

 {/* Rating */}
 {issue.supplier_case?.rating && (
 <div className="flex items-center gap-2 mt-3 pt-3 border-t border-[var(--theme-border-soft)]">
 <span className="text-[var(--color-text-muted)] text-xs">Rating:</span>
 <div className="flex gap-0.5">{[1,2,3,4,5].map(s => <span key={s} className={`text-sm ${s <= issue.supplier_case.rating ? 'text-amber-400' : 'text-[#333]'}`}>&#9733;</span>)}</div>
 {issue.supplier_case.rating_feedback && <span className="text-[#666] text-xs italic">"{issue.supplier_case.rating_feedback}"</span>}
 </div>
 )}
 </div>

 {/* Quotes (Iter 216h263) — dedicated PDF/image upload slot for
     supplier quotes. Lives ABOVE Purchase Orders so the manager
     can see the quote before raising the PO. Uses the same
     /attachments endpoint with `kind=quote`. */}
 <div className="p-4 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg" data-testid={`quotes-section-${issue.id}`}>
 <div className="flex items-center justify-between mb-3">
 <h4 className="text-white font-medium flex items-center gap-2">
 <Receipt size={16} className="text-[var(--color-brand-cyan-hover)]" /> Quotes ({(attachments || []).filter((a) => (a.kind || '').toLowerCase() === 'quote').length})
 </h4>
 <label className="cursor-pointer">
 <input
 type="file"
 className="hidden"
 onChange={(e) => handleFileUpload(e, 'quote')}
 accept=".pdf,image/*"
 data-testid={`quote-input-${issue.id}`}
 />
 <span className="inline-flex items-center gap-1 text-sm text-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue-alt)]">
 {uploadingQuote ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
 {uploadingQuote ? 'Uploading…' : 'Add quote (PDF)'}
 </span>
 </label>
 </div>
 {(attachments || []).filter((a) => (a.kind || '').toLowerCase() === 'quote').length > 0 ? (
 <div className="space-y-2">
 {(attachments || []).filter((a) => (a.kind || '').toLowerCase() === 'quote').map((att) => (
 <div key={att.id} className="flex items-center justify-between p-2 bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded">
 <div className="flex items-center gap-2 min-w-0">
 <FileText size={14} className="text-[var(--color-brand-cyan-hover)] shrink-0" />
 <span className="text-[var(--theme-text)] text-sm truncate">{att.filename}</span>
 <span className="text-[var(--color-text-muted)] text-xs shrink-0">
 {att.uploaded_by}{att.uploaded_at ? ` · ${new Date(att.uploaded_at).toLocaleDateString()}` : ''}
 </span>
 </div>
 {att.download_url && (
 <a href={att.download_url} target="_blank" rel="noreferrer" className="text-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue-alt)] shrink-0" data-testid={`quote-open-${att.id}`}>
 <ExternalLink size={14} />
 </a>
 )}
 </div>
 ))}
 </div>
 ) : (
 <p className="text-[var(--color-text-muted)] text-sm" data-testid={`quotes-empty-${issue.id}`}>
 No quotes attached. Drop the supplier&apos;s quote PDF here so you can review it before raising a PO.
 </p>
 )}
 </div>

 {/* Purchase Orders */}
 <div className="p-4 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg">
 <div className="flex items-center justify-between mb-3">
 <h4 className="text-white font-medium flex items-center gap-2">
 <ShoppingCart size={16} /> Purchase Orders ({purchaseOrders.length})
 </h4>
 <Button size="sm" onClick={() => {
 // Auto-populate PO with defaults
 const defaultItems = [];
 if (poDefaults?.callout_fee) defaultItems.push({ description: 'Callout fee', quantity: 1, unit_price: poDefaults.callout_fee });
 if (poDefaults?.labour_rate_per_hour) defaultItems.push({ description: 'Labour (per hour)', quantity: 1, unit_price: poDefaults.labour_rate_per_hour });
 if (poDefaults?.custom_items?.length > 0) {
 poDefaults.custom_items.forEach(ci => {
 if (ci.description) defaultItems.push({ description: ci.description, quantity: ci.quantity || 1, unit_price: ci.unit_price || 0 });
 });
 }
 if (defaultItems.length === 0) defaultItems.push({ description: '', quantity: 1, unit_price: 0 });
 setPOForm(f => ({ ...f, items: defaultItems, supplier_name: issue.supplier || f.supplier_name }));
 setShowPODialog(true);
 }} className="bg-[var(--color-brand-blue)] text-white" data-testid={`create-po-btn-${issue.id}`}>
 <Plus size={14} className="mr-1" /> Create PO
 </Button>
 </div>
 {purchaseOrders.length > 0 ? (
 <div className="space-y-2">
 {purchaseOrders.map(po => (
 <div key={po.id} className="flex items-center justify-between p-3 bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-lg" data-testid={`po-card-${po.id}`}>
 <div>
 <p className="text-white font-medium text-sm">{po.po_number}</p>
 <p className="text-[var(--color-text-muted)] text-xs">{po.supplier_name} | {po.created_at?.slice(0, 10)}</p>
 </div>
 <div className="flex items-center gap-2">
 <span className="text-white font-semibold text-sm">{"\u00A3"}{po.total?.toFixed(2)}</span>
 <Badge className={po.status === 'sent' ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}>{po.status}</Badge>
 <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-white text-xs" onClick={() => handleViewPOPdf(po.id)} data-testid={`view-po-pdf-${po.id}`}>
 <FileText size={12} className="mr-1" /> View
 </Button>
 <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-white text-xs" onClick={async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/purchase-orders/${po.id}/pdf`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 const printWin = window.open('', '_blank');
 if (printWin) {
 printWin.document.write(res.data);
 printWin.document.close();
 setTimeout(() => printWin.print(), 500);
 }
 } catch { notify.error('Failed to print PO'); }
 }} data-testid={`print-po-btn-${po.id}`}>
 <Printer size={12} className="mr-1" /> Print
 </Button>
 {po.status === 'draft' && (
 <Button size="sm" variant="outline" className="border-[rgb(var(--rgb-brand-blue)/0.5)] text-[var(--color-brand-blue)] text-xs" onClick={() => handleSendPO(po.id)} data-testid={`send-po-btn-${po.id}`}>
 <Send size={12} className="mr-1" /> Send
 </Button>
 )}
 </div>
 </div>
 ))}
 </div>
 ) : (
 <p className="text-[var(--color-text-muted)] text-sm">No purchase orders created for this fault.</p>
 )}
 </div>

 {(user?.account_type === 'mod_site' || user?.is_mod_user) && (issue.bfpo_case_id || issue.linked_case_id) && (
 <div className="flex pt-2">
  <Button size="sm" variant="outline" className="h-8 text-xs" data-testid="mod-fault-service-report-btn"
    onClick={async () => {
      try {
        const r = await axios.get(`${API}/mod/site/faults/${issue.id}/service-report.pdf`,
          { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }, responseType: 'blob' });
        window.open(URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' })), '_blank');
      } catch { notify.error('Service report not available yet'); }
    }}>
    <FileText size={12} className="mr-1" /> Service report
  </Button>
 </div>
 )}

 {/* Status Actions */}
 {issue.status !== 'resolved' && (
 <div className="flex gap-2 pt-2 border-t border-[var(--theme-border)] flex-wrap">
 {issue.status === 'open' && (
 <Button size="sm" onClick={() => onUpdate(issue.id, 'in_progress')} className="bg-yellow-500 hover:bg-yellow-600 text-white" data-testid={`detail-progress-btn-${issue.id}`}>
 Mark In Progress
 </Button>
 )}
 <Button size="sm" onClick={() => onUpdate(issue.id, 'resolved')} className="bg-green-500 hover:bg-green-600 text-white" data-testid={`detail-resolve-btn-${issue.id}`}>
 Mark Resolved
 </Button>
 {/* Iter 216h117 — MOD site users can escalate to DIO. Hidden for non-MOD. */}
{/* Iter 216h137 — Surface the configured DIO contract context above the button so the engineer sees who escalation goes to. */}
{user?.account_type === 'mod_site' && !issue.escalated_to_dio && (
<div className="flex items-center gap-2 flex-wrap" data-testid={`detail-dio-block-${issue.id}`}>
<Button
  size="sm"
  variant="outline"
  onClick={() => setDioModalOpen(true)}
  className="border-cyan-400/60 bg-cyan-50 text-cyan-800 hover:bg-cyan-100"
  data-testid={`detail-escalate-dio-${issue.id}`}
>
  <ShieldCheck size={12} className="mr-1" /> Report to DIO
</Button>
{dioContract?.configured ? (
<div className="text-[10.5px] text-cyan-800 bg-cyan-50/60 border border-cyan-200 rounded px-2 py-1 max-w-[280px]" data-testid={`detail-dio-ctx-${issue.id}`}>
  <p className="font-bold leading-tight">DIO contract on file</p>
  <p className="leading-tight truncate">
    {dioContract.dio_contract_ref ? <code className="font-mono">{dioContract.dio_contract_ref}</code> : 'No ref'} · {dioContract.dio_contact_name || dioContract.dio_contact_email || 'HQ ops'}
  </p>
</div>
) : dioContract && !dioContract.configured ? (
<div className="text-[10.5px] text-amber-800 bg-amber-50/60 border border-amber-200 rounded px-2 py-1 max-w-[280px]" data-testid={`detail-dio-ctx-${issue.id}`}>
  <p className="font-bold leading-tight">No DIO contract set</p>
  <p className="leading-tight">Escalation will go to HQ ops only.</p>
</div>
) : null}
</div>
)}
 {user?.account_type === 'mod_site' && issue.escalated_to_dio && (
 <span
   className="inline-flex items-center gap-1 text-[11px] font-extrabold px-2 py-1 rounded border border-cyan-400/40 bg-cyan-50 text-cyan-800"
   data-testid={`detail-dio-pill-${issue.id}`}
   title={`Escalated ${issue.dio_escalated_at ? new Date(issue.dio_escalated_at).toLocaleString() : ''}`}
 >
   <ShieldCheck size={11} /> Escalated to DIO
 </span>
 )}
 </div>
 )}

 {/* MOD acceptance limbo fix — a fault marked resolved but awaiting the
     reporter's email confirmation will auto-reopen after the grace window.
     Let the site owner/manager confirm the fix directly and close it. */}
 {user?.account_type === 'mod_site' && issue.status === 'resolved' && issue.acceptance_status === 'pending' && (
 <div className="pt-2 border-t border-[var(--theme-border)]" data-testid={`mod-acceptance-pending-${issue.id}`}>
 <div className="flex items-start gap-2 text-[12px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2 mb-2">
 <AlertTriangle size={14} className="shrink-0 mt-0.5" />
 <span>Awaiting the reporter's email confirmation. If they don't respond this fault will auto-reopen. You can confirm the fix directly to close it now.</span>
 </div>
 <Button
   size="sm"
   onClick={async () => {
     try {
       await axios.post(
         `${API}/mod/site/faults/${issue.id}/confirm-resolved`,
         { note: '' },
         { headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } },
       );
       setIssue({ ...issue, acceptance_status: 'accepted' });
       notify.success('Fault closed', 'Confirmed resolved — it will no longer auto-reopen.');
       if (onUpdate) onUpdate();
     } catch (e) {
       notify.error('Could not confirm', e?.response?.data?.detail || 'Please try again.');
     }
   }}
   className="bg-emerald-500 hover:bg-emerald-600 text-white"
   data-testid={`mod-confirm-resolved-btn-${issue.id}`}
 >
   <CheckCircle size={12} className="mr-1" /> Confirm resolved &amp; close
 </Button>
 </div>
 )}

 {/* Iter 216k — supplier-email collector dialog. Replaces the
     ugly browser prompt() that was firing every time an operator
     sent a message to a supplier without an email on file. */}
 <MODDIOEscalateModal
   open={dioModalOpen}
   onClose={() => setDioModalOpen(false)}
   api={API}
   faultId={issue.id}
   ticketRef={issue.mod_ticket_ref}
   existingDioEmail={issue.dio_contact_email || ''}
   onEscalated={() => {
     setIssue({ ...issue, escalated_to_dio: true, dio_escalated_at: new Date().toISOString() });
     if (onUpdate) onUpdate();
   }}
 />
 <Dialog
   open={supplierEmailDialog.open}
   onOpenChange={(o) => setSupplierEmailDialog((s) => ({ ...s, open: o, ...(o ? {} : { pending: null, email: '' }) }))}
 >
   <DialogContent className="max-w-md bg-[var(--theme-surface)] border-[var(--theme-border)]" data-testid="supplier-email-dialog">
     <DialogHeader>
       <DialogTitle className="text-[var(--theme-text)] flex items-center gap-2">
         <span style={{ color: 'var(--color-brand-blue)' }}>✉</span>
         Add supplier email
       </DialogTitle>
     </DialogHeader>
     <div className="space-y-3">
       <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>
         <strong className="text-[var(--theme-text)]">{issue.supplier || 'This supplier'}</strong> doesn't have an email on file yet. Add one now and we'll save it on the case so you're not asked again.
       </p>
       <div>
         <Label className="text-[var(--theme-text)] text-sm">Supplier email</Label>
         <Input
           type="email"
           autoFocus
           value={supplierEmailDialog.email}
           onChange={(e) => setSupplierEmailDialog((s) => ({ ...s, email: e.target.value }))}
           onKeyDown={(e) => { if (e.key === 'Enter' && !supplierEmailDialog.submitting) _confirmSupplierEmail(); }}
           placeholder="service@supplier.com"
           className="mt-1 bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)]"
           data-testid="supplier-email-dialog-input"
         />
         <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
           This is the inbox we'll send the case notification + 2-way chat alerts to.
         </p>
       </div>
       <div className="flex justify-end gap-2 pt-2">
         <Button variant="outline" onClick={() => setSupplierEmailDialog({ open: false, email: '', pending: null, submitting: false })} data-testid="supplier-email-dialog-cancel">
           Cancel
         </Button>
         <Button
           onClick={_confirmSupplierEmail}
           disabled={supplierEmailDialog.submitting}
           className="bg-[var(--color-brand-blue)] text-white hover:opacity-90"
           data-testid="supplier-email-dialog-confirm"
         >
           {supplierEmailDialog.submitting ? 'Saving…' : 'Save & send'}
         </Button>
       </div>
     </div>
   </DialogContent>
 </Dialog>

 {/* Create PO Dialog */}
 <Dialog open={showPODialog} onOpenChange={setShowPODialog}>
 <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-white max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="po-dialog">
 <DialogHeader>
 <DialogTitle className="text-white">Create Purchase Order</DialogTitle>
 </DialogHeader>
 <div className="space-y-4">
 <div className="p-3 bg-[rgb(var(--rgb-brand-blue)/0.1)] border border-[rgb(var(--rgb-brand-blue)/0.3)] rounded-lg text-sm">
 <p className="text-[var(--color-brand-blue)] font-medium">For: {issue.serial_number} - {issue.machine_type}</p>
 <p className="text-[var(--color-text-muted)]">{issue.issue_description?.substring(0, 100)}</p>
 </div>

 <div>
 <Label className="text-white text-sm">Your PO Number (optional)</Label>
 <Input value={poForm.po_number} onChange={e => setPOForm({ ...poForm, po_number: e.target.value })}
 placeholder="e.g., PO-2026-001 (leave blank for auto-generated)"
 className="bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-white mt-1" data-testid="po-custom-number" />
 </div>

 <div className="grid grid-cols-2 gap-3">
 <div>
 <Label className="text-white text-sm">Supplier Name</Label>
 <Input value={poForm.supplier_name} onChange={e => setPOForm({ ...poForm, supplier_name: e.target.value })}
 className="bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-white mt-1" data-testid="po-supplier-name" />
 </div>
 <div>
 <Label className="text-white text-sm">Supplier Email</Label>
 <Input type="email" value={poForm.supplier_email} onChange={e => setPOForm({ ...poForm, supplier_email: e.target.value })}
 className="bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-white mt-1" data-testid="po-supplier-email" />
 </div>
 </div>
 <div>
 <Label className="text-white text-sm">Delivery Address</Label>
 <Input value={poForm.delivery_address} onChange={e => setPOForm({ ...poForm, delivery_address: e.target.value })}
 placeholder="Gym address..." className="bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-white mt-1" data-testid="po-delivery-address" />
 </div>

 {/* Line Items */}
 <div>
 <Label className="text-white text-sm mb-2 block">Line Items</Label>
 <div className="space-y-2">
 {poForm.items.map((item, idx) => (
 <div key={idx} className="grid grid-cols-12 gap-2 items-center">
 <div className="col-span-6">
 <Input value={item.description} onChange={e => updateLineItem(idx, 'description', e.target.value)}
 placeholder="Part / service description" className="bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-white text-sm" data-testid={`po-item-desc-${idx}`} />
 </div>
 <div className="col-span-2">
 <Input value={item.quantity} onChange={e => updateLineItem(idx, 'quantity', e.target.value.replace(/[^0-9]/g, ''))}
 placeholder="Qty" className="bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-white text-sm" data-testid={`po-item-qty-${idx}`} />
 </div>
 <div className="col-span-3">
 <div className="relative">
 <span className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] text-sm">{"\u00A3"}</span>
 <Input value={item.unit_price} onChange={e => updateLineItem(idx, 'unit_price', e.target.value.replace(/[^0-9.]/g, ''))}
 placeholder="0.00" className="bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-white text-sm pl-6" data-testid={`po-item-price-${idx}`} />
 </div>
 </div>
 <div className="col-span-1">
 {poForm.items.length > 1 && (
 <button onClick={() => removeLineItem(idx)} className="text-red-400 hover:text-red-300 p-1"><Trash2 size={14} /></button>
 )}
 </div>
 </div>
 ))}
 </div>
 <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-[var(--color-text-muted)] mt-2" onClick={addLineItem} data-testid="po-add-item-btn">
 <Plus size={14} className="mr-1" /> Add Line
 </Button>
 </div>

 {/* Totals */}
 <div className="p-3 bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-lg text-right space-y-1">
 <p className="text-[var(--color-text-muted)] text-sm">Subtotal: <span className="text-white">{"\u00A3"}{poSubtotal.toFixed(2)}</span></p>
 <p className="text-[var(--color-text-muted)] text-sm">VAT (20%): <span className="text-white">{"\u00A3"}{(poSubtotal * 0.2).toFixed(2)}</span></p>
 <p className="text-white font-bold text-lg">Total: {"\u00A3"}{(poSubtotal * 1.2).toFixed(2)}</p>
 </div>

 <div>
 <Label className="text-white text-sm">Notes</Label>
 <Textarea value={poForm.notes} onChange={e => setPOForm({ ...poForm, notes: e.target.value })}
 rows={2} placeholder="Additional notes for the supplier..." className="bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-white mt-1" data-testid="po-notes" />
 </div>

 <Button onClick={handleCreatePO} disabled={poLoading} className="w-full" data-testid="po-submit-btn">
 {poLoading ? 'Creating...' : 'Create Purchase Order'}
 </Button>
 </div>
 </DialogContent>
 </Dialog>
 </div>
 );
};

export default IssueDetailPanel;
