"use client";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2,
  Loader2,
  Circle,
  ChevronDown,
  ChevronUp,
  Globe,
  Landmark,
  Gauge,
  ClipboardList,
  Calculator,
  Wrench,
  Sparkles,
  Lightbulb,
  Cpu,
  Brain,
  Scale,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/lib/i18n";

export type TraceNode = {
  id: number;
  node: string;
  label: string;
  icon: string;
  iteration: number;
  status: "running" | "done";
  summary?: string;
  output?: string;
  ok?: boolean;
  thoughts: string[];
  tools: Array<{ tool: string; input: string; summary?: string; ok?: boolean }>;
  reflections: Array<{ text: string; action: string }>;
};

interface Props {
  nodes: TraceNode[];
  planSteps?: string[];
  statusMessage?: string;
  isRunning?: boolean;
  engine?: string;
}

const NODE_COLORS: Record<string, { color: string; bg: string; glow: string }> = {
  planner:    { color: "#60a5fa", bg: "rgba(96,165,250,0.12)",  glow: "rgba(96,165,250,0.2)" },
  gate:       { color: "#fb7185", bg: "rgba(251,113,133,0.12)", glow: "rgba(251,113,133,0.2)" },
  supervisor: { color: "#a78bfa", bg: "rgba(167,139,250,0.12)", glow: "rgba(167,139,250,0.2)" },
  research:   { color: "#22d3ee", bg: "rgba(34,211,238,0.12)",  glow: "rgba(34,211,238,0.2)" },
  analyst:    { color: "#fbbf24", bg: "rgba(251,191,36,0.12)",  glow: "rgba(251,191,36,0.2)" },
  schemes:    { color: "#fb923c", bg: "rgba(251,146,60,0.12)",  glow: "rgba(251,146,60,0.2)" },
  writer:     { color: "#2dd4bf", bg: "rgba(45,212,191,0.12)",  glow: "rgba(45,212,191,0.2)" },
  critic:     { color: "#f472b6", bg: "rgba(244,114,182,0.12)",  glow: "rgba(244,114,182,0.2)" },
  refine:     { color: "#34d399", bg: "rgba(52,211,153,0.12)",  glow: "rgba(52,211,153,0.2)" },
  finalize:   { color: "#4ade80", bg: "rgba(74,222,128,0.12)",  glow: "rgba(74,222,128,0.2)" },
};

function nodeColor(node: string) {
  return NODE_COLORS[node] ?? { color: "var(--accent)", bg: "rgba(0,0,0,0.06)", glow: "rgba(0,0,0,0.1)" };
}

function ToolIcon({ tool }: { tool: string }) {
  const map: Record<string, LucideIcon> = {
    web_search: Globe,
    scheme_match: Landmark,
    loan_ready_score: Gauge,
    document_checklist: ClipboardList,
    cashflow_projection: Calculator,
  };
  const Icon = map[tool] ?? Wrench;
  return <Icon size={12} />;
}

function NodeCard({ n, i }: { n: TraceNode; i: number }) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const cfg = nodeColor(n.node);
  const busy = n.status === "running";
  const expandable = Boolean(n.output) || n.thoughts.length + n.tools.length + n.reflections.length > 0;
  const open = expanded || busy;

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: Math.min(i * 0.05, 0.4), duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className={busy ? "running-border" : ""}
      style={{
        background: "var(--bg-card)",
        border: `1px solid ${busy ? "transparent" : "var(--border)"}`,
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        boxShadow: "0 2px 12px rgba(0,0,0,0.3)",
        transition: "border-color 0.3s, box-shadow 0.3s",
      }}
    >
      {busy && (
        <div style={{ height: "2px", background: "var(--border)" }}>
          <motion.div
            initial={{ width: "0%" }}
            animate={{ width: "100%" }}
            transition={{ duration: 30, ease: "linear" }}
            style={{ height: "100%", background: `linear-gradient(90deg, ${cfg.color}, var(--accent2))` }}
          />
        </div>
      )}
      {!busy && <div style={{ height: "2px", background: n.ok === false ? "var(--error)" : cfg.color }} />}

      <div
        role={expandable ? "button" : undefined}
        tabIndex={expandable ? 0 : undefined}
        aria-expanded={expandable ? open : undefined}
        onKeyDown={(e) => {
          if (!expandable) return;
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((p) => !p);
          }
        }}
        onClick={() => expandable && setExpanded((p) => !p)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "12px",
          padding: "14px 16px",
          cursor: expandable ? "pointer" : "default",
        }}
      >
        <div style={{ flexShrink: 0 }}>
          {!busy ? (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 300, damping: 15 }}
            >
              {n.ok === false ? (
                <Circle size={18} color="var(--error)" />
              ) : (
                <CheckCircle2 size={18} color={cfg.color} />
              )}
            </motion.div>
          ) : (
            <Loader2 size={18} color={cfg.color} className="animate-spin" style={{ animation: "spin 1s linear infinite" }} />
          )}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{
            fontSize: "0.85rem",
            fontWeight: 600,
            color: busy ? "var(--text-primary)" : "var(--text-primary)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}>
            {n.label}
            {n.iteration > 0 && (
              <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginLeft: "6px" }}>
                {t("timeline.pass", { n: n.iteration })}
              </span>
            )}
          </p>
          {n.summary && (
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "2px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {n.summary}
            </p>
          )}
        </div>

        {expandable && (
          <div style={{ color: "var(--text-muted)", flexShrink: 0, marginLeft: "4px" }}>
            {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </div>
        )}
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            style={{ overflow: "hidden" }}
          >
            <div style={{
              borderTop: "1px solid var(--border)",
              padding: "12px 16px",
              background: "var(--bg-surface)",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}>
              {/* Thoughts */}
              {n.thoughts.map((t, ti) => (
                <div key={`t-${ti}`} style={{ display: "flex", gap: "8px", alignItems: "flex-start", color: "var(--text-secondary)", fontSize: "0.78rem" }}>
                  <Lightbulb size={12} color={cfg.color} style={{ flexShrink: 0, marginTop: "2px" }} />
                  <span style={{ lineHeight: 1.6 }}>{t}</span>
                </div>
              ))}

              {/* Tool calls */}
              {n.tools.map((tool, ti) => (
                <div
                  key={`tool-${ti}`}
                  style={{
                    display: "flex",
                    gap: "8px",
                    alignItems: "flex-start",
                    fontSize: "0.76rem",
                    padding: "7px 10px",
                    borderRadius: "var(--radius-sm)",
                    background: "var(--bg-card)",
                    border: "1px solid var(--border)",
                    color: "var(--text-secondary)",
                  }}
                >
                  <div style={{ color: cfg.color, flexShrink: 0, marginTop: "1px" }}>
                    <ToolIcon tool={tool.tool} />
                  </div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{tool.tool}</span>
                    {tool.input && <span style={{ color: "var(--text-muted)", marginLeft: "6px", wordBreak: "break-word" }}>{tool.input}</span>}
                    {tool.summary && (
                      <p style={{ marginTop: "3px", color: tool.ok === false ? "var(--error)" : "var(--text-muted)", lineHeight: 1.5 }}>
                        → {tool.summary}
                      </p>
                    )}
                  </div>
                </div>
              ))}

              {/* Reflections */}
              {n.reflections.map((r, ri) => (
                <div
                  key={`r-${ri}`}
                  style={{
                    display: "flex",
                    gap: "8px",
                    alignItems: "flex-start",
                    fontSize: "0.76rem",
                    padding: "7px 10px",
                    borderRadius: "var(--radius-sm)",
                    background: "rgba(244,114,182,0.06)",
                    border: "1px solid rgba(244,114,182,0.2)",
                    color: "var(--text-secondary)",
                  }}
                >
                  <Sparkles size={12} color="#f472b6" style={{ flexShrink: 0, marginTop: "1px" }} />
                  <span style={{ lineHeight: 1.6 }}>{r.text}</span>
                </div>
              ))}

              {/* Node output */}
              {n.output && (
                <pre style={{
                  fontSize: "0.76rem",
                  color: "var(--text-secondary)",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  maxHeight: "200px",
                  overflowY: "auto",
                  lineHeight: "1.7",
                  fontFamily: "inherit",
                  background: "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-sm)",
                  padding: "10px",
                }}>
                  {n.output}
                </pre>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function AgentTimeline({ nodes, planSteps, statusMessage, isRunning, engine }: Props) {
  const { t } = useI18n();
  const hasContent = nodes.length + (planSteps?.length ?? 0) > 0 || Boolean(statusMessage && isRunning);
  if (!hasContent) return null;

  const doneCount = nodes.filter((n) => n.status === "done").length;
  const progress = nodes.length > 0 ? Math.round((doneCount / nodes.length) * 100) : 0;
  const active = nodes.filter((n) => n.status === "running").length;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      style={{ width: "100%", maxWidth: "760px", margin: "0 auto", marginTop: "20px" }}
    >
      {/* Progress header */}
      {(nodes.length > 0 || isRunning) && (
        <div style={{ marginBottom: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 500 }}>
              {statusMessage ||
                (active > 0
                  ? t("timeline.working")
                  : t("timeline.agentsDone", { done: doneCount, total: nodes.length }))}
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              {engine && (
                <span style={{
                  fontSize: "0.66rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em",
                  color: engine === "langgraph" ? "#a78bfa" : "#fbbf24",
                  background: engine === "langgraph" ? "rgba(167,139,250,0.12)" : "rgba(251,191,36,0.12)",
                  border: `1px solid ${engine === "langgraph" ? "rgba(167,139,250,0.3)" : "rgba(251,191,36,0.3)"}`,
                  borderRadius: "20px", padding: "2px 8px",
                  display: "flex", alignItems: "center", gap: "4px",
                }}>
                  {engine === "langgraph" ? <Cpu size={9} /> : <Brain size={9} />}
                  {engine === "langgraph" ? "LangGraph" : "Native"}
                </span>
              )}
              <span style={{ fontSize: "0.78rem", color: "var(--accent)", fontWeight: 700 }}>{progress}%</span>
            </span>
          </div>
          <div style={{ height: "4px", background: "var(--border)", borderRadius: "99px", overflow: "hidden" }}>
            <motion.div
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.4 }}
              style={{ height: "100%", background: "linear-gradient(90deg, var(--accent), var(--accent2))", borderRadius: "99px" }}
            />
          </div>
        </div>
      )}

      {/* Reserved plan chips */}
      {planSteps && planSteps.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "12px" }}>
          {planSteps.map((s, i) => (
            <span key={`plan-${i}`} style={{
              fontSize: "0.7rem",
              color: "var(--text-secondary)",
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "20px",
              padding: "4px 10px",
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
            }}>
              <Scale size={10} color="var(--accent)" />
              {s}
            </span>
          ))}
        </div>
      )}

      {/* Empty-state live banner (before first node_start) */}
      {nodes.length === 0 && isRunning && statusMessage && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          style={{ display: "flex", alignItems: "center", gap: "10px", padding: "14px 18px", background: "var(--bg-card)", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)" }}
        >
          <Loader2 size={16} color="var(--accent)" style={{ animation: "spin 1s linear infinite", flexShrink: 0 }} />
          <span style={{ fontSize: "0.86rem", color: "var(--text-secondary)" }}>{statusMessage}</span>
        </motion.div>
      )}

      {/* Node cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        <AnimatePresence>
          {nodes.map((n, i) => (
            <NodeCard key={n.id} n={n} i={i} />
          ))}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}