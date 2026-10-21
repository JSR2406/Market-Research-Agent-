"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import { BadgeCheck, Ban, Clock3, ExternalLink, ListChecks, ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export type GateScheme = {
  name: string;
  status: string;
  source_url: string;
  last_verified_at: string;
};

export type GatePayload = {
  gate_id: string;
  kind: string;
  status: string;
  question: string;
  detail: string;
  options?: Array<{ value: string; label: string }>;
  steps: string[];
  schemes: GateScheme[];
};

type Props = {
  gate: GatePayload;
  /** Send the user's decision. The card does not decide anything itself. */
  onDecide: (decision: "approve" | "reject", note: string) => void;
  /** A decision is in flight — the buttons are locked until the server answers. */
  busy?: boolean;
  /** The run parked without an answer: the gate can still be decided later. */
  parked?: boolean;
};

const STATUS_TONE: Record<string, { color: string; bg: string }> = {
  pending: { color: "var(--warn)", bg: "rgba(251,146,60,0.14)" },
  approved: { color: "var(--success)", bg: "rgba(37,211,102,0.14)" },
  rejected: { color: "var(--text-muted)", bg: "rgba(255,255,255,0.06)" },
};

export default function GateCard({ gate, onDecide, busy, parked }: Props) {
  const { t } = useI18n();
  const [note, setNote] = useState("");

  const tone = STATUS_TONE[gate.status] ?? STATUS_TONE.pending;
  const isPending = gate.status === "pending";

  // The backend sends the button labels in the user's language; the UI copy is
  // the fallback for an older server that does not.
  const optionLabel = (value: string, fallbackKey: string): string => {
    const match = (gate.options ?? []).find((o) => o.value === value);
    if (match?.label) return match.label;
    const translated = t(fallbackKey);
    return translated === fallbackKey ? fallbackKey : translated;
  };

  const badgeText =
    gate.status === "approved"
      ? t("gate.approved")
      : gate.status === "rejected"
        ? t("gate.rejected")
        : t("gate.waiting");

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      aria-label={t("gate.title")}
      style={{
        background: "rgba(251,146,60,0.05)",
        border: `1px solid ${isPending ? "rgba(251,146,60,0.32)" : "var(--border)"}`,
        borderRadius: "var(--radius-lg)",
        padding: "clamp(14px, 4vw, 20px)",
        display: "flex",
        flexDirection: "column",
        gap: "14px",
      }}
    >
      {/* Header — who is asking and why */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
        {isPending ? (
          <ShieldCheck size={16} color={tone.color} />
        ) : gate.status === "approved" ? (
          <BadgeCheck size={16} color={tone.color} />
        ) : (
          <Ban size={16} color={tone.color} />
        )}
        <h3 style={{ margin: 0, fontSize: "0.92rem", fontWeight: 700, color: "var(--text-primary)" }}>
          {t("gate.title")}
        </h3>
        <span
          style={{
            fontSize: "0.66rem",
            fontWeight: 800,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: tone.color,
            background: tone.bg,
            padding: "3px 9px",
            borderRadius: "999px",
            display: "inline-flex",
            alignItems: "center",
            gap: "5px",
          }}
        >
          {isPending ? <Clock3 size={11} /> : null}
          {badgeText}
        </span>
      </div>

      {/* The question the agent may not answer on the user's behalf */}
      <div>
        <p style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)" }}>
          {gate.question}
        </p>
        {gate.detail ? (
          <p style={{ margin: "6px 0 0", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
            {gate.detail}
          </p>
        ) : null}
      </div>

      {/* The plan — what will happen once you say yes */}
      {gate.steps?.length ? (
        <div>
          <p
            style={{
              margin: "0 0 6px",
              fontSize: "0.68rem",
              fontWeight: 700,
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <ListChecks size={12} /> {t("gate.stepsLabel")}
          </p>
          <ol style={{ margin: 0, paddingLeft: "18px", display: "flex", flexDirection: "column", gap: "4px" }}>
            {gate.steps.map((step, i) => (
              <li key={i} style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                {step}
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {/* The schemes — every one carries its official source */}
      {gate.schemes?.length ? (
        <div>
          <p
            style={{
              margin: "0 0 6px",
              fontSize: "0.68rem",
              fontWeight: 700,
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            {t("gate.schemesLabel")}
          </p>
          <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: "5px" }}>
            {gate.schemes.map((scheme, i) => (
              <li
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  flexWrap: "wrap",
                  padding: "7px 10px",
                  borderRadius: "8px",
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border)",
                  fontSize: "0.76rem",
                }}
              >
                <span style={{ fontWeight: 700, color: "var(--text-primary)" }}>{scheme.name}</span>
                {scheme.status ? (
                  <span style={{ color: "var(--text-muted)" }}>{scheme.status}</span>
                ) : null}
                {scheme.source_url ? (
                  <a
                    href={scheme.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      marginLeft: "auto",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "4px",
                      fontSize: "0.68rem",
                      color: "var(--accent)",
                      textDecoration: "underline",
                    }}
                  >
                    {t("gate.source")}
                    {scheme.last_verified_at ? ` · ${t("gate.verified")} ${scheme.last_verified_at}` : ""}
                    <ExternalLink size={10} />
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* The decision */}
      {isPending ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {parked ? (
            <p style={{ margin: 0, fontSize: "0.76rem", color: "var(--warn)" }}>{t("gate.parked")}</p>
          ) : null}

          <label
            htmlFor="gate-note"
            style={{ fontSize: "0.7rem", fontWeight: 700, color: "var(--text-muted)" }}
          >
            {t("gate.note")}
          </label>
          <textarea
            id="gate-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={t("gate.notePlaceholder")}
            rows={2}
            maxLength={500}
            style={{
              width: "100%",
              resize: "vertical",
              padding: "9px 11px",
              borderRadius: "10px",
              border: "1px solid var(--border)",
              background: "var(--bg-surface)",
              color: "var(--text-primary)",
              fontFamily: "inherit",
              fontSize: "0.82rem",
            }}
          />

          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            <motion.button
              type="button"
              whileTap={{ scale: 0.97 }}
              disabled={busy}
              onClick={() => onDecide("approve", note)}
              style={{
                flex: "1 1 150px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "7px",
                padding: "11px 18px",
                borderRadius: "var(--radius-md)",
                border: "1px solid transparent",
                background: busy ? "var(--bg-surface)" : "linear-gradient(135deg, var(--accent), var(--accent2))",
                color: busy ? "var(--text-muted)" : "#fff",
                fontSize: "0.86rem",
                fontWeight: 700,
                cursor: busy ? "wait" : "pointer",
              }}
            >
              <BadgeCheck size={15} /> {optionLabel("approve", "gate.approve")}
            </motion.button>
            <motion.button
              type="button"
              whileTap={{ scale: 0.97 }}
              disabled={busy}
              onClick={() => onDecide("reject", note)}
              style={{
                flex: "1 1 150px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "7px",
                padding: "11px 18px",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--border-bright)",
                background: "transparent",
                color: "var(--text-secondary)",
                fontSize: "0.86rem",
                fontWeight: 700,
                cursor: busy ? "wait" : "pointer",
              }}
            >
              <Ban size={15} /> {optionLabel("reject", "gate.reject")}
            </motion.button>
          </div>
        </div>
      ) : null}
    </motion.section>
  );
}
