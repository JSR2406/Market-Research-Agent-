"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  BadgeCheck,
  Ban,
  ChevronDown,
  CircleSlash,
  FileWarning,
  Gavel,
  Layers,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";

export type EligibilityReason = {
  label: string;
  basis: string;
  severity: string;
  action?: string;
};

export type EligibilityTier = {
  scheme_id: string;
  name: string;
  status: string;
  status_label: string;
  min_amount: number | null;
  max_amount: number | null;
  loan_ceiling: string;
};

export type EligibilityFamily = {
  family: string;
  name: string;
  status: string;
  status_label: string;
  reasons: EligibilityReason[];
  documents: string[];
  collateral_requirement: string;
  apply_via: string;
  source_url: string;
  last_verified_at: string;
  recommended_scheme_id: string;
  recommended_name: string;
  tiers: EligibilityTier[];
};

type Tone = { color: string; bg: string; Icon: typeof BadgeCheck };

const TONES: Record<string, Tone> = {
  eligible: { color: "var(--success)", bg: "rgba(37,211,102,0.14)", Icon: BadgeCheck },
  likely: { color: "var(--accent)", bg: "rgba(79,142,247,0.14)", Icon: BadgeCheck },
  wrong_tier: { color: "var(--warn)", bg: "rgba(251,146,60,0.14)", Icon: Layers },
  blocked: { color: "var(--warn)", bg: "rgba(251,146,60,0.14)", Icon: FileWarning },
  not_eligible: { color: "var(--text-muted)", bg: "rgba(255,255,255,0.06)", Icon: CircleSlash },
};

/** Status labels are translated; the backend's English label is the fallback. */
function statusLabel(t: (k: string) => string, status: string, fallback: string): string {
  const key = `elig.status.${status}`;
  const label = t(key);
  return label === key ? fallback || label : label;
}

function money(value: number | null | undefined): string {
  if (value == null) return "";
  if (value >= 10_000_000) return `₹${(value / 10_000_000).toFixed(value % 10_000_000 === 0 ? 0 : 2)} crore`;
  if (value >= 100_000) return `₹${(value / 100_000).toFixed(value % 100_000 === 0 ? 0 : 1)} lakh`;
  return `₹${value.toLocaleString("en-IN")}`;
}

function band(min: number | null, max: number | null): string {
  if (min == null && max == null) return "No published ceiling";
  if (min == null) return `Up to ${money(max)}`;
  if (max == null) return `From ${money(min)}`;
  return `${money(min)} – ${money(max)}`;
}

export default function EligibilityPanel({
  families,
  businessLabel,
  amount,
}: {
  families: EligibilityFamily[];
  businessLabel?: string;
  amount?: number | null;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const { t } = useI18n();

  if (!families?.length) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      aria-label="Scheme eligibility verdicts"
      style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        padding: "clamp(14px, 4vw, 20px)",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
        <Gavel size={15} color="var(--accent)" />
        <h3 style={{ margin: 0, fontSize: "0.92rem", fontWeight: 700, color: "var(--text-primary)" }}>
          What you can actually apply for
        </h3>
        {businessLabel && (
          <span
            style={{
              fontSize: "0.66rem",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: "var(--accent)",
              background: "rgba(79,142,247,0.12)",
              padding: "3px 8px",
              borderRadius: "8px",
            }}
          >
            {t("elig.yourBusiness", { label: businessLabel })}
          </span>
        )}
        {amount ? (
          <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontWeight: 600 }}>
            {t("elig.asking", { amount: money(amount) })}
          </span>
        ) : null}
      </div>

      <p style={{ margin: 0, fontSize: "0.72rem", color: "var(--text-muted)" }}>
        {t("elig.subtitle")}
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {families.map((card) => {
          const tone = TONES[card.status] ?? TONES.likely;
          const { Icon } = tone;
          const isOpen = !!open[card.family];
          const reasons = (card.reasons ?? []).filter(
            (r) => r.severity === "disqualifying" || r.severity === "blocking"
          );

          return (
            <div
              key={card.family}
              style={{
                border: "1px solid var(--border)",
                borderRadius: "12px",
                background: "var(--bg-surface)",
                overflow: "hidden",
              }}
            >
              <button
                type="button"
                onClick={() => setOpen((o) => ({ ...o, [card.family]: !o[card.family] }))}
                aria-expanded={isOpen}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  width: "100%",
                  padding: "11px 13px",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                  fontFamily: "inherit",
                }}
              >
                <span
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "5px",
                    padding: "3px 9px",
                    borderRadius: "999px",
                    fontSize: "0.66rem",
                    fontWeight: 800,
                    color: tone.color,
                    background: tone.bg,
                    whiteSpace: "nowrap",
                    flexShrink: 0,
                  }}
                >
                  <Icon size={11} />
                  {statusLabel(t, card.status, card.status_label)}
                </span>
                <span
                  style={{
                    flex: 1,
                    fontSize: "0.85rem",
                    fontWeight: 700,
                    color:
                      card.status === "not_eligible" ? "var(--text-muted)" : "var(--text-primary)",
                  }}
                >
                  {card.name}
                </span>
                <motion.span
                  animate={{ rotate: isOpen ? 180 : 0 }}
                  style={{ display: "flex", color: "var(--text-muted)", flexShrink: 0 }}
                >
                  <ChevronDown size={15} />
                </motion.span>
              </button>

              {/* One line of consequence, always visible — this is the part that changes behaviour */}
              {card.status === "not_eligible" && reasons[0] ? (
                <p
                  style={{
                    margin: 0,
                    padding: "0 13px 10px",
                    fontSize: "0.74rem",
                    color: "var(--text-muted)",
                  }}
                >
                  {reasons[0].label}
                </p>
              ) : null}
              {card.status === "blocked" && reasons[0] ? (
                <p
                  style={{
                    margin: 0,
                    padding: "0 13px 10px",
                    fontSize: "0.74rem",
                    color: "var(--warn)",
                  }}
                >
                  {reasons[0].action ?? reasons[0].label}
                </p>
              ) : null}
              {card.recommended_name && card.status !== "not_eligible" ? (
                <p
                  style={{
                    margin: 0,
                    padding: "0 13px 10px",
                    fontSize: "0.74rem",
                    color: "var(--accent)",
                    fontWeight: 600,
                  }}
                >
                  {t("elig.use", { name: card.recommended_name.split("(")[0].trim() })}
                </p>
              ) : null}

              {isOpen && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  style={{ padding: "0 13px 13px", display: "flex", flexDirection: "column", gap: "10px" }}
                >
                  {reasons.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
                      {reasons.map((reason, i) => (
                        <div
                          key={i}
                          style={{
                            padding: "8px 10px",
                            borderRadius: "8px",
                            background: "rgba(255,255,255,0.04)",
                            borderLeft: `2px solid ${tone.color}`,
                          }}
                        >
                          <p style={{ margin: 0, fontSize: "0.78rem", fontWeight: 600, color: "var(--text-primary)" }}>
                            {reason.label}
                          </p>
                          {reason.basis ? (
                            <p style={{ margin: "3px 0 0", fontSize: "0.66rem", color: "var(--text-muted)" }}>
                              {t("elig.tapRule", { rule: reason.basis })}
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}

                  {card.tiers?.length > 1 ? (
                    <div>
                      <p style={{ margin: "0 0 5px", fontSize: "0.68rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                        {t("elig.tiers")}
                      </p>
                      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                        {card.tiers.map((tier) => {
                          const isRec = tier.scheme_id === card.recommended_scheme_id;
                          return (
                            <div
                              key={tier.scheme_id}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "8px",
                                padding: "6px 9px",
                                borderRadius: "8px",
                                background: isRec ? "rgba(79,142,247,0.12)" : "rgba(255,255,255,0.03)",
                                fontSize: "0.72rem",
                              }}
                            >
                              {isRec ? <BadgeCheck size={12} color="var(--accent)" /> : <Ban size={12} color="var(--text-muted)" />}
                              <span style={{ fontWeight: 600, color: "var(--text-secondary)" }}>
                                {tier.name.split("(")[0].split("-").pop()?.trim() || tier.name}
                              </span>
                              <span style={{ marginLeft: "auto", color: "var(--text-muted)" }}>
                                {band(tier.min_amount, tier.max_amount)}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}

                  {card.documents?.length > 0 ? (
                    <div>
                      <p style={{ margin: "0 0 5px", fontSize: "0.68rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                        {t("elig.documents")}
                      </p>
                      <ul style={{ margin: 0, paddingLeft: "16px", display: "flex", flexDirection: "column", gap: "3px" }}>
                        {card.documents.map((doc, i) => (
                          <li key={i} style={{ fontSize: "0.74rem", color: "var(--text-secondary)" }}>
                            {doc}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {card.collateral_requirement ? (
                    <p style={{ margin: 0, fontSize: "0.72rem", color: "var(--text-secondary)" }}>
                      <span style={{ color: "var(--text-muted)" }}>{t("elig.collateral")} </span>
                      {card.collateral_requirement}
                    </p>
                  ) : null}

                  {card.source_url ? (
                    <a
                      href={card.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ fontSize: "0.68rem", color: "var(--accent)", textDecoration: "underline" }}
                    >
                      {t("elig.source")}
                      {card.last_verified_at
                        ? ` · ${t("elig.verified", { date: card.last_verified_at })}`
                        : ""}
                    </a>
                  ) : null}
                </motion.div>
              )}
            </div>
          );
        })}
      </div>
    </motion.section>
  );
}