"use client";
import { useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Square, Zap, Sparkles, Mic, MicOff, Loader } from "lucide-react";

interface Props {
  onStart: (topic: string, maxSteps: number) => void;
  onCancel: () => void;
  isRunning: boolean;
}

const EXAMPLE_TOPICS = [
  "Vegetable seller in rural Maharashtra, earning ₹15k/month",
  "Tailor in tier-2 city, ₹25k/month, needs sewing machine loan",
  "Small dairy farmer in Gujarat, 3 cows, ₹20k/month",
];

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type VoiceState = "idle" | "recording" | "transcribing" | "error";

export default function TopicInput({ onStart, onCancel, isRunning }: Props) {
  const [topic, setTopic] = useState("");
  const [maxSteps, setMaxSteps] = useState(4);
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [voiceMsg, setVoiceMsg] = useState("");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const startRecording = useCallback(async () => {
    setVoiceMsg("");
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
            setVoiceMsg("✓ Transcribed — review and submit");
          } else {
            setVoiceMsg(json.warning ?? "Could not understand audio — please type instead.");
          }
        } catch {
          setVoiceMsg("Voice unavailable right now — please type instead.");
        }
        setVoiceState("idle");
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setVoiceState("recording");
    } catch {
      setVoiceMsg("Microphone access denied — please type instead.");
      setVoiceState("error");
      setTimeout(() => setVoiceState("idle"), 3000);
    }
  }, []);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
  }, []);

  const handleMicClick = () => {
    if (isRunning) return;
    if (voiceState === "recording") stopRecording();
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
          padding: "28px 32px 20px",
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
              GrameenAI Advisor
            </h1>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "1px" }}>
              Financial advisory for micro-entrepreneurs • Multi-agent AI
            </p>
          </div>
        </div>
      </div>

      {/* Input Area */}
      <div style={{ padding: "24px 32px" }}>
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
            placeholder="Describe your business — what you sell, roughly how much you earn, and where you're located"
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
            title={voiceState === "recording" ? "Stop recording" : "Speak your business description"}
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
            <motion.p
              key="voice-msg"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              style={{
                fontSize: "0.76rem",
                color: voiceMsg.startsWith("✓") ? "var(--success)" : voiceState === "recording" ? "#f87171" : "var(--text-muted)",
                marginBottom: "8px",
                paddingLeft: "2px",
              }}
            >
              {voiceState === "recording" ? "🎙 Recording… click mic again to stop"
                : voiceState === "transcribing" ? "Transcribing…"
                : voiceMsg}
            </motion.p>
          )}
        </AnimatePresence>

        {/* Example topics */}
        <div style={{ marginBottom: "20px" }}>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Quick examples
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
            {EXAMPLE_TOPICS.map((t) => (
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

        {/* Footer row */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
          {/* Steps selector */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <Zap size={13} color="var(--text-muted)" />
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Research depth:</span>
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
            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>steps</span>
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
                <Square size={13} /> Stop Research
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
                <Search size={14} /> Start Research
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}
