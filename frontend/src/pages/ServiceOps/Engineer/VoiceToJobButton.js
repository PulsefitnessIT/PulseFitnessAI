/**
 * VoiceToJobButton — iter 220cw.
 *
 * Floating mic button that lets engineers dictate a job description
 * (driver-friendly, one-handed). The audio is sent to
 * `POST /api/svc/engineer/ai/voice-to-job` which:
 *   1. Whisper-transcribes the recording.
 *   2. Runs the transcript through the GPT-5.2 email-parse
 *      extractor (same JSON shape as the paste-email helper).
 *
 * On success we navigate to the New Job form with the parsed fields
 * stashed in `sessionStorage` so the form pre-fills.
 *
 * Re-uses the proven MediaRecorder pattern from EngineerDictationButton.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Mic, MicOff, Loader2, X,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const MAX_SECONDS = 90;
export const VOICE_JOB_DRAFT_KEY = 'svc.engineer.voiceJobDraft';

export default function VoiceToJobButton() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
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

  // Iter 220ea·5 — Listen for the SpeedDial's open event so the
  // single consolidated launcher can drive this modal.
  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener('gx:open-voice', onOpen);
    return () => window.removeEventListener('gx:open-voice', onOpen);
  }, []);

  // Iter 220ea·5 — The engineer SpeedDial owns the launcher on
  // engineer routes; suppress the floating mic so we don't show
  // two buttons at the same corner.
  const isEngineerRoute = typeof window !== 'undefined'
    && /^\/svc\/engineer/.test(window.location.pathname);

  const cleanup = useCallback(() => {
    if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
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
      const r = await axios.post(`${API}/svc/engineer/ai/voice-to-job`, fd, {
        ...auth(),
        headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
        timeout: 120000,
      });
      const draft = {
        transcript: r.data?.transcript || '',
        parsed: r.data?.parsed || {},
      };
      try {
        sessionStorage.setItem(VOICE_JOB_DRAFT_KEY, JSON.stringify(draft));
      } catch { /* private mode — fall through, the form will still open empty */ }
      const filled = Object.values(draft.parsed).filter(Boolean).length;
      notify.success(
        'Got it',
        filled > 0
          ? `Pre-filled ${filled} field${filled === 1 ? '' : 's'} from your dictation.`
          : 'Transcript ready — review and tweak.',
      );
      setOpen(false);
      navigate('/svc/engineer/jobs/new?from=voice');
    } catch (e) {
      const d = e?.response?.data?.detail;
      const msg = typeof d === 'string' ? d : (d?.message || 'Voice-to-job failed');
      setError(msg);
      notify.error('Voice-to-job failed', msg);
    } finally {
      setProcessing(false);
    }
  }, [navigate]);

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
      const mimeCandidates = [
        'audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg',
      ];
      const mime = mimeCandidates.find((m) => {
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
        setSeconds((s) => {
          if (s + 1 >= MAX_SECONDS) stop();
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

  if (!supported) return null;

  return (
    <>
      {/* Floating action button — bottom right. Hidden on engineer
          routes where the SpeedDial provides the consolidated
          launcher. */}
      {!isEngineerRoute && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full bg-gradient-to-br from-blue-600 to-indigo-700 text-white shadow-xl flex items-center justify-center hover:scale-105 transition-transform"
          aria-label="Voice-to-job"
          data-testid="voice-to-job-fab"
        >
          <Mic size={22} />
        </button>
      )}

      {/* Modal */}
      {open && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-4"
          data-testid="voice-to-job-modal"
        >
          <div className="bg-white rounded-3xl w-full max-w-md p-6 shadow-2xl border border-slate-200">
            <div className="flex items-start justify-between mb-4">
              <div>
                <p className="text-[10px] uppercase font-bold tracking-[0.2em] text-blue-700">
                  Voice-to-job
                </p>
                <h3 className="text-lg font-extrabold text-slate-900 mt-1">
                  Talk it through
                </h3>
                <p className="text-xs text-slate-500 mt-1 leading-snug">
                  Driving back from a site? Say something like
                  <span className="italic"> "Treadmill 4 at Acme Gym belt is slipping, customer is Sarah on 07700 900123, priority P2."</span>
                  We'll transcribe and pre-fill the new-job form.
                </p>
              </div>
              <button
                type="button"
                onClick={() => { stop(); setOpen(false); }}
                className="text-slate-400 hover:text-slate-700 p-1"
                aria-label="Close"
                data-testid="voice-to-job-close"
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex flex-col items-center gap-4 py-3">
              <button
                type="button"
                disabled={processing}
                onClick={recording ? stop : start}
                className={`relative inline-flex items-center justify-center w-20 h-20 rounded-full text-white font-bold shadow-lg transition-transform active:scale-95 disabled:opacity-50 ${
                  recording ? 'bg-rose-600' : 'bg-gradient-to-br from-blue-600 to-indigo-700'
                }`}
                aria-label={recording ? 'Stop recording' : 'Start recording'}
                data-testid="voice-to-job-mic-btn"
              >
                {processing ? <Loader2 size={28} className="animate-spin" />
                  : recording ? <MicOff size={28} /> : <Mic size={28} />}
                {recording && (
                  <span className="absolute inset-0 rounded-full border-4 border-rose-300 animate-ping opacity-60" />
                )}
              </button>
              <p className="text-sm font-bold text-slate-900 tabular-nums" data-testid="voice-to-job-state">
                {processing ? 'Transcribing…'
                  : recording ? `Recording ${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')} / 01:30`
                  : 'Tap to start'}
              </p>
              {error && (
                <p className="text-xs text-rose-700 bg-rose-50 border border-rose-200 px-3 py-1.5 rounded-full" data-testid="voice-to-job-error">
                  {error}
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
