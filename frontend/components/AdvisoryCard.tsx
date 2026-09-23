"use client";
import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, IndianRupee, FileCheck, Target, ArrowRight, CheckSquare, Volume2, Loader, VolumeX, Download, Share2, CheckCircle2, FileText } from "lucide-react";

interface CashFlow {
  [key: string]: string | number;
}

interface AdvisoryData {
  business_summary?: string;
  cash_flow_snapshot?: CashFlow;
  matched_schemes?: string[];
  documents_needed?: string[];
  next_step?: string;
  loan_ready_score?: { score?: number; level?: string; why?: string[] };
}

interface Props {
  report: string;
  topic: string;
  simplified?: string;
}

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type AudioState = "idle" | "loading" | "playing" | "error";

function Sparkles({ size }: { size?: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size || 16} height={size || 16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
      <path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/>
    </svg>
  );
}

function ScoreGauge({ score }: { score: number }) {
  const radius = 44;
  const circ = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  const color =
    clamped >= 80 ? "var(--success)"
    : clamped >= 60 ? "var(--accent)"
    : clamped >= 40 ? "var(--warn)"
    : "var(--error)";
  return (
    <svg width="128" height="128" viewBox="0 0 120 120" aria-label={`Loan-ready score ${clamped} out of 100`}>
      <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" />
      <circle
        cx="60" cy="60" r={radius} fill="none"
        stroke={color} strokeWidth="10" strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={circ * (1 - clamped / 100)}
        transform="rotate(-90 60 60)"
        style={{ transition: "stroke-dashoffset 0.9s ease" }}
      />
      <text x="60" y="57" textAnchor="middle" fill="var(--text-primary)" fontSize="24" fontWeight="800">{clamped}</text>
      <text x="60" y="76" textAnchor="middle" fill="var(--text-muted)" fontSize="9">out of 100</text>
    </svg>
  );
}

export default function AdvisoryCard({ report, topic, simplified }: Props) {
  const [audioState, setAudioState] = useState<AudioState>("idle");
  const [audioMsg, setAudioMsg] = useState("");
  const [copied, setCopied] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  let data: AdvisoryData = {};
  try {
    const cleanJSON = report.replace(/^```(json)?\s*/i, "").replace(/```\s*$/i, "").trim();
    data = JSON.parse(cleanJSON);
  } catch {
    data = { business_summary: "Could not parse report. Raw data: " + report.slice(0, 200) };
  }

  const downloadText = () => {
    const doc = [
      `LOAN READINESS ADVISORY`,
      `Generated for: ${topic}`,
      "",
      "= IN SIMPLE WORDS =",
      simplified || "Not available.",
      "",
      "= FULL ADVISORY =",
      report,
    ].join("\n");
    const blob = new Blob([doc], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${topic.slice(0, 50).replace(/\s+/g, "-").toLowerCase()}-advisory.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(
        (simplified ? `${simplified}\n\n` : "") + report
      );
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  // Build a plain-English summary for TTS from the structured data
  const buildSpeakText = (): string => {
    const parts: string[] = [];
    if (data.business_summary) parts.push("Business Summary: " + data.business_summary);
    if (data.matched_schemes?.length)
      parts.push("Matched government schemes: " + data.matched_schemes.slice(0, 3).join(", ") + ".");
    if (data.next_step) parts.push("Your next step is: " + data.next_step);
    return parts.join(" ") || report.slice(0, 600);
  };

  const handleListen = async () => {
    if (audioState === "playing") {
      audioRef.current?.pause();
      setAudioState("idle");
      return;
    }
    setAudioState("loading");
    setAudioMsg("");
    try {
      const res = await fetch(`${BACKEND_URL}/api/voice/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: buildSpeakText() }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        setAudioMsg(j.detail ?? "Voice unavailable right now.");
        setAudioState("error");
        setTimeout(() => setAudioState("idle"), 4000);
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => { setAudioState("idle"); URL.revokeObjectURL(url); };
      audio.onerror = () => { setAudioState("error"); setAudioMsg("Audio playback failed."); setTimeout(() => setAudioState("idle"), 3000); };
      await audio.play();
      setAudioState("playing");
    } catch {
      setAudioMsg("Voice unavailable right now — no disruption to the text view.");
      setAudioState("error");
      setTimeout(() => setAudioState("idle"), 4000);
    }
  };

  const audioIcon =
    audioState === "loading" ? <Loader size={13} style={{ animation: "spin 1s linear infinite" }} />
    : audioState === "playing" ? <VolumeX size={13} />
    : <Volume2 size={13} />;

  const audioLabel =
    audioState === "loading" ? "Generating audio…"
    : audioState === "playing" ? "Stop"
    : "Listen to Advisory";

  return (
    <motion.div
      initial={{ opacity: 0, y: 40 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      style={{
        width: "100%",
        maxWidth: "760px",
        margin: "20px auto 40px",
        background: "var(--bg-card)",
        borderRadius: "var(--radius-xl)",
        border: "1px solid var(--border-bright)",
        boxShadow: "0 32px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(79,142,247,0.08)",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "18px 24px",
          borderBottom: "1px solid var(--border)",
          background: "linear-gradient(135deg, rgba(79,142,247,0.06) 0%, rgba(139,92,246,0.04) 100%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={{ width: "32px", height: "32px", borderRadius: "8px", background: "linear-gradient(135deg, var(--accent), var(--accent2))", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <BookOpen size={16} color="#fff" />
          </div>
          <div>
            <p style={{ fontSize: "0.88rem", fontWeight: 700, color: "var(--text-primary)" }}>Market Research &amp; Business Advisory</p>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Generated for: {topic}</p>
          </div>
        </div>

        {/* Listen + export */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "8px" }}>
          <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
            <motion.button
              onClick={copyText}
              title="Copy advisory text"
              whileTap={{ scale: 0.95 }}
              style={{
                display: "flex", alignItems: "center", gap: "5px",
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                color: "var(--text-secondary)",
                borderRadius: "var(--radius-sm)",
                padding: "7px 10px",
                fontSize: "0.75rem",
                fontWeight: 600,
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              {copied ? <CheckCircle2 size={12} color="var(--success)" /> : <Share2 size={12} />}
              {copied ? "Copied!" : "Copy"}
            </motion.button>
            <motion.button
              onClick={downloadText}
              title="Download advisory as .txt"
              whileTap={{ scale: 0.95 }}
              style={{
                display: "flex", alignItems: "center", gap: "5px",
                background: "linear-gradient(135deg, var(--accent), var(--accent2))",
                border: "none",
                color: "#fff",
                borderRadius: "var(--radius-sm)",
                padding: "7px 12px",
                fontSize: "0.75rem",
                fontWeight: 700,
                cursor: "pointer",
                fontFamily: "inherit",
                boxShadow: "0 4px 12px rgba(79,142,247,0.3)",
              }}
            >
              <Download size={12} /> Download .txt
            </motion.button>
          </div>
          <motion.button
            id="listen-advisory-btn"
            onClick={handleListen}
            disabled={audioState === "loading"}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.96 }}
            style={{
              display: "flex", alignItems: "center", gap: "6px",
              background: audioState === "playing"
                ? "rgba(248,113,113,0.15)"
                : "linear-gradient(135deg, rgba(79,142,247,0.15), rgba(139,92,246,0.15))",
              border: `1px solid ${audioState === "playing" ? "rgba(248,113,113,0.4)" : "rgba(139,92,246,0.3)"}`,
              color: audioState === "playing" ? "var(--error)" : "var(--accent2)",
              borderRadius: "var(--radius-sm)",
              padding: "7px 14px",
              fontSize: "0.78rem",
              fontWeight: 600,
              cursor: audioState === "loading" ? "wait" : "pointer",
              fontFamily: "inherit",
              transition: "all 0.2s",
            }}
          >
            {audioIcon} {audioLabel}
          </motion.button>
          <AnimatePresence>
            {audioState === "error" && audioMsg && (
              <motion.p
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                style={{ fontSize: "0.68rem", color: "var(--error)", maxWidth: "220px", textAlign: "right" }}
              >
                {audioMsg}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      </div>

      <div style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "24px" }}>
        {/* Loan-Ready Score */}
        {data.loan_ready_score && typeof data.loan_ready_score.score === "number" && (
          <motion.div
            initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.02 }}
            style={{
              display: "flex", alignItems: "center", gap: "18px", flexWrap: "wrap",
              background: "linear-gradient(135deg, rgba(79,142,247,0.08), rgba(139,92,246,0.05))",
              border: "1px solid rgba(139,92,246,0.22)",
              borderRadius: "12px", padding: "18px",
            }}
          >
            <ScoreGauge score={data.loan_ready_score.score} />
            <div style={{ flex: 1, minWidth: "220px" }}>
              <div style={{ marginBottom: "6px" }}>
                <span style={{
                  fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em",
                  color: "var(--accent)", background: "rgba(79,142,247,0.12)",
                  padding: "3px 8px", borderRadius: "8px",
                }}>
                  Loan-Ready Score
                </span>
                {data.loan_ready_score.level && (
                  <span style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)", marginLeft: "8px" }}>
                    {data.loan_ready_score.level}
                  </span>
                )}
              </div>
              {Array.isArray(data.loan_ready_score.why) && data.loan_ready_score.why.length > 0 && (
                <ul style={{ margin: 0, padding: "0 0 0 16px", display: "flex", flexDirection: "column", gap: "4px" }}>
                  {data.loan_ready_score.why.map((r, i) => (
                    <li key={i} style={{ fontSize: "0.78rem", lineHeight: 1.45, color: "var(--text-secondary)" }}>{r}</li>
                  ))}
                </ul>
              )}
            </div>
          </motion.div>
        )}

        {/* In Simple Words */}
        {simplified && (
          <motion.div
            initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
            style={{
              background: "linear-gradient(135deg, rgba(37,211,102,0.08), rgba(45,212,191,0.06))",
              border: "1px solid rgba(45,212,191,0.25)",
              borderRadius: "12px",
              padding: "18px",
            }}
          >
            <h3 style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--success)", marginBottom: "10px", display: "flex", alignItems: "center", gap: "6px" }}>
              <FileText size={16} /> In Simple Words — Read Aloud Version
            </h3>
            <pre style={{
              fontSize: "0.88rem",
              color: "var(--text-primary)",
              lineHeight: 1.8,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: "inherit",
            }}>
              {simplified}
            </pre>
          </motion.div>
        )}

        {/* Business Summary */}
        {data.business_summary && (
          <motion.div
            initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 }}
            style={{ background: "var(--bg-surface)", padding: "16px", borderRadius: "12px", border: "1px solid var(--border)" }}
          >
            <h3 style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--accent)", marginBottom: "8px", display: "flex", alignItems: "center", gap: "6px" }}>
              <Target size={16} /> Business Summary
            </h3>
            <p style={{ fontSize: "0.95rem", color: "var(--text-primary)", lineHeight: 1.6 }}>{data.business_summary}</p>
          </motion.div>
        )}

        {/* Cash-Flow Snapshot */}
        {data.cash_flow_snapshot && Object.keys(data.cash_flow_snapshot).length > 0 && (
          <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 }}>
            <h3 style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--accent)", marginBottom: "12px", display: "flex", alignItems: "center", gap: "6px" }}>
              <IndianRupee size={16} /> Cash-Flow Snapshot
            </h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "12px" }}>
              {Object.entries(data.cash_flow_snapshot).map(([k, v]) => (
                <motion.div
                  key={k}
                  whileHover={{ scale: 1.02 }}
                  style={{ background: "rgba(79,142,247,0.05)", border: "1px solid rgba(79,142,247,0.1)", borderRadius: "8px", padding: "12px" }}
                >
                  <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "capitalize", marginBottom: "4px" }}>{k.replace(/_/g, " ")}</p>
                  <p style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>{String(v)}</p>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Matched Schemes */}
        {data.matched_schemes && data.matched_schemes.length > 0 && (
          <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 }}>
            <h3 style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--accent)", marginBottom: "12px", display: "flex", alignItems: "center", gap: "6px" }}>
              <Sparkles size={16} /> Matched Schemes
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {data.matched_schemes.map((scheme, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 + idx * 0.05 }}
                  style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "12px", fontSize: "0.9rem", color: "var(--text-primary)" }}
                >
                  {scheme}
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Documents Needed */}
        {data.documents_needed && data.documents_needed.length > 0 && (
          <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.25 }}>
            <h3 style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--accent)", marginBottom: "12px", display: "flex", alignItems: "center", gap: "6px" }}>
              <FileCheck size={16} /> Checklist of Documents Needed
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {data.documents_needed.map((doc, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 + idx * 0.05 }}
                  style={{ display: "flex", alignItems: "flex-start", gap: "8px" }}
                >
                  <CheckSquare size={16} color="var(--text-muted)" style={{ marginTop: "2px", flexShrink: 0 }} />
                  <span style={{ fontSize: "0.9rem", color: "var(--text-secondary)" }}>{doc}</span>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Next Step */}
        {data.next_step && (
          <motion.div
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
            style={{ background: "linear-gradient(135deg, rgba(79,142,247,0.1), rgba(139,92,246,0.1))", border: "1px solid rgba(139,92,246,0.2)", borderRadius: "12px", padding: "16px" }}
          >
            <h3 style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--accent2)", marginBottom: "6px", display: "flex", alignItems: "center", gap: "6px" }}>
              <ArrowRight size={16} /> Next Step
            </h3>
            <p style={{ fontSize: "0.95rem", color: "var(--text-primary)", fontWeight: 500 }}>{data.next_step}</p>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
