"use client";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Loader2, Circle, ChevronDown, ChevronUp, Bot } from "lucide-react";
import { useState } from "react";

const AGENT_CONFIG: Record<string, { label: string; color: string; bg: string; glow: string }> = {
  research_agent:    { label: "Research",    color: "#60a5fa", bg: "rgba(96,165,250,0.12)",  glow: "rgba(96,165,250,0.2)" },
  analyst_agent:     { label: "Analyst",     color: "#a78bfa", bg: "rgba(167,139,250,0.12)", glow: "rgba(167,139,250,0.2)" },
  opportunity_agent: { label: "Opportunity", color: "#fb923c", bg: "rgba(251,146,60,0.12)",  glow: "rgba(251,146,60,0.2)" },
  writer_agent:      { label: "Writer",      color: "#34d399", bg: "rgba(52,211,153,0.12)",  glow: "rgba(52,211,153,0.2)" },
  editor_agent:      { label: "Editor",      color: "#f472b6", bg: "rgba(244,114,182,0.12)", glow: "rgba(244,114,182,0.2)" },
};

type Step = {
  step: string;
  agent?: string;
  status: "pending" | "running" | "done";
  output?: string;
};

interface Props {
  steps: Step[];
  statusMessage?: string;
}

function StepCard({ s, i, total }: { s: Step; i: number; total: number }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = s.agent ? AGENT_CONFIG[s.agent] : null;

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: i * 0.06, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      style={{
        background: "var(--bg-card)",
        border: `1px solid ${s.status === "running" ? (cfg?.color ?? "var(--accent)") : "var(--border)"}`,
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        boxShadow: s.status === "running"
          ? `0 0 20px ${cfg?.glow ?? "var(--accent-glow)"}`
          : "0 2px 12px rgba(0,0,0,0.3)",
        transition: "border-color 0.3s, box-shadow 0.3s",
      }}
    >
      {/* Progress bar for running step */}
      {s.status === "running" && (
        <div style={{ height: "2px", background: "var(--border)" }}>
          <motion.div
            initial={{ width: "0%" }}
            animate={{ width: "100%" }}
            transition={{ duration: 25, ease: "linear" }}
            style={{ height: "100%", background: `linear-gradient(90deg, ${cfg?.color ?? "var(--accent)"}, var(--accent2))` }}
          />
        </div>
      )}
      {s.status === "done" && (
        <div style={{ height: "2px", background: cfg?.color ?? "var(--success)" }} />
      )}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "12px",
          padding: "14px 16px",
          cursor: s.output ? "pointer" : "default",
        }}
        onClick={() => s.output && setExpanded((p) => !p)}
      >
        {/* Status icon */}
        <div style={{ flexShrink: 0 }}>
          {s.status === "done" ? (
            <CheckCircle2 size={18} color={cfg?.color ?? "var(--success)"} />
          ) : s.status === "running" ? (
            <Loader2 size={18} color={cfg?.color ?? "var(--accent)"} className="animate-spin" style={{ animation: "spin 1s linear infinite" }} />
          ) : (
            <Circle size={18} color="var(--text-muted)" />
          )}
        </div>

        {/* Step label */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{
            fontSize: "0.85rem",
            fontWeight: 500,
            color: s.status === "pending" ? "var(--text-muted)" : "var(--text-primary)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}>
            <span style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginRight: "6px" }}>
              {i + 1}/{total}
            </span>
            {s.step}
          </p>
        </div>

        {/* Agent badge */}
        {cfg && (
          <span style={{
            flexShrink: 0,
            fontSize: "0.72rem",
            fontWeight: 600,
            color: cfg.color,
            background: cfg.bg,
            border: `1px solid ${cfg.color}33`,
            borderRadius: "20px",
            padding: "3px 10px",
            display: "flex",
            alignItems: "center",
            gap: "4px",
          }}>
            <Bot size={10} />
            {cfg.label}
          </span>
        )}

        {/* Expand toggle */}
        {s.output && (
          <div style={{ color: "var(--text-muted)", flexShrink: 0, marginLeft: "4px" }}>
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </div>
        )}
      </div>

      {/* Expanded output */}
      <AnimatePresence>
        {expanded && s.output && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            style={{ overflow: "hidden" }}
          >
            <div style={{
              borderTop: "1px solid var(--border)",
              padding: "14px 16px",
              background: "var(--bg-surface)",
            }}>
              <pre style={{
                fontSize: "0.78rem",
                color: "var(--text-secondary)",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                maxHeight: "220px",
                overflowY: "auto",
                lineHeight: "1.7",
                fontFamily: "inherit",
              }}>
                {s.output}
              </pre>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function AgentTimeline({ steps, statusMessage }: Props) {
  if (steps.length === 0 && !statusMessage) return null;

  const doneCount = steps.filter((s) => s.status === "done").length;
  const progress = steps.length > 0 ? Math.round((doneCount / steps.length) * 100) : 0;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      style={{ width: "100%", maxWidth: "760px", margin: "0 auto", marginTop: "20px" }}
    >
      {/* Progress header */}
      {steps.length > 0 && (
        <div style={{ marginBottom: "16px" }}>
          <div style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "8px",
          }}>
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 500 }}>
              {statusMessage || `${doneCount} of ${steps.length} steps complete`}
            </span>
            <span style={{ fontSize: "0.78rem", color: "var(--accent)", fontWeight: 700 }}>
              {progress}%
            </span>
          </div>
          <div style={{
            height: "4px",
            background: "var(--border)",
            borderRadius: "99px",
            overflow: "hidden",
          }}>
            <motion.div
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.4 }}
              style={{
                height: "100%",
                background: "linear-gradient(90deg, var(--accent), var(--accent2))",
                borderRadius: "99px",
              }}
            />
          </div>
        </div>
      )}

      {/* Status-only message (before plan arrives) */}
      {steps.length === 0 && statusMessage && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            padding: "14px 18px",
            background: "var(--bg-card)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--border-bright)",
          }}
        >
          <Loader2
            size={16}
            color="var(--accent)"
            style={{ animation: "spin 1s linear infinite", flexShrink: 0 }}
          />
          <span style={{ fontSize: "0.86rem", color: "var(--text-secondary)" }}>{statusMessage}</span>
        </motion.div>
      )}

      {/* Step cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        <AnimatePresence>
          {steps.map((s, i) => (
            <StepCard key={i} s={s} i={i} total={steps.length} />
          ))}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
