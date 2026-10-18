"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import { listReports, generateReport, downloadReport, advisorMe, listClients, type Report } from "@/lib/advisor";
import { FileText, Download, Plus, AlertCircle } from "lucide-react";

export default function ReportsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [reports, setReports] = useState<Report[]>([]);
  const [me, setMe] = useState<{ name: string; plan: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, m] = await Promise.all([listReports(), advisorMe()]);
      setReports(r);
      setMe({ name: m.name, plan: m.plan });
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("workspace.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { load(); }, [load]);

  const generateCombined = async () => {
    setGenerating(true);
    setError("");
    try {
      const clientsRes = await listClients();
      const ids = clientsRes.clients.map((c) => c.id);
      if (ids.length === 0) {
        setError("Add at least one client before generating a report.");
        return;
      }
      const report = await generateReport({ kind: "combined", client_ids: ids, locale: "en" });
      await downloadReport(report.id);
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("workspace.error"));
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async (id: string) => {
    setError("");
    try {
      await downloadReport(id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("workspace.error"));
    }
  };

  if (loading) {
    return (
      <div style={{ padding: "32px 20px", textAlign: "center", color: "var(--text-muted)" }}>
        {t("workspace.loading")}
      </div>
    );
  }

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

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px" }}>
        <div>
          <h1 style={{ fontSize: "1.25rem", fontWeight: 800, marginBottom: "2px" }}>{t("workspace.reports")}</h1>
          <p style={{ fontSize: "0.86rem", color: "var(--text-muted)" }}>{me ? `Advisor: ${me.name} (${me.plan})` : ""}</p>
        </div>
        <button
          onClick={generateCombined}
          disabled={generating}
          style={{ display: "flex", alignItems: "center", gap: "8px", padding: "9px 16px", fontSize: "0.88rem", fontWeight: 700, borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--accent)", color: "#fff", cursor: generating ? "not-allowed" : "pointer", opacity: generating ? 0.7 : 1 }}
        >
          <Plus size={16} /> {t("workspace.export_combined")}
        </button>
      </div>

      {error && (
        <div style={{ marginBottom: "16px", padding: "10px 14px", borderRadius: "var(--radius-md)", background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.25)", color: "var(--error)", fontSize: "0.84rem", display: "flex", alignItems: "center", gap: "8px" }}>
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {reports.length === 0 ? (
        <div style={{ padding: "32px 24px", textAlign: "center", color: "var(--text-muted)", border: "1px dashed var(--border)", borderRadius: "var(--radius-lg)", background: "var(--bg-surface)" }}>
          <FileText size={32} style={{ marginBottom: "10px", color: "var(--text-muted)" }} />
          <p style={{ fontSize: "0.9rem" }}>{t("workspace.reports_empty")}</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {reports.map((r) => (
            <div key={r.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", background: "var(--bg-card)" }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: "0.92rem", color: "var(--text-primary)" }}>
                  {r.kind === "combined" ? t("workspace.report_kind_combined") : t("workspace.report_kind_single")}
                </div>
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  {r.client_ids.length} client{(r.client_ids.length === 1 ? "" : "s")} · {r.locale.toUpperCase()} · {new Date(r.created_at * 1000).toLocaleDateString()}
                </div>
              </div>
              <button
                onClick={() => handleDownload(r.id)}
                style={{ display: "flex", alignItems: "center", gap: "6px", padding: "8px 14px", fontSize: "0.84rem", fontWeight: 600, borderRadius: "var(--radius-md)", border: "1px solid var(--border)", background: "var(--bg-surface)", color: "var(--text-primary)", cursor: "pointer" }}
              >
                <Download size={16} /> {t("workspace.export_pdf")}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
