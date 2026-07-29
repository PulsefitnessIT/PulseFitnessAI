/**
 * Marketing-side AI chat widget — Iter 216ba.
 *
 * Floating button bottom-right of every marketing page. Opens a modest
 * chat panel that talks to /api/marketing/chat (Claude Sonnet 4.5
 * grounded on the help corpus). Anonymous, no signup required, rate-
 * limited server-side.
 */
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { MessageCircle, X, Send, Sparkles, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function MarketingChat() {
  const { t } = useTranslation();
  const SUGGESTIONS = [
    t('mkt.mc_sugg_pricing', 'How does pricing work?'),
    t('mkt.mc_sugg_import', 'Can I import my existing members?'),
    t('mkt.mc_sugg_stripe', 'Do you integrate with Stripe?'),
    t('mkt.mc_sugg_trial', 'What is in the free trial?'),
  ];
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState(() => [
    {
      role: 'assistant',
      text: t('mkt.mc_welcome', 'Hi — I am the Pulse Fitness sales assistant. Ask me anything about pricing, modules, integrations, or migration. I will give you a straight answer.'),
    },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const scrollerRef = useRef(null);

  useEffect(() => {
    if (scrollerRef.current) scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [messages, open]);

  const send = async (text) => {
    const txt = (text || '').trim();
    if (!txt || busy) return;
    setMessages((m) => [...m, { role: 'user', text: txt }]);
    setInput('');
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/marketing/chat`, {
        message: txt,
        session_id: sessionId,
        context_path: typeof window !== 'undefined' ? window.location.pathname : '',
      }, { timeout: 30000 });
      if (data.session_id) setSessionId(data.session_id);
      setMessages((m) => [...m, { role: 'assistant', text: data.answer }]);
    } catch (e) {
      const msg = e?.response?.data?.detail || t('mkt.mc_network_err', 'Network hiccup — try again in a moment.');
      setMessages((m) => [...m, { role: 'assistant', text: msg }]);
    }
    setBusy(false);
  };

  return (
    <>
      {/* Floating button */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-5 right-5 z-[55] w-14 h-14 rounded-full bg-gradient-to-br from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] text-white shadow-[0_18px_40px_-10px_rgba(91,91,245,0.6)] flex items-center justify-center hover:scale-105 transition-transform"
        aria-label={open ? t('mkt.mc_close', 'Close chat') : t('mkt.mc_open', 'Open chat')}
        data-testid="gx-chat-launcher"
      >
        {open ? <X size={20} /> : <MessageCircle size={22} />}
      </button>

      {/* Chat panel */}
      {open && (
        <div
          className="fixed bottom-24 right-5 z-[55] w-[calc(100%-2.5rem)] max-w-md rounded-2xl bg-white shadow-[0_30px_80px_-20px_rgba(15,23,42,0.45)] border border-slate-200 flex flex-col overflow-hidden dark:bg-zinc-900 dark:border-zinc-800"
          style={{ height: 520 }}
          data-testid="gx-chat-panel"
        >
          {/* Header */}
          <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-3 bg-gradient-to-r from-[var(--gx-brand-from)]/8 to-[var(--gx-brand-to)]/8 dark:border-zinc-800">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] flex items-center justify-center text-white">
              <Sparkles size={15} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-slate-900 dark:text-zinc-100">Pulse Fitness Sales AI</p>
              <p className="text-[11px] text-slate-500">{t('mkt.mc_tagline', 'Honest answers · grounded on the live product')}</p>
            </div>
          </div>

          {/* Messages */}
          <div ref={scrollerRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3" data-testid="gx-chat-messages">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                    m.role === 'user'
                      ? 'bg-slate-900 text-white rounded-br-sm'
                      : 'bg-slate-100 text-slate-800 rounded-bl-sm'
                  }`}
                  data-testid={`gx-chat-msg-${m.role}`}
                >
                  {m.text}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start" data-testid="gx-chat-thinking">
                <div className="bg-slate-100 text-slate-500 rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-[13px] inline-flex items-center gap-2 dark:bg-zinc-800">
                  <Loader2 size={13} className="animate-spin" /> {t('mkt.mc_thinking', 'Thinking…')}
                </div>
              </div>
            )}
          </div>

          {/* Suggestions (only on first turn) */}
          {messages.length === 1 && !busy && (
            <div className="px-4 pb-2 flex flex-wrap gap-1.5" data-testid="gx-chat-suggestions">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s} type="button" onClick={() => send(s)}
                  className="text-[11px] rounded-full border border-slate-200 px-2.5 py-1 text-slate-600 hover:bg-slate-50 dark:bg-zinc-900 dark:border-zinc-800"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <form
            onSubmit={(e) => { e.preventDefault(); send(input); }}
            className="px-3 py-3 border-t border-slate-100 flex items-center gap-2 dark:border-zinc-800"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t('mkt.mc_input_ph', 'Ask anything…')}
              disabled={busy}
              className="flex-1 h-9 rounded-full bg-slate-50 border border-slate-200 px-4 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--gx-brand-to)]/30 dark:bg-zinc-900 dark:border-zinc-800"
              data-testid="gx-chat-input"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="w-9 h-9 rounded-full bg-gradient-to-br from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] text-white flex items-center justify-center disabled:opacity-50"
              data-testid="gx-chat-send"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            </button>
          </form>
        </div>
      )}
    </>
  );
}
