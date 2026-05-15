import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { notify } from '@/components/notifications';
import {
  ClipboardCheck, Plus, Calendar, History, BarChart3, Trash2, Search,
} from 'lucide-react';

import { classifyByName, getTasksForType } from './pulseCheckSheets/constants';
import EquipmentGroupCard from './pulseCheckSheets/EquipmentGroupCard';
import CompleteSheetDialog from './pulseCheckSheets/CompleteSheetDialog';
import CreateTemplateDialog from './pulseCheckSheets/CreateTemplateDialog';
import HistoryList from './pulseCheckSheets/HistoryList';
import Report from './pulseCheckSheets/Report';

const SUB_TABS = [
  { key: 'sheets',  label: 'Check Sheets', icon: ClipboardCheck },
  { key: 'history', label: 'History',      icon: History },
  { key: 'report',  label: 'Report',       icon: BarChart3 },
];

/**
 * Pulse Fitness daily-check-sheets tab. Refactored in iter-216c into
 * focused subcomponents under `./pulseCheckSheets/`. This file owns
 * state + API calls + sub-tab routing only.
 *
 * Multi-machine completion (iter-216bn): when a group has more than one
 * machine, operators can tick multiple machines and we fan out one
 * completion record per ticked machine on submit.
 */
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
  const [selectedSerials, setSelectedSerials] = useState([]);
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

  // Iter 216h126 — refetch on window focus AND poll every 30s while
  // the Check Sheets tab is open. Without this, a check completed on
  // mobile (via the QR scan flow) doesn't turn the serial chip green
  // on the desktop dashboard until the user reloads the page —
  // exactly the regression Jack reported during the Third Space demo.
  useEffect(() => {
    const onFocus = () => loadHistory();
    window.addEventListener('focus', onFocus);
    const id = setInterval(loadHistory, 30000);
    return () => {
      window.removeEventListener('focus', onFocus);
      clearInterval(id);
    };
  }, [loadHistory]);

  const handleStartSheet = (group) => {
    const tasks = getTasksForType(group.equipment_type);
    setActiveSheet({
      name: group.equipment_type,
      equipment_type: group.equipment_type,
      machines: group.machines,
      items: tasks,
    });
    // Default: all machines selected — operator can untick to narrow.
    setSelectedSerials(group.machines.map(m => m.serial_number || m.name));
    setCheckedItems({});
    setCompletionDate(new Date().toISOString().split('T')[0]);
    setCompletionNotes('');
    setShowCompleteDialog(true);
  };

  const handleStartCustomSheet = (template) => {
    setActiveSheet({
      name: template.name,
      equipment_type: 'Custom',
      items: template.items || [],
      template_id: template.id,
      machines: [],
    });
    setSelectedSerials([]);
    setCheckedItems({});
    setCompletionDate(new Date().toISOString().split('T')[0]);
    setCompletionNotes('');
    setShowCompleteDialog(true);
  };

  const handleCompleteSheet = async () => {
    const items = activeSheet.items.map(item => ({ name: item, checked: !!checkedItems[item] }));
    const machines = activeSheet?.machines || [];
    // Multi-machine fan-out: post one completion per ticked machine.
    // Custom templates / single-machine groups use the single-record path.
    const targets = (machines.length > 1 && selectedSerials.length > 0)
      ? selectedSerials
      : (machines.length === 1 ? [machines[0].serial_number || machines[0].name] : ['']);
    if (machines.length > 1 && targets.length === 0) {
      notify.error('Please select at least one machine');
      return;
    }
    try {
      const payloads = targets.map(serial => {
        const sel = machines.find(m => (m.serial_number || m.name) === serial);
        const templateName = sel
          ? `${activeSheet.equipment_type} - ${serial}`
          : activeSheet.name;
        return {
          template_id: sel?.id || activeSheet.template_id || activeSheet.name,
          template_name: templateName,
          serial_number: serial || '',
          equipment_type: activeSheet.equipment_type,
          date: completionDate,
          items,
          notes: completionNotes,
        };
      });
      await Promise.all(payloads.map(p =>
        axios.post(`${API}/check-sheets/complete`, p, { headers })
      ));
      notify.success(`Check sheet completed for ${payloads.length} ${payloads.length === 1 ? 'machine' : 'machines'}`);
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

  // Group equipment by type — explicit `equipment_type` first, then
  // name-based classifier (iter-216bn). Anything still unmatched goes
  // to "Uncategorised" — never the silent "Other" dump.
  const filtered = equipment.filter(e =>
    !searchQuery
    || e.name?.toLowerCase().includes(searchQuery.toLowerCase())
    || (e.serial_number || '').toLowerCase().includes(searchQuery.toLowerCase())
  );
  const grouped = [];
  const typeMap = {};
  for (const eq of filtered) {
    const type = (eq.equipment_type && eq.equipment_type.trim())
      || classifyByName(eq.name)
      || 'Uncategorised';
    if (!typeMap[type]) {
      typeMap[type] = { equipment_type: type, machines: [] };
      grouped.push(typeMap[type]);
    }
    typeMap[type].machines.push(eq);
  }

  const todayStr = new Date().toISOString().split('T')[0];
  const todayHistory = history.filter(h => (h.completed_date || '').startsWith(todayStr));
  const completedTodayNames = new Set(todayHistory.map(h => h.template_name));

  return (
    <div className="space-y-5" data-testid="pulse-check-sheets">
      {/* Sub-tab nav */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex gap-2">
          {SUB_TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setSubTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-all ${
                subTab === tab.key
                  ? 'bg-blue-50 border-blue-200 text-blue-700'
                  : 'bg-white border-zinc-200 text-zinc-500 hover:border-zinc-300 dark:bg-zinc-900 dark:border-zinc-800'
              }`}
              data-testid={`pulse-cs-tab-${tab.key}`}
            >
              <tab.icon size={15} />{tab.label}
            </button>
          ))}
        </div>
        {subTab === 'sheets' && (
          <Button
            size="sm"
            onClick={() => setShowCreateDialog(true)}
            className="bg-blue-600 hover:bg-blue-700 text-white"
            data-testid="pulse-create-template-btn"
          >
            <Plus size={14} className="mr-1" /> Custom Template
          </Button>
        )}
      </div>

      {/* Sheets */}
      {subTab === 'sheets' && (
        <div className="space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" size={16} />
            <Input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search equipment..."
              className="bg-white border-zinc-200 text-zinc-900 pl-10 h-10 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800"
              data-testid="pulse-cs-search"
            />
          </div>

          <Card className="bg-blue-50 border-blue-200 p-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Calendar size={18} className="text-blue-600" />
                <div>
                  <p className="text-zinc-900 font-medium text-sm dark:text-zinc-100">Today's Progress</p>
                  <p className="text-zinc-500 text-xs">{todayStr}</p>
                </div>
              </div>
              <Badge className="bg-blue-100 text-blue-700 border-blue-200" data-testid="pulse-today-progress">
                {todayHistory.length} completed today
              </Badge>
            </div>
          </Card>

          {grouped.map(group => (
            <EquipmentGroupCard
              key={group.equipment_type}
              group={group}
              completedTodayNames={completedTodayNames}
              onStart={handleStartSheet}
            />
          ))}
          {grouped.length === 0 && (
            <p className="text-center text-zinc-400 py-8 text-sm">No equipment found</p>
          )}

          {customTemplates.length > 0 && (
            <div className="mt-4">
              <h3 className="font-semibold text-zinc-900 text-sm mb-3 dark:text-zinc-100">Custom Templates</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {customTemplates.map(t => (
                  <Card key={t.id} className="bg-white border-zinc-200 shadow-sm p-5 hover:border-blue-300 transition-colors dark:bg-zinc-900 dark:border-zinc-800">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <p className="font-medium text-zinc-900 text-sm dark:text-zinc-100">{t.name}</p>
                        <p className="text-xs text-zinc-400">{(t.items || []).length} items</p>
                      </div>
                      <button onClick={() => handleDeleteTemplate(t.id)} className="text-zinc-400 hover:text-red-500">
                        <Trash2 size={13} />
                      </button>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => handleStartCustomSheet(t)}
                      className="w-full bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200"
                      data-testid={`pulse-custom-start-${t.id}`}
                    >
                      <ClipboardCheck size={13} className="mr-1" /> Start Check
                    </Button>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {subTab === 'history' && <HistoryList history={history} />}
      {subTab === 'report' && <Report report={report} />}

      <CompleteSheetDialog
        open={showCompleteDialog}
        onOpenChange={setShowCompleteDialog}
        activeSheet={activeSheet}
        selectedSerials={selectedSerials}
        setSelectedSerials={setSelectedSerials}
        checkedItems={checkedItems}
        setCheckedItems={setCheckedItems}
        completionDate={completionDate}
        setCompletionDate={setCompletionDate}
        completionNotes={completionNotes}
        setCompletionNotes={setCompletionNotes}
        onSubmit={handleCompleteSheet}
      />

      <CreateTemplateDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        newTemplate={newTemplate}
        setNewTemplate={setNewTemplate}
        onSubmit={handleCreateTemplate}
      />
    </div>
  );
};

export default PulseCheckSheetsTab;
