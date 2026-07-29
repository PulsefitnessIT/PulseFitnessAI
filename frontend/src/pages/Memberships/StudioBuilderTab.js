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
import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  Plus, Trash2, Calendar as CalendarIcon, GripVertical, Sparkles,
  AlertTriangle, Save, Loader2, X, RefreshCw, Tag,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import Button from '@/components/shared/Button';
import DatePicker from '@/components/shared/DatePicker';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
// 30-minute slots from 06:00 → 22:00 (covers most studios)
const SLOT_MINUTES = 30;
const SLOTS = Array.from({ length: ((22 - 6) * 60) / SLOT_MINUTES }, (_, i) => {
  const total = 6 * 60 + i * SLOT_MINUTES;
  const hh = String(Math.floor(total / 60)).padStart(2, '0');
  const mm = String(total % 60).padStart(2, '0');
  return `${hh}:${mm}`;
});

function timeToSlotIndex(timeStr) {
  const [hh, mm] = (timeStr || '07:00').split(':').map((x) => parseInt(x, 10));
  const total = (hh || 7) * 60 + (mm || 0);
  const fromBase = total - 6 * 60;
  return Math.max(0, Math.min(SLOTS.length - 1, Math.round(fromBase / SLOT_MINUTES)));
}

export default function StudioBuilderTab({ API, headers, onAddInstructor }) {
  const { t } = useTranslation();
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
  // Iter 216ah G2 — full "+ New class" editor so operators don't have to
  // go via the quickstart wizard (or worse, the API) to create a template.
  const [showNewClass, setShowNewClass] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, ind, tm, tpl] = await Promise.all([
        axios.get(`${API}/memberships/studio/settings`, auth),
        axios.get(`${API}/memberships/studio/industries`, auth),
        axios.get(`${API}/memberships/terms`, auth),
        axios.get(`${API}/memberships/classes/templates`, auth),
      ]);
      setSettings(s.data || {});
      setIndustries(ind.data?.industries || []);
      setTerms(tm.data?.terms || []);
      setActiveTermId(tm.data?.active_term_id || null);
      setTemplates(tpl.data?.templates || []);
    } catch (e) {
      notify.error(t('memberships_console.sb_load_err', 'Failed to load studio builder'), e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [API, auth, t]);
  useEffect(() => { load(); }, [load]);

  const setIndustry = async (industryId) => {
    try {
      await axios.post(`${API}/memberships/studio/settings`, {
        studio_mode: true, studio_industry: industryId,
      }, auth);
      notify.success(t('memberships_console.sb_industry_saved', 'Industry saved'), industries.find((i) => i.id === industryId)?.label);
      await load();
    } catch (e) {
      notify.error(t('memberships_console.sb_save_fail', 'Failed to save'), e?.response?.data?.detail || e.message);
    }
  };

  const onDropToSlot = async (template, dayIdx, timeStr) => {
    // Iter 216ah G8 — optimistic update first: mutate local state so the
    // chip appears on the target cell instantly. Dropping `await load()`
    // (which re-rendered the whole grid and scrolled the page to the top).
    const recurs = Array.from(new Set([...(template.recurs_days || []), dayIdx])).sort();
    const prevTemplates = templates;
    setTemplates((cur) => cur.map((tpl) =>
      tpl.id === template.id ? { ...tpl, recurs_days: recurs, start_time: timeStr } : tpl,
    ));
    setSavingId(template.id);
    try {
      await axios.patch(`${API}/memberships/classes/templates/${template.id}`, {
        recurs_days: recurs,
        start_time: timeStr,
      }, auth);
      notify.success(t('memberships_console.sb_class_scheduled', 'Class scheduled'), `${template.name} · ${t(`memberships_console.sb_day_${dayIdx}`, DAYS[dayIdx])} ${timeStr}`);
    } catch (e) {
      // Roll back on failure — never leave the UI in an inconsistent state.
      setTemplates(prevTemplates);
      notify.error(t('memberships_console.sb_update_failed', 'Update failed'), e?.response?.data?.detail || e.message);
    } finally { setSavingId(null); }
  };

  const onDropToIdle = async (template) => {
    if (!template.recurs_days?.length) return;
    const prevTemplates = templates;
    setTemplates((cur) => cur.map((tpl) =>
      tpl.id === template.id ? { ...tpl, recurs_days: [] } : tpl,
    ));
    setSavingId(template.id);
    try {
      await axios.patch(`${API}/memberships/classes/templates/${template.id}`, {
        recurs_days: [],
      }, auth);
      notify.success(t('memberships_console.sb_removed', 'Removed from timetable'), template.name);
    } catch (e) {
      setTemplates(prevTemplates);
      notify.error(t('memberships_console.sb_update_failed', 'Update failed'), e?.response?.data?.detail || e.message);
    } finally { setSavingId(null); }
  };

  const removeFromDay = async (template, dayIdx) => {
    const prevTemplates = templates;
    const next = (template.recurs_days || []).filter((d) => d !== dayIdx);
    setTemplates((cur) => cur.map((tpl) =>
      tpl.id === template.id ? { ...tpl, recurs_days: next } : tpl,
    ));
    setSavingId(template.id);
    try {
      await axios.patch(`${API}/memberships/classes/templates/${template.id}`, {
        recurs_days: next,
      }, auth);
    } catch (e) {
      setTemplates(prevTemplates);
      notify.error(t('memberships_console.sb_update_failed', 'Update failed'), e?.response?.data?.detail || e.message);
    } finally { setSavingId(null); }
  };

  const rebuildTerm = async () => {
    if (!window.confirm(t('memberships_console.sb_rebuild_confirm', 'Rebuild the timetable for the active term?\n\nEmpty future occurrences will be regenerated honouring holiday blocks. Booked classes are preserved.'))) return;
    setRematerialising(true);
    try {
      const r = await axios.post(`${API}/memberships/terms/rematerialise`, {}, auth);
      notify.success(t('memberships_console.sb_rebuilt', 'Timetable rebuilt'), t('memberships_console.sb_new_occ', '{{n}} new occurrences', { n: r.data?.occurrences_made ?? 0 }));
    } catch (e) {
      notify.error(t('memberships_console.sb_rebuild_failed', 'Rebuild failed'), e?.response?.data?.detail || e.message);
    } finally { setRematerialising(false); }
  };

  const idleTemplates = templates.filter((tpl) => !(tpl.recurs_days?.length));
  const scheduledTemplates = templates.filter((tpl) => tpl.recurs_days?.length);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground p-6" data-testid="studio-builder-loading">
        <Loader2 size={14} className="animate-spin" /> {t('memberships_console.sb_loading', 'Loading studio builder…')}
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
            notify.success(t('memberships_console.sb_term_created', 'Term created'), body.name);
            await load();
          } catch (e) {
            notify.error(t('memberships_console.sb_create_failed', 'Create failed'), e?.response?.data?.detail || e.message);
          }
        }}
        onDelete={async (term) => {
          if (!window.confirm(t('memberships_console.sb_archive_confirm', 'Archive term {{name}}?', { name: term.name }))) return;
          try {
            await axios.delete(`${API}/memberships/terms/${term.id}`, auth);
            await load();
          } catch (e) {
            notify.error(t('memberships_console.sb_delete_failed', 'Delete failed'), e?.response?.data?.detail || e.message);
          }
        }}
        onAddHoliday={async (term) => {
          const name = window.prompt(t('memberships_console.sb_holiday_name_prompt', 'Holiday name (e.g. Half-term, Easter):'));
          if (!name) return;
          const starts = window.prompt(t('memberships_console.sb_start_prompt', 'Start date YYYY-MM-DD:'), term.starts_on);
          if (!starts) return;
          const ends = window.prompt(t('memberships_console.sb_end_prompt', 'End date YYYY-MM-DD:'), starts);
          if (!ends) return;
          try {
            await axios.post(`${API}/memberships/terms/${term.id}/holidays`,
              { name, starts_on: starts, ends_on: ends }, auth);
            await load();
            notify.success(t('memberships_console.sb_holiday_added', 'Holiday added'));
          } catch (e) {
            notify.error(t('memberships_console.sb_failed', 'Failed'), e?.response?.data?.detail || e.message);
          }
        }}
        onRemoveHoliday={async (term, block) => {
          try {
            await axios.delete(`${API}/memberships/terms/${term.id}/holidays/${block.id}`, auth);
            await load();
          } catch (e) {
            notify.error(t('memberships_console.sb_failed', 'Failed'), e?.response?.data?.detail || e.message);
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
        onNewClass={() => setShowNewClass(true)}
        industry={industry}
      />

      {showNewClass && (
        <ClassTemplateEditor
          API={API} auth={auth}
          onClose={() => setShowNewClass(false)}
          onSaved={async (created) => {
            setShowNewClass(false);
            // Optimistic: prepend the new template; background reload for safety.
            if (created) setTemplates((cur) => [created, ...cur]);
            await load();
          }}
          // Iter 216h247 — route the "+ Add new instructor" picker to
          // the parent so the user lands on the Instructors tab.
          onAddInstructor={() => { setShowNewClass(false); onAddInstructor?.(); }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Identity
// ─────────────────────────────────────────────────────────────────
function IdentityCard({ industries, currentIndustry, currentLabel, onChoose }) {
  const { t } = useTranslation();
  return (
    <section
      className="rounded-2xl border p-4 bg-white"
      style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }}
      data-testid="studio-builder-identity"
    >
      <header className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60">{t('memberships_console.sb_identity_label', 'Studio identity')}</p>
          <h3 className="text-base font-bold inline-flex items-center gap-2">
            <Sparkles size={14} className="text-violet-500" />
            {currentIndustry ? t('memberships_console.sb_tailored', 'Tailored for {{label}}', { label: currentLabel || currentIndustry }) : t('memberships_console.sb_pick_type', 'Pick your studio type')}
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
                {(ind.disciplines || []).slice(0, 4).join(' · ') || t('memberships_console.sb_custom', 'Custom')}
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
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [starts, setStarts] = useState('');
  const [ends, setEnds] = useState('');
  const [isDefault, setIsDefault] = useState(true);
  const submit = (e) => {
    e.preventDefault();
    if (!name.trim() || !starts || !ends) {
      notify.error(t('memberships_console.sb_missing_fields', 'Missing fields'), t('memberships_console.sb_missing_fields_detail', 'Name, start and end are all required'));
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
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60">{t('memberships_console.sb_terms_label', 'Terms & holidays')}</p>
          <h3 className="text-base font-bold inline-flex items-center gap-2">
            <CalendarIcon size={14} className="text-emerald-500" />
            {t('memberships_console.sb_term_calendar', 'Term calendar')}
          </h3>
        </div>
        <button
          type="button"
          onClick={onToggleForm}
          className="px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5"
          style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff' }}
          data-testid="studio-builder-add-term-btn"
        >
          <Plus size={12} /> {showForm ? t('memberships_console.sb_close', 'Close') : t('memberships_console.sb_add_term', 'Add term')}
        </button>
      </header>

      {showForm ? (
        <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-4 gap-2 mb-4 p-3 rounded-xl border" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid="studio-builder-term-form">
          <label className="block">
            <span className="text-[11px] font-bold opacity-70">{t('memberships_console.sb_name', 'Name')}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('memberships_console.sb_term_name_ph', 'Autumn Term 2026')} className="w-full px-2 py-1 text-sm rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid="studio-builder-term-name" />
          </label>
          <label className="block">
            <span className="text-[11px] font-bold opacity-70">{t('memberships_console.sb_starts', 'Starts')}</span>
            {/* Iter 216h255 — shared DatePicker for consistency. */}
            <DatePicker value={starts} onChange={(iso) => setStarts(iso)} testid="studio-builder-term-starts" />
          </label>
          <label className="block">
            <span className="text-[11px] font-bold opacity-70">{t('memberships_console.sb_ends', 'Ends')}</span>
            <DatePicker value={ends} onChange={(iso) => setEnds(iso)} minDate={starts || undefined} testid="studio-builder-term-ends" />
          </label>
          <label className="flex items-end gap-2 text-xs">
            <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} data-testid="studio-builder-term-default" />
            <span>{t('memberships_console.sb_make_default', 'Make default')}</span>
            <button type="submit" className="ml-auto px-2 py-1 rounded text-xs font-bold" style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff' }} data-testid="studio-builder-term-save">
              <Save size={11} className="inline mr-1" /> {t('memberships_console.sb_save', 'Save')}
            </button>
          </label>
        </form>
      ) : null}

      {terms.length === 0 ? (
        <p className="text-sm opacity-60 italic">{t('memberships_console.sb_no_terms', 'No terms yet — add one to drive the timetable rebuild.')}</p>
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
                    {term.is_default ? <span className="ml-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">{t('memberships_console.sb_default_badge', 'default')}</span> : null}
                    {term.id === activeTermId ? <span className="ml-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">{t('memberships_console.sb_active_badge', 'active')}</span> : null}
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
                          <button type="button" onClick={() => onRemoveHoliday(term, h)} aria-label={t('memberships_console.sb_remove_holiday', 'Remove holiday')} style={{ background: 'none', border: 0, cursor: 'pointer', color: 'inherit', padding: 0 }}>
                            <X size={9} />
                          </button>
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
                <button type="button" onClick={() => onAddHoliday(term)} className="px-2 py-1 rounded text-[11px] font-bold border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`studio-builder-add-holiday-${term.id}`}>
                  {t('memberships_console.sb_add_holiday_btn', '+ Holiday')}
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
  onDropToSlot, onDropToIdle, onRemoveFromDay, onRebuildTerm, onRefresh,
  onNewClass, industry,
}) {
  const { t } = useTranslation();
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
    const tpl = templates.find((x) => x.id === id);
    if (!tpl) return;
    onDropToSlot(tpl, dayIdx, timeStr);
  };
  const handleDropIdle = (e) => {
    e.preventDefault();
    const id = e.dataTransfer.getData('text/plain') || dragId;
    if (!id) return;
    const tpl = templates.find((x) => x.id === id);
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
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60">{t('memberships_console.sb_weekly_builder', 'Weekly timetable builder')}</p>
          <h3 className="text-base font-bold">{t('memberships_console.sb_drag_hint', 'Drag a class onto a slot to schedule it')}</h3>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={onNewClass} className="px-3 py-1.5 rounded-lg text-xs font-extrabold inline-flex items-center gap-1.5" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="studio-builder-new-class">
            <Plus size={11} /> {t('memberships_console.sb_new_class', 'New class')}
          </button>
          <button type="button" onClick={onRefresh} className="px-2 py-1 rounded text-[11px] font-bold border inline-flex items-center gap-1" style={{ borderColor: 'var(--theme-border)' }} data-testid="studio-builder-refresh">
            <RefreshCw size={11} /> {t('memberships_console.sb_refresh', 'Refresh')}
          </button>
          <button type="button" onClick={onRebuildTerm} disabled={rematerialising} className="px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5" style={{ background: '#10b981', color: '#fff', opacity: rematerialising ? 0.6 : 1 }} data-testid="studio-builder-rebuild">
            {rematerialising ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
            {t('memberships_console.sb_rebuild_btn', 'Rebuild term occurrences')}
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
          <Tag size={11} /> {t('memberships_console.sb_class_library', 'Class library — drag onto the grid below')}
        </p>
        {idleTemplates.length === 0 ? (
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-xs opacity-60 italic m-0">{t('memberships_console.sb_all_scheduled', 'All your templates are scheduled. Drop one here to remove it from the timetable — or create another.')}</p>
            <button type="button" onClick={onNewClass}
              className="px-3 py-1.5 rounded-lg text-xs font-extrabold inline-flex items-center gap-1.5"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
              data-testid="studio-builder-new-class-inline">
              <Plus size={11} /> {t('memberships_console.sb_new_class', 'New class')}
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {idleTemplates.map((tpl) => (
              <TemplateChip key={tpl.id} tpl={tpl} dragId={dragId} onDragStart={handleDragStart} onDragEnd={handleDragEnd} saving={savingId === tpl.id} />
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
                  {t(`memberships_console.sb_day_${i}`, d)}
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
                    const cards = scheduledTemplates.filter((tpl) =>
                      tpl.recurs_days?.includes(dayIdx) && timeToSlotIndex(tpl.start_time) === slotIdx,
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
                            tpl={c}
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
          <p className="text-sm font-bold">{t('memberships_console.sb_no_templates', 'No class templates yet')}</p>
          <p className="text-xs opacity-70 mt-1">{t('memberships_console.sb_no_templates_hint_a', 'Create class templates from the')} <strong>{t('memberships_console.sb_classes', 'Classes')}</strong> {t('memberships_console.sb_no_templates_hint_b', 'tab, then drag them into the grid.')}</p>
        </div>
      ) : null}
    </section>
  );
}

function TemplateChip({ tpl, dragId, onDragStart, onDragEnd, saving }) {
  const { t } = useTranslation();
  const colour = tpl.colour || '#3b82f6';
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, tpl.id)}
      onDragEnd={onDragEnd}
      className={`px-2 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 cursor-grab select-none border ${dragId === tpl.id ? 'opacity-50' : ''}`}
      style={{
        background: `${colour}1a`,
        borderColor: colour,
        color: 'inherit',
      }}
      data-testid={`studio-builder-chip-${tpl.id}`}
    >
      <GripVertical size={11} style={{ color: colour }} />
      <span>{tpl.name}</span>
      {tpl.discipline ? <span className="opacity-70 font-normal text-[10px]">· {tpl.discipline}</span> : null}
      {(tpl.min_age || tpl.max_age) ? <span className="opacity-70 font-normal text-[10px]">· {t('memberships_console.sb_age', 'age')} {tpl.min_age ?? '?'}–{tpl.max_age ?? '?'}</span> : null}
      {tpl.skill_level ? <span className="opacity-70 font-normal text-[10px]">· {tpl.skill_level}</span> : null}
      {saving ? <Loader2 size={10} className="animate-spin" /> : null}
    </div>
  );
}

function ScheduledCard({ tpl, dayIdx, saving, onRemove, onDragStart, onDragEnd, _industry }) {
  const { t } = useTranslation();
  const colour = tpl.colour || '#3b82f6';
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, tpl.id)}
      onDragEnd={onDragEnd}
      className="rounded-md p-1.5 text-[11px] cursor-grab leading-tight"
      style={{
        background: `${colour}26`,
        borderLeft: `3px solid ${colour}`,
      }}
      data-testid={`studio-builder-scheduled-${tpl.id}-${dayIdx}`}
    >
      <div className="flex items-start gap-1">
        <span className="font-bold flex-1 truncate">{tpl.name}</span>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          aria-label={t('memberships_console.sb_remove_from_day', 'Remove from day')}
          className="opacity-60 hover:opacity-100"
          style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', color: 'inherit' }}
          data-testid={`studio-builder-scheduled-remove-${tpl.id}-${dayIdx}`}
        >
          {saving ? <Loader2 size={10} className="animate-spin" /> : <X size={10} />}
        </button>
      </div>
      <div className="opacity-70 tabular-nums">{tpl.start_time} · {tpl.duration_min}m</div>
      {tpl.room_name ? <div className="opacity-60 truncate">{tpl.room_name}</div> : null}
      {tpl.skill_level || tpl.discipline ? (
        <div className="opacity-60 truncate">{[tpl.discipline, tpl.skill_level].filter(Boolean).join(' · ')}</div>
      ) : null}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Class Template Editor (iter 216ah — Sprint A · G2)
// ─────────────────────────────────────────────────────────────────
/**
 * Full-featured "new class" modal. Creates a class template via
 * POST /memberships/classes/templates and also serves as the edit
 * drawer (see ClassActionDrawer for the timetable-side entry point).
 *
 * Iter 216h247:
 *   • Portaled to ``document.body`` so the fixed-inset backdrop covers
 *     the full viewport (was clipped by a transformed ancestor in
 *     Pulse Pro — same fix as the Add Staff modal h242).
 *   • Free-text instructor input replaced with a dropdown loaded from
 *     ``GET /memberships/instructors``. A final option "+ Add new
 *     instructor" closes the modal and notifies the parent via
 *     ``onAddInstructor`` so the user is routed to the Instructors
 *     tab. The original free-text fallback is still available (for
 *     impromptu cover instructors) but lives in an expandable
 *     "use a custom name" toggle below the dropdown.
 */
export function ClassTemplateEditor({ API, auth, initial, onSaved, onClose, onAddInstructor }) {
  const { t } = useTranslation();
  const isEdit = !!initial?.id;
  const [form, setForm] = useState(() => ({
    name: initial?.name || '',
    category: initial?.category || 'Group',
    description: initial?.description || '',
    duration_min: initial?.duration_min ?? 45,
    capacity: initial?.capacity ?? 20,
    colour: initial?.colour || '#19CDFF',
    start_time: initial?.start_time || '09:00',
    recurs_days: initial?.recurs_days || [],
    room_name: initial?.room_name || '',
    instructor_id: initial?.instructor_id || '',
    instructor_name: initial?.instructor_name || '',
    credits_to_book: initial?.credits_to_book ?? 1,
    waitlist_enabled: initial?.waitlist_enabled !== false,
    max_waitlist: initial?.max_waitlist ?? 10,
    skill_level: initial?.skill_level || '',
    discipline: initial?.discipline || '',
    min_age: initial?.min_age ?? '',
    max_age: initial?.max_age ?? '',
  }));
  const [saving, setSaving] = useState(false);
  const [instructors, setInstructors] = useState([]);
  const [showCustomInstructor, setShowCustomInstructor] = useState(!!initial?.instructor_name && !initial?.instructor_id);

  // Load instructor directory once on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/memberships/instructors`, auth);
        if (!cancelled) setInstructors(data?.instructors || []);
      } catch { /* non-fatal */ }
    })();
    return () => { cancelled = true; };
  }, [API, auth]);

  const up = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));

  const toggleDay = (i) => setForm((f) => ({
    ...f,
    recurs_days: f.recurs_days.includes(i)
      ? f.recurs_days.filter((d) => d !== i)
      : [...f.recurs_days, i].sort(),
  }));

  const save = async () => {
    if (!form.name.trim()) { notify.error(t('memberships_console.sb_cte_name_req', 'Class name is required')); return; }
    if (!Number.isFinite(Number(form.duration_min)) || Number(form.duration_min) < 5) {
      notify.error(t('memberships_console.sb_cte_dur_min', 'Duration must be at least 5 minutes')); return;
    }
    if (!Number.isFinite(Number(form.capacity)) || Number(form.capacity) < 1) {
      notify.error(t('memberships_console.sb_cte_cap_min', 'Capacity must be at least 1')); return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        duration_min: Number(form.duration_min),
        capacity: Number(form.capacity),
        credits_to_book: Number(form.credits_to_book) || 1,
        max_waitlist: Number(form.max_waitlist) || 0,
        min_age: form.min_age === '' ? null : Number(form.min_age),
        max_age: form.max_age === '' ? null : Number(form.max_age),
        // Iter 216h247 — send both id and label so the timetable
        // renderer keeps showing the same name even if the
        // instructor's profile is renamed later.
        instructor_id: form.instructor_id || null,
        instructor_name: form.instructor_name || null,
      };
      if (isEdit) {
        await axios.patch(`${API}/memberships/classes/templates/${initial.id}`, payload, auth);
        notify.success(t('memberships_console.sb_cte_updated', 'Class updated'));
        onSaved?.({ ...initial, ...payload });
      } else {
        const r = await axios.post(`${API}/memberships/classes/templates`, payload, auth);
        notify.success(t('memberships_console.sb_cte_created', 'Class created'), form.name);
        onSaved?.(r.data?.template);
      }
    } catch (e) {
      notify.error(isEdit ? t('memberships_console.sb_update_failed', 'Update failed') : t('memberships_console.sb_create_failed', 'Create failed'), e?.response?.data?.detail || e.message);
    }
    setSaving(false);
  };

  return createPortal((
    // Iter 216h247 — portal to document.body so the fixed inset-0
    // backdrop covers the full viewport (a transformed ancestor was
    // clipping it in Pulse Pro, leaving a white area to the right and
    // making the modal appear "half way down the page").
    <div className="fixed inset-0 z-[100] bg-black/70 grid items-center justify-items-center p-3" onClick={onClose} data-testid="class-template-editor">
      <div className="w-full max-w-2xl rounded-2xl shadow-2xl flex flex-col max-h-[92vh]"
        style={{ background: 'var(--theme-surface, #fff)', border: '1px solid var(--theme-border, #e2e8f0)' }}
        onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 flex items-start justify-between border-b" style={{ borderColor: 'var(--theme-border)' }}>
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] font-extrabold text-[var(--color-brand-cyan)]">{t('memberships_console.sb_cte_kicker', 'Class template')}</p>
            <h3 className="text-lg font-extrabold">{isEdit ? t('memberships_console.sb_cte_edit', 'Edit class') : t('memberships_console.sb_new_class', 'New class')}</h3>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} icon={X} title={t('memberships_console.sb_close', 'Close')} data-testid="mbr-studio-builder-close" />
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4 text-sm">
          <Field label={t('memberships_console.sb_cte_f_name', 'Class name')}><input type="text" value={form.name} onChange={(e) => up('name')(e.target.value)} className={InputCls} placeholder={t('memberships_console.sb_cte_name_ph', 'e.g. Open Flow Yoga')} data-testid="cte-name" /></Field>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Field label={t('memberships_console.sb_cte_f_duration', 'Duration (min)')}><input type="number" min="5" max="240" value={form.duration_min} onChange={(e) => up('duration_min')(e.target.value)} className={InputCls} data-testid="cte-duration" /></Field>
            <Field label={t('memberships_console.sb_cte_f_capacity', 'Capacity')}><input type="number" min="1" value={form.capacity} onChange={(e) => up('capacity')(e.target.value)} className={InputCls} data-testid="cte-capacity" /></Field>
            <Field label={t('memberships_console.sb_cte_f_start', 'Start time')}><input type="time" value={form.start_time} onChange={(e) => up('start_time')(e.target.value)} className={InputCls} data-testid="cte-start" /></Field>
            <Field label={t('memberships_console.sb_cte_f_credits', 'Credits to book')}><input type="number" min="0" value={form.credits_to_book} onChange={(e) => up('credits_to_book')(e.target.value)} className={InputCls} data-testid="cte-credits" /></Field>
          </div>

          <Field label={t('memberships_console.sb_cte_f_days', 'Recurring days')}>
            <div className="flex gap-1 flex-wrap">
              {DAYS.map((d, i) => (
                <button key={d} type="button" onClick={() => toggleDay(i)}
                  className="px-2.5 py-1 text-[11px] font-bold rounded-md border"
                  style={{
                    background: form.recurs_days.includes(i) ? 'var(--color-brand-cyan)' : 'transparent',
                    color: form.recurs_days.includes(i) ? 'var(--color-surface-darker)' : 'inherit',
                    borderColor: 'var(--theme-border)',
                  }}
                  data-testid={`cte-day-${i}`}>
                  {t(`memberships_console.sb_day_${i}`, d)}
                </button>
              ))}
            </div>
          </Field>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Field label={t('memberships_console.sb_cte_f_room', 'Room')}><input type="text" value={form.room_name} onChange={(e) => up('room_name')(e.target.value)} className={InputCls} placeholder={t('memberships_console.sb_cte_room_ph', 'Studio 1')} data-testid="cte-room" /></Field>
            {/* Iter 216h247 — instructor dropdown with "+ Add new instructor"
                option. Falls back to a free-text label for cover instructors
                via the "use a custom name" toggle. */}
            <Field label={t('memberships_console.sb_cte_f_instructor', 'Instructor')}>
              <select
                value={form.instructor_id || (showCustomInstructor ? '__custom__' : '')}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === '__add_new__') {
                    onAddInstructor?.();
                    return;
                  }
                  if (v === '__custom__') {
                    setShowCustomInstructor(true);
                    setForm((f) => ({ ...f, instructor_id: '' }));
                    return;
                  }
                  const picked = instructors.find((i) => i.id === v);
                  setShowCustomInstructor(false);
                  setForm((f) => ({
                    ...f,
                    instructor_id: v || '',
                    instructor_name: picked ? picked.name : '',
                  }));
                }}
                className={InputCls}
                data-testid="cte-instructor-select"
              >
                <option value="">{t('memberships_console.sb_cte_choose_inst', '— Choose instructor —')}</option>
                {instructors.map((i) => (
                  <option key={i.id} value={i.id}>{i.name}{i.headline ? ` · ${i.headline}` : ''}</option>
                ))}
                <option value="__custom__">{t('memberships_console.sb_cte_custom_opt', 'Use a custom name (cover)')}</option>
                <option value="__add_new__">{t('memberships_console.sb_cte_add_inst_opt', '+ Add new instructor…')}</option>
              </select>
              {showCustomInstructor && (
                <input
                  type="text"
                  value={form.instructor_name}
                  onChange={(e) => up('instructor_name')(e.target.value)}
                  className={`${InputCls} mt-1`}
                  placeholder={t('memberships_console.sb_cte_inst_ph', 'e.g. Sarah (cover)')}
                  data-testid="cte-instructor-custom"
                />
              )}
            </Field>
            <Field label={t('memberships_console.sb_cte_f_colour', 'Colour')}><input type="color" value={form.colour} onChange={(e) => up('colour')(e.target.value)} className="h-9 w-16 rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid="cte-colour" /></Field>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <Field label={t('memberships_console.sb_cte_f_discipline', 'Discipline')}><input type="text" value={form.discipline} onChange={(e) => up('discipline')(e.target.value)} className={InputCls} placeholder={t('memberships_console.sb_cte_disc_ph', 'Ballet, Tap, …')} data-testid="cte-discipline" /></Field>
            <Field label={t('memberships_console.sb_cte_f_skill', 'Skill level')}><input type="text" value={form.skill_level} onChange={(e) => up('skill_level')(e.target.value)} className={InputCls} placeholder={t('memberships_console.sb_cte_skill_ph', 'beginner')} data-testid="cte-skill" /></Field>
            <Field label={t('memberships_console.sb_cte_f_minage', 'Min age')}><input type="number" min="0" max="100" value={form.min_age} onChange={(e) => up('min_age')(e.target.value)} className={InputCls} data-testid="cte-min-age" /></Field>
            <Field label={t('memberships_console.sb_cte_f_maxage', 'Max age')}><input type="number" min="0" max="100" value={form.max_age} onChange={(e) => up('max_age')(e.target.value)} className={InputCls} data-testid="cte-max-age" /></Field>
          </div>

          <Field label={t('memberships_console.sb_cte_f_desc', 'Description (optional)')}>
            <textarea rows={3} value={form.description} onChange={(e) => up('description')(e.target.value)}
              className={InputCls} placeholder={t('memberships_console.sb_cte_desc_ph', 'What should members expect?')} data-testid="cte-description" />
          </Field>

          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={form.waitlist_enabled} onChange={(e) => up('waitlist_enabled')(e.target.checked)} data-testid="cte-waitlist" />
            {t('memberships_console.sb_cte_waitlist', 'Allow a waitlist when the class is full')}
          </label>
          {form.waitlist_enabled && (
            <Field label={t('memberships_console.sb_cte_f_maxwait', 'Max waitlist')}><input type="number" min="0" value={form.max_waitlist} onChange={(e) => up('max_waitlist')(e.target.value)} className={InputCls} data-testid="cte-max-waitlist" /></Field>
          )}
        </div>

        <div className="px-5 py-3 flex justify-end gap-2 border-t" style={{ borderColor: 'var(--theme-border)' }}>
          <button onClick={onClose} className="px-3 py-2 text-xs font-bold rounded-lg border" style={{ borderColor: 'var(--theme-border)' }}>{t('memberships_console.sb_cancel', 'Cancel')}</button>
          <button onClick={save} disabled={saving}
            className="px-4 py-2 text-xs font-extrabold rounded-lg inline-flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)', opacity: saving ? 0.7 : 1 }}
            data-testid="cte-save">
            {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
            {isEdit ? t('memberships_console.sb_cte_save_changes', 'Save changes') : t('memberships_console.sb_cte_create_class', 'Create class')}
          </button>
        </div>
      </div>
    </div>
  ), document.body);
}

const InputCls = 'w-full px-3 py-2 rounded-md text-sm border bg-transparent focus:outline-none focus:border-[var(--color-brand-cyan)] border-[color:var(--theme-border)]';
function Field({ label, children }) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wider font-bold opacity-60 mb-1 block">{label}</span>
      {children}
    </label>
  );
}
