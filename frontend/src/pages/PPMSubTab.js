import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '@/components/ui/dialog';
import axios from 'axios';
import { notify } from '@/components/notifications';
import {
  Calendar, Plus, CheckCircle, Clock, AlertTriangle, RefreshCw,
  ChevronDown, ChevronUp, Trash2, Upload, FileText, Download, X
} from 'lucide-react';

/* Use the site-wide CSS variables so dark/light mode works automatically */
const S = {
  card: { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', borderRadius: '12px', boxShadow: 'var(--theme-card-shadow)' },
  text: { color: 'var(--theme-text)' },
  muted: { color: 'var(--theme-text-muted)' },
  hover: { background: 'var(--theme-hover-bg)', borderColor: 'var(--theme-border)' },
  border: { borderColor: 'var(--theme-border)' },
};

const FREQ_LABELS = { weekly: 'Weekly', monthly: 'Monthly', quarterly: 'Quarterly', biannual: 'Bi-Annual', annual: 'Annual' };

const PPMSubTab = () => {
  const { API } = useAuth();
  const [schedules, setSchedules] = useState([]);
  const [summary, setSummary] = useState(null);
  const [checklists, setChecklists] = useState({});
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [form, setForm] = useState({
    title: '', description: '', frequency: 'annual', site_name: '', assigned_to: '',
    supplier_name: '', supplier_email: '', equipment_type: '', install_date: '',
    sla_tier: '', source: 'manual', checklist_category: '', checklist_items: [],
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [schedRes, sumRes, checkRes] = await Promise.all([
        axios.get(`${API}/ppm/schedules`, { headers }),
        axios.get(`${API}/ppm/summary`, { headers }),
        axios.get(`${API}/ppm/checklists`, { headers }),
      ]);
      setSchedules(schedRes.data.schedules || []);
      setSummary(sumRes.data);
      setChecklists(checkRes.data.checklists || {});
    } catch (err) { console.error('PPM load failed:', err); }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: context helpers re-create each render but read the latest token / handler at call time; adding them would invalidate the memo every render and break the optimisation.
  }, [API]);

  useEffect(() => { loadData(); }, [loadData]);

  const createSchedule = async () => {
    if (!form.title.trim()) { notify.error('Title required'); return; }
    try {
      const items = form.checklist_items.length > 0 ? form.checklist_items : (checklists[form.checklist_category] || []);
      await axios.post(`${API}/ppm/schedules`, { ...form, checklist_items: items }, { headers });
      notify.success('PPM schedule created');
      setShowCreate(false);
      setForm({ title: '', description: '', frequency: 'annual', site_name: '', assigned_to: '', supplier_name: '', supplier_email: '', equipment_type: '', install_date: '', sla_tier: '', source: 'manual', checklist_category: '', checklist_items: [] });
      loadData();
    } catch { notify.error('Failed to create schedule'); }
  };

  const completeTask = async (taskId) => {
    try { await axios.patch(`${API}/ppm/tasks/${taskId}`, { status: 'completed' }, { headers }); notify.success('Task marked complete'); loadData(); } catch { notify.error('Failed'); }
  };

  const deleteSchedule = async (scheduleId) => {
    try { await axios.delete(`${API}/ppm/schedules/${scheduleId}`, { headers }); notify.success('Schedule deleted'); loadData(); } catch { notify.error('Failed'); }
  };

  const uploadCertificate = async (scheduleId, file) => {
    const fd = new FormData(); fd.append('file', file);
    try { await axios.post(`${API}/ppm/schedules/${scheduleId}/certificates`, fd, { headers: { ...headers, 'Content-Type': 'multipart/form-data' } }); notify.success('Certificate uploaded'); loadData(); } catch { notify.error('Upload failed'); }
  };

  const deleteCertificate = async (scheduleId, certId) => {
    try { await axios.delete(`${API}/ppm/schedules/${scheduleId}/certificates/${certId}`, { headers }); notify.success('Certificate removed'); loadData(); } catch { notify.error('Failed'); }
  };

  const selectChecklist = (category) => {
    setForm(f => ({ ...f, checklist_category: category, checklist_items: checklists[category] || [], equipment_type: category }));
  };

  if (loading) return <div className="flex items-center justify-center py-16"><RefreshCw className="animate-spin" size={24} style={S.muted} /></div>;

  return (
    <div className="space-y-5" data-testid="ppm-subtab">
      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="ppm-summary-cards">
          {[
            { label: 'Active Schedules', value: summary.active_schedules, color: S.text },
            { label: 'Upcoming (90d)', value: summary.upcoming_90d, color: { color: 'var(--color-info)' } },
            { label: 'Completed', value: summary.completed, color: { color: 'var(--color-success)' } },
            { label: 'Overdue', value: summary.overdue, color: { color: 'var(--color-danger)' } },
            { label: 'Compliance', value: `${summary.compliance_pct}%`, color: S.text },
          ].map((c, i) => (
            <div key={i} style={S.card} className="p-4 text-center">
              <p className="text-2xl font-bold" style={c.color}>{c.value}</p>
              <p className="text-[11px] font-semibold mt-1" style={S.muted}>{c.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium" style={S.muted}>{schedules.length} schedule{schedules.length !== 1 ? 's' : ''}</p>
        <Button size="sm" onClick={() => setShowCreate(true)} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-alt2)] text-white h-8" data-testid="ppm-create-schedule">
          <Plus size={14} className="mr-1" /> New Schedule
        </Button>
      </div>

      {/* Schedule Cards */}
      <div className="space-y-3" data-testid="ppm-schedules-list">
        {schedules.length === 0 ? (
          <div style={S.card} className="p-10 text-center">
            <Calendar size={40} className="mx-auto mb-3" style={S.muted} />
            <p style={S.muted}>No PPM schedules yet. Create one to start tracking maintenance.</p>
          </div>
        ) : schedules.map(sched => {
          const isOpen = expanded === sched.id;
          const tasks = sched.tasks || [];
          const completedCount = tasks.filter(t => t.status === 'completed').length;
          const overdueCount = tasks.filter(t => t.status === 'overdue').length;
          const nextTask = tasks.find(t => t.status === 'scheduled' || t.status === 'overdue');
          const certs = sched.certificates || [];
          // Due-soon calc: any scheduled task within 7 days
          const now = Date.now();
          const dueSoonCount = tasks.filter(t => {
            if (t.status !== 'scheduled' || !t.due_date) return false;
            const days = (new Date(t.due_date).getTime() - now) / 86400000;
            return days >= 0 && days <= 7;
          }).length;
          const cardAccent = overdueCount > 0
            ? { borderLeft: '3px solid var(--color-danger)', boxShadow: '0 0 0 1px rgba(239,68,68,0.25), 0 4px 14px rgba(239,68,68,0.1)' }
            : dueSoonCount > 0
              ? { borderLeft: '3px solid var(--color-warning)', boxShadow: '0 0 0 1px rgba(245,158,11,0.25), 0 4px 14px rgba(245,158,11,0.1)' }
              : completedCount === tasks.length && tasks.length > 0
                ? { borderLeft: '3px solid var(--color-success)', boxShadow: '0 0 0 1px rgba(16,185,129,0.2)' }
                : {};

          return (
            <div key={sched.id} style={{ ...S.card, ...cardAccent, transition: 'all 0.2s ease' }} className="overflow-hidden" data-testid={`ppm-schedule-${sched.id}`}>
              {/* Header */}
              <div className="p-4 cursor-pointer" onClick={() => setExpanded(isOpen ? null : sched.id)}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-bold text-sm" style={S.text}>{sched.title}</p>
                      <Badge className="text-[10px] bg-blue-500/20 text-blue-500">{FREQ_LABELS[sched.frequency] || sched.frequency}</Badge>
                      {sched.sla_tier && <Badge className="text-[10px] bg-purple-500/20 text-purple-500">{sched.sla_tier} SLA</Badge>}
                      {overdueCount > 0 && <Badge className="text-[10px] bg-red-500/20 text-red-500">{overdueCount} Overdue</Badge>}
                      {overdueCount === 0 && dueSoonCount > 0 && <Badge className="text-[10px] bg-amber-500/20 text-amber-500">{dueSoonCount} Due Soon</Badge>}
                    </div>
                    <p className="text-xs mt-1" style={S.muted}>
                      {sched.site_name}{sched.equipment_type && ` · ${sched.equipment_type}`}{sched.supplier_name && ` · Supplier: ${sched.supplier_name}`}
                    </p>
                    <div className="flex items-center gap-4 mt-2 text-xs">
                      <span style={S.muted}>{tasks.length} visits</span>
                      {completedCount > 0 && <span className="text-emerald-500 font-semibold">{completedCount} completed</span>}
                      {nextTask && <span className="text-blue-500 font-semibold">Next: {nextTask.scheduled_date}</span>}
                      {certs.length > 0 && <span className="flex items-center gap-1 text-amber-500 font-semibold"><FileText size={12} /> {certs.length} cert{certs.length !== 1 ? 's' : ''}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-red-500" onClick={e => { e.stopPropagation(); deleteSchedule(sched.id); }} data-testid={`ppm-delete-${sched.id}`}><Trash2 size={14} /></Button>
                    {isOpen ? <ChevronUp size={16} style={S.muted} /> : <ChevronDown size={16} style={S.muted} />}
                  </div>
                </div>
              </div>

              {/* Expanded content */}
              {isOpen && (
                <div className="border-t px-4 pb-4 space-y-4" style={S.border}>
                  {sched.description && <p className="text-xs pt-3" style={S.muted}>{sched.description}</p>}

                  {/* Service Visits */}
                  <div className="pt-2">
                    <p className="text-xs font-bold mb-2" style={S.text}>Service Visits</p>
                    {tasks.length === 0 ? (
                      <p className="text-xs" style={S.muted}>No visits scheduled yet</p>
                    ) : (
                      <div className="space-y-1.5">
                        {tasks.map(task => (
                          <div key={task.id} className="rounded-lg border flex items-center justify-between p-2.5" style={{ ...S.hover, ...(task.status === 'completed' ? { background: 'rgba(16,185,129,0.08)' } : task.status === 'overdue' ? { background: 'rgba(239,68,68,0.08)' } : {}) }} data-testid={`ppm-task-${task.id}`}>
                            <div className="flex items-center gap-2">
                              {task.status === 'completed' ? <CheckCircle size={14} className="text-emerald-500" /> : task.status === 'overdue' ? <AlertTriangle size={14} className="text-red-500" /> : <Clock size={14} style={S.muted} />}
                              <span className="text-xs font-semibold" style={S.text}>{task.scheduled_date}</span>
                              <Badge className={`text-[10px] ${task.status === 'completed' ? 'bg-emerald-500/20 text-emerald-500' : task.status === 'overdue' ? 'bg-red-500/20 text-red-500' : 'bg-blue-500/20 text-blue-500'}`}>{task.status}</Badge>
                              {task.completed_by && <span className="text-[10px]" style={S.muted}>by {task.completed_by}</span>}
                            </div>
                            {task.status !== 'completed' && (
                              <Button size="sm" variant="outline" className="h-6 text-[10px] text-emerald-500 border-emerald-500/40 hover:bg-emerald-500/10" onClick={() => completeTask(task.id)} data-testid={`ppm-complete-${task.id}`}>
                                <CheckCircle size={10} className="mr-1" /> Complete
                              </Button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Checklist */}
                  {(sched.checklist_items || []).length > 0 && (
                    <div>
                      <p className="text-xs font-bold mb-2" style={S.text}>Service Checklist ({sched.checklist_category || sched.equipment_type || 'Custom'})</p>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
                        {sched.checklist_items.map((item, i) => (
                          <div key={i} className="flex items-start gap-1.5 text-[11px] py-0.5">
                            <CheckCircle size={10} className="mt-0.5 flex-shrink-0" style={S.muted} />
                            <span style={S.muted}>{item}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Certificates */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs font-bold" style={S.text}>Service Certificates</p>
                      <label className="cursor-pointer">
                        <input type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx" onChange={e => { if (e.target.files[0]) uploadCertificate(sched.id, e.target.files[0]); e.target.value = ''; }} data-testid={`ppm-upload-cert-${sched.id}`} />
                        <span className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded border cursor-pointer" style={{ ...S.border, ...S.muted }}><Upload size={10} /> Upload Certificate</span>
                      </label>
                    </div>
                    {certs.length === 0 ? (
                      <p className="text-[11px]" style={S.muted}>No certificates uploaded yet</p>
                    ) : (
                      <div className="space-y-1">
                        {certs.map(cert => (
                          <div key={cert.id} className="flex items-center justify-between p-2 rounded border" style={S.border}>
                            <div className="flex items-center gap-2">
                              <FileText size={14} className="text-amber-500" />
                              <div>
                                <p className="text-xs font-semibold" style={S.text}>{cert.filename}</p>
                                <p className="text-[10px]" style={S.muted}>Uploaded {cert.uploaded_at?.split('T')[0]} by {cert.uploaded_by}</p>
                              </div>
                            </div>
                            <div className="flex gap-1">
                              <a href={`${API}/ppm/schedules/${sched.id}/certificates/${cert.id}`} target="_blank" rel="noreferrer" className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded border" style={{ ...S.border, ...S.muted }}><Download size={10} /></a>
                              <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-red-500" onClick={() => deleteCertificate(sched.id, cert.id)}><X size={10} /></Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="ppm-create-dialog">
          <DialogHeader><DialogTitle>New PPM Schedule</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label className="text-xs font-semibold">Schedule Title</Label><Input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="e.g. Annual Treadmill Service" data-testid="ppm-form-title" /></div>
            <div><Label className="text-xs font-semibold">Description</Label><Textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Service details" rows={2} data-testid="ppm-form-desc" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-xs font-semibold">Source</Label>
                <Select value={form.source} onValueChange={v => setForm({ ...form, source: v })}><SelectTrigger data-testid="ppm-form-source"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="manual">Manual</SelectItem><SelectItem value="sla">SLA / Warranty</SelectItem></SelectContent>
                </Select></div>
              {form.source === 'sla' ? (
                <div><Label className="text-xs font-semibold">SLA Tier</Label>
                  <Select value={form.sla_tier} onValueChange={v => { const freq = (v === 'platinum' || v === 'gold') ? 'annual' : v === 'silver' ? 'biannual' : 'annual'; setForm({ ...form, sla_tier: v, frequency: freq }); }}>
                    <SelectTrigger data-testid="ppm-form-sla"><SelectValue placeholder="Select tier" /></SelectTrigger>
                    <SelectContent><SelectItem value="bronze">Bronze</SelectItem><SelectItem value="silver">Silver (2x/year)</SelectItem><SelectItem value="gold">Gold (1x/year)</SelectItem><SelectItem value="platinum">Platinum (1x/year)</SelectItem></SelectContent>
                  </Select></div>
              ) : (
                <div><Label className="text-xs font-semibold">Frequency</Label>
                  <Select value={form.frequency} onValueChange={v => setForm({ ...form, frequency: v })}><SelectTrigger data-testid="ppm-form-freq"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="monthly">Monthly</SelectItem><SelectItem value="quarterly">Quarterly</SelectItem><SelectItem value="biannual">Bi-Annual</SelectItem><SelectItem value="annual">Annual</SelectItem></SelectContent>
                  </Select></div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-xs font-semibold">Site</Label><Input value={form.site_name} onChange={e => setForm({ ...form, site_name: e.target.value })} placeholder="Site name" data-testid="ppm-form-site" /></div>
              <div><Label className="text-xs font-semibold">Install Date (Anniversary)</Label><Input type="date" value={form.install_date} onChange={e => setForm({ ...form, install_date: e.target.value })} data-testid="ppm-form-install-date" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-xs font-semibold">Supplier</Label><Input value={form.supplier_name} onChange={e => setForm({ ...form, supplier_name: e.target.value })} placeholder="Supplier name" data-testid="ppm-form-supplier" /></div>
              <div><Label className="text-xs font-semibold">Supplier Email</Label><Input value={form.supplier_email} onChange={e => setForm({ ...form, supplier_email: e.target.value })} placeholder="email@supplier.com" data-testid="ppm-form-supplier-email" /></div>
            </div>
            <div><Label className="text-xs font-semibold">Equipment Type & Service Checklist</Label>
              <Select value={form.checklist_category} onValueChange={selectChecklist}><SelectTrigger data-testid="ppm-form-checklist"><SelectValue placeholder="Select equipment type for checklist" /></SelectTrigger>
                <SelectContent>{Object.keys(checklists).map(k => (<SelectItem key={k} value={k}>{k} ({checklists[k].length} items)</SelectItem>))}</SelectContent>
              </Select>
              {form.checklist_items.length > 0 && (
                <div className="mt-2 max-h-32 overflow-y-auto border rounded p-2 text-xs space-y-0.5" style={S.border}>
                  {form.checklist_items.map((item, i) => (<div key={i} className="flex items-center gap-1.5" style={S.muted}><CheckCircle size={10} className="flex-shrink-0 opacity-40" />{item}</div>))}
                </div>
              )}</div>
            <div><Label className="text-xs font-semibold">Assigned To</Label><Input value={form.assigned_to} onChange={e => setForm({ ...form, assigned_to: e.target.value })} placeholder="Engineer or team" data-testid="ppm-form-assigned" /></div>
            <Button className="w-full bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-alt2)] text-white font-semibold" onClick={createSchedule} data-testid="ppm-form-submit">Create Schedule</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default PPMSubTab;
