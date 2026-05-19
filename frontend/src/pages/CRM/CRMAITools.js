import { useState, useEffect, useCallback } from 'react';
import { useCRM } from './CRMApp';
import {
  Sparkles, Mail, TrendingUp, Send, RefreshCw, Loader2, Mic,
  Shield, CheckCircle
} from 'lucide-react';
import axios from 'axios';

export default function CRMAITools() {
  const { API, headers, c, isDark } = useCRM();
  const [activeAI, setActiveAI] = useState('scoring');
  const [contacts, setContacts] = useState([]);
  const [selectedContact, setSelectedContact] = useState('');

  const [scoreResult, setScoreResult] = useState(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const [emailResult, setEmailResult] = useState(null);
  const [emailLoading, setEmailLoading] = useState(false);
  const [emailTone, setEmailTone] = useState('professional');
  const [emailPurpose, setEmailPurpose] = useState('follow-up');
  const [emailContext, setEmailContext] = useState('');
  const [meetingTitle, setMeetingTitle] = useState('');
  const [transcript, setTranscript] = useState('');
  const [meetingResult, setMeetingResult] = useState(null);
  const [meetingLoading, setMeetingLoading] = useState(false);
  const [cleaningReport, setCleaningReport] = useState(null);
  const [cleaningLoading, setCleaningLoading] = useState(false);

  const fetchContacts = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/contacts?limit=200`, { headers: headers() });
      setContacts(res.data.contacts);
    } catch (e) { console.error(e); }
  }, [API, headers]);

  useEffect(() => { fetchContacts(); }, [fetchContacts]);

  const runLeadScore = async () => {
    if (!selectedContact) return;
    setScoreLoading(true); setScoreResult(null);
    try {
      const res = await axios.post(`${API}/crm/ai/lead-score`, { contact_id: selectedContact }, { headers: headers() });
      setScoreResult(res.data);
    } catch (e) { setScoreResult({ score: 0, label: 'Error', reasoning: 'Failed. Try again.', next_action: '' }); }
    setScoreLoading(false);
  };

  const generateEmail = async () => {
    setEmailLoading(true); setEmailResult(null);
    try {
      const res = await axios.post(`${API}/crm/ai/generate-email`, {
        contact_id: selectedContact || null, tone: emailTone, purpose: emailPurpose, context: emailContext,
      }, { headers: headers() });
      setEmailResult(res.data);
    } catch (e) { setEmailResult({ subject: 'Error', body: 'Failed to generate.', follow_up_note: '' }); }
    setEmailLoading(false);
  };

  const analyseMeeting = async () => {
    if (!transcript.trim() || transcript.length < 20) return;
    setMeetingLoading(true); setMeetingResult(null);
    try {
      const res = await axios.post(`${API}/crm/ai/meeting-intelligence`, {
        title: meetingTitle || 'Meeting', transcript, contact_id: selectedContact || null,
      }, { headers: headers() });
      setMeetingResult(res.data);
    } catch (e) { setMeetingResult({ summary: 'Analysis failed.', key_points: [], action_items: [], sentiment: 'neutral', next_steps: [] }); }
    setMeetingLoading(false);
  };

  const runDataCleaning = async () => {
    setCleaningLoading(true); setCleaningReport(null);
    try {
      const res = await axios.get(`${API}/crm/ai/data-cleaning/report`, { headers: headers() });
      setCleaningReport(res.data);
    } catch (e) { console.error(e); }
    setCleaningLoading(false);
  };

  const scoreColors = { Hot: 'var(--color-danger-alt)', Warm: 'var(--color-accent-amber)', Cool: 'var(--color-info-ios)', Cold: 'var(--color-text-faint-alt)', Error: 'var(--color-danger-alt)' };
  const sentimentColors = { positive: 'var(--color-success-alt)', neutral: 'var(--color-info-ios)', negative: 'var(--color-danger-alt)' };

  const tabs = [
    { id: 'scoring', label: 'Lead Scoring', icon: TrendingUp, color: 'var(--color-info-ios)' },
    { id: 'email', label: 'Email Generator', icon: Mail, color: 'var(--color-accent-magenta)' },
    { id: 'meetings', label: 'Meeting Intel', icon: Mic, color: 'var(--color-success-alt)' },
    { id: 'cleaning', label: 'Data Cleaning', icon: Shield, color: 'var(--color-accent-amber)' },
  ];

  return (
    <div data-testid="crm-ai-tools">
      {/* Header */}
      <div className="mb-5">
        <h1 className="text-xl font-bold tracking-tight" style={{ color: c.text }}>AI Tools</h1>
        <p className="text-xs mt-0.5" style={{ color: c.textDim }}>AI-powered sales and service intelligence</p>
      </div>

      {/* Tab pills */}
      <div className="flex gap-2 mb-5 flex-wrap">
        {tabs.map(tb => {
          const Icon = tb.icon;
          const active = activeAI === tb.id;
          return (
            <button key={tb.id} onClick={() => setActiveAI(tb.id)}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-medium rounded-md transition-all ${active ? 'text-white' : ''}`}
              style={{
                background: active ? tb.color : (isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)'),
                color: active ? '#fff' : c.textMuted,
              }}
              data-testid={`ai-tab-${tb.id}`}>
              <Icon size={14} /> {tb.label}
            </button>
          );
        })}
      </div>

      {/* Contact selector for scoring/email/meetings */}
      {['scoring', 'email', 'meetings'].includes(activeAI) && (
        <div className="max-w-md mb-5">
          <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Select Contact</label>
          <select value={selectedContact} onChange={e => { setSelectedContact(e.target.value); setScoreResult(null); }}
            className="w-full mt-1 px-3 py-2 text-sm rounded-md"
            style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}`, color: c.text }}
            data-testid="ai-contact-select">
            <option value="">Choose a contact...</option>
            {contacts.map(ct => <option key={ct.id} value={ct.id}>{ct.first_name} {ct.last_name}{ct.company_name ? ` - ${ct.company_name}` : ''}</option>)}
          </select>
        </div>
      )}

      {/* LEAD SCORING */}
      {activeAI === 'scoring' && (
        <div className="rounded-lg border p-6 max-w-2xl" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: 'var(--color-info-ios)30' }} data-testid="ai-scoring-panel">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles size={18} style={{ color: 'var(--color-info-ios)' }} />
            <h3 className="text-sm font-semibold" style={{ color: c.text }}>AI Lead Scoring</h3>
          </div>
          <p className="text-xs mb-5" style={{ color: c.textDim }}>Analyze contact engagement, deal history, and activity patterns</p>
          <button onClick={runLeadScore} disabled={!selectedContact || scoreLoading}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-40" data-testid="ai-score-btn">
            {scoreLoading ? <Loader2 size={14} className="animate-spin" /> : <TrendingUp size={14} />}
            {scoreLoading ? 'Analyzing...' : 'Score Lead'}
          </button>
          {scoreResult && (
            <div className="mt-5 p-4 rounded-lg border" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="ai-score-result">
              <div className="flex items-center gap-4 mb-3">
                <div className="text-4xl font-bold tracking-tighter" style={{ color: scoreColors[scoreResult.label] || 'var(--color-info-ios)' }}>{scoreResult.score}</div>
                <div>
                  <span className="text-xs font-bold px-2 py-0.5 rounded" style={{ background: `${scoreColors[scoreResult.label]}20`, color: scoreColors[scoreResult.label] }}>{scoreResult.label}</span>
                  <span className="text-[10px] block mt-1" style={{ color: c.textDim }}>/ 100</span>
                </div>
              </div>
              <p className="text-sm" style={{ color: c.textMuted }}>{scoreResult.reasoning}</p>
              {scoreResult.next_action && (
                <div className="flex items-start gap-2 mt-3 px-3 py-2 rounded-md" style={{ background: 'var(--color-info-ios)08', border: '1px solid var(--color-info-ios)20' }}>
                  <RefreshCw size={12} className="mt-0.5 shrink-0" style={{ color: 'var(--color-info-ios)' }} />
                  <span className="text-xs" style={{ color: 'var(--color-info-ios)' }}>{scoreResult.next_action}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* EMAIL GENERATOR */}
      {activeAI === 'email' && (
        <div className="rounded-lg border p-6 max-w-2xl" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="ai-email-panel">
          <div className="flex items-center gap-2 mb-2">
            <Mail size={18} style={{ color: 'var(--color-accent-magenta)' }} />
            <h3 className="text-sm font-semibold" style={{ color: c.text }}>AI Email Generator</h3>
          </div>
          <p className="text-xs mb-4" style={{ color: c.textDim }}>Generate professional emails tailored to your contacts</p>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Tone</label>
              <select value={emailTone} onChange={e => setEmailTone(e.target.value)}
                className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                {['professional', 'casual', 'persuasive', 'friendly'].map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Purpose</label>
              <select value={emailPurpose} onChange={e => setEmailPurpose(e.target.value)}
                className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                {['follow-up', 'introduction', 'proposal', 'meeting-request', 'thank-you'].map(p => <option key={p} value={p}>{p.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}</option>)}
              </select>
            </div>
          </div>
          <textarea value={emailContext} onChange={e => setEmailContext(e.target.value)} rows={2} placeholder="Optional context..."
            className="w-full mb-3 px-3 py-2 text-sm rounded-md resize-none" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
          <button onClick={generateEmail} disabled={emailLoading}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md text-white disabled:opacity-40" style={{ background: 'var(--color-accent-magenta)' }} data-testid="ai-email-btn">
            {emailLoading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            {emailLoading ? 'Generating...' : 'Generate Email'}
          </button>
          {emailResult && (
            <div className="mt-4 p-4 rounded-lg border" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="ai-email-result">
              <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Subject</p>
              <p className="text-sm font-medium mb-3" style={{ color: c.text }}>{emailResult.subject}</p>
              <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Body</p>
              <pre className="text-sm whitespace-pre-wrap font-sans mt-1 leading-relaxed" style={{ color: c.textMuted }}>{emailResult.body}</pre>
              {emailResult.follow_up_note && (
                <div className="mt-3 px-3 py-2 rounded-md" style={{ background: 'var(--color-accent-magenta)08', border: '1px solid var(--color-accent-magenta)20' }}>
                  <span className="text-xs" style={{ color: 'var(--color-accent-magenta)' }}>{emailResult.follow_up_note}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* MEETING INTELLIGENCE */}
      {activeAI === 'meetings' && (
        <div className="rounded-lg border p-6 max-w-2xl" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="ai-meeting-panel">
          <div className="flex items-center gap-2 mb-2">
            <Mic size={18} style={{ color: 'var(--color-success-alt)' }} />
            <h3 className="text-sm font-semibold" style={{ color: c.text }}>Meeting Intelligence</h3>
          </div>
          <p className="text-xs mb-4" style={{ color: c.textDim }}>Analyze meeting transcripts for key insights and action items</p>
          <input value={meetingTitle} onChange={e => setMeetingTitle(e.target.value)} placeholder="Meeting title"
            className="w-full mb-2 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
          <textarea value={transcript} onChange={e => setTranscript(e.target.value)} rows={5} placeholder="Paste meeting transcript..."
            className="w-full mb-3 px-3 py-2 text-sm rounded-md resize-none" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
          <button onClick={analyseMeeting} disabled={meetingLoading || transcript.length < 20}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md text-white disabled:opacity-40" style={{ background: 'var(--color-success-alt)' }} data-testid="ai-meeting-btn">
            {meetingLoading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {meetingLoading ? 'Analyzing...' : 'Analyze Meeting'}
          </button>
          {meetingResult && (
            <div className="mt-5 space-y-3" data-testid="ai-meeting-result">
              <div className="flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Sentiment:</span>
                <span className="text-xs font-medium px-2 py-0.5 rounded capitalize" style={{ background: `${sentimentColors[meetingResult.sentiment]}20`, color: sentimentColors[meetingResult.sentiment] }}>{meetingResult.sentiment}</span>
              </div>
              <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Summary</p>
                <p className="text-sm mt-1" style={{ color: c.textMuted }}>{meetingResult.summary}</p>
              </div>
              {meetingResult.key_points?.length > 0 && (
                <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                  <p className="text-[10px] uppercase tracking-wider mb-2" style={{ color: c.textDim }}>Key Points</p>
                  {meetingResult.key_points.map((p, i) => (
                    <p key={i} className="text-sm flex items-start gap-2" style={{ color: c.textMuted }}><span style={{ color: 'var(--color-info-ios)' }}>-</span>{p}</p>
                  ))}
                </div>
              )}
              {meetingResult.action_items?.length > 0 && (
                <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                  <p className="text-[10px] uppercase tracking-wider mb-2" style={{ color: c.textDim }}>Action Items</p>
                  {meetingResult.action_items.map((item, i) => (
                    <div key={i} className="flex items-center gap-3 py-1.5">
                      <CheckCircle size={12} style={{ color: 'var(--color-success-alt)' }} />
                      <span className="text-sm flex-1" style={{ color: c.text }}>{item.task}</span>
                      <span className="text-[10px]" style={{ color: c.textDim }}>{item.assignee}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* DATA CLEANING */}
      {activeAI === 'cleaning' && (
        <div className="rounded-lg border p-6 max-w-2xl" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid="ai-cleaning-panel">
          <div className="flex items-center gap-2 mb-2">
            <Shield size={18} style={{ color: 'var(--color-accent-amber)' }} />
            <h3 className="text-sm font-semibold" style={{ color: c.text }}>Data Quality Scanner</h3>
          </div>
          <p className="text-xs mb-5" style={{ color: c.textDim }}>Detect missing fields, invalid emails, and potential duplicates</p>
          <button onClick={runDataCleaning} disabled={cleaningLoading}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md text-white disabled:opacity-40" style={{ background: 'var(--color-accent-amber)' }} data-testid="ai-cleaning-btn">
            {cleaningLoading ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
            {cleaningLoading ? 'Scanning...' : 'Run Scan'}
          </button>
          {cleaningReport && (
            <div className="mt-5 space-y-3" data-testid="ai-cleaning-result">
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                {[
                  { l: 'Missing Email', v: cleaningReport.missing_email, col: 'var(--color-danger-alt)' },
                  { l: 'Missing Phone', v: cleaningReport.missing_phone, col: 'var(--color-accent-amber)' },
                  { l: 'Missing Company', v: cleaningReport.missing_company, col: 'var(--color-warning)' },
                  { l: 'Invalid Email', v: cleaningReport.invalid_email, col: 'var(--color-danger-alt)' },
                  { l: 'Duplicates', v: cleaningReport.potential_duplicates, col: 'var(--color-accent-magenta)' },
                ].map(item => (
                  <div key={item.l} className="p-3 rounded-lg border text-center" style={{ background: isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                    <p className="text-2xl font-bold" style={{ color: item.v > 0 ? item.col : 'var(--color-success-alt)' }}>{item.v}</p>
                    <p className="text-[9px] uppercase tracking-wider mt-1" style={{ color: c.textDim }}>{item.l}</p>
                  </div>
                ))}
              </div>
              {cleaningReport.missing_email === 0 && cleaningReport.invalid_email === 0 && cleaningReport.potential_duplicates === 0 && (
                <div className="flex items-center gap-2 p-3 rounded-lg" style={{ background: 'var(--color-success-alt)10', border: '1px solid var(--color-success-alt)20' }}>
                  <CheckCircle size={14} style={{ color: 'var(--color-success-alt)' }} />
                  <span className="text-sm" style={{ color: 'var(--color-success-alt)' }}>Data is clean!</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
