"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, MessageSquare, Sparkles, MessageCircle } from "lucide-react";
import { SiteHeader } from "@/components/SiteHeader";
import ChatPanel from "@/components/ChatPanel";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/useSession";
import { answerLabel } from "@/lib/intake";

const LiveAdvisorPanel = dynamic(() => import("@/components/LiveAdvisorPanel"), { ssr: false });

export default function AdvisorPage() {
  const { t, locale } = useI18n();
  const { sessionId, ready, ensureSessionId, intake } = useSession();
  const [showWelcome, setShowWelcome] = useState(true);

  // A chat turn needs a session id (it is the memory namespace). Create one as
  // soon as the page loads, exactly like the research page does.
  useEffect(() => {
    if (ready && !sessionId) ensureSessionId();
  }, [ready, sessionId, ensureSessionId]);

  const hasContext = Object.keys(intake).length > 0;

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

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
          style={{ textAlign: "center", margin: "20px 0 24px", maxWidth: "620px" }}
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
            <MessageSquare size={26} color="var(--accent)" />
          </div>
          <h1 style={{ fontSize: "clamp(1.4rem, 4.5vw, 2rem)", fontWeight: 800, marginBottom: "8px" }}>
            {t("advisor.title")}
          </h1>
          <p style={{ color: "var(--text-secondary)" }}>{t("advisor.subtitle")}</p>
        </motion.div>

        {/* Research context badge */}
        {hasContext && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            style={{
              width: "100%",
              maxWidth: "760px",
              padding: "14px 18px",
              borderRadius: "var(--radius-md)",
              background: "rgba(34,211,165,0.08)",
              border: "1px solid rgba(34,211,165,0.25)",
              marginBottom: "16px",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                color: "var(--success)",
                fontWeight: 600,
                fontSize: "0.86rem",
                marginBottom: "6px",
              }}
            >
              <Sparkles size={15} aria-hidden="true" />
              {t("advisor.contextActive")}
            </div>
            <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginBottom: "10px" }}>
              {t("advisor.contextDesc")}
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {Object.entries(intake).map(([key, value]) => (
                <span
                  key={key}
                  style={{
                    padding: "3px 10px",
                    borderRadius: "999px",
                    background: "rgba(34,211,165,0.12)",
                    color: "var(--text-secondary)",
                    fontSize: "0.74rem",
                  }}
                >
                  {answerLabel(intake, key) || value}
                </span>
              ))}
            </div>
          </motion.div>
        )}

        {/* Welcome card */}
        <AnimatePresence>
          {showWelcome && (
            <motion.div
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -14 }}
              style={{
                width: "100%",
                maxWidth: "760px",
                padding: "20px clamp(16px, 4vw, 24px)",
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-lg)",
                marginBottom: "16px",
              }}
            >
              <h2 style={{ fontSize: "1.05rem", fontWeight: 700, marginBottom: "8px" }}>
                {t("advisor.welcome.title")}
              </h2>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem", marginBottom: "12px" }}>
                {t("advisor.welcome.desc")}
              </p>
              <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "6px" }}>
                {["advisor.welcome.item1", "advisor.welcome.item2", "advisor.welcome.item3", "advisor.welcome.item4"].map(
                  (key) => (
                    <li
                      key={key}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                        fontSize: "0.84rem",
                        color: "var(--text-secondary)",
                      }}
                    >
                      <span
                        aria-hidden="true"
                        style={{
                          width: "6px",
                          height: "6px",
                          borderRadius: "999px",
                          background: "var(--accent)",
                          flexShrink: 0,
                        }}
                      />
                      {t(key)}
                    </li>
                  )
                )}
              </ul>
              <button
                type="button"
                onClick={() => setShowWelcome(false)}
                style={{
                  marginTop: "14px",
                  background: "transparent",
                  border: "none",
                  color: "var(--accent)",
                  fontWeight: 600,
                  fontSize: "0.86rem",
                  cursor: "pointer",
                  padding: 0,
                  fontFamily: "inherit",
                }}
              >
                {t("advisor.welcome.gotIt")}
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Chat — the same advisor that lives on the research report, standalone */}
        {sessionId && <ChatPanel sessionId={sessionId} topic="" intake={intake} locale={locale} />}

        {/* Realtime voice advisor (LiveKit) */}
        <LiveAdvisorPanel />

        {/* WhatsApp — next channel */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{
            marginTop: "32px",
            marginBottom: "48px",
            width: "100%",
            maxWidth: "760px",
            padding: "20px clamp(16px, 5vw, 24px)",
            background: "rgba(37,211,102,0.04)",
            border: "1px dashed rgba(37,211,102,0.3)",
            borderRadius: "var(--radius-xl)",
            display: "flex",
            alignItems: "center",
            gap: "16px",
          }}
        >
          <div
            aria-hidden="true"
            style={{
              width: "44px",
              height: "44px",
              borderRadius: "22px",
              background: "linear-gradient(135deg, #25D366, #128C7E)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <MessageCircle size={22} color="#fff" />
          </div>
          <div>
            <div
              style={{
                display: "inline-block",
                background: "rgba(37,211,102,0.15)",
                color: "#25D366",
                padding: "2px 8px",
                borderRadius: "10px",
                fontSize: "0.68rem",
                fontWeight: 700,
                marginBottom: "4px",
                textTransform: "uppercase",
              }}
            >
              {t("misc.whatsappBadge")}
            </div>
            <p style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-primary)" }}>
              {t("misc.whatsappTitle")}
            </p>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{t("misc.whatsappText")}</p>
          </div>
        </motion.div>
      </main>
    </>
  );
}
