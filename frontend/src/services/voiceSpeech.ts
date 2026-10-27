export type SpeechRecognitionFailure = (message: string) => void;

type SpeechResult = { isFinal: boolean; [index: number]: { transcript: string } };
type SpeechResultEvent = { resultIndex: number; results: ArrayLike<SpeechResult> };
type SpeechErrorEvent = { error: string };

interface BrowserSpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onerror: ((event: SpeechErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

interface BrowserSpeechRecognitionConstructor {
  new(): BrowserSpeechRecognition;
}

declare global {
  interface Window {
    SpeechRecognition?: BrowserSpeechRecognitionConstructor;
    webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
  }
}

export interface VoiceIO {
  isRecognitionSupported(): boolean;
  requestMicrophonePermission(): Promise<void>;
  listen(language: string, onUtterance: (text: string) => void, onError: SpeechRecognitionFailure, onEnd: () => void): void;
  stopListening(): void;
  speak(text: string, language: string, onEnd: () => void, onError: SpeechRecognitionFailure): boolean;
  stopSpeaking(): void;
}

export class BrowserVoiceIO implements VoiceIO {
  private recognition: BrowserSpeechRecognition | null = null;
  private microphoneStream: MediaStream | null = null;

  isRecognitionSupported(): boolean {
    return Boolean(window.SpeechRecognition ?? window.webkitSpeechRecognition);
  }

  async requestMicrophonePermission(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("This browser cannot request microphone access. Use a supported browser on HTTPS or localhost.");
    }
    this.releaseMicrophone();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    // Keep the permission stream only until recognition has started. The
    // browser recognition service owns the live capture; holding a second
    // getUserMedia capture open can conflict with mobile speech services.
    this.microphoneStream = stream;
  }

  listen(language: string, onUtterance: (text: string) => void, onError: SpeechRecognitionFailure, onEnd: () => void): void {
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) throw new Error("Speech recognition is not supported in this browser.");
    const recognition = new Recognition();
    recognition.lang = language;
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const transcripts: string[] = [];
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (result?.isFinal && result[0]?.transcript.trim()) transcripts.push(result[0].transcript.trim());
      }
      const transcript = transcripts.join(" ").trim();
      if (transcript) onUtterance(transcript);
    };
    recognition.onerror = (event) => onError(event.error);
    recognition.onend = onEnd;
    this.recognition = recognition;
    recognition.start();
    this.releaseMicrophone();
  }

  stopListening(): void {
    const recognition = this.recognition;
    this.recognition = null;
    if (recognition) {
      recognition.onend = null;
      recognition.onresult = null;
      recognition.onerror = null;
      try {
        recognition.abort();
      } catch {
        // The browser may already have ended its microphone session.
      }
    }
    this.releaseMicrophone();
  }

  private releaseMicrophone(): void {
    this.microphoneStream?.getTracks().forEach((track) => track.stop());
    this.microphoneStream = null;
  }

  speak(text: string, language: string, onEnd: () => void, onError: SpeechRecognitionFailure): boolean {
    const synthesis = window.speechSynthesis;
    if (!synthesis || typeof SpeechSynthesisUtterance === "undefined") return false;
    const speech = new SpeechSynthesisUtterance(text);
    speech.lang = language;
    const voices = synthesis.getVoices();
    const voice = voices.find((candidate) => candidate.lang.toLowerCase() === language.toLowerCase())
      ?? voices.find((candidate) => candidate.lang.toLowerCase().startsWith(language.slice(0, 2).toLowerCase()));
    if (voice) speech.voice = voice;
    speech.onend = onEnd;
    speech.onerror = (event) => onError(event.error);
    synthesis.cancel();
    synthesis.speak(speech);
    return true;
  }

  stopSpeaking(): void {
    window.speechSynthesis?.cancel();
  }
}
