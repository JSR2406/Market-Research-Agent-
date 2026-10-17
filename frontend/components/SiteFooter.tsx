"use client";

import Link from "next/link";
import { Handshake } from "lucide-react";
import AnalyticsToggle from "@/components/AnalyticsToggle";
import { useI18n } from "@/lib/i18n";

/**
 * Site-wide footer. Lives in the root layout so every route — including the
 * legal pages themselves — is reachable from anywhere, and so the privacy
 * promise ("7 days, export or delete") is visible without opening a menu.
 */
const LEGAL_LINKS = [
  { href: "/about", labelKey: "footer.about" },
  { href: "/privacy", labelKey: "footer.privacy" },
  { href: "/terms", labelKey: "footer.terms" },
  { href: "/disclaimer", labelKey: "footer.disclaimer" },
] as const;

export function SiteFooter() {
  const { t } = useI18n();

  return (
    <footer
      aria-label={t("footer.aria")}
      style={{
        marginTop: "auto",
        borderTop: "1px solid var(--border)",
        background: "rgba(13,13,16,0.6)",
      }}
    >
      <div
        style={{
          maxWidth: "1080px",
          marginInline: "auto",
          padding: "28px clamp(12px, 4vw, 20px)",
          display: "flex",
          flexWrap: "wrap",
          gap: "24px",
          justifyContent: "space-between",
        }}
      >
        <div style={{ flex: "1 1 260px", minWidth: 0 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "9px",
              marginBottom: "10px",
              color: "var(--text-primary)",
              fontWeight: 700,
              fontSize: "0.92rem",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: "26px",
                height: "26px",
                borderRadius: "8px",
                background: "linear-gradient(135deg, var(--accent), #9b87f5)",
              }}
            >
              <Handshake size={15} color="#fff" />
            </span>
            {t("brand.name")}
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.82rem", lineHeight: 1.6, margin: 0, maxWidth: "360px" }}>
            {t("footer.tagline")}
          </p>
        </div>

        <nav aria-label={t("footer.trust")} style={{ flex: "0 1 auto" }}>
          <h2 style={{ fontSize: "0.78rem", fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-muted)", margin: "0 0 10px" }}>
            {t("footer.trust")}
          </h2>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "8px" }}>
            {LEGAL_LINKS.map(({ href, labelKey }) => (
              <li key={href}>
                <Link
                  href={href}
                  style={{ color: "var(--text-secondary)", textDecoration: "none", fontSize: "0.84rem" }}
                >
                  {t(labelKey)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div style={{ flex: "1 1 240px", minWidth: 0 }}>
          <h2 style={{ fontSize: "0.78rem", fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-muted)", margin: "0 0 10px" }}>
            {t("footer.privacy")}
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.82rem", lineHeight: 1.6, margin: "0 0 8px" }}>
            {t("footer.dataNote")}
          </p>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", lineHeight: 1.6, margin: 0 }}>
            {t("footer.rights")}
          </p>
          <div style={{ marginTop: "14px" }}>
            <AnalyticsToggle />
          </div>
        </div>
      </div>

      <div
        style={{
          borderTop: "1px solid var(--border)",
          padding: "14px clamp(12px, 4vw, 20px)",
          textAlign: "center",
          color: "var(--text-muted)",
          fontSize: "0.78rem",
        }}
      >
        {/* The year is derived from the clock; suppressHydrationWarning keeps the
            server/client boundary from warning across a new year. */}
        <span suppressHydrationWarning>{t("footer.copyright", { year: new Date().getFullYear() })}</span>
      </div>
    </footer>
  );
}
