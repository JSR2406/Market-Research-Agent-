"use client";

import { useEffect, useState } from "react";
import { BarChart3 } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { analyticsAllowed, setOptOut } from "@/lib/analytics";

/**
 * One-click opt-out for the anonymous usage counts.
 *
 * The switch reflects the *effective* state: a browser sending Do-Not-Track is
 * already "off" even though the stored preference is untouched, so the control
 * reports what is actually happening rather than what was last clicked.
 */
export default function AnalyticsToggle() {
  const { t } = useI18n();
  const [enabled, setEnabled] = useState(true);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setEnabled(analyticsAllowed());
    setMounted(true);
  }, []);

  const toggle = () => {
    const next = !enabled;
    // Turning off stores the preference; turning on clears it.
    setOptOut(!next);
    setEnabled(next);
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
      <BarChart3 size={14} aria-hidden="true" style={{ color: "var(--text-muted)", flexShrink: 0 }} />
      <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{t("footer.analytics")}</span>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label={t("footer.analyticsToggle")}
        onClick={toggle}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
          padding: "3px 9px",
          borderRadius: "999px",
          border: "1px solid var(--border)",
          background: enabled ? "var(--accent-glow)" : "transparent",
          color: enabled ? "var(--accent)" : "var(--text-muted)",
          fontSize: "0.72rem",
          fontWeight: 700,
          cursor: "pointer",
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "999px",
            background: enabled ? "var(--accent)" : "var(--text-muted)",
          }}
        />
        {mounted ? (enabled ? t("footer.analyticsOn") : t("footer.analyticsOff")) : t("footer.analyticsOff")}
      </button>
      <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", flexBasis: "100%" }}>
        {t("footer.analyticsNote")}
      </span>
    </div>
  );
}
