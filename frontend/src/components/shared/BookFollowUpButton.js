import { lazy, Suspense, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { CalendarPlus, Loader2 } from 'lucide-react';
import { notify } from '@/components/notifications';

const ServiceDeskIntakeForm = lazy(() => import('@/pages/ServiceOps/ServiceDeskIntakeForm'));
const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });

// One-tap follow-up from a completed job's "Further Work / Parts Required".
export function BookFollowUpButton({ caseId, report, followUpRef, onBooked }) {
  const [initial, setInitial] = useState(null);
  const [busy, setBusy] = useState(false);
  const [bookedRef, setBookedRef] = useState(followUpRef || null);
  const needed = (report?.further_work_required || '').trim() || (report?.further_parts_required || []).length;
  if (!needed) return null;
  if (bookedRef) {
    return <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700" data-testid="follow-up-booked"><CalendarPlus size={13} /> Follow-up booked · {bookedRef}</span>;
  }
  const open = async () => {
    setBusy(true);
    try {
      const { data } = await axios.get(`${API}/svc/cases/${caseId}/follow-up-draft`, auth());
      if (data.existing_follow_up) { setBookedRef(data.existing_follow_up); return; }
      setInitial({ ...data, followUpOf: data.follow_up_of, followUpRef: data.reference });
    } catch (e) {
      notify.error('Could not prepare the follow-up', e?.response?.data?.detail || e.message);
    } finally { setBusy(false); }
  };
  return (
    <>
      <button type="button" onClick={open} disabled={busy} data-testid="book-follow-up-btn"
        className="inline-flex items-center gap-1.5 rounded-full bg-[#19CDFF] text-[#1B1C1D] px-3.5 py-1.5 text-xs font-semibold hover:bg-[#0091CA] hover:text-white disabled:opacity-60">
        {busy ? <Loader2 size={13} className="animate-spin" /> : <CalendarPlus size={13} />} Book follow-up
      </button>
      {initial && createPortal(
        <div style={{ position: 'fixed', inset: 0, zIndex: 1200 }} data-testid="follow-up-intake-layer">
          <Suspense fallback={null}>
            <ServiceDeskIntakeForm initial={initial} onClose={() => setInitial(null)}
              onCreated={(c) => { setInitial(null); setBookedRef(c?.reference || 'booked'); notify.success('Follow-up job booked', c?.reference || ''); onBooked?.(c); }} />
          </Suspense>
        </div>,
        document.body,
      )}
    </>
  );
}

export default BookFollowUpButton;
