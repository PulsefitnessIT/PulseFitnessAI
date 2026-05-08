/**
 * ClassEditorModal — Memberships console.
 *
 * Iter 215bv — extracted from MembershipsConsole.js. Create / edit a
 * recurring class template. On create, the backend materialises 8
 * weeks of occurrences automatically.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { ModalShell, Input, ModalActions } from '@/pages/Memberships/_shared';

const DAYS_OF_WEEK = [
  { value: 0, label: 'Mon' }, { value: 1, label: 'Tue' }, { value: 2, label: 'Wed' },
  { value: 3, label: 'Thu' }, { value: 4, label: 'Fri' }, { value: 5, label: 'Sat' }, { value: 6, label: 'Sun' },
];

export default function ClassEditorModal({ API, headers, template, onClose }) {
  const isNew = !template;
  const [f, setF] = useState(() => ({
    name: template?.name || '',
    category: template?.category || 'Group',
    description: template?.description || '',
    instructor_id: template?.instructor_id || '',
    instructor_name: template?.instructor_name || '',
    room_name: template?.room_name || '',
    duration_min: template?.duration_min ?? 45,
    capacity: template?.capacity ?? 20,
    colour: template?.colour || 'var(--color-brand-cyan)',
    recurs_days: template?.recurs_days || [],
    start_time: template?.start_time || '07:00',
    booking_opens_hours_before: template?.booking_opens_hours_before ?? 168,
    cancellation_cutoff_hours_before: template?.cancellation_cutoff_hours_before ?? 12,
    waitlist_enabled: template?.waitlist_enabled ?? true,
    max_waitlist: template?.max_waitlist ?? 10,
    credits_to_book: template?.credits_to_book ?? 1,
  }));
  const [saving, setSaving] = useState(false);
  const [instructors, setInstructors] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/memberships/instructors`, { headers });
        setInstructors(data.instructors || []);
      } catch { /* non-fatal */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const up = (k) => (v) => setF((prev) => ({ ...prev, [k]: v }));
  const toggleDay = (d) => setF((prev) => ({
    ...prev, recurs_days: prev.recurs_days.includes(d)
      ? prev.recurs_days.filter((x) => x !== d)
      : [...prev.recurs_days, d].sort(),
  }));

  const submit = async () => {
    if (!f.name.trim()) { notify.error('Class name required'); return; }
    if (isNew && f.recurs_days.length === 0) { notify.error('Pick at least one day'); return; }
    const payload = {
      ...f,
      duration_min: Number(f.duration_min) || 45,
      capacity: Number(f.capacity) || 20,
      booking_opens_hours_before: Number(f.booking_opens_hours_before) || 168,
      cancellation_cutoff_hours_before: Number(f.cancellation_cutoff_hours_before) || 12,
      max_waitlist: Number(f.max_waitlist) || 10,
      credits_to_book: Number(f.credits_to_book) || 1,
    };
    setSaving(true);
    try {
      if (isNew) await axios.post(`${API}/memberships/classes/templates`, payload, { headers });
      else await axios.patch(`${API}/memberships/classes/templates/${template.id}`, payload, { headers });
      notify.success(isNew ? 'Class created · 8 weeks of occurrences generated' : 'Class updated');
      onClose(true);
    } catch (e) { notifyApiError(notify, e, 'Failed'); }
    finally { setSaving(false); }
  };

  return (
    <ModalShell title={isNew ? 'New class' : 'Edit class'} eyebrow="Template" testId="mbr-class-editor"
      onClose={() => onClose(false)} wide>
      <Input label="Class name" value={f.name} onChange={up('name')} required testid="mbr-class-name" />
      <div className="grid grid-cols-2 gap-3">
        <Input label="Category" value={f.category} onChange={up('category')} testid="mbr-class-category" />
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Colour</span>
          <input type="color" value={f.colour} onChange={(e) => up('colour')(e.target.value)} className="mt-1 h-10 w-16 rounded cursor-pointer bg-transparent" data-testid="mbr-class-colour" />
        </label>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Instructor</span>
          <select
            value={f.instructor_id || ''}
            onChange={(e) => {
              const id = e.target.value;
              const picked = instructors.find((i) => i.id === id);
              setF((prev) => ({
                ...prev,
                instructor_id: id || '',
                instructor_name: picked ? picked.name : prev.instructor_name,
              }));
            }}
            className="mt-1 w-full rounded-lg border border-[color:var(--theme-border)] bg-transparent px-2 py-2 text-sm"
            data-testid="mbr-class-instructor-picker">
            <option value="">— none —</option>
            {instructors.map((i) => (
              <option key={i.id} value={i.id}>{i.name}{i.headline ? ` · ${i.headline}` : ''}</option>
            ))}
          </select>
          {instructors.length === 0 && (
            <p className="mt-1 text-[10px] text-[color:var(--theme-text-muted)]">
              No instructors yet — add one under the Instructors tab, or use the free-text override below.
            </p>
          )}
          <input type="text" value={f.instructor_name} onChange={(e) => up('instructor_name')(e.target.value)}
            placeholder="Or type a name (no profile)"
            className="mt-1 w-full rounded-lg border border-[color:var(--theme-border)] bg-transparent px-2 py-1 text-xs text-[color:var(--theme-text-muted)]"
            data-testid="mbr-class-instructor" />
        </label>
        <Input label="Room / studio" value={f.room_name} onChange={up('room_name')} testid="mbr-class-room" />
      </div>
      <div>
        <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] block mb-1.5">Days of week</span>
        <div className="flex gap-1.5 flex-wrap">
          {DAYS_OF_WEEK.map((d) => {
            const on = f.recurs_days.includes(d.value);
            return (
              <button key={d.value} type="button" onClick={() => toggleDay(d.value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-extrabold uppercase tracking-wider transition border ${on ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] border-[var(--color-brand-cyan)]' : 'bg-transparent text-[color:var(--theme-text-muted)] border-[color:var(--theme-border)] hover:bg-black/[0.04] dark:hover:bg-white dark:bg-zinc-900/5'}`}
                data-testid={`mbr-class-day-${d.value}`}>
                {d.label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Input label="Start time" value={f.start_time} onChange={up('start_time')} testid="mbr-class-start" />
        <Input label="Duration (min)" value={f.duration_min} onChange={up('duration_min')} type="number" testid="mbr-class-duration" />
        <Input label="Capacity" value={f.capacity} onChange={up('capacity')} type="number" testid="mbr-class-capacity" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Input label="Booking opens (hrs)" value={f.booking_opens_hours_before} onChange={up('booking_opens_hours_before')} type="number" testid="mbr-class-opens" />
        <Input label="Cancel cutoff (hrs)" value={f.cancellation_cutoff_hours_before} onChange={up('cancellation_cutoff_hours_before')} type="number" testid="mbr-class-cutoff" />
        <Input label="Credits to book" value={f.credits_to_book} onChange={up('credits_to_book')} type="number" testid="mbr-class-credits" />
      </div>
      <div className="grid grid-cols-2 gap-3 items-end">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.waitlist_enabled} onChange={(e) => up('waitlist_enabled')(e.target.checked)} data-testid="mbr-class-waitlist" />
          <span className="text-[color:var(--theme-text-muted)]">Waitlist enabled</span>
        </label>
        <Input label="Max waitlist" value={f.max_waitlist} onChange={up('max_waitlist')} type="number" testid="mbr-class-waitlist-max" />
      </div>
      <ModalActions onCancel={() => onClose(false)} onSave={submit} saving={saving} testId="mbr-class-save" />
    </ModalShell>
  );
}
