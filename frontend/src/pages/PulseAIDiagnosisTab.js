import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';

import axios from 'axios';
import { notify } from '@/components/notifications';
import {
  Brain, Send, Loader2, FileText, Clock, ChevronDown, ChevronUp
} from 'lucide-react';

const EQUIPMENT_TYPES = ['Treadmill', 'Exercise Bike', 'Cross Trainer', 'Rowing Machine', 'Spin Bike', 'Strength Equipment', 'Free Weights', 'StepMill', 'Cable Machine'];

const PulseAIDiagnosisTab = ({ equipment }) => {
  const { API, user } = useAuth();
  // Iter 220n — brand-aware copy. Pulse customers see "AI Fault
  // Diagnosis"; Pulse Fitness ops customers see "AI Triage". Same component,
  // same backend — just the user-facing language matches the brand.
  const isPulseAccount = user?.account_type === 'pulse_pro' || user?.account_type === 'lite';
  const COPY = isPulseAccount
    ? { hero: 'AI Fault Diagnosis', tab: 'Fault Diagnosis',
        sub: 'Describe a fault and our AI will help diagnose the issue and suggest repairs.' }
    : { hero: 'AI Triage', tab: 'AI Triage',
        sub: 'Describe a fault and our AI will triage the issue, suggest likely causes, and recommend next steps.' };
  const [subTab, setSubTab] = useState('chat');
  const [chatHistory, setChatHistory] = useState([]);
  const [chatMessage, setChatMessage] = useState('');
  const [chatMachineType, setChatMachineType] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [auditHistory, setAuditHistory] = useState([]);
  const [auditForm, setAuditForm] = useState({ equipment_type: '', equipment_id: '', usage_frequency: '', last_maintenance: '', notes: '' });
  const [auditLoading, setAuditLoading] = useState(false);
  const [expandedAudit, setExpandedAudit] = useState(null);
  const chatEndRef = useRef(null);
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const loadAudits = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/audit/history`, { headers });
      setAuditHistory(res.data.audits || []);
    } catch (err) { console.error('Failed to load audit history:', err); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: context helpers re-create each render but read the latest token / handler at call time; adding them would invalidate the memo every render and break the optimisation.
  }, [API]);

  useEffect(() => { loadAudits(); }, [loadAudits]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chatHistory]);

  const handleChatSubmit = async (e) => {
    e.preventDefault();
    if (!chatMessage.trim() || !chatMachineType) { notify.error('Select a machine type and enter a message'); return; }
    setChatLoading(true);
    const contextMsg = `[${chatMachineType}] ${chatMessage}`;
    setChatHistory(prev => [...prev, { role: 'user', content: chatMessage }]);
    setChatMessage('');
    try {
      const res = await axios.post(`${API}/chat/diagnose`, { message: contextMsg }, { headers });
      setChatHistory(prev => [...prev, { role: 'assistant', content: res.data.response }]);
    } catch { notify.error('AI diagnosis failed'); }
    setChatLoading(false);
  };

  const handleAuditSubmit = async (e) => {
    e.preventDefault();
    if (!auditForm.equipment_type) { notify.error('Select an equipment type'); return; }
    setAuditLoading(true);
    try {
      const res = await axios.post(`${API}/audit/generate`, auditForm, { headers });
      notify.success('Audit report generated');
      setAuditHistory([res.data, ...auditHistory]);
      setAuditForm({ equipment_type: '', equipment_id: '', usage_frequency: '', last_maintenance: '', notes: '' });
    } catch { notify.error('Failed to generate audit'); }
    setAuditLoading(false);
  };

  return (
    <div className="space-y-5" data-testid="pulse-ai-diagnosis">
      {/* Sub-tabs */}
      <div className="flex gap-2">
        {[{ key: 'chat', label: COPY.tab, icon: Brain }, { key: 'audit', label: 'Audit Reports', icon: FileText }].map(tab => (
          <button key={tab.key} onClick={() => setSubTab(tab.key)} className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-all ${subTab === tab.key ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-white border-zinc-200 text-zinc-500 hover:border-zinc-300 dark:bg-zinc-900 dark:border-zinc-800'}`} data-testid={`pulse-ai-tab-${tab.key}`}>
            <tab.icon size={15} />{tab.label}
          </button>
        ))}
      </div>

      {/* Chat Tab */}
      {subTab === 'chat' && (
        <div className="max-w-2xl mx-auto space-y-4">
          <Card className="bg-blue-50 border-blue-200 p-5">
            <div className="flex items-center gap-3">
              <Brain size={20} className="text-blue-600" />
              <div><p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{COPY.hero}</p><p className="text-xs text-zinc-500">{COPY.sub}</p></div>
            </div>
          </Card>

          {/* Machine Type Selector */}
          <div>
            <Label className="text-zinc-700 text-sm">Equipment Type</Label>
            <Select value={chatMachineType} onValueChange={setChatMachineType}>
              <SelectTrigger className="bg-white border-zinc-200 text-zinc-900 mt-1 h-11 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" data-testid="pulse-ai-machine-type"><SelectValue placeholder="Select equipment type..." /></SelectTrigger>
              <SelectContent className="bg-white border-zinc-200 max-h-60 dark:bg-zinc-900 dark:border-zinc-800">
                {EQUIPMENT_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                {/* Add types from actual equipment */}
                {[...new Set(equipment.map(e => e.equipment_type).filter(t => t && !EQUIPMENT_TYPES.includes(t)))].map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          {/* Chat Messages */}
          <Card className="bg-white border-zinc-200 shadow-sm overflow-hidden dark:bg-zinc-900 dark:border-zinc-800">
            <div className="max-h-[400px] overflow-y-auto p-4 space-y-3" data-testid="pulse-ai-chat-area">
              {chatHistory.length === 0 && (
                <div className="text-center py-8">
                  <Brain size={32} className="text-zinc-300 mx-auto mb-2" />
                  <p className="text-zinc-400 text-sm">Start a conversation about an equipment fault</p>
                </div>
              )}
              {chatHistory.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100'}`} data-testid={`pulse-ai-msg-${i}`}>
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div className="flex justify-start">
                  <div className="bg-zinc-100 rounded-xl px-4 py-3 text-sm text-zinc-500 flex items-center gap-2 dark:bg-zinc-800">
                    <Loader2 size={14} className="animate-spin" /> Diagnosing...
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            <form onSubmit={handleChatSubmit} className="border-t border-zinc-100 p-3 flex gap-2 dark:border-zinc-800">
              <Input value={chatMessage} onChange={e => setChatMessage(e.target.value)} placeholder="Describe the fault..." className="bg-zinc-50 border-zinc-200 text-zinc-900 flex-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" disabled={chatLoading} data-testid="pulse-ai-chat-input" />
              <Button type="submit" disabled={chatLoading || !chatMessage.trim() || !chatMachineType} className="bg-blue-600 hover:bg-blue-700 text-white px-4" data-testid="pulse-ai-chat-send">
                {chatLoading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              </Button>
            </form>
          </Card>

          {chatHistory.length > 0 && (
            <Button variant="outline" size="sm" className="border-zinc-200 text-zinc-500 dark:border-zinc-800" onClick={() => setChatHistory([])} data-testid="pulse-ai-clear-chat">
              Clear Conversation
            </Button>
          )}
        </div>
      )}

      {/* Audit Tab */}
      {subTab === 'audit' && (
        <div className="space-y-5">
          <Card className="bg-white border-zinc-200 shadow-sm p-5 max-w-xl mx-auto dark:bg-zinc-900 dark:border-zinc-800" data-testid="pulse-audit-form">
            <h3 className="font-semibold text-zinc-900 mb-4 flex items-center gap-2 dark:text-zinc-100"><FileText size={18} className="text-blue-600" /> Generate Audit Report</h3>
            <form onSubmit={handleAuditSubmit} className="space-y-4">
              <div>
                <Label className="text-zinc-700 text-sm">Equipment Type</Label>
                <Select value={auditForm.equipment_type} onValueChange={v => setAuditForm({ ...auditForm, equipment_type: v })}>
                  <SelectTrigger className="bg-white border-zinc-200 text-zinc-900 mt-1 h-11 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" data-testid="pulse-audit-type"><SelectValue placeholder="Select type..." /></SelectTrigger>
                  <SelectContent className="bg-white border-zinc-200 max-h-60 dark:bg-zinc-900 dark:border-zinc-800">
                    {EQUIPMENT_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                    {[...new Set(equipment.map(e => e.equipment_type).filter(t => t && !EQUIPMENT_TYPES.includes(t)))].map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-zinc-700 text-sm">Specific Machine (optional)</Label>
                <Select value={auditForm.equipment_id} onValueChange={v => setAuditForm({ ...auditForm, equipment_id: v })}>
                  <SelectTrigger className="bg-white border-zinc-200 text-zinc-900 mt-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" data-testid="pulse-audit-machine"><SelectValue placeholder="Select machine..." /></SelectTrigger>
                  <SelectContent className="bg-white border-zinc-200 max-h-60 dark:bg-zinc-900 dark:border-zinc-800">
                    <SelectItem value=" ">None — General audit</SelectItem>
                    {equipment.filter(e => !auditForm.equipment_type || e.equipment_type === auditForm.equipment_type).map(e => (
                      <SelectItem key={e.id} value={e.id}>{e.name} {e.serial_number ? `(${e.serial_number})` : ''}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-zinc-700 text-sm">Usage Frequency</Label>
                  <Select value={auditForm.usage_frequency} onValueChange={v => setAuditForm({ ...auditForm, usage_frequency: v })}>
                    <SelectTrigger className="bg-white border-zinc-200 text-zinc-900 mt-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" data-testid="pulse-audit-usage"><SelectValue placeholder="Select..." /></SelectTrigger>
                    <SelectContent className="bg-white border-zinc-200 dark:bg-zinc-900 dark:border-zinc-800">
                      <SelectItem value="Light (1-3 hours/day)">Light</SelectItem>
                      <SelectItem value="Moderate (4-8 hours/day)">Moderate</SelectItem>
                      <SelectItem value="Heavy (8+ hours/day)">Heavy</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-zinc-700 text-sm">Last Maintenance</Label>
                  <Input type="date" value={auditForm.last_maintenance} onChange={e => setAuditForm({ ...auditForm, last_maintenance: e.target.value })} className="bg-white border-zinc-200 text-zinc-900 mt-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" data-testid="pulse-audit-date" />
                </div>
              </div>
              <div>
                <Label className="text-zinc-700 text-sm">Additional Notes</Label>
                <Textarea value={auditForm.notes} onChange={e => setAuditForm({ ...auditForm, notes: e.target.value })} rows={2} placeholder="Any specific concerns..." className="bg-white border-zinc-200 text-zinc-900 mt-1 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800" data-testid="pulse-audit-notes" />
              </div>
              <Button type="submit" disabled={auditLoading || !auditForm.equipment_type} className="w-full bg-blue-600 hover:bg-blue-700 text-white h-11" data-testid="pulse-audit-submit">
                {auditLoading ? <><Loader2 size={16} className="animate-spin mr-2" /> Generating...</> : <><Brain size={16} className="mr-2" /> Generate Audit Report</>}
              </Button>
            </form>
          </Card>

          {/* Audit History */}
          <div>
            <h3 className="font-semibold text-zinc-900 text-sm mb-3 dark:text-zinc-100">Audit History ({auditHistory.length})</h3>
            {auditHistory.length > 0 ? (
              <div className="space-y-3">
                {auditHistory.map((audit, i) => {
                  const expanded = expandedAudit === i;
                  return (
                    <Card key={audit.id || i} className="bg-white border-zinc-200 shadow-sm overflow-hidden dark:bg-zinc-900 dark:border-zinc-800" data-testid={`pulse-audit-${i}`}>
                      <div className="p-4 flex items-center justify-between cursor-pointer" onClick={() => setExpandedAudit(expanded ? null : i)}>
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center"><FileText size={16} className="text-blue-600" /></div>
                          <div>
                            <p className="font-medium text-zinc-900 text-sm dark:text-zinc-100">{audit.equipment_name || audit.equipment_type}</p>
                            <p className="text-xs text-zinc-400"><Clock size={10} className="inline mr-1" />{audit.created_at?.slice(0, 10)}</p>
                          </div>
                        </div>
                        {expanded ? <ChevronUp size={16} className="text-zinc-400" /> : <ChevronDown size={16} className="text-zinc-400" />}
                      </div>
                      {expanded && (
                        <div className="px-4 pb-4 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                          <div className="bg-zinc-50 border border-zinc-100 rounded-lg p-4 text-sm text-zinc-700 whitespace-pre-wrap max-h-[400px] overflow-y-auto dark:bg-zinc-900 dark:border-zinc-800" data-testid={`pulse-audit-report-${i}`}>
                            {audit.report}
                          </div>
                        </div>
                      )}
                    </Card>
                  );
                })}
              </div>
            ) : (
              <Card className="bg-white border-zinc-200 shadow-sm p-8 text-center dark:bg-zinc-900 dark:border-zinc-800">
                <FileText size={28} className="text-zinc-300 mx-auto mb-2" />
                <p className="text-zinc-400 text-sm">No audit reports generated yet</p>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default PulseAIDiagnosisTab;
