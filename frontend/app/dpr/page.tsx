"use client";

/**
 * /dpr — the bank-ready Detailed Project Report (WS-5).
 *
 * Reuses the Business Check-up answers (`useSession`) instead of asking again,
 * lets the user put a rupee figure on the project, then previews the report the
 * backend computed and offers the PDF. Every number on this page comes from
 * `/api/dpr`; nothing is calculated in the browser.
 */
import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  Download,
  ExternalLink,
  FileSpreadsheet,
  Loader2,
  Sparkles,
} from "lucide-react";
import { SiteHeader } from "@/components/SiteHeader";
import { API_BASE } from "@/lib/api";
import { track } from "@/lib/analytics";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/useSession";

type ReportTable = { columns: string[]; rows: string[][] };
type ReportSection = { id: string; title: string; body: string[]; table?: ReportTable | null };
type Report = {
  meta: {
    generated_on: string;
    business_label: string;
    scheme_id: string;
    scheme_name: string;
    source_url: string;
    last_verified_at: string;
    project_cost: number | null;
  };
  sections: ReportSection[];
  assumptions: string[];
  disclaimer: string;
};
type Job = {
  job_id: string;
  status: string;
  progress: string[];
  report: Report | null;
  pdf_url: string;
  error: string;
};
type Option = { scheme_id: string; scheme_name: string; status: string; status_label: string };

const STATUS_COLOR: Record<string, string> = {
  eligible: "var(--success)",
  likely: "var(--accent)",
  blocked: "var(--text-muted)",
};

/** Indian-grouped input helper: keeps only digits, so "₹1,00,000" is understood. */
function rupees(value: string): number | undefined {
  const digits = value.replace(/[^0-9]/g, "");
  if (!digits) return undefined;
  const parsed = Number(digits);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export default function DprPage() {
  const { t, locale } = useI18n();
  const { intake, ready, ensureSessionId } = useSession();

  const [options, setOptions] = useState<Option[]>([]);
  const [schemeId, setSchemeId] = useState("");
  const [cost, setCost] = useState("");
  const [sales, setSales] = useState("");
  const [expenses, setExpenses] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const hasProfile = Object.keys(intake).length > 0;

  // Offer the schemes this business actually matches, best first.
  useEffect(() => {
    if (!ready || !hasProfile) return;
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/eligibility`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ intake, lang: locale }),
          signal: controller.signal,
        });
        if (!res.ok) return;
        const data = await res.json();
        const seen = new Set<string>();
        const next: Option[] = [];
        // `/api/eligibility` returns the scored, open schemes under `ranked`
        // (each carrying `name`). Reading `verdicts` here used to leave the
        // dropdown empty, which silently disabled the whole page.
        for (const verdict of data.ranked ?? []) {
          if (!["eligible", "likely"].includes(verdict.status)) continue;
          const family = verdict.tier_group || verdict.scheme_id;
          if (seen.has(family)) continue;
          seen.add(family);
          next.push({
            scheme_id: verdict.scheme_id,
            scheme_name: verdict.name,
            status: verdict.status,
            status_label: verdict.status_label,
          });
        }
        setOptions(next);
        if (next.length && !schemeId) {
          const open = next.find((o) => o.status !== "blocked") ?? next[0];
          setSchemeId(open.scheme_id);
        }
      } catch {
        /* offline — the page still explains itself */
      }
    })();
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, JSON.stringify(intake), locale]);

  const generate = useCallback(async () => {
    setBusy(true);
    setFailed(false);
    try {
      const res = await fetch(`${API_BASE}/api/dpr`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          intake,
          scheme_id: schemeId,
          project_cost: rupees(cost) ?? null,
          monthly_sales: rupees(sales) ?? null,
          monthly_expenses: rupees(expenses) ?? null,
          session_id: ensureSessionId(),
          lang: locale,
        }),
      });
      if (!res.ok) throw new Error("request failed");
      const data: Job = await res.json();
      if (data.status !== "done" || !data.report) {
        setFailed(true);
        return;
      }
      setJob(data);
      track("dpr_generated", { scheme: schemeId });
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }, [intake, schemeId, cost, sales, expenses, ensureSessionId, locale]);

  return (
    <>
      <SiteHeader />
      <main style={{ maxWidth: "900px", marginInline: "auto", padding: "0 clamp(12px, 4vw, 20px) 60px" }}>
        <div style={{ padding: "28px 0 8px" }}>
          <h1
            style={{
              fontSize: "clamp(1.4rem, 3.2vw, 1.9rem)",
              fontWeight: 800,
              letterSpacing: "-0.02em",
              marginBottom: "8px",
              display: "flex",
              alignItems: "center",
              gap: "10px",
            }}
          >
            <FileSpreadsheet size={24} color="var(--accent)" aria-hidden="true" />
            {t("dpr.title")}
          </h1>
          <p style={{ color: "var(--text-secondary)", maxWidth: "640px", lineHeight: 1.6 }}>{t("dpr.subtitle")}</p>
        </div>

        {!ready ? null : !hasProfile ? (
          <div
            style={{
              marginTop: "18px",
              padding: "20px",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--border)",
              background: "var(--bg-elevated)",
            }}
          >
            <p style={{ color: "var(--text-secondary)", marginBottom: "14px" }}>{t("dpr.needProfile")}</p>
            <Link href="/research" style={ctaStyle}>
              <Sparkles size={15} aria-hidden="true" />
              {t("dpr.goToCheckup")}
            </Link>
          </div>
        ) : (
          <motion.section
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
            style={{
              marginTop: "18px",
              padding: "clamp(14px, 3vw, 22px)",
              borderRadius: "var(--radius-lg)",
              border: "1px solid var(--border)",
              background: "var(--bg-elevated)",
            }}
          >
            <div style={{ display: "grid", gap: "12px", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
              <Field label={t("dpr.scheme")} htmlFor="dpr-scheme">
                <select
                  id="dpr-scheme"
                  value={schemeId}
                  onChange={(e) => setSchemeId(e.target.value)}
                  style={{
                    ...inputStyle,
                    color: STATUS_COLOR[options.find((o) => o.scheme_id === schemeId)?.status ?? ""] ?? "var(--text-primary)",
                  }}
                >
                  {options.map((option) => (
                    <option key={option.scheme_id} value={option.scheme_id}>
                      {option.scheme_name} — {option.status_label}
                    </option>
                  ))}
                </select>
                {options.length === 0 && (
                  <p style={{ marginTop: "6px", fontSize: "0.74rem", color: "var(--text-muted)", lineHeight: 1.5 }}>{t("dpr.noSchemes")}</p>
                )}
              </Field>
              <Field label={`${t("dpr.cost")} (${t("dpr.optional")})`} htmlFor="dpr-cost">
                <input
                  id="dpr-cost"
                  inputMode="numeric"
                  value={cost}
                  onChange={(e) => setCost(e.target.value)}
                  placeholder="10,00,000"
                  style={inputStyle}
                />
              </Field>
              <Field label={`${t("dpr.sales")} (${t("dpr.optional")})`} htmlFor="dpr-sales">
                <input
                  id="dpr-sales"
                  inputMode="numeric"
                  value={sales}
                  onChange={(e) => setSales(e.target.value)}
                  placeholder="1,20,000"
                  style={inputStyle}
                />
              </Field>
              <Field label={`${t("dpr.expenses")} (${t("dpr.optional")})`} htmlFor="dpr-expenses">
                <input
                  id="dpr-expenses"
                  inputMode="numeric"
                  value={expenses}
                  onChange={(e) => setExpenses(e.target.value)}
                  placeholder="80,000"
                  style={inputStyle}
                />
              </Field>
            </div>

            <p style={{ marginTop: "10px", fontSize: "0.74rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
              {t("dpr.optionalHint")}
            </p>

            <div style={{ marginTop: "14px", display: "flex", flexWrap: "wrap", alignItems: "center", gap: "12px" }}>
              <button
                type="button"
                onClick={generate}
                disabled={busy || !schemeId}
                style={{ ...ctaStyle, opacity: busy || !schemeId ? 0.6 : 1, border: "none", cursor: busy ? "default" : "pointer" }}
              >
                {busy ? <Loader2 size={15} className="spin" aria-hidden="true" /> : <FileSpreadsheet size={15} aria-hidden="true" />}
                {busy ? t("dpr.generating") : t("dpr.generate")}
              </button>
              {job?.pdf_url && (
                <a href={`${API_BASE}${job.pdf_url}`} style={{ ...ctaStyle, background: "transparent", border: "1px solid var(--border-bright)" }}>
                  <Download size={15} aria-hidden="true" />
                  {t("dpr.download")}
                </a>
              )}
            </div>

            {failed && (
              <p
                style={{
                  marginTop: "12px",
                  display: "flex",
                  alignItems: "center",
                  gap: "7px",
                  fontSize: "0.8rem",
                  color: "var(--warn, #fb923c)",
                }}
              >
                <AlertTriangle size={14} aria-hidden="true" />
                {t("dpr.failed")}
              </p>
            )}
          </motion.section>
        )}

        {job?.report && (
          <motion.article
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
            style={{ marginTop: "20px", display: "grid", gap: "16px" }}
          >
            <div
              style={{
                padding: "14px 16px",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--border)",
                background: "var(--bg-elevated)",
                display: "flex",
                flexWrap: "wrap",
                gap: "6px 16px",
                alignItems: "center",
                fontSize: "0.8rem",
              }}
            >
              <strong style={{ fontSize: "0.92rem" }}>{job.report.meta.scheme_name}</strong>
              <span style={{ color: "var(--text-muted)" }}>{job.report.meta.generated_on}</span>
              {job.report.meta.source_url && (
                <a
                  href={job.report.meta.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ display: "inline-flex", alignItems: "center", gap: "5px", color: "var(--accent)", textDecoration: "none" }}
                >
                  <ExternalLink size={12} aria-hidden="true" />
                  {t("dpr.source")}
                </a>
              )}
              <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{t("dpr.pdfNote")}</span>
            </div>

            {job.report.sections.map((section) => (
              <section
                key={section.id}
                style={{
                  padding: "16px",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--border)",
                  background: "var(--bg-elevated)",
                }}
              >
                <h2 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "8px" }}>{section.title}</h2>
                {section.body.map((line, index) => (
                  <p key={index} style={{ fontSize: "0.83rem", color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: "5px", wordBreak: "break-word" }}>
                    {line}
                  </p>
                ))}
                {section.table && section.table.rows.length > 0 && (
                  <div style={{ overflowX: "auto", marginTop: "8px" }}>
                    <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.76rem", minWidth: "420px" }}>
                      <thead>
                        <tr>
                          {section.table.columns.map((column) => (
                            <th key={column} style={thStyle}>
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {section.table.rows.map((row, rowIndex) => (
                          <tr key={rowIndex}>
                            {row.map((cell, cellIndex) => (
                              <td key={cellIndex} style={tdStyle}>
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            ))}

            <section
              style={{
                padding: "16px",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--border)",
                background: "var(--bg-elevated)",
              }}
            >
              <h2 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "8px" }}>{t("dpr.assumptions")}</h2>
              <ul style={{ listStyle: "none", display: "grid", gap: "5px" }}>
                {job.report.assumptions.map((assumption) => (
                  <li key={assumption} style={{ fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                    • {assumption}
                  </li>
                ))}
              </ul>
              <p style={{ marginTop: "10px", fontSize: "0.74rem", color: "var(--text-muted)", lineHeight: 1.55 }}>
                {job.report.disclaimer}
              </p>
            </section>
          </motion.article>
        )}
      </main>
    </>
  );
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} style={labelStyle}>
        {label}
      </label>
      {children}
    </div>
  );
}

const labelStyle: CSSProperties = {
  display: "block",
  fontSize: "0.72rem",
  fontWeight: 600,
  color: "var(--text-muted)",
  marginBottom: "5px",
};

const inputStyle: CSSProperties = {
  width: "100%",
  background: "var(--bg-surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "9px 11px",
  fontSize: "0.85rem",
  color: "var(--text-primary)",
  fontFamily: "inherit",
};

const ctaStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "8px",
  padding: "11px 20px",
  borderRadius: "var(--radius-md)",
  background: "linear-gradient(135deg, var(--accent), var(--accent-dim))",
  color: "#fff",
  textDecoration: "none",
  fontWeight: 700,
  fontSize: "0.87rem",
};

const thStyle: CSSProperties = {
  textAlign: "left",
  padding: "7px 9px",
  borderBottom: "1px solid var(--border-bright)",
  color: "var(--text-muted)",
  fontWeight: 700,
  whiteSpace: "nowrap",
};

const tdStyle: CSSProperties = {
  padding: "7px 9px",
  borderBottom: "1px solid var(--border)",
  color: "var(--text-secondary)",
};
