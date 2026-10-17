/**
 * Browser-native speech — the voice path with nothing in the middle.
 *
 * `window.SpeechRecognition` (or its `webkit` spelling) turns speech into text
 * and `window.speechSynthesis` turns text back into speech, both on the user's
 * own device. That matters twice over here:
 *
 *  1. **Privacy.** On this path there is no `fetch` in the file at all: audio is
 *     never uploaded, never stored, and the server is not involved. The same
 *     promise the local STT/TTS engines make, taken one step further.
 *  2. **Reach.** It needs no API key, no model download and no cold start, and it
 *     speaks the device's own language — which is what makes voice usable in
 *     Hindi as well as English, and ready for the next languages when they land.
 *
 * Everything degrades quietly: if the browser has neither API, both entry
 * points return `null` and the caller falls back to the server voice endpoints.
 * Nothing in this module ever throws.
 */

/** Which browser speech APIs this device actually has. */
export type SpeechSupport = { recognition: boolean; synthesis: boolean };

/* The Web Speech API is not in every TypeScript lib.dom, so the shapes are
 * declared here rather than relying on the ambient types. */
type RecognitionAlternative = { transcript: string };
type RecognitionResult = {
  isFinal: boolean;
  length: number;
  [index: number]: RecognitionAlternative;
};
type RecognitionEvent = {
  resultIndex: number;
  results: { length: number; [index: number]: RecognitionResult };
};
type RecognitionErrorEvent = { error?: string };

interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

type RecognitionCtor = new () => RecognitionLike;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const scope = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

function synth(): SpeechSynthesis | null {
  if (typeof window === "undefined") return null;
  if (!("speechSynthesis" in window)) return null;
  return window.speechSynthesis;
}

/** Feature-detect once, on the client; never assume. */
export function speechSupport(): SpeechSupport {
  const hasSynthesis =
    typeof window !== "undefined" && typeof window.SpeechSynthesisUtterance === "function" && synth() !== null;
  return { recognition: recognitionCtor() !== null, synthesis: hasSynthesis };
}

/** Site locale (`en` | `hi`) → the BCP-47 tag the device expects. */
export function speechLang(locale: string): string {
  return locale === "hi" ? "hi-IN" : "en-IN";
}

/** A live listening session; `stop()` finishes it and still reports the words. */
export type ListenSession = { stop: () => void };

export type ListenHandlers = {
  /** Site locale the user is browsing in — decides the expected language. */
  locale: string;
  /** Words so far, including the not-yet-final ones. */
  onInterim?: (text: string) => void;
  /** The final transcript, once the device has settled on one. */
  onResult: (text: string) => void;
  /** `not-allowed` (mic blocked), `no-speech`, `network`, `aborted`, … */
  onError?: (code: string) => void;
  /** Fires once the session closes, however it ended. */
  onEnd?: () => void;
};

/**
 * Listen once. Returns `null` when the browser cannot do it (so the caller can
 * use the server recorder instead).
 */
export function startListening(handlers: ListenHandlers): ListenSession | null {
  const Ctor = recognitionCtor();
  if (!Ctor) return null;

  let recognition: RecognitionLike;
  try {
    recognition = new Ctor();
  } catch {
    return null;
  }

  const lang = speechLang(handlers.locale);
  let finalText = "";
  let interimText = "";
  let stopped = false;
  let failed = false;

  recognition.lang = lang;
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.onresult = (event) => {
    if (!event || !event.results) return;
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      if (!result) continue;
      const words = result[0]?.transcript ?? "";
      if (result.isFinal) finalText += words;
      else interimText = words;
    }
    const soFar = `${finalText}${interimText}`.trim();
    if (soFar && handlers.onInterim) handlers.onInterim(soFar);
  };

  recognition.onerror = (event) => {
    const code = event?.error || "error";
    // A tap on stop can surface as `aborted`/`no-speech` — that is the user's
    // own doing, not a failure worth reporting back to them.
    if (stopped && (code === "aborted" || code === "no-speech")) return;
    failed = true;
    if (handlers.onError) handlers.onError(code);
  };

  recognition.onend = () => {
    // `onend` always fires last — after an error too. Report the words once.
    const spoken = (finalText || interimText).trim();
    if (!failed && spoken) handlers.onResult(spoken);
    if (handlers.onEnd) handlers.onEnd();
  };

  try {
    recognition.start();
  } catch {
    // Some browsers throw if a session is already live; treat as unsupported.
    return null;
  }

  return {
    stop: () => {
      stopped = true;
      try {
        recognition.stop();
      } catch {
        try {
          recognition.abort();
        } catch {
          /* already closed */
        }
      }
    },
  };
}

export type SpeakHandlers = {
  onStart?: () => void;
  onEnd?: () => void;
  onError?: () => void;
};

/** A live utterance; `stop()` cuts it off mid-sentence. */
export type SpeakSession = { stop: () => void };

/**
 * Say something out loud in the user's language, on the device.
 * Returns `null` when synthesis is unavailable or the text is empty.
 */
export function speak(text: string, locale: string, handlers: SpeakHandlers = {}): SpeakSession | null {
  const engine = synth();
  if (!engine || !text || !text.trim()) return null;

  // One voice at a time — a second tap replaces the first rather than stacking.
  try {
    engine.cancel();
  } catch {
    /* nothing queued */
  }

  let utterance: SpeechSynthesisUtterance;
  try {
    utterance = new window.SpeechSynthesisUtterance(text.trim().slice(0, 4000));
  } catch {
    return null;
  }

  const tag = speechLang(locale);
  const want = tag.slice(0, 2).toLowerCase();
  utterance.lang = tag;
  utterance.rate = 0.98;

  // Prefer a voice that actually speaks the language; fall back to the tag.
  try {
    const voices = engine.getVoices() || [];
    const match = voices.find((v) => (v.lang || "").toLowerCase().startsWith(want));
    if (match) utterance.voice = match;
  } catch {
    /* voice list is advisory only */
  }

  utterance.onstart = () => handlers.onStart?.();
  utterance.onend = () => handlers.onEnd?.();
  utterance.onerror = () => handlers.onError?.();

  try {
    engine.speak(utterance);
  } catch {
    return null;
  }

  return {
    stop: () => {
      try {
        engine.cancel();
      } catch {
        /* already silent */
      }
    },
  };
}

/** Silence anything mid-sentence (e.g. leaving the page). */
export function stopSpeaking(): void {
  const engine = synth();
  if (!engine) return;
  try {
    engine.cancel();
  } catch {
    /* nothing to stop */
  }
}
