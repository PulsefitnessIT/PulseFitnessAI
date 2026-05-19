import { useState, useRef, useEffect } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { Send, Loader2, FileText, Sparkles } from 'lucide-react';

const DocumentQA = ({ compact = false }) => {
 const { API } = useAuth();
 const [open, _setOpen] = useState(false);
 const [question, setQuestion] = useState('');
 const [loading, setLoading] = useState(false);
 const [history, setHistory] = useState([]);
 const scrollRef = useRef(null);
 const inputRef = useRef(null);
 const token = localStorage.getItem('token');

 useEffect(() => {
 if (scrollRef.current) {
 scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
 }
 }, [history]);

 useEffect(() => {
 if (open && inputRef.current) inputRef.current.focus();
 }, [open]);

 const handleAsk = async (e) => {
 e?.preventDefault();
 if (!question.trim() || loading) return;

 const q = question.trim();
 setHistory(prev => [...prev, { role: 'user', text: q }]);
 setQuestion('');
 setLoading(true);

 try {
 const res = await axios.post(`${API}/documents/ask`, { question: q }, {
 headers: { Authorization: `Bearer ${token}` },
 timeout: 60000,
 });
 setHistory(prev => [...prev, {
 role: 'assistant',
 text: res.data.answer,
 sources: res.data.sources || [],
 count: res.data.documents_searched || 0,
 }]);
 } catch {
 notify.error('Failed to get answer');
 setHistory(prev => [...prev, { role: 'assistant', text: 'Sorry, I couldn\'t process that question. Please try again.' }]);
 }
 setLoading(false);
 };

 // Compact mode: inline card within Documents tab
 if (compact) {
 return (
 <Card className="overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid="doc-qa-panel">
 <div className="flex items-center gap-2 px-4 py-3" style={{ borderBottom: '1px solid var(--theme-border)' }}>
 <div className="w-7 h-7 rounded-lg flex items-center justify-center bg-purple-500/15">
 <Sparkles size={14} className="text-purple-400" />
 </div>
 <div className="flex-1">
 <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Ask Your Documents</p>
 <p className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>AI-powered answers from your uploaded manuals</p>
 </div>
 </div>
 <div ref={scrollRef} className="max-h-[300px] overflow-y-auto p-4 space-y-3" style={{ minHeight: history.length ? '120px' : '0px' }}>
 {history.map((msg, i) => (
 <div key={`msg-${i}-${msg.role}`} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
 <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${msg.role === 'user' ? 'bg-[var(--color-brand-blue)] text-white' : ''}`}
 style={msg.role !== 'user' ? { background: 'var(--theme-bg)', color: 'var(--theme-text)' } : {}}>
 <div className="whitespace-pre-wrap">{msg.text}</div>
 {msg.sources?.length > 0 && (
 <div className="flex flex-wrap gap-1 mt-2 pt-2" style={{ borderTop: '1px solid var(--theme-border)' }}>
 {msg.sources.filter(s => s.supplier || s.equipment).slice(0, 3).map((s, j) => (
 <Badge key={`src-${j}-${s.supplier}`} className="bg-purple-500/15 text-purple-300 text-[9px]">
 <FileText size={8} className="mr-0.5" /> {s.supplier || s.equipment || s.filename}
 </Badge>
 ))}
 {msg.count > 0 && <span className="text-[9px]" style={{ color: 'var(--theme-text-muted)' }}>({msg.count} docs searched)</span>}
 </div>
 )}
 </div>
 </div>
 ))}
 {loading && (
 <div className="flex justify-start">
 <div className="rounded-xl px-3 py-2 text-sm flex items-center gap-2" style={{ background: 'var(--theme-bg)', color: 'var(--theme-text-muted)' }}>
 <Loader2 size={14} className="animate-spin" /> Searching documents...
 </div>
 </div>
 )}
 </div>
 <form onSubmit={handleAsk} className="flex gap-2 p-3" style={{ borderTop: '1px solid var(--theme-border)' }}>
 <Input
 ref={inputRef}
 value={question}
 onChange={e => setQuestion(e.target.value)}
 placeholder="e.g. What torque spec for a Technogym belt?"
 className="flex-1 text-sm"
 style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
 disabled={loading}
 data-testid="doc-qa-input"
 />
 <Button type="submit" size="sm" disabled={loading || !question.trim()} className="bg-[var(--color-brand-blue)] text-white px-3" data-testid="doc-qa-send">
 <Send size={14} />
 </Button>
 </form>
 </Card>
 );
 }

 // Floating mode deprecated — the "Ask GymAxis / Ask Pulse Fitness" orb now
 // handles document Q&A via the same LLM plus context pipeline. Returning null
 // keeps legacy call-sites from crashing while removing the duplicate lilac FAB.
 return null;
};

export default DocumentQA;
