"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import TopicInput from "@/components/TopicInput";
import AgentTimeline, { type TraceNode } from "@/components/AgentTimeline";
import AdvisoryCard from "@/components/AdvisoryCard";
import ChatPanel from "@/components/ChatPanel";
import Usps from "@/components/Usps";
const LiveAdvisorPanel = dynamic(() => import("@/components/LiveAdvisorPanel"), { ssr: false });
import StartupQuiz, { type ProfileInit } from "@/components/StartupQuiz";
const CashflowSimulator = dynamic(() => import("@/components/CashflowSimulator"), { ssr: false });
import { migrateIntake } from "@/lib/intake";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, MessageCircle, X } from "lucide-react";
import { API_BASE, WS_URL } from "@/lib/api";

const WS_RECONNECT_DELAY_MS = 1500;
const WS_MAX_RETRIES = 3;
const SESSION_KEY = "grameenai_session";
const PROFILE_KEY = "grameenai_profile";

export default function ResearchPage() {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  // Mirror of `isRunning` for use inside the WebSocket `onclose` closure —
  // the closure captures the value at connect time and would otherwise go stale.
  const isRunningRef = useRef(false);
  const pendingStartRef = useRef<{
    topic: string;
    maxSteps: number;
    sessionId: string;
    profile: string;
    intake: ProfileInit;
  } | null>(null);

  const [isRunning, setIsRunning] = useState(false);
  const [nodes, setNodes] = useState<TraceNode[]>([]);
  const [planSteps, setPlanSteps] = useState<string[]>([]);
  const [engine, setEngine] = useState("");
  const [finalReport, setFinalReport] = useState<string | null>(null);
  const [simplifiedReport, setSimplifiedReport] = useState<string>("");
  const [currentTopic, setCurrentTopic] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [mounted, setMounted] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [profile, setProfile] = useState<ProfileInit>({});
  const [resumeNote, setResumeNote] = useState("");

  useEffect(() => {
    isRunningRef.current = isRunning;
  }, [isRunning]);

  useEffect(() => {
    setMounted(true);
    // Stable per-browser session: ties the chat memory and the advisory run
    // together so follow-up questions remember this research session.
    try {
      const existing = window.localStorage.getItem(SESSION_KEY);
      if (existing) {
        setSessionId(existing);
      } else {
        const id = `s-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
        window.localStorage.setItem(SESSION_KEY, id);
        setSessionId(id);
      }
    } catch {
      // localStorage unavailable (private mode) — chat degrades to stateless.
    }

    // Restore the optional Business Check-up answers. migrateIntake() also
    // upgrades the older chip-code format written by previous versions.
    try {
      const savedProfile = window.localStorage.getItem(PROFILE_KEY);
      if (savedProfile) {
        const parsed = migrateIntake(JSON.parse(savedProfile));
        if (parsed && Object.keys(parsed).length) setProfile(parsed);
      }
    } catch {
      /* noop */
    }
  }, []);

  // Resume the saved advisory for this browser session, if any.
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}`);
        if (!res.ok) return;
        const body = await res.json();
        if (cancelled || !body?.final_report) return;
        setFinalReport(body.final_report as string);
        setSimplifiedReport(((body.simplified_report as string) ?? "").trim());
        setCurrentTopic((body.topic as string) ?? "");
        setResumeNote("Reopened your last advisory — run research again to refresh it.");
      } catch {
        /* backend offline — nothing to resume */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const changeProfile = useCallback((next: ProfileInit) => {
    setProfile(next);
    try {
      window.localStorage.setItem(PROFILE_KEY, JSON.stringify(next));
    } catch {
      /* noop */
    }
  }, []);

  const handleMessage = useCallback((data: Record<string, unknown>) => {
    setErrorMessage("");
    switch (data.type) {
      case "status":
        setStatusMessage(data.message as string);
        break;
      case "graph":
        setEngine((data.engine as string) ?? "");
        break;
      case "plan":
        setPlanSteps((data.plan as string[]) ?? []);
        setStatusMessage("");
        break;
      case "node_start":
        setNodes((prev) => [
          ...prev,
          {
            id: (data.index as number) ?? Date.now(),
            node: data.node as string,
            label: (data.label as string) ?? (data.node as string),
            icon: (data.icon as string) ?? "",
            iteration: (data.iteration as number) ?? 0,
            status: "running",
            thoughts: [],
            tools: [],
            reflections: [],
          },
        ]);
        setStatusMessage(`Running ${(data.label as string) ?? (data.node as string)}…`);
        break;
      case "node_end":
        setNodes((prev) =>
          prev.map((n) =>
            n.status === "running"
              ? {
                  ...n,
                  status: "done",
                  summary: (data.summary as string) ?? "",
                  output: data.output as string | undefined,
                  ok: data.ok as boolean | undefined,
                }
              : n
          )
        );
        setStatusMessage("");
        break;
      case "thought": {
        const text = (data.text as string) ?? "";
        if (!text) break;
        setNodes((prev) =>
          prev.map((n) =>
            n.status === "running" && n.node === data.node
              ? { ...n, thoughts: [...n.thoughts, text] }
              : n
          )
        );
        break;
      }
      case "tool_call": {
        const tool = (data.tool as string) ?? "";
        setNodes((prev) =>
          prev.map((n) =>
            n.status === "running" && n.node === data.node
              ? { ...n, tools: [...n.tools, { tool, input: (data.input as string) ?? "" }] }
              : n
          )
        );
        break;
      }
      case "tool_result": {
        const tool = (data.tool as string) ?? "";
        const summary = (data.summary as string) ?? "";
        const ok = data.ok as boolean;
        setNodes((prev) =>
          prev.map((n) => {
            if (n.status !== "running" || n.node !== data.node) return n;
            const idx = [...n.tools].reverse().findIndex((t) => t.tool === tool && t.summary === undefined);
            if (idx === -1) return n;
            const target = n.tools.length - 1 - idx;
            return {
              ...n,
              tools: n.tools.map((t, i) => (i === target ? { ...t, summary, ok } : t)),
            };
          })
        );
        break;
      }
      case "reflection": {
        setNodes((prev) =>
          prev.map((n) =>
            n.status === "running" && n.node === data.node
              ? {
                  ...n,
                  reflections: [
                    ...n.reflections,
                    { text: (data.text as string) ?? "", action: (data.action as string) ?? "" },
                  ],
                }
              : n
          )
        );
        break;
      }
      case "done":
        setFinalReport(data.final_report as string);
        setSimplifiedReport(((data.simplified_report as string) ?? "").trim());
        setIsRunning(false);
        setStatusMessage("Research complete.");
        retriesRef.current = 0;
        break;
      case "cancelled":
        setIsRunning(false);
        setNodes((prev) => prev.map((n) => (n.status === "running" ? { ...n, status: "done" } : n)));
        setStatusMessage("Research cancelled.");
        retriesRef.current = 0;
        break;
      case "error":
        setIsRunning(false);
        setNodes((prev) => prev.map((n) => (n.status === "running" ? { ...n, status: "done", ok: false } : n)));
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
        // Unexpected close while running — attempt reconnect.
        // Read the live value via ref; the captured `isRunning` state is stale.
        const running = isRunningRef.current;
        if (running && retriesRef.current < WS_MAX_RETRIES && !ev.wasClean) {
          retriesRef.current += 1;
          setStatusMessage(
            `Connection lost. Retrying (${retriesRef.current}/${WS_MAX_RETRIES})…`
          );
          setTimeout(() => {
            connectWs();
          }, WS_RECONNECT_DELAY_MS * retriesRef.current);
        } else if (running) {
          setIsRunning(false);
          setErrorMessage(
            "The connection dropped while your research was running. Please try again."
          );
          setStatusMessage("");
        }
      };
    },
    [handleMessage]
  );

  const handleStart = async (topic: string, maxSteps: number) => {
    setIsRunning(true);
    setNodes([]);
    setPlanSteps([]);
    setEngine("");
    setFinalReport(null);
    setSimplifiedReport("");
    setCurrentTopic(topic);
    setResumeNote("");
    setStatusMessage("Connecting…");
    setErrorMessage("");
    retriesRef.current = 0;

    // The Business Check-up answers travel as STRUCTURED data ({field_id: text}).
    // The backend owns the canonical snippet from them — it is folded into the
    // run topic, injected into synthesis and persisted for the advisor chat, so
    // every surface reads the same intake. No extra LLM calls.
    const payload = {
      type: "start",
      topic,
      max_steps: maxSteps,
      session_id: sessionId,
      intake: profile,
    };

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
      return;
    }

    pendingStartRef.current = { topic, maxSteps, sessionId, profile: "", intake: profile };
    connectWs((ws) => {
      const pending = pendingStartRef.current;
      if (pending) {
        ws.send(
          JSON.stringify({
            type: "start",
            topic: pending.topic,
            max_steps: pending.maxSteps,
            session_id: pending.sessionId,
            intake: pending.intake,
          })
        );
        pendingStartRef.current = null;
      }
    });

    // Timeout fallback if connection never opens
    setTimeout(() => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) {
        setStatusMessage("");
        setErrorMessage(
          "We couldn't reach your Business Saathi just now. Please check your internet connection and try again."
        );
        setIsRunning(false);
      }
    }, 8000);
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

  if (!mounted) {
    return <div style={{ minHeight: "100vh" }} suppressHydrationWarning />;
  }

  return (
    <main
      suppressHydrationWarning
      className="page-shell"
      style={{
        minHeight: "100vh",
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
            fontSize: "clamp(0.68rem, 2.5vw, 0.78rem)",
            fontWeight: 600,
            color: "var(--accent)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            marginBottom: "10px",
            paddingInline: "8px",
          }}
        >
          Market research, growth planning &amp; government schemes for small businesses
        </h2>
        <p
          style={{
            fontSize: "clamp(1.65rem, 7vw, 2.2rem)",
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
          Your AI Business Saathi
        </p>
        <p
          style={{
            marginTop: "8px",
            fontSize: "0.92rem",
            color: "var(--text-muted)",
            maxWidth: "520px",
            margin: "8px auto 0",
          }}
        >
          Describe your business in plain language — get live market research, a clear business road-map, matched government schemes, and a loan-readiness checklist in under 60 seconds.
        </p>
      </motion.div>

      {/* Business Check-up — optional quick questions that sharpen the first report */}
      <StartupQuiz value={profile} onChange={changeProfile} />

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

      {/* Why Saathi — what makes this different from a generic chatbot */}
      <Usps />

      {/* Agent trace */}
      <AgentTimeline
        nodes={nodes}
        planSteps={planSteps}
        engine={engine}
        statusMessage={statusMessage}
        isRunning={isRunning}
      />

      {/* Resume banner */}
      <AnimatePresence>
        {resumeNote && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            style={{
              marginTop: "16px", width: "100%", maxWidth: "760px",
              display: "flex", alignItems: "center", gap: "10px",
              padding: "12px 18px",
              background: "rgba(251,146,60,0.08)",
              border: "1px solid rgba(251,146,60,0.25)",
              borderRadius: "var(--radius-md)",
            }}
          >
            <span style={{ fontSize: "0.82rem", color: "var(--warn)", flex: 1 }}>{resumeNote}</span>
            <button
              type="button"
              aria-label="Dismiss resume notice"
              onClick={() => setResumeNote("")}
              style={{ border: "none", background: "transparent", color: "var(--text-muted)", cursor: "pointer", display: "flex" }}
            >
              <X size={14} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Report */}
      <AnimatePresence>
        {finalReport && (
          <AdvisoryCard
            report={finalReport}
            topic={currentTopic}
            simplified={simplifiedReport}
            sessionId={sessionId}
          />
        )}
      </AnimatePresence>

      {/* Cash-flow simulator — self-serve financial viz, runs locally */}
      <CashflowSimulator />

      {/* Personal business advisor chat — one intake layer: it knows the same
          Business Check-up answers the research run used, and asks for what is
          still missing. */}
      <ChatPanel
        sessionId={sessionId}
        topic={currentTopic}
        intake={profile}
      />

      {/* Realtime voice advisor (LiveKit) */}
      <LiveAdvisorPanel />

      {/* WhatsApp Roadmap — voice input/output is now live; WhatsApp channel is next */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{
          marginTop: "48px",
          marginBottom: "80px",
          width: "100%",
          maxWidth: "760px",
          padding: "20px clamp(16px, 5vw, 24px)",
          background: "rgba(37,211,102,0.04)",
          border: "1px dashed rgba(37,211,102,0.3)",
          borderRadius: "var(--radius-xl)",
          display: "flex",
          alignItems: "center",
          gap: "16px",
        }}
      >
        <div style={{ width: "44px", height: "44px", borderRadius: "22px", background: "linear-gradient(135deg, #25D366, #128C7E)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: "0 4px 12px rgba(37,211,102,0.2)" }}>
          <MessageCircle size={22} color="#fff" />
        </div>
        <div>
          <div style={{ display: "inline-block", background: "rgba(37,211,102,0.15)", color: "#25D366", padding: "2px 8px", borderRadius: "10px", fontSize: "0.68rem", fontWeight: 700, marginBottom: "4px", textTransform: "uppercase" }}>
            Coming Next (Roadmap)
          </div>
          <p style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-primary)" }}>WhatsApp Advisory Bot</p>
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Deliver the same advisory via WhatsApp in Hindi, Marathi &amp; Gujarati — no app install needed.</p>
        </div>
      </motion.div>
    </main>
  );
}
