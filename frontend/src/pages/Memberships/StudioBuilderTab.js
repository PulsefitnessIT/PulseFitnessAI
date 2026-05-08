/**
 * StudioBuilderTab — Phase A (Iter 216z)
 *
 * The "command centre" for studio operators:
 *   1. Studio identity (industry preset chooser)
 *   2. Terms & holiday manager
 *   3. Drag-and-drop weekly timetable builder
 *
 * Drag a class template card into a day-column slot to set the day-of-week
 * + start-time and instantly persist via PATCH /memberships/classes/templates/{id}.
 * Drop into the "Idle templates" rail to detach all weekday recurrences.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Plus, Trash2, Calendar as CalendarIcon, GripVertical, Sparkles,
  AlertTriangle, Save, Loader2, X, RefreshCw, Tag,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
// 30-minute slots from 06:00 → 22:00 (covers most studios)
const SLOT_MINUTES = 30;
const SLOTS = Array.from({ length: ((22 - 6) * 60) / SLOT_MINUTES }, (_, i) => {
  const total = 6 * 60 + i * SLOT_MINUTES;
  const hh = String(Math.floor(total / 60)).padStart(2, '0');
  const mm = String(total % 60).padStart(2, '0');
  return `${hh}:${mm}`;
});

function timeToSlotIndex(t) {
  const [hh, mm] = (t || '07:00').split(':').map((x) => parseInt(x, 10));
  const total = (hh || 7) * 60 + (mm || 0);
  const fromBase = total - 6 * 60;
  return Math.max(0, Math.min(SLOTS.length - 1, Math.round(fromBase / SLOT_MINUTES)));
}

export default function StudioBuilderTab({ API, headers }) {
  const auth = useMemo(() => ({ headers }), [headers]);
  const [settings, setSettings] = useState(null);
  const [industries, setIndustries] = useState([]);
  const [terms, setTerms] = useState([]);
  const [activeTermId, setActiveTermId] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);
  const [rematerialising, setRematerialising] = useState(false);
  const [showTermForm, setShowTermForm] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, ind, t, tpl] = await Promise.all([
        axios.get(`${API}/memberships/studio/settings`, auth),
        axios.get(`${API}/memberships/studio/industries`, auth),
        axios.get(`${API}/memberships/terms`, auth),
        axios.get(`${API}/memberships/classes/templates`, auth),
      ]);
      setSettings(s.data || {});
      setIndustries(ind.data?.industries || []);
      setTerms(t.data?.terms || []);
      setActiveTermId(t.data?.active_term_id || null);
      setTemplates(tpl.data?.templates || []);
    } catch (e) {
      notify.error('Failed to load studio builder', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [API, auth]);
  useEffect(() => { load(); }, [load]);

  const setIndustry = async (industryId) => {
    try {
      await axios.post(`${API}/memberships/studio/settings`, {
        studio_mode: true, studio_industry: industryId,
      }, auth);
      notify.success('Industry saved', industries.find((i) => i.id === industryId)?.label);
      await load();
    } catch (e) {
      notify.error('Failed to save', e?.response?.data?.detail || e.message);
    }
  };

  const onDropToSlot = async (template, dayIdx, timeStr) => {
    setSavingId(template.id);
    const recurs = Array.from(new Set([...(template.recurs_days || []), dayIdx])).sort();
    try {
      await axios.patch(`${API}/memberships/classes/templates/${template.id}`, {
        recurs_days: recurs,
        start_time: timeStr,
      }, auth);
      notify.success('Class scheduled', `${template.name} · ${DAYS[dayIdx]} ${timeStr}`);
      await load();
    } catch (e) {
      notify.error('Update failed', e?.response?.data?.detail || e.message);
    } finally { setSavingId(null); }
  };

  const onDropToIdle = async (template) => {
    if (!template.recurs_days?.length) return;
    setSavingId(template.id);
    try {
      await axios.patch(`${API}/memberships/classes/templates/${template.id}`, {
        recurs_days: [],
      }, auth);
      notify.success('Removed from timetable', template.name);
      await load();
    } catch (e) {
      notify.error('Update failed', e?.response?.data?.detail || e.message);
    } finally { setSavingId(null); }
  };

  const removeFromDay = async (template, dayIdx) => {
    setSavingId(template.id);
    const next = (template.recurs_days || []).filter((d) => d !== dayIdx);
    try {
      await axios.patch(`${API}/memberships/classes/templates/${template.id}`, {
        recurs_days: next,
      }, auth);
      await load();
    } catch (e) {
      notify.error('Update failed', e?.response?.data?.detail || e.message);
    } finally { setSavingId(null); }
  };

  const rebuildTerm = async () => {
    if (!window.confirm('Rebuild the timetable for the active term?\n\nEmpty future occurrences will be regenerated honouring holiday blocks. Booked classes are preserved.')) return;
    setRematerialising(true);
    try {
      const r = await axios.post(`${API}/memberships/terms/rematerialise`, {}, auth);
      notify.success('Timetable rebuilt', `${r.data?.occurrences_made ?? 0} new occurrences`);
    } catch (e) {
      notify.error('Rebuild failed', e?.response?.data?.detail || e.message);
    } finally { setRematerialising(false); }
  };

  const idleTemplates = templates.filter((t) => !(t.recurs_days?.length));
  const scheduledTemplates = templates.filter((t) => t.recurs_days?.length);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground p-6" data-testid="studio-builder-loading">
        <Loader2 size={14} className="animate-spin" /> Loading studio builder…
      </div>
    );
  }

  const industry = settings?.industry_preset;

  return (
    <div className="space-y-5" data-testid="studio-builder">
      {/* Identity */}
      <IdentityCard
        industries={industries}
        currentIndustry={settings?.studio_industry}
        currentLabel={industry?.label}
        onChoose={setIndustry}
      />

      {/* Terms */}
      <TermsCard
        terms={terms}
        activeTermId={activeTermId}
        showForm={showTermForm}
        onToggleForm={() => setShowTermForm((v) => !v)}
        onCreate={async (body) => {
          try {
            await axios.post(`${API}/memberships/terms`, body, auth);
            setShowTermForm(false);
            notify.success('Term created', body.name);
            await load();
          } catch (e) {
            notify.error('Create failed', e?.response?.data?.detail || e.message);
          }
        }}
        onDelete={async (term) => {
          if (!window.confirm(`Archive term "${term.name}"?`)) return;
          try {
            await axios.delete(`${API}/memberships/terms/${term.id}`, auth);
            await load();
          } catch (e) {
            notify.error('Delete failed', e?.response?.data?.detail || e.message);
          }
        }}
        onAddHoliday={async (term) => {
          const name = window.prompt('Holiday name (e.g. Half-term, Easter):');
          if (!name) return;
          const starts = window.prompt('Start date YYYY-MM-DD:', term.starts_on);
          if (!starts) return;
          const ends = window.prompt('End date YYYY-MM-DD:', starts);
          if (!ends) return;
          try {
            await axios.post(`${API}/memberships/terms/${term.id}/holidays`,
              { name, starts_on: starts, ends_on: ends }, auth);
            await load();
            notify.success('Holiday added');
          } catch (e) {
            notify.error('Failed', e?.response?.data?.detail || e.message);
          }
        }}
        onRemoveHoliday={async (term, block) => {
          try {
            await axios.delete(`${API}/memberships/terms/${term.id}/holidays/${block.id}`, auth);
            await load();
          } catch (e) {
            notify.error('Failed', e?.response?.data?.detail || e.message);
          }
        }}
      />

      {/* Drag-drop builder */}
      <BuilderGrid
        templates={templates}
        idleTemplates={idleTemplates}
        scheduledTemplates={scheduledTemplates}
        savingId={savingId}
        rematerialising={rematerialising}
        onDropToSlot={onDropToSlot}
        onDropToIdle={onDropToIdle}
        onRemoveFromDay={removeFromDay}
        onRebuildTerm={rebuildTerm}
        onRefresh={load}
        industry={industry}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Identity
// ─────────────────────────────────────────────────────────────────
function IdentityCard({ industries, currentIndustry, currentLabel, onChoose }) {
  return (
    <section
      className="rounded-2xl border p-4 bg-white"
      style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }}
      data-testid="studio-builder-identity"
    >
      <header className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60">Studio identity</p>
          <h3 className="text-base font-bold inline-flex items-center gap-2">
            <Sparkles size={14} className="text-violet-500" />
            {currentIndustry ? `Tailored for ${currentLabel || currentIndustry}` : 'Pick your studio type'}
          </h3>
        </div>
      </header>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2" data-testid="studio-builder-industry-grid">
        {industries.map((ind) => {
          const active = ind.id === currentIndustry;
          return (
            <button
              key={ind.id}
              type="button"
              onClick={() => onChoose(ind.id)}
              className={`text-left rounded-xl border p-3 transition-all duration-150 hover:shadow ${active ? 'ring-2' : ''}`}
              style={{
                borderColor: active ? 'var(--color-brand-blue, #1d4ed8)' : 'var(--theme-border, #e2e8f0)',
                background: active ? 'rgba(29,78,216,0.06)' : 'var(--theme-surface, #fff)',
              }}
              data-testid={`studio-industry-option-${ind.id}`}
            >
              <p className="text-sm font-bold">{ind.label}</p>
              <p className="text-[11px] opacity-60 mt-0.5">
                {(ind.disciplines || []).slice(0, 4).join(' · ') || 'Custom'}
              </p>
              <div className="flex gap-1 mt-2">
                {(ind.default_palette || []).slice(0, 5).map((c) => (
                  <span key={c} style={{
                    width: 12, height: 12, borderRadius: 4, background: c,
                    border: '1px solid rgba(0,0,0,0.05)',
                  }} />
                ))}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────
// Terms
// ─────────────────────────────────────────────────────────────────
function TermsCard({ terms, activeTermId, showForm, onToggleForm, onCreate, onDelete, onAddHoliday, onRemoveHoliday }) {
  const [name, setName] = useState('');
  const [starts, setStarts] = useState('');
  const [ends, setEnds] = useState('');
  const [isDefault, setIsDefault] = useState(true);
  const submit = (e) => {
    e.preventDefault();
    if (!name.trim() || !starts || !ends) {
      notify.error('Missing fields', 'Name, start and end are all required');
      return;
    }
    onCreate({ name: name.trim(), starts_on: starts, ends_on: ends, is_default: isDefault });
    setName(''); setStarts(''); setEnds(''); setIsDefault(true);
  };
  return (
    <section
      className="rounded-2xl border p-4"
      style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }}
      data-testid="studio-builder-terms"
    >
      <header className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60">Terms & holidays</p>
          <h3 className="text-base font-bold inline-flex items-center gap-2">
            <CalendarIcon size={14} className="text-emerald-500" />
            Term calendar
          </h3>
        </div>
        <button
          type="button"
          onClick={onToggleForm}
          className="px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5"
          style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff' }}
          data-testid="studio-builder-add-term-btn"
        >
          <Plus size={12} /> {showForm ? 'Close' : 'Add term'}
        </button>
      </header>

      {showForm ? (
        <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-4 gap-2 mb-4 p-3 rounded-xl border" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid="studio-builder-term-form">
          <label className="block">
            <span className="text-[11px] font-bold opacity-70">Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Autumn Term 2026" className="w-full px-2 py-1 text-sm rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid="studio-builder-term-name" />
          </label>
          <label className="block">
            <span className="text-[11px] font-bold opacity-70">Starts</span>
            <input type="date" value={starts} onChange={(e) => setStarts(e.target.value)} className="w-full px-2 py-1 text-sm rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid="studio-builder-term-starts" />
          </label>
          <label className="block">
            <span className="text-[11px] font-bold opacity-70">Ends</span>
            <input type="date" value={ends} onChange={(e) => setEnds(e.target.value)} className="w-full px-2 py-1 text-sm rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid="studio-builder-term-ends" />
          </label>
          <label className="flex items-end gap-2 text-xs">
            <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} data-testid="studio-builder-term-default" />
            <span>Make default</span>
            <button type="submit" className="ml-auto px-2 py-1 rounded text-xs font-bold" style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff' }} data-testid="studio-builder-term-save">
              <Save size={11} className="inline mr-1" /> Save
            </button>
          </label>
        </form>
      ) : null}

      {terms.length === 0 ? (
        <p className="text-sm opacity-60 italic">No terms yet — add one to drive the timetable rebuild.</p>
      ) : (
        <ul className="space-y-2" data-testid="studio-builder-term-list">
          {terms.map((term) => (
            <li
              key={term.id}
              className="rounded-xl border p-3"
              style={{ borderColor: term.id === activeTermId ? 'var(--color-brand-blue, #1d4ed8)' : 'var(--theme-border, #e2e8f0)' }}
              data-testid={`studio-builder-term-${term.id}`}
            >
              <div className="flex items-start gap-2 flex-wrap">
                <span style={{ background: term.colour, width: 10, height: 10, borderRadius: 3, marginTop: 4 }} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold truncate">
                    {term.name}
                    {term.is_default ? <span className="ml-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">default</span> : null}
                    {term.id === activeTermId ? <span className="ml-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">active</span> : null}
                  </p>
                  <p className="text-[11px] opacity-70 tabular-nums">{term.starts_on} → {term.ends_on}</p>
                  {term.holiday_blocks?.length ? (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {term.holiday_blocks.map((h) => (
                        <span
                          key={h.id}
                          className="text-[10px] px-1.5 py-0.5 rounded inline-flex items-center gap-1"
                          style={{ background: 'rgba(239,68,68,0.1)', color: '#b91c1c' }}
                          data-testid={`studio-builder-holiday-${h.id}`}
                        >
                          {h.name} · {h.starts_on}–{h.ends_on}
                          <button type="button" onClick={() => onRemoveHoliday(term, h)} aria-label="Remove holiday" style={{ background: 'none', border: 0, cursor: 'pointer', color: 'inherit', padding: 0 }}>
                            <X size={9} />
                          </button>
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
                <button type="button" onClick={() => onAddHoliday(term)} className="px-2 py-1 rounded text-[11px] font-bold border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`studio-builder-add-holiday-${term.id}`}>
                  + Holiday
                </button>
                <button type="button" onClick={() => onDelete(term)} className="px-2 py-1 rounded text-[11px] font-bold border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`studio-builder-delete-term-${term.id}`}>
                  <Trash2 size={11} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────
// Drag-drop builder
// ─────────────────────────────────────────────────────────────────
function BuilderGrid({
  templates, idleTemplates, scheduledTemplates, savingId, rematerialising,
  onDropToSlot, onDropToIdle, onRemoveFromDay, onRebuildTerm, onRefresh, industry,
}) {
  const [dragId, setDragId] = useState(null);
  const handleDragStart = (e, id) => {
    setDragId(id);
    e.dataTransfer.setData('text/plain', id);
    e.dataTransfer.effectAllowed = 'move';
  };
  const handleDragEnd = () => setDragId(null);
  const handleDragOver = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; };
  const handleDropSlot = (e, dayIdx, timeStr) => {
    e.preventDefault();
    const id = e.dataTransfer.getData('text/plain') || dragId;
    if (!id) return;
    const tpl = templates.find((t) => t.id === id);
    if (!tpl) return;
    onDropToSlot(tpl, dayIdx, timeStr);
  };
  const handleDropIdle = (e) => {
    e.preventDefault();
    const id = e.dataTransfer.getData('text/plain') || dragId;
    if (!id) return;
    const tpl = templates.find((t) => t.id === id);
    if (!tpl) return;
    onDropToIdle(tpl);
  };

  return (
    <section
      className="rounded-2xl border p-4"
      style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }}
      data-testid="studio-builder-grid"
    >
      <header className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60">Weekly timetable builder</p>
          <h3 className="text-base font-bold">Drag a class onto a slot to schedule it</h3>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={onRefresh} className="px-2 py-1 rounded text-[11px] font-bold border inline-flex items-center gap-1" style={{ borderColor: 'var(--theme-border)' }} data-testid="studio-builder-refresh">
            <RefreshCw size={11} /> Refresh
          </button>
          <button type="button" onClick={onRebuildTerm} disabled={rematerialising} className="px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5" style={{ background: '#10b981', color: '#fff', opacity: rematerialising ? 0.6 : 1 }} data-testid="studio-builder-rebuild">
            {rematerialising ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
            Rebuild term occurrences
          </button>
        </div>
      </header>

      {/* Idle templates rail */}
      <div
        onDragOver={handleDragOver}
        onDrop={handleDropIdle}
        className="rounded-xl border-2 border-dashed p-3 mb-4"
        style={{ borderColor: dragId ? 'var(--color-brand-blue, #1d4ed8)' : 'var(--theme-border, #e2e8f0)', background: dragId ? 'rgba(29,78,216,0.04)' : 'transparent' }}
        data-testid="studio-builder-idle-rail"
      >
        <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 mb-2 inline-flex items-center gap-1">
          <Tag size={11} /> Class library — drag onto the grid below
        </p>
        {idleTemplates.length === 0 ? (
          <p className="text-xs opacity-60 italic">All your templates are scheduled. Drop one here to remove it from the timetable.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {idleTemplates.map((t) => (
              <TemplateChip key={t.id} t={t} dragId={dragId} onDragStart={handleDragStart} onDragEnd={handleDragEnd} saving={savingId === t.id} />
            ))}
          </div>
        )}
      </div>

      {/* Grid */}
      <div className="overflow-x-auto" data-testid="studio-builder-week-grid">
        <table className="w-full text-xs border-collapse" style={{ minWidth: 760 }}>
          <thead>
            <tr>
              <th className="text-left p-1.5 sticky left-0" style={{ background: 'var(--theme-surface, #fff)', minWidth: 56 }}></th>
              {DAYS.map((d, i) => (
                <th key={d} className="text-left p-1.5 font-bold" data-testid={`studio-builder-day-head-${i}`}>
                  {d}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {SLOTS.map((time, slotIdx) => {
              const isHourBoundary = time.endsWith(':00');
              return (
                <tr key={time} style={{ borderTop: isHourBoundary ? '1px solid var(--theme-border, #e2e8f0)' : '1px dotted var(--theme-border, #e2e8f0)' }}>
                  <td className="p-1.5 align-top opacity-70 tabular-nums sticky left-0" style={{ background: 'var(--theme-surface, #fff)' }}>
                    {isHourBoundary ? time : ''}
                  </td>
                  {DAYS.map((_, dayIdx) => {
                    const cards = scheduledTemplates.filter((t) =>
                      t.recurs_days?.includes(dayIdx) && timeToSlotIndex(t.start_time) === slotIdx,
                    );
                    return (
                      <td
                        key={dayIdx}
                        onDragOver={handleDragOver}
                        onDrop={(e) => handleDropSlot(e, dayIdx, time)}
                        className="align-top p-0.5"
                        style={{
                          height: 36,
                          background: dragId ? 'rgba(29,78,216,0.03)' : 'transparent',
                          borderLeft: '1px solid var(--theme-border, #e2e8f0)',
                          minWidth: 90,
                        }}
                        data-testid={`studio-builder-slot-${dayIdx}-${time}`}
                      >
                        {cards.map((c) => (
                          <ScheduledCard
                            key={`${c.id}-${dayIdx}`}
                            t={c}
                            dayIdx={dayIdx}
                            saving={savingId === c.id}
                            onRemove={() => onRemoveFromDay(c, dayIdx)}
                            onDragStart={handleDragStart}
                            onDragEnd={handleDragEnd}
                            industry={industry}
                          />
                        ))}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {templates.length === 0 ? (
        <div className="mt-4 p-4 rounded-xl border-2 border-dashed text-center" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }}>
          <AlertTriangle size={20} className="mx-auto mb-2 text-amber-500" />
          <p className="text-sm font-bold">No class templates yet</p>
          <p className="text-xs opacity-70 mt-1">Create class templates from the <strong>Classes</strong> tab, then drag them into the grid.</p>
        </div>
      ) : null}
    </section>
  );
}

function TemplateChip({ t, dragId, onDragStart, onDragEnd, saving }) {
  const colour = t.colour || '#3b82f6';
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, t.id)}
      onDragEnd={onDragEnd}
      className={`px-2 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 cursor-grab select-none border ${dragId === t.id ? 'opacity-50' : ''}`}
      style={{
        background: `${colour}1a`,
        borderColor: colour,
        color: 'inherit',
      }}
      data-testid={`studio-builder-chip-${t.id}`}
    >
      <GripVertical size={11} style={{ color: colour }} />
      <span>{t.name}</span>
      {t.discipline ? <span className="opacity-70 font-normal text-[10px]">· {t.discipline}</span> : null}
      {(t.min_age || t.max_age) ? <span className="opacity-70 font-normal text-[10px]">· age {t.min_age ?? '?'}–{t.max_age ?? '?'}</span> : null}
      {t.skill_level ? <span className="opacity-70 font-normal text-[10px]">· {t.skill_level}</span> : null}
      {saving ? <Loader2 size={10} className="animate-spin" /> : null}
    </div>
  );
}

function ScheduledCard({ t, dayIdx, saving, onRemove, onDragStart, onDragEnd, industry }) {
  const colour = t.colour || '#3b82f6';
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, t.id)}
      onDragEnd={onDragEnd}
      className="rounded-md p-1.5 text-[11px] cursor-grab leading-tight"
      style={{
        background: `${colour}26`,
        borderLeft: `3px solid ${colour}`,
      }}
      data-testid={`studio-builder-scheduled-${t.id}-${dayIdx}`}
    >
      <div className="flex items-start gap-1">
        <span className="font-bold flex-1 truncate">{t.name}</span>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          aria-label="Remove from day"
          className="opacity-60 hover:opacity-100"
          style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', color: 'inherit' }}
          data-testid={`studio-builder-scheduled-remove-${t.id}-${dayIdx}`}
        >
          {saving ? <Loader2 size={10} className="animate-spin" /> : <X size={10} />}
        </button>
      </div>
      <div className="opacity-70 tabular-nums">{t.start_time} · {t.duration_min}m</div>
      {t.room_name ? <div className="opacity-60 truncate">{t.room_name}</div> : null}
      {t.skill_level || t.discipline ? (
        <div className="opacity-60 truncate">{[t.discipline, t.skill_level].filter(Boolean).join(' · ')}</div>
      ) : null}
    </div>
  );
}
