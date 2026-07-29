/**
 * AI Assistant — Marketing Suite copilot
 *
 * Floating bottom-right panel with two stacked surfaces:
 *
 *   1. Quick Suggestions (top)  — context-aware chips per active tab,
 *      backed by the existing deterministic `/assistant/ask` endpoint.
 *   2. Free-form Chat (below)   — conversational Q&A grounded on the
 *      org's real metrics, powered by Claude Sonnet 4.5 via the new
 *      `/assistant/chat` endpoint. Conversation persists across tabs
 *      and reloads (server-stored per session_id). Claude can attach
 *      a one-click "Do it" action (navigate_tab / instantiate_template /
 *      clear_demo_data) that the platform executes via
 *      `/assistant/execute-action`.
 *
 * Empty-state shows three "starter" example questions to lower the
 * friction barrier for first-time users.
 */
import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Sparkles, X, ChevronRight, Loader2, Send, MessageSquare, Zap, CheckCircle2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import { useTranslation } from 'react-i18next';

// Render Claude's markdown-ish output as plain HTML (bold + line breaks only).
// Keeps things lightweight — no react-markdown dep.
function renderAnswer(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>');
}

const AIAssistant = ({ API, headers, activeTab, onSuggestionAction }) => {
  const { t } = useTranslation();
  const STARTER_QUESTIONS = [
    t('mkt.aia_starter_1', 'How is my last campaign performing?'),
    t('mkt.aia_starter_2', 'Which audience should I target next?'),
    t('mkt.aia_starter_3', 'Suggest a winback message for inactive members'),
  ];
  const [open, setOpen] = useState(true);
  const [question, setQuestion] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [busySuggest, setBusySuggest] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const [turns, setTurns] = useState([]);  // [{role, content, action?, done?}]
  const [executingIdx, setExecutingIdx] = useState(null);
  // Persist session id across reloads — chat history follows it.
  const sessionId = React.useMemo(() => {
    const stored = localStorage.getItem('marketing_assistant_session');
    if (stored) return stored;
    const id = `ma-${Math.random().toString(36).slice(2, 11)}`;
    localStorage.setItem('marketing_assistant_session', id);
    return id;
  }, []);
  const chatScrollRef = useRef(null);

  const fetchSuggestions = async () => {
    setBusySuggest(true);
    try {
      const { data } = await axios.post(`${API}/api/marketing/assistant/ask`, { page: activeTab }, { headers });
      setSuggestions(data.suggestions || []);
    } catch { /* sidebar isn't critical */ }
    setBusySuggest(false);
  };

  // Replay prior chat history on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/api/marketing/assistant/chat/${sessionId}`, { headers });
        if (!cancelled) setTurns(data.turns || []);
      } catch { /* fine */ }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  useEffect(() => { fetchSuggestions();   }, [activeTab]);

  // Auto-scroll on new turn.
  useEffect(() => {
    if (chatScrollRef.current) chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
  }, [turns, chatBusy]);

  const sendMessage = async (msg) => {
    const text = (msg ?? question).trim();
    if (!text || chatBusy) return;
    setQuestion('');
    setTurns((prev) => [...prev, { role: 'user', content: text }]);
    setChatBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/api/marketing/assistant/chat`,
        { session_id: sessionId, message: text },
        { headers, timeout: 60_000 },
      );
      setTurns((prev) => [...prev, { role: 'assistant', content: data.answer, action: data.action }]);
    } catch (err) {
      setTurns((prev) => [...prev, { role: 'assistant', content: t('mkt.aia_ai_err', 'Sorry — I had trouble reaching the AI service. Please try again in a moment.') }]);
    } finally {
      setChatBusy(false);
    }
  };

  const executeAction = async (action, turnIdx) => {
    if (!action || executingIdx !== null) return;
    setExecutingIdx(turnIdx);
    try {
      const { data } = await axios.post(
        `${API}/api/marketing/assistant/execute-action`,
        { type: action.type, params: action.params },
        { headers },
      );
      // Mark this turn as done so the button shows a tick and disables.
      setTurns((prev) => prev.map((turn, i) => i === turnIdx ? { ...turn, done: true } : turn));

      // Side-effects per action type
      if (action.type === 'navigate_tab' && data.navigate_to_tab) {
        if (onSuggestionAction) {
          // Reuse the existing tab-jump bridge — but we always pass the tab id directly.
          // MarketingSuite handles `setTab` via a closure; we emit a custom event for safety.
          window.dispatchEvent(new CustomEvent('mkt-jump-tab', { detail: data.navigate_to_tab }));
        }
        notify.success(t('mkt.aia_switched', 'Switched to {{tab}} tab', { tab: data.navigate_to_tab.charAt(0).toUpperCase() + data.navigate_to_tab.slice(1) }));
      } else if (action.type === 'instantiate_template') {
        notify.success(t('mkt.aia_template_ready', 'Template ready'), t('mkt.aia_template_ready_body', 'Audience size: {{n}} · saved as a draft.', { n: data.audience_size || 0 }));
        window.dispatchEvent(new CustomEvent('mkt-jump-tab', { detail: 'campaigns' }));
      } else if (action.type === 'clear_demo_data') {
        const total = (data.audiences_removed || 0) + (data.campaigns_removed || 0) + (data.journeys_removed || 0) + (data.creatives_removed || 0);
        notify.success(t('mkt.aia_demo_cleared', 'Demo data cleared'), t('mkt.aia_demo_cleared_body', '{{n}} item(s) removed.', { n: total }));
      }
    } catch (err) {
      notify.error(err.response?.data?.detail || t('mkt.aia_action_err', 'Could not execute that action'));
    } finally {
      setExecutingIdx(null);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 w-12 h-12 rounded-full bg-gradient-to-br from-[var(--color-brand-blue)] to-[var(--color-brand-cyan-hover)] text-white shadow-xl flex items-center justify-center hover:scale-105 transition z-30"
        aria-label={t('mkt.aia_open', 'Open AI Assistant')}
        data-testid="ai-assistant-toggle"
      >
        <Sparkles size={18} />
      </button>
    );
  }

  return (
    <div
      className="fixed bottom-5 right-5 w-96 max-w-[calc(100vw-2rem)] rounded-2xl shadow-2xl overflow-hidden z-30 flex flex-col max-h-[calc(100vh-6rem)]"
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', borderWidth: 1 }}
      data-testid="ai-assistant"
    >
      <div className="flex items-center justify-between p-3 bg-gradient-to-r from-[var(--color-brand-blue)] to-[var(--color-brand-cyan-hover)] text-white flex-shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles size={14} />
          <p className="text-sm font-semibold">{t('mkt.aia_title', 'AI Assistant')} <span className="text-[10px] font-normal opacity-80 ml-1">· Claude</span></p>
        </div>
        <button onClick={() => setOpen(false)} className="text-white/80 hover:text-white" data-testid="ai-assistant-close" aria-label={t('mkt.aia_close', 'Close')}>
          <X size={14} />
        </button>
      </div>

      {/* Suggestions strip — always visible, compact. Hidden when chat thread is non-empty so the chat dominates. */}
      {turns.length === 0 && (
        <div className="p-3 border-b flex-shrink-0" style={{ borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>{t('mkt.aia_suggestions', 'Suggestions for this tab')}</p>
          {busySuggest && suggestions.length === 0 ? (
            <div className="flex items-center gap-2 text-xs py-2" style={{ color: 'var(--theme-text-muted)' }}>
              <Loader2 size={12} className="animate-spin" /> {t('mkt.aia_thinking', 'Thinking…')}
            </div>
          ) : suggestions.length === 0 ? (
            <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{t('mkt.aia_no_suggestions', 'No suggestions right now — ask me anything below.')}</p>
          ) : (
            <div className="space-y-1.5">
              {suggestions.slice(0, 2).map((s) => (
                <button
                  key={s.id}
                  onClick={() => s.action && onSuggestionAction?.(s.action)}
                  className="w-full text-left p-2 rounded-md border hover:border-[rgb(var(--rgb-brand-blue)/0.4)] transition group"
                  style={{ borderColor: 'var(--theme-border)' }}
                  data-testid={`ai-suggestion-${s.id}`}
                >
                  <p className="text-[11px] font-semibold flex items-center gap-1.5" style={{ color: 'var(--theme-text)' }}>
                    {s.label}
                    {s.action && <ChevronRight size={10} className="text-[var(--color-brand-blue)] opacity-0 group-hover:opacity-100" />}
                  </p>
                  <p className="text-[10px] mt-0.5 leading-snug" style={{ color: 'var(--theme-text-muted)' }}>{s.body}</p>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Chat thread */}
      <div ref={chatScrollRef} className="flex-1 overflow-y-auto p-3 space-y-2.5" data-testid="ai-assistant-chat-thread" style={{ minHeight: turns.length === 0 ? 0 : 200 }}>
        {turns.length === 0 ? (
          <div className="text-center py-2">
            <MessageSquare className="mx-auto mb-2 opacity-40" size={20} style={{ color: 'var(--theme-text-muted)' }} />
            <p className="text-[11px] font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>{t('mkt.aia_try_one', 'Try one of these:')}</p>
            <div className="space-y-1.5">
              {STARTER_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(q)}
                  className="w-full text-left text-[11px] px-2.5 py-1.5 rounded-md border hover:border-[rgb(var(--rgb-brand-blue)/0.4)] hover:bg-[rgb(var(--rgb-brand-blue)/0.05)] transition"
                  style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                  data-testid={`ai-starter-${i}`}
                >
                  "{q}"
                </button>
              ))}
            </div>
          </div>
        ) : (
          turns.map((turn, i) => (
            <div
              key={i}
              className={`flex ${turn.role === 'user' ? 'justify-end' : 'justify-start'}`}
              data-testid={`ai-turn-${i}`}
            >
              <div className={`max-w-[85%] flex flex-col gap-2 ${turn.role === 'user' ? 'items-end' : 'items-start'}`}>
                <div
                  className={`px-3 py-2 rounded-2xl text-xs leading-relaxed ${turn.role === 'user' ? 'rounded-br-sm' : 'rounded-bl-sm'}`}
                  style={turn.role === 'user'
                    ? { background: 'linear-gradient(135deg, var(--color-brand-blue), var(--color-brand-cyan))', color: 'white' }
                    : { background: 'var(--theme-bg)', color: 'var(--theme-text)', border: '1px solid var(--theme-border)' }}
                  dangerouslySetInnerHTML={turn.role === 'assistant' ? { __html: renderAnswer(turn.content) } : undefined}
                >
                  {turn.role === 'user' ? turn.content : null}
                </div>
                {turn.role === 'assistant' && turn.action && (
                  <button
                    onClick={() => !turn.done && executeAction(turn.action, i)}
                    disabled={turn.done || executingIdx === i}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-bold shadow-sm transition disabled:opacity-60"
                    style={turn.done
                      ? { background: 'rgb(16 185 129 / 0.12)', color: 'rgb(16 185 129)', border: '1px solid rgb(16 185 129 / 0.3)' }
                      : { background: 'linear-gradient(135deg, var(--color-brand-blue), var(--color-brand-cyan))', color: 'white' }}
                    data-testid={`ai-action-${i}`}
                  >
                    {executingIdx === i ? <Loader2 size={11} className="animate-spin" /> : turn.done ? <CheckCircle2 size={11} /> : <Zap size={11} />}
                    {turn.done ? t('mkt.aia_done', 'Done') : (executingIdx === i ? t('mkt.aia_working', 'Working…') : turn.action.label)}
                  </button>
                )}
                {/* Dedup: route campaign-generation intent to the AI Director — the canonical place to draft a full campaign. */}
                {turn.role === 'assistant' && !turn.action && /(campaign|email|message|copy|winback|subject line|promote|class|launch|drive)/i.test(turn.content || '') && turns[i - 1]?.content && (
                  <button
                    onClick={() => {
                      window.dispatchEvent(new CustomEvent('mkt-jump-tab', { detail: 'creative' }));
                      // Hand the user's last question to the Director as a seed prompt
                      setTimeout(() => {
                        window.dispatchEvent(new CustomEvent('director:seed-prompt', { detail: { prompt: turns[i - 1].content } }));
                      }, 500);
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-semibold border border-[rgb(var(--rgb-brand-blue)/0.3)] text-[var(--color-brand-blue)] hover:bg-[rgb(var(--rgb-brand-blue)/0.05)] transition"
                    data-testid={`ai-build-director-${i}`}
                  >
                    <Sparkles size={11}/> {t('mkt.aia_build_director', 'Build this in AI Director')}
                  </button>
                )}
              </div>
            </div>
          ))
        )}
        {chatBusy && (
          <div className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--theme-text-muted)' }} data-testid="ai-chat-thinking">
            <Loader2 size={11} className="animate-spin" /> {t('mkt.aia_thinking', 'Thinking…')}
          </div>
        )}
      </div>

      {/* Input bar */}
      <form
        className="p-2.5 flex gap-1.5 border-t flex-shrink-0"
        style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}
        onSubmit={(e) => { e.preventDefault(); sendMessage(); }}
        data-testid="ai-assistant-form"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={t('mkt.aia_input_ph', 'Ask anything about your marketing…')}
          disabled={chatBusy}
          className="flex-1 px-2.5 py-1.5 text-xs rounded-md disabled:opacity-50"
          style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)', border: '1px solid var(--theme-border)' }}
          data-testid="ai-assistant-input"
        />
        <button
          type="submit"
          disabled={!question.trim() || chatBusy}
          className="p-1.5 rounded-md bg-[var(--color-brand-blue)] text-white disabled:opacity-40 disabled:cursor-not-allowed"
          data-testid="ai-assistant-send"
          aria-label={t('mkt.aia_send', 'Send')}
        >
          {chatBusy ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
        </button>
      </form>
    </div>
  );
};

export default AIAssistant;
