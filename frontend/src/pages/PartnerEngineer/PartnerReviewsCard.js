/**
 * PartnerReviewsCard.js (iter 216h286)
 *
 * Engineer-side reviews panel: aggregate rating, list of reviews
 * (approved + pending + rejected — the engineer sees everything on
 * their own wall) and a one-shot response form per review.
 *
 * Hides itself if the partner has no reviews yet — engineers don't
 * need to see another empty state on the dashboard.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Star, MessageSquare, Reply, CheckCircle2, Clock, AlertCircle } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL;

function StarBar({ rating, size = 14 }) {
  return (
    <span className="inline-flex items-center gap-0.5" data-testid="review-stars">
      {[1, 2, 3, 4, 5].map((n) => (
        <Star
          key={n}
          size={size}
          className={n <= (rating || 0) ? 'text-amber-500 fill-amber-500' : 'text-zinc-200'}
        />
      ))}
    </span>
  );
}

const STATUS_META = {
  approved: { label: 'Published', tone: 'bg-emerald-100 text-emerald-700', Icon: CheckCircle2 },
  pending:  { label: 'Awaiting review', tone: 'bg-amber-100 text-amber-700', Icon: Clock },
  rejected: { label: 'Hidden by moderator', tone: 'bg-zinc-200 text-zinc-700', Icon: AlertCircle },
};

function ReviewItem({ review, onRespond }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(review.engineer_response || '');
  const [busy, setBusy] = useState(false);
  const status = STATUS_META[review.status] || STATUS_META.pending;
  const StatusIcon = status.Icon;

  const save = async () => {
    setBusy(true);
    try {
      await onRespond(review.id, text);
      setOpen(false);
    } finally { setBusy(false); }
  };

  return (
    <div className="px-4 py-3 border-t border-zinc-100" data-testid={`review-item-${review.id}`}>
      <div className="flex items-start gap-3">
        <div className="shrink-0 w-9 h-9 rounded-full bg-zinc-100 flex items-center justify-center text-xs font-bold text-zinc-700">
          {(review.reviewer_name || '?').charAt(0).toUpperCase()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-bold text-zinc-900 truncate">{review.reviewer_name}</p>
            {review.gym_name && <span className="text-[11px] text-zinc-500">· {review.gym_name}</span>}
            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded inline-flex items-center gap-1 ${status.tone}`}>
              <StatusIcon size={10} /> {status.label}
            </span>
          </div>
          <StarBar rating={review.rating} />
          {review.title && <p className="mt-1 text-[13px] font-bold text-zinc-900">{review.title}</p>}
          <p className="mt-0.5 text-[13px] text-zinc-700 whitespace-pre-wrap">{review.body}</p>
          {review.engineer_response && (
            <div className="mt-2 pl-3 border-l-2 border-cyan-200 bg-cyan-50/50 rounded-r p-2">
              <p className="text-[11px] font-semibold text-cyan-900 mb-0.5 inline-flex items-center gap-1">
                <Reply size={11} /> Your response
              </p>
              <p className="text-[12px] text-zinc-800 whitespace-pre-wrap">{review.engineer_response}</p>
            </div>
          )}
          {review.status === 'approved' && !open && (
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="mt-2 text-[11px] font-bold text-cyan-700 hover:underline inline-flex items-center gap-1"
              data-testid={`review-respond-${review.id}`}
            >
              <Reply size={10} /> {review.engineer_response ? 'Edit response' : 'Respond'}
            </button>
          )}
          {open && (
            <div className="mt-2 space-y-1.5">
              <textarea
                rows={3}
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={1500}
                placeholder="A short, professional response. Visible publicly."
                className="w-full border border-zinc-200 rounded p-2 text-sm bg-white"
                data-testid={`review-response-input-${review.id}`}
              />
              <div className="flex items-center justify-end gap-2">
                <button type="button" onClick={() => setOpen(false)} className="text-[11px] text-zinc-500 hover:text-zinc-800">Cancel</button>
                <button
                  type="button"
                  onClick={save}
                  disabled={busy || !text.trim()}
                  className="px-2.5 py-1 text-[11px] font-bold text-white rounded disabled:opacity-50"
                  style={{ background: '#0891b2' }}
                  data-testid={`review-save-response-${review.id}`}
                >
                  {busy ? 'Saving…' : 'Save response'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PartnerReviewsCard() {
  const [data, setData] = useState(null);
  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

  const load = async () => {
    try {
      const r = await axios.get(`${API}/api/partners/me/reviews`, { headers });
      setData(r.data);
    } catch { /* silent — non-partners */ }
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const respond = async (id, response) => {
    try {
      await axios.post(`${API}/api/partners/me/reviews/${id}/respond`,
        { response }, { headers });
      notify.success('Response saved');
      load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not save response');
      throw e;
    }
  };

  if (!data) return null;
  const { reviews, summary } = data;
  if (!reviews.length) return null;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white overflow-hidden" data-testid="partner-reviews-card">
      <div className="px-4 py-3 flex items-center gap-3 border-b border-zinc-100 bg-gradient-to-r from-amber-50/40 to-white">
        <MessageSquare size={16} className="text-zinc-500" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-zinc-900">Customer reviews</p>
          <p className="text-[11px] text-zinc-500">
            {summary.total} {summary.total === 1 ? 'review' : 'reviews'} ·
            {' '}{summary.approved} live
            {summary.pending > 0 && <> · {summary.pending} awaiting moderation</>}
          </p>
        </div>
        {summary.average !== null && (
          <div className="text-right shrink-0">
            <p className="text-lg font-bold text-zinc-900">{summary.average.toFixed(1)}</p>
            <StarBar rating={Math.round(summary.average)} size={12} />
          </div>
        )}
      </div>
      <div data-testid="partner-reviews-list">
        {reviews.map((r) => <ReviewItem key={r.id} review={r} onRespond={respond} />)}
      </div>
    </div>
  );
}
