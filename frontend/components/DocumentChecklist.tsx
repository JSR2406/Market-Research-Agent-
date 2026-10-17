"use client";
/**
 * DocumentChecklist.tsx — the papers to keep ready, per matched scheme (WS-4).
 *
 * Grouped by who issues each paper (you / government / bank / CA) and split into
 * must-have vs if-you-have-it. Two exports:
 *   • Print / Save as PDF — scoped by a print stylesheet, so the printed page
 *     carries the scheme name, the date and the source link;
 *   • Copy for WhatsApp — the server-built plain-text list, ready to paste into
 *     the family group or send to a bank agent.
 */
import { useEffect, useState, type CSSProperties } from "react";
import { motion } from "framer-motion";
import { ChevronDown, ClipboardCopy, FileText, Printer } from "lucide-react";
import { API_BASE } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { IntakeAnswers } from "@/lib/intake";

type DocItem = { text: string; mandatory: boolean; tag: string };
type DocGroup = { issuer: string; label: string; items: DocItem[] };
type Checklist = {
  scheme_id: string;
  scheme_name: string;
  status?: string;
  status_label?: string;
  bank_led: boolean;
  routing_note: string;
  apply_via: string;
  groups: DocGroup[];
  source_url: string;
  last_verified_at: string;
  whatsapp_text: string;
};
type DocPlan = {
  generated_on: string;
  checklists: Checklist[];
  default_note: string;
  disclaimer: string;
};

export default function DocumentChecklist({ intake }: { intake: IntakeAnswers }) {
  const { t, locale } = useI18n();
  const [plan, setPlan] = useState<DocPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [copied, setCopied] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      (async () => {
        setLoading(true);
        try {
          const res = await fetch(`${API_BASE}/api/documents`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ intake, lang: locale }),
            signal: controller.signal,
          });
          if (!res.ok) return;
          setPlan(await res.json());
        } catch {
          /* offline — the check-up still works without the checklist */
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
  }, [JSON.stringify(intake), locale]);

  const copy = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(id);
      setTimeout(() => setCopied(""), 2000);
    } catch {
      /* clipboard blocked — the WhatsApp text is still selectable on screen */
    }
  };

  const checklists = plan?.checklists ?? [];
  const visible = showAll ? checklists : checklists.slice(0, 2);

  if (checklists.length === 0) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      aria-label={t("docs.title")}
      className="print-area"
      style={{
        marginTop: "12px",
        padding: "12px",
        borderRadius: "10px",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid var(--border)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
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
          <FileText size={13} />
          {t("docs.title")}
          {loading && (
            <span style={{ fontWeight: 500, color: "var(--text-muted)", fontSize: "0.68rem" }}>
              {t("docs.loading")}
            </span>
          )}
        </p>
        <button
          type="button"
          onClick={() => window.print()}
          style={actionStyle}
        >
          <Printer size={12} />
          {t("docs.print")}
        </button>
        {plan?.generated_on && (
          <span style={{ fontSize: "0.64rem", color: "var(--text-muted)" }}>
            {t("docs.generatedOn", { date: plan.generated_on })}
          </span>
        )}
      </div>

      <div style={{ marginTop: "10px", display: "grid", gap: "10px" }}>
        {visible.map((checklist) => (
          <div
            key={checklist.scheme_id}
            style={{
              padding: "9px 10px",
              borderRadius: "9px",
              background: "rgba(0,0,0,0.14)",
              border: "1px solid var(--border)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-primary)" }}>
                {checklist.scheme_name}
              </span>
              {checklist.status_label && (
                <span
                  style={{
                    fontSize: "0.62rem",
                    fontWeight: 600,
                    textTransform: "uppercase",
                    letterSpacing: "0.03em",
                    color: checklist.status === "blocked" ? "var(--text-muted)" : "var(--success)",
                  }}
                >
                  {checklist.status_label}
                </span>
              )}
              <button
                type="button"
                onClick={() => copy(checklist.whatsapp_text, checklist.scheme_id)}
                style={{ ...actionStyle, marginLeft: "auto" }}
              >
                <ClipboardCopy size={12} />
                {copied === checklist.scheme_id ? t("docs.copied") : t("docs.copyWhatsapp")}
              </button>
            </div>

            {checklist.groups.map((group) => (
              <div key={group.issuer} style={{ marginTop: "7px" }}>
                <p
                  style={{
                    margin: 0,
                    fontSize: "0.68rem",
                    fontWeight: 700,
                    color: "var(--accent)",
                  }}
                >
                  {group.label}
                </p>
                <ul style={{ margin: "3px 0 0", paddingLeft: "16px", display: "grid", gap: "3px" }}>
                  {group.items.map((item, index) => (
                    <li key={index} style={{ fontSize: "0.71rem", color: "var(--text-secondary)" }}>
                      {item.text}
                      <span
                        style={{
                          marginLeft: "6px",
                          fontSize: "0.6rem",
                          color: item.mandatory ? "var(--text-muted)" : "var(--warning, #d97706)",
                          border: "1px solid var(--border)",
                          borderRadius: "999px",
                          padding: "1px 6px",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {item.tag}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}

            <p style={{ margin: "7px 0 0", fontSize: "0.68rem", color: "var(--text-muted)" }}>
              {checklist.routing_note} {checklist.apply_via}
            </p>
          </div>
        ))}
      </div>

      {checklists.length > 2 && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          aria-expanded={showAll}
          style={{ ...actionStyle, marginTop: "8px" }}
        >
          <ChevronDown size={12} style={{ transform: showAll ? "rotate(180deg)" : "none" }} />
          {showAll ? t("benefits.showLess") : t("benefits.showAll", { count: checklists.length })}
        </button>
      )}

      {plan?.default_note && (
        <p style={{ margin: "8px 0 0", fontSize: "0.66rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
          {plan.default_note}
        </p>
      )}
      {plan?.disclaimer && (
        <p style={{ margin: "6px 0 0", fontSize: "0.66rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
          {plan.disclaimer}
        </p>
      )}
    </motion.section>
  );
}

const actionStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "5px",
  background: "transparent",
  border: "1px solid var(--border)",
  borderRadius: "999px",
  padding: "3px 9px",
  cursor: "pointer",
  color: "var(--accent)",
  fontSize: "0.68rem",
  fontFamily: "inherit",
};
