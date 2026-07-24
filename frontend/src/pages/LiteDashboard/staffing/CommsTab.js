/**
 * Phase S3 — Internal Comms Hub.
 *
 * Two-pane workforce messaging: thread list left, conversation right.
 * Threads come in four flavours — DMs, groups, channels, and
 * announcements — but the UI treats them uniformly because the
 * backend does too. Operators get a "+ New" menu to start any kind;
 * staff only see DM as a starter.
 *
 * Read state, urgent flag, scheduled send and 15-min edit are all
 * server-side; this component is a thin renderer + composer.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  Send, Loader2, Plus, MessageSquare, Megaphone, Hash, Users as UsersIcon, AlertTriangle, Check, Pin, Pencil, Trash2, X, Search,
} from 'lucide-react';
import Button from '@/components/shared/Button';
import RowActions from '@/components/shared/RowActions';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const KIND_META = {
  dm:           { icon: MessageSquare, labelKey: 'staffing.comms_dm',        labelDefault: 'DM' },
  group:        { icon: UsersIcon,     labelKey: 'staffing.comms_group',     labelDefault: 'Group' },
  channel:      { icon: Hash,          labelKey: 'staffing.comms_channel',   labelDefault: 'Channel' },
  announcement: { icon: Megaphone,     labelKey: 'staffing.comms_broadcast', labelDefault: 'Broadcast' },
};

function timeShort(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const today = new Date();
    if (d.toDateString() === today.toDateString()) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString([], { day: '2-digit', month: 'short' });
  } catch { return iso; }
}

function dayLabel(iso, t) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const today = new Date();
    const yest = new Date(today);
    yest.setDate(today.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return t('staffing.comms_today', 'Today');
    if (d.toDateString() === yest.toDateString()) return t('staffing.comms_yesterday', 'Yesterday');
    const weekAgo = new Date(today);
    weekAgo.setDate(today.getDate() - 6);
    if (d >= weekAgo) {
      return d.toLocaleDateString([], { weekday: 'long' });
    }
    return d.toLocaleDateString([], { weekday: 'short', day: '2-digit', month: 'short', year: today.getFullYear() === d.getFullYear() ? undefined : 'numeric' });
  } catch { return ''; }
}

function timeTooltip(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString([], {
      weekday: 'short', day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

function initials(name) {
  if (!name) return '?';
  const parts = String(name).trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const AVATAR_PALETTE = [
  { bg: '#FCA5A5', fg: '#7F1D1D' },
  { bg: '#FDBA74', fg: '#7C2D12' },
  { bg: '#FCD34D', fg: '#78350F' },
  { bg: '#86EFAC', fg: '#14532D' },
  { bg: '#67E8F9', fg: '#164E63' },
  { bg: '#93C5FD', fg: '#1E3A8A' },
  { bg: '#C4B5FD', fg: '#4C1D95' },
  { bg: '#F0ABFC', fg: '#701A75' },
  { bg: '#F9A8D4', fg: '#831843' },
];

function colorForKey(key) {
  const s = String(key || '');
  let h = 0;
  for (let i = 0; i < s.length; i += 1) {
    h = (h * 31 + s.charCodeAt(i)) >>> 0;
  }
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function Avatar({ name, authorKey, size = 28 }) {
  const { t } = useTranslation();
  const c = colorForKey(authorKey || name);
  const unknown = t('staffing.comms_unknown', 'Unknown');
  return (
    <div
      className="rounded-full flex items-center justify-center font-bold flex-shrink-0"
      style={{
        width: size,
        height: size,
        background: c.bg,
        color: c.fg,
        fontSize: size <= 28 ? 10 : 12,
      }}
      title={name || unknown}
      aria-label={`${t('staffing.comms_avatar_for', 'Avatar for')} ${name || unknown}`}
      data-testid="msg-avatar"
    >
      {initials(name)}
    </div>
  );
}

// ─────────────────── Compose new thread modal ───────────────────

function NewThreadModal({ open, onClose, headers, isManager, staffList, onCreated }) {
  const { t } = useTranslation();
  const [kind, setKind] = useState('dm');
  const [name, setName] = useState('');
  const [memberIds, setMemberIds] = useState([]);
  const [siteId, setSiteId] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');

  if (!open) return null;

  const kinds = isManager ? ['dm', 'group', 'channel', 'announcement'] : ['dm'];
  const filteredStaff = staffList.filter((s) =>
    !search || (s.full_name || '').toLowerCase().includes(search.toLowerCase()),
  );

  const submit = async () => {
    if (kind === 'dm' && memberIds.length !== 1) {
      window.alert(t('staffing.comms_pick_one', 'Pick exactly one person to DM'));
      return;
    }
    if ((kind === 'group') && memberIds.length === 0) {
      window.alert(t('staffing.comms_pick_member', 'Pick at least one member'));
      return;
    }
    if (kind === 'channel' && !siteId && !roleFilter) {
      window.alert(t('staffing.comms_pick_scope', 'Pick a site or role to scope the channel'));
      return;
    }
    setBusy(true);
    try {
      const payload = {
        kind,
        name: name.trim() || null,
        member_ids: memberIds,
        site_id: siteId || null,
        role_filter: roleFilter || null,
      };
      const { data } = await axios.post(`${API}/staffing/comms/threads`, payload, { headers });
      onCreated && onCreated(data);
      onClose();
    } catch (e) {
      window.alert(e.response?.data?.detail || t('staffing.comms_create_failed', 'Create failed'));
    }
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid="new-thread-modal">
      <div className="w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl p-5 space-y-3 max-h-[90vh] overflow-y-auto"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <div className="flex items-center justify-between">
          <h4 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{t('staffing.comms_new_conv', 'New conversation')}</h4>
          <button type="button" onClick={onClose} className="w-7 h-7 rounded-full inline-flex items-center justify-center" style={{ color: 'var(--theme-text-muted)' }}><X size={14} /></button>
        </div>
        <div className="flex gap-1.5 flex-wrap" data-testid="new-thread-kind">
          {kinds.map((k) => {
            const M = KIND_META[k]; const Icon = M.icon;
            const on = kind === k;
            return (
              <button key={k} type="button" onClick={() => setKind(k)}
                className="h-8 px-3 rounded-full text-xs font-bold inline-flex items-center gap-1 transition-colors"
                style={{
                  background: on ? 'var(--color-brand-cyan)' : 'transparent',
                  color: on ? '#001219' : 'var(--theme-text-muted)',
                  border: '1px solid var(--theme-border)',
                }}
                data-testid={`new-thread-kind-${k}`}>
                <Icon size={11} /> {t(M.labelKey, M.labelDefault)}
              </button>
            );
          })}
        </div>
        {(kind === 'group' || kind === 'announcement' || kind === 'channel') && (
          <input value={name} onChange={(e) => setName(e.target.value)}
            placeholder={kind === 'channel' ? t('staffing.comms_channel_name', 'Channel name (optional)') : kind === 'announcement' ? t('staffing.comms_subject', 'Subject (optional)') : t('staffing.comms_group_name', 'Group name (optional)')}
            className="w-full h-9 rounded-md bg-transparent border px-2 text-sm"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="new-thread-name" />
        )}
        {kind === 'channel' ? (
          <div className="grid grid-cols-2 gap-2">
            <input value={siteId} onChange={(e) => setSiteId(e.target.value)} placeholder={t('staffing.comms_site_id', 'Site ID (optional)')}
              className="h-9 rounded-md bg-transparent border px-2 text-xs"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="new-thread-site" />
            <input value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} placeholder={t('staffing.comms_role_ph', 'Role (e.g. instructor)')}
              className="h-9 rounded-md bg-transparent border px-2 text-xs"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="new-thread-role" />
          </div>
        ) : (
          <>
            <div className="relative">
              <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 opacity-50" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('staffing.comms_search_staff', 'Search staff…')}
                className="w-full h-9 rounded-md bg-transparent border pl-7 pr-2 text-xs"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="new-thread-search" />
            </div>
            <div className="max-h-56 overflow-y-auto border rounded-md" style={{ borderColor: 'var(--theme-border)' }} data-testid="new-thread-staff-list">
              {filteredStaff.length === 0 ? (
                <p className="text-xs p-3 text-center" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.comms_no_staff_match', 'No staff match.')}</p>
              ) : filteredStaff.map((s) => {
                const on = memberIds.includes(s.id);
                return (
                  <button key={s.id} type="button"
                    onClick={() => {
                      if (kind === 'dm') setMemberIds([s.id]);
                      else setMemberIds(on ? memberIds.filter((m) => m !== s.id) : [...memberIds, s.id]);
                    }}
                    className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-xs transition-colors"
                    style={{ background: on ? 'rgba(25,205,255,0.12)' : 'transparent', color: 'var(--theme-text)' }}
                    data-testid={`new-thread-staff-${s.id}`}>
                    <span>
                      <span className="font-bold">{s.full_name}</span>
                      <span className="ml-1.5 text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{s.primary_role}</span>
                    </span>
                    {on && <Check size={12} style={{ color: 'var(--color-brand-cyan)' }} />}
                  </button>
                );
              })}
            </div>
          </>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="h-9 rounded-full border px-4 text-xs font-bold"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>{t('staffing.comms_cancel', 'Cancel')}</button>
          <button type="button" onClick={submit} disabled={busy}
            className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-60"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }}
            data-testid="new-thread-submit">
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
            {busy ? t('staffing.comms_creating', 'Creating…') : t('staffing.comms_create', 'Create')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────── Conversation pane ───────────────────

function MessageRow({ msg, mine, isManager, showAuthor, isGroup, onEdit, onDelete }) {
  const { t } = useTranslation();
  const deleted = !!msg.deleted_at;
  const align = mine ? 'items-end' : 'items-start';
  const tint = msg.urgent
    ? 'rgba(239,68,68,0.15)'
    : mine ? 'var(--color-brand-cyan)' : 'var(--theme-surface-hover, rgba(255,255,255,0.04))';
  const txtColour = (msg.urgent || mine) ? '#001219' : 'var(--theme-text)';

  const bubble = (
    <div className={`flex flex-col ${align} gap-0.5 min-w-0`}>
      <div className={`flex items-end gap-1.5 ${mine ? 'flex-row-reverse' : ''}`}>
        {msg.urgent && !deleted && (
          <span className="inline-flex items-center gap-0.5 text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded" style={{ background: 'rgba(239,68,68,0.15)', color: '#EF4444' }}>
            <AlertTriangle size={9} /> {t('staffing.comms_urgent', 'Urgent')}
          </span>
        )}
        {msg.pinned && !deleted && (
          <span className="inline-flex items-center gap-0.5 text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded" style={{ background: 'rgba(245,158,11,0.15)', color: '#F59E0B' }}>
            <Pin size={9} /> {t('staffing.comms_pinned', 'Pinned')}
          </span>
        )}
        <div className="rounded-2xl px-3 py-2 text-sm max-w-[75ch] whitespace-pre-wrap break-words" style={{
          background: deleted ? 'transparent' : tint,
          color: deleted ? 'var(--theme-text-muted)' : txtColour,
          border: deleted ? '1px dashed var(--theme-border)' : 'none',
          fontStyle: deleted ? 'italic' : 'normal',
        }}>
          {deleted ? t('staffing.comms_msg_deleted', 'Message deleted') : msg.body}
        </div>
      </div>
      <div className={`flex items-center gap-1 text-[10px] ${mine ? 'justify-end' : 'justify-start'}`} style={{ color: 'var(--theme-text-muted)' }}>
        <span title={timeTooltip(msg.sent_at)}>{timeShort(msg.sent_at)}</span>
        {msg.edited_at && <span>· {t('staffing.comms_edited', 'edited')}</span>}
        {!deleted && mine && (
          <RowActions gap={0.5}>
            <Button variant="ghost" size="iconSm" onClick={() => onEdit(msg)} icon={Pencil} title={t('staffing.comms_edit_msg', 'Edit message')} data-testid={`msg-edit-${msg.id}`} />
            <Button variant="ghostDestructive" size="iconSm" onClick={() => onDelete(msg)} icon={Trash2} title={t('staffing.comms_delete_msg', 'Delete message')} data-testid={`msg-delete-${msg.id}`} />
          </RowActions>
        )}
        {!mine && isManager && !deleted && (
          <RowActions>
            <Button variant="ghostDestructive" size="iconSm" onClick={() => onDelete(msg)} icon={Trash2} title={t('staffing.comms_delete_msg', 'Delete message')} data-testid={`msg-delete-${msg.id}`} />
          </RowActions>
        )}
      </div>
    </div>
  );

  if (mine) {
    return (
      <div className="flex justify-end" data-testid={`msg-${msg.id}`}>
        {bubble}
      </div>
    );
  }

  const authorKey = msg.author_staff_id || msg.author_id || msg.author_email;
  return (
    <div className="flex items-start gap-2" data-testid={`msg-${msg.id}`}>
      {isGroup ? (
        showAuthor ? (
          <Avatar name={msg.author_name} authorKey={authorKey} />
        ) : (
          <div style={{ width: 28 }} aria-hidden="true" />
        )
      ) : null}
      <div className="flex flex-col items-start gap-0.5 min-w-0">
        {isGroup && showAuthor && msg.author_name && (
          <span
            className="text-[11px] font-bold px-1"
            style={{ color: 'var(--theme-text)' }}
            data-testid={`msg-author-${msg.id}`}
          >
            {msg.author_name}
          </span>
        )}
        {bubble}
      </div>
    </div>
  );
}

function Conversation({ thread, headers, isManager, myStaffId, onUpdate }) {
  const { t } = useTranslation();
  const [messages, setMessages] = useState([]);
  const [body, setBody] = useState('');
  const [urgent, setUrgent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);
  const scrollRef = useRef(null);

  const load = useCallback(async () => {
    const { data } = await axios.get(`${API}/staffing/comms/threads/${thread.id}/messages`, { headers, params: { limit: 100 } });
    setMessages(data.messages || []);
    try { await axios.post(`${API}/staffing/comms/threads/${thread.id}/read`, {}, { headers }); }
    catch { /* noop */ }
    onUpdate && onUpdate();
  }, [thread.id, headers, onUpdate]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages.length]);

  const send = async () => {
    if (!body.trim()) return;
    setBusy(true);
    try {
      if (editing) {
        await axios.patch(`${API}/staffing/comms/threads/${thread.id}/messages/${editing.id}`,
          { body: body.trim() }, { headers });
      } else {
        await axios.post(`${API}/staffing/comms/threads/${thread.id}/messages`,
          { body: body.trim(), urgent }, { headers });
      }
      setBody(''); setUrgent(false); setEditing(null);
      load();
    } catch (e) {
      window.alert(e.response?.data?.detail || t('staffing.comms_send_failed', 'Send failed'));
    }
    setBusy(false);
  };

  const startEdit = (msg) => { setEditing(msg); setBody(msg.body); };
  const remove = async (msg) => {
    if (!window.confirm(t('staffing.comms_delete_confirm', 'Delete this message?'))) return;
    try {
      await axios.delete(`${API}/staffing/comms/threads/${thread.id}/messages/${msg.id}`, { headers });
      load();
    } catch (e) { window.alert(e.response?.data?.detail || t('staffing.comms_delete_failed', 'Delete failed')); }
  };

  const M = KIND_META[thread.kind];
  const Icon = M.icon;
  const memberLabel = (() => {
    if (thread.kind === 'dm') {
      const other = (thread.members || []).find((m) => m.staff_id !== myStaffId);
      return other?.full_name || t('staffing.comms_dm', 'DM');
    }
    return thread.name || (thread.members || []).map((m) => m.full_name).filter(Boolean).slice(0, 4).join(', ');
  })();

  const canSend = !(thread.kind === 'announcement' && !isManager);

  return (
    <div className="flex flex-col h-full" data-testid="conversation">
      <div className="px-4 py-2 border-b flex items-center gap-2" style={{ borderColor: 'var(--theme-border)' }}>
        <Icon size={14} style={{ color: 'var(--color-brand-cyan)' }} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>{memberLabel}</p>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>
            {t(M.labelKey, M.labelDefault)} · {thread.members?.length || 0} {thread.members?.length === 1 ? t('staffing.comms_member', 'member') : t('staffing.comms_members', 'members')}
          </p>
        </div>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-2" data-testid="conversation-messages">
        {messages.length === 0 ? (
          <p className="text-center text-xs py-8" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.comms_no_messages', 'No messages yet — say hi.')}</p>
        ) : (() => {
          const isGroup = thread.kind !== 'dm';
          const out = [];
          let prevDay = null;
          let prevAuthorKey = null;
          for (const m of messages) {
            const day = (m.sent_at || '').slice(0, 10);
            if (day && day !== prevDay) {
              out.push(
                <div
                  key={`sep-${day}`}
                  className="flex items-center justify-center py-2"
                  data-testid={`conversation-day-${day}`}
                >
                  <span
                    className="text-[10px] font-semibold uppercase tracking-[0.18em] px-3 py-1 rounded-full"
                    style={{ background: 'var(--theme-surface)', color: 'var(--theme-text-muted)', border: '1px solid var(--theme-border)' }}
                  >
                    {dayLabel(m.sent_at, t)}
                  </span>
                </div>,
              );
              prevDay = day;
              prevAuthorKey = null;
            }
            const mine = m.author_staff_id === myStaffId || m.author_id === myStaffId;
            const authorKey = m.author_staff_id || m.author_id || m.author_email;
            const showAuthor = isGroup && !mine && authorKey !== prevAuthorKey;
            out.push(
              <MessageRow
                key={m.id}
                msg={m}
                mine={mine}
                isManager={isManager}
                isGroup={isGroup}
                showAuthor={showAuthor}
                onEdit={startEdit}
                onDelete={remove}
              />,
            );
            prevAuthorKey = authorKey;
          }
          return out;
        })()}
      </div>
      {canSend ? (
        <div className="border-t p-3 space-y-2" style={{ borderColor: 'var(--theme-border)' }}>
          {editing && (
            <div className="text-[10px] inline-flex items-center gap-1" style={{ color: 'var(--theme-text-muted)' }}>
              <Pencil size={10} /> {t('staffing.comms_editing_msg', 'Editing message')}
              <button type="button" onClick={() => { setEditing(null); setBody(''); }} className="ml-1 underline" data-testid="cancel-edit">{t('staffing.comms_cancel_lc', 'cancel')}</button>
            </div>
          )}
          <div className="flex gap-2 items-end">
            <textarea value={body} onChange={(e) => setBody(e.target.value)}
              placeholder={thread.kind === 'announcement' ? t('staffing.comms_broadcast_ph', 'Broadcast something to your team…') : t('staffing.comms_message_ph', 'Message…')}
              rows={2}
              onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send(); }}
              className="flex-1 rounded-md bg-transparent border px-3 py-2 text-sm resize-none"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="conversation-input" />
            <div className="flex flex-col gap-1.5">
              {!editing && isManager && (
                <button type="button" onClick={() => setUrgent(!urgent)}
                  className="h-9 px-2 rounded-md text-[10px] font-bold uppercase tracking-wider inline-flex items-center gap-1 border"
                  style={{
                    borderColor: urgent ? '#EF4444' : 'var(--theme-border)',
                    background: urgent ? 'rgba(239,68,68,0.15)' : 'transparent',
                    color: urgent ? '#EF4444' : 'var(--theme-text-muted)',
                  }}
                  data-testid="conversation-urgent-toggle">
                  <AlertTriangle size={10} /> {t('staffing.comms_urgent', 'Urgent')}
                </button>
              )}
              <button type="button" onClick={send} disabled={busy || !body.trim()}
                className="h-9 px-3 rounded-md text-xs font-bold inline-flex items-center gap-1 disabled:opacity-50"
                style={{ background: 'var(--color-brand-cyan)', color: '#001219' }}
                data-testid="conversation-send">
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
                {t('staffing.comms_send', 'Send')}
              </button>
            </div>
          </div>
          <p className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.comms_send_hint', '⌘ / Ctrl + Enter to send')}</p>
        </div>
      ) : (
        <div className="border-t p-3 text-[11px] text-center" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>
          {t('staffing.comms_readonly', 'Read-only — only managers can post here.')}
        </div>
      )}
    </div>
  );
}

// ─────────────────── Main hub ───────────────────

export default function CommsTab({ headers, isManager }) {
  const { t } = useTranslation();
  const [threads, setThreads] = useState([]);
  const [staffList, setStaffList] = useState([]);
  const [myStaffId, setMyStaffId] = useState(null);
  const [active, setActive] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [thRes, sRes] = await Promise.all([
        axios.get(`${API}/staffing/comms/threads`, { headers }),
        axios.get(`${API}/staffing/staff`, { headers }),
      ]);
      setThreads(thRes.data.threads || []);
      setMyStaffId(thRes.data.my_staff_id || null);
      setStaffList(sRes.data.staff || []);
    } catch { /* noop */ }
    setLoading(false);
  }, [headers]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const i = setInterval(() => { if (document.visibilityState === 'visible') load(); }, 30_000);
    return () => clearInterval(i);
  }, [load]);

  const hydrated = useMemo(() => {
    const byId = new Map(staffList.map((s) => [s.id, s]));
    return threads.map((th) => ({
      ...th,
      members: (th.members || []).map((m) => ({ ...m, ...(byId.get(m.staff_id) || {}) })),
    }));
  }, [threads, staffList]);

  const filtered = useMemo(() => {
    if (!q.trim()) return hydrated;
    const ql = q.toLowerCase();
    return hydrated.filter((th) => {
      if ((th.name || '').toLowerCase().includes(ql)) return true;
      if ((th.last_message_preview || '').toLowerCase().includes(ql)) return true;
      return (th.members || []).some((m) => (m.full_name || '').toLowerCase().includes(ql));
    });
  }, [hydrated, q]);

  const selected = filtered.find((th) => th.id === active);

  return (
    <div className="space-y-3" data-testid="comms-tab">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{t('staffing.comms_internal_messaging', 'Internal messaging')}</p>
        </div>
        <button type="button" onClick={() => setShowNew(true)}
          className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5"
          style={{ background: 'var(--color-brand-cyan)', color: '#001219' }}
          data-testid="comms-new">
          <Plus size={12} /> {t('staffing.comms_new', 'New')}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-3 rounded-xl border overflow-hidden"
        style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)', minHeight: '520px' }}>
        {/* Thread list */}
        <div className="border-r flex flex-col" style={{ borderColor: 'var(--theme-border)' }}>
          <div className="p-2 border-b" style={{ borderColor: 'var(--theme-border)' }}>
            <div className="relative">
              <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 opacity-50" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('staffing.comms_search_threads', 'Search threads…')}
                className="w-full h-8 rounded-md bg-transparent border pl-6 pr-2 text-xs"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="comms-search" />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto" data-testid="thread-list">
            {loading && (
              <div className="p-3 inline-flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
                <Loader2 size={12} className="animate-spin" /> {t('staffing.comms_loading', 'Loading…')}
              </div>
            )}
            {!loading && filtered.length === 0 && (
              <p className="p-4 text-center text-xs" style={{ color: 'var(--theme-text-muted)' }}>
                {threads.length === 0 ? t('staffing.comms_no_convs', 'No conversations yet — start one with "+ New".') : t('staffing.comms_no_matches', 'No matches.')}
              </p>
            )}
            {filtered.map((th) => {
              const M = KIND_META[th.kind]; const Icon = M.icon;
              const on = active === th.id;
              const unread = th.unread_count || 0;
              const otherName = th.kind === 'dm'
                ? (th.members || []).find((m) => m.staff_id !== myStaffId)?.full_name || t('staffing.comms_dm', 'DM')
                : null;
              const label = th.name || otherName || t(M.labelKey, M.labelDefault);
              return (
                <button key={th.id} type="button" onClick={() => setActive(th.id)}
                  className="w-full flex items-start gap-2 p-3 text-left border-b transition-colors"
                  style={{
                    background: on ? 'rgba(25,205,255,0.10)' : 'transparent',
                    borderColor: 'var(--theme-border)',
                  }}
                  data-testid={`thread-row-${th.id}`}>
                  <Icon size={13} className="mt-0.5 shrink-0" style={{
                    color: on ? 'var(--color-brand-cyan)' : 'var(--theme-text-muted)',
                  }} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>{label}</span>
                      <span className="text-[10px] tabular-nums shrink-0" style={{ color: 'var(--theme-text-muted)' }}>
                        {timeShort(th.last_message_at)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-[11px] truncate" style={{ color: 'var(--theme-text-muted)' }}>
                        {th.last_message_preview || t('staffing.comms_no_msgs_yet', 'No messages yet')}
                      </span>
                      {unread > 0 && (
                        <span className="ml-1 shrink-0 text-[10px] font-bold rounded-full px-1.5 py-0.5"
                          style={{ background: 'var(--color-brand-cyan)', color: '#001219' }}
                          data-testid={`thread-unread-${th.id}`}>
                          {unread}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Conversation */}
        <div className="min-h-[520px] flex flex-col">
          {selected ? (
            <Conversation
              thread={selected}
              headers={headers}
              isManager={isManager}
              myStaffId={myStaffId}
              onUpdate={load}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center p-6 text-center">
              <div>
                <MessageSquare size={28} className="mx-auto mb-2 opacity-40" />
                <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{t('staffing.comms_pick_conv', 'Pick a conversation')}</p>
                <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.comms_or_create', 'or create a new one with the “+ New” button.')}</p>
              </div>
            </div>
          )}
        </div>
      </div>

      <NewThreadModal
        open={showNew}
        onClose={() => setShowNew(false)}
        headers={headers}
        isManager={isManager}
        staffList={staffList.filter((s) => s.id !== myStaffId)}
        onCreated={(th) => { setActive(th.id); load(); }}
      />
    </div>
  );
}
