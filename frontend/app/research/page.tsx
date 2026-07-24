"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import TopicInput from "@/components/TopicInput";
import AgentTimeline from "@/components/AgentTimeline";
import ReportViewer from "@/components/ReportViewer";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle } from "lucide-react";

// Use wss:// in production (HTTPS pages block ws://)
const rawWsUrl =
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/market";

const WS_URL =
  typeof window !== "undefined" &&
  window.location.protocol === "https:" &&
  rawWsUrl.startsWith("ws://")
    ? rawWsUrl.replace("ws://", "wss://")
    : rawWsUrl;

const WS_RECONNECT_DELAY_MS = 1500;
const WS_MAX_RETRIES = 3;

type Step = {
  step: string;
  agent?: string;
  status: "pending" | "running" | "done";
  output?: string;
};

export default function ResearchPage() {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const pendingStartRef = useRef<{ topic: string; maxSteps: number } | null>(null);

  const [isRunning, setIsRunning] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [finalReport, setFinalReport] = useState<string | null>(null);
  const [currentTopic, setCurrentTopic] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const handleMessage = useCallback((data: Record<string, unknown>) => {
    setErrorMessage("");
    switch (data.type) {
      case "status":
        setStatusMessage(data.message as string);
        break;
      case "plan":
        setSteps(
          (data.plan as string[]).map((step) => ({
            step,
            status: "pending" as const,
          }))
        );
        setStatusMessage("");
        break;
      case "step_start":
        setSteps((prev) =>
          prev.map((s, i) =>
            i === data.step_index
              ? { ...s, status: "running", agent: data.agent as string }
              : s
          )
        );
        setStatusMessage(
          `Running ${(data.agent as string)?.replace("_agent", "")}…`
        );
        break;
      case "step_end":
        setSteps((prev) =>
          prev.map((s, i) =>
            i === data.step_index
              ? {
                  ...s,
                  status: "done",
                  agent: data.agent as string,
                  output: data.output as string,
                }
              : s
          )
        );
        setStatusMessage("");
        break;
      case "done":
        setFinalReport(data.final_report as string);
        setIsRunning(false);
        setStatusMessage("Research complete ✓");
        retriesRef.current = 0;
        break;
      case "cancelled":
        setIsRunning(false);
        setStatusMessage("Research cancelled.");
        retriesRef.current = 0;
        break;
      case "error":
        setIsRunning(false);
        setErrorMessage(data.message as string);
        setStatusMessage("");
        retriesRef.current = 0;
        break;
    }
  }, []);

  // ── WebSocket with reconnect ───────────────────────────────────
  const connectWs = useCallback(
    (onOpenCallback?: (ws: WebSocket) => void) => {
      if (
        wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING
      ) {
        if (onOpenCallback && wsRef.current.readyState === WebSocket.OPEN) {
          onOpenCallback(wsRef.current);
        }
        return;
      }

      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        retriesRef.current = 0;
        if (onOpenCallback) onOpenCallback(ws);
      };

      ws.onerror = () => {
        // onclose fires after onerror — let onclose handle retry
      };

      ws.onmessage = (e) => {
        try {
          handleMessage(JSON.parse(e.data));
        } catch (err) {
          console.error("WS parse error:", err);
        }
      };

      ws.onclose = (ev) => {
        // Unexpected close while running — attempt reconnect
        if (isRunning && retriesRef.current < WS_MAX_RETRIES && !ev.wasClean) {
          retriesRef.current += 1;
          setStatusMessage(
            `Connection lost. Retrying (${retriesRef.current}/${WS_MAX_RETRIES})…`
          );
          setTimeout(() => {
            connectWs();
          }, WS_RECONNECT_DELAY_MS * retriesRef.current);
        } else if (isRunning) {
          setIsRunning(false);
          setErrorMessage(
            "Backend connection closed unexpectedly. Please try again."
          );
          setStatusMessage("");
        }
      };
    },
    [handleMessage, isRunning]
  );

  const handleStart = async (topic: string, maxSteps: number) => {
    setIsRunning(true);
    setSteps([]);
    setFinalReport(null);
    setCurrentTopic(topic);
    setStatusMessage("Connecting…");
    setErrorMessage("");
    retriesRef.current = 0;

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "start", topic, max_steps: maxSteps }));
      return;
    }

    pendingStartRef.current = { topic, maxSteps };
    connectWs((ws) => {
      const pending = pendingStartRef.current;
      if (pending) {
        ws.send(
          JSON.stringify({ type: "start", topic: pending.topic, max_steps: pending.maxSteps })
        );
        pendingStartRef.current = null;
      }
    });

    // Timeout fallback if connection never opens
    setTimeout(() => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) {
        setStatusMessage("");
        setErrorMessage(
          "Could not connect to the backend. Is the server running? Check that NEXT_PUBLIC_WS_URL is set correctly."
        );
        setIsRunning(false);
      }
    }, 5000);
  };

  const handleCancel = () => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "cancel" }));
    }
    setIsRunning(false);
    setStatusMessage("");
  };

  useEffect(() => () => { wsRef.current?.close(); }, []);

  return (
    <main
      style={{
        minHeight: "100vh",
        padding: "48px 20px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
      }}
    >
      {/* Hero heading */}
      <motion.div
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        style={{ textAlign: "center", marginBottom: "32px" }}
      >
        <h2
          style={{
            fontSize: "0.78rem",
            fontWeight: 600,
            color: "var(--accent)",
            textTransform: "uppercase",
            letterSpacing: "0.12em",
            marginBottom: "10px",
          }}
        >
          Powered by Gemini 2.5 Flash via OpenRouter
        </h2>
        <p
          style={{
            fontSize: "2.2rem",
            fontWeight: 800,
            color: "var(--text-primary)",
            letterSpacing: "-0.03em",
            lineHeight: 1.2,
            background:
              "linear-gradient(135deg, var(--text-primary) 40%, var(--accent))",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          AI Market Intelligence
        </p>
        <p
          style={{
            marginTop: "8px",
            fontSize: "0.92rem",
            color: "var(--text-muted)",
            maxWidth: "480px",
            margin: "8px auto 0",
          }}
        >
          Multi-agent research pipeline that generates comprehensive market
          reports in minutes.
        </p>
      </motion.div>

      {/* Main input */}
      <div style={{ width: "100%", maxWidth: "760px" }}>
        <TopicInput
          onStart={handleStart}
          onCancel={handleCancel}
          isRunning={isRunning}
        />
      </div>

      {/* Error banner */}
      <AnimatePresence>
        {errorMessage && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            style={{
              marginTop: "16px",
              width: "100%",
              maxWidth: "760px",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "14px 18px",
              background: "rgba(248,113,113,0.08)",
              border: "1px solid rgba(248,113,113,0.25)",
              borderRadius: "var(--radius-md)",
            }}
          >
            <AlertTriangle
              size={16}
              color="var(--error)"
              style={{ flexShrink: 0 }}
            />
            <span style={{ fontSize: "0.86rem", color: "var(--error)" }}>
              {errorMessage}
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Agent timeline */}
      <AgentTimeline steps={steps} statusMessage={statusMessage} />

      {/* Report */}
      <AnimatePresence>
        {finalReport && (
          <ReportViewer report={finalReport} topic={currentTopic} />
        )}
      </AnimatePresence>
    </main>
  );
}
