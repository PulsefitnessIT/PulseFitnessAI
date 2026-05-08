/**
 * Course builder + pupil enrolment manager.
 *
 * Rendered as a subtab inside the Plans tab of the memberships console.
 * Lists every course-kind plan with:
 *   • materialised session dates (with excluded-date pills)
 *   • enrolled pupils with un-enrol
 *   • bulk enrolment from the member roster (pick multi)
 *
 * Iter 215x.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { GraduationCap, Users, Calendar, X, UserPlus, Loader2, Info, PoundSterling } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

function formatDate(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' }); }
  catch { return iso; }
}

export default function CoursesView({ API, headers }) {
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);

  const loadCourses = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/memberships/plans`, { headers });
      const only = (data.plans || []).filter((p) => p.kind === 'course' && !p.archived);
      setCourses(only);
      if (only.length && !selectedId) setSelectedId(only[0].id);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load courses');
    } finally { setLoading(false); }
  }, [API, headers, selectedId]);

  useEffect(() => { loadCourses(); /* eslint-disable-next-line */ }, []);

  const selected = useMemo(
    () => courses.find((c) => c.id === selectedId) || null,
    [courses, selectedId],
  );

  return (
    <div data-testid="mbr-courses">
      <div className="flex items-end justify-between gap-4 flex-wrap mb-4">
        <div>
          <h3 className="text-xl font-black tracking-tight">Course builder</h3>
          <p className="mt-1 text-sm text-[color:var(--theme-text-muted)]">
            Build multi-week / term courses — enrol pupils once, auto-book every session, skip school holidays, invoice monthly.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="p-8 text-center text-sm text-[color:var(--theme-text-muted)]"><Loader2 className="mx-auto animate-spin" /></div>
      ) : courses.length === 0 ? (
        <div className="p-8 text-center rounded-xl border border-dashed border-[color:var(--theme-border)]">
          <GraduationCap className="mx-auto mb-3 text-[color:var(--color-brand-cyan)]" size={28} />
          <div className="font-bold mb-1">No courses yet</div>
          <div className="text-sm text-[color:var(--theme-text-muted)]">
            Create a new plan with kind = "Course" to get started. The plan's sessions, start date and excluded holidays become the course schedule.
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-4">
          <div className="space-y-1.5" data-testid="mbr-courses-list">
            {courses.map((c) => (
              <button key={c.id} onClick={() => setSelectedId(c.id)}
                className={`w-full text-left rounded-lg px-3 py-2 border transition ${
                  selectedId === c.id
                    ? 'border-[color:var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.08)]'
                    : 'border-[color:var(--theme-border)] hover:bg-white/5'
                }`}
                data-testid={`mbr-course-row-${c.id}`}>
                <div className="font-bold text-sm truncate flex items-center gap-1.5">
                  <GraduationCap size={12} /> {c.name}
                </div>
                <div className="text-[11px] text-[color:var(--theme-text-muted)] mt-0.5">
                  {(c.course_occurrence_ids?.length || 0)} sessions · £{(c.price_pence / 100).toFixed(2)}
                  {c.smoothed && ' · smoothed'}
                </div>
              </button>
            ))}
          </div>
          {selected ? (
            <CourseDetail API={API} headers={headers} course={selected} onRefresh={loadCourses} />
          ) : (
            <div className="p-6 text-[color:var(--theme-text-muted)] text-sm">Pick a course on the left to see its pupils and sessions.</div>
          )}
        </div>
      )}
    </div>
  );
}

function CourseDetail({ API, headers, course, onRefresh }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showEnrol, setShowEnrol] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/memberships/plans/${course.id}/enrolments`, { headers });
      setData(data);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load enrolments');
    } finally { setLoading(false); }
  }, [API, headers, course.id]);

  useEffect(() => { load(); }, [load]);

  const unenrol = async (member) => {
    if (!window.confirm(`Un-enrol ${member.first_name} ${member.last_name}? Future sessions will be cancelled.`)) return;
    try {
      const { data: r } = await axios.delete(
        `${API}/memberships/plans/${course.id}/enrolments/${member.id}`,
        { headers },
      );
      notify.success(`Un-enrolled — ${r.bookings_cancelled} bookings cancelled`);
      load();
    } catch (e) {
      notifyApiError(notify, e, 'Un-enrol failed');
    }
  };

  if (loading || !data) return <div className="p-8 text-center"><Loader2 className="mx-auto animate-spin" /></div>;

  const sessions = data.sessions || [];
  const pupils = data.enrolled || [];
  const pricePerPupil = course.price_pence / 100;
  const smoothedMonthly = course.smoothed && course.smoothed_annual_pence
    ? course.smoothed_annual_pence / (course.smoothed_months || 12) / 100
    : null;

  return (
    <div className="space-y-4" data-testid="mbr-course-detail">
      {/* Headline */}
      <div className="rounded-xl border border-[color:var(--theme-border)] p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <h4 className="text-lg font-extrabold">{course.name}</h4>
          <span className="text-[10px] font-bold uppercase tracking-wider rounded-full px-2 py-0.5 bg-white/5">
            {sessions.length} sessions
          </span>
          <span className="ml-auto inline-flex items-center gap-1 text-sm font-bold">
            <PoundSterling size={14} /> £{pricePerPupil.toFixed(2)} per pupil
          </span>
          {smoothedMonthly && (
            <span className="text-xs text-[color:var(--color-brand-cyan)] font-bold">
              · £{smoothedMonthly.toFixed(2)}/month smoothed
            </span>
          )}
        </div>
        {course.smoothed && (
          <div className="mt-3 p-3 rounded-lg bg-[rgb(var(--rgb-brand-cyan)/0.06)] border border-[color:var(--color-brand-cyan)]/20 flex gap-2 text-xs">
            <Info size={14} className="shrink-0 text-[color:var(--color-brand-cyan)] mt-0.5" />
            <div>
              Pro-rata monthly: each pupil's monthly invoice will include a
              <strong> £{smoothedMonthly.toFixed(2)} </strong>
              smoothed installment line. If a pupil is on multiple courses, all
              installments + individual class charges are grouped into one invoice.
            </div>
          </div>
        )}
      </div>

      {/* Sessions */}
      <div className="rounded-xl border border-[color:var(--theme-border)] p-4">
        <div className="flex items-center justify-between mb-2">
          <h5 className="font-bold flex items-center gap-1.5"><Calendar size={14} /> Schedule</h5>
          {(course.course_excluded_dates || []).length > 0 && (
            <span className="text-[11px] text-amber-400 font-bold">
              Skipping {course.course_excluded_dates.length} date{course.course_excluded_dates.length === 1 ? '' : 's'}
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-2">
          {sessions.map((s) => {
            const full = (s.bookings_count || 0) >= (s.capacity || 0);
            return (
              <div key={s.id} className="rounded-lg border border-[color:var(--theme-border)] p-2.5 text-xs"
                data-testid={`mbr-course-session-${s.id}`}>
                <div className="font-bold text-sm">{formatDate(s.starts_at)}</div>
                <div className="text-[10px] text-[color:var(--theme-text-muted)] mt-1">
                  Session #{s.course_session_index || '?'}
                </div>
                <div className={`mt-1 text-[11px] font-bold ${full ? 'text-amber-400' : 'text-[color:var(--color-brand-cyan)]'}`}>
                  {s.bookings_count || 0}/{s.capacity || 0} enrolled
                </div>
              </div>
            );
          })}
        </div>
        {(course.course_excluded_dates || []).length > 0 && (
          <div className="mt-3 pt-3 border-t border-[color:var(--theme-border)]">
            <div className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] mb-2">Excluded dates</div>
            <div className="flex flex-wrap gap-1.5">
              {(course.course_excluded_dates || []).map((d) => (
                <span key={d} className="text-[11px] font-bold rounded-full bg-amber-500/15 text-amber-300 px-2 py-0.5">
                  {d}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Pupils */}
      <div className="rounded-xl border border-[color:var(--theme-border)] p-4">
        <div className="flex items-center justify-between mb-3">
          <h5 className="font-bold flex items-center gap-1.5"><Users size={14} /> Enrolled pupils ({pupils.length})</h5>
          <button onClick={() => setShowEnrol(true)}
            className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-extrabold"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="mbr-course-enrol">
            <UserPlus size={12} /> Enrol pupils
          </button>
        </div>
        {pupils.length === 0 ? (
          <div className="text-sm text-[color:var(--theme-text-muted)] py-4 text-center">
            No pupils enrolled yet. Click "Enrol pupils" to bulk-add from your member roster.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
            {pupils.map((p) => (
              <div key={p.id} className="flex items-center gap-2 rounded-lg px-3 py-2 bg-white/5"
                data-testid={`mbr-course-pupil-${p.id}`}>
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-sm truncate">{p.first_name} {p.last_name}</div>
                  <div className="text-[11px] text-[color:var(--theme-text-muted)] truncate">{p.email}</div>
                </div>
                <button onClick={() => unenrol(p)}
                  className="p-1 rounded text-red-400 hover:bg-red-500/10"
                  title="Un-enrol"
                  data-testid={`mbr-course-unenrol-${p.id}`}>
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {showEnrol && (
        <EnrolDialog API={API} headers={headers} course={course}
          alreadyEnrolled={pupils.map((p) => p.id)}
          onClose={(changed) => { setShowEnrol(false); if (changed) { load(); onRefresh?.(); } }} />
      )}
    </div>
  );
}

function EnrolDialog({ API, headers, course, alreadyEnrolled, onClose }) {
  const [members, setMembers] = useState([]);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(new Set());
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/memberships/members`, { headers });
        const all = (data.members || []).filter((m) => m.status !== 'cancelled');
        setMembers(all);
      } catch (e) {
        notifyApiError(notify, e, 'Failed to load members');
      } finally { setLoading(false); }
    })();
    // eslint-disable-next-line
  }, []);

  const enrolledSet = useMemo(() => new Set(alreadyEnrolled), [alreadyEnrolled]);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return members
      .filter((m) => !enrolledSet.has(m.id))
      .filter((m) => !q || [
        m.first_name, m.last_name, m.email,
      ].filter(Boolean).some((s) => s.toLowerCase().includes(q)));
  }, [members, search, enrolledSet]);

  const toggle = (id) => {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const save = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) { notify.info('Pick at least one pupil'); return; }
    setSaving(true);
    try {
      const { data } = await axios.post(
        `${API}/memberships/plans/${course.id}/enrol`,
        { member_ids: ids },
        { headers },
      );
      notify.success(
        `Enrolled ${data.enrolled_member_count} pupil${data.enrolled_member_count === 1 ? '' : 's'} · ` +
        `${data.bookings_created} booking${data.bookings_created === 1 ? '' : 's'} created` +
        (data.bookings_skipped_already_enrolled ? ` · ${data.bookings_skipped_already_enrolled} skipped (already booked)` : ''),
      );
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, 'Enrol failed');
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="mbr-course-enrol-dialog">
      <div className="absolute inset-0 bg-black/70" onClick={() => onClose(false)} />
      <div className="relative w-full max-w-xl max-h-[80vh] flex flex-col bg-[color:var(--theme-bg-1)] border border-[color:var(--theme-border)] rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-[color:var(--theme-border)]">
          <h3 className="font-black text-lg">Enrol pupils in {course.name}</h3>
          <p className="text-xs text-[color:var(--theme-text-muted)] mt-1">
            Each pupil will be auto-booked into all {course.course_occurrence_ids?.length || 0} sessions.
          </p>
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search pupils by name or email…"
            className="mt-3 w-full rounded-lg border border-[color:var(--theme-border)] bg-transparent px-3 py-2 text-sm"
            data-testid="mbr-course-enrol-search" />
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {loading ? <Loader2 className="mx-auto animate-spin my-8" /> :
           filtered.length === 0 ? (
            <div className="text-center text-sm text-[color:var(--theme-text-muted)] py-8">
              {members.length === 0 ? 'No members in your roster yet. Add pupils from the Members tab first.'
                : enrolledSet.size >= members.length ? 'All active members are already enrolled 🎉'
                : 'No matching pupils.'}
            </div>
          ) : filtered.map((m) => {
            const on = selected.has(m.id);
            return (
              <button key={m.id} type="button" onClick={() => toggle(m.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition ${
                  on ? 'bg-[rgb(var(--rgb-brand-cyan)/0.12)] border border-[color:var(--color-brand-cyan)]' : 'hover:bg-white/5 border border-transparent'
                }`}
                data-testid={`mbr-course-enrol-candidate-${m.id}`}>
                <div className={`w-4 h-4 rounded border-2 grid place-items-center text-[10px] ${on ? 'bg-[color:var(--color-brand-cyan)] border-[color:var(--color-brand-cyan)] text-black' : 'border-white/30'}`}>
                  {on && '✓'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-sm truncate">{m.first_name} {m.last_name}</div>
                  <div className="text-[11px] text-[color:var(--theme-text-muted)] truncate">{m.email}</div>
                </div>
              </button>
            );
          })}
        </div>
        <div className="p-3 border-t border-[color:var(--theme-border)] flex items-center gap-2">
          <span className="text-xs text-[color:var(--theme-text-muted)]">
            {selected.size} selected
          </span>
          <button onClick={() => onClose(false)}
            className="ml-auto px-3 py-2 text-xs font-bold rounded-lg border border-[color:var(--theme-border)] hover:bg-white/5">Cancel</button>
          <button onClick={save} disabled={saving || selected.size === 0}
            className="px-4 py-2 text-sm font-extrabold rounded-lg disabled:opacity-50"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="mbr-course-enrol-confirm">
            {saving ? 'Enrolling…' : `Enrol ${selected.size} pupil${selected.size === 1 ? '' : 's'}`}
          </button>
        </div>
      </div>
    </div>
  );
}
