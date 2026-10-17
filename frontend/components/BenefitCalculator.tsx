"use client";
/**
 * BenefitCalculator.tsx — "how much?" for every scheme the check-up matches.
 *
 * The eligibility panel answers *whether* a scheme is open; this answers *how
 * much* — and it asks the backend (`POST /api/benefits`), which computes every
 * figure in code from `schemes.json`. Nothing here does arithmetic the server
 * could do, so the number on screen can always be traced to a source.
 *
 * Two deliberate choices:
 * 1. The project-cost box is optional. Without it the calculator publishes the
 *    published rates and a worked example instead of inventing a total.
 * 2. Loans and subsidy money are shown separately — a loan ceiling is not
 *    "benefit", and adding them together would mislead.
 */
import { useEffect, useState, type CSSProperties } from "react";
import { motion } from "framer-motion";
import { Calculator, ChevronDown, ExternalLink, Info } from "lucide-react";
import { API_BASE } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { IntakeAnswers } from "@/lib/intake";

type BenefitRow = {
  scheme_id: string;
  scheme_name: string;
  status: string;
  status_label: string;
  kind: string;
  repayable: boolean;
  lines: string[];
  subsidy_min: number | null;
  subsidy_max: number | null;
  loan_min: number | null;
  loan_max: number | null;
  source_url: string;
  last_verified_at: string;
  tiers?: { name: string; min_amount: number | null; max_amount: number | null }[];
};

type BenefitResult = {
  business_label?: string;
  project_cost?: number | null;
  rows: BenefitRow[];
  headline: {
    subsidy_min: number | null;
    subsidy_max: number | null;
    loan_access: number;
    matched_count: number;
  };
  assumptions: string[];
  disclaimer: string;
};

/** Indian-grouped rupees: 250000 → "₹2,50,000". */
function inr(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const digits = String(Math.round(Math.abs(value)));
  let grouped = digits;
  if (digits.length > 3) {
    const tail = digits.slice(-3);
    let head = digits.slice(0, -3);
    const parts: string[] = [];
    while (head.length > 2) {
      parts.unshift(head.slice(-2));
      head = head.slice(0, -2);
    }
    if (head) parts.unshift(head);
    grouped = `${parts.join(",")},${tail}`;
  }
  return `₹${value < 0 ? "-" : ""}${grouped}`;
}

export default function BenefitCalculator({ intake }: { intake: IntakeAnswers }) {
  const { t, locale } = useI18n();
  const [cost, setCost] = useState("");
  const [result, setResult] = useState<BenefitResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      (async () => {
        setLoading(true);
        try {
          const parsed = Number(cost.replace(/[^0-9]/g, ""));
          const res = await fetch(`${API_BASE}/api/benefits`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              intake,
              project_cost: parsed >= 1000 ? parsed : null,
              lang: locale,
            }),
            signal: controller.signal,
          });
          if (!res.ok) return;
          setResult(await res.json());
        } catch {
          /* offline — the quiz keeps working, the estimate simply stays old */
        } finally {
          setLoading(false);
        }
      })();
    }, 800);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(intake), cost, locale]);

  const rows = result?.rows ?? [];
  const visible = showAll ? rows : rows.slice(0, 3);
  const { subsidy_min: subsidyMin, subsidy_max: subsidyMax, loan_access: loanAccess } =
    result?.headline ?? { subsidy_min: null, subsidy_max: null, loan_access: 0 };

  return (
    <motion.section
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      aria-label={t("benefits.title")}
      style={{
        marginTop: "12px",
        padding: "12px",
        borderRadius: "10px",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid var(--border)",
      }}
    >
      <p
        style={{
          margin: 0,
          fontSize: "0.74rem",
          fontWeight: 700,
          color: "var(--text-primary)",
          display: "flex",
          alignItems: "center",
          gap: "6px",
        }}
      >
        <Calculator size={13} />
        {t("benefits.title")}
        {loading && (
          <span style={{ fontWeight: 500, color: "var(--text-muted)", fontSize: "0.68rem" }}>
            {t("benefits.loading")}
          </span>
        )}
      </p>

      <div style={{ marginTop: "8px" }}>
        <label
          htmlFor="benefit-project-cost"
          style={{ display: "block", fontSize: "0.7rem", color: "var(--text-secondary)" }}
        >
          {t("benefits.costLabel")}
        </label>
        <input
          id="benefit-project-cost"
          type="text"
          inputMode="numeric"
          value={cost}
          onChange={(e) => setCost(e.target.value)}
          placeholder={t("benefits.costHint")}
          style={{
            marginTop: "4px",
            width: "100%",
            maxWidth: "260px",
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            borderRadius: "10px",
            padding: "7px 10px",
            fontSize: "0.78rem",
            color: "var(--text-primary)",
            fontFamily: "inherit",
          }}
        />
      </div>

      {(subsidyMax !== null || loanAccess > 0) && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "10px" }}>
          {subsidyMax !== null && (
            <span style={chipStyle("var(--success)")}>
              {t("benefits.subsidy")}: {inr(subsidyMin)} – {inr(subsidyMax)}
            </span>
          )}
          {loanAccess > 0 && (
            <span style={chipStyle("var(--accent)")}>
              {t("benefits.credit")}: {inr(loanAccess)}
            </span>
          )}
        </div>
      )}

      {result && rows.length === 0 && (
        <p style={{ margin: "10px 0 0", fontSize: "0.72rem", color: "var(--text-muted)" }}>
          {t("benefits.none")}
        </p>
      )}

      <div style={{ marginTop: "10px", display: "grid", gap: "8px" }}>
        {visible.map((row) => (
          <div
            key={row.scheme_id}
            style={{
              padding: "9px 10px",
              borderRadius: "9px",
              background: "rgba(0,0,0,0.14)",
              border: "1px solid var(--border)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-primary)" }}>
                {row.scheme_name}
              </span>
              <span
                style={{
                  fontSize: "0.62rem",
                  fontWeight: 600,
                  color: row.status === "blocked" ? "var(--text-muted)" : "var(--success)",
                  textTransform: "uppercase",
                  letterSpacing: "0.03em",
                }}
              >
                {row.status_label}
              </span>
              {row.subsidy_max !== null && (
                <span style={{ fontSize: "0.68rem", color: "var(--success)" }}>
                  {inr(row.subsidy_min)} – {inr(row.subsidy_max)}
                </span>
              )}
              {row.subsidy_max === null && row.loan_max ? (
                <span style={{ fontSize: "0.68rem", color: "var(--text-secondary)" }}>
                  {row.loan_min ? `${inr(row.loan_min)} – ` : "≤ "}
                  {inr(row.loan_max)}
                </span>
              ) : null}
            </div>
            <ul style={{ margin: "6px 0 0", paddingLeft: "16px", display: "grid", gap: "3px" }}>
              {row.lines.slice(0, 6).map((line, index) => (
                <li key={index} style={{ fontSize: "0.7rem", color: "var(--text-secondary)", lineHeight: 1.45 }}>
                  {line}
                </li>
              ))}
            </ul>
            {row.source_url && (
              <a
                href={row.source_url}
                target="_blank"
                rel="noreferrer"
                style={{
                  marginTop: "5px",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                  fontSize: "0.64rem",
                  color: "var(--text-muted)",
                }}
              >
                <ExternalLink size={10} />
                {t("benefits.source")}
                {row.last_verified_at ? ` · ${row.last_verified_at}` : ""}
              </a>
            )}
          </div>
        ))}
      </div>

      {rows.length > 3 && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          aria-expanded={showAll}
          style={{
            marginTop: "8px",
            display: "inline-flex",
            alignItems: "center",
            gap: "5px",
            background: "transparent",
            border: "none",
            padding: 0,
            cursor: "pointer",
            color: "var(--accent)",
            fontSize: "0.7rem",
            fontFamily: "inherit",
          }}
        >
          <ChevronDown size={12} style={{ transform: showAll ? "rotate(180deg)" : "none" }} />
          {showAll ? t("benefits.showLess") : t("benefits.showAll", { count: rows.length })}
        </button>
      )}

      {result?.disclaimer && (
        <p
          style={{
            margin: "10px 0 0",
            fontSize: "0.66rem",
            color: "var(--text-muted)",
            lineHeight: 1.5,
            display: "flex",
            gap: "5px",
          }}
        >
          <Info size={12} style={{ flexShrink: 0, marginTop: "2px" }} />
          <span>
            <strong>{t("benefits.disclaimerLabel")}: </strong>
            {result.disclaimer}
          </span>
        </p>
      )}
    </motion.section>
  );
}

function chipStyle(color: string): CSSProperties {
  return {
    fontSize: "0.7rem",
    fontWeight: 600,
    color,
    background: "rgba(255,255,255,0.04)",
    border: "1px solid var(--border)",
    borderRadius: "999px",
    padding: "3px 9px",
  };
}
