import { useEffect, useState } from 'react';
import axios from 'axios';
import { Pencil, Trash2 } from 'lucide-react';
import { notify } from '@/components/notifications';

export const GYM_COMMENT_EDIT_WINDOW_MS = 15 * 60 * 1000;

/** True while the signed-in user may still edit/delete this message. */
export function canChangeGymComment(c, user, now = Date.now()) {
  if (!c || c.author_role === 'supplier' || !c.author_user_id || !user?.id) return false;
  if (c.author_user_id !== user.id) return false;
  const created = Date.parse(c.created_at);
  return Number.isFinite(created) && now - created <= GYM_COMMENT_EDIT_WINDOW_MS;
}

/**
 * Site-staff message body inside the supplier thread: text + "edited" note,
 * and — for the author, within 15 minutes — inline Edit / Delete.
 * The server enforces the same rules (author + 15-minute window).
 */
export default function GymCommentBody({ comment: c, caseToken, API, user, onChanged }) {
  const [now, setNow] = useState(Date.now());
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(c.message || '');
  const [busy, setBusy] = useState(false);
  const editable = canChangeGymComment(c, user, now);

  // Re-evaluate every 20s so the buttons disappear when the window closes.
  useEffect(() => {
    if (!canChangeGymComment(c, user)) return undefined;
    const t = setInterval(() => setNow(Date.now()), 20000);
    return () => clearInterval(t);
  }, [c, user]);

  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });
  const url = `${API}/supplier/case/${caseToken}/comments/gym/${c.id}`;

  const save = async () => {
    const text = draft.trim();
    if (!text) { notify.error('Message cannot be empty — delete it instead'); return; }
    setBusy(true);
    try {
      await axios.patch(url, { message: text }, { headers: headers() });
      setEditing(false);
      notify.success('Message updated');
      onChanged?.();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not update the message');
    }
    setBusy(false);
  };

  const remove = async () => {
    if (!window.confirm('Delete this message? The supplier may already have received it by email.')) return;
    setBusy(true);
    try {
      await axios.delete(url, { headers: headers() });
      notify.success('Message deleted');
      onChanged?.();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not delete the message');
    }
    setBusy(false);
  };

  if (editing) {
    return (
      <div className="mt-1" data-testid={`gym-comment-editor-${c.id}`}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          className="w-full rounded-lg px-2 py-1.5 text-sm text-zinc-900 bg-white focus:outline-none"
          data-testid={`gym-comment-edit-input-${c.id}`}
          autoFocus
        />
        <div className="flex justify-end gap-2 mt-1">
          <button type="button" disabled={busy} onClick={() => { setEditing(false); setDraft(c.message || ''); }}
            className="text-[11px] px-2 py-0.5 rounded bg-white/20 hover:bg-white/30" data-testid={`gym-comment-edit-cancel-${c.id}`}>Cancel</button>
          <button type="button" disabled={busy || !draft.trim()} onClick={save}
            className="text-[11px] px-2 py-0.5 rounded bg-white text-emerald-700 font-semibold hover:bg-white/90" data-testid={`gym-comment-edit-save-${c.id}`}>Save</button>
        </div>
      </div>
    );
  }

  return (
    <>
      {c.message && <p className="text-sm leading-relaxed" style={{ color: '#fff' }} data-testid={`gym-comment-text-${c.id}`}>{c.message}</p>}
      {(c.edited_at || editable) && (
        <div className="flex items-center gap-2 mt-1">
          {c.edited_at && <span className="text-[11px] italic" style={{ color: 'rgba(255,255,255,0.85)' }} data-testid={`gym-comment-edited-${c.id}`}>edited</span>}
          {editable && (
            <>
              <button type="button" disabled={busy} onClick={() => { setDraft(c.message || ''); setEditing(true); }}
                className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 min-h-[28px] rounded-md bg-white/25 hover:bg-white/35"
                data-testid={`gym-comment-edit-${c.id}`} title="Edit (available for 15 minutes after sending)">
                <Pencil size={10} /> Edit
              </button>
              <button type="button" disabled={busy} onClick={remove}
                className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 min-h-[28px] rounded-md bg-white/25 hover:bg-white/35"
                data-testid={`gym-comment-delete-${c.id}`} title="Delete (available for 15 minutes after sending)">
                <Trash2 size={10} /> Delete
              </button>
            </>
          )}
        </div>
      )}
    </>
  );
}
