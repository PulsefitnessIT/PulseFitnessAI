import { useState, useEffect, useCallback, useRef } from 'react';
import { useCRM } from './CRMApp';
import {
  Plus, Search, Target, DollarSign, Calendar, User, Building2, ArrowLeft, GripVertical, List, LayoutGrid, X, Activity, FileText, Phone, Mail, CheckCircle, Edit2, Printer,
  GitBranch, Award,
} from 'lucide-react';
import axios from 'axios';
import HelpHint from '@/components/HelpHint';
import EmptyState from '@/components/shared/EmptyState';
import Button from '@/components/shared/Button';
import { notify } from '@/components/notifications';
import { notifyPicklistError } from '@/lib/picklistErrorHandler';
import TimelinePanel from '@/components/CRM/TimelinePanel';
import CRMAuditTrail from './CRMAuditTrail';
import { AINextActionCard } from './CRMPhase3Panels';
import { MEETING_LOCATION_PRESETS } from '@/utils/crmDropdowns';

const STAGE_COLORS = {
  lead: 'var(--color-text-faint-alt)', qualified: 'var(--color-accent-violet)', discovery: 'var(--color-info)', solution: 'var(--color-cyan-500)',
  proposal: 'var(--color-warning)', negotiation: 'var(--color-orange)', verbal_won: 'var(--color-success-alt-2)',
  closed_won: 'var(--color-success)', closed_lost: 'var(--color-danger)',
};

const fmt = (n) => `£${(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 0 })}`;

/* ═══ OPPORTUNITY DETAIL ═══ */
function OpportunityDetail({ oppId, onBack, c, isDark, API, headers, _setActiveTab, navigateTo }) {
  const [opp, setOpp] = useState(null);
  const [tab, setTab] = useState('overview');
  const [showAddNote, setShowAddNote] = useState(false);
  const [noteForm, setNoteForm] = useState({ subject: '', body: '', type: 'note' });
  const [saving, setSaving] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [editForm, setEditForm] = useState({});
  const [savingEdit, setSavingEdit] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/opportunities/${oppId}`, { headers: headers() });
      setOpp(res.data);
    } catch (e) { console.error(e); }
  }, [API, headers, oppId]);

  useEffect(() => { load(); }, [load]);

  const addActivity = async () => {
    if (!noteForm.subject.trim()) return;
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/activities`, {
        ...noteForm, opportunity_id: oppId,
        company_id: opp?.company_id, contact_id: opp?.contact_id,
      }, { headers: headers() });
      setShowAddNote(false);
      setNoteForm({ subject: '', body: '', type: 'note' });
      load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  if (!opp) return <div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  const openEdit = () => {
    setEditForm({
      title: opp.title || '', value: opp.value || '', stage: opp.stage || 'lead',
      close_date: opp.close_date || '', source: opp.source || '',
      next_step: opp.next_step || '', competitor: opp.competitor || '',
      probability: opp.probability || 0,
    });
    setShowEdit(true);
  };

  const saveEdit = async () => {
    setSavingEdit(true);
    try {
      await axios.put(`${API}/crm/v2/opportunities/${oppId}`, {
        ...editForm, value: parseFloat(editForm.value) || 0, probability: parseInt(editForm.probability) || 0,
      }, { headers: headers() });
      setShowEdit(false);
      load();
    } catch (e) {
      // Iter 220bt — surface picklist errors with "Did you mean" hint.
      if (!notifyPicklistError(e, notify)) {
        notify.error('Could not save opportunity', e?.response?.data?.detail || e.message);
      }
    }
    setSavingEdit(false);
  };

  const stageColor = STAGE_COLORS[opp.stage] || 'var(--color-text-faint-alt)';
  const actIcons = { note: FileText, call: Phone, email: Mail, meeting: Calendar, task: CheckCircle, system: Activity };

  return (
    <div data-testid="crm-opportunity-detail">
      <div className="flex items-center gap-3 mb-4">
        <button onClick={onBack} className="p-1.5 rounded-md" style={{ color: c.textDim }} data-testid="opp-back-btn"><ArrowLeft size={18} /></button>
        <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: `${stageColor}15` }}>
          <Target size={20} style={{ color: stageColor }} />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-lg font-bold truncate" style={{ color: c.text }}>{opp.title}</h1>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${stageColor}20`, color: stageColor }}>
              {opp.stage?.replace('_', ' ')}
            </span>
            {opp.company?.name && <span className="text-xs flex items-center gap-1" style={{ color: 'var(--color-info-ios)' }}><Building2 size={11} />{opp.company.name}</span>}
            {opp.contact && <span className="text-xs" style={{ color: c.textDim }}>{opp.contact.first_name} {opp.contact.last_name}</span>}
          </div>
        </div>
        <button onClick={openEdit} className="px-3 py-1.5 text-xs font-medium rounded-md border transition-all hover:bg-white/5" style={{ borderColor: c.border, color: c.textMuted }} data-testid="opp-edit-btn">
          <Edit2 size={12} className="inline mr-1" /> Edit
        </button>
        <button onClick={() => setShowAddNote(true)} className="px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md hover:bg-[var(--color-brand-blue-deep)]" data-testid="opp-add-activity-btn">
          <Plus size={12} className="inline mr-1" /> Activity
        </button>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        {[
          { label: 'Value', val: fmt(opp.value), color: 'var(--color-info-ios)' },
          { label: 'Weighted', val: fmt(opp.weighted_value), color: 'var(--color-success-alt)' },
          { label: 'Probability', val: `${opp.probability || 0}%`, color: opp.probability >= 60 ? 'var(--color-success-alt)' : 'var(--color-warning)' },
          { label: 'Close Date', val: opp.close_date || 'TBD', color: c.textMuted },
        ].map((kpi, i) => (
          <div key={i} className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{kpi.label}</p>
            <p className="text-lg font-bold" style={{ color: kpi.color }}>{kpi.val}</p>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 overflow-x-auto pb-1">
        {['overview', `quotes (${opp.quotes?.length || 0})`, `tenders (${opp.tenders?.length || 0})`, 'stage history', 'timeline', 'audit'].map(t => {
          const id = t.split(' ')[0];
          return (
            <button key={id} onClick={() => setTab(id)} className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap ${tab === id ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
              style={tab !== id ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          );
        })}
      </div>

      <div className="rounded-lg border p-5" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
        {tab === 'overview' && (
          <div className="space-y-3">
            <AINextActionCard opportunityId={oppId} />
            {[
              { l: 'Owner', v: opp.owner_name },
              { l: 'Source', v: opp.source },
              { l: 'Competitor', v: opp.competitor },
              { l: 'Next Step', v: opp.next_step },
            ].map(r => r.v ? (
              <div key={r.l} className="flex items-center gap-3">
                <span className="text-xs w-28" style={{ color: c.textDim }}>{r.l}</span>
                <span className="text-sm" style={{ color: c.text }}>{r.v}</span>
              </div>
            ) : null)}
            {opp.risk_factors?.length > 0 && (
              <div>
                <span className="text-xs" style={{ color: c.textDim }}>Risk Factors</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {opp.risk_factors.map((r, i) => (
                    <span key={i} className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'var(--color-danger-alt)20', color: 'var(--color-danger-alt)' }}>{r}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {tab === 'quotes' && (
          <div className="space-y-2">
            {(opp.quotes || []).map(q => (
              <div key={q.id} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <FileText size={16} style={{ color: 'var(--color-warning)' }} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium" style={{ color: c.text }}>{q.quote_number}</p>
                  <p className="text-[11px]" style={{ color: c.textDim }}>{q.status}</p>
                </div>
                <span className="text-sm font-bold" style={{ color: c.text }}>{fmt(q.total)}</span>
              </div>
            ))}
            {(opp.quotes || []).length === 0 && <p className="text-center py-6 text-sm" style={{ color: c.textDim }}>No quotes linked</p>}
          </div>
        )}

        {/* Iter 220an — Tenders linked to this opportunity */}
        {tab === 'tenders' && (
          <div className="space-y-2" data-testid="opportunity-tenders-section">
            {(opp.tenders || []).map(t => {
              const sc = {
                draft: 'var(--color-text-faint-alt)', parsing: 'var(--color-info-ios)',
                in_progress: 'var(--color-warning)', review: 'var(--color-accent-magenta)',
                submitted: 'var(--color-success-alt)', won: 'var(--color-success-alt-2)',
                lost: 'var(--color-danger)',
              }[t.status] || 'var(--color-text-faint-alt)';
              return (
                <div
                  key={t.id}
                  onClick={() => navigateTo && navigateTo('tender', t.id)}
                  className="flex items-center gap-3 p-3 rounded-md border cursor-pointer transition-all hover:scale-[1.005]"
                  style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
                  data-testid={`opportunity-tender-${t.id}`}
                >
                  <Award size={16} style={{ color: sc }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium truncate" style={{ color: c.text }}>{t.title}</p>
                      <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${sc}20`, color: sc }}>{t.status?.replace('_', ' ')}</span>
                      <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textDim }}>{t.type}</span>
                    </div>
                    <p className="text-[11px]" style={{ color: c.textDim }}>
                      {t.issuer && <>{t.issuer} &middot; </>}
                      {t.total_questions || 0} questions
                      {t.deadline && <> &middot; Due: {new Date(t.deadline).toLocaleDateString('en-GB')}</>}
                    </p>
                  </div>
                </div>
              );
            })}
            {(opp.tenders || []).length === 0 && (
              <p className="text-center py-6 text-sm" style={{ color: c.textDim }} data-testid="opportunity-tenders-empty">
                No tenders linked to this deal yet
              </p>
            )}
          </div>
        )}

        {tab === 'stage' && (
          <div className="space-y-0">
            {(opp.stage_history || []).slice().reverse().map((h, i) => (
              <div key={i} className="flex gap-3 relative">
                {i < (opp.stage_history?.length || 0) - 1 && <div className="absolute left-3.5 top-8 w-px h-full" style={{ background: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} />}
                <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10" style={{ background: `${STAGE_COLORS[h.stage] || 'var(--color-text-faint-alt)'}20` }}>
                  <Target size={12} style={{ color: STAGE_COLORS[h.stage] || 'var(--color-text-faint-alt)' }} />
                </div>
                <div className="flex-1 pb-4">
                  <p className="text-sm font-medium" style={{ color: c.text }}>{h.stage?.replace('_', ' ')}</p>
                  <p className="text-[10px]" style={{ color: c.textDim }}>
                    {h.by} &middot; {new Date(h.entered_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'timeline' && (
          <TimelinePanel
            scope={{ type: 'opportunity', id: oppId }}
            API={API}
            headers={headers}
            isDark={isDark}
            c={c}
          />
        )}

        {tab === 'audit' && (
          <CRMAuditTrail entityType="opportunity" entityId={oppId} emptyText="No edits logged on this deal yet." />
        )}
      </div>

      {/* Edit Deal Dialog */}
      {showEdit && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowEdit(false)}>
          <div className="w-full max-w-lg mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="edit-deal-dialog">
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-4 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>Edit Deal</h2>
              <button onClick={() => setShowEdit(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="edit-deal-close"><X size={16} /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Deal Title</label>
                <input value={editForm.title || ''} onChange={e => setEditForm({...editForm, title: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="edit-deal-title" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Value (£)</label>
                <input type="number" value={editForm.value || ''} onChange={e => setEditForm({...editForm, value: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="edit-deal-value" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Stage</label>
                <select value={editForm.stage || 'lead'} onChange={e => setEditForm({...editForm, stage: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="edit-deal-stage">
                  {Object.keys(STAGE_COLORS).map(s => <option key={s} value={s}>{s.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Close Date</label>
                <input type="date" value={editForm.close_date || ''} onChange={e => setEditForm({...editForm, close_date: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="edit-deal-close-date" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Probability (%)</label>
                <input type="number" min="0" max="100" value={editForm.probability || ''} onChange={e => setEditForm({...editForm, probability: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Source</label>
                <input value={editForm.source || ''} onChange={e => setEditForm({...editForm, source: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Competitor</label>
                <input value={editForm.competitor || ''} onChange={e => setEditForm({...editForm, competitor: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Next Step</label>
                <input value={editForm.next_step || ''} onChange={e => setEditForm({...editForm, next_step: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            </div>
            <div className="flex gap-2 mt-5 justify-end">
              <button onClick={() => setShowEdit(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={saveEdit} disabled={savingEdit} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="save-deal-edit-btn">
                {savingEdit ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Activity Dialog */}
      {showAddNote && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowAddNote(false)}>
          <div className="w-full max-w-md mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-3 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>Log Activity</h2>
              <button onClick={() => setShowAddNote(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="add-activity-close"><X size={16} /></button>
            </div>
            <div className="flex gap-1 mb-3 flex-wrap">
              {['note', 'call', 'email', 'meeting', 'task'].map(t => (
                <button key={t} onClick={() => setNoteForm({ ...noteForm, type: t })} className={`px-3 py-1.5 text-xs font-medium rounded-md ${noteForm.type === t ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
                  style={noteForm.type !== t ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <input value={noteForm.subject} onChange={e => setNoteForm({ ...noteForm, subject: e.target.value })} placeholder="Subject *" className="w-full mb-2 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
            <textarea value={noteForm.body} onChange={e => setNoteForm({ ...noteForm, body: e.target.value })} placeholder="Details..." rows={3} className="w-full mb-2 px-3 py-2 text-sm rounded-md resize-none" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
            {noteForm.type === 'email' && (
              <div className="grid grid-cols-2 gap-2 mb-2">
                <input value={noteForm.email_from||''} onChange={e => setNoteForm({...noteForm, email_from: e.target.value})} placeholder="From email" className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
                <input value={noteForm.email_to||''} onChange={e => setNoteForm({...noteForm, email_to: e.target.value})} placeholder="To email" className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            )}
            {noteForm.type === 'call' && (
              <div className="grid grid-cols-3 gap-2 mb-2">
                <input type="number" value={noteForm.call_duration||''} onChange={e => setNoteForm({...noteForm, call_duration: e.target.value})} placeholder="Mins" className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
                <select value={noteForm.call_outcome||'connected'} onChange={e => setNoteForm({...noteForm, call_outcome: e.target.value})} className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  <option value="connected">Connected</option><option value="voicemail">Voicemail</option><option value="no_answer">No Answer</option>
                </select>
                <input type="date" value={noteForm.follow_up_date||''} onChange={e => setNoteForm({...noteForm, follow_up_date: e.target.value})} className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            )}
            {noteForm.type === 'meeting' && (
              <div className="grid grid-cols-2 gap-2 mb-2">
                <input value={noteForm.meeting_location||''} onChange={e => setNoteForm({...noteForm, meeting_location: e.target.value})} placeholder="Location"
                  list="crm-meeting-location-presets"
                  className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
                <datalist id="crm-meeting-location-presets">
                  {MEETING_LOCATION_PRESETS.map((l) => <option key={l} value={l} />)}
                </datalist>
                <input type="number" value={noteForm.meeting_duration||''} onChange={e => setNoteForm({...noteForm, meeting_duration: e.target.value})} placeholder="Duration (mins)" className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
                <input value={noteForm.attendees||''} onChange={e => setNoteForm({...noteForm, attendees: e.target.value})} placeholder="Attendees" className="col-span-2 px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            )}
            {noteForm.type === 'task' && (
              <div className="grid grid-cols-2 gap-2 mb-2">
                <input type="date" value={noteForm.due_date||''} onChange={e => setNoteForm({...noteForm, due_date: e.target.value})} className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
                <select value={noteForm.priority||'normal'} onChange={e => setNoteForm({...noteForm, priority: e.target.value})} className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option>
                </select>
              </div>
            )}
            <div className="flex gap-2 justify-end mt-3">
              <button onClick={() => setShowAddNote(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={addActivity} disabled={saving || !noteForm.subject.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50">Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══ KANBAN VIEW ═══ */
function KanbanView({ opps, stages, onSelect, onMove, c, isDark }) {
  const dragItem = useRef(null);

  const handleDragStart = (id) => { dragItem.current = id; };
  const handleDragOver = (e) => { e.preventDefault(); };
  const handleDrop = (stageId) => {
    if (dragItem.current) { onMove(dragItem.current, stageId); dragItem.current = null; }
  };

  return (
    <div className="flex gap-3 overflow-x-auto pb-4 snap-x snap-mandatory" style={{ minHeight: 'calc(100vh - 320px)' }} data-testid="crm-kanban-board">
      {stages.filter(s => !['closed_won', 'closed_lost'].includes(s.id)).map(stage => {
        const stageOpps = opps.filter(o => o.stage === stage.id);
        const stageValue = stageOpps.reduce((s, o) => s + (o.value || 0), 0);
        const color = STAGE_COLORS[stage.id] || 'var(--color-text-faint-alt)';
        return (
          <div key={stage.id} className="flex-shrink-0 w-[280px] flex flex-col snap-start"
            onDragOver={handleDragOver} onDrop={() => handleDrop(stage.id)} data-testid={`kanban-col-${stage.id}`}>
            <div className="flex items-center justify-between px-3 py-2.5 mb-3 rounded-md" style={{ background: `${color}10`, borderLeft: `3px solid ${color}` }}>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium" style={{ color: c.text }}>{stage.name}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: isDark ? 'var(--color-ink-alt)' : 'var(--color-border-alt)', color: c.textDim }}>{stageOpps.length}</span>
              </div>
              <span className="text-[11px] font-mono" style={{ color: c.textDim }}>{fmt(stageValue)}</span>
            </div>
            <div className="flex-1 space-y-2 min-h-[100px]">
              {stageOpps.map(opp => (
                <div key={opp.id} draggable onDragStart={() => handleDragStart(opp.id)}
                  onClick={() => onSelect(opp.id)}
                  className="p-4 rounded-lg border cursor-pointer transition-all hover:scale-[1.01] group"
                  style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
                  data-testid={`deal-card-${opp.id}`}>
                  <div className="flex items-start justify-between mb-2">
                    <h4 className="text-sm font-medium leading-tight pr-2" style={{ color: c.text }}>{opp.title}</h4>
                    <GripVertical size={14} className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0" style={{ color: c.textDim }} />
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex items-center gap-1.5 font-medium" style={{ color: 'var(--color-success-alt)' }}>
                      <DollarSign size={12} /> {fmt(opp.value)}
                    </div>
                    {opp.company_name && (
                      <div className="flex items-center gap-1.5" style={{ color: c.textDim }}>
                        <Building2 size={12} /> {opp.company_name}
                      </div>
                    )}
                    {opp.contact_name && (
                      <div className="flex items-center gap-1.5" style={{ color: c.textDim }}>
                        <User size={12} /> {opp.contact_name}
                      </div>
                    )}
                    {opp.close_date && (
                      <div className="flex items-center gap-1.5" style={{ color: c.textDim }}>
                        <Calendar size={12} /> {opp.close_date}
                      </div>
                    )}
                  </div>
                  <div className="mt-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Win prob.</span>
                      <span className="text-xs font-medium" style={{ color: opp.probability >= 60 ? 'var(--color-success-alt)' : opp.probability >= 30 ? 'var(--color-warning)' : 'var(--color-danger)' }}>
                        {opp.probability}%
                      </span>
                    </div>
                    <div className="h-1 rounded-full overflow-hidden" style={{ background: isDark ? 'var(--color-ink-alt)' : 'var(--color-border-alt)' }}>
                      <div className="h-full rounded-full transition-all" style={{ width: `${opp.probability}%`, background: opp.probability >= 60 ? 'var(--color-success-alt)' : opp.probability >= 30 ? 'var(--color-warning)' : 'var(--color-danger)' }} />
                    </div>
                  </div>
                </div>
              ))}
              {stageOpps.length === 0 && (
                <div className="text-center py-8 text-xs border border-dashed rounded-md" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c.textDim }}>
                  Drop deals here
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ═══ LIST VIEW ═══ */
function ListView({ opps, onSelect, c, isDark }) {
  return (
    <div className="rounded-lg border overflow-hidden" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="crm-pipeline-list">
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }}>
              {['Deal', 'Company', 'Value', 'Stage', 'Probability', 'Close Date', 'Owner'].map(h => (
                <th key={h} className="px-4 py-3 text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {opps.map(opp => {
              const stageColor = STAGE_COLORS[opp.stage] || 'var(--color-text-faint-alt)';
              return (
                <tr key={opp.id} onClick={() => onSelect(opp.id)} className="cursor-pointer transition-colors hover:opacity-80"
                  style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}` }} data-testid={`deal-row-${opp.id}`}>
                  <td className="px-4 py-3 font-medium" style={{ color: c.text }}>{opp.title}</td>
                  <td className="px-4 py-3" style={{ color: c.textMuted }}>{opp.company_name || '—'}</td>
                  <td className="px-4 py-3 font-bold" style={{ color: 'var(--color-success-alt)' }}>{fmt(opp.value)}</td>
                  <td className="px-4 py-3">
                    <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${stageColor}20`, color: stageColor }}>
                      {opp.stage?.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-3" style={{ color: opp.probability >= 60 ? 'var(--color-success-alt)' : 'var(--color-warning)' }}>{opp.probability}%</td>
                  <td className="px-4 py-3" style={{ color: c.textDim }}>{opp.close_date || '—'}</td>
                  <td className="px-4 py-3" style={{ color: c.textDim }}>{opp.owner_name || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {opps.length === 0 && (
        <EmptyState
          icon={Target}
          title="Your pipeline is wide open"
          hint="Add your first opportunity to start tracking deals through stages, set probabilities, and forecast revenue. Or import existing deals from CSV."
          testId="crm-pipeline-list-empty"
        />
      )}
    </div>
  );
}

/* ═══ MAIN PIPELINE ═══ */
export default function CRMPipeline() {
  const crm = useCRM();
  const { API, headers, c, isDark, navTarget, setNavTarget } = crm;
  const [opps, setOpps] = useState([]);
  const [stages, setStages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('kanban');
  const [search, setSearch] = useState('');
  const [selectedOpp, setSelectedOpp] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [form, setForm] = useState({
    title: '', value: '', company_id: '', company_name: '', contact_id: '', contact_name: '',
    stage: 'lead', close_date: '', source: '', next_step: '',
  });
  const [saving, setSaving] = useState(false);

  // Cross-module navigation
  useEffect(() => {
    if (navTarget && (navTarget.type === 'opportunity' || navTarget.type === 'deal') && navTarget.id) {
      setSelectedOpp(navTarget.id);
      setNavTarget(null);
    }
  }, [navTarget, setNavTarget]);

  const load = useCallback(async () => {
    try {
      const [oppsRes, stagesRes] = await Promise.all([
        axios.get(`${API}/crm/v2/opportunities?limit=200`, { headers: headers() }),
        axios.get(`${API}/crm/v2/opportunities/stages`, { headers: headers() }),
      ]);
      setOpps(oppsRes.data.opportunities);
      setStages(stagesRes.data.stages);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [API, headers]);

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

  useEffect(() => { load(); }, [load]);

  const moveOpp = async (oppId, newStage) => {
    setOpps(prev => prev.map(o => o.id === oppId ? { ...o, stage: newStage } : o));
    try {
      await axios.put(`${API}/crm/v2/opportunities/${oppId}`, { stage: newStage }, { headers: headers() });
      load();
    } catch (e) { console.error(e); load(); }
  };

  const handleCreate = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const payload = { ...form, value: parseFloat(form.value) || 0 };
      const _res = await axios.post(`${API}/crm/v2/opportunities`, payload, { headers: headers() });
      setShowCreate(false);
      setForm({ title: '', value: '', company_id: '', company_name: '', contact_id: '', contact_name: '', stage: 'lead', close_date: '', source: '', next_step: '' });
      load();
    } catch (e) {
      // Iter 220bs / 220bt — surface structured picklist-validation
      // errors as a rich "Did you mean: X?" toast so the operator
      // can fix the offending field in one click.
      if (!notifyPicklistError(e, notify)) {
        notify.error('Could not create opportunity', e?.response?.data?.detail || e.message);
      }
    }
    setSaving(false);
  };

  const openCreate = () => {
    loadLookups();
    setShowCreate(true);
  };

  if (selectedOpp) {
    return <OpportunityDetail oppId={selectedOpp} onBack={() => { setSelectedOpp(null); load(); }} {...crm} />;
  }

  const activeOpps = opps.filter(o => !['closed_won', 'closed_lost'].includes(o.stage));
  const filtered = search
    ? activeOpps.filter(o => o.title?.toLowerCase().includes(search.toLowerCase()) || o.company_name?.toLowerCase().includes(search.toLowerCase()))
    : activeOpps;
  const pipelineTotal = activeOpps.reduce((s, o) => s + (o.value || 0), 0);
  const weightedTotal = activeOpps.reduce((s, o) => s + (o.weighted_value || 0), 0);

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  const printReport = () => {
    const sorted = [...activeOpps].sort((a, b) => (b.probability || 0) - (a.probability || 0));
    const rows = sorted.map(o =>
      `<tr><td style="padding:8px;border-bottom:1px solid #eee">${o.title}</td><td style="padding:8px;border-bottom:1px solid #eee">${o.company_name || '—'}</td><td style="padding:8px;border-bottom:1px solid #eee">${(o.stage || '').replace('_',' ')}</td><td style="padding:8px;border-bottom:1px solid #eee;text-align:right">£${(o.value || 0).toLocaleString()}</td><td style="padding:8px;border-bottom:1px solid #eee;text-align:right">${o.probability || 0}%</td><td style="padding:8px;border-bottom:1px solid #eee;text-align:right">£${(o.weighted_value || 0).toLocaleString()}</td><td style="padding:8px;border-bottom:1px solid #eee">${o.close_date || '—'}</td><td style="padding:8px;border-bottom:1px solid #eee">${o.owner_name || '—'}</td></tr>`
    ).join('');
    const html = `<html><head><title>Pipeline Report</title><style>body{font-family:-apple-system,sans-serif;padding:40px;color:#111}h1{font-size:20px;margin-bottom:4px}table{width:100%;border-collapse:collapse;margin-top:16px}th{text-align:left;padding:10px 8px;background:var(--color-neutral-75);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #ddd}td{font-size:13px}.summary{display:flex;gap:32px;margin:12px 0;font-size:13px;color:#666}</style></head><body><h1>Pipeline Report</h1><p style="color:#888;font-size:12px">${new Date().toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long',year:'numeric'})}</p><div class="summary"><span><b>${activeOpps.length}</b> active deals</span><span>Total: <b>£${pipelineTotal.toLocaleString()}</b></span><span>Weighted: <b>£${weightedTotal.toLocaleString()}</b></span></div><table><thead><tr><th>Deal</th><th>Company</th><th>Stage</th><th style="text-align:right">Value</th><th style="text-align:right">Probability</th><th style="text-align:right">Weighted</th><th>Close Date</th><th>Owner</th></tr></thead><tbody>${rows}</tbody></table></body></html>`;
    const win = window.open('', '_blank');
    win.document.write(html);
    win.document.close();
    win.print();
  };

  return (
    <div data-testid="crm-pipeline">
      {/* Toolbar — search + summary + view-toggle + actions */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: c.textDim }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search deals..." className="w-full pl-9 pr-3 py-2 text-sm rounded-md"
            style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}`, color: c.text }} data-testid="pipeline-search" />
        </div>
        <p className="text-xs flex items-center gap-1.5" style={{ color: c.textDim }}>
          {activeOpps.length} active &middot; {fmt(pipelineTotal)} total &middot; {fmt(weightedTotal)} weighted
          <HelpHint guideId="crm-pipeline-first-deal" testId="help-hint-pipeline" />
        </p>
        <div className="flex items-center gap-2 ml-auto">
          <Button variant="secondary" size="sm" onClick={printReport} icon={Printer} data-testid="print-report-btn">
            Report
          </Button>
          <div className="subtab-bar">
            <button type="button" onClick={() => setView('kanban')} className={`subtab-pill ${view === 'kanban' ? 'is-active' : ''}`} data-testid="view-kanban-btn">
              <LayoutGrid size={14} />
            </button>
            <button type="button" onClick={() => setView('list')} className={`subtab-pill ${view === 'list' ? 'is-active' : ''}`} data-testid="view-list-btn">
              <List size={14} />
            </button>
          </div>
          <Button variant="primary" size="sm" onClick={openCreate} icon={Plus} data-testid="create-deal-btn">
            New Deal
          </Button>
        </div>
      </div>

      {/* View */}
      {opps.length === 0 ? (
        <EmptyState
          icon={GitBranch}
          title="Your pipeline is empty"
          hint="Create your first deal to start tracking opportunities. Deals move through stages with auto-updated probability and weighted forecasting."
          primaryAction={{ label: 'New deal', onClick: openCreate, testId: 'crm-pipeline-empty-create' }}
          testId="crm-pipeline-empty"
        />
      ) : view === 'kanban' ? (
        <KanbanView opps={filtered} stages={stages} onSelect={setSelectedOpp} onMove={moveOpp} c={c} isDark={isDark} />
      ) : (
        <ListView opps={filtered} onSelect={setSelectedOpp} c={c} isDark={isDark} />
      )}

      {/* Create Dialog */}
      {showCreate && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-lg mx-4 rounded-xl p-6 shadow-2xl" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="create-deal-dialog">
            <h2 className="text-lg font-semibold mb-4" style={{ color: c.text }}>New Opportunity</h2>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Deal Title *</label>
                <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Value (£)</label>
                <input type="number" value={form.value} onChange={e => setForm({ ...form, value: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Stage</label>
                <select value={form.stage} onChange={e => setForm({ ...form, stage: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  {stages.filter(s => !['closed_won', 'closed_lost'].includes(s.id)).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Company</label>
                <select value={form.company_id} onChange={e => {
                  const co = companies.find(c => c.id === e.target.value);
                  setForm({ ...form, company_id: e.target.value, company_name: co?.name || '', contact_id: '', contact_name: '' });
                }} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  <option value="">Select...</option>
                  {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Contact {form.company_id && <span className="normal-case font-normal" style={{ color: c.textDim }}>({(contacts.filter(ct => ct.company_id === form.company_id)).length})</span>}</label>
                <select value={form.contact_id} onChange={e => {
                  const ct = contacts.find(c => c.id === e.target.value);
                  setForm({ ...form, contact_id: e.target.value, contact_name: ct ? `${ct.first_name} ${ct.last_name}` : '' });
                }} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  <option value="">Select{form.company_id ? '' : ' company first'}...</option>
                  {(form.company_id ? contacts.filter(ct => ct.company_id === form.company_id) : contacts).map(ct => <option key={ct.id} value={ct.id}>{ct.first_name} {ct.last_name}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Close Date</label>
                <input type="date" value={form.close_date} onChange={e => setForm({ ...form, close_date: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Source</label>
                <input value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} placeholder="e.g. Referral" className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            </div>
            <div className="flex gap-2 mt-5 justify-end">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm rounded-md" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleCreate} disabled={saving || !form.title.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md hover:bg-[var(--color-brand-blue-deep)] disabled:opacity-50">
                {saving ? 'Creating...' : 'Create Deal'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
