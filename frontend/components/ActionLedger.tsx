"use client";
import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Check, ListChecks, Lock, Loader2 } from "lucide-react";
import { API_BASE } from "@/lib/api";

export type LedgerAction = {
  id: string;
  title: string;
  why: string;
  how: string;
  points: number;
  unlocks: string[];
  gates: string[];
  status: "done" | "todo" | "blocked";
  blocked_reason: string;
  user_confirmable: boolean;
  auto_answered: boolean;
};

export type LedgerScore = {
  score: number;
  level?: string;
  points_earned?: number;
  points_possible?: number;
  reasons?: string[];
  next_action?: LedgerAction | null;
  blockers?: LedgerAction[];
  actions?: LedgerAction[];
  done_count?: number;
  total_count?: number;
};

export default function ActionLedger({
  sessionId,
  initial,
}: {
  sessionId: string;
  initial: LedgerScore;
}) {
  const [ledger, setLedger] = useState<LedgerScore>(initial);
  const [ticking, setTicking] = useState<string | null>(null);
  const [error, setError] = useState("");

  // The advisory and this panel can drift apart if the run re-rendered; the
  // server is the source of truth for the persisted score.
  useEffect(() => setLedger(initial), [initial]);

  const toggle = useCallback(
    async (action: LedgerAction) => {
      if (!sessionId || ticking) return;
      setTicking(action.id);
      setError("");
      const done = (ledger.actions ?? []).filter((a) => a.status === "done").map((a) => a.id);
      const next = action.status === "done" ? done.filter((id) => id !== action.id) : [...done, action.id];
      try {
        const res = await fetch(`${API_BASE}/api/ledger/${encodeURIComponent(sessionId)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ completed: next }),
        });
        if (!res.ok) throw new Error("bad status");
        const body = (await res.json()) as LedgerScore;
        setLedger(body);
      } catch {
        setError("We couldn't save that just now. Please try again.");
      } finally {
        setTicking(null);
      }
    },
    [ledger.actions, sessionId, ticking]
  );

  const actions = ledger.actions ?? [];
  if (!actions.length) return null;

  const done = actions.filter((a) => a.status === "done").length;
  const blockers = ledger.blockers ?? [];

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      aria-label="Action ledger"
      style={{
        background: "rgba(37,211,102,0.04)",
        border: "1px solid rgba(37,211,102,0.2)",
        borderRadius: "var(--radius-lg)",
        padding: "clamp(14px, 4vw, 20px)",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
        <ListChecks size={15} color="var(--success)" />
        <h3 style={{ margin: 0, fontSize: "0.92rem", fontWeight: 700, color: "var(--text-primary)" }}>
          Your action checklist
        </h3>
        <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontWeight: 600 }}>
          {done} of {actions.length} done
        </span>
      </div>

      <p style={{ margin: 0, fontSize: "0.74rem", color: "var(--text-secondary)" }}>
        Your score is <strong style={{ color: "var(--text-primary)" }}>{ledger.score}/100</strong>
        {ledger.level ? ` — ${ledger.level}` : ""}. Tick what you have actually done and the score updates
        straight away. Nothing here is shared anywhere.
      </p>

      {/* The one next thing — always the highest-value action */}
      {ledger.next_action ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "10px 12px",
            borderRadius: "10px",
            background: "rgba(79,142,247,0.1)",
            border: "1px solid rgba(79,142,247,0.24)",
          }}
        >
          <ArrowRight size={14} color="var(--accent)" style={{ flexShrink: 0 }} />
          <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--text-primary)" }}>
            Do this next: {ledger.next_action.title}
          </span>
          <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "var(--accent)", fontWeight: 700, flexShrink: 0 }}>
            +{ledger.next_action.points}
          </span>
        </div>
      ) : null}

      {blockers.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {blockers.map((b) => (
            <div
              key={b.id}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "8px",
                padding: "9px 11px",
                borderRadius: "10px",
                background: "rgba(248,113,113,0.07)",
                border: "1px solid rgba(248,113,113,0.22)",
              }}
            >
              <Lock size={13} color="var(--error)" style={{ flexShrink: 0, marginTop: "2px" }} />
              <div style={{ flex: 1 }}>
                <p style={{ margin: 0, fontSize: "0.78rem", fontWeight: 700, color: "var(--error)" }}>
                  {b.title}
                </p>
                <p style={{ margin: "2px 0 0", fontSize: "0.71rem", color: "var(--text-secondary)" }}>
                  {b.why}
                </p>
                <p style={{ margin: "2px 0 0", fontSize: "0.71rem", color: "var(--text-muted)" }}>
                  How: {b.how}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
        {actions.map((action) => {
          const isDone = action.status === "done";
          const isBusy = ticking === action.id;
          const tickable = action.user_confirmable || action.auto_answered;
          return (
            <li
              key={action.id}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "10px",
                padding: "10px 12px",
                borderRadius: "10px",
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                opacity: isDone ? 0.72 : 1,
              }}
            >
              <button
                type="button"
                onClick={() => toggle(action)}
                disabled={!tickable || !!ticking}
                aria-pressed={isDone}
                aria-label={`${isDone ? "Completed" : "Mark complete"}: ${action.title}`}
                title={
                  tickable
                    ? isDone
                      ? "Tap to undo"
                      : "Tap when you have done this"
                    : "We already know this from your answers"
                }
                style={{
                  width: "20px",
                  height: "20px",
                  minWidth: "20px",
                  marginTop: "1px",
                  borderRadius: "6px",
                  border: `1px solid ${isDone ? "transparent" : "var(--border-bright)"}`,
                  background: isDone ? "var(--success)" : "transparent",
                  color: "#06210f",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: tickable && !ticking ? "pointer" : "default",
                  padding: 0,
                }}
              >
                {isBusy ? (
                  <Loader2 size={12} className="spin" color="var(--text-muted)" />
                ) : isDone ? (
                  <Check size={13} />
                ) : null}
              </button>

              <div style={{ flex: 1, minWidth: 0 }}>
                <p
                  style={{
                    margin: 0,
                    fontSize: "0.8rem",
                    fontWeight: 600,
                    color: isDone ? "var(--text-muted)" : "var(--text-primary)",
                    textDecoration: isDone ? "line-through" : "none",
                  }}
                >
                  {action.title}
                </p>
                {!isDone ? (
                  <p style={{ margin: "2px 0 0", fontSize: "0.71rem", color: "var(--text-muted)" }}>
                    {action.why}
                  </p>
                ) : null}
                {action.unlocks?.length > 0 && !isDone ? (
                  <p style={{ margin: "3px 0 0", fontSize: "0.66rem", color: "var(--accent)", fontWeight: 600 }}>
                    Opens up: {action.unlocks.join(", ")}
                  </p>
                ) : null}
              </div>

              {action.points > 0 && (
                <span
                  style={{
                    fontSize: "0.68rem",
                    fontWeight: 800,
                    color: isDone ? "var(--success)" : "var(--text-muted)",
                    flexShrink: 0,
                  }}
                >
                  +{action.points}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {error ? (
        <p role="alert" style={{ margin: 0, fontSize: "0.72rem", color: "var(--error)" }}>
          {error}
        </p>
      ) : null}
    </motion.section>
  );
}