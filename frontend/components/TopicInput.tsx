"use client";
import { useState, useRef, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Square, Zap, Sparkles, Mic, MicOff, Loader, Check, ShieldCheck } from "lucide-react";
import { API_BASE } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { speechSupport, startListening, type ListenSession } from "@/lib/speech";

interface Props {
  onStart: (topic: string, maxSteps: number) => void;
  onCancel: () => void;
  isRunning: boolean;
  /** Ask the user to approve the plan before the research starts. */
  gatesOn: boolean;
  onGatesChange: (on: boolean) => void;
}

const EXAMPLE_KEYS = ["input.example1", "input.example2", "input.example3"] as const;
const EXAMPLE_FALLBACK = [
  "Vegetable seller in rural Maharashtra, earning ₹15k/month",
  "Tailor in tier-2 city, ₹25k/month, needs sewing machine loan",
  "Small dairy farmer in Gujarat, 3 cows, ₹20k/month",
];

const BACKEND_URL = API_BASE;

type VoiceState = "idle" | "recording" | "transcribing" | "error";

interface VoiceCap {
  whisper_model?: string;
  stt_default: string;
  tts_default: string;
  private_by_default: boolean;
}

const ENGINE_LABELS: Record<string, string> = {
  elevenlabs: "ElevenLabs",
  faster_whisper: "local (no key)",
  speech_recognition: "Google free",
  piper: "local (no key)",
  huggingface: "Hugging Face",
  pyttsx3: "device",
  none: "unavailable",
};

const engineLabel = (key: string): string => ENGINE_LABELS[key] ?? key;

export default function TopicInput({ onStart, onCancel, isRunning, gatesOn, onGatesChange }: Props) {
  const { t, locale } = useI18n();
  const examples = EXAMPLE_KEYS.map((key, i) => t(key) || EXAMPLE_FALLBACK[i]);
  const [topic, setTopic] = useState("");
  const [maxSteps, setMaxSteps] = useState(4);
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [voiceMsg, setVoiceMsg] = useState("");
  const [voiceOk, setVoiceOk] = useState(false);
  const [voiceCap, setVoiceCap] = useState<VoiceCap | null>(null);
  /** True when this device can turn speech into text by itself (no upload). */
  const [deviceSpeech, setDeviceSpeech] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const listenRef = useRef<ListenSession | null>(null);

  // Feature-detect the on-device path before offering it (SSR-safe: client only).
  useEffect(() => {
    const support = speechSupport();
    setDeviceSpeech(support.recognition);
  }, []);

  // Reveal which engines back the voice button (privacy-by-default claim).
  useEffect(() => {
    let cancelled = false;
    fetch(`${BACKEND_URL}/api/voice/status`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: VoiceCap | null) => {
        if (d && !cancelled) setVoiceCap(d);
      })
      .catch(() => {
        /* status is informational — no need for a global error surface */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const startRecording = useCallback(async () => {
    setVoiceMsg("");
    setVoiceOk(false);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        // Stop all tracks to release the mic
        stream.getTracks().forEach((t) => t.stop());
        setVoiceState("transcribing");
        try {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          const fd = new FormData();
          fd.append("file", blob, "recording.webm");
          const res = await fetch(`${BACKEND_URL}/api/voice/transcribe`, { method: "POST", body: fd });
          const json = await res.json();
          if (json.text) {
            setTopic(json.text);
            setVoiceMsg(t("mic.done"));
            setVoiceOk(true);
          } else {
            setVoiceMsg(json.warning ?? t("mic.unheard"));
            setVoiceOk(false);
          }
        } catch {
          setVoiceMsg(t("mic.unavailable"));
          setVoiceOk(false);
        }
        setVoiceState("idle");
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setVoiceState("recording");
    } catch {
      setVoiceMsg(t("mic.denied"));
      setVoiceState("error");
      setTimeout(() => setVoiceState("idle"), 3000);
    }
  }, [t]);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
  }, []);

  // On-device listening: the words are typed into the box as they are spoken and
  // the audio never leaves the handset. Falls through to the server recorder
  // when the browser cannot do it.
  const startBrowserListen = useCallback(() => {
    setVoiceMsg("");
    setVoiceOk(false);
    const session = startListening({
      locale,
      onInterim: (text) => setTopic(text),
      onResult: (text) => {
        setTopic(text);
        setVoiceMsg(t("mic.done"));
        setVoiceOk(true);
      },
      onError: (code) => {
        const blocked = code === "not-allowed" || code === "service-not-allowed";
        setVoiceMsg(blocked ? t("mic.denied") : t("mic.unheard"));
        setVoiceOk(false);
      },
      onEnd: () => {
        listenRef.current = null;
        setVoiceState("idle");
      },
    });
    if (!session) {
      setVoiceMsg(t("mic.unavailable"));
      setVoiceState("error");
      setTimeout(() => setVoiceState("idle"), 3000);
      return;
    }
    listenRef.current = session;
    setVoiceState("recording");
  }, [locale, t]);

  const handleMicClick = () => {
    if (isRunning) return;
    if (voiceState === "recording") {
      if (listenRef.current) listenRef.current.stop();
      else stopRecording();
      return;
    }
    if (deviceSpeech) startBrowserListen();
    else startRecording();
  };

  const micColor =
    voiceState === "recording" ? "#f87171"
    : voiceState === "transcribing" ? "var(--accent)"
    : "var(--text-muted)";

  return (
    <motion.div
      initial={{ opacity: 0, y: -32 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      style={{
        width: "100%",
        maxWidth: "760px",
        margin: "0 auto",
        background: "var(--bg-card)",
        borderRadius: "var(--radius-xl)",
        border: "1px solid var(--border-bright)",
        boxShadow: "0 24px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(79,142,247,0.05)",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "clamp(20px, 5vw, 28px) clamp(16px, 6vw, 32px) 20px",
          borderBottom: "1px solid var(--border)",
          background: "linear-gradient(135deg, rgba(79,142,247,0.06) 0%, transparent 60%)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
          <div
            style={{
              width: "36px", height: "36px", borderRadius: "10px",
              background: "linear-gradient(135deg, var(--accent), var(--accent2))",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <Sparkles size={18} color="#fff" />
          </div>
          <div>
            <h1 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
              {t("brand.name")}
            </h1>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "1px" }}>
              {t("brand.tagline")}
            </p>
          </div>
        </div>
      </div>

      {/* Input Area */}
      <div style={{ padding: "24px clamp(16px, 6vw, 32px)" }}>
        {/* Textarea + mic row */}
        <div style={{ position: "relative", marginBottom: "8px" }}>
          <textarea
            suppressHydrationWarning
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !isRunning && topic.trim()) {
                e.preventDefault();
                onStart(topic.trim(), maxSteps);
              }
            }}
            placeholder={t("input.placeholder")}
            disabled={isRunning}
            rows={3}
            style={{
              width: "100%",
              background: "var(--bg-surface)",
              border: "1px solid var(--border-bright)",
              borderRadius: "var(--radius-md)",
              padding: "14px 50px 14px 16px",
              fontSize: "0.92rem",
              color: "var(--text-primary)",
              resize: "none",
              outline: "none",
              lineHeight: "1.6",
              transition: "border-color 0.2s, box-shadow 0.2s",
              fontFamily: "inherit",
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = "var(--accent)";
              e.currentTarget.style.boxShadow = "0 0 0 3px var(--accent-glow)";
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = "var(--border-bright)";
              e.currentTarget.style.boxShadow = "none";
            }}
          />
          {/* Mic button — overlaid top-right of textarea */}
          <motion.button
            id="voice-mic-btn"
            onClick={handleMicClick}
            disabled={isRunning || voiceState === "transcribing"}
            title={voiceState === "recording" ? t("mic.stop") : t("mic.speak")}
            aria-label={voiceState === "recording" ? t("mic.stopAria") : t("mic.record")}
            whileTap={{ scale: 0.9 }}
            animate={voiceState === "recording" ? { boxShadow: ["0 0 0 0px rgba(248,113,113,0.4)", "0 0 0 8px rgba(248,113,113,0)"] } : {}}
            transition={voiceState === "recording" ? { duration: 1, repeat: Infinity } : {}}
            style={{
              position: "absolute",
              top: "10px",
              right: "10px",
              width: "32px",
              height: "32px",
              borderRadius: "50%",
              border: voiceState === "recording" ? "1.5px solid #f87171" : "1.5px solid var(--border)",
              background: voiceState === "recording" ? "rgba(248,113,113,0.1)" : "var(--bg-surface)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: isRunning || voiceState === "transcribing" ? "not-allowed" : "pointer",
              opacity: isRunning ? 0.4 : 1,
              transition: "all 0.2s",
            }}
          >
            {voiceState === "transcribing"
              ? <Loader size={14} color="var(--accent)" style={{ animation: "spin 1s linear infinite" }} />
              : voiceState === "recording"
                ? <MicOff size={14} color="#f87171" />
                : <Mic size={14} color={micColor} />}
          </motion.button>
        </div>

        {/* Voice status/hint */}
        <AnimatePresence>
          {(voiceState !== "idle" || voiceMsg) && (
            <motion.div
              key="voice-msg"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                fontSize: "0.76rem",
                color:
                  voiceOk ? "var(--success)"
                  : voiceState === "recording" ? "#f87171"
                  : "var(--text-muted)",
                marginBottom: "8px",
                paddingLeft: "2px",
                overflow: "hidden",
              }}
            >
              {voiceState === "recording" && <Mic size={12} color="#f87171" />}
              {voiceState === "transcribing" && (
                <Loader size={12} color="var(--accent)" style={{ animation: "spin 1s linear infinite" }} />
              )}
              {voiceOk && <Check size={12} color="var(--success)" />}
              <span>
                {voiceState === "recording" ? t("mic.recording")
                  : voiceState === "transcribing" ? t("mic.transcribing")
                  : voiceMsg}
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Example topics */}
        <div style={{ marginBottom: "20px" }}>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Quick examples
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
            {examples.map((t) => (
              <button
                key={t}
                onClick={() => !isRunning && setTopic(t)}
                disabled={isRunning}
                style={{
                  fontSize: "0.76rem", color: "var(--text-secondary)", background: "var(--bg-surface)",
                  border: "1px solid var(--border)", borderRadius: "20px", padding: "4px 12px",
                  cursor: isRunning ? "not-allowed" : "pointer", transition: "all 0.15s", opacity: isRunning ? 0.4 : 1,
                }}
                onMouseEnter={(e) => { if (!isRunning) { e.currentTarget.style.borderColor = "var(--accent)"; e.currentTarget.style.color = "var(--accent)"; } }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--text-secondary)"; }}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Voice privacy & engine chip (from /api/voice/status) */}
        {(deviceSpeech || voiceCap) && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "8px 12px",
              marginBottom: "16px",
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-md)",
            }}
          >
            <ShieldCheck
              size={14}
              color={deviceSpeech || voiceCap?.private_by_default ? "var(--success)" : "var(--accent)"}
              aria-hidden="true"
            />
            <span style={{ fontSize: "0.74rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
              {deviceSpeech ? (
                <>{t("voice.device")}</>
              ) : voiceCap?.private_by_default ? (
                <>
                  {t("voice.private")}{" "}
                  {t("voice.stt")}: <strong style={{ color: "var(--text-secondary)", fontWeight: 600 }}>
                    {engineLabel(voiceCap.stt_default)}
                  </strong>{" "}
                  · {t("voice.tts")}: <strong style={{ color: "var(--text-secondary)", fontWeight: 600 }}>
                    {engineLabel(voiceCap.tts_default)}
                  </strong>
                </>
              ) : (
                <>
                  {t("voice.cloud")}
                </>
              )}
            </span>
          </div>
        )}

        {/* Footer row */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
            {/* Steps selector */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Zap size={13} color="var(--text-muted)" />
              <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{t("input.depth")}</span>
              <div style={{ display: "flex", gap: "4px" }}>
                {[1, 2, 3, 4, 5, 6].map((n) => (
                  <button
                    key={n}
                    onClick={() => setMaxSteps(n)}
                    style={{
                      width: "30px", height: "30px", borderRadius: "8px", fontSize: "0.8rem", fontWeight: 600,
                      border: `1px solid ${maxSteps === n ? "var(--accent)" : "var(--border)"}`,
                      background: maxSteps === n ? "var(--accent)" : "transparent",
                      color: maxSteps === n ? "#fff" : "var(--text-muted)",
                      cursor: "pointer", transition: "all 0.15s",
                    }}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{t("input.steps")}</span>
            </div>

            {/* Approval gate — the user sees the plan before anything is spent */}
            <button
              type="button"
              role="switch"
              aria-checked={gatesOn}
              disabled={isRunning}
              title={t("gate.toggleHint")}
              onClick={() => onGatesChange(!gatesOn)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "6px 11px",
                borderRadius: "999px",
                border: `1px solid ${gatesOn ? "var(--accent)" : "var(--border)"}`,
                background: gatesOn ? "rgba(79,142,247,0.12)" : "transparent",
                color: gatesOn ? "var(--accent)" : "var(--text-muted)",
                fontSize: "0.74rem",
                fontWeight: 700,
                cursor: isRunning ? "not-allowed" : "pointer",
                opacity: isRunning ? 0.6 : 1,
              }}
            >
              <ShieldCheck size={13} />
              {t("gate.toggle")}
            </button>
          </div>

          {/* Action button */}
          <AnimatePresence mode="wait">
            {isRunning ? (
              <motion.button
                key="cancel"
                initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
                whileTap={{ scale: 0.95 }}
                onClick={onCancel}
                style={{
                  display: "flex", alignItems: "center", gap: "8px",
                  background: "rgba(248, 113, 113, 0.15)", border: "1px solid rgba(248, 113, 113, 0.4)",
                  color: "var(--error)", padding: "9px 18px", borderRadius: "var(--radius-md)",
                  fontSize: "0.86rem", fontWeight: 600, cursor: "pointer",
                }}
              >
                <Square size={13} /> {t("input.stop")}
              </motion.button>
            ) : (
              <motion.button
                key="start"
                initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
                whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
                onClick={() => topic.trim() && onStart(topic.trim(), maxSteps)}
                disabled={!topic.trim()}
                style={{
                  display: "flex", alignItems: "center", gap: "8px",
                  background: topic.trim() ? "linear-gradient(135deg, var(--accent), var(--accent2))" : "var(--bg-surface)",
                  border: "1px solid transparent",
                  color: topic.trim() ? "#fff" : "var(--text-muted)",
                  padding: "9px 22px", borderRadius: "var(--radius-md)",
                  fontSize: "0.86rem", fontWeight: 700,
                  cursor: topic.trim() ? "pointer" : "not-allowed",
                  boxShadow: topic.trim() ? "0 4px 20px rgba(79,142,247,0.3)" : "none",
                  transition: "all 0.2s",
                }}
              >
                <Search size={14} /> {t("input.start")}
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}
