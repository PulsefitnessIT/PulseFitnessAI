import React, { useState, useEffect, useCallback } from 'react';
import { useCRM } from './CRMApp';
import {
  Plus, Search, MessageSquare, CheckCircle, Clock,
  ArrowLeft, Phone, Mail, FileText, Calendar, Activity,
  X, Building2, Users, Target, MapPin
} from 'lucide-react';
import axios from 'axios';

const TYPE_COLORS = {
  note: 'var(--color-info-ios)', call: 'var(--color-success-alt)', email: 'var(--color-accent-magenta)',
  meeting: 'var(--color-warning)', task: 'var(--color-accent-amber)', system: 'var(--color-text-faint-alt)', visit: 'var(--color-cyan-500)',
};
const TYPE_ICONS = {
  note: FileText, call: Phone, email: Mail,
  meeting: Calendar, task: CheckCircle, system: Activity, visit: MapPin,
};
const TYPE_LIST = [
  { id: 'note', label: 'Notes' }, { id: 'call', label: 'Calls' },
  { id: 'email', label: 'Emails' }, { id: 'meeting', label: 'Meetings' },
  { id: 'task', label: 'Tasks' }, { id: 'system', label: 'System' },
];

export default function CRMInbox() {
  const { API, headers, c, isDark, user, navigateTo } = useCRM();
  const [activities, setActivities] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [teamMembers, setTeamMembers] = useState([]);
  const [staffFilter, setStaffFilter] = useState('mine');
  const [form, setForm] = useState({
    type: 'note', subject: '', body: '', company_id: '', contact_id: '',
    due_date: '', priority: 'normal',
  });
  const [saving, setSaving] = useState(false);

  const isManagerOrOwner = ['admin', 'owner', 'manager', 'director'].includes(user?.role);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ skip: '0', limit: '200' });
      if (typeFilter) params.set('type', typeFilter);
      const res = await axios.get(`${API}/crm/v2/activities?${params}`, { headers: headers() });
      setActivities(res.data.activities);
      setTotal(res.data.total);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [API, headers, typeFilter]);

  const loadLookups = useCallback(async () => {
    try {
      const [coRes, ctRes] = await Promise.all([
        axios.get(`${API}/crm/v2/companies?limit=200`, { headers: headers() }),
        axios.get(`${API}/crm/v2/contacts?limit=200`, { headers: headers() }),
      ]);
      setCompanies(coRes.data.companies);
      setContacts(ctRes.data.contacts);
    } catch (e) { console.error(e); }
  }, [API, headers]);

  const loadTeam = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/users`, { headers: headers() });
      setTeamMembers(res.data.users || []);
    } catch (e) { console.error(e); }
  }, [API, headers]);

  useEffect(() => { load(); loadTeam(); }, [load, loadTeam]);

  const handleCreate = async () => {
    if (!form.subject.trim()) return;
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/activities`, form, { headers: headers() });
      setShowCreate(false);
      setForm({ type: 'note', subject: '', body: '', company_id: '', contact_id: '', due_date: '', priority: 'normal' });
      load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const markComplete = async (actId) => {
    try {
      await axios.put(`${API}/crm/v2/activities/${actId}`, { completed_at: new Date().toISOString() }, { headers: headers() });
      load();
      if (selected?.id === actId) setSelected(null);
    } catch (e) { console.error(e); }
  };

  const deleteActivity = async (actId) => {
    try {
      await axios.delete(`${API}/crm/v2/activities/${actId}`, { headers: headers() });
      load();
      if (selected?.id === actId) setSelected(null);
    } catch (e) { console.error(e); }
  };

  const openCreate = () => { loadLookups(); setShowCreate(true); };

  // Staff filter
  const staffFiltered = activities.filter(a => {
    if (staffFilter === 'mine') return a.owner_id === user?.id || (!a.owner_id && a.owner_name === user?.full_name);
    if (staffFilter === 'all') return true;
    return a.owner_id === staffFilter || a.owner_name === teamMembers.find(m => m.id === staffFilter)?.full_name;
  });

  const filtered = search
    ? staffFiltered.filter(a => a.subject?.toLowerCase().includes(search.toLowerCase()) || a.body?.toLowerCase().includes(search.toLowerCase()) || a.owner_name?.toLowerCase().includes(search.toLowerCase()))
    : staffFiltered;

  const tasksDue = staffFiltered.filter(a => a.type === 'task' && !a.completed_at).length;
  const staffLabel = staffFilter === 'mine' ? 'My Activities' : staffFilter === 'all' ? 'All Staff' : (teamMembers.find(m => m.id === staffFilter)?.full_name || 'Staff');

  // Company-first contact filtering in create form
  const filteredContacts = form.company_id ? contacts.filter(ct => ct.company_id === form.company_id) : contacts;

  return (
    <div data-testid="crm-inbox">
      {/* Toolbar — search + filters + actions */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: c.textDim }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search activities..."
            className="w-full pl-9 pr-3 py-2 text-sm rounded-md"
            style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}`, color: c.text }}
            data-testid="inbox-search" />
        </div>

        <div className="flex items-center gap-1.5">
          <Users size={13} style={{ color: c.textDim }} />
          <select value={staffFilter} onChange={e => setStaffFilter(e.target.value)}
            className="px-2 py-1.5 text-xs rounded-md"
            style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
            data-testid="activity-staff-filter">
            <option value="mine">My Activities</option>
            {isManagerOrOwner && <option value="all">All Staff</option>}
            {isManagerOrOwner && teamMembers.map(m => (
              <option key={m.id} value={m.id}>{m.full_name}</option>
            ))}
          </select>
        </div>

        <p className="text-xs ml-auto" style={{ color: c.textDim }}>
          {filtered.length} activities
          {tasksDue > 0 && <> &middot; <span style={{ color: 'var(--color-accent-amber)' }}>{tasksDue} tasks due</span></>}
        </p>
        <button type="button" onClick={openCreate} className="btn-primary" data-testid="create-activity-btn">
          <Plus size={14} /> Log Activity
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">

        {/* Type Filter */}
        <div className="flex gap-1 overflow-x-auto">
          <button onClick={() => setTypeFilter('')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-all ${!typeFilter ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
            style={typeFilter ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}
            data-testid="filter-all">All</button>
          {TYPE_LIST.map(f => (
            <button key={f.id} onClick={() => setTypeFilter(f.id)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-all ${typeFilter === f.id ? '' : ''}`}
              style={typeFilter === f.id
                ? { background: `${TYPE_COLORS[f.id]}15`, color: TYPE_COLORS[f.id], border: `1px solid ${TYPE_COLORS[f.id]}40` }
                : { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted, border: '1px solid transparent' }
              }
              data-testid={`filter-${f.id}`}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Split layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-0 rounded-lg border overflow-hidden" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', minHeight: 'calc(100vh - 300px)' }}>
        {/* Activity list */}
        <div className={`overflow-y-auto ${selected ? 'hidden lg:block' : ''}`} style={{ borderRight: isDark ? '1px solid var(--color-surface-dark-panel)' : '1px solid var(--color-border-alt)' }} data-testid="inbox-list">
          {loading ? (
            <div className="flex justify-center py-12"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-16 px-4">
              <Activity size={36} className="mx-auto mb-3" style={{ color: c.textDim }} />
              <p className="text-sm" style={{ color: c.textDim }}>No activities{staffFilter === 'mine' ? ' in your feed' : ''}</p>
              <button onClick={openCreate} className="text-xs text-[var(--color-info-ios)] mt-2 hover:underline">Log your first activity</button>
            </div>
          ) : (
            filtered.map(act => {
              const Icon = TYPE_ICONS[act.type] || Activity;
              const color = TYPE_COLORS[act.type] || 'var(--color-text-faint-alt)';
              const isSelected = selected?.id === act.id;
              const timeAgo = (() => {
                const diff = Date.now() - new Date(act.created_at).getTime();
                const mins = Math.floor(diff / 60000);
                if (mins < 60) return `${mins}m`;
                const hrs = Math.floor(mins / 60);
                if (hrs < 24) return `${hrs}h`;
                return `${Math.floor(hrs / 24)}d`;
              })();
              return (
                <div key={act.id} onClick={() => setSelected(act)}
                  className="px-4 py-3 cursor-pointer transition-colors"
                  style={{
                    borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}`,
                    background: isSelected ? (isDark ? 'var(--color-surface-dark-2)' : 'var(--color-blue-50)') : 'transparent',
                    borderLeft: isSelected ? '3px solid var(--color-info-ios)' : '3px solid transparent',
                  }}
                  data-testid={`inbox-item-${act.id}`}>
                  <div className="flex items-start gap-3">
                    <div className="w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5" style={{ background: `${color}15` }}>
                      <Icon size={13} style={{ color }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium truncate" style={{ color: c.text }}>{act.subject}</p>
                        {act.type === 'task' && !act.completed_at && <Clock size={10} style={{ color: 'var(--color-accent-amber)' }} />}
                        {act.type === 'task' && act.completed_at && <CheckCircle size={10} style={{ color: 'var(--color-success-alt)' }} />}
                      </div>
                      {act.body && <p className="text-xs truncate mt-0.5" style={{ color: c.textDim }}>{act.body}</p>}
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        <span className="text-[10px]" style={{ color: c.textDim }}>{act.owner_name}</span>
                        <span className="text-[10px]" style={{ color: c.textDim }}>{timeAgo}</span>
                        {act.company_id && (
                          <span className="text-[9px] flex items-center gap-0.5 px-1.5 py-0.5 rounded" style={{ background: 'var(--color-info-ios)10', color: 'var(--color-info-ios)' }}>
                            <Building2 size={8} />{companies.find(co => co.id === act.company_id)?.name || ''}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Detail panel */}
        <div className={`lg:col-span-2 flex flex-col ${selected ? '' : 'hidden lg:flex'}`} style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)' }}>
          {selected ? (
            <div className="flex-1 overflow-y-auto">
              <div className="px-5 py-4 flex items-center justify-between" style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}`, background: isDark ? 'var(--color-surface-dark-1)' : '#fff' }}>
                <div className="flex items-center gap-3 min-w-0">
                  <button onClick={() => setSelected(null)} className="lg:hidden p-1 rounded-md" style={{ color: c.textDim }}><ArrowLeft size={16} /></button>
                  <div className="w-8 h-8 rounded-md flex items-center justify-center" style={{ background: `${TYPE_COLORS[selected.type] || 'var(--color-text-faint-alt)'}15` }}>
                    {React.createElement(TYPE_ICONS[selected.type] || Activity, { size: 15, style: { color: TYPE_COLORS[selected.type] || 'var(--color-text-faint-alt)' } })}
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold truncate" style={{ color: c.text }}>{selected.subject}</h3>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${TYPE_COLORS[selected.type]}20`, color: TYPE_COLORS[selected.type] }}>{selected.type}</span>
                      <span className="text-[10px]" style={{ color: c.textDim }}>by {selected.owner_name}</span>
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                  {selected.type === 'task' && !selected.completed_at && (
                    <button onClick={() => markComplete(selected.id)} className="px-3 py-1.5 text-xs font-medium rounded-md bg-[rgb(var(--rgb-success-alt)/0.1)] text-[var(--color-success-alt)] hover:bg-[rgb(var(--rgb-success-alt)/0.2)]" data-testid="mark-complete-btn">
                      <CheckCircle size={12} className="inline mr-1" /> Complete
                    </button>
                  )}
                  <button onClick={() => deleteActivity(selected.id)} className="px-3 py-1.5 text-xs font-medium rounded-md text-[var(--color-danger-alt)] hover:bg-[rgb(var(--rgb-danger-alt)/0.1)]" data-testid="delete-activity-btn">
                    <X size={12} className="inline mr-1" /> Delete
                  </button>
                </div>
              </div>
              <div className="px-5 py-5 space-y-4">
                {selected.body && (
                  <div className="p-4 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                    <p className="text-sm whitespace-pre-wrap" style={{ color: c.text }}>{selected.body}</p>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { l: 'Created', v: new Date(selected.created_at).toLocaleString('en-GB') },
                    { l: 'Priority', v: selected.priority },
                    { l: 'Due Date', v: selected.due_date ? new Date(selected.due_date).toLocaleDateString('en-GB') : null },
                    { l: 'Completed', v: selected.completed_at ? new Date(selected.completed_at).toLocaleString('en-GB') : null },
                  ].filter(r => r.v).map(r => (
                    <div key={r.l} className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                      <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{r.l}</p>
                      <p className="text-sm font-medium mt-0.5 capitalize" style={{ color: c.text }}>{r.v}</p>
                    </div>
                  ))}
                </div>
                {/* Linked entities */}
                {(selected.company_id || selected.contact_id || selected.opportunity_id) && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider font-medium mb-2" style={{ color: c.textDim }}>Linked To</p>
                    <div className="flex flex-wrap gap-2">
                      {selected.company_id && (
                        <button onClick={() => navigateTo && navigateTo('company', selected.company_id)} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all hover:scale-105" style={{ background: 'var(--color-accent-magenta)15', color: 'var(--color-accent-magenta)', border: '1px solid var(--color-accent-magenta)30' }} data-testid="linked-company">
                          <Building2 size={11} /> {companies.find(co => co.id === selected.company_id)?.name || 'Company'}
                        </button>
                      )}
                      {selected.opportunity_id && (
                        <button onClick={() => navigateTo && navigateTo('deal', selected.opportunity_id)} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all hover:scale-105" style={{ background: 'var(--color-info-ios)15', color: 'var(--color-info-ios)', border: '1px solid var(--color-info-ios)30' }} data-testid="linked-deal">
                          <Target size={11} /> Deal
                        </button>
                      )}
                    </div>
                  </div>
                )}
                {/* Type-specific metadata */}
                {selected.type === 'call' && (selected.call_duration || selected.call_outcome) && (
                  <div className="grid grid-cols-3 gap-3">
                    {selected.call_duration && <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}><p className="text-[10px] uppercase" style={{ color: c.textDim }}>Duration</p><p className="text-sm font-medium" style={{ color: c.text }}>{selected.call_duration} mins</p></div>}
                    {selected.call_outcome && <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}><p className="text-[10px] uppercase" style={{ color: c.textDim }}>Outcome</p><p className="text-sm font-medium capitalize" style={{ color: c.text }}>{selected.call_outcome}</p></div>}
                    {selected.follow_up_date && <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}><p className="text-[10px] uppercase" style={{ color: c.textDim }}>Follow-up</p><p className="text-sm font-medium" style={{ color: c.text }}>{new Date(selected.follow_up_date).toLocaleDateString('en-GB')}</p></div>}
                  </div>
                )}
                {selected.type === 'meeting' && (selected.meeting_location || selected.attendees) && (
                  <div className="grid grid-cols-2 gap-3">
                    {selected.meeting_location && <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}><p className="text-[10px] uppercase" style={{ color: c.textDim }}>Location</p><p className="text-sm font-medium" style={{ color: c.text }}>{selected.meeting_location}</p></div>}
                    {selected.attendees && <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}><p className="text-[10px] uppercase" style={{ color: c.textDim }}>Attendees</p><p className="text-sm font-medium" style={{ color: c.text }}>{selected.attendees}</p></div>}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <MessageSquare size={40} className="mx-auto mb-3" style={{ color: c.textDim }} />
                <p className="text-sm" style={{ color: c.textDim }}>Select an activity to view details</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create Activity Dialog */}
      {showCreate && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-lg mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="create-activity-dialog">
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-4 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>Log Activity</h2>
              <button onClick={() => setShowCreate(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="inbox-create-close"><X size={16} /></button>
            </div>
            <div className="flex gap-1 mb-4 flex-wrap">
              {['note', 'call', 'email', 'meeting', 'task'].map(t => (
                <button key={t} onClick={() => setForm({ ...form, type: t })}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md ${form.type === t ? '' : ''}`}
                  style={form.type === t
                    ? { background: `${TYPE_COLORS[t]}15`, color: TYPE_COLORS[t], border: `1px solid ${TYPE_COLORS[t]}40` }
                    : { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted, border: '1px solid transparent' }
                  }>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <div className="space-y-3">
              <input value={form.subject} onChange={e => setForm({ ...form, subject: e.target.value })} placeholder="Subject *"
                className="w-full px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="activity-subject-input" />
              <textarea value={form.body} onChange={e => setForm({ ...form, body: e.target.value })} placeholder="Details..." rows={3}
                className="w-full px-3 py-2 text-sm rounded-md resize-none" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />

              {form.type === 'email' && (
                <div className="grid grid-cols-2 gap-3">
                  <div><label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>From</label><input value={form.email_from || ''} onChange={e => setForm({ ...form, email_from: e.target.value })} placeholder="sender@email.com" className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} /></div>
                  <div><label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>To</label><input value={form.email_to || ''} onChange={e => setForm({ ...form, email_to: e.target.value })} placeholder="recipient@email.com" className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} /></div>
                </div>
              )}
              {form.type === 'call' && (
                <div className="grid grid-cols-3 gap-3">
                  <div><label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Duration (mins)</label><input type="number" value={form.call_duration || ''} onChange={e => setForm({ ...form, call_duration: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} /></div>
                  <div><label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Outcome</label><select value={form.call_outcome || 'connected'} onChange={e => setForm({ ...form, call_outcome: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}><option value="connected">Connected</option><option value="voicemail">Voicemail</option><option value="no_answer">No Answer</option></select></div>
                  <div><label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Follow-up</label><input type="date" value={form.follow_up_date || ''} onChange={e => setForm({ ...form, follow_up_date: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} /></div>
                </div>
              )}
              {form.type === 'meeting' && (
                <div className="grid grid-cols-2 gap-3">
                  <div><label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Location</label><input value={form.meeting_location || ''} onChange={e => setForm({ ...form, meeting_location: e.target.value })} placeholder="e.g. Teams / Office" className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} /></div>
                  <div><label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Duration (mins)</label><input type="number" value={form.meeting_duration || ''} onChange={e => setForm({ ...form, meeting_duration: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} /></div>
                  <div className="col-span-2"><label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Attendees</label><input value={form.attendees || ''} onChange={e => setForm({ ...form, attendees: e.target.value })} placeholder="Comma-separated" className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} /></div>
                </div>
              )}
              {form.type === 'task' && (
                <div className="grid grid-cols-2 gap-3">
                  <div><label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Due Date</label><input type="date" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} /></div>
                  <div><label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Priority</label><select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option></select></div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Company</label>
                  <select value={form.company_id} onChange={e => setForm({ ...form, company_id: e.target.value, contact_id: '' })}
                    className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                    <option value="">None</option>
                    {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Contact</label>
                  <select value={form.contact_id} onChange={e => setForm({ ...form, contact_id: e.target.value })}
                    className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                    <option value="">{form.company_id ? 'Select...' : 'Select company first...'}</option>
                    {filteredContacts.map(ct => <option key={ct.id} value={ct.id}>{ct.first_name} {ct.last_name}</option>)}
                  </select>
                </div>
              </div>
            </div>
            <div className="flex gap-2 mt-5 justify-end">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleCreate} disabled={saving || !form.subject.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="save-activity-btn">
                {saving ? 'Saving...' : 'Save Activity'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
