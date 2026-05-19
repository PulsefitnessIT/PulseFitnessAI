import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { notify } from '@/components/notifications';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import axios from 'axios';
import {
 Wrench, MapPin, AlertTriangle, Clock, CheckCircle, Send,
 Image, FileText, ChevronDown, ChevronUp, Shield, Loader2,
 Calendar, User, Building2, Paperclip, Star, X, Camera, MessageCircle,
 Phone, Mail, Copy, ContactRound, Globe
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_FLOW = [
 { value: 'pending', label: 'Pending', color: 'bg-white/10 text-zinc-500', icon: Clock },
 { value: 'acknowledged', label: 'Acknowledged', color: 'bg-blue-500/20 text-blue-400', icon: CheckCircle },
 { value: 'engineer_scheduled', label: 'Engineer Scheduled', color: 'bg-purple-500/20 text-purple-400', icon: Calendar },
 { value: 'in_progress', label: 'In Progress', color: 'bg-yellow-500/20 text-yellow-400', icon: Wrench },
 { value: 'parts_ordered', label: 'Parts Ordered', color: 'bg-orange-500/20 text-orange-400', icon: FileText },
 { value: 'completed', label: 'Completed', color: 'bg-green-500/20 text-green-400', icon: CheckCircle },
];

/* ═══ SITE CONTACT CARD ═══
 * Shows the gym's address, phone, email, and the specific reporter who
 * logged the fault, plus 3 "create-by-email" shortcuts so the supplier can
 * drag this job straight into their own ticketing system.
 */
function SiteContactCard({ reporter, site, organizationName, token, jobRef, issue }) {
 const [copying, setCopying] = useState(false);
 const apiBase = `${API}/api/supplier/case/${token}`;
 const gymName = site?.gym_name || organizationName || '';
 const address = site?.address || '';
 const sitePhone = site?.phone || '';
 const siteEmail = site?.email || '';
 const siteWeb = site?.website || '';
 const repName = reporter?.name || '';
 const repEmail = reporter?.email || '';
 const repPhone = reporter?.phone || '';
 const repRole = reporter?.role || '';
 // Gym-floor-logged faults deserve extra visual weight on this card —
 // engineers reading the case page from a phone should immediately see
 // "shift worker, not manager" so they call the right person.
 const isGymFloor = repRole.toLowerCase() === 'gym floor';

 const handleCopyTicket = async () => {
 try {
 setCopying(true);
 const res = await fetch(`${apiBase}/summary.txt`);
 const text = await res.text();
 await navigator.clipboard.writeText(text);
 notify.success('Ticket summary copied — paste into your ticketing system');
 } catch {
 notify.error('Copy failed — use the Download button instead');
 } finally {
 setCopying(false);
 }
 };

 const ContactRow = ({ icon: Icon, label, value, href, testId }) => {
 if (!value) return null;
 return (
 <div className="flex items-start gap-2.5 py-1.5" data-testid={testId}>
 <Icon size={13} className="text-[var(--color-brand-blue)] flex-shrink-0 mt-0.5" />
 <div className="flex-1 min-w-0">
 <p className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</p>
 {href ? (
 <a href={href} className="text-zinc-900 text-sm hover:text-[var(--color-brand-blue)] break-words">{value}</a>
 ) : (
 <p className="text-zinc-800 text-sm break-words">{value}</p>
 )}
 </div>
 </div>
 );
 };

 return (
 <Card className="bg-white border-zinc-200 p-5" data-testid="site-contact-card">
 <h2 className="text-zinc-900 font-semibold text-lg mb-3 flex items-center gap-2">
 <ContactRound size={18} className="text-[var(--color-brand-blue)]" /> Gym &amp; Reporter Contact
 </h2>

 <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
 {/* Gym block */}
 <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-4">
 <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-2">Gym / Site</p>
 <p className="text-zinc-900 font-semibold text-sm mb-1">{gymName || '—'}</p>
 <ContactRow icon={MapPin} label="Address" value={address} testId="sup-case-gym-address" />
 <ContactRow icon={Phone} label="Site Phone" value={sitePhone} href={sitePhone ? `tel:${sitePhone.replace(/\s/g, '')}` : undefined} testId="sup-case-gym-phone" />
 <ContactRow icon={Mail} label="Site Email" value={siteEmail} href={siteEmail ? `mailto:${siteEmail}?subject=${encodeURIComponent(`[${jobRef || 'Job'}] ${issue?.machine_type || 'Equipment'}`)}` : undefined} testId="sup-case-gym-email" />
 <ContactRow icon={Globe} label="Website" value={siteWeb} href={siteWeb} testId="sup-case-gym-web" />
 </div>

 {/* Reporter block */}
 <div
 className={`rounded-lg p-4 border ${isGymFloor ? 'bg-sky-50 border-sky-300 ring-2 ring-sky-200' : 'bg-zinc-50 border-zinc-200'}`}
 data-testid="sup-case-reporter-block"
 data-gym-floor={isGymFloor ? 'true' : 'false'}
 >
 <p className={`text-[10px] uppercase tracking-wider mb-2 ${isGymFloor ? 'text-sky-700 font-bold' : 'text-zinc-500'}`}>
 Reported by
 </p>
 <p className="text-zinc-900 font-semibold text-sm mb-1 flex items-center gap-2 flex-wrap">
 <span>{repName || 'Unknown'}</span>
 {repRole && (
 <span
 className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
 isGymFloor
 ? 'bg-sky-100 text-sky-700 border border-sky-300'
 : 'bg-zinc-100 text-zinc-600 border border-zinc-200'
 }`}
 data-testid="sup-case-reporter-role-chip"
 >
 {repRole}
 </span>
 )}
 </p>
 <ContactRow icon={Mail} label="Email" value={repEmail} href={repEmail ? `mailto:${repEmail}?subject=${encodeURIComponent(`[${jobRef || 'Job'}] ${issue?.machine_type || 'Equipment'}`)}` : undefined} testId="sup-case-reporter-email" />
 <ContactRow icon={Phone} label="Phone" value={repPhone} href={repPhone ? `tel:${repPhone.replace(/\s/g, '')}` : undefined} testId="sup-case-reporter-phone" />
 {!repEmail && !repPhone && (
 <p className="text-zinc-500 text-xs italic">No direct contact on file. Use site phone above.</p>
 )}
 {isGymFloor && (repEmail || repPhone) && (
 <p className="text-[10px] text-sky-700 mt-2 italic" data-testid="sup-case-reporter-floor-hint">
 Logged from the gym floor — call this shift worker first; they saw the fault.
 </p>
 )}
 </div>
 </div>

 {/* Create-by-email action row */}
 <div className="mt-4 pt-4 border-t border-zinc-200">
 <p className="text-zinc-500 text-[11px] mb-2">
 <strong className="text-zinc-900">Importing this job into your ticketing system?</strong> Copy the summary,
 download a vCard of the site, or grab a structured .txt to drag into ServiceM8 / Freshdesk / Zendesk.
 </p>
 <div className="flex flex-wrap gap-2">
 <Button
 size="sm" onClick={handleCopyTicket} disabled={copying}
 className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-alt2)] text-white h-8 text-xs"
 data-testid="sup-case-copy-summary"
 >
 {copying ? <Loader2 size={12} className="animate-spin mr-1" /> : <Copy size={12} className="mr-1" />}
 Copy ticket summary
 </Button>
 <Button
 size="sm" variant="outline" asChild
 className="border-zinc-200 text-white h-8 text-xs hover:bg-zinc-100"
 data-testid="sup-case-download-summary"
 >
 <a href={`${apiBase}/summary.txt`} download>
 <FileText size={12} className="mr-1" /> Download .txt
 </a>
 </Button>
 <Button
 size="sm" variant="outline" asChild
 className="border-zinc-200 text-white h-8 text-xs hover:bg-zinc-100"
 data-testid="sup-case-download-vcf"
 >
 <a href={`${apiBase}/contact.vcf`} download>
 <ContactRound size={12} className="mr-1" /> Save site contact (vCard)
 </a>
 </Button>
 </div>
 </div>
 </Card>
 );
}

/* ═══ COMMENTS SECTION ═══ */
function CommentsSection({ token, comments, onRefresh, caseData, isGymViewer }) {
 const [message, setMessage] = useState('');
 const [file, setFile] = useState(null);
 const [sending, setSending] = useState(false);
 const [authorName, setAuthorName] = useState('');
 const [nameConfirmed, setNameConfirmed] = useState(false);
 const fileRef = useRef(null);
 const bottomRef = useRef(null);

 useEffect(() => {
 bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
 }, [comments]);

 const sendComment = async () => {
 if (!message.trim() && !file) return;
 setSending(true);
 try {
 const fd = new FormData();
 fd.append('message', message.trim());
 // Attribution note: if the viewer is an authenticated gym user (they
 // followed the "Supplier Card" link from their own dashboard), the
 // backend forces author_role="gym" regardless of what we send.
 // Submitting "supplier" here keeps the public-link flow identical
 // for real suppliers responding from the unauthenticated email link.
 fd.append('author_name', authorName || caseData?.supplier_name || 'Supplier');
 fd.append('author_role', 'supplier');
 if (file) fd.append('file', file);
 // If a gym JWT is present in localStorage, include it so the backend
 // can identify the gym user and attribute the comment correctly.
 const gymToken = typeof window !== 'undefined' ? localStorage.getItem('token') : '';
 const headers = { 'Content-Type': 'multipart/form-data' };
 if (gymToken) headers.Authorization = `Bearer ${gymToken}`;
 await axios.post(`${API}/api/supplier/case/${token}/comments`, fd, { headers });
 setMessage('');
 setFile(null);
 if (fileRef.current) fileRef.current.value = '';
 onRefresh();
 } catch (e) {
 alert(e.response?.data?.detail || 'Failed to send');
 }
 setSending(false);
 };

 const handleKeyDown = (e) => {
 if (e.key === 'Enter' && !e.shiftKey) {
 e.preventDefault();
 sendComment();
 }
 };

 return (
 <Card className="bg-white border-zinc-200 p-0 overflow-hidden" data-testid="comments-section">
 <div className="px-6 py-4 border-b border-zinc-100 flex items-center gap-2">
 <MessageCircle size={18} className="text-[var(--color-brand-blue)]" />
 <h2 className="text-zinc-900 font-semibold text-lg">Messages</h2>
 <span className="text-zinc-500 text-sm ml-1">({comments.length})</span>
 </div>

 {/* Messages */}
 <div className="max-h-[400px] overflow-y-auto p-4 space-y-3" data-testid="comments-list">
 {comments.length === 0 && (
 <p className="text-center text-zinc-400 text-sm py-8">No messages yet. Start the conversation below.</p>
 )}
 {comments.map((c) => {
 const isSupplier = c.author_role === 'supplier';
 const isSeenByRecipient = isSupplier && c.read_at_gym;
 return (
 <div key={c.id} className={`flex ${isSupplier ? 'justify-end' : 'justify-start'}`} data-testid={`comment-${c.id}`}>
 <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${isSupplier ? 'rounded-br-sm' : 'rounded-bl-sm'}`}
 style={{ background: isSupplier ? 'var(--color-info-ios)' : 'var(--color-success-alt)', color: '#fff' }}>
 <div className="flex items-center gap-2 mb-1">
 {isSupplier ? <Wrench size={11} style={{ color: 'rgba(255,255,255,0.7)' }} /> : <Building2 size={11} style={{ color: 'rgba(255,255,255,0.7)' }} />}
 <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.7)' }}>
 {c.author_name || (isSupplier ? 'Supplier' : 'Site')}
 </span>
 <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.5)' }}>{new Date(c.created_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
 </div>
 {c.message && <p className="text-sm leading-relaxed" style={{ color: '#fff' }}>{c.message}</p>}
 {(c.attachments || []).map((a, i) => (
 <div key={i} className="mt-2">
 {a.content_type?.startsWith('image/') ? (
 <a href={a.download_url} target="_blank" rel="noreferrer">
 <img src={a.download_url} alt={a.filename} className="rounded-lg max-h-48 object-cover" />
 </a>
 ) : a.content_type?.startsWith('video/') ? (
 <video controls className="rounded-lg max-h-48 w-full"><source src={a.download_url} type={a.content_type} /></video>
 ) : (
 <a href={a.download_url} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-xs text-[var(--color-info-ios)] hover:underline">
 <Paperclip size={12} /> {a.filename}
 </a>
 )}
 </div>
 ))}
 {isSupplier && (
 <div
 className="flex justify-end mt-1.5 items-center"
 data-testid={`supplier-comment-receipt-${c.id}`}
 >
 <span
 className="text-[10px]"
 style={{ color: isSeenByRecipient ? 'var(--color-blue-100)' : 'rgba(255,255,255,0.55)' }}
 title={isSeenByRecipient ? `Seen by the site ${new Date(c.read_at_gym).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` : 'Delivered — not yet seen by the site'}
 >
 {isSeenByRecipient ? 'Seen ✓✓' : 'Sent ✓'}
 </span>
 </div>
 )}
 </div>
 </div>
 );
 })}
 <div ref={bottomRef} />
 </div>

 {/* Compose */}
 {isGymViewer ? (
 // Gym users viewing a supplier case from their own dashboard get a
 // read-only view with a pointer back to their own reply UI. The
 // backend will also force-correct attribution if they somehow post,
 // but the visual hint prevents the confusion in the first place.
 <div
 className="border-t border-zinc-200 p-4 bg-zinc-50"
 data-testid="gym-viewer-banner"
 >
 <div className="flex items-start gap-3">
 <div className="w-8 h-8 rounded-full bg-[var(--color-success-alt-2)]/15 border border-[var(--color-success-alt-2)]/30 flex items-center justify-center shrink-0">
 <Building2 size={14} className="text-[var(--color-success-alt-2)]" />
 </div>
 <div className="flex-1">
 <p className="text-sm font-medium text-zinc-900">You're viewing the supplier card</p>
 <p className="text-xs text-zinc-500 mt-1">
 To send a message to the supplier, close this tab and use the message box
 on the fault detail in your own dashboard — it'll be sent from your gym
 account and go straight to the supplier's email.
 </p>
 </div>
 </div>
 </div>
 ) : (
 <div className="border-t border-zinc-200 p-4">
 {!nameConfirmed ? (
 <div className="flex gap-2 mb-3">
 <Input
 placeholder="Enter your name to start messaging"
 value={authorName}
 onChange={e => setAuthorName(e.target.value)}
 onKeyDown={e => { if (e.key === 'Enter' && authorName.trim()) { e.preventDefault(); setNameConfirmed(true); } }}
 className="bg-zinc-50 border-zinc-200 text-zinc-800 text-sm h-9 flex-1"
 data-testid="comment-author-input"
 autoComplete="off"
 />
 <Button size="sm" disabled={!authorName.trim()} onClick={() => setNameConfirmed(true)}
 className="bg-[var(--color-info-ios)] text-white h-9 px-4" data-testid="confirm-name-btn">
 Continue
 </Button>
 </div>
 ) : (
 <div className="flex items-center gap-2 mb-3">
 <User size={13} className="text-[var(--color-info-ios)]" />
 <span className="text-zinc-900 text-sm font-medium">{authorName}</span>
 <button onClick={() => setNameConfirmed(false)} className="text-zinc-400 hover:text-zinc-800 text-xs ml-1">(change)</button>
 </div>
 )}
 {nameConfirmed && (
 <>
 {file && (
 <div className="flex items-center gap-2 mb-2 px-3 py-1.5 bg-[var(--color-surface-dark-2)] rounded-lg">
 <Paperclip size={13} className="text-[var(--color-info-ios)]" />
 <span className="text-xs text-zinc-800 truncate flex-1">{file.name}</span>
 <button onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = ''; }} className="text-zinc-500 hover:text-zinc-900">
 <X size={14} />
 </button>
 </div>
 )}
 <div className="flex items-end gap-2">
 <div className="flex-1 relative">
 <Textarea
 value={message}
 onChange={e => setMessage(e.target.value)}
 onKeyDown={handleKeyDown}
 placeholder="Type a message..."
 rows={1}
 className="bg-zinc-50 border-zinc-200 text-zinc-800 text-sm resize-none min-h-[40px] pr-10"
 data-testid="comment-input"
 />
 </div>
 <input type="file" ref={fileRef} onChange={e => setFile(e.target.files?.[0] || null)} className="hidden" accept="image/*,video/*,.pdf,.doc,.docx" />
 <Button variant="ghost" size="sm" onClick={() => fileRef.current?.click()} className="text-zinc-500 hover:text-zinc-900 px-2" data-testid="comment-attach-btn">
 <Camera size={18} />
 </Button>
 <Button onClick={sendComment} disabled={sending || (!message.trim() && !file)} size="sm"
 className="bg-[var(--color-info-ios)] text-white px-3 disabled:opacity-40" data-testid="comment-send-btn">
 {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
 </Button>
 </div>
 </>
 )}
 </div>
 )}
 </Card>
 );
}


/* ═══ SCHEDULE VISIT ═══ */
function ScheduleVisit({ token, caseData, onRefresh }) {
 const [showForm, setShowForm] = useState(false);
 const [form, setForm] = useState({ scheduled_date: '', engineer_name: '', notes: '' });
 const [saving, setSaving] = useState(false);

 const handleSubmit = async () => {
 if (!form.scheduled_date) return;
 setSaving(true);
 try {
 await axios.post(`${API}/api/supplier/case/${token}/schedule`, form);
 setShowForm(false);
 onRefresh();
 } catch (e) {
 alert(e.response?.data?.detail || 'Failed');
 }
 setSaving(false);
 };

 if (caseData.scheduled_date && caseData.current_status !== 'completed') {
 return (
 <Card className="bg-purple-500/5 border-purple-500/20 p-5" data-testid="scheduled-visit-card">
 <div className="flex items-center gap-3">
 <Calendar size={20} className="text-purple-400" />
 <div>
 <p className="text-purple-400 font-semibold text-sm">Engineer Visit Scheduled</p>
 <p className="text-zinc-900 font-medium">{new Date(caseData.scheduled_date).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</p>
 {caseData.engineer_name && <p className="text-zinc-500 text-xs mt-0.5">Engineer: {caseData.engineer_name}</p>}
 </div>
 <Button variant="outline" size="sm" className="ml-auto border-purple-500/30 text-purple-400 text-xs" onClick={() => setShowForm(true)} data-testid="reschedule-btn">
 Reschedule
 </Button>
 </div>
 </Card>
 );
 }

 if (!showForm) {
 return (
 <Card className="bg-white border-zinc-200 p-5 text-center" data-testid="schedule-prompt">
 <Calendar size={28} className="mx-auto mb-2 text-purple-400" />
 <p className="text-zinc-900 font-medium mb-1">Schedule an Engineer Visit</p>
 <p className="text-zinc-500 text-xs mb-3">Select a date and assign an engineer</p>
 <Button onClick={() => setShowForm(true)} className="bg-purple-600 hover:bg-purple-500 text-white" data-testid="schedule-visit-btn">
 <Calendar size={15} className="mr-1.5" /> Schedule Visit
 </Button>
 </Card>
 );
 }

 return (
 <Card className="bg-white border-zinc-200 p-5" data-testid="schedule-form">
 <h3 className="text-zinc-900 font-semibold mb-3 flex items-center gap-2"><Calendar size={16} className="text-purple-400" /> Schedule Engineer Visit</h3>
 <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
 <div>
 <Label className="text-zinc-800 text-xs">Visit Date *</Label>
 <Input type="date" value={form.scheduled_date} onChange={e => setForm({ ...form, scheduled_date: e.target.value })}
 className="bg-zinc-50 border-zinc-200 text-zinc-900 mt-1" data-testid="schedule-date-input" />
 </div>
 <div>
 <Label className="text-zinc-800 text-xs">Engineer Name</Label>
 <Input value={form.engineer_name} onChange={e => setForm({ ...form, engineer_name: e.target.value })} placeholder="Engineer name"
 className="bg-zinc-50 border-zinc-200 text-zinc-900 mt-1" data-testid="schedule-engineer-input" />
 </div>
 <div className="sm:col-span-2">
 <Label className="text-zinc-800 text-xs">Notes</Label>
 <Textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} placeholder="Any arrival notes..."
 rows={2} className="bg-zinc-50 border-zinc-200 text-zinc-900 mt-1 resize-none" />
 </div>
 </div>
 <div className="flex gap-2 mt-3">
 <Button onClick={handleSubmit} disabled={saving || !form.scheduled_date} className="bg-purple-600 text-white flex-1" data-testid="confirm-schedule-btn">
 {saving ? <Loader2 size={14} className="animate-spin mr-1" /> : <Calendar size={14} className="mr-1" />}
 {saving ? 'Scheduling...' : 'Confirm Schedule'}
 </Button>
 <Button variant="outline" onClick={() => setShowForm(false)} className="border-zinc-200 text-zinc-500">Cancel</Button>
 </div>
 </Card>
 );
}


/* ═══ RATING ═══ */
function RatingSection({ token, caseData, onRefresh }) {
 const [rating, setRating] = useState(0);
 const [hover, setHover] = useState(0);
 const [feedback, setFeedback] = useState('');
 const [saving, setSaving] = useState(false);

 if (caseData.rating) {
 return (
 <Card className="bg-white border-zinc-200 p-5 text-center" data-testid="rating-done">
 <div className="flex justify-center gap-1 mb-2">
 {[1, 2, 3, 4, 5].map(s => <Star key={s} size={22} className={s <= caseData.rating ? 'text-amber-400 fill-amber-400' : 'text-[#333]'} />)}
 </div>
 <p className="text-zinc-500 text-sm">Thank you for your feedback</p>
 {caseData.rating_feedback && <p className="text-zinc-500 text-xs mt-1 italic">"{caseData.rating_feedback}"</p>}
 </Card>
 );
 }

 if (caseData.current_status !== 'completed') return null;

 const submit = async () => {
 if (!rating) return;
 setSaving(true);
 try {
 await axios.post(`${API}/api/supplier/case/${token}/rate`, { rating, feedback });
 onRefresh();
 } catch (e) { alert('Failed to submit rating'); }
 setSaving(false);
 };

 return (
 <Card className="bg-white border-zinc-200 p-5 text-center" data-testid="rating-form">
 <p className="text-zinc-900 font-semibold mb-2">How was the service?</p>
 <div className="flex justify-center gap-1 mb-3">
 {[1, 2, 3, 4, 5].map(s => (
 <button key={s} onMouseEnter={() => setHover(s)} onMouseLeave={() => setHover(0)} onClick={() => setRating(s)} className="p-0.5" data-testid={`star-${s}`}>
 <Star size={28} className={`transition-colors ${s <= (hover || rating) ? 'text-amber-400 fill-amber-400' : 'text-[#333]'}`} />
 </button>
 ))}
 </div>
 <Textarea value={feedback} onChange={e => setFeedback(e.target.value)} placeholder="Optional feedback..." rows={2}
 className="bg-zinc-50 border-zinc-200 text-zinc-800 text-sm resize-none mb-3" />
 <Button onClick={submit} disabled={saving || !rating} className="bg-amber-500 hover:bg-amber-400 text-black font-semibold" data-testid="submit-rating-btn">
 {saving ? 'Submitting...' : 'Submit Rating'}
 </Button>
 </Card>
 );
}


/* ═══ MAIN PAGE ═══ */
const SupplierCasePage = () => {
 const { token } = useParams();
 const [caseData, setCaseData] = useState(null);
 const [loading, setLoading] = useState(true);
 const [error, setError] = useState(null);
 const [updating, setUpdating] = useState(false);
 const [showUpdateForm, setShowUpdateForm] = useState(false);
 const [showHistory, setShowHistory] = useState(false);
 const [formData, setFormData] = useState({ status: '', notes: '', engineer_name: '', estimated_arrival: '', parts_required: '' });
 const [updateSuccess, setUpdateSuccess] = useState(false);

 const loadCase = async () => {
 try {
 const res = await axios.get(`${API}/api/supplier/case/${token}`);
 setCaseData(res.data);
 } catch (err) {
 setError(err.response?.status === 404 ? 'This case link is invalid or has expired.' : 'Failed to load case details.');
 } finally {
 setLoading(false);
 }
 };

 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
 useEffect(() => { loadCase(); }, [token]);

 const handleUpdate = async () => {
 if (!formData.status) return;
 setUpdating(true);
 try {
 await axios.post(`${API}/api/supplier/case/${token}/update`, formData);
 setUpdateSuccess(true);
 setShowUpdateForm(false);
 loadCase();
 setTimeout(() => setUpdateSuccess(false), 5000);
 } catch (err) {
 alert(err.response?.data?.detail || 'Update failed');
 } finally {
 setUpdating(false);
 }
 };

 const getStatusBadge = (status) => {
 const s = STATUS_FLOW.find(sf => sf.value === status) || { label: status, color: 'bg-white/10 text-zinc-500' };
 return <Badge className={s.color}>{s.label}</Badge>;
 };

 const getSeverityColor = (sev) => {
 if (sev === 'critical') return 'text-red-400 bg-red-500/10 border-red-500/30';
 if (sev === 'medium') return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30';
 return 'text-green-400 bg-green-500/10 border-green-500/30';
 };

 if (loading) return <div className="min-h-screen bg-zinc-50 flex items-center justify-center"><Loader2 size={32} className="text-[var(--color-brand-blue)] animate-spin" /></div>;

 if (error) {
 return (
 <div className="min-h-screen bg-zinc-50 flex items-center justify-center p-4">
 <Card className="bg-white border-zinc-200 p-8 max-w-md text-center">
 <AlertTriangle size={48} className="mx-auto mb-4 text-red-400" />
 <h2 className="text-zinc-900 text-xl font-semibold mb-2">Case Not Found</h2>
 <p className="text-zinc-500">{error}</p>
 </Card>
 </div>
 );
 }

 const { issue, equipment, media, status_history, current_status, organization_name, _supplier_name, comments, reporter, site, job_ref, platform_name, platform_tagline, is_pulse_branded, brand_color, logo_url } = caseData;

 // A gym user is viewing this page via the "Supplier Card" link in their
 // own dashboard (they're authenticated with a JWT). Pass this down so the
 // compose UI hides + they see a "use your dashboard to reply" banner.
 const isGymViewer = typeof window !== 'undefined' && Boolean(localStorage.getItem('token'));

 // Build a custom gradient from the org brand colour (falls back to the default Pulse/GymAxis blue)
 const primary = brand_color || 'var(--color-brand-blue)';
 const shade = (hex, amt) => {
 try {
 const h = hex.replace('#', '');
 const n = parseInt(h, 16);
 const r = Math.max(0, Math.min(255, ((n >> 16) & 0xff) + amt));
 const g = Math.max(0, Math.min(255, ((n >> 8) & 0xff) + amt));
 const b = Math.max(0, Math.min(255, (n & 0xff) + amt));
 return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
 } catch { return hex; }
 };
 const darker = shade(primary, -55);
 const headerGradient = `linear-gradient(to right, ${primary}, ${darker})`;

 // Status progress bar
 const activeIdx = STATUS_FLOW.findIndex(s => s.value === current_status);

 return (
 <div className="min-h-screen bg-zinc-50 text-zinc-900" data-theme="light" data-testid="supplier-case-page">
 {/* Header — uses the gym's own brand colour when available */}
 <div className="px-6 py-5" style={{ background: headerGradient }} data-testid="supplier-case-header">
 <div className="max-w-4xl mx-auto">
 <div className="flex items-center justify-between gap-3">
 <div className="flex items-center gap-3 min-w-0">
 {logo_url && (
 <img src={logo_url} alt={`${platform_name} logo`}
 className="h-10 w-10 rounded bg-white/90 p-1 object-contain shrink-0"
 data-testid="supplier-case-logo"
 onError={(e) => { e.target.style.display = 'none'; }} />
 )}
 <div className="min-w-0">
 <h1 className="text-zinc-900 text-xl font-bold truncate">{platform_name || 'GymAxis AI'}</h1>
 <p className="text-zinc-600 text-sm truncate">{organization_name} &middot; {platform_tagline || 'Service Case'}</p>
 </div>
 </div>
 {getStatusBadge(current_status)}
 </div>
 {/* Progress Steps */}
 <div className="flex items-center gap-0 mt-4 overflow-x-auto">
 {STATUS_FLOW.map((s, i) => {
 const done = i <= activeIdx;
 const Icon = s.icon;
 return (
 <React.Fragment key={s.value}>
 {i > 0 && <div className={`h-0.5 flex-1 min-w-[16px] ${done ? 'bg-white/60' : 'bg-white/15'}`} />}
 <div className={`flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-medium whitespace-nowrap ${done ? 'bg-white/20 text-white' : 'bg-white/5 text-white/30'}`}>
 <Icon size={11} /> {s.label}
 </div>
 </React.Fragment>
 );
 })}
 </div>
 </div>
 </div>

 <div className="max-w-4xl mx-auto p-4 sm:p-6 space-y-5">
 {updateSuccess && (
 <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 flex items-center gap-3" data-testid="update-success">
 <CheckCircle size={20} className="text-green-400" />
 <span className="text-green-400">Status updated successfully</span>
 </div>
 )}

 {/* Schedule Visit (prominent) */}
 {current_status !== 'completed' && (
 <ScheduleVisit token={token} caseData={caseData} onRefresh={loadCase} />
 )}

 {/* Fault Details */}
 <Card className="bg-white border-zinc-200 p-5" data-testid="fault-details-card">
 <h2 className="text-zinc-900 font-semibold text-lg mb-4 flex items-center gap-2">
 <Wrench size={18} className="text-[var(--color-brand-blue)]" /> Fault Details
 {job_ref && (
 <span
 className="ml-2 inline-flex items-center text-[11px] font-mono tracking-wider px-2 py-0.5 rounded border border-zinc-200 bg-zinc-50 text-zinc-500"
 data-testid="sup-case-job-ref"
 >
 {job_ref}
 </span>
 )}
 </h2>
 <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
 <div><p className="text-zinc-500 text-[10px] uppercase tracking-wider">Equipment</p><p className="text-zinc-900 font-medium text-sm">{issue.machine_type}</p></div>
 <div><p className="text-zinc-500 text-[10px] uppercase tracking-wider">Serial</p><p className="text-zinc-800 text-sm">{issue.serial_number || 'N/A'}</p></div>
 <div><p className="text-zinc-500 text-[10px] uppercase tracking-wider">Severity</p><Badge className={`${getSeverityColor(issue.severity)} border text-xs`}>{issue.severity?.toUpperCase()}</Badge></div>
 <div><p className="text-zinc-500 text-[10px] uppercase tracking-wider">Reported</p><p className="text-zinc-800 text-sm">{issue.created_at ? new Date(issue.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : 'N/A'}</p></div>
 </div>
 <div className="mt-4 p-4 bg-zinc-50 rounded-lg border border-zinc-100">
 <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-1">Description</p>
 <p className="text-zinc-800 text-sm leading-relaxed whitespace-pre-wrap">{issue.issue_description}</p>
 </div>
 {issue.ai_triage?.likely_cause && (
 <div className="mt-3 p-4 bg-blue-500/5 rounded-lg border border-blue-500/20" data-testid="sup-case-ai-triage">
 <p className="text-blue-300 text-[10px] uppercase tracking-wider mb-1 flex items-center gap-1">
 <AlertTriangle size={11} /> AI Triage
 </p>
 <p className="text-zinc-800 text-sm leading-relaxed"><strong>Likely cause:</strong> {issue.ai_triage.likely_cause}</p>
 {issue.ai_triage.recommended_action && (
 <p className="text-zinc-800 text-sm leading-relaxed mt-1"><strong>Suggested:</strong> {issue.ai_triage.recommended_action}</p>
 )}
 </div>
 )}

 {/* Job Card snapshot — mirrors the gym-side compact tile */}
 {issue.sicon_case_id && (
 <div className="mt-4 p-4 rounded-lg border border-[rgb(var(--rgb-brand-blue)/0.3)] bg-[rgb(var(--rgb-brand-blue)/0.1)]"
 data-testid="sup-case-job-card">
 <div className="flex items-center justify-between flex-wrap gap-2">
 <div className="flex items-center gap-2">
 <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-brand-cyan-hover)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>
 <p className="text-zinc-900 font-semibold text-sm">Job Card</p>
 <span className="font-mono text-[11px] text-zinc-500">
 {issue.sicon_case_number || `#${issue.sicon_case_id}`}
 </span>
 </div>
 <div className="flex items-center gap-2">
 {issue.sicon_priority && (
 <Badge className="bg-amber-500/15 text-amber-400 border border-amber-500/30 text-[10px]">{issue.sicon_priority}</Badge>
 )}
 {issue.sicon_status && (
 <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.15)] text-[var(--color-brand-cyan-hover)] border border-[rgb(var(--rgb-brand-blue)/0.3)] text-[10px]">{issue.sicon_status}</Badge>
 )}
 </div>
 </div>
 <div className="grid grid-cols-2 gap-4 mt-3 text-xs">
 {(issue.sicon_assigned_to || (issue.sicon_appointments?.[0]?.employee_ids || []).length > 0) && (
 <div>
 <p className="text-zinc-500 text-[10px] uppercase tracking-wider">Engineer</p>
 <p className="text-zinc-900 font-medium" data-testid="sup-case-job-engineer">
 {issue.sicon_assigned_to || 'Assigned — see Pulse Fitness'}
 </p>
 </div>
 )}
 {(() => {
 const next = (issue.sicon_appointments || []).find(a => !a.appointment_complete) || (issue.sicon_appointments || []).slice(-1)[0];
 if (!next?.scheduled_start) return null;
 return (
 <div>
 <p className="text-zinc-500 text-[10px] uppercase tracking-wider">Scheduled</p>
 <p className="text-zinc-900 font-medium" data-testid="sup-case-job-scheduled">
 {new Date(next.scheduled_start).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
 {' '}
 {new Date(next.scheduled_start).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
 </p>
 </div>
 );
 })()}
 {issue.sicon_sub_location_description && (
 <div className="col-span-2">
 <p className="text-zinc-500 text-[10px] uppercase tracking-wider">Location on site</p>
 <p className="text-zinc-900 font-medium">
 {issue.sicon_sub_location_description}
 {issue.sicon_sub_location_comment && <span className="text-zinc-500"> · {issue.sicon_sub_location_comment}</span>}
 </p>
 </div>
 )}
 </div>
 </div>
 )}
 </Card>

 {/* Gym contact & address — for "create by email" workflows */}
 {(reporter || site) && (
 <SiteContactCard reporter={reporter} site={site} organizationName={organization_name} token={token} jobRef={job_ref} issue={issue} />
 )}

 {/* Equipment */}
 {equipment && (
 <Card className="bg-white border-zinc-200 p-5" data-testid="equipment-info-card">
 <h2 className="text-zinc-900 font-semibold text-lg mb-3 flex items-center gap-2"><Shield size={18} className="text-[var(--color-brand-blue)]" /> Equipment</h2>
 <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
 {equipment.name && <div><p className="text-zinc-500 text-[10px] uppercase">Name</p><p className="text-zinc-900">{equipment.name}</p></div>}
 {equipment.manufacturer && <div><p className="text-zinc-500 text-[10px] uppercase">Manufacturer</p><p className="text-zinc-900">{equipment.manufacturer}</p></div>}
 {equipment.model && <div><p className="text-zinc-500 text-[10px] uppercase">Model</p><p className="text-zinc-900">{equipment.model}</p></div>}
 {equipment.supplier && <div data-testid="sup-case-equip-supplier"><p className="text-zinc-500 text-[10px] uppercase">Supplier</p><p className="text-indigo-400">{equipment.supplier}</p></div>}
 {equipment.location && <div className="col-span-2"><p className="text-zinc-500 text-[10px] uppercase flex items-center gap-1"><MapPin size={10} /> Location</p><p className="text-zinc-900">{equipment.location}</p></div>}
 </div>
 </Card>
 )}

 {/* Photos & Videos from fault */}
 {media && media.length > 0 && (
 <Card className="bg-white border-zinc-200 p-5" data-testid="media-card">
 <h2 className="text-zinc-900 font-semibold text-lg mb-3 flex items-center gap-2"><Image size={18} className="text-[var(--color-brand-blue)]" /> Fault Photos & Videos</h2>
 <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
 {media.map((item, idx) => (
 <div key={idx} className="rounded-lg overflow-hidden bg-zinc-50 border border-zinc-200">
 {item.content_type?.startsWith('video/') ? (
 <video controls className="w-full"><source src={item.download_url} type={item.content_type} /></video>
 ) : (
 <a href={item.download_url} target="_blank" rel="noreferrer">
 <img src={item.download_url} alt={item.filename || `Photo ${idx + 1}`} className="w-full h-36 object-cover" />
 </a>
 )}
 </div>
 ))}
 </div>
 </Card>
 )}

 {/* TWO-WAY COMMENTS */}
 <CommentsSection token={token} comments={comments || []} onRefresh={loadCase} caseData={caseData} isGymViewer={isGymViewer} />

 {/* Status History */}
 {status_history && status_history.length > 0 && (
 <Card className="bg-white border-zinc-200 p-5" data-testid="status-history-card">
 <button className="w-full flex items-center justify-between text-left" onClick={() => setShowHistory(!showHistory)}>
 <h2 className="text-zinc-900 font-semibold text-base flex items-center gap-2">
 <Clock size={16} className="text-[var(--color-brand-blue)]" /> Status History ({status_history.length})
 </h2>
 {showHistory ? <ChevronUp size={16} className="text-zinc-500" /> : <ChevronDown size={16} className="text-zinc-500" />}
 </button>
 {showHistory && (
 <div className="mt-3 space-y-2">
 {status_history.map((entry, idx) => (
 <div key={idx} className="flex gap-3 p-3 bg-zinc-50 rounded-lg border border-zinc-100">
 <div className="w-2 h-2 rounded-full bg-[var(--color-brand-blue)] mt-1.5 flex-shrink-0" />
 <div className="flex-1">
 <div className="flex items-center gap-2 mb-0.5">{getStatusBadge(entry.status)} <span className="text-zinc-400 text-[10px]">{entry.updated_at ? new Date(entry.updated_at).toLocaleString('en-GB') : ''}</span></div>
 {entry.engineer_name && <p className="text-zinc-800 text-xs">Engineer: {entry.engineer_name}</p>}
 {entry.scheduled_date && <p className="text-purple-400 text-xs">Scheduled: {new Date(entry.scheduled_date).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}</p>}
 {entry.notes && <p className="text-[#888] text-xs mt-0.5">{entry.notes}</p>}
 </div>
 </div>
 ))}
 </div>
 )}
 </Card>
 )}

 {/* Update Status */}
 {current_status !== 'completed' && (
 <Card className="bg-white border-zinc-200 p-5" data-testid="update-status-card">
 {!showUpdateForm ? (
 <div className="text-center">
 <Button onClick={() => setShowUpdateForm(true)} className="bg-[var(--color-brand-blue)] text-white px-8" data-testid="show-update-btn">
 Update Case Status
 </Button>
 </div>
 ) : (
 <div className="space-y-4">
 <h2 className="text-zinc-900 font-semibold text-lg">Update Status</h2>
 <div>
 <Label className="text-zinc-800 text-sm">New Status</Label>
 <Select value={formData.status} onValueChange={val => setFormData({ ...formData, status: val })}>
 <SelectTrigger className="bg-zinc-50 border-zinc-200 text-zinc-900 mt-1" data-testid="status-select"><SelectValue placeholder="Select status" /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 {STATUS_FLOW.filter(s => s.value !== 'pending').map(s => <SelectItem key={s.value} value={s.value} className="text-white">{s.label}</SelectItem>)}
 </SelectContent>
 </Select>
 </div>
 {formData.status === 'parts_ordered' && (
 <div><Label className="text-zinc-800 text-sm">Parts Required</Label><Textarea value={formData.parts_required} onChange={e => setFormData({ ...formData, parts_required: e.target.value })} placeholder="List parts..." rows={2} className="bg-zinc-50 border-zinc-200 text-zinc-900 mt-1" /></div>
 )}
 <div><Label className="text-zinc-800 text-sm">Notes</Label><Textarea value={formData.notes} onChange={e => setFormData({ ...formData, notes: e.target.value })} placeholder="Additional notes..." rows={2} className="bg-zinc-50 border-zinc-200 text-zinc-900 mt-1" data-testid="notes-input" /></div>
 <div className="flex gap-3">
 <Button onClick={handleUpdate} disabled={updating || !formData.status} className="bg-[var(--color-brand-blue)] text-white flex-1" data-testid="submit-update-btn">
 {updating ? <Loader2 size={16} className="animate-spin mr-2" /> : null}{updating ? 'Updating...' : 'Submit Update'}
 </Button>
 <Button variant="outline" onClick={() => setShowUpdateForm(false)} className="border-zinc-200 text-zinc-500">Cancel</Button>
 </div>
 </div>
 )}
 </Card>
 )}

 {/* Completed + Rating */}
 {current_status === 'completed' && (
 <Card className="bg-green-500/5 border-green-500/20 p-5 text-center" data-testid="case-completed">
 <CheckCircle size={28} className="mx-auto mb-2 text-green-400" />
 <h2 className="text-green-400 font-semibold text-lg">Case Completed</h2>
 <p className="text-zinc-500 text-sm mt-1">This fault has been marked as resolved.</p>
 </Card>
 )}

 <RatingSection token={token} caseData={caseData} onRefresh={loadCase} />

 <p className="text-center text-[#444] text-xs pb-4">
 Powered by {is_pulse_branded ? (platform_name || 'Pulse Fitness') : 'GymAxis AI'}
 </p>
 </div>
 </div>
 );
};

export default SupplierCasePage;
