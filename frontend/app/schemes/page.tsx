"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  FileText,
  ExternalLink,
  ShieldCheck,
  BadgeIndianRupee,
  Percent,
  ChevronDown,
  AlertTriangle,
  Sparkles,
} from "lucide-react";
import { SiteHeader } from "@/components/SiteHeader";
import { API_BASE } from "@/lib/api";
import { track } from "@/lib/analytics";
import { useI18n } from "@/lib/i18n";

type SchemeCheck = {
  id: string;
  type?: string;
  severity?: string;
  label: string;
  label_hi?: string;
  basis?: string;
};

type Scheme = {
  id: string;
  scheme_name: string;
  benefit_type?: string;
  target_segment?: string;
  loan_ceiling?: string;
  amount_band_note?: string;
  checks?: SchemeCheck[];
  tier_group?: string;
  collateral_requirement?: string;
  nodal_agency?: string;
  one_line_eligibility?: string;
  eligibility_rules?: string[];
  exclusions?: string[];
  documents?: string[];
  interest_rate?: string;
  source_url?: string;
  last_verified_at?: string;
  apply_via?: string;
};

type SchemeType = "loan" | "subsidy" | "guarantee" | "other";

/**
 * The dataset has no explicit "type" field, so the card badge is derived with
 * fixed rules from the data we do have (never guessed per-render).
 */
function schemeType(s: Scheme): SchemeType {
  const group = (s.tier_group || "").toLowerCase();
  if (group.includes("cgtmse")) return "guarantee";
  if (group.includes("pmegp")) return "subsidy";
  if (group.includes("mudra") || group.includes("svanidhi")) return "loan";
  const benefit = (s.benefit_type || "").toLowerCase();
  if (benefit.includes("guarantee")) return "guarantee";
  if (benefit.includes("subsid")) return "subsidy";
  if (benefit.includes("loan")) return "loan";
  return "other";
}

const TYPE_STYLES: Record<SchemeType, { color: string; bg: string }> = {
  loan: { color: "var(--accent)", bg: "var(--accent-glow)" },
  subsidy: { color: "var(--success)", bg: "rgba(34,211,165,0.12)" },
  guarantee: { color: "var(--warn)", bg: "rgba(251,146,60,0.12)" },
  other: { color: "var(--text-secondary)", bg: "rgba(255,255,255,0.06)" },
};

const FILTERS: { key: "all" | SchemeType; labelKey: string }[] = [
  { key: "all", labelKey: "schemes.filter.all" },
  { key: "loan", labelKey: "schemes.filter.loans" },
  { key: "subsidy", labelKey: "schemes.filter.subsidies" },
  { key: "guarantee", labelKey: "schemes.filter.guarantees" },
];

export default function SchemesPage() {
  const { t, locale } = useI18n();
  const [schemes, setSchemes] = useState<Scheme[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | SchemeType>("all");
  const [openId, setOpenId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setFailed(false);
    try {
      const res = await fetch(`${API_BASE}/api/schemes`);
      if (!res.ok) throw new Error("bad status");
      const body = await res.json();
      setSchemes(Array.isArray(body?.schemes) ? body.schemes : []);
    } catch {
      setFailed(true);
      setSchemes([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return schemes.filter((s) => {
      if (filter !== "all" && schemeType(s) !== filter) return false;
      if (!q) return true;
      const haystack = [
        s.scheme_name,
        s.benefit_type,
        s.target_segment,
        s.one_line_eligibility,
        s.nodal_agency,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [schemes, query, filter]);

  const checkLabel = (c: SchemeCheck) => (locale === "hi" && c.label_hi ? c.label_hi : c.label);

  return (
    <>
      <SiteHeader />
      <main className="page-shell" style={{ maxWidth: "1080px", marginInline: "auto" }}>
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          style={{ textAlign: "center", marginBottom: "24px" }}
        >
          <h1 style={{ fontSize: "clamp(1.4rem, 4.5vw, 2rem)", fontWeight: 800, marginBottom: "8px" }}>
            {t("schemes.title")}
          </h1>
          <p style={{ color: "var(--text-secondary)", maxWidth: "640px", marginInline: "auto" }}>
            {t("schemes.subtitle")}
          </p>
        </motion.div>

        {/* Search + filters */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "12px",
            marginBottom: "22px",
          }}
        >
          <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
            <Search
              size={17}
              color="var(--text-muted)"
              aria-hidden="true"
              style={{ position: "absolute", left: "14px" }}
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("schemes.searchPlaceholder")}
              aria-label={t("schemes.searchAria")}
              style={{
                width: "100%",
                padding: "12px 14px 12px 40px",
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-md)",
                color: "var(--text-primary)",
                fontSize: "0.9rem",
                fontFamily: "inherit",
              }}
            />
          </div>

          <div
            role="group"
            aria-label={t("schemes.filterAria")}
            style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}
          >
            {FILTERS.map((f) => {
              const active = filter === f.key;
              return (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setFilter(f.key)}
                  aria-pressed={active}
                  style={{
                    padding: "7px 16px",
                    borderRadius: "999px",
                    border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                    background: active ? "var(--accent-glow)" : "transparent",
                    color: active ? "var(--accent)" : "var(--text-secondary)",
                    fontSize: "0.82rem",
                    fontWeight: 600,
                    cursor: "pointer",
                    fontFamily: "inherit",
                  }}
                >
                  {t(f.labelKey)}
                </button>
              );
            })}
          </div>
        </div>

        {/* States */}
        {loading && (
          <p style={{ color: "var(--text-muted)", textAlign: "center", padding: "40px 0" }}>
            <FileText size={16} aria-hidden="true" /> …
          </p>
        )}

        {!loading && failed && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "12px",
              padding: "36px 20px",
              background: "rgba(248,113,113,0.06)",
              border: "1px solid rgba(248,113,113,0.25)",
              borderRadius: "var(--radius-lg)",
            }}
          >
            <AlertTriangle size={22} color="var(--error)" aria-hidden="true" />
            <p style={{ color: "var(--error)", fontWeight: 600 }}>{t("schemes.errorTitle")}</p>
            <button
              type="button"
              onClick={load}
              style={{
                padding: "9px 20px",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--border-bright)",
                background: "transparent",
                color: "var(--text-primary)",
                fontWeight: 600,
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              {t("schemes.retry")}
            </button>
          </div>
        )}

        {!loading && !failed && visible.length === 0 && (
          <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--text-muted)" }}>
            <p style={{ fontWeight: 600, color: "var(--text-secondary)" }}>{t("schemes.noResults")}</p>
            <p style={{ fontSize: "0.84rem" }}>{t("schemes.noResultsDesc")}</p>
          </div>
        )}

        {/* Cards */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))",
            gap: "14px",
          }}
        >
          {visible.map((s, i) => {
            const type = schemeType(s);
            const badge = TYPE_STYLES[type];
            const expanded = openId === s.id;
            return (
              <motion.article
                key={s.id}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.2 }}
                transition={{ duration: 0.35, delay: Math.min(i * 0.04, 0.3) }}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  padding: "20px",
                  background: "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-lg)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px" }}>
                  <span
                    style={{
                      padding: "3px 10px",
                      borderRadius: "999px",
                      background: badge.bg,
                      color: badge.color,
                      fontSize: "0.68rem",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {t(`schemes.type.${type}`)}
                  </span>
                  {s.last_verified_at && (
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "4px",
                        fontSize: "0.68rem",
                        color: "var(--text-muted)",
                      }}
                    >
                      <ShieldCheck size={12} aria-hidden="true" />
                      {t("schemes.verified")} {s.last_verified_at}
                    </span>
                  )}
                </div>

                <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "6px", lineHeight: 1.35 }}>
                  {s.scheme_name}
                </h2>
                {s.benefit_type && (
                  <p style={{ fontSize: "0.84rem", color: "var(--text-secondary)", marginBottom: "12px" }}>
                    {s.benefit_type}
                  </p>
                )}

                <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "12px" }}>
                  {s.loan_ceiling && (
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "8px", fontSize: "0.82rem" }}>
                      <BadgeIndianRupee size={15} color="var(--accent)" aria-hidden="true" style={{ marginTop: "2px", flexShrink: 0 }} />
                      <span style={{ color: "var(--text-secondary)" }}>
                        <strong style={{ color: "var(--text-primary)" }}>{t("schemes.maxAmount")}:</strong>{" "}
                        {s.loan_ceiling}
                      </span>
                    </div>
                  )}
                  {s.interest_rate && (
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "8px", fontSize: "0.82rem" }}>
                      <Percent size={15} color="var(--accent)" aria-hidden="true" style={{ marginTop: "2px", flexShrink: 0 }} />
                      <span style={{ color: "var(--text-secondary)" }}>
                        <strong style={{ color: "var(--text-primary)" }}>{t("schemes.interestRate")}:</strong>{" "}
                        {s.interest_rate}
                      </span>
                    </div>
                  )}
                </div>

                {s.one_line_eligibility && (
                  <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "12px" }}>
                    {s.one_line_eligibility}
                  </p>
                )}

                <button
                  type="button"
                  onClick={() => {
                    const next = !expanded;
                    setOpenId(next ? s.id : null);
                    if (next) track("scheme_view", { page: s.id });
                  }}
                  aria-expanded={expanded}
                  aria-controls={`scheme-details-${s.id}`}
                  style={{
                    marginTop: "auto",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",
                    padding: "9px 14px",
                    borderRadius: "var(--radius-md)",
                    border: "1px solid var(--border-bright)",
                    background: "transparent",
                    color: "var(--text-primary)",
                    fontSize: "0.82rem",
                    fontWeight: 600,
                    cursor: "pointer",
                    fontFamily: "inherit",
                  }}
                >
                  {expanded ? t("schemes.showLess") : t("schemes.seeDetails")}
                  <ChevronDown
                    size={15}
                    aria-hidden="true"
                    style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}
                  />
                </button>

                <AnimatePresence initial={false}>
                  {expanded && (
                    <motion.div
                      id={`scheme-details-${s.id}`}
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.22 }}
                      style={{ overflow: "hidden" }}
                    >
                      <div style={{ paddingTop: "14px", display: "flex", flexDirection: "column", gap: "12px" }}>
                        {!!s.eligibility_rules?.length && (
                          <Detail title={t("schemes.eligibility")}>
                            <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "5px" }}>
                              {s.eligibility_rules.map((r) => (
                                <li key={r} style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                                  • {r}
                                </li>
                              ))}
                            </ul>
                          </Detail>
                        )}
                        {!!s.documents?.length && (
                          <Detail title={t("schemes.documents")}>
                            <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "5px" }}>
                              {s.documents.map((d) => (
                                <li key={d} style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                                  • {d}
                                </li>
                              ))}
                            </ul>
                          </Detail>
                        )}
                        {!!s.exclusions?.length && (
                          <Detail title={t("schemes.excluded")}>
                            <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "5px" }}>
                              {s.exclusions.map((e) => (
                                <li key={e} style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                                  • {e}
                                </li>
                              ))}
                            </ul>
                          </Detail>
                        )}
                        {!!s.checks?.length && (
                          <Detail title={t("schemes.eligibleFor")}>
                            <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "5px" }}>
                              {s.checks.map((c) => (
                                <li key={c.id} style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                                  • {checkLabel(c)}
                                </li>
                              ))}
                            </ul>
                          </Detail>
                        )}
                        {s.source_url && (
                          <a
                            href={s.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "6px",
                              fontSize: "0.8rem",
                              color: "var(--accent)",
                              textDecoration: "none",
                              wordBreak: "break-all",
                            }}
                          >
                            <ExternalLink size={13} aria-hidden="true" />
                            {t("schemes.source")}
                          </a>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.article>
            );
          })}
        </div>

        {/* Personalised-match CTA */}
        <div
          style={{
            marginTop: "32px",
            marginBottom: "40px",
            padding: "24px clamp(16px, 4vw, 28px)",
            textAlign: "center",
            background: "linear-gradient(135deg, rgba(79,142,247,0.12), rgba(155,135,245,0.08))",
            border: "1px solid var(--border-bright)",
            borderRadius: "var(--radius-xl)",
          }}
        >
          <Sparkles size={22} color="var(--accent)" aria-hidden="true" />
          <h2 style={{ fontSize: "1.15rem", fontWeight: 800, margin: "10px 0 6px" }}>
            {t("schemes.cta.title")}
          </h2>
          <p style={{ color: "var(--text-secondary)", marginBottom: "18px" }}>{t("schemes.cta.desc")}</p>
          <Link
            href="/research"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "11px 24px",
              borderRadius: "var(--radius-md)",
              background: "linear-gradient(135deg, var(--accent), var(--accent-dim))",
              color: "#fff",
              textDecoration: "none",
              fontWeight: 700,
              fontSize: "0.9rem",
            }}
          >
            {t("schemes.cta.button")}
          </Link>
        </div>
      </main>
    </>
  );
}

function Detail({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3
        style={{
          fontSize: "0.72rem",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "var(--text-muted)",
          marginBottom: "6px",
        }}
      >
        {title}
      </h3>
      {children}
    </div>
  );
}
