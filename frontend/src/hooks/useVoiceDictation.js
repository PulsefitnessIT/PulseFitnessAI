/**
 * useVoiceDictation — Web Speech API wrapper for hands-free engineer notes.
 *
 * Falls back gracefully when the browser doesn't support
 * SpeechRecognition (Safari iOS pre-14.5, Firefox desktop) — the caller
 * can use `supported` to hide the mic button.
 *
 * Usage:
 *   const { supported, listening, start, stop, reset } = useVoiceDictation({
 *     onResult: (text) => setNote((n) => `${n} ${text}`.trim()),
 *     lang: 'en-GB',
 *   });
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export default function useVoiceDictation({
  onResult,
  onError,
  lang = 'en-GB',
  continuous = true,
  interimResults = false,
} = {}) {
  const recognitionRef = useRef(null);
  const [listening, setListening] = useState(false);
  const SR = (typeof window !== 'undefined') &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);

  // Lazy-construct the recogniser once per component instance.
  if (SR && !recognitionRef.current) {
    const r = new SR();
    r.lang = lang;
    r.continuous = continuous;
    r.interimResults = interimResults;
    r.onresult = (event) => {
      // Stitch together every final transcript that arrived since last fire.
      let finalText = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const res = event.results[i];
        if (res.isFinal) finalText += res[0].transcript;
      }
      if (finalText && onResult) onResult(finalText.trim());
    };
    r.onerror = (event) => {
      setListening(false);
      if (onError) onError(event.error || 'voice-error');
    };
    r.onend = () => setListening(false);
    recognitionRef.current = r;
  }

  // Stop the recogniser if the host component unmounts mid-listen.
  useEffect(() => () => {
    try { recognitionRef.current?.abort(); } catch { /* noop */ }
  }, []);

  const start = useCallback(() => {
    const r = recognitionRef.current;
    if (!r || listening) return;
    try {
      r.start();
      setListening(true);
    } catch (e) {
      setListening(false);
      if (onError) onError(e.message || 'voice-start-error');
    }
  }, [listening, onError]);

  const stop = useCallback(() => {
    try { recognitionRef.current?.stop(); } catch { /* noop */ }
    setListening(false);
  }, []);

  const reset = useCallback(() => {
    try { recognitionRef.current?.abort(); } catch { /* noop */ }
    setListening(false);
  }, []);

  return { supported: !!SR, listening, start, stop, reset };
}
