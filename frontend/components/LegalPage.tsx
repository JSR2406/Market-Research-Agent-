"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, ScrollText } from "lucide-react";
import { SiteHeader } from "@/components/SiteHeader";
import { useI18n } from "@/lib/i18n";

export type LegalSection = { titleKey: string; bodyKey: string };

type LegalPageProps = {
  titleKey: string;
  subtitleKey: string;
  updated: string;
  sections: LegalSection[];
};

/**
 * Shared shell for the trust pages (About / Privacy / Terms / Disclaimer).
 *
 * Every word comes from the i18n dictionaries — the page contains no hardcoded
 * user-facing copy, so switching to Hindi translates the whole document. The
 * content itself is data (`sections`), which keeps the four documents consistent
 * and makes adding a fifth a one-file change.
 */
export default function LegalPage({ titleKey, subtitleKey, updated, sections }: LegalPageProps) {
  const { t } = useI18n();

  return (
    <>
      <SiteHeader />
      <main className="page-shell" style={{ maxWidth: "760px", marginInline: "auto" }}>
        <Link
          href="/"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            color: "var(--text-secondary)",
            textDecoration: "none",
            fontSize: "0.84rem",
          }}
        >
          <ArrowLeft size={15} aria-hidden="true" />
          {t("legal.backHome")}
        </Link>

        <motion.header
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          style={{ margin: "18px 0 6px" }}
        >
          <div
            aria-hidden="true"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "48px",
              height: "48px",
              borderRadius: "999px",
              background: "var(--accent-glow)",
              marginBottom: "12px",
            }}
          >
            <ScrollText size={22} color="var(--accent)" />
          </div>
          <h1 style={{ fontSize: "clamp(1.4rem, 4.5vw, 2rem)", fontWeight: 800, marginBottom: "8px" }}>
            {t(titleKey)}
          </h1>
          <p style={{ color: "var(--text-secondary)", marginBottom: "6px" }}>{t(subtitleKey)}</p>
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", margin: 0 }}>
            {t("legal.updated", { date: updated })}
          </p>
        </motion.header>

        <div className="prose" style={{ marginTop: "10px", paddingBottom: "48px" }}>
          {sections.map((section, index) => (
            <motion.section
              key={section.titleKey}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.05 * (index + 1) }}
            >
              <h2>{t(section.titleKey)}</h2>
              <p>{t(section.bodyKey)}</p>
            </motion.section>
          ))}
        </div>
      </main>
    </>
  );
}
