import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import {
  ClipboardCheck, Plus, Calendar, CheckCircle, X, History,
  Users, BarChart3, Trash2, Search, ChevronDown, ChevronUp
} from 'lucide-react';

const EQUIPMENT_TYPE_TASKS = {
  'Treadmill': ['All Areas Cleaned','Hoover Underneath','E-Stop Check','Console + & - Keys Check','Heart Rate Check','Speed Test','Incline Check','Belt Aligned','Power/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Running Machine': ['All Areas Cleaned','Hoover Underneath','E-Stop Check','Console + & - Keys Check','Heart Rate Check','Speed Test','Incline Check','Belt Aligned','Power/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Upright Bike': ['All Areas Cleaned','Hoover Underneath','Seat Adjustment Working','Foot Straps & Pedals Check','+ & - Keys Check','Resistance Check','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Recumbent Bike': ['All Areas Cleaned','Hoover Underneath','Seat Adjustment Working','Foot Straps & Pedals Check','+ & - Keys Check','Resistance Check','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Exercise Bike': ['All Areas Cleaned','Hoover Underneath','Seat Adjustment Working','Foot Straps & Pedals Check','+ & - Keys Check','Resistance Check','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Cross Trainer': ['All Areas Cleaned','Hoover Underneath','Handles Move Smoothly','Pedals Check','+ & - Keys Check','Resistance Check','Heart Rate Check','Console Check','Power Cable/Ethernet Cable Fitted OK','TV Tuned/Internet Connected'],
  'Rower': ['All Areas Cleaned','Hoover Underneath','Foot Straps & Heel Lock Check','Console Check/Batteries OK','Console Keys Check','Smooth Chain/Seat Rail - Lubricate If Required','Heart Rate Check','Resistance Check/Fan','Hoover Fan','Inspect Bungees and Drive Cords'],
  'Rowing Machine': ['All Areas Cleaned','Hoover Underneath','Foot Straps & Heel Lock Check','Console Check/Batteries OK','Console Keys Check','Smooth Chain/Seat Rail - Lubricate If Required','Heart Rate Check','Resistance Check/Fan','Hoover Fan','Inspect Bungees and Drive Cords'],
  'Spin Bike': ['All Areas Cleaned','All Locking Levers/Knobs Checked','Pedals Screwed In Tightly','Toe Straps Secure','Crank Feels Smooth','Handlebars Check','Console Batteries OK','Speed Test','Resistance Check'],
  'Group Cycle': ['All Areas Cleaned','All Locking Levers/Knobs Checked','Pedals Screwed In Tightly','Toe Straps Secure','Crank Feels Smooth','Handlebars Check','Console Batteries OK','Speed Test','Resistance Check'],
  'Strength Equipment': ['All Areas Cleaned','Hoover Around','Check Upholstery for Splits','Tighten Upholstery Bolts','Lubricate Guiding Rods','Lubricate Moving Parts When Needed','Check all Cables & Pulleys','Smooth Seat Movement','Weight Pin Available & Can Select Each Weight','Handles Move Smoothly'],
  'Free Weights': ['Framework Dusted','Upholstery Clean','Clean Mirrors','Wipe down Weight Plates','Check Weight Bars for Defects','Check Rubber Weight Covers','Check & Clean Dumbbell Stack','Lubricate Moving Parts','Check Upholstery for Splits','Tighten Weight Bolts'],
  'Bench': ['Framework Dusted','Upholstery Clean','Check Upholstery for Splits','Tighten Upholstery Bolts','Check Adjustment Pins','Lubricate Moving Parts','Check All Bolts & Fixings','Clean Frame'],
};
const DEFAULT_TASKS = ['All Areas Cleaned','Visual Inspection for Damage','Check for Loose Bolts/Fixings','Lubricate Moving Parts','Check Safety Features','Console/Display Check','Power Cable Check','Test Equipment Operation'];

function getTasksForType(type) {
  if (!type) return DEFAULT_TASKS;
  const lower = type.toLowerCase();
  for (const [key, tasks] of Object.entries(EQUIPMENT_TYPE_TASKS)) {
    if (lower.includes(key.toLowerCase()) || key.toLowerCase().includes(lower)) return tasks;
  }
  return DEFAULT_TASKS;
}

const PulseCheckSheetsTab = ({ equipment }) => {
  const { API } = useAuth();
  const [subTab, setSubTab] = useState('sheets');
  const [history, setHistory] = useState([]);
  const [report, setReport] = useState(null);
  const [customTemplates, setCustomTemplates] = useState([]);
  const [showCompleteDialog, setShowCompleteDialog] = useState(false);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [activeSheet, setActiveSheet] = useState(null);
  const [completionDate, setCompletionDate] = useState(new Date().toISOString().split('T')[0]);
  const [completionNotes, setCompletionNotes] = useState('');
  const [checkedItems, setCheckedItems] = useState({});
  const [selectedSerial, setSelectedSerial] = useState('');
  const [expandedHistory, setExpandedHistory] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [newTemplate, setNewTemplate] = useState({ name: '', items: [''] });
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const loadHistory = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/check-sheets/history`, { headers });
      setHistory(res.data.completions || []);
    } catch (err) { console.error('Failed to load check sheet history:', err); }
  }, [API]);

  const loadReport = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/check-sheets/report`, { headers });
      setReport(res.data);
    } catch (err) { console.error('Failed to load check sheet report:', err); }
  }, [API]);

  const loadCustomTemplates = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/maintenance/templates`, { headers });
      setCustomTemplates(res.data.templates || []);
    } catch (err) { console.error('Failed to load custom templates:', err); }
  }, [API]);

  useEffect(() => { loadHistory(); loadReport(); loadCustomTemplates(); }, [loadHistory, loadReport, loadCustomTemplates]);

  const handleStartSheet = (group) => {
    const tasks = getTasksForType(group.equipment_type);
    setActiveSheet({ name: group.equipment_type, equipment_type: group.equipment_type, machines: group.machines, items: tasks });
    setSelectedSerial(group.machines.length === 1 ? (group.machines[0].serial_number || group.machines[0].name) : '');
    setCheckedItems({});
    setCompletionDate(new Date().toISOString().split('T')[0]);
    setCompletionNotes('');
    setShowCompleteDialog(true);
  };

  const handleStartCustomSheet = (template) => {
    setActiveSheet({ name: template.name, equipment_type: 'Custom', items: template.items || [], template_id: template.id, machines: [] });
    setCheckedItems({});
    setCompletionDate(new Date().toISOString().split('T')[0]);
    setCompletionNotes('');
    setShowCompleteDialog(true);
  };

  const handleCompleteSheet = async () => {
    if (activeSheet?.machines?.length > 1 && !selectedSerial) { notify.error('Please select a machine'); return; }
    const items = activeSheet.items.map(item => ({ name: item, checked: !!checkedItems[item] }));
    const sel = (activeSheet.machines || []).find(m => (m.serial_number || m.name) === selectedSerial);
    const templateName = sel ? `${activeSheet.equipment_type} - ${selectedSerial}` : activeSheet.name;
    try {
      await axios.post(`${API}/check-sheets/complete`, {
        template_id: sel?.id || activeSheet.template_id || activeSheet.name,
        template_name: templateName, serial_number: selectedSerial || '',
        equipment_type: activeSheet.equipment_type, date: completionDate, items, notes: completionNotes
      }, { headers });
      notify.success(`Check sheet completed for ${templateName}`);
      setShowCompleteDialog(false);
      loadHistory(); loadReport();
    } catch { notify.error('Failed to save'); }
  };

  const handleCreateTemplate = async () => {
    if (!newTemplate.name.trim()) { notify.error('Enter a template name'); return; }
    const items = newTemplate.items.filter(i => i.trim());
    if (!items.length) { notify.error('Add at least one item'); return; }
    try {
      await axios.post(`${API}/maintenance/templates`, { name: newTemplate.name, category: 'Custom', items }, { headers });
      notify.success('Template created');
      setShowCreateDialog(false);
      setNewTemplate({ name: '', items: [''] });
      loadCustomTemplates();
    } catch { notify.error('Failed to create template'); }
  };

  const handleDeleteTemplate = async (id) => {
    try {
      await axios.delete(`${API}/maintenance/templates/${id}`, { headers });
      setCustomTemplates(customTemplates.filter(t => t.id !== id));
      notify.success('Template deleted');
    } catch { notify.error('Failed to delete'); }
  };

  // Group equipment by type
  const filtered = equipment.filter(e => !searchQuery || e.name?.toLowerCase().includes(searchQuery.toLowerCase()) || (e.serial_number || '').toLowerCase().includes(searchQuery.toLowerCase()));
  const grouped = [];
  const typeMap = {};
  for (const eq of filtered) {
    const type = eq.equipment_type || 'Other';
    if (!typeMap[type]) { typeMap[type] = { equipment_type: type, machines: [] }; grouped.push(typeMap[type]); }
    typeMap[type].machines.push(eq);
  }

  const todayStr = new Date().toISOString().split('T')[0];
  const todayHistory = history.filter(h => (h.completed_date || '').startsWith(todayStr));
  const completedTodayNames = new Set(todayHistory.map(h => h.template_name));

  return (
    <div className="space-y-5" data-testid="pulse-check-sheets">
      {/* Sub-tabs */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex gap-2">
          {[{ key: 'sheets', label: 'Check Sheets', icon: ClipboardCheck }, { key: 'history', label: 'History', icon: History }, { key: 'report', label: 'Report', icon: BarChart3 }].map(tab => (
            <button key={tab.key} onClick={() => setSubTab(tab.key)} className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-all ${subTab === tab.key ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-white border-zinc-200 text-zinc-500 hover:border-zinc-300 dark:bg-zinc-900 dark:border-zinc-800'}`} data-testid={`pulse-cs-tab-${tab.key}`}>
              <tab.icon size={15} />{tab.label}
            </button>
          ))}
        </div>
        {subTab === 'sheets' && (
          <Button size="sm" onClick={() => setShowCreateDialog(true)} className="bg-blue-600 hover:bg-blue-700 text-white" data-testid="pulse-create-template-btn">
            <Plus size={14} className="mr-1" /> Custom Template
          </Button>
        )}
      </div>

      {/* Sheets Tab */}
      {subTab === 'sheets' && (
        <div className="space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" size={16} />
            <Input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search equipment..." className="bg-white border-zinc-200 text-zinc-900 pl-10 h-10 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" data-testid="pulse-cs-search" />
          </div>
          {/* Today's Progress */}
          <Card className="bg-blue-50 border-blue-200 p-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Calendar size={18} className="text-blue-600" />
                <div><p className="text-zinc-900 font-medium text-sm dark:text-zinc-100">Today's Progress</p><p className="text-zinc-500 text-xs">{todayStr}</p></div>
              </div>
              <Badge className="bg-blue-100 text-blue-700 border-blue-200" data-testid="pulse-today-progress">
                {todayHistory.length} completed today
              </Badge>
            </div>
          </Card>
          {/* Equipment Groups */}
          {grouped.map(group => {
            const tasks = getTasksForType(group.equipment_type);
            const done = group.machines.every(m => completedTodayNames.has(`${group.equipment_type} - ${m.serial_number || m.name}`));
            return (
              <Card key={group.equipment_type} className={`bg-white shadow-sm p-5 transition-colors ${done ? 'border-emerald-300' : 'border-zinc-200 hover:border-blue-300 dark:border-zinc-800'}`} data-testid={`pulse-equip-group-${group.equipment_type}`}>
                <div className="flex items-center justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold text-zinc-900 dark:text-zinc-100">{group.equipment_type}</h3>
                      <Badge className="bg-zinc-100 text-zinc-500 text-xs dark:bg-zinc-800">{group.machines.length} machine{group.machines.length > 1 ? 's' : ''}</Badge>
                      {done && <Badge className="bg-emerald-50 text-emerald-700 text-xs"><CheckCircle size={10} className="mr-1" />Done</Badge>}
                    </div>
                    <div className="flex flex-wrap gap-1 mb-1">
                      {group.machines.map(m => {
                        const sn = m.serial_number || m.name;
                        const isChecked = completedTodayNames.has(`${group.equipment_type} - ${sn}`);
                        return <span key={m.id} className={`text-xs px-2 py-0.5 rounded border ${isChecked ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-zinc-50 border-zinc-200 text-zinc-500 dark:bg-zinc-900 dark:border-zinc-800'}`}>{isChecked && <CheckCircle size={9} className="inline mr-0.5" />}{sn}</span>;
                      })}
                    </div>
                    <p className="text-xs text-zinc-400">{tasks.slice(0, 3).join(' · ')}{tasks.length > 3 ? ` +${tasks.length - 3} more` : ''}</p>
                  </div>
                  <Button onClick={() => handleStartSheet(group)} className={done ? 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200' : 'bg-blue-600 hover:bg-blue-700 text-white'} data-testid={`pulse-start-${group.equipment_type}`}>
                    <ClipboardCheck size={15} className="mr-1.5" />{done ? 'Check Again' : 'Start Check'}
                  </Button>
                </div>
              </Card>
            );
          })}
          {grouped.length === 0 && <p className="text-center text-zinc-400 py-8 text-sm">No equipment found</p>}
          {/* Custom Templates */}
          {customTemplates.length > 0 && (
            <div className="mt-4">
              <h3 className="font-semibold text-zinc-900 text-sm mb-3 dark:text-zinc-100">Custom Templates</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {customTemplates.map(t => (
                  <Card key={t.id} className="bg-white border-zinc-200 shadow-sm p-5 hover:border-blue-300 transition-colors dark:bg-zinc-900 dark:border-zinc-800">
                    <div className="flex items-start justify-between mb-2">
                      <div><p className="font-medium text-zinc-900 text-sm dark:text-zinc-100">{t.name}</p><p className="text-xs text-zinc-400">{(t.items || []).length} items</p></div>
                      <button onClick={() => handleDeleteTemplate(t.id)} className="text-zinc-400 hover:text-red-500"><Trash2 size={13} /></button>
                    </div>
                    <Button size="sm" onClick={() => handleStartCustomSheet(t)} className="w-full bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200" data-testid={`pulse-custom-start-${t.id}`}>
                      <ClipboardCheck size={13} className="mr-1" /> Start Check
                    </Button>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* History Tab */}
      {subTab === 'history' && (
        <div className="space-y-3">
          {history.length > 0 ? history.map((entry, idx) => {
            const total = entry.items?.length || 0;
            const checked = (entry.items || []).filter(i => i.checked).length;
            const expanded = expandedHistory === idx;
            return (
              <Card key={idx} className="bg-white border-zinc-200 shadow-sm p-5 cursor-pointer dark:bg-zinc-900 dark:border-zinc-800" onClick={() => setExpandedHistory(expanded ? null : idx)} data-testid={`pulse-history-${idx}`}>
                <div className="flex items-center justify-between">
                  <div><p className="font-medium text-zinc-900 text-sm dark:text-zinc-100">{entry.template_name}</p><p className="text-xs text-zinc-400"><Calendar size={11} className="inline mr-1" />{entry.completed_date} · By: {entry.completed_by}</p></div>
                  <div className="flex items-center gap-2">
                    <Badge className={checked === total ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}>{checked}/{total}</Badge>
                    {expanded ? <ChevronUp size={14} className="text-zinc-400" /> : <ChevronDown size={14} className="text-zinc-400" />}
                  </div>
                </div>
                {expanded && (
                  <div className="mt-3 pt-3 border-t border-zinc-100 space-y-1 dark:border-zinc-800">
                    {(entry.items || []).map((item, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm py-0.5">
                        {item.checked ? <CheckCircle size={13} className="text-emerald-500" /> : <X size={13} className="text-red-400" />}
                        <span className={item.checked ? 'text-zinc-900 dark:text-zinc-100' : 'text-zinc-400'}>{item.name}</span>
                      </div>
                    ))}
                    {entry.notes && <p className="text-xs text-zinc-400 mt-2 pt-2 border-t border-zinc-100 dark:border-zinc-800">Notes: {entry.notes}</p>}
                  </div>
                )}
              </Card>
            );
          }) : <p className="text-center text-zinc-400 py-8 text-sm">No check sheets completed yet</p>}
        </div>
      )}

      {/* Report Tab */}
      {subTab === 'report' && report && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Total Completions', value: report.total_completions, color: 'text-zinc-900 dark:text-zinc-100' },
              { label: 'Last 7 Days', value: report.last_7_days, color: 'text-blue-600' },
              { label: 'Active Staff', value: report.staff_count, color: 'text-zinc-900 dark:text-zinc-100' },
              { label: 'Avg per Staff', value: report.staff_count > 0 ? Math.round(report.total_completions / report.staff_count) : 0, color: 'text-emerald-600' },
            ].map(s => (
              <Card key={s.label} className="bg-white border-zinc-200 shadow-sm p-5 text-center dark:bg-zinc-900 dark:border-zinc-800">
                <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
                <p className="text-xs text-zinc-400">{s.label}</p>
              </Card>
            ))}
          </div>
          <Card className="bg-white border-zinc-200 shadow-sm p-5 dark:bg-zinc-900 dark:border-zinc-800">
            <h3 className="font-semibold text-zinc-900 text-sm mb-3 flex items-center gap-2 dark:text-zinc-100"><Users size={16} className="text-blue-600" /> Staff Breakdown</h3>
            {Object.entries(report.by_staff || {}).map(([name, data]) => (
              <div key={name} className="p-3 bg-zinc-50 rounded-lg border border-zinc-100 mb-2 dark:bg-zinc-900 dark:border-zinc-800">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-zinc-900 text-sm dark:text-zinc-100">{name}</span>
                  <Badge className="bg-blue-50 text-blue-700">{data.count} completions</Badge>
                </div>
                <p className="text-xs text-zinc-400">Last: {data.last_completed?.slice(0, 10) || 'N/A'}</p>
              </div>
            ))}
            {!Object.keys(report.by_staff || {}).length && <p className="text-sm text-zinc-400 text-center py-4">No data yet</p>}
          </Card>
        </div>
      )}
      {subTab === 'report' && !report && <p className="text-center text-zinc-400 py-8 text-sm">No report data available</p>}

      {/* Complete Check Sheet Dialog */}
      <Dialog open={showCompleteDialog} onOpenChange={setShowCompleteDialog}>
        <DialogContent className="bg-white border-zinc-200 text-zinc-900 max-w-lg max-h-[85vh] overflow-y-auto dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800">
          <DialogHeader><DialogTitle>{activeSheet?.equipment_type}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            {activeSheet?.machines?.length > 1 && (
              <div>
                <Label className="text-zinc-700 text-sm">Select Machine</Label>
                <Select value={selectedSerial} onValueChange={setSelectedSerial}>
                  <SelectTrigger className="bg-white border-zinc-200 text-zinc-900 mt-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" data-testid="pulse-sheet-serial"><SelectValue placeholder="Select machine..." /></SelectTrigger>
                  <SelectContent className="bg-white border-zinc-200 dark:bg-zinc-900 dark:border-zinc-800">
                    {(activeSheet.machines || []).map((m, i) => <SelectItem key={i} value={m.serial_number || m.name}>{m.name} {m.serial_number ? `(${m.serial_number})` : ''}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
            {activeSheet?.machines?.length === 1 && (
              <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-3 dark:bg-zinc-900 dark:border-zinc-800">
                <p className="text-xs text-zinc-400 uppercase">Machine</p>
                <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{activeSheet.machines[0].name}</p>
                {activeSheet.machines[0].serial_number && <p className="text-xs text-zinc-400">SN: {activeSheet.machines[0].serial_number}</p>}
              </div>
            )}
            <div>
              <Label className="text-zinc-700 text-sm">Date</Label>
              <Input type="date" value={completionDate} onChange={e => setCompletionDate(e.target.value)} className="bg-white border-zinc-200 text-zinc-900 mt-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" />
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-zinc-500"><span>Check Items</span><span>{Object.values(checkedItems).filter(Boolean).length}/{activeSheet?.items?.length || 0}</span></div>
              {(activeSheet?.items || []).map((item, idx) => (
                <label key={idx} className="flex items-center gap-3 p-3 bg-zinc-50 border border-zinc-200 rounded-lg cursor-pointer hover:border-blue-300 transition-colors dark:bg-zinc-900 dark:border-zinc-800" data-testid={`pulse-check-item-${idx}`}>
                  <input type="checkbox" checked={!!checkedItems[item]} onChange={() => setCheckedItems(p => ({ ...p, [item]: !p[item] }))} className="w-4 h-4 accent-blue-600" />
                  <span className={`text-sm flex-1 ${checkedItems[item] ? 'text-zinc-900 dark:text-zinc-100' : 'text-zinc-500'}`}>{item}</span>
                  {checkedItems[item] && <CheckCircle size={14} className="text-emerald-500" />}
                </label>
              ))}
            </div>
            <div>
              <Label className="text-zinc-700 text-sm">Notes (optional)</Label>
              <Textarea value={completionNotes} onChange={e => setCompletionNotes(e.target.value)} rows={2} placeholder="Any issues noticed..." className="bg-white border-zinc-200 text-zinc-900 mt-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" />
            </div>
            <Button onClick={handleCompleteSheet} className="w-full bg-blue-600 hover:bg-blue-700 text-white" data-testid="pulse-submit-sheet">Submit Completed Sheet</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Template Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="bg-white border-zinc-200 text-zinc-900 max-w-lg dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800">
          <DialogHeader><DialogTitle>Create Custom Check Sheet</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-zinc-700 text-sm">Template Name</Label>
              <Input value={newTemplate.name} onChange={e => setNewTemplate({ ...newTemplate, name: e.target.value })} placeholder="e.g., Swimming Pool Checks" className="bg-white border-zinc-200 text-zinc-900 mt-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" data-testid="pulse-template-name" />
            </div>
            <div>
              <Label className="text-zinc-700 text-sm">Check Items</Label>
              <div className="space-y-2 mt-1">
                {newTemplate.items.map((item, idx) => (
                  <div key={idx} className="flex gap-2">
                    <Input value={item} onChange={e => { const items = [...newTemplate.items]; items[idx] = e.target.value; setNewTemplate({ ...newTemplate, items }); }} placeholder={`Item ${idx + 1}`} className="bg-white border-zinc-200 text-zinc-900 text-sm dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" />
                    {newTemplate.items.length > 1 && <button onClick={() => setNewTemplate({ ...newTemplate, items: newTemplate.items.filter((_, i) => i !== idx) })} className="text-zinc-400 hover:text-red-500"><X size={14} /></button>}
                  </div>
                ))}
              </div>
              <Button size="sm" variant="outline" className="border-zinc-200 text-zinc-600 mt-2 dark:border-zinc-800" onClick={() => setNewTemplate({ ...newTemplate, items: [...newTemplate.items, ''] })}>
                <Plus size={13} className="mr-1" /> Add Item
              </Button>
            </div>
            <Button onClick={handleCreateTemplate} className="w-full bg-blue-600 hover:bg-blue-700 text-white" data-testid="pulse-save-template">Create Template</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default PulseCheckSheetsTab;
