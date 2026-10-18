"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import {
  getClient,
  matchClient,
  listNotes,
  addNote,
  deleteNote,
  generateReport,
  downloadReport,
  type Client,
  type MatchResult,
} from "@/lib/advisor";
import { Loader2, Trash2, Download, FileText, AlertCircle } from "lucide-react";

export default function ClientDetailPage() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useParams();
  const clientId = (params as { id: string }).id;

  const [client, setClient] = useState<Client | null>(null);
  const [match, setMatch] = useState<MatchResult | null>(null);
  const [notes, setNotes] = useState<{ id: string; body: string; created_at: number }[]>([]);
  const [noteBody, setNoteBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [matching, setMatching] = useState(false);
  const [error, setError] = useState("");
  const [locale] = useState("en");

  const loadClient = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    try {
      const c = await getClient(clientId);
      setClient(c);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("workspace.error"));
    } finally {
      setLoading(false);
    }
  }, [clientId, t]);

  const loadNotes = useCallback(async () => {
    if (!clientId) return;
    try {
      const n = await listNotes(clientId);
      setNotes(n);
    } catch {
      /* notes are optional; silent on failure */
    }
  }, [clientId]);

  useEffect(() => {
    loadClient();
    loadNotes();
  }, [loadClient, loadNotes]);

  const runMatch = async () => {
    if (!client) return;
    setMatching(true);
    setError("");
    try {
      const m = await matchClient(clientId, {
        topic: "",
        amount: undefined,
        lang: locale,
        intake: client.profile as Record<string, string>,
      });
      setMatch(m);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("workspace.error"));
    } finally {
      setMatching(false);
    }
  };

  const addNoteHandler = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!noteBody.trim() || !clientId) return;
    try {
      const n = await addNote(clientId, noteBody.trim());
      setNoteBody("");
      setNotes((prev) => [n, ...prev]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("workspace.error"));
    }
  };

  const removeNote = async (id: string) => {
    try {
      await deleteNote(id);
      setNotes((prev) => prev.filter((n) => n.id !== id));
    } catch {
      /* silent */
    }
  };

  const exportPdf = async (kind: "single" | "combined") => {
    if (!client) return;
    setLoading(true);
    try {
      const report = await generateReport({ kind, client_ids: [clientId], locale });
      await downloadReport(report.id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("workspace.error"));
    } finally {
      setLoading(false);
    }
  };

  if (loading && !client) {
    return (
      <div style={{ padding: "32px 20px", textAlign: "center", color: "var(--text-muted)" }}>
        {t("workspace.loading")}
      </div>
    );
  }
  if (!client) {
    return (
      <div style={{ padding: "32px 20px", textAlign: "center", color: "var(--error)" }}>
        {error || t("workspace.error")}
        <br />
        <button onClick={() => router.push("/workspace")} style={{ marginTop: "10px", padding: "8px 14px", fontSize: "0.86rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", background: "transparent", cursor: "pointer" }}>
          {t("workspace.back")}
        </button>
      </div>
    );
  }

  const ranked = match?.ranked ?? [];
  const documents = Array.from(
    new Set(ranked.flatMap((m) => (m.documents as unknown as string[]) ?? [])),
  );

  return (
    <div style={{ padding: "24px 20px", maxWidth: "900px", margin: "0 auto" }}>
      <nav style={{ marginBottom: "16px" }}>
        <a
          href="/workspace"
          onClick={() => router.push("/workspace")}
          style={{ display: "inline-flex", alignItems: "center", gap: "8px", fontSize: "0.84rem", color: "var(--text-secondary)", textDecoration: "none" }}
        >
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          {t("workspace.back")}
        </a>
      </nav>

      {error && (
        <div style={{ marginBottom: "16px", padding: "10px 14px", borderRadius: "var(--radius-md)", background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.25)", color: "var(--error)", fontSize: "0.84rem", display: "flex", alignItems: "center", gap: "8px" }}>
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px" }}>
        <div>
          <h1 style={{ fontSize: "1.25rem", fontWeight: 800, marginBottom: "2px" }}>{client.label}</h1>
          <p style={{ fontSize: "0.86rem", color: "var(--text-muted)" }}>{t("workspace.client_detail")}</p>
        </div>
        <div style={{ display: "flex", gap: "10px" }}>
          <button
            onClick={runMatch}
            disabled={matching}
            style={{ display: "flex", alignItems: "center", gap: "8px", padding: "9px 14px", fontSize: "0.88rem", fontWeight: 700, borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--accent)", color: "#fff", cursor: matching ? "not-allowed" : "pointer", opacity: matching ? 0.7 : 1 }}
          >
            {matching ? <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} /> : ""} Match schemes
          </button>
          <button
            onClick={() => exportPdf("single")}
            disabled={loading}
            style={{ display: "flex", alignItems: "center", gap: "8px", padding: "9px 14px", fontSize: "0.88rem", fontWeight: 700, borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.7 : 1 }}
          >
            <Download size={16} /> {t("workspace.export_single")}
          </button>
        </div>
      </div>

      {/* Profile */}
      <section style={{ marginBottom: "24px", padding: "18px 20px", borderRadius: "var(--radius-lg)", background: "var(--bg-card)", border: "1px solid var(--border)" }}>
        <h2 style={{ fontSize: "0.9rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", marginBottom: "12px" }}>{t("workspace.profile")}</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px" }}>
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("workspace.business_type")}</div>
            <div style={{ fontSize: "0.9rem", color: "var(--text-primary)" }}>{String(client.profile.business ?? "—")}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("workspace.location")}</div>
            <div style={{ fontSize: "0.9rem", color: "var(--text-primary)" }}>{String(client.profile.location ?? "—")}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("workspace.sector")}</div>
            <div style={{ fontSize: "0.9rem", color: "var(--text-primary)" }}>{client.sector || "—"}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("workspace.state")}</div>
            <div style={{ fontSize: "0.9rem", color: "var(--text-primary)" }}>{client.state || "—"}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("workspace.stage")}</div>
            <div style={{ fontSize: "0.9rem", color: "var(--text-primary)" }}>{client.stage || "—"}</div>
          </div>
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("workspace.readiness_score")}</div>
            <div style={{ fontSize: "1.5rem", fontWeight: 800, color: match ? (match.readiness ?? 0) >= 70 ? "var(--success)" : (match.readiness ?? 0) >= 40 ? "var(--warn)" : "var(--error)" : "var(--text-muted)" }}>
              {client.readiness != null ? client.readiness : "—"} / 100
            </div>
          </div>
        </div>
      </section>

      {/* Matches */}
      <section style={{ marginBottom: "24px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
          <h2 style={{ fontSize: "0.9rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)" }}>{t("workspace.matches")}</h2>
          {match && <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{ranked.length} scheme{(ranked.length === 1 ? "" : "s")} matched</span>}
        </div>
        {matching && (
          <div style={{ marginBottom: "12px", padding: "10px 14px", borderRadius: "var(--radius-md)", background: "var(--bg-surface)", color: "var(--text-muted)", fontSize: "0.86rem", display: "flex", alignItems: "center", gap: "8px" }}>
            <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} /> Running eligibility…
          </div>
        )}
        {!match && !matching && (
          <div style={{ padding: "10px 14px", color: "var(--text-muted)", fontSize: "0.86rem" }}>
            Tap &quot;Match schemes&quot; to see which schemes this client qualifies for.
          </div>
        )}
        {match && ranked.length === 0 && (
          <div style={{ padding: "14px", borderRadius: "var(--radius-md)", background: "var(--bg-surface)", color: "var(--text-muted)", fontSize: "0.86rem" }}>
            No schemes matched this client&apos;s profile.
          </div>
        )}
        {match && ranked.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {ranked.map((m) => {
              const statusColor = (() => {
                switch (m.status) {
                  case "eligible": return "var(--success)";
                  case "likely": return "var(--warn)";
                  case "blocked": return "var(--error)";
                  default: return "var(--text-muted)";
                }
              })();
              return (
                <div key={m.scheme_id} style={{ padding: "12px 14px", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", background: "var(--bg-card)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "6px" }}>
                    <div style={{ fontWeight: 800, fontSize: "0.95rem" }}>{m.name}</div>
                    <span style={{ fontSize: "0.78rem", fontWeight: 700, color: statusColor }}>{m.status_label}</span>
                  </div>
                  <div style={{ fontSize: "0.84rem", color: "var(--text-secondary)", marginBottom: "6px" }}>
                    Score {m.score} / 100  <span style={{ color: "var(--text-muted)" }}>·</span>
                    {m.tier_group ? `Tier: ${m.tier_group}` : ""}
                  </div>
                  {(m.matched as unknown as { label: string }[]).length > 0 && (
                    <div style={{ fontSize: "0.82rem", color: "var(--text-primary)", marginBottom: "4px" }}>
                      <span style={{ fontWeight: 600, color: "var(--text-muted)", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", marginRight: "6px" }}>Why you qualify</span>
                      {(m.matched as unknown as { label: string }[]).map((r, i) => (
                        <span key={i} style={{ display: "inline-block", marginRight: "8px", fontSize: "0.82rem" }}>✓ {r.label}</span>
                      ))}
                    </div>
                  )}
                  {(m.failed as unknown as { label: string }[]).length > 0 && (
                    <div style={{ fontSize: "0.82rem", color: "var(--error)", marginBottom: "4px" }}>
                      <span style={{ fontWeight: 600, color: "var(--error)", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", marginRight: "6px" }}>What to fix</span>
                      {(m.failed as unknown as { label: string }[]).map((r, i) => (
                        <span key={i} style={{ display: "inline-block", marginRight: "8px", fontSize: "0.82rem" }}>✗ {r.label}</span>
                      ))}
                    </div>
                  )}
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                    {m.source_url ? `Source: ${m.source_url}` : ""}
                    {m.last_verified_at ? `  (verified ${m.last_verified_at})` : ""}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {documents.length > 0 && (
        <section style={{ marginBottom: "24px" }}>
          <h2 style={{ fontSize: "0.9rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", marginBottom: "12px" }}>{t("workspace.documents")}</h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {documents.map((d) => (
              <span key={d} style={{ padding: "6px 10px", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", background: "var(--bg-surface)", fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                <FileText size={12} style={{ marginRight: "6px" }} /> {d}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Notes */}
      <section>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
          <h2 style={{ fontSize: "0.9rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)" }}>{t("workspace.notes")}</h2>
        </div>
        <form onSubmit={addNoteHandler} style={{ display: "flex", gap: "10px", marginBottom: "14px", flexWrap: "wrap" }}>
          <input
            type="text"
            value={noteBody}
            onChange={(e) => setNoteBody(e.target.value)}
            placeholder={t("workspace.note_placeholder")}
            style={{ flex: 1, minWidth: "220px", padding: "10px 14px", fontSize: "0.88rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}
          />
          <button type="submit" disabled={!noteBody.trim()} style={{ padding: "10px 16px", fontSize: "0.88rem", fontWeight: 700, borderRadius: "var(--radius-md)", border: "none", background: "var(--accent)", color: "#fff", cursor: !noteBody.trim() ? "not-allowed" : "pointer" }}>
            {t("workspace.save_note")}
          </button>
        </form>
        {notes.length === 0 ? (
          <div style={{ padding: "10px 14px", color: "var(--text-muted)", fontSize: "0.86rem" }}>{t("workspace.reports_empty")}</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {notes.map((n) => (
              <div key={n.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "10px 14px", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", background: "var(--bg-card)" }}>
                <div>
                  <p style={{ fontSize: "0.9rem", color: "var(--text-primary)", marginBottom: "2px" }}>{n.body}</p>
                  <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>{new Date(n.created_at * 1000).toLocaleDateString()}</span>
                </div>
                <button
                  onClick={() => removeNote(n.id)}
                  style={{ padding: "6px", color: "var(--text-muted)", border: "none", background: "none", cursor: "pointer" }}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
