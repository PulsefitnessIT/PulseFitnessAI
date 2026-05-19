/**
 * GymAxis Memberships — Front-Desk Check-in console (Phase 4).
 *
 * One-tap mark-attended/no-show roster, plus member search to add a
 * walk-in or look up details. Also exposes:
 *   - Drop-in invite broadcast button per under-capacity class
 *   - Kiosk token issue + URL preview
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  CalendarDays, Search, UserCheck, UserX, RefreshCw,
  Send, Tablet, Copy, KeyRound, AlertCircle, Loader2, Users, UserPlus, Megaphone, Share2, X,
} from 'lucide-react';
import { notify, useConfirm } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import Button from '@/components/shared/Button';

export default function CheckinTab({ API, headers }) {
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeOcc, setActiveOcc] = useState(null);
  const [dayWindow, setDayWindow] = useState(1);
  const [showSearch, setShowSearch] = useState(false);
  const [showKiosk, setShowKiosk] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/memberships/checkin/today?days=${dayWindow}`, { headers });
      setClasses(r.data.classes || []);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load classes');
    }
    setLoading(false);
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps -- todo: review missing dep(s) 'load'; pre-existing as of iter 216h226-polish-5.
  useEffect(() => { load();   }, [dayWindow]);

  return (
    <div data-testid="mbr-checkin-tab" className="space-y-4">
      <div className="flex items-end justify-end gap-4 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex gap-1 p-1 rounded-md border border-[color:var(--theme-border)]">
            {[1, 3, 7].map((d) => (
              <button key={d} onClick={() => setDayWindow(d)}
                className={`px-2.5 py-1 rounded text-[11px] font-bold ${
                  dayWindow === d ? 'bg-emerald-500 text-white' : 'text-[color:var(--theme-text-muted)]'
                }`}
                data-testid={`mbr-checkin-window-${d}`}>
                {d === 1 ? 'Today' : `${d} days`}
              </button>
            ))}
          </div>
          <button onClick={load}
            className="px-3 py-2 rounded-md border border-[color:var(--theme-border)] text-xs font-bold flex items-center gap-1.5"
            data-testid="mbr-checkin-refresh">
            <RefreshCw size={12} /> Refresh
          </button>
          <button onClick={() => setShowSearch(true)}
            className="px-3 py-2 rounded-md border border-[color:var(--theme-border)] text-xs font-bold flex items-center gap-1.5"
            data-testid="mbr-checkin-find-member-btn">
            <Search size={12} /> Find member
          </button>
          <button onClick={() => setShowKiosk(true)}
            className="px-3 py-2 rounded-md text-xs font-bold flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="mbr-checkin-kiosk-btn">
            <Tablet size={12} /> Kiosk mode
          </button>
        </div>
      </div>

      {loading ? (
        <Spinner />
      ) : classes.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[color:var(--theme-border)] p-10 text-center">
          <CalendarDays size={32} className="mx-auto text-[color:var(--theme-text-muted)] mb-3" />
          <p className="text-sm font-bold">No scheduled classes in this window</p>
          <p className="text-xs text-[color:var(--theme-text-muted)] mt-1">Add a class on the Timetable tab to see it here.</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {classes.map((occ) => (
            <ClassCard key={occ.id} occ={occ} onOpen={() => setActiveOcc(occ)} API={API} headers={headers} onChanged={load} />
          ))}
        </div>
      )}

      {activeOcc && <RosterDrawer API={API} headers={headers} occ={activeOcc} onClose={() => { setActiveOcc(null); load(); }} />}
      {showSearch && <MemberSearchDialog API={API} headers={headers} onClose={() => setShowSearch(false)} />}
      {showKiosk && <KioskDialog API={API} headers={headers} onClose={() => setShowKiosk(false)} />}
    </div>
  );
}


function ClassCard({ occ, onOpen, API, headers, onChanged }) {
  const confirm = useConfirm();
  const cap = occ.capacity || 0;
  const booked = occ.bookings_count || 0;
  const wl = occ.waitlist_count || 0;
  const fillPct = cap > 0 ? Math.round((booked / cap) * 100) : 0;
  const start = occ.starts_at ? new Date(occ.starts_at) : null;
  const isToday = start && start.toDateString() === new Date().toDateString();
  const tone = fillPct >= 100 ? 'red' : fillPct >= 70 ? 'emerald' : fillPct >= 30 ? 'amber' : 'zinc';
  const tones = {
    red: 'bg-red-500',
    emerald: 'bg-emerald-500',
    amber: 'bg-amber-500',
    zinc: 'bg-zinc-400',
  };
  const canInvite = cap > 0 && booked < cap;

  const sendInvite = async (e) => {
    e.stopPropagation();
    const ok = await confirm({
      title: 'Send drop-in invites?',
      body: `Email all opted-in members in your studio (capped at 200) about the open spots in ${occ.name}.`,
      tone: 'info', confirmLabel: 'Send invites',
    });
    if (!ok) return;
    try {
      const r = await axios.post(`${API}/memberships/occurrences/${occ.id}/dropin-invite`, {}, { headers });
      notify.success(`${r.data.invites_sent || 0} drop-in invite${r.data.invites_sent === 1 ? '' : 's'} queued`);
      onChanged?.();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to send invites');
    }
  };

  return (
    <button onClick={onOpen}
      className="text-left rounded-xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] hover:border-emerald-500/60 transition p-3"
      data-testid={`mbr-checkin-class-${occ.id}`}>
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <p className="font-bold truncate">{occ.name}</p>
          <p className="text-[11px] text-[color:var(--theme-text-muted)] truncate">
            {start && start.toLocaleString([], { weekday: isToday ? undefined : 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            {occ.instructor_name && ` · ${occ.instructor_name}`}
            {occ.room_name && ` · ${occ.room_name}`}
          </p>
        </div>
        <div className="text-right flex-shrink-0">
          <p className="text-base font-extrabold">{booked}<span className="text-[color:var(--theme-text-muted)]">/{cap}</span></p>
          <p className="text-[9px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)]">{fillPct}%{wl > 0 ? ` · +${wl}` : ''}</p>
        </div>
      </div>
      <div className="mt-2 h-1 rounded-full bg-zinc-500/15 overflow-hidden">
        <div className={`h-full ${tones[tone]}`} style={{ width: `${Math.min(fillPct, 100)}%` }} />
      </div>
      {canInvite && (
        <div className="flex justify-end mt-2">
          <span onClick={sendInvite}
            className="px-2 py-1 rounded text-[10px] font-bold text-emerald-500 hover:bg-emerald-500/10 inline-flex items-center gap-1 cursor-pointer"
            data-testid={`mbr-checkin-invite-${occ.id}`}>
            <Send size={9} /> Drop-in invite
          </span>
        </div>
      )}
    </button>
  );
}


function RosterDrawer({ API, headers, occ, onClose }) {
  const [roster, setRoster] = useState([]);
  const [loading, setLoading] = useState(true);
  const [walkInOpen, setWalkInOpen] = useState(false);
  const [broadcastOpen, setBroadcastOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/memberships/occurrences/${occ.id}/roster`, { headers });
      // Backend returns { occurrence, bookings:[{id, status, member:{first_name,...}}] }
      // Flatten to a row shape that's easy to render.
      const rows = (r.data.bookings || []).map((b) => ({
        booking_id: b.id,
        status: b.status,
        first_name: b.member?.first_name || '',
        last_name: b.member?.last_name || '',
        email: b.member?.email || '',
        no_show_count: b.member?.no_show_count || 0,
        created_at: b.created_at || '',
      }));
      // Iter 215t — sort: attended/booked/no_show first, then waitlist at
      // bottom so operators see who's actually coming at a glance.
      const STATUS_ORDER = { attended: 0, booked: 1, no_show: 2, waitlist: 3 };
      rows.sort((a, b) => {
        const sa = STATUS_ORDER[a.status] ?? 5;
        const sb = STATUS_ORDER[b.status] ?? 5;
        if (sa !== sb) return sa - sb;
        return (a.created_at || '').localeCompare(b.created_at || '');
      });
      // Compute waitlist positions (1-indexed) for nicer UX.
      let wlPos = 0;
      for (const row of rows) {
        if (row.status === 'waitlist') { wlPos += 1; row.waitlist_position = wlPos; }
      }
      setRoster(rows);
    } catch (e) {
      notifyApiError(notify, e, 'Roster failed');
    }
    setLoading(false);
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- todo: review missing dep(s) 'load'; pre-existing as of iter 216h226-polish-5.
  useEffect(() => { load();   }, [occ.id]);

  const mark = async (booking_id, status) => {
    try {
      await axios.post(`${API}/memberships/checkin/${occ.id}/mark`, { booking_id, status }, { headers });
      setRoster((prev) => prev.map((r) => r.booking_id === booking_id ? { ...r, status } : r));
    } catch (e) {
      notifyApiError(notify, e, 'Failed');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60" />
      <div className="relative ml-auto w-full sm:max-w-md h-full bg-[color:var(--theme-surface)] border-l border-[color:var(--theme-border)] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="mbr-checkin-roster">
        <div className="p-4 border-b border-[color:var(--theme-border)] sticky top-0 bg-[color:var(--theme-surface)] z-10">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-[9px] uppercase tracking-wider font-bold text-emerald-500">Roster</p>
              <h3 className="text-base font-extrabold">{occ.name}</h3>
              <p className="text-[11px] text-[color:var(--theme-text-muted)]">
                {occ.starts_at && new Date(occ.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                {occ.instructor_name && ` · ${occ.instructor_name}`}
              </p>
            </div>
            <Button variant="ghost" size="iconSm" onClick={onClose} icon={X} title="Close" data-testid="mbr-checkin-roster-close" />
          </div>
        </div>
        <div className="p-4">
          <div className="flex gap-2 mb-3">
            <button
              type="button" onClick={() => setWalkInOpen(true)}
              className="flex-1 h-9 rounded-lg border border-[color:var(--theme-border)] text-xs font-bold inline-flex items-center justify-center gap-1.5 hover:bg-zinc-500/5"
              data-testid="mbr-checkin-walk-in"
            >
              <UserPlus size={13} /> Walk-in
            </button>
            <button
              type="button" onClick={() => setBroadcastOpen(true)}
              className="flex-1 h-9 rounded-lg border border-[color:var(--theme-border)] text-xs font-bold inline-flex items-center justify-center gap-1.5 hover:bg-zinc-500/5"
              data-testid="mbr-checkin-broadcast"
            >
              <Megaphone size={13} /> Message class
            </button>
            <button
              type="button" onClick={() => setShareOpen(true)}
              className="flex-1 h-9 rounded-lg border border-[color:var(--theme-border)] text-xs font-bold inline-flex items-center justify-center gap-1.5 hover:bg-zinc-500/5"
              data-testid="mbr-checkin-share"
            >
              <Share2 size={13} /> Share
            </button>
          </div>
          {loading ? <Spinner /> : roster.length === 0 ? (
            <Empty title="No bookings yet" hint="When members book, they'll appear here. Use 'Walk-in' to add someone who turned up without a booking." />
          ) : (
            <div className="space-y-1.5">
              {roster.map((b) => <RosterRow key={b.booking_id} b={b} onMark={mark} />)}
            </div>
          )}
        </div>
      </div>
      {walkInOpen && <WalkInDialog API={API} headers={headers} occ={occ} onClose={() => setWalkInOpen(false)} onSuccess={load} />}
      {broadcastOpen && <BroadcastDialog API={API} headers={headers} occ={occ} onClose={() => setBroadcastOpen(false)} />}
      {shareOpen && <ShareClassDialog API={API} occ={occ} onClose={() => setShareOpen(false)} />}
    </div>
  );
}


function RosterRow({ b, onMark }) {
  const status = b.status;
  const isAttended = status === 'attended';
  const isNoShow = status === 'no_show';
  const isWaitlist = status === 'waitlist';
  return (
    <div className={`flex items-center gap-2 p-2 rounded-lg border ${
      isAttended ? 'border-emerald-500/40 bg-emerald-500/5'
      : isNoShow ? 'border-red-500/40 bg-red-500/5'
      : isWaitlist ? 'border-violet-500/40 bg-violet-500/5'
      : 'border-[color:var(--theme-border)]'
    }`}
      data-testid={`mbr-roster-${b.booking_id}`}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <p className="font-bold text-sm truncate">{b.first_name} {b.last_name}</p>
          {isWaitlist && (
            <span className="text-[9px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300"
              data-testid={`mbr-roster-waitlist-${b.booking_id}`}>
              Waitlist · #{b.waitlist_position || '?'}
            </span>
          )}
        </div>
        <p className="text-[10px] text-[color:var(--theme-text-muted)] truncate">
          {b.email}
          {b.no_show_count > 0 && ` · ${b.no_show_count} no-show${b.no_show_count === 1 ? '' : 's'}`}
        </p>
      </div>
      <div className="flex gap-1">
        {!isWaitlist && (
          <>
            <button onClick={() => onMark(b.booking_id, 'attended')}
              className={`p-2 rounded ${isAttended ? 'bg-emerald-500 text-white' : 'border border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10'}`}
              title="Mark attended" data-testid={`mbr-roster-attend-${b.booking_id}`}>
              <UserCheck size={14} />
            </button>
            <button onClick={() => onMark(b.booking_id, 'no_show')}
              className={`p-2 rounded ${isNoShow ? 'bg-red-500 text-white' : 'border border-red-500/40 text-red-500 hover:bg-red-500/10'}`}
              title="Mark no-show" data-testid={`mbr-roster-noshow-${b.booking_id}`}>
              <UserX size={14} />
            </button>
          </>
        )}
        {isWaitlist && (
          <span className="text-[10px] font-bold text-violet-300 italic pr-1 self-center">
            auto-promote
          </span>
        )}
      </div>
    </div>
  );
}


function MemberSearchDialog({ API, headers, onClose }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!q || q.length < 2) { setResults([]); return; }
    let cancelled = false;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await axios.get(`${API}/memberships/checkin/search-members?q=${encodeURIComponent(q)}`, { headers });
        if (!cancelled) setResults(r.data.results || []);
      } catch (e) {
        if (!cancelled) notify.error('Search failed');
      }
      if (!cancelled) setLoading(false);
    }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  }, [q, API, headers]);

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60" />
      <div className="relative w-full max-w-lg bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] rounded-2xl p-4 max-h-[calc(100vh-2rem)] flex flex-col" onClick={(e) => e.stopPropagation()} data-testid="mbr-checkin-search">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-extrabold flex items-center gap-2"><Search size={16} /> Find member</h3>
          <Button variant="ghost" size="iconSm" onClick={onClose} icon={X} title="Close" data-testid="mbr-checkin-search-close" />
        </div>
        <input autoFocus type="text" placeholder="Type a name, email, or phone…"
          value={q} onChange={(e) => setQ(e.target.value)}
          className="w-full px-3 py-2 rounded-md border border-[color:var(--theme-border)] bg-transparent text-sm"
          data-testid="mbr-checkin-search-input" />
        <div className="mt-3 max-h-80 overflow-y-auto space-y-1.5">
          {loading && <Spinner />}
          {!loading && q.length >= 2 && results.length === 0 && (
            <p className="text-xs text-[color:var(--theme-text-muted)] text-center py-4">No matches.</p>
          )}
          {results.map((m) => (
            <div key={m.id}
              className="flex items-start gap-2 p-2 rounded-lg border border-[color:var(--theme-border)]"
              data-testid={`mbr-checkin-search-result-${m.id}`}>
              <Users size={12} className="text-[color:var(--theme-text-muted)] mt-1 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="font-bold text-sm truncate">{m.first_name} {m.last_name}</p>
                <p className="text-[10px] text-[color:var(--theme-text-muted)] truncate">{m.email}{m.phone && ` · ${m.phone}`}</p>
              </div>
              <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-zinc-500/15">
                {m.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}


function KioskDialog({ API, headers, onClose }) {
  const [token, setToken] = useState(null);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);
  const confirm = useConfirm();

  useEffect(() => {
    axios.get(`${API}/memberships/checkin/kiosk-token`, { headers })
      .then((r) => setMeta(r.data.token))
      .catch(() => {});
  }, [API, headers]);

  const issue = async () => {
    if (meta) {
      const ok = await confirm({
        title: 'Rotate kiosk token?',
        body: 'The current kiosk URL will stop working immediately. Update any tablets running kiosk mode.',
        tone: 'warning', confirmLabel: 'Rotate',
      });
      if (!ok) return;
    }
    setLoading(true);
    try {
      const r = await axios.post(`${API}/memberships/checkin/kiosk-token`, {}, { headers });
      setToken(r.data.token);
      setMeta({ issued_at: new Date().toISOString() });
      notify.success('Kiosk token issued — copy the URL now');
    } catch (e) {
      notifyApiError(notify, e, 'Failed');
    }
    setLoading(false);
  };

  const url = token ? `${window.location.origin}/checkin/kiosk?token=${token}` : null;

  const copyUrl = async () => {
    if (!url) return;
    try { await navigator.clipboard.writeText(url); notify.success('Copied'); }
    catch { notify.error('Could not copy'); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 overflow-y-auto" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60" />
      <div className="relative w-full max-w-lg bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] rounded-2xl p-4 max-h-[calc(100vh-2rem)] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="mbr-checkin-kiosk-dlg">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-extrabold flex items-center gap-2"><Tablet size={16} /> Kiosk mode</h3>
          <Button variant="ghost" size="iconSm" onClick={onClose} icon={X} title="Close" data-testid="mbr-checkin-kiosk-dlg-close" />
        </div>
        <p className="text-xs text-[color:var(--theme-text-muted)] mb-4">
          Open the kiosk URL on a reception tablet — members check in by typing their name and entering the 6-digit code from their Pass tab.
        </p>

        {meta && !token && (
          <div className="rounded-lg border border-[color:var(--theme-border)] bg-zinc-500/5 p-3 text-xs mb-3">
            <p className="font-bold flex items-center gap-1.5"><KeyRound size={11} /> Kiosk token already issued</p>
            <p className="text-[10px] text-[color:var(--theme-text-muted)] mt-1">
              Issued {meta.issued_at && new Date(meta.issued_at).toLocaleString()}.
              We never store the secret — rotate to see a new URL.
            </p>
          </div>
        )}

        {token && url && (
          <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-3 mb-3">
            <p className="text-[10px] uppercase tracking-wider font-bold text-emerald-500 mb-1.5 flex items-center gap-1"><AlertCircle size={9} /> Save this URL — it's shown ONCE</p>
            <code className="block text-[11px] break-all bg-zinc-900 text-emerald-200 p-2 rounded font-mono" data-testid="mbr-checkin-kiosk-url">
              {url}
            </code>
            <button onClick={copyUrl}
              className="mt-2 px-2 py-1 rounded text-[10px] font-bold border border-emerald-500/40 text-emerald-500 inline-flex items-center gap-1"
              data-testid="mbr-checkin-kiosk-copy">
              <Copy size={9} /> Copy URL
            </button>
          </div>
        )}

        <button onClick={issue} disabled={loading}
          className="w-full px-3 py-2.5 rounded-md font-extrabold text-sm flex items-center justify-center gap-1.5 disabled:opacity-50"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid="mbr-checkin-kiosk-issue">
          {loading ? <Loader2 size={12} className="animate-spin" /> : <KeyRound size={12} />}
          {meta ? 'Rotate kiosk token' : 'Issue kiosk token'}
        </button>
      </div>
    </div>
  );
}


function Spinner() {
  return (
    <div className="flex items-center justify-center py-8 text-[color:var(--theme-text-muted)] text-sm gap-2">
      <Loader2 size={14} className="animate-spin" /> Loading…
    </div>
  );
}

// Iter 215r — Share dialog. Copies the social-friendly share URL and
// shows the rendered OG preview image so operators know what clients
// will see when they paste the link into IG / WhatsApp / FB.
function ShareClassDialog({ API, occ, onClose }) {
  const base = typeof window !== 'undefined' ? window.location.origin : '';
  const [slug, setSlug] = React.useState('');
  React.useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/memberships/share/org-slug`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
    }).then((r) => {
      if (!cancelled && r.data?.slug) setSlug(r.data.slug);
    }).catch(() => { /* ignore */ });
    return () => { cancelled = true; };
  }, [API]);

  // Fall back to the public class page URL if slug isn't known yet.
  const shareUrl = slug ? `${base}/api/m/${slug}/c/${occ.id}/share` : '';
  const ogUrl = slug ? `${base}/api/m/${slug}/c/${occ.id}/og.png?v=${Date.now()}` : '';

  const copy = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      notify.success('Link copied', 'Paste into Instagram, WhatsApp, or your socials.');
    } catch {
      notify.error('Copy failed', 'Long-press the link to copy manually.');
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center p-4" onClick={onClose} data-testid="share-dialog">
      <div className="absolute inset-0 bg-black/60" />
      <div className="relative w-full max-w-md rounded-2xl bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] p-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-3">
          <div>
            <p className="text-[9px] uppercase tracking-wider font-bold text-cyan-500">Share</p>
            <h3 className="text-base font-extrabold">{occ.name}</h3>
          </div>
          <Button variant="ghost" size="iconSm" onClick={onClose} icon={X} title="Close" data-testid="share-dialog-close" />
        </div>
        {ogUrl ? (
          <img src={ogUrl} alt="Social preview" width={520} height={273}
            className="w-full rounded-lg border border-[color:var(--theme-border)] aspect-[1200/630] object-cover"
            data-testid="share-og-preview" />
        ) : (
          <div className="w-full aspect-[1200/630] rounded-lg border border-dashed border-[color:var(--theme-border)] grid place-items-center text-xs text-[color:var(--theme-text-muted)]">
            Preview loading…
          </div>
        )}
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-[color:var(--theme-border)] bg-white/5 p-2">
          <input readOnly value={shareUrl}
            className="flex-1 bg-transparent text-xs font-mono min-w-0"
            data-testid="share-url" />
          <button onClick={copy}
            className="h-9 px-3 rounded-lg bg-[var(--color-brand-cyan)] text-[var(--color-ink)] text-xs font-bold inline-flex items-center gap-1"
            data-testid="share-copy">
            <Copy size={12} /> Copy
          </button>
        </div>
        <p className="text-[11px] text-[color:var(--theme-text-muted)] mt-2">
          Paste this link anywhere — Instagram, WhatsApp, Facebook, Twitter, email — and they'll see the preview image above.
        </p>
      </div>
    </div>
  );
}

function Empty({ title, hint }) {
  return (
    <div className="rounded-xl border border-dashed border-[color:var(--theme-border)] p-8 text-center">
      <p className="text-sm font-bold">{title}</p>
      {hint && <p className="text-xs text-[color:var(--theme-text-muted)] mt-1">{hint}</p>}
    </div>
  );
}

// Iter 215q — walk-in dialog. One form → creates member (if new) + booking
// with status=attended in a single server call. Closes on success, parent
// re-loads the roster.
function WalkInDialog({ API, headers, occ, onClose, onSuccess }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!name.trim()) { notify.error('Name required', 'Enter at least a first name.'); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/memberships/checkin/walk-in`, {
        name: name.trim(),
        email: email.trim() || undefined,
        phone: phone.trim() || undefined,
        occurrence_id: occ.id,
      }, { headers });
      notify.success('Walk-in checked in', `${name.trim()} added to the register.`);
      onSuccess();
      onClose();
    } catch (e) {
      notifyApiError(notify, e, 'Walk-in failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center p-4" onClick={onClose} data-testid="walk-in-dialog">
      <div className="absolute inset-0 bg-black/60" />
      <div className="relative w-full max-w-sm rounded-2xl bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] p-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-3">
          <div>
            <p className="text-[9px] uppercase tracking-wider font-bold text-cyan-500">Walk-in</p>
            <h3 className="text-base font-extrabold">Add &amp; check in</h3>
          </div>
          <Button variant="ghost" size="iconSm" onClick={onClose} icon={X} title="Close" data-testid="walk-in-dialog-close" />
        </div>
        <div className="space-y-2">
          <input autoFocus placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)}
            className="w-full h-11 rounded-lg border border-[color:var(--theme-border)] bg-transparent px-3 text-sm" data-testid="walk-in-name" />
          <input placeholder="Email (optional)" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            className="w-full h-11 rounded-lg border border-[color:var(--theme-border)] bg-transparent px-3 text-sm" data-testid="walk-in-email" />
          <input placeholder="Phone (optional)" value={phone} onChange={(e) => setPhone(e.target.value)}
            className="w-full h-11 rounded-lg border border-[color:var(--theme-border)] bg-transparent px-3 text-sm" data-testid="walk-in-phone" />
          <p className="text-[11px] text-[color:var(--theme-text-muted)]">We'll mark them attended immediately and create a lightweight member record you can flesh out later.</p>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button type="button" onClick={onClose} className="h-10 px-4 rounded-lg border border-[color:var(--theme-border)] text-sm font-semibold">Cancel</button>
          <button type="button" onClick={submit} disabled={saving}
            className="h-10 px-4 rounded-lg bg-[var(--color-brand-cyan)] text-[var(--color-ink)] text-sm font-bold disabled:opacity-50" data-testid="walk-in-submit">
            {saving ? <Loader2 size={14} className="animate-spin" /> : 'Check in'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Iter 215q — bulk message a class. Email only for now (Twilio SMS
// is still mocked). Shows delivered/failed count from the server.
function BroadcastDialog({ API, headers, occ, onClose }) {
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (message.trim().length < 2) { notify.error('Message required'); return; }
    setSaving(true);
    try {
      const { data } = await axios.post(`${API}/memberships/classes/${occ.id}/broadcast`, {
        message: message.trim(),
        subject: subject.trim() || undefined,
      }, { headers });
      notify.success('Message sent', `${data.delivered}/${data.recipient_count} delivered · ${data.skipped_no_email} skipped · ${data.failed} failed`);
      onClose();
    } catch (e) {
      notifyApiError(notify, e, 'Send failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center p-4" onClick={onClose} data-testid="broadcast-dialog">
      <div className="absolute inset-0 bg-black/60" />
      <div className="relative w-full max-w-md rounded-2xl bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] p-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-3">
          <div>
            <p className="text-[9px] uppercase tracking-wider font-bold text-amber-500">Broadcast</p>
            <h3 className="text-base font-extrabold">Message this class</h3>
          </div>
          <Button variant="ghost" size="iconSm" onClick={onClose} icon={X} title="Close" data-testid="broadcast-dialog-close" />
        </div>
        <div className="space-y-2">
          <input placeholder={`Subject (default: "Update: ${occ.name}")`} value={subject} onChange={(e) => setSubject(e.target.value)}
            className="w-full h-11 rounded-lg border border-[color:var(--theme-border)] bg-transparent px-3 text-sm" data-testid="broadcast-subject" />
          <textarea rows={5} placeholder="Quick update — please bring a mat, or meet at the park entrance…"
            value={message} onChange={(e) => setMessage(e.target.value)}
            className="w-full rounded-lg border border-[color:var(--theme-border)] bg-transparent px-3 py-2 text-sm" data-testid="broadcast-message" />
          <p className="text-[11px] text-[color:var(--theme-text-muted)]">Sent via email to everyone booked in or attended. SMS coming soon.</p>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button type="button" onClick={onClose} className="h-10 px-4 rounded-lg border border-[color:var(--theme-border)] text-sm font-semibold">Cancel</button>
          <button type="button" onClick={submit} disabled={saving}
            className="h-10 px-4 rounded-lg bg-[var(--color-brand-cyan)] text-[var(--color-ink)] text-sm font-bold disabled:opacity-50" data-testid="broadcast-submit">
            {saving ? <Loader2 size={14} className="animate-spin" /> : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}
