import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import axios from 'axios';
import { notify } from '@/components/notifications';
import {
 ClipboardCheck, Plus, Calendar, CheckCircle, X, History,
 Users, BarChart3, Trash2, Search, ChevronDown, ChevronUp
} from 'lucide-react';

// Iter 216e — task templates + classifier are owned by
// `./pulseCheckSheets/constants.js`. Keeping them centralised stops the
// Operations standalone tab and the Pulse tab drifting apart (which
// already happened once: the Operations copy had `Bike`, `Elliptical`,
// `Leg Press` aliases the Pulse copy was missing).
import { getTasksForType } from './pulseCheckSheets/constants';

const CheckSheetsTab = () => {
 const { _t } = useTranslation();
 const { API, _user } = useAuth();
 const [subTab, setSubTab] = useState('sheets');
 const [equipment, setEquipment] = useState([]);
 const [customTemplates, setCustomTemplates] = useState([]);
 const [showCompleteDialog, setShowCompleteDialog] = useState(false);
 const [showCreateDialog, setShowCreateDialog] = useState(false);
 const [activeSheet, setActiveSheet] = useState(null);
 const [completionDate, setCompletionDate] = useState(new Date().toISOString().split('T')[0]);
 const [completionNotes, setCompletionNotes] = useState('');
 const [checkedItems, setCheckedItems] = useState({});
 const [history, setHistory] = useState([]);
 const [report, setReport] = useState(null);
 const [newTemplate, setNewTemplate] = useState({ name: '', category: '', equipment_type: '', items: [''] });
 const [searchQuery, setSearchQuery] = useState('');
 const [filterType, setFilterType] = useState('all');
 const [expandedHistory, setExpandedHistory] = useState(null);
 const [selectedSerial, setSelectedSerial] = useState('');

 useEffect(() => {
 loadEquipment();
 loadCustomTemplates();
 loadHistory();
 loadReport();
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
 }, []);

 const loadEquipment = async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/equipment`, { headers: { Authorization: `Bearer ${token}` } });
 setEquipment(res.data.equipment || []);
 } catch { setEquipment([]); }
 };

 const loadCustomTemplates = async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/maintenance/templates`, { headers: { Authorization: `Bearer ${token}` } });
 setCustomTemplates(res.data.templates || []);
 } catch {}
 };

 const loadHistory = async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/check-sheets/history`, { headers: { Authorization: `Bearer ${token}` } });
 setHistory(res.data.completions || []);
 } catch {}
 };

 const loadReport = async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/check-sheets/report`, { headers: { Authorization: `Bearer ${token}` } });
 setReport(res.data);
 } catch {}
 };

 const handleStartSheet = (group) => {
 // Iter 222 — a custom template assigned to this equipment type
 // REPLACES the built-in default checklist for the type.
 const assigned = customTemplates.find(t => (t.equipment_type || '') === group.equipment_type);
 const tasks = assigned ? (assigned.items || []) : getTasksForType(group.equipment_type);
 setActiveSheet({
 name: group.equipment_type,
 equipment_type: group.equipment_type,
 machines: group.machines,
 items: tasks,
 template_id: assigned?.id,
 custom_template_name: assigned?.name || null,
 });
 setSelectedSerial(group.machines.length === 1 ? (group.machines[0].serial_number || group.machines[0].name) : '');
 setCheckedItems({});
 setCompletionDate(new Date().toISOString().split('T')[0]);
 setCompletionNotes('');
 setShowCompleteDialog(true);
 };

 const handleStartCustomSheet = (template) => {
 setActiveSheet({
 name: template.name,
 serial_number: '',
 equipment_type: 'Custom',
 items: template.items || [],
 template_id: template.id,
 });
 setCheckedItems({});
 setCompletionDate(new Date().toISOString().split('T')[0]);
 setCompletionNotes('');
 setShowCompleteDialog(true);
 };

 const toggleItem = (item) => {
 setCheckedItems(prev => ({ ...prev, [item]: !prev[item] }));
 };

 const handleCompleteSheet = async () => {
 if (activeSheet?.machines?.length > 1 && !selectedSerial) {
 notify.error('Please select which machine you are checking');
 return;
 }
 const items = activeSheet.items.map(item => ({
 name: item,
 checked: !!checkedItems[item]
 }));
 const selectedMachine = (activeSheet.machines || []).find(m =>
 (m.serial_number || m.name) === selectedSerial
 );
 const templateName = selectedMachine
 ? `${activeSheet.equipment_type} - ${selectedSerial}`
 : activeSheet.name;
 const token = localStorage.getItem('token');
 try {
 await axios.post(`${API}/check-sheets/complete`, {
 template_id: selectedMachine?.id || activeSheet.template_id || activeSheet.name,
 template_name: templateName,
 serial_number: selectedSerial || '',
 equipment_type: activeSheet.equipment_type,
 date: completionDate,
 items,
 notes: completionNotes
 }, { headers: { Authorization: `Bearer ${token}` } });
 notify.success(`Check sheet completed for ${templateName}`);
 setShowCompleteDialog(false);
 loadHistory();
 loadReport();
 } catch {
 notify.error('Failed to save completion');
 }
 };

 const handleCreateTemplate = async () => {
 if (!newTemplate.name.trim()) { notify.error('Enter a template name'); return; }
 const items = newTemplate.items.filter(i => i.trim());
 if (items.length === 0) { notify.error('Add at least one item'); return; }
 const token = localStorage.getItem('token');
 try {
 await axios.post(`${API}/maintenance/templates`, {
 name: newTemplate.name,
 category: newTemplate.category || 'Custom',
 equipment_type: newTemplate.equipment_type === 'none' ? '' : (newTemplate.equipment_type || ''),
 items
 }, { headers: { Authorization: `Bearer ${token}` } });
 notify.success(newTemplate.equipment_type && newTemplate.equipment_type !== 'none'
 ? `Template created — now the default for ${newTemplate.equipment_type}`
 : 'Template created');
 setShowCreateDialog(false);
 setNewTemplate({ name: '', category: '', equipment_type: '', items: [''] });
 loadCustomTemplates();
 } catch {
 notify.error('Failed to create template');
 }
 };

 const handleDeleteTemplate = async (id) => {
 const token = localStorage.getItem('token');
 try {
 await axios.delete(`${API}/maintenance/templates/${id}`, { headers: { Authorization: `Bearer ${token}` } });
 setCustomTemplates(customTemplates.filter(t => t.id !== id));
 notify.success('Template deleted');
 } catch { notify.error('Failed to delete'); }
 };

 const equipmentTypes = [...new Set(equipment.map(e => e.equipment_type).filter(Boolean))];

 const filteredEquipment = equipment
 .filter(e => filterType === 'all' || e.equipment_type === filterType)
 .filter(e => !searchQuery || e.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
 (e.serial_number || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
 (e.equipment_type || '').toLowerCase().includes(searchQuery.toLowerCase()));

 // Group equipment by type
 const groupedEquipment = [];
 const typeMap = {};
 for (const equip of filteredEquipment) {
 const type = equip.equipment_type || 'Other';
 if (!typeMap[type]) {
 typeMap[type] = { equipment_type: type, machines: [] };
 groupedEquipment.push(typeMap[type]);
 }
 typeMap[type].machines.push(equip);
 }

 const todayStr = new Date().toISOString().split('T')[0];
 const todayHistory = history.filter(h => (h.completed_date || '').startsWith(todayStr));
 const completedTodayNames = new Set(todayHistory.map(h => h.template_name));

 // Count how many individual machines were checked today
 const machinesCheckedToday = equipment.filter(e => {
 const serialKey = `${e.equipment_type} - ${e.serial_number || e.name}`;
 return completedTodayNames.has(serialKey) || completedTodayNames.has(e.name);
 }).length;

 return (
 <div className="space-y-6" data-testid="checksheets-tab">
 <div className="flex items-center justify-between flex-wrap gap-3">
 <div className="flex gap-3 flex-wrap">
 {[
 { key: 'sheets', label: 'Check Sheets', icon: ClipboardCheck },
 { key: 'history', label: 'History', icon: History },
 { key: 'report', label: 'Completion Report', icon: BarChart3 },
 ].map(tab => (
 <button
 key={tab.key}
 onClick={() => setSubTab(tab.key)}
 className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-all ${
 subTab === tab.key ? 'bg-[rgb(var(--rgb-brand-blue)/0.1)] border-[rgb(var(--rgb-brand-blue)/0.5)] text-[var(--color-brand-blue)]' : 'bg-[var(--theme-surface)] border-white/10 text-[var(--color-text-muted)] hover:border-white/20'
 }`}
 data-testid={`cs-tab-${tab.key}`}
 >
 <tab.icon size={16} /> {tab.label}
 </button>
 ))}
 </div>
 {subTab === 'sheets' && (
 <Button onClick={() => setShowCreateDialog(true)} className="bg-[var(--color-brand-blue)] text-white" data-testid="create-template-btn">
 <Plus size={16} className="mr-1" /> Custom Template
 </Button>
 )}
 </div>

 {/* Equipment-Based Check Sheets */}
 {subTab === 'sheets' && (
 <div className="space-y-4">
 {/* Filters */}
 <div className="flex flex-col sm:flex-row gap-3">
 <div className="relative flex-1">
 <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" size={16} />
 <Input
 value={searchQuery}
 onChange={e => setSearchQuery(e.target.value)}
 placeholder="Search equipment by name or serial number..."
 className="bg-[var(--theme-surface)] border-white/10 text-white pl-10"
 data-testid="cs-search-input"
 />
 </div>
 <Select value={filterType} onValueChange={setFilterType}>
 <SelectTrigger className="w-full sm:w-48 bg-[var(--theme-surface)] border-white/10 text-white" data-testid="cs-filter-type">
 <SelectValue placeholder="All Types" />
 </SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-white/10">
 <SelectItem value="all" className="text-white">All Types</SelectItem>
 {equipmentTypes.map(type => (
 <SelectItem key={type} value={type} className="text-white">{type}</SelectItem>
 ))}
 </SelectContent>
 </Select>
 </div>

 {/* Today's Progress */}
 <Card className="bg-[rgb(var(--rgb-brand-blue)/0.05)] border-[rgb(var(--rgb-brand-blue)/0.2)] p-5">
 <div className="flex items-center justify-between">
 <div className="flex items-center gap-3">
 <Calendar size={20} className="text-[var(--color-brand-blue)]" />
 <div>
 <p className="text-white font-medium text-sm">Today's Progress</p>
 <p className="text-[var(--color-text-muted)] text-xs">{todayStr}</p>
 </div>
 </div>
 <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)]" data-testid="today-progress-badge">
 {machinesCheckedToday} / {equipment.length} machines checked
 </Badge>
 </div>
 </Card>

 {/* Grouped Equipment Cards */}
 {groupedEquipment.length > 0 ? (
 <div className="space-y-4">
 {groupedEquipment.map((group) => {
 const assignedTemplate = customTemplates.find(t => (t.equipment_type || '') === group.equipment_type);
 const tasks = assignedTemplate ? (assignedTemplate.items || []) : getTasksForType(group.equipment_type);
 const checkedSerials = group.machines.filter(m => {
 const key = `${group.equipment_type} - ${m.serial_number || m.name}`;
 return completedTodayNames.has(key) || completedTodayNames.has(m.name);
 });
 const allDone = checkedSerials.length === group.machines.length;
 return (
 <Card
 key={group.equipment_type}
 className={`bg-[var(--theme-surface)] border-white/10 p-5 transition-colors ${allDone ? 'border-green-500/30' : 'hover:border-[rgb(var(--rgb-brand-blue)/0.3)]'}`}
 data-testid={`equip-group-${group.equipment_type}`}
 >
 <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
 {/* Left: Type header + serial numbers */}
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-3 mb-2">
 <h3 className="text-white font-semibold text-base">{group.equipment_type}</h3>
 <Badge className="bg-white/10 text-[var(--color-text-muted)] text-xs">
 {group.machines.length} {group.machines.length === 1 ? 'machine' : 'machines'}
 </Badge>
 {allDone && (
 <Badge className="bg-green-500/20 text-green-400 text-xs">
 <CheckCircle size={12} className="mr-1" /> All Done
 </Badge>
 )}
 {!allDone && checkedSerials.length > 0 && (
 <Badge className="bg-yellow-500/20 text-yellow-400 text-xs">
 {checkedSerials.length}/{group.machines.length} checked
 </Badge>
 )}
 {assignedTemplate && (
 <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)] text-xs" data-testid={`custom-assigned-${group.equipment_type}`}>
 <ClipboardCheck size={11} className="mr-1" /> {assignedTemplate.name}
 </Badge>
 )}
 </div>

 {/* Serial Numbers */}
 <div className="mb-2">
 <p className="text-[var(--color-text-muted)] text-xs font-medium uppercase tracking-wider mb-1">Serial Numbers</p>
 <div className="flex flex-wrap gap-1.5">
 {group.machines.map((m, i) => {
 const sn = m.serial_number || m.name;
 const isChecked = completedTodayNames.has(`${group.equipment_type} - ${sn}`) || completedTodayNames.has(m.name);
 return (
 <span
 key={i}
 className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border ${
 isChecked
 ? 'bg-green-500/10 border-green-500/30 text-green-400'
 : 'bg-[var(--color-ink-alt)] border-white/10 text-[var(--color-text-muted)]'
 }`}
 data-testid={`sn-badge-${sn}`}
 >
 {isChecked && <CheckCircle size={10} />}
 {sn}
 </span>
 );
 })}
 </div>
 </div>

 {/* Task preview */}
 <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-[var(--color-text-muted)]">
 {tasks.slice(0, 3).map((task, i) => (
 <span key={i} className="flex items-center gap-1">
 <span className="w-1 h-1 rounded-full bg-[var(--color-brand-blue)]" />{task}
 </span>
 ))}
 {tasks.length > 3 && <span className="text-[var(--color-brand-blue)]">+{tasks.length - 3} more</span>}
 </div>
 </div>

 {/* Right: Start Check button */}
 <Button
 className={`flex-shrink-0 ${allDone
 ? 'bg-green-500/10 hover:bg-green-500/20 text-green-400 border border-green-500/30'
 : ''
 }`}
 onClick={() => handleStartSheet(group)}
 data-testid={`start-group-${group.equipment_type}`}
 >
 <ClipboardCheck size={16} className="mr-2" />
 {allDone ? 'Check Again' : 'Start Check'}
 </Button>
 </div>
 </Card>
 );
 })}
 </div>
 ) : (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-12 text-center">
 <ClipboardCheck size={48} className="mx-auto mb-4 text-[var(--color-text-muted)]" />
 <p className="text-[var(--color-text-muted)]">
 {equipment.length === 0
 ? 'No equipment added yet. Add equipment in the Equipment tab first.'
 : 'No equipment matches your search.'}
 </p>
 </Card>
 )}

 {/* Custom Templates Section */}
 {customTemplates.length > 0 && (
 <div className="mt-6">
 <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
 <ClipboardCheck size={18} className="text-[var(--color-brand-blue)]" /> Custom Templates
 </h3>
 <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
 {customTemplates.map((template, idx) => (
 <Card key={template.id || idx} className="bg-[var(--theme-surface)] border-white/10 p-5 hover:border-[rgb(var(--rgb-brand-blue)/0.3)] transition-colors" data-testid={`custom-template-${idx}`}>
 <div className="flex items-start justify-between mb-3">
 <div>
 <h3 className="text-white font-semibold">{template.name}</h3>
 <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)] text-xs mt-1">
 Custom | {(template.items || []).length} items
 </Badge>
 {template.equipment_type && (
 <Badge className="bg-emerald-500/15 text-emerald-400 text-xs mt-1 ml-1" data-testid={`custom-template-type-${idx}`}>
 {template.equipment_type}
 </Badge>
 )}
 </div>
 <button onClick={() => handleDeleteTemplate(template.id)} className="text-red-400 hover:text-red-300">
 <Trash2 size={14} />
 </button>
 </div>
 <ul className="space-y-1 mb-4 text-sm text-[var(--color-text-muted)] max-h-24 overflow-y-auto">
 {(template.items || []).slice(0, 4).map((item, i) => (
 <li key={i} className="flex items-center gap-2">
 <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-brand-blue)]" />{item}
 </li>
 ))}
 {(template.items || []).length > 4 && (
 <li className="text-[var(--color-brand-blue)] text-xs">+{(template.items || []).length - 4} more</li>
 )}
 </ul>
 <Button
 size="sm"
 className="w-full bg-[rgb(var(--rgb-brand-blue)/0.1)] hover:bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)] border border-[rgb(var(--rgb-brand-blue)/0.3)]"
 onClick={() => handleStartCustomSheet(template)}
 data-testid={`start-custom-${idx}`}
 >
 <ClipboardCheck size={14} className="mr-1" /> Start Check
 </Button>
 </Card>
 ))}
 </div>
 </div>
 )}
 </div>
 )}

 {/* History */}
 {subTab === 'history' && (
 <div className="space-y-3">
 {history.length > 0 ? history.map((entry, idx) => {
 const totalItems = entry.items?.length || 0;
 const checkedCount = (entry.items || []).filter(i => i.checked).length;
 const isExpanded = expandedHistory === idx;
 return (
 <Card key={idx} className="bg-[var(--theme-surface)] border-white/10 p-5" data-testid={`history-entry-${idx}`}>
 <div
 className="flex items-center justify-between cursor-pointer"
 onClick={() => setExpandedHistory(isExpanded ? null : idx)}
 >
 <div>
 <p className="text-white font-medium">{entry.template_name}</p>
 <p className="text-[var(--color-text-muted)] text-sm">
 <Calendar size={12} className="inline mr-1" />{entry.completed_date} | By: {entry.completed_by}
 </p>
 </div>
 <div className="flex items-center gap-3">
 <Badge className={checkedCount === totalItems ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}>
 {checkedCount}/{totalItems} completed
 </Badge>
 {isExpanded ? <ChevronUp size={16} className="text-[var(--color-text-muted)]" /> : <ChevronDown size={16} className="text-[var(--color-text-muted)]" />}
 </div>
 </div>
 {isExpanded && (
 <div className="mt-3 pt-3 border-t border-white/10 space-y-1">
 {(entry.items || []).map((item, i) => (
 <div key={i} className="flex items-center gap-2 text-sm py-1">
 {item.checked
 ? <CheckCircle size={14} className="text-green-400 flex-shrink-0" />
 : <X size={14} className="text-red-400 flex-shrink-0" />
 }
 <span className={item.checked ? 'text-white' : 'text-[var(--color-text-muted)]'}>{item.name}</span>
 </div>
 ))}
 {entry.notes && <p className="text-[var(--color-text-muted)] text-sm mt-2 pt-2 border-t border-white/10">Notes: {entry.notes}</p>}
 </div>
 )}
 </Card>
 );
 }) : (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-12 text-center">
 <History size={48} className="mx-auto mb-4 text-[var(--color-text-muted)]" />
 <p className="text-[var(--color-text-muted)]">No check sheets completed yet</p>
 </Card>
 )}
 </div>
 )}

 {/* Manager Report */}
 {subTab === 'report' && (
 <div className="space-y-6">
 {report ? (
 <>
 <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5 text-center" data-testid="report-total">
 <p className="text-3xl font-bold text-white">{report.total_completions}</p>
 <p className="text-[var(--color-text-muted)] text-sm">Total Completions</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5 text-center" data-testid="report-7days">
 <p className="text-3xl font-bold text-[var(--color-brand-blue)]">{report.last_7_days}</p>
 <p className="text-[var(--color-text-muted)] text-sm">Last 7 Days</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5 text-center" data-testid="report-staff">
 <p className="text-3xl font-bold text-white">{report.staff_count}</p>
 <p className="text-[var(--color-text-muted)] text-sm">Active Staff</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5 text-center" data-testid="report-avg">
 <p className="text-3xl font-bold text-green-400">
 {report.staff_count > 0 ? Math.round(report.total_completions / report.staff_count) : 0}
 </p>
 <p className="text-[var(--color-text-muted)] text-sm">Avg per Staff</p>
 </Card>
 </div>

 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="staff-breakdown">
 <h3 className="text-white font-semibold mb-4 flex items-center gap-2"><Users size={18} className="text-[var(--color-brand-blue)]" /> Staff Completion Breakdown</h3>
 {Object.keys(report.by_staff || {}).length > 0 ? (
 <div className="space-y-3">
 {Object.entries(report.by_staff).map(([name, data]) => (
 <div key={name} className="p-3 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <div className="flex items-center justify-between mb-2">
 <span className="text-white font-medium">{name}</span>
 <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)]">{data.count} completions</Badge>
 </div>
 <p className="text-[var(--color-text-muted)] text-xs">Last completed: {data.last_completed?.slice(0, 10) || 'N/A'}</p>
 <div className="flex flex-wrap gap-1 mt-2">
 {Object.entries(data.sheets || {}).map(([sheet, cnt]) => (
 <Badge key={sheet} className="bg-white/5 text-[var(--color-text-muted)] text-xs">{sheet}: {cnt}</Badge>
 ))}
 </div>
 </div>
 ))}
 </div>
 ) : (
 <p className="text-[var(--color-text-muted)] text-center py-4">No staff completion data yet</p>
 )}
 </Card>
 </>
 ) : (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-12 text-center">
 <BarChart3 size={48} className="mx-auto mb-4 text-[var(--color-text-muted)]" />
 <p className="text-[var(--color-text-muted)]">No report data available yet</p>
 </Card>
 )}
 </div>
 )}

 {/* Complete Check Sheet Dialog */}
 <Dialog open={showCompleteDialog} onOpenChange={setShowCompleteDialog}>
 <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white max-w-lg max-h-[85vh] overflow-y-auto" data-testid="complete-sheet-dialog">
 <DialogHeader>
 <DialogTitle className="text-white text-lg">{activeSheet?.equipment_type}</DialogTitle>
 <p className="text-[var(--color-text-muted)] text-sm">{activeSheet?.machines?.length || 0} machines in this group</p>
 </DialogHeader>
 <div className="space-y-4">
 {/* Serial Number Selector */}
 {activeSheet?.machines?.length > 1 && (
 <div>
 <Label className="text-white text-sm">Serial Number / Machine</Label>
 <Select value={selectedSerial} onValueChange={setSelectedSerial}>
 <SelectTrigger className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="sheet-serial-select">
 <SelectValue placeholder="Select which machine you are checking" />
 </SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-white/10">
 {(activeSheet.machines || []).map((m, i) => (
 <SelectItem key={i} value={m.serial_number || m.name} className="text-white">
 {m.name} {m.serial_number ? `(${m.serial_number})` : ''}
 </SelectItem>
 ))}
 </SelectContent>
 </Select>
 </div>
 )}
 {activeSheet?.machines?.length === 1 && (
 <div className="bg-[var(--color-ink-alt)] border border-white/10 rounded-lg p-3">
 <p className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider">Machine</p>
 <p className="text-white text-sm font-medium">{activeSheet.machines[0].name}</p>
 {activeSheet.machines[0].serial_number && (
 <p className="text-[var(--color-text-muted)] text-xs">SN: {activeSheet.machines[0].serial_number}</p>
 )}
 </div>
 )}

 <div>
 <Label className="text-white text-sm">Date</Label>
 <Input type="date" value={completionDate} onChange={e => setCompletionDate(e.target.value)} className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="sheet-date-input" />
 </div>
 <div className="space-y-2">
 <div className="flex items-center justify-between text-sm text-[var(--color-text-muted)] mb-1">
 <span>Check Items</span>
 <span>{Object.values(checkedItems).filter(Boolean).length}/{activeSheet?.items?.length || 0} done</span>
 </div>
 {(activeSheet?.items || []).map((item, idx) => (
 <label key={idx} className="flex items-center gap-3 p-3 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg cursor-pointer hover:border-[rgb(var(--rgb-brand-blue)/0.3)] transition-colors" data-testid={`check-item-${idx}`}>
 <input type="checkbox" checked={!!checkedItems[item]} onChange={() => toggleItem(item)} className="w-4 h-4 accent-[var(--color-brand-blue)]" />
 <span className={`text-sm flex-1 ${checkedItems[item] ? 'text-white' : 'text-[var(--color-text-muted)]'}`}>{item}</span>
 {checkedItems[item] && <CheckCircle size={14} className="text-green-400" />}
 </label>
 ))}
 </div>
 <div>
 <Label className="text-white text-sm">Notes (optional)</Label>
 <Textarea value={completionNotes} onChange={e => setCompletionNotes(e.target.value)} rows={2} placeholder="Any issues noticed during check..." className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="sheet-notes-input" />
 </div>
 <div className="flex justify-between items-center pt-2">
 <span className="text-[var(--color-text-muted)] text-sm">
 {Object.values(checkedItems).filter(Boolean).length}/{activeSheet?.items?.length || 0} items checked
 </span>
 <Button onClick={handleCompleteSheet} className="bg-[var(--color-brand-blue)] text-white" data-testid="submit-sheet-btn">
 Submit Completed Sheet
 </Button>
 </div>
 </div>
 </DialogContent>
 </Dialog>

 {/* Create Custom Template Dialog */}
 <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
 <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white max-w-lg" data-testid="create-template-dialog">
 <DialogHeader>
 <DialogTitle className="text-white">Create Custom Check Sheet</DialogTitle>
 </DialogHeader>
 <div className="space-y-4">
 <div>
 <Label className="text-white text-sm">Template Name</Label>
 <Input value={newTemplate.name} onChange={e => setNewTemplate({ ...newTemplate, name: e.target.value })} placeholder="e.g., Swimming Pool Checks" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="template-name-input" />
 </div>
 <div>
 <Label className="text-white text-sm">Category</Label>
 <Input value={newTemplate.category} onChange={e => setNewTemplate({ ...newTemplate, category: e.target.value })} placeholder="e.g., Facility, Pool, Custom" className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="template-category-input" />
 </div>
 <div>
 <Label className="text-white text-sm">Applies to equipment type</Label>
 <Select value={newTemplate.equipment_type || 'none'} onValueChange={v => setNewTemplate({ ...newTemplate, equipment_type: v })}>
 <SelectTrigger className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1" data-testid="template-equipment-type-select">
 <SelectValue placeholder="Any (general template)" />
 </SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-white/10 max-h-60">
 <SelectItem value="none" className="text-white">Any — general template</SelectItem>
 {equipmentTypes.map(type => (
 <SelectItem key={type} value={type} className="text-white">{type}</SelectItem>
 ))}
 </SelectContent>
 </Select>
 <p className="text-[var(--color-text-muted)] text-xs mt-1">When set, this replaces the built-in default checklist for that equipment type.</p>
 </div>
 <div>
 <Label className="text-white text-sm">Check Items</Label>
 <div className="space-y-2 mt-1">
 {newTemplate.items.map((item, idx) => (
 <div key={idx} className="flex gap-2">
 <Input value={item} onChange={e => {
 const items = [...newTemplate.items];
 items[idx] = e.target.value;
 setNewTemplate({ ...newTemplate, items });
 }} placeholder={`Item ${idx + 1}`} className="bg-[var(--color-ink-alt)] border-white/10 text-white text-sm" data-testid={`template-item-${idx}`} />
 {newTemplate.items.length > 1 && (
 <button onClick={() => setNewTemplate({ ...newTemplate, items: newTemplate.items.filter((_, i) => i !== idx) })} className="text-red-400"><X size={14} /></button>
 )}
 </div>
 ))}
 </div>
 <Button size="sm" variant="outline" className="border-white/10 text-[var(--color-text-muted)] mt-2" onClick={() => setNewTemplate({ ...newTemplate, items: [...newTemplate.items, ''] })} data-testid="add-template-item-btn">
 <Plus size={14} className="mr-1" /> Add Item
 </Button>
 </div>
 <Button onClick={handleCreateTemplate} className="w-full bg-[var(--color-brand-blue)] text-white" data-testid="save-template-btn">Create Template</Button>
 </div>
 </DialogContent>
 </Dialog>
 </div>
 );
};

export default CheckSheetsTab;
