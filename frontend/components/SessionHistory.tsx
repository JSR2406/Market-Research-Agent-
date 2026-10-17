"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  History,
  Loader2,
  ChevronDown,
  FileText,
  AlertTriangle,
  Download,
  Trash2,
  ArrowRight,
} from "lucide-react";
import { API_BASE } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export type RunSummary = {
  run_id: string;
  created_at: number | null;
  topic: string;
  has_report: boolean;
  eligibility?: {
    business_class?: string;
    business_label?: string;
    amount?: number | null;
  };
  loan_ready_score?: number | null;
};

interface Props {
  sessionId: string;
  /** Non-empty while a research run is live — renders a real-time entry. */
  runningTopic?: string;
  /** Change this value (e.g. the finished report) to trigger a refetch. */
  refreshKey?: string | number;
  /** Cap how many runs to show inline (the rest live on /history). */
  limit?: number;
  /** Offer the "open full history" link (off on the /history page itself). */
  showViewAll?: boolean;
  /** Called after the user deletes the session. */
  onDeleted?: () => void;
}

function formatWhen(ts: number | null, locale: string): string {
  if (!ts) return "";
  try {
    return new Date(ts * 1000).toLocaleString(locale === "hi" ? "hi-IN" : "en-IN", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

/**
 * Session History — the visible store of everything researched in this session.
 *
 * The backend keeps every run in `backend/sessions/{id}.json` (capped, newest
 * first). This section makes that history real and usable: it lists each run,
 * shows a live in-progress entry while a run is happening, and lets the user
 * re-open a past report, export the whole session, or delete it.
 */
export default function SessionHistory({
  sessionId,
  runningTopic = "",
  refreshKey,
  limit,
  showViewAll = false,
  onDeleted,
}: Props) {
  const { t, locale } = useI18n();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [report, setReport] = useState<string>("");
  const [reportLoading, setReportLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (!sessionId) {
      setRuns([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setFailed(false);
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/runs`);
      if (!res.ok) throw new Error("bad status");
      const body = await res.json();
      setRuns(Array.isArray(body?.runs) ? (body.runs as RunSummary[]) : []);
    } catch (err) {
      console.error("history load failed:", err);
      setFailed(true);
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  // Refetch once a live run stops being live, so the freshly saved run appears.
  const wasRunning = useCallback(() => runningTopic !== "", [runningTopic]);
  useEffect(() => {
    if (!wasRunning()) return;
    const id = window.setInterval(() => {
      // Light poll while a run is live so the list stays current in real time.
      if (sessionId) {
        fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/runs`)
          .then((r) => (r.ok ? r.json() : null))
          .then((b) => Array.isArray(b?.runs) && setRuns(b.runs as RunSummary[]))
          .catch(() => {});
      }
    }, 5000);
    return () => window.clearInterval(id);
  }, [wasRunning, sessionId]);

  const toggle = async (run: RunSummary) => {
    if (openId === run.run_id) {
      setOpenId(null);
      return;
    }
    setOpenId(run.run_id);
    setReport("");
    setReportLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/runs/${encodeURIComponent(run.run_id)}`
      );
      if (!res.ok) throw new Error("bad status");
      const body = await res.json();
      setReport(((body?.simplified_report as string) || (body?.final_report as string) || "").trim());
    } catch (err) {
      console.error("history run load failed:", err);
      setReport("");
    } finally {
      setReportLoading(false);
    }
  };

  const exportSession = async () => {
    setBusy(true);
    setNotice("");
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/export`);
      if (!res.ok) throw new Error("bad status");
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `saathi-session-${sessionId}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("export failed:", err);
      setNotice(t("history.error"));
    } finally {
      setBusy(false);
    }
  };

  const deleteSession = async () => {
    setBusy(true);
    setNotice("");
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("bad status");
      setRuns([]);
      setOpenId(null);
      setNotice(t("history.clearDone"));
      onDeleted?.();
    } catch (err) {
      console.error("delete failed:", err);
      setNotice(t("history.clearFailed"));
    } finally {
      setBusy(false);
    }
  };

  const visible = typeof limit === "number" ? runs.slice(0, limit) : runs;
  const hidden = runs.length - visible.length;

  return (
    <section
      aria-label={t("history.title")}
      style={{
        width: "100%",
        maxWidth: "760px",
        marginTop: "32px",
        padding: "20px clamp(16px, 4vw, 24px)",
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-xl)",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: "12px", marginBottom: "14px" }}>
        <span
          aria-hidden="true"
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: "38px",
            height: "38px",
            borderRadius: "12px",
            background: "var(--accent-glow)",
            flexShrink: 0,
          }}
        >
          <History size={19} color="var(--accent)" />
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2 style={{ fontSize: "1.02rem", fontWeight: 700, marginBottom: "2px" }}>
            {t("history.title")}
          </h2>
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{t("history.subtitle")}</p>
        </div>
        <div style={{ display: "flex", gap: "8px", flexShrink: 0 }}>
          <button
            type="button"
            onClick={exportSession}
            disabled={busy || (!runs.length && !runningTopic)}
            aria-label="Export session data"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 12px",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--border-bright)",
              background: "transparent",
              color: "var(--text-secondary)",
              fontSize: "0.78rem",
              fontWeight: 600,
              cursor: busy ? "default" : "pointer",
              fontFamily: "inherit",
              opacity: busy || (!runs.length && !runningTopic) ? 0.5 : 1,
            }}
          >
            <Download size={14} aria-hidden="true" />
            {t("history.export")}
          </button>
          <button
            type="button"
            onClick={deleteSession}
            disabled={busy || (!runs.length && !runningTopic)}
            aria-label={t("history.clear")}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 12px",
              borderRadius: "var(--radius-md)",
              border: "1px solid rgba(248,113,113,0.35)",
              background: "transparent",
              color: "var(--error)",
              fontSize: "0.78rem",
              fontWeight: 600,
              cursor: busy ? "default" : "pointer",
              fontFamily: "inherit",
              opacity: busy || (!runs.length && !runningTopic) ? 0.5 : 1,
            }}
          >
            <Trash2 size={14} aria-hidden="true" />
            {t("history.clear")}
          </button>
        </div>
      </div>

      {notice && (
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "10px" }} role="status">
          {notice}
        </p>
      )}

      {loading && (
        <p
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            color: "var(--text-muted)",
            fontSize: "0.84rem",
            padding: "12px 0",
          }}
        >
          <Loader2 size={15} className="spin" aria-hidden="true" />
          {t("history.loading")}
        </p>
      )}

      {!loading && failed && (
        <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "10px 0" }}>
          <AlertTriangle size={15} color="var(--error)" aria-hidden="true" />
          <span style={{ color: "var(--error)", fontSize: "0.84rem" }}>{t("history.error")}</span>
          <button
            type="button"
            onClick={load}
            style={{
              padding: "5px 12px",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--border-bright)",
              background: "transparent",
              color: "var(--text-primary)",
              fontSize: "0.78rem",
              fontWeight: 600,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            {t("history.retry")}
          </button>
        </div>
      )}

      {!loading && !failed && (
        <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "8px" }}>
          {/* Real-time entry while a run is in progress. */}
          {runningTopic !== "" && (
            <li>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  padding: "11px 14px",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--accent)",
                  background: "var(--accent-glow)",
                }}
              >
                <Loader2 size={15} color="var(--accent)" className="spin" aria-hidden="true" />
                <span
                  style={{
                    flex: 1,
                    minWidth: 0,
                    fontSize: "0.86rem",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {runningTopic || t("history.topicFallback")}
                </span>
                <span style={{ fontSize: "0.74rem", color: "var(--accent)", fontWeight: 600, flexShrink: 0 }}>
                  {t("history.inProgress")}
                </span>
              </div>
            </li>
          )}

          {!loading && !failed && visible.length === 0 && runningTopic === "" && (
            <li style={{ color: "var(--text-muted)", fontSize: "0.84rem", padding: "6px 0" }}>
              {t("history.empty")}
            </li>
          )}

          <AnimatePresence initial={false}>
            {visible.map((run) => {
              const expanded = openId === run.run_id;
              const label = run.eligibility?.business_label || "";
              const amount = run.eligibility?.amount;
              const score = run.loan_ready_score;
              return (
                <motion.li
                  key={run.run_id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-md)",
                    overflow: "hidden",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "11px 14px" }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p
                        style={{
                          fontSize: "0.86rem",
                          fontWeight: 600,
                          color: "var(--text-primary)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {run.topic || t("history.topicFallback")}
                      </p>
                      <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "flex", gap: "8px", flexWrap: "wrap" }}>
                        <span>
                          {t("history.savedOn")} {formatWhen(run.created_at, locale)}
                        </span>
                        {label && <span>· {label}</span>}
                        {typeof amount === "number" && amount > 0 && (
                          <span>· ₹{amount.toLocaleString("en-IN")}</span>
                        )}
                        {typeof score === "number" && (
                          <span>
                            · {t("history.loanReady")} {score}/100
                          </span>
                        )}
                      </p>
                    </div>
                    {run.has_report ? (
                      <button
                        type="button"
                        onClick={() => toggle(run)}
                        aria-expanded={expanded}
                        aria-controls={`run-${run.run_id}`}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          padding: "6px 12px",
                          borderRadius: "var(--radius-md)",
                          border: "1px solid var(--border-bright)",
                          background: "transparent",
                          color: "var(--text-primary)",
                          fontSize: "0.78rem",
                          fontWeight: 600,
                          cursor: "pointer",
                          fontFamily: "inherit",
                          flexShrink: 0,
                        }}
                      >
                        <FileText size={13} aria-hidden="true" />
                        {expanded ? t("history.hideReport") : t("history.viewReport")}
                        <ChevronDown
                          size={13}
                          aria-hidden="true"
                          style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}
                        />
                      </button>
                    ) : (
                      <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", flexShrink: 0 }}>
                        {t("history.noReport")}
                      </span>
                    )}
                  </div>

                  <AnimatePresence initial={false}>
                    {expanded && (
                      <motion.div
                        id={`run-${run.run_id}`}
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        style={{ overflow: "hidden", borderTop: "1px solid var(--border)" }}
                      >
                        <div style={{ padding: "12px 14px" }}>
                          {reportLoading ? (
                            <span style={{ display: "inline-flex", alignItems: "center", gap: "8px", color: "var(--text-muted)", fontSize: "0.82rem" }}>
                              <Loader2 size={14} className="spin" aria-hidden="true" />
                              {t("history.loading")}
                            </span>
                          ) : (
                            <p style={{ fontSize: "0.84rem", color: "var(--text-secondary)", whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                              {report || t("history.noReport")}
                            </p>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ul>
      )}

      {hidden > 0 && (
        <p style={{ marginTop: "10px", fontSize: "0.78rem", color: "var(--text-muted)" }}>
          {t("history.limited", { n: runs.length })}
        </p>
      )}

      {showViewAll && (
        <Link
          href="/history"
          style={{
            marginTop: "14px",
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            color: "var(--accent)",
            textDecoration: "none",
            fontSize: "0.82rem",
            fontWeight: 600,
          }}
        >
          {t("history.viewAll")}
          <ArrowRight size={14} aria-hidden="true" />
        </Link>
      )}
    </section>
  );
}
