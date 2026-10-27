import { LoaderCircle, Mic, Pause, Play, RotateCcw, Square, Volume2 } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { BrowserVoiceIO, type VoiceIO } from "../services/voiceSpeech";
import { Button, Card, Notice } from "./Ui";

export type VoiceState = "idle" | "requesting_permission" | "reconnecting" | "listening" | "processing" | "speaking" | "paused" | "error";

const statusLabels: Record<VoiceState, string> = {
  idle: "Tap to start",
  requesting_permission: "Requesting microphone permission…",
  reconnecting: "Reconnecting microphone…",
  listening: "I'm listening…",
  processing: "Understanding your request…",
  speaking: "Responding…",
  paused: "Assistant paused",
  error: "Assistant error",
};

export function VoiceAssistant({ voiceIO: providedVoiceIO }: { voiceIO?: VoiceIO } = {}) {
  const navigate = useNavigate();
  const [state, setState] = useState<VoiceState>("idle");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [language, setLanguage] = useState("en-IN");
  const [warning, setWarning] = useState("");
  const [textCommand, setTextCommand] = useState("");
  const voiceIORef = useRef<VoiceIO | null>(null);
  if (!voiceIORef.current) voiceIORef.current = providedVoiceIO ?? new BrowserVoiceIO();
  const voiceIO = voiceIORef.current;
  const activeRef = useRef(false);
  const processingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const retryRef = useRef<{ request_id: string; utterance: string; language: "en" | "te" | "mixed" } | null>(null);
  const mountedRef = useRef(true);
  const reconnectTimerRef = useRef<number | null>(null);
  const sessionGenerationRef = useRef(0);

  const clearReconnectTimer = () => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  };

  const stopRecognition = () => {
    clearReconnectTimer();
    voiceIO.stopListening();
  };

  const startListening = () => {
    if (!activeRef.current || !mountedRef.current) return;
    const generation = sessionGenerationRef.current;
    if (!voiceIO.isRecognitionSupported()) {
      activeRef.current = false;
      setError("Speech recognition is not supported in this browser. Try Chrome or Edge, or use the text command below.");
      setState("error");
      return;
    }
    try {
      voiceIO.listen(language === "te-IN" ? "te-IN" : "en-IN", (utterance) => {
        if (generation !== sessionGenerationRef.current || !activeRef.current || !mountedRef.current) return;
        if (processingRef.current) return;
        if (/^(?:assistant\s+)?pause(?:\s+(?:assistant|chey|cheyyi))?[.! ]*$/i.test(utterance.trim())) {
          pause();
          setMessage("Assistant paused.");
          return;
        }
        if (/^(?:assistant\s+)?stop(?:\s+assistant|\s+chey|\s+cheyyi)?[.! ]*$/i.test(utterance.trim())) {
          stop();
          setMessage("Assistant stopped.");
          return;
        }
        processingRef.current = true;
        stopRecognition();
        void runCommand(utterance, true);
      }, (speechError) => {
        if (generation !== sessionGenerationRef.current || !activeRef.current) return;
        // Chrome and Edge report no-speech after a quiet period. That is a
        // recoverable end-of-utterance condition, not a failed session.
        if (speechError === "no-speech" || speechError === "aborted") {
          setState("reconnecting");
          return;
        }
        activeRef.current = false;
        processingRef.current = false;
        stopRecognition();
        const detail = speechError === "not-allowed" || speechError === "service-not-allowed"
        ? "Microphone permission was denied. Allow microphone access in your browser and retry."
        : speechError === "audio-capture"
        ? "The microphone could not be accessed. Check that it is connected and not being used exclusively by another app."
        : speechError === "network"
        ? "Speech recognition lost its network connection. Retry or use the text command below."
        : `Speech recognition failed: ${speechError}. Retry or use the text command below.`;
        setError(detail);
        setState("error");
      }, () => {
        if (generation === sessionGenerationRef.current && activeRef.current && !processingRef.current && !document.hidden) {
          clearReconnectTimer();
          setState("reconnecting");
          reconnectTimerRef.current = window.setTimeout(() => {
            reconnectTimerRef.current = null;
            startListening();
          }, 250);
        }
      });
      setError("");
      setState("listening");
    } catch (cause) {
      activeRef.current = false;
      stopRecognition();
      setError(cause instanceof Error ? cause.message : "Could not start speech recognition.");
      setState("error");
    }
  };

  const beginSession = async () => {
    if (!voiceIO.isRecognitionSupported()) {
      setError("Speech recognition is not supported in this browser. Try Chrome or Edge, or use the text command below.");
      setState("error");
      return;
    }
    setError("");
    setMessage("");
    clearReconnectTimer();
    setState("requesting_permission");
    try {
      await voiceIO.requestMicrophonePermission();
      if (!mountedRef.current) return;
      if (document.hidden) {
        stopRecognition();
        setState("paused");
        return;
      }
      sessionGenerationRef.current += 1;
      activeRef.current = true;
      startListening();
    } catch (cause) {
      activeRef.current = false;
      const detail = cause instanceof DOMException && cause.name === "NotAllowedError"
        ? "Microphone permission was denied. Allow microphone access in your browser, then retry."
        : cause instanceof Error ? `Microphone could not be started: ${cause.message}` : "Microphone could not be started.";
      setError(detail);
      setState("error");
    }
  };

  const speakResponse = (text: string, navigateTo: string | null, shouldSpeak: boolean) => {
    const generation = sessionGenerationRef.current;
    if (!shouldSpeak) {
      setState(activeRef.current ? "listening" : "idle");
      if (activeRef.current) startListening();
      if (navigateTo) navigate(navigateTo);
      return;
    }
    setState("speaking");
    const started = voiceIO.speak(text, language === "mixed" ? "en-IN" : language, () => {
      if (generation !== sessionGenerationRef.current || !mountedRef.current) return;
      if (navigateTo) {
        activeRef.current = false;
        stopRecognition();
        setState("idle");
        navigate(navigateTo);
      } else if (activeRef.current) {
        startListening();
      } else {
        setState("idle");
      }
    }, (speechError) => {
      if (generation !== sessionGenerationRef.current || !activeRef.current) return;
      activeRef.current = false;
      stopRecognition();
      setError(`Speech synthesis failed: ${speechError}. The response is available as text.`);
      setState("error");
    });
    if (!started) {
      if (generation !== sessionGenerationRef.current) return;
      if (navigateTo) {
        activeRef.current = false;
        stopRecognition();
        setState("idle");
        navigate(navigateTo);
        return;
      }
      setState(activeRef.current ? "listening" : "idle");
      if (activeRef.current) startListening();
    }
  };

  const runCommand = async (utterance: string, fromVoice: boolean, request?: { request_id: string; utterance: string; language: "en" | "te" | "mixed" }) => {
    const responseLanguage = language === "te-IN" ? "te" : language === "mixed" ? "mixed" : "en";
    const payload = request ?? { request_id: crypto.randomUUID(), utterance, language: responseLanguage };
    const resumeVoice = activeRef.current;
    const generation = sessionGenerationRef.current;
    if (!fromVoice) stopRecognition();
    retryRef.current = payload;
    processingRef.current = true;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError("");
    setState("processing");
    try {
      const response = await api.voiceCommand(payload, controller.signal);
      if (controller.signal.aborted || !mountedRef.current || generation !== sessionGenerationRef.current) return;
      retryRef.current = null;
      setMessage(response.message);
      setWarning(response.warning ?? "");
      processingRef.current = false;
      speakResponse(response.message, response.navigate_to ?? null, fromVoice || resumeVoice);
    } catch (cause) {
      if (controller.signal.aborted || !mountedRef.current) return;
      processingRef.current = false;
      setError(cause instanceof Error ? cause.message : "The voice command failed.");
      setState("error");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  };

  const pause = () => {
    sessionGenerationRef.current += 1;
    activeRef.current = false;
    processingRef.current = false;
    abortRef.current?.abort();
    abortRef.current = null;
    stopRecognition();
    voiceIO.stopSpeaking();
    setState("paused");
  };

  const stop = () => {
    sessionGenerationRef.current += 1;
    activeRef.current = false;
    processingRef.current = false;
    retryRef.current = null;
    abortRef.current?.abort();
    abortRef.current = null;
    stopRecognition();
    voiceIO.stopSpeaking();
    setError("");
    setState("idle");
  };

  const submitText = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const command = textCommand.trim();
    if (!command || processingRef.current) return;
    setTextCommand("");
    const responseLanguage = language === "te-IN" ? "te" : language === "mixed" ? "mixed" : "en";
    void runCommand(command, false, { request_id: crypto.randomUUID(), utterance: command, language: responseLanguage });
  };

  useEffect(() => {
    mountedRef.current = true;
    const pauseWhenHidden = () => {
      if (!document.hidden || !activeRef.current) return;
      sessionGenerationRef.current += 1;
      activeRef.current = false;
      processingRef.current = false;
      abortRef.current?.abort();
      abortRef.current = null;
      stopRecognition();
      voiceIO.stopSpeaking();
      setState("paused");
    };
    document.addEventListener("visibilitychange", pauseWhenHidden);
    return () => {
      document.removeEventListener("visibilitychange", pauseWhenHidden);
      mountedRef.current = false;
      sessionGenerationRef.current += 1;
      activeRef.current = false;
      clearReconnectTimer();
      abortRef.current?.abort();
      stopRecognition();
      voiceIO.stopSpeaking();
    };
  }, []);

  const sessionActive = state === "listening" || state === "reconnecting" || state === "processing" || state === "speaking" || (state === "error" && activeRef.current);

  return <Card className="mb-6 overflow-hidden border-violet-200 bg-gradient-to-br from-white via-violet-50/50 to-fuchsia-50/70">
    <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-4">
        <span className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl ${state === "listening" ? "bg-violet-600 text-white shadow-lg shadow-violet-200" : "bg-violet-100 text-violet-700"}`}>
          {state === "processing" ? <LoaderCircle className="animate-spin" size={25} /> : <Mic size={25} />}
        </span>
        <div className="min-w-0">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-violet-600">StyleMate voice</p>
          <h3 className="mt-1 text-xl font-bold text-slate-950">Your stylist, hands-free</h3>
          <p className="mt-1 text-sm text-slate-600" role="status" aria-live="polite">{statusLabels[state]}</p>
          {state === "listening" && <div className="mt-2 flex h-5 items-center gap-1" aria-label="Microphone is actively listening">
            {[0, 1, 2, 3, 4, 5, 6].map((bar) => <span key={bar} className="voice-wave-bar" style={{ animationDelay: `${bar * 90}ms` }} />)}
          </div>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {(state === "idle" || (state === "error" && !activeRef.current)) && <Button onClick={() => void beginSession()}><Mic size={17} />Start Voice Assistant</Button>}
        {(state === "requesting_permission" || state === "reconnecting") && <Button disabled><LoaderCircle className="animate-spin" size={17} />{state === "requesting_permission" ? "Allow microphone…" : "Reconnecting…"}</Button>}
        {state === "paused" && <Button onClick={() => void beginSession()}><Play size={17} />Resume</Button>}
        {sessionActive && <Button variant="secondary" onClick={pause}><Pause size={17} />Pause</Button>}
        {sessionActive && <Button variant="quiet" onClick={stop}><Square size={16} />Stop Assistant</Button>}
        {state === "error" && retryRef.current && <Button variant="secondary" onClick={() => { const retry = retryRef.current; if (retry) void runCommand(retry.utterance, true, retry); }}><RotateCcw size={16} />Retry command</Button>}
      </div>
    </div>
    <div className="mt-5 grid gap-4 border-t border-violet-100 pt-4 md:grid-cols-[1fr_auto] md:items-end">
      <form onSubmit={submitText} className="flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor="voice-command">Type a StyleMate command</label>
        <input id="voice-command" value={textCommand} onChange={(event) => setTextCommand(event.target.value)} placeholder="Or type: show my blue shirts…" className="focus-ring min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm" />
        <Button variant="secondary" type="submit" disabled={!textCommand.trim() || state === "processing"}>Send command</Button>
      </form>
      <label className="flex items-center gap-2 text-xs font-semibold text-slate-600">Speech language
        <select aria-label="Speech language" value={language} onChange={(event) => setLanguage(event.target.value)} disabled={sessionActive} className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-xs">
          <option value="en-IN">English (India)</option>
          <option value="te-IN">Telugu</option>
          <option value="mixed">Telugu-English mix</option>
        </select>
      </label>
    </div>
    {error && <Notice tone="error"><span>{error}</span></Notice>}
    {warning && <Notice tone="info"><span>{warning}</span></Notice>}
    {!error && <p className="mt-3 text-xs leading-5 text-slate-500">Microphone access is requested only when you start. Voice recognition depends on browser support and an internet connection. It stops if you pause, stop, leave this page, background the tab, or lock your phone.</p>}
    {message && <div className="mt-4 flex items-start gap-2 rounded-2xl bg-white/80 p-4 text-sm leading-6 text-slate-700"><Volume2 className="mt-1 shrink-0 text-violet-600" size={17} /><p>{message}</p></div>}
  </Card>;
}
