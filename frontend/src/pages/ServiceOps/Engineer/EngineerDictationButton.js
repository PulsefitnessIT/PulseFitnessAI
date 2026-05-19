/**
 * EngineerDictationButton — voice-to-text dictation for the engineer's
 * work summary.
 *
 * Iter 216h134. Captures up to 60s of mic audio (MediaRecorder),
 * posts to `/api/svc/engineer/ai/dictate-summary`, and yields
 * `{ transcript, summary }` to the caller via `onResult`.
 *
 * Behaviour:
 *  • Press & hold OR tap-to-toggle (auto-detect by long-press).
 *  • Visible recording state with elapsed time + waveform pulse.
 *  • Auto-stops at 60s to keep budget in check.
 *  • Graceful errors when mic permission is denied or the API fails.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Mic, MicOff, Loader2, Sparkles, AlertTriangle } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const MAX_SECONDS = 60;

export default function EngineerDictationButton({ caseId, hint, onResult, disabled }) {
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState('');
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const tickRef = useRef(null);

  const supported = typeof navigator !== 'undefined'
    && navigator.mediaDevices?.getUserMedia
    && typeof window !== 'undefined'
    && 'MediaRecorder' in window;

  const cleanup = useCallback(() => {
    if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    mediaRecorderRef.current = null;
    setRecording(false);
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  const send = useCallback(async (blob) => {
    setProcessing(true);
    try {
      const fd = new FormData();
      const ext = (blob.type.split('/')[1] || 'webm').split(';')[0];
      fd.append('audio', blob, `dictation.${ext}`);
      if (caseId) fd.append('case_id', caseId);
      if (hint) fd.append('hint', hint);
      const r = await axios.post(`${API}/svc/engineer/ai/dictate-summary`, fd, {
        ...auth(),
        headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
        timeout: 120000,
      });
      onResult?.(r.data);
      notify.success('Summary drafted');
    } catch (e) {
      const d = e?.response?.data?.detail;
      const msg = typeof d === 'string' ? d : (d?.message || 'Dictation failed');
      setError(msg);
      notify.error(msg);
    } finally {
      setProcessing(false);
    }
  }, [caseId, hint, onResult]);

  const stop = useCallback(() => {
    const mr = mediaRecorderRef.current;
    if (mr && mr.state !== 'inactive') {
      try { mr.stop(); } catch { /* noop */ }
    }
  }, []);

  const start = useCallback(async () => {
    if (!supported) {
      setError('This browser does not support microphone capture.');
      return;
    }
    setError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      // Pick the best supported mime
      const mimeCandidates = [
        'audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg',
      ];
      const mime = mimeCandidates.find(m => {
        try { return MediaRecorder.isTypeSupported(m); } catch { return false; }
      }) || '';
      const mr = mime ? new MediaRecorder(stream, { mimeType: mime })
                       : new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data?.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || 'audio/webm' });
        cleanup();
        setSeconds(0);
        if (blob.size > 1000) {
          send(blob);
        } else {
          setError('Too quiet — try again.');
        }
      };
      mr.start();
      setSeconds(0);
      setRecording(true);
      tickRef.current = setInterval(() => {
        setSeconds(s => {
          if (s + 1 >= MAX_SECONDS) {
            stop();
          }
          return s + 1;
        });
      }, 1000);
    } catch (err) {
      setError(err?.name === 'NotAllowedError'
        ? 'Microphone permission denied.'
        : (err?.message || 'Could not start recording.'));
      cleanup();
    }
  }, [supported, cleanup, send, stop]);

  if (!supported) {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 flex items-start gap-2" data-testid="dictation-unsupported">
        <AlertTriangle size={14} className="mt-0.5" />
        <span>Voice dictation isn't supported in this browser. You can still type the summary above.</span>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4" data-testid="dictation-card">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles size={14} className="text-blue-600" />
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500">
          Or dictate your summary (AI will polish it)
        </p>
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={disabled || processing}
          onClick={recording ? stop : start}
          className={`relative inline-flex items-center justify-center w-14 h-14 rounded-full text-white font-bold shadow-md transition-transform active:scale-95 disabled:opacity-50 ${
            recording ? 'bg-rose-600 hover:bg-rose-700' : 'bg-blue-600 hover:bg-blue-700'
          }`}
          aria-label={recording ? 'Stop dictation' : 'Start dictation'}
          data-testid="dictation-mic-btn"
        >
          {processing ? <Loader2 size={20} className="animate-spin" />
            : recording ? <MicOff size={20} /> : <Mic size={20} />}
          {recording && (
            <span className="absolute inset-0 rounded-full border-2 border-rose-300 animate-ping opacity-75" />
          )}
        </button>
        <div className="flex-1 min-w-0">
          {recording ? (
            <>
              <p className="text-sm font-bold text-rose-700 tabular-nums" data-testid="dictation-timer">
                {seconds}s / {MAX_SECONDS}s
              </p>
              <p className="text-[11px] text-slate-500">
                Speak naturally — describe what was diagnosed &amp; repaired. Tap again to stop.
              </p>
            </>
          ) : processing ? (
            <>
              <p className="text-sm font-bold text-slate-800" data-testid="dictation-processing">
                Transcribing &amp; polishing…
              </p>
              <p className="text-[11px] text-slate-500">
                Whisper transcription, then GPT-5.2 rewrite. Usually 5-15 seconds.
              </p>
            </>
          ) : (
            <>
              <p className="text-sm font-bold text-slate-800">Tap mic to dictate</p>
              <p className="text-[11px] text-slate-500">
                Up to {MAX_SECONDS} seconds. Powered by OpenAI Whisper + GPT-5.2.
              </p>
            </>
          )}
          {error && (
            <p className="text-[11px] text-rose-600 mt-1" data-testid="dictation-error">{error}</p>
          )}
        </div>
      </div>
    </div>
  );
}
