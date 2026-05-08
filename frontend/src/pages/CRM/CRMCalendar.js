import React, { useState, useEffect, useCallback } from 'react';
import { useCRM } from './CRMApp';
import {
  ChevronLeft, ChevronRight, Phone, Mail, Calendar as CalendarIcon,
  FileText, CheckCircle, Activity, MapPin, Wrench, Plus, X, Users, Filter
} from 'lucide-react';
import axios from 'axios';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const EVENT_TYPES = [
  { key: 'call', label: 'Calls', icon: Phone, color: 'var(--color-warning)' },
  { key: 'email', label: 'Emails', icon: Mail, color: 'var(--color-info-ios)' },
  { key: 'meeting', label: 'Meetings', icon: CalendarIcon, color: 'var(--color-accent-violet)' },
  { key: 'task', label: 'Tasks', icon: CheckCircle, color: 'var(--color-success-alt)' },
  { key: 'note', label: 'Notes', icon: FileText, color: 'var(--color-text-faint-alt)' },
  { key: 'visit', label: 'Visits', icon: MapPin, color: 'var(--color-accent-amber)' },
  { key: 'engineer', label: 'Engineer', icon: Wrench, color: 'var(--color-danger)' },
  { key: 'system', label: 'System', icon: Activity, color: 'var(--color-text-muted)' },
];
const TYPE_COLORS = Object.fromEntries(EVENT_TYPES.map(t => [t.key, t.color]));
const TYPE_ICONS = Object.fromEntries(EVENT_TYPES.map(t => [t.key, t.icon]));

export default function CRMCalendar() {
  const { user, API, headers, c, isDark } = useCRM();
  const [currentDate, setCurrentDate] = useState(new Date());
  const [activities, setActivities] = useState([]);
  const [engineerAppts, setEngineerAppts] = useState([]);
  const [selectedDay, setSelectedDay] = useState(null);
  const [teamMembers, setTeamMembers] = useState([]);
  const [staffFilter, setStaffFilter] = useState('mine');
  const [typeFilters, setTypeFilters] = useState(new Set(EVENT_TYPES.map(t => t.key)));
  const [showAddEvent, setShowAddEvent] = useState(false);
  const [eventForm, setEventForm] = useState({ type: 'meeting', subject: '', body: '', due_date: '' });
  const [saving, setSaving] = useState(false);

  const isManagerOrOwner = ['admin', 'owner', 'manager', 'director'].includes(user?.role);
  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const load = useCallback(async () => {
    try {
      const [actRes, engRes] = await Promise.all([
        axios.get(`${API}/crm/v2/activities?limit=500`, { headers: headers() }),
        axios.get(`${API}/issues?limit=200`, { headers: headers() }).catch(() => ({ data: { issues: [] } })),
      ]);
      setActivities(actRes.data.activities || []);
      const appts = (engRes.data.issues || [])
        .filter(i => i.scheduled_date || i.created_at)
        .map(i => ({
          id: i.id, type: 'engineer', subject: `Engineer: ${i.title || i.issue_type || 'Service Visit'}`,
          body: `${i.equipment_name || ''} — ${i.status || ''}`.trim(),
          created_at: i.scheduled_date || i.created_at,
          due_date: i.scheduled_date || '',
          company_name: i.organization_name || '',
          owner_id: i.assigned_to || '',
          owner_name: i.assigned_to_name || '',
        }));
      setEngineerAppts(appts);
    } catch (e) { console.error(e); }
  }, [API, headers]);

  const loadTeam = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/users`, { headers: headers() });
      setTeamMembers(res.data.users || []);
    } catch (e) { console.error(e); }
  }, [API, headers]);

  useEffect(() => { load(); loadTeam(); }, [load, loadTeam]);

  const allEvents = [...activities, ...engineerAppts];

  const filteredEvents = allEvents.filter(ev => {
    if (!typeFilters.has(ev.type)) return false;
    if (staffFilter === 'mine') return ev.owner_id === user?.id || (!ev.owner_id && ev.owner_name === user?.full_name);
    if (staffFilter !== 'all') return ev.owner_id === staffFilter || ev.owner_name === teamMembers.find(m => m.id === staffFilter)?.full_name;
    return true;
  });

  const getEventsForDate = (dateStr) => {
    return filteredEvents.filter(e => {
      const d = e.due_date || e.follow_up_date || e.created_at || '';
      return d.startsWith(dateStr);
    });
  };

  const firstDay = new Date(year, month, 1);
  let startDay = firstDay.getDay() - 1;
  if (startDay < 0) startDay = 6;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = new Date().toISOString().split('T')[0];
  const selectedDateStr = selectedDay;

  const prevMonth = () => setCurrentDate(new Date(year, month - 1, 1));
  const nextMonth = () => setCurrentDate(new Date(year, month + 1, 1));
  const goToday = () => { setCurrentDate(new Date()); setSelectedDay(today); };

  const calDays = [];
  for (let i = 0; i < startDay; i++) calDays.push(null);
  for (let d = 1; d <= daysInMonth; d++) calDays.push(d);

  const selectedEvents = selectedDateStr ? getEventsForDate(selectedDateStr) : [];

  const toggleType = (key) => {
    const next = new Set(typeFilters);
    if (next.has(key)) next.delete(key); else next.add(key);
    setTypeFilters(next);
  };

  const openAddEvent = (dateStr) => {
    setEventForm({ type: 'meeting', subject: '', body: '', due_date: dateStr || selectedDateStr || today });
    setShowAddEvent(true);
  };

  const handleAddEvent = async () => {
    if (!eventForm.subject.trim()) return;
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/activities`, eventForm, { headers: headers() });
      setShowAddEvent(false);
      setEventForm({ type: 'meeting', subject: '', body: '', due_date: '' });
      load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const staffLabel = staffFilter === 'mine' ? 'My Calendar' : staffFilter === 'all' ? 'All Staff' : (teamMembers.find(m => m.id === staffFilter)?.full_name || 'Staff');

  return (
    <div data-testid="crm-calendar">
      {/* Toolbar — staff filter + type filters + actions */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <div className="flex items-center gap-1.5">
          <Users size={13} style={{ color: c.textDim }} />
          <select value={staffFilter} onChange={e => setStaffFilter(e.target.value)}
            className="px-2 py-1 text-xs rounded-md" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="calendar-staff-filter">
            <option value="mine">My Calendar</option>
            {isManagerOrOwner && <option value="all">All Staff</option>}
            {isManagerOrOwner && teamMembers.map(m => (
              <option key={m.id} value={m.id}>{m.full_name}</option>
            ))}
          </select>
        </div>
        <div className="w-px h-5" style={{ background: c.border }} />
        {/* Type Filters */}
        <div className="flex items-center gap-1 flex-wrap">
          <Filter size={13} style={{ color: c.textDim }} />
          {EVENT_TYPES.filter(t => t.key !== 'system').map(t => {
            const active = typeFilters.has(t.key);
            return (
              <button key={t.key} onClick={() => toggleType(t.key)}
                className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded-md transition-all"
                style={{
                  background: active ? `${t.color}15` : (isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)'),
                  color: active ? t.color : c.textDim,
                  border: `1px solid ${active ? `${t.color}40` : 'transparent'}`,
                }}
                data-testid={`filter-${t.key}`}>
                <t.icon size={10} /> {t.label}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <button type="button" onClick={goToday} className="btn-secondary btn-sm" data-testid="calendar-today-btn">Today</button>
          <button type="button" onClick={() => openAddEvent(selectedDateStr || today)} className="btn-primary btn-sm" data-testid="calendar-add-event-btn">
            <Plus size={12} /> Add Event
          </button>
        </div>
      </div>

      <div className="flex gap-5">
        {/* Calendar Grid */}
        <div className="flex-1">
          <div className="flex items-center justify-between mb-4">
            <button onClick={prevMonth} className="p-1.5 rounded-md hover:bg-white/5" style={{ color: c.textDim }} data-testid="calendar-prev"><ChevronLeft size={18} /></button>
            <h2 className="text-base font-semibold" style={{ color: c.text }}>
              {currentDate.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })}
            </h2>
            <button onClick={nextMonth} className="p-1.5 rounded-md hover:bg-white/5" style={{ color: c.textDim }} data-testid="calendar-next"><ChevronRight size={18} /></button>
          </div>

          <div className="grid grid-cols-7 gap-px rounded-lg overflow-hidden border" style={{ background: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            {DAYS.map(d => (
              <div key={d} className="py-2 text-center text-[10px] uppercase tracking-wider font-medium" style={{ background: isDark ? 'var(--color-neutral-900)' : 'var(--color-neutral-25-alt)', color: c.textDim }}>{d}</div>
            ))}
            {calDays.map((day, i) => {
              if (day === null) return <div key={`empty-${i}`} style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', minHeight: 80 }} />;
              const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
              const dayEvents = getEventsForDate(dateStr);
              const isToday = dateStr === today;
              const isSelected = dateStr === selectedDateStr;
              return (
                <div key={dateStr} onClick={() => setSelectedDay(dateStr)}
                  className="p-1.5 cursor-pointer transition-colors relative group"
                  style={{
                    background: isSelected ? (isDark ? 'var(--color-navy-950)' : 'var(--color-info-bg)') : (isDark ? 'var(--color-ink-alt)' : '#fff'),
                    minHeight: 80,
                    borderLeft: isSelected ? '2px solid var(--color-info-ios)' : '2px solid transparent',
                  }}
                  data-testid={`calendar-day-${dateStr}`}>
                  <div className="flex items-center justify-between">
                    <span className={`text-xs font-medium ${isToday ? 'w-6 h-6 rounded-full bg-[var(--color-info-ios)] text-white flex items-center justify-center' : ''}`}
                      style={!isToday ? { color: c.text } : {}}>
                      {day}
                    </span>
                    <button onClick={e => { e.stopPropagation(); openAddEvent(dateStr); }}
                      className="w-5 h-5 rounded flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                      style={{ background: 'var(--color-info-ios)20', color: 'var(--color-info-ios)' }}
                      data-testid={`add-event-day-${dateStr}`}>
                      <Plus size={10} />
                    </button>
                  </div>
                  <div className="mt-1 space-y-0.5">
                    {dayEvents.slice(0, 3).map((ev, j) => {
                      const color = TYPE_COLORS[ev.type] || 'var(--color-text-faint-alt)';
                      return (
                        <div key={ev.id || j} className="flex items-center gap-1 px-1 py-0.5 rounded text-[9px] truncate" style={{ background: `${color}15`, color }}>
                          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
                          <span className="truncate">{ev.subject}</span>
                        </div>
                      );
                    })}
                    {dayEvents.length > 3 && (
                      <span className="text-[9px] px-1" style={{ color: c.textDim }}>+{dayEvents.length - 3} more</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Day Detail Panel */}
        <div className="w-80 shrink-0">
          <div className="rounded-lg border p-4 sticky top-4" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold" style={{ color: c.text }}>
                {selectedDateStr
                  ? new Date(selectedDateStr + 'T12:00:00').toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
                  : 'Select a day'}
              </h3>
              {selectedDateStr && (
                <button onClick={() => openAddEvent(selectedDateStr)} className="w-6 h-6 rounded flex items-center justify-center" style={{ background: 'var(--color-info-ios)15', color: 'var(--color-info-ios)' }} data-testid="add-event-panel-btn">
                  <Plus size={12} />
                </button>
              )}
            </div>
            {selectedEvents.length > 0 ? (
              <div className="space-y-2 max-h-[60vh] overflow-y-auto">
                {selectedEvents.map((ev, i) => {
                  const Icon = TYPE_ICONS[ev.type] || Activity;
                  const color = TYPE_COLORS[ev.type] || 'var(--color-text-faint-alt)';
                  return (
                    <div key={ev.id || i} className="p-2.5 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`calendar-event-${ev.id || i}`}>
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-6 h-6 rounded flex items-center justify-center shrink-0" style={{ background: `${color}15` }}>
                          <Icon size={12} style={{ color }} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium truncate" style={{ color: c.text }}>{ev.subject}</p>
                          <span className="text-[9px] font-bold uppercase px-1 py-0.5 rounded" style={{ background: `${color}20`, color }}>{ev.type}</span>
                        </div>
                      </div>
                      {ev.body && <p className="text-[11px] mt-1" style={{ color: c.textDim }}>{ev.body}</p>}
                      {ev.company_name && <p className="text-[10px] mt-0.5" style={{ color: 'var(--color-info-ios)' }}>{ev.company_name}</p>}
                      <p className="text-[9px] mt-1" style={{ color: c.textDim }}>
                        {ev.owner_name || ''} {ev.created_at ? `· ${new Date(ev.created_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}` : ''}
                      </p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-sm" style={{ color: c.textDim }}>
                  {selectedDateStr ? 'No events this day' : 'Click a date to view events'}
                </p>
                {selectedDateStr && (
                  <button onClick={() => openAddEvent(selectedDateStr)} className="text-xs text-[var(--color-info-ios)] mt-2 hover:underline">Add an event</button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Add Event Dialog */}
      {showAddEvent && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowAddEvent(false)}>
          <div className="w-full max-w-md mx-4 rounded-xl p-6 shadow-2xl" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="add-calendar-event-dialog">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>Add Event</h2>
              <button onClick={() => setShowAddEvent(false)} className="p-1" style={{ color: c.textDim }}><X size={16} /></button>
            </div>
            <div className="flex gap-1 mb-3 flex-wrap">
              {['meeting', 'call', 'email', 'task', 'note', 'visit'].map(t => {
                const et = EVENT_TYPES.find(e => e.key === t);
                return (
                  <button key={t} onClick={() => setEventForm({ ...eventForm, type: t })}
                    className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md transition-all"
                    style={eventForm.type === t
                      ? { background: `${et.color}15`, color: et.color, border: `1px solid ${et.color}40` }
                      : { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted, border: '1px solid transparent' }
                    }
                    data-testid={`event-type-${t}`}>
                    <et.icon size={11} /> {et.label}
                  </button>
                );
              })}
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Subject *</label>
                <input value={eventForm.subject} onChange={e => setEventForm({ ...eventForm, subject: e.target.value })}
                  placeholder="e.g. Client follow-up call"
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="event-subject-input" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Date</label>
                <input type="date" value={eventForm.due_date} onChange={e => setEventForm({ ...eventForm, due_date: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="event-date-input" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Details</label>
                <textarea value={eventForm.body} onChange={e => setEventForm({ ...eventForm, body: e.target.value })}
                  placeholder="Notes, location, attendees..." rows={3}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md resize-none" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="event-body-input" />
              </div>
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowAddEvent(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleAddEvent} disabled={saving || !eventForm.subject.trim()}
                className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50"
                data-testid="save-calendar-event-btn">
                {saving ? 'Saving...' : 'Add Event'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
