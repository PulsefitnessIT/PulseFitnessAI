/**
 * Communications Inbox — Master Admin (Iter 216h94).
 *
 * Centralised feed of every sales enquiry submitted through the public
 * marketing contact form. Operators can:
 *
 *  · filter by status (new / read / replied / closed) or interest area,
 *  · click any row to see the full enquiry and reply timeline,
 *  · send a reply via Resend (server appends to `replies[]` + sets
 *    status → replied),
 *  · attach private internal notes,
 *  · close / re-open the row.
 *
 * The list view is intentionally dense — Master Admin operators are
 * power users and we optimise for triage speed (status pill + email +
 * preview snippet + relative time) over visual polish.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Inbox, RefreshCw, Search, Mail, MailOpen, Reply, CheckCircle2,
  ChevronRight, Send, X, Phone, Building2, Clock, Sparkles,
  AlertTriangle, Hourglass, UserCircle2, FileText,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_META = {
  new:     { label: 'New',     pill: 'bg-blue-50 text-blue-700 border-blue-200',     icon: Mail },
  read:    { label: 'Read',    pill: 'bg-slate-50 text-slate-700 border-slate-200',  icon: MailOpen },
  replied: { label: 'Replied', pill: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: Reply },
  closed:  { label: 'Closed',  pill: 'bg-zinc-100 text-zinc-600 border-zinc-200',    icon: CheckCircle2 },
};
const STATUS_TABS = ['new', 'read', 'replied', 'closed'];

const INTEREST_LABELS = {
  memberships: 'Memberships', service_desk: 'Service Desk',
  engineers: 'Engineers', marketing: 'Marketing', crm: 'CRM',
  pricing: 'Pricing', other: 'Other',
};

function relativeTime(iso) {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - then);
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

function authHeader() {
  const token = localStorage.getItem('gymaxis_token') || localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export default function AdminCommunications() {
  const [summary, setSummary] = useState({ total: 0, by_status: { new: 0, read: 0, replied: 0, closed: 0 } });
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('new');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (search.trim()) params.search = search.trim();
      const [listRes, sumRes] = await Promise.all([
        axios.get(`${API}/master-admin/communications`, { params, headers: authHeader() }),
        axios.get(`${API}/master-admin/communications/summary`, { headers: authHeader() }),
      ]);
      setItems(listRes.data?.items || []);
      setSummary(sumRes.data || { total: 0, by_status: {} });
    } catch (e) {
      toast.error('Failed to load communications inbox');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, search]);

  useEffect(() => { fetchList(); }, [fetchList]);

  return (
    <div className="space-y-5" data-testid="admin-communications">
      <Header summary={summary} statusFilter={statusFilter} setStatusFilter={setStatusFilter} onRefresh={fetchList} loading={loading} />
      <SearchBar search={search} setSearch={setSearch} />
      <ListView items={items} loading={loading} onPick={setSelectedId} />
      {selectedId && (
        <DetailDrawer
          enquiryId={selectedId}
          onClose={() => setSelectedId(null)}
          onAfterMutate={fetchList}
        />
      )}
    </div>
  );
}

function Header({ summary, statusFilter, setStatusFilter, onRefresh, loading }) {
  const slaWarn = summary?.sla?.warning || 0;
  const slaBreach = summary?.sla?.breached || 0;
  return (
    <div className="bg-white border border-zinc-200 rounded-2xl p-5 shadow-sm">
      <div className="flex items-center justify-between gap-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-blue-50">
            <Inbox size={18} className="text-blue-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-zinc-900">Communications inbox</h2>
            <p className="text-xs text-zinc-500">Every sales enquiry from the public marketing site lands here.</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {(slaWarn > 0 || slaBreach > 0) && (
            <div className="flex items-center gap-2 text-[11px] font-semibold" data-testid="comms-sla-roll-up">
              {slaWarn > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200 px-2 py-0.5">
                  <Hourglass size={10} /> {slaWarn} warning
                </span>
              )}
              {slaBreach > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 text-rose-700 border border-rose-200 px-2 py-0.5">
                  <AlertTriangle size={10} /> {slaBreach} breached
                </span>
              )}
            </div>
          )}
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-zinc-700 hover:text-zinc-900 disabled:opacity-50"
            data-testid="comms-refresh"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2" role="tablist">
        {STATUS_TABS.map((s) => {
          const meta = STATUS_META[s];
          const Icon = meta.icon;
          const active = statusFilter === s;
          const count = summary.by_status?.[s] ?? 0;
          return (
            <button
              key={s}
              type="button"
              role="tab"
              onClick={() => setStatusFilter(s)}
              className="inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-semibold border transition whitespace-nowrap"
              style={active
                ? { background: '#0F172A', color: '#FFFFFF', borderColor: '#0F172A' }
                : { background: '#FFFFFF', color: '#3F3F46', borderColor: '#E4E4E7' }
              }
              data-testid={`comms-tab-${s}`}
            >
              <Icon size={12} color={active ? '#FFFFFF' : '#3F3F46'} />
              <span style={{ color: active ? '#FFFFFF' : '#3F3F46' }}>{meta.label}</span>
              <span
                className="inline-flex items-center justify-center rounded-full min-w-[20px] px-1.5 text-[11px] font-bold"
                style={active
                  ? { background: 'rgba(255,255,255,0.20)', color: '#FFFFFF' }
                  : { background: '#F4F4F5', color: '#3F3F46' }
                }
              >{count}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SearchBar({ search, setSearch }) {
  return (
    <div className="relative">
      <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-400" />
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by name, email, company, message"
        className="w-full rounded-xl border border-zinc-200 bg-white pl-10 pr-3 py-2.5 text-sm focus:outline-none focus:border-zinc-400"
        data-testid="comms-search"
      />
    </div>
  );
}

function ListView({ items, loading, onPick }) {
  if (!loading && items.length === 0) {
    return (
      <div className="bg-white border border-zinc-200 rounded-2xl py-16 text-center" data-testid="comms-empty">
        <Inbox size={36} className="mx-auto text-zinc-300" />
        <p className="mt-3 text-sm text-zinc-500">No enquiries match this filter — try a different status or clear the search.</p>
      </div>
    );
  }
  return (
    <div className="bg-white border border-zinc-200 rounded-2xl overflow-hidden">
      <div className="divide-y divide-zinc-100" data-testid="comms-list">
        {items.map((it) => {
          const meta = STATUS_META[it.status] || STATUS_META.new;
          return (
            <button
              key={it.id}
              type="button"
              onClick={() => onPick(it.id)}
              className="w-full text-left px-5 py-4 flex items-start gap-4 hover:bg-zinc-50 transition"
              data-testid={`comms-row-${it.id}`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-zinc-900 truncate">{it.name}</span>
                  <span className="text-xs text-zinc-500 truncate">{it.email}</span>
                  {it.company && (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-zinc-500">
                      <Building2 size={10} /> {it.company}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm text-zinc-600 line-clamp-2">{it.preview}</p>
                <div className="mt-2 flex items-center gap-3 text-[11px] text-zinc-400 flex-wrap">
                  <span>{relativeTime(it.created_at)}</span>
                  {it.interest && <span className="rounded-full bg-zinc-50 px-2 py-0.5 text-zinc-600 border border-zinc-200">{INTEREST_LABELS[it.interest] || it.interest}</span>}
                  {it.assigned_to && (
                    <span className="inline-flex items-center gap-1 text-zinc-600 font-semibold">
                      <UserCircle2 size={11} className="text-zinc-400" />{it.assigned_to.split('@')[0]}
                    </span>
                  )}
                  {it.sla === 'warning' && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 font-semibold">
                      <Hourglass size={10} /> SLA warning · {Math.floor(it.hours_open)}h
                    </span>
                  )}
                  {it.sla === 'breached' && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 text-rose-700 border border-rose-200 px-2 py-0.5 font-semibold">
                      <AlertTriangle size={10} /> SLA breached · {Math.floor(it.hours_open)}h
                    </span>
                  )}
                  {it.reply_count > 0 && <span className="inline-flex items-center gap-1 text-emerald-600 font-semibold"><Reply size={10} />{it.reply_count}</span>}
                </div>
              </div>
              <div className="flex flex-col items-end gap-2 flex-shrink-0">
                <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${meta.pill}`}>
                  {meta.label}
                </span>
                <ChevronRight size={14} className="text-zinc-300" />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function DetailDrawer({ enquiryId, onClose, onAfterMutate }) {
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reply, setReply] = useState({ subject: '', body: '' });
  const [sending, setSending] = useState(false);
  const [internalNotes, setInternalNotes] = useState('');
  const [savingNotes, setSavingNotes] = useState(false);
  const [admins, setAdmins] = useState([]);
  const [canned, setCanned] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [docRes, settingsRes, cannedRes] = await Promise.all([
        axios.get(`${API}/master-admin/communications/${enquiryId}`, { headers: authHeader() }),
        axios.get(`${API}/master-admin/communications/settings`, { headers: authHeader() }),
        axios.get(`${API}/master-admin/canned-replies`, { headers: authHeader() }),
      ]);
      setDoc(docRes.data);
      setInternalNotes(docRes.data?.internal_notes || '');
      setAdmins(settingsRes.data?.admins || []);
      setCanned(cannedRes.data?.items || []);
      setReply({
        subject: `Re: your enquiry${docRes.data?.company ? ' — ' + docRes.data.company : ''}`,
        body: `Hi ${(docRes.data?.name || '').split(' ')[0] || 'there'},\n\nThanks for getting in touch with GymAxis.\n\n`,
      });
    } catch (e) {
      toast.error('Failed to load enquiry');
      onClose();
    } finally {
      setLoading(false);
    }
  }, [enquiryId, onClose]);

  useEffect(() => { load(); }, [load]);

  const sendReply = async () => {
    if (!reply.subject.trim() || !reply.body.trim()) {
      toast.error('Subject and message are required.');
      return;
    }
    setSending(true);
    try {
      await axios.post(`${API}/master-admin/communications/${enquiryId}/reply`, reply, { headers: authHeader() });
      toast.success('Reply sent.');
      await load();
      onAfterMutate?.();
    } catch (e) {
      const msg = e.response?.data?.detail || 'Failed to send reply';
      toast.error(msg);
    } finally {
      setSending(false);
    }
  };

  const updateStatus = async (status) => {
    try {
      await axios.patch(`${API}/master-admin/communications/${enquiryId}`, { status }, { headers: authHeader() });
      toast.success(`Marked as ${status}.`);
      await load();
      onAfterMutate?.();
    } catch (e) {
      toast.error('Failed to update status');
    }
  };

  const updateAssignee = async (email) => {
    try {
      await axios.patch(`${API}/master-admin/communications/${enquiryId}`, { assigned_to: email || '' }, { headers: authHeader() });
      toast.success(email ? `Assigned to ${email}` : 'Unassigned');
      await load();
      onAfterMutate?.();
    } catch (e) {
      const msg = e.response?.data?.detail || 'Failed to update assignee';
      toast.error(msg);
    }
  };

  const applyTemplate = (tplId) => {
    if (!tplId) return;
    const tpl = canned.find((c) => c.id === tplId);
    if (!tpl) return;
    setReply({ subject: tpl.subject, body: tpl.body });
    toast.success(`Loaded template: ${tpl.label}`);
  };

  const saveNotes = async () => {
    setSavingNotes(true);
    try {
      await axios.patch(`${API}/master-admin/communications/${enquiryId}`, { internal_notes: internalNotes }, { headers: authHeader() });
      toast.success('Notes saved.');
      await load();
    } catch (e) {
      toast.error('Failed to save notes');
    } finally {
      setSavingNotes(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex" data-testid="comms-detail-drawer">
      <button
        type="button"
        aria-label="Close enquiry"
        onClick={onClose}
        className="flex-1 bg-zinc-900/30 backdrop-blur-sm"
      />
      <div className="w-full max-w-2xl bg-white border-l border-zinc-200 overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-zinc-100 px-6 py-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-2">
            <Inbox size={16} className="text-blue-600" />
            <span className="text-sm font-semibold text-zinc-900">Enquiry detail</span>
          </div>
          <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-900" data-testid="comms-detail-close">
            <X size={18} />
          </button>
        </div>

        {loading || !doc ? (
          <div className="p-10 text-center text-sm text-zinc-500">Loading…</div>
        ) : (
          <div className="p-6 space-y-6">
            <EnquiryHeader doc={doc} updateStatus={updateStatus} />
            <AssigneePicker admins={admins} value={doc.assigned_to || ''} onChange={updateAssignee} />
            <EnquiryMeta doc={doc} />
            <MessageBlock doc={doc} />
            <ReplyTimeline doc={doc} />
            <ReplyComposer reply={reply} setReply={setReply} sending={sending} onSend={sendReply} canned={canned} applyTemplate={applyTemplate} />
            <InternalNotes value={internalNotes} setValue={setInternalNotes} onSave={saveNotes} saving={savingNotes} />
          </div>
        )}
      </div>
    </div>
  );
}

function AssigneePicker({ admins, value, onChange }) {
  return (
    <div className="rounded-xl border border-zinc-100 bg-white p-4" data-testid="comms-assignee">
      <div className="text-[10px] uppercase tracking-[0.12em] font-bold text-zinc-400 mb-2 flex items-center gap-1"><UserCircle2 size={11} /> Assignee</div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:border-zinc-400"
        data-testid="comms-assignee-select"
      >
        <option value="">Unassigned</option>
        {admins.map((a) => (
          <option key={a.email} value={a.email}>{a.name || a.email}</option>
        ))}
      </select>
      <p className="text-[11px] text-zinc-400 mt-1">Only Master Admins appear here. Choose &quot;Unassigned&quot; to clear.</p>
    </div>
  );
}

function EnquiryHeader({ doc, updateStatus }) {
  const meta = STATUS_META[doc.status] || STATUS_META.new;
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${meta.pill}`}>{meta.label}</span>
        <span className="text-xs text-zinc-400">{new Date(doc.created_at).toLocaleString()}</span>
      </div>
      <h3 className="text-xl font-bold text-zinc-900">{doc.name}</h3>
      <p className="text-sm text-zinc-500">{doc.email}{doc.company ? ` · ${doc.company}` : ''}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {doc.status !== 'closed' && (
          <button type="button" onClick={() => updateStatus('closed')} className="text-xs font-semibold inline-flex items-center gap-1 rounded-full border border-zinc-200 px-3 py-1 text-zinc-700 hover:bg-zinc-50" data-testid="comms-mark-closed">
            <CheckCircle2 size={11} /> Mark as closed
          </button>
        )}
        {doc.status === 'closed' && (
          <button type="button" onClick={() => updateStatus('read')} className="text-xs font-semibold inline-flex items-center gap-1 rounded-full border border-zinc-200 px-3 py-1 text-zinc-700 hover:bg-zinc-50" data-testid="comms-reopen">
            <Sparkles size={11} /> Re-open
          </button>
        )}
        <a href={`mailto:${doc.email}`} className="text-xs font-semibold inline-flex items-center gap-1 rounded-full border border-zinc-200 px-3 py-1 text-zinc-700 hover:bg-zinc-50">
          <Mail size={11} /> Email client
        </a>
      </div>
    </div>
  );
}

function EnquiryMeta({ doc }) {
  const rows = useMemo(() => [
    doc.phone && { icon: Phone, label: 'Phone', value: doc.phone },
    doc.gym_size && { icon: Building2, label: 'Gym size', value: doc.gym_size },
    doc.interest && { icon: Sparkles, label: 'Interest', value: INTEREST_LABELS[doc.interest] || doc.interest },
    doc.preferred_contact_time && { icon: Clock, label: 'Best time', value: doc.preferred_contact_time },
    doc.heard_from && { icon: Sparkles, label: 'Heard from', value: doc.heard_from.replace('_', ' ') },
  ].filter(Boolean), [doc]);
  if (rows.length === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-3" data-testid="comms-detail-meta">
      {rows.map((r, i) => {
        const Icon = r.icon;
        return (
          <div key={i} className="rounded-xl border border-zinc-100 bg-zinc-50/60 p-3">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.12em] font-bold text-zinc-400">
              <Icon size={10} /> {r.label}
            </div>
            <div className="mt-1 text-sm font-medium text-zinc-800 capitalize">{r.value}</div>
          </div>
        );
      })}
    </div>
  );
}

function MessageBlock({ doc }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-[0.12em] font-bold text-zinc-400 mb-2">Message</p>
      <div className="rounded-xl border border-zinc-100 bg-white p-4 text-sm text-zinc-700 whitespace-pre-wrap leading-relaxed" data-testid="comms-detail-message">
        {doc.message}
      </div>
    </div>
  );
}

function ReplyTimeline({ doc }) {
  const replies = doc.replies || [];
  if (replies.length === 0) return null;
  return (
    <div data-testid="comms-reply-timeline">
      <p className="text-[10px] uppercase tracking-[0.12em] font-bold text-zinc-400 mb-2">Replies sent ({replies.length})</p>
      <div className="space-y-3">
        {replies.map((r) => (
          <div key={r.id} className="rounded-xl border border-emerald-100 bg-emerald-50/40 p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold text-emerald-700">{r.subject}</span>
              <span className="text-[10px] text-zinc-400">{new Date(r.sent_at).toLocaleString()}</span>
            </div>
            <div className="text-sm text-zinc-700 whitespace-pre-wrap">{r.body}</div>
            <div className="mt-2 text-[10px] text-zinc-400">Sent by {r.sent_by}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReplyComposer({ reply, setReply, sending, onSend, canned, applyTemplate }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] uppercase tracking-[0.12em] font-bold text-zinc-400">Send a reply</p>
        {canned && canned.length > 0 && (
          <div className="flex items-center gap-1.5">
            <FileText size={11} className="text-zinc-400" />
            <select
              onChange={(e) => { applyTemplate(e.target.value); e.target.value = ''; }}
              defaultValue=""
              className="text-[11px] rounded-md border border-zinc-200 bg-white px-2 py-1 focus:outline-none focus:border-zinc-400"
              data-testid="comms-canned-picker"
            >
              <option value="">Load template…</option>
              {canned.map((c) => (
                <option key={c.id} value={c.id}>{c.label}</option>
              ))}
            </select>
          </div>
        )}
      </div>
      <div className="rounded-xl border border-zinc-200 bg-white p-4 space-y-3">
        <input
          type="text"
          value={reply.subject}
          onChange={(e) => setReply((r) => ({ ...r, subject: e.target.value }))}
          placeholder="Subject"
          className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:border-zinc-400"
          data-testid="comms-reply-subject"
        />
        <textarea
          value={reply.body}
          onChange={(e) => setReply((r) => ({ ...r, body: e.target.value }))}
          rows={6}
          placeholder="Write your reply…"
          className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm focus:outline-none focus:border-zinc-400"
          data-testid="comms-reply-body"
        />
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onSend}
            disabled={sending}
            className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold disabled:opacity-50"
            style={{ background: '#0F172A', color: '#FFFFFF' }}
            data-testid="comms-reply-send"
          >
            <Send size={12} /> {sending ? 'Sending…' : 'Send reply'}
          </button>
        </div>
      </div>
    </div>
  );
}

function InternalNotes({ value, setValue, onSave, saving }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-[0.12em] font-bold text-zinc-400 mb-2">Internal notes (private)</p>
      <div className="rounded-xl border border-amber-100 bg-amber-50/40 p-4 space-y-2">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          rows={3}
          placeholder="Add a private note — only the Master Admin team sees this."
          className="w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm focus:outline-none focus:border-amber-400"
          data-testid="comms-notes"
        />
        <div className="flex items-center justify-end">
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="text-xs font-semibold inline-flex items-center gap-1 rounded-full border border-amber-300 px-3 py-1 text-amber-800 hover:bg-amber-100 disabled:opacity-50"
            data-testid="comms-notes-save"
          >
            {saving ? 'Saving…' : 'Save notes'}
          </button>
        </div>
      </div>
    </div>
  );
}
