"use client";
import { Languages } from "lucide-react";
import { LOCALES, useI18n } from "@/lib/i18n";

/**
 * Site-wide language control. Sits at the top of the page so it switches the
 * entire site — check-up, verdicts, ledger, report, chat — not just the chat.
 */
export default function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const { locale, setLocale, t } = useI18n();

  return (
    <div
      role="group"
      aria-label={t("misc.langAria")}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "6px",
        alignSelf: "center",
        padding: "5px 10px",
        background: "rgba(255,255,255,0.05)",
        border: "1px solid rgba(255,255,255,0.12)",
        borderRadius: "999px",
        marginBottom: compact ? 0 : "18px",
      }}
    >
      <Languages size={13} color="var(--text-muted)" aria-hidden="true" />
      {LOCALES.map((l) => {
        const active = l.code === locale;
        return (
          <button
            key={l.code}
            type="button"
            onClick={() => setLocale(l.code)}
            aria-pressed={active}
            lang={l.code}
            title={l.label}
            style={{
              border: "none",
              background: active ? "rgba(79,142,247,0.2)" : "transparent",
              color: active ? "var(--accent)" : "var(--text-muted)",
              fontSize: "0.72rem",
              fontWeight: 700,
              padding: "3px 10px",
              borderRadius: "999px",
              cursor: "pointer",
              fontFamily: "inherit",
              transition: "background 0.15s, color 0.15s",
            }}
          >
            {l.native}
          </button>
        );
      })}
    </div>
  );
}