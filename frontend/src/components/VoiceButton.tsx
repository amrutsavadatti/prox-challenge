import { useCallback, useEffect, useRef, useState } from 'react';
import { Mic, Square } from 'lucide-react';
import { useStore } from '@/store';

function pickMime(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
  ];
  for (const m of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(m)) return m;
  }
  return '';
}

interface Props {
  disabled?: boolean;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === 'string' && error) return error;
  return fallback;
}

export function VoiceButton({ disabled }: Props) {
  const sendVoiceMessage = useStore((s) => s.sendVoiceMessage);
  const stopPlayback = useStore((s) => s.stopPlayback);
  const unlockAudio = useStore((s) => s.unlockAudio);
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  // Keep the stream alive between recordings so start() is instant.
  const streamRef = useRef<MediaStream | null>(null);
  const mimeRef = useRef<string>(pickMime());

  // Pre-warm: request mic access on mount so the device is ready before first press.
  useEffect(() => {
    if (!navigator.mediaDevices?.getUserMedia) return;
    const mime = mimeRef.current;
    if (!mime) return;
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((s) => { streamRef.current = s; })
      .catch(() => { /* permission denied — will surface on first press */ });
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, []);

  const start = useCallback(async () => {
    setError(null);
    unlockAudio();
    stopPlayback();

    const mime = mimeRef.current;
    if (!mime) { setError('No supported audio format'); return; }
    if (!navigator.mediaDevices?.getUserMedia) { setError('Mic not supported'); return; }

    try {
      // Reuse the pre-warmed stream; request a new one only if it died.
      if (!streamRef.current || streamRef.current.getTracks().some((t) => t.readyState === 'ended')) {
        streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
      const stream = streamRef.current;
      chunksRef.current = [];
      const rec = new MediaRecorder(stream, { mimeType: mime });
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mime });
        // Do NOT stop tracks — keep the stream alive for the next recording.
        if (blob.size > 1000) sendVoiceMessage(blob, mime);
      };
      rec.start();
      recorderRef.current = rec;
      setIsRecording(true);
    } catch (error: unknown) {
      setError(getErrorMessage(error, 'Mic permission denied'));
    }
  }, [sendVoiceMessage, stopPlayback, unlockAudio]);

  const stop = useCallback(() => {
    recorderRef.current?.stop();
    recorderRef.current = null;
    setIsRecording(false);
  }, []);

  // Ctrl+Space hold-to-talk
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.code === 'Space' && !e.repeat) {
        e.preventDefault();
        if (!isRecording && !disabled) {
          void start();
        }
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space' && isRecording) {
        e.preventDefault();
        stop();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
    };
  }, [disabled, isRecording, start, stop]);

  const toggle = () => {
    if (disabled && !isRecording) return;
    if (isRecording) stop();
    else void start();
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={toggle}
        disabled={disabled && !isRecording}
        aria-label={isRecording ? 'Stop recording' : 'Record voice message'}
        title={isRecording ? 'Release Ctrl+Space or click to send' : 'Click or hold Ctrl+Space to record'}
        className={
          isRecording
            ? 'shrink-0 w-8 h-8 rounded-lg bg-red-500 text-white flex items-center justify-center animate-pulse'
            : 'shrink-0 w-8 h-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent flex items-center justify-center disabled:opacity-40 transition-colors'
        }
      >
        {isRecording ? <Square size={14} fill="currentColor" /> : <Mic size={16} />}
      </button>
      {error && (
        <p className="absolute -top-6 right-0 text-xs text-destructive whitespace-nowrap">
          {error}
        </p>
      )}
    </div>
  );
}
