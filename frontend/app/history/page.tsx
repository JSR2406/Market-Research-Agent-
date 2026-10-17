"use client";

import { useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { History, ArrowLeft, Plus } from "lucide-react";
import { SiteHeader } from "@/components/SiteHeader";
import SessionHistory from "@/components/SessionHistory";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/useSession";

export default function HistoryPage() {
  const { t } = useI18n();
  const { sessionId, ready, ensureSessionId } = useSession();

  // The session id is the history namespace — create one on first visit so the
  // page always has a stable store to read from, exactly like /research.
  useEffect(() => {
    if (ready && !sessionId) ensureSessionId();
  }, [ready, sessionId, ensureSessionId]);

  return (
    <>
      <SiteHeader />
      <main
        className="page-shell"
        style={{
          maxWidth: "820px",
          marginInline: "auto",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
        }}
      >
        <div style={{ width: "100%", maxWidth: "760px" }}>
          <Link
            href="/research"
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
            {t("advisor.backToResearch")}
          </Link>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
          style={{ textAlign: "center", margin: "20px 0 8px", maxWidth: "620px" }}
        >
          <div
            aria-hidden="true"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "56px",
              height: "56px",
              borderRadius: "999px",
              background: "var(--accent-glow)",
              marginBottom: "14px",
            }}
          >
            <History size={26} color="var(--accent)" />
          </div>
          <h1 style={{ fontSize: "clamp(1.4rem, 4.5vw, 2rem)", fontWeight: 800, marginBottom: "8px" }}>
            {t("history.title")}
          </h1>
          <p style={{ color: "var(--text-secondary)" }}>{t("history.subtitle")}</p>
        </motion.div>

        {sessionId && <SessionHistory sessionId={sessionId} />}

        <Link
          href="/research"
          style={{
            marginTop: "24px",
            marginBottom: "64px",
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            padding: "11px 22px",
            borderRadius: "var(--radius-md)",
            background: "linear-gradient(135deg, var(--accent), var(--accent-dim))",
            color: "#fff",
            textDecoration: "none",
            fontWeight: 700,
            fontSize: "0.9rem",
          }}
        >
          <Plus size={17} aria-hidden="true" />
          {t("landing.hero.cta")}
        </Link>
      </main>
    </>
  );
}
