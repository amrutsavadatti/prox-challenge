import { useEffect, useRef, useState } from 'react';
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

export function VoiceButton({ disabled }: Props) {
  const sendVoiceMessage = useStore((s) => s.sendVoiceMessage);
  const stopPlayback = useStore((s) => s.stopPlayback);
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const mimeRef = useRef<string>('');

  useEffect(() => {
    return () => {
      recorderRef.current?.stop();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const start = async () => {
    setError(null);
    stopPlayback();

    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Mic not supported in this browser');
      return;
    }
    const mime = pickMime();
    if (!mime) {
      setError('No supported audio format');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      mimeRef.current = mime;
      chunksRef.current = [];
      const rec = new MediaRecorder(stream, { mimeType: mime });
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mime });
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        if (blob.size > 1000) sendVoiceMessage(blob, mime);
      };
      rec.start();
      recorderRef.current = rec;
      setIsRecording(true);
    } catch (err: any) {
      setError(err?.message ?? 'Mic permission denied');
    }
  };

  const stop = () => {
    recorderRef.current?.stop();
    recorderRef.current = null;
    setIsRecording(false);
  };

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
        title={isRecording ? 'Stop' : 'Hold to record (click to start, click again to send)'}
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
