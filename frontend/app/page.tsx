"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  BarChart3,
  FileCheck2,
  Landmark,
  Lightbulb,
  ShieldCheck,
  TrendingUp,
  WifiOff,
} from "lucide-react";
import { SiteHeader } from "@/components/SiteHeader";
import { useI18n } from "@/lib/i18n";

const FEATURES = [
  { icon: Lightbulb, titleKey: "landing.features.1.title", descKey: "landing.features.1.desc" },
  { icon: BarChart3, titleKey: "landing.features.2.title", descKey: "landing.features.2.desc" },
  { icon: Landmark, titleKey: "landing.features.3.title", descKey: "landing.features.3.desc" },
  { icon: FileCheck2, titleKey: "landing.features.4.title", descKey: "landing.features.4.desc" },
  { icon: WifiOff, titleKey: "landing.features.5.title", descKey: "landing.features.5.desc" },
  { icon: ShieldCheck, titleKey: "landing.features.6.title", descKey: "landing.features.6.desc" },
] as const;

const cardStyle: React.CSSProperties = {
  padding: "22px clamp(16px, 4vw, 24px)",
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-lg)",
};

export default function LandingPage() {
  const { t } = useI18n();

  return (
    <>
      <SiteHeader />
      <main className="page-shell" style={{ maxWidth: "1080px", marginInline: "auto" }}>
        {/* Hero */}
        <section style={{ textAlign: "center", padding: "clamp(20px, 6vw, 56px) 0 clamp(16px, 4vw, 32px)" }}>
          <motion.span
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            style={{
              display: "inline-block",
              padding: "5px 14px",
              borderRadius: "999px",
              background: "var(--accent-glow)",
              color: "var(--accent)",
              fontSize: "0.75rem",
              fontWeight: 600,
              marginBottom: "18px",
            }}
          >
            {t("landing.hero.badge")}
          </motion.span>

          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            style={{
              fontSize: "clamp(1.7rem, 6vw, 2.9rem)",
              fontWeight: 800,
              letterSpacing: "-0.03em",
              lineHeight: 1.15,
              marginBottom: "16px",
              background: "linear-gradient(135deg, var(--text-primary) 45%, var(--accent))",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            {t("landing.hero.title")}
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.08 }}
            style={{
              fontSize: "clamp(0.95rem, 2.6vw, 1.1rem)",
              color: "var(--text-secondary)",
              maxWidth: "620px",
              margin: "0 auto 28px",
            }}
          >
            {t("landing.hero.subtitle")}
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.16 }}
            style={{ display: "flex", flexWrap: "wrap", gap: "12px", justifyContent: "center" }}
          >
            <Link
              href="/research"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                padding: "13px 26px",
                borderRadius: "var(--radius-md)",
                background: "linear-gradient(135deg, var(--accent), var(--accent-dim))",
                color: "#fff",
                textDecoration: "none",
                fontWeight: 700,
                fontSize: "0.95rem",
                boxShadow: "0 6px 20px var(--accent-glow)",
              }}
            >
              {t("landing.hero.cta")}
              <ArrowRight size={18} aria-hidden="true" />
            </Link>
            <Link
              href="/schemes"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                padding: "13px 26px",
                borderRadius: "var(--radius-md)",
                background: "transparent",
                border: "1px solid var(--border-bright)",
                color: "var(--text-primary)",
                textDecoration: "none",
                fontWeight: 600,
                fontSize: "0.95rem",
              }}
            >
              {t("landing.hero.ctaSecondary")}
            </Link>
          </motion.div>

          <p style={{ marginTop: "18px", fontSize: "0.8rem", color: "var(--text-muted)" }}>
            {t("landing.hero.trust")}
          </p>
        </section>

        {/* Features */}
        <section style={{ paddingBottom: "40px" }}>
          <div style={{ textAlign: "center", marginBottom: "28px" }}>
            <h2 style={{ fontSize: "clamp(1.3rem, 4vw, 1.8rem)", fontWeight: 800, marginBottom: "8px" }}>
              {t("landing.features.title")}
            </h2>
            <p style={{ color: "var(--text-secondary)", maxWidth: "560px", marginInline: "auto" }}>
              {t("landing.features.subtitle")}
            </p>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
              gap: "14px",
            }}
          >
            {FEATURES.map(({ icon: Icon, titleKey, descKey }, i) => (
              <motion.article
                key={titleKey}
                initial={{ opacity: 0, y: 14 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.4 }}
                transition={{ duration: 0.4, delay: i * 0.05 }}
                style={cardStyle}
              >
                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "40px",
                    height: "40px",
                    borderRadius: "12px",
                    background: "var(--accent-glow)",
                    marginBottom: "12px",
                  }}
                >
                  <Icon size={20} color="var(--accent)" aria-hidden="true" />
                </div>
                <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "6px" }}>
                  {t(titleKey)}
                </h3>
                <p style={{ fontSize: "0.86rem", color: "var(--text-secondary)" }}>{t(descKey)}</p>
              </motion.article>
            ))}
          </div>
        </section>

        {/* Closing CTA */}
        <section
          style={{
            ...cardStyle,
            textAlign: "center",
            background: "linear-gradient(135deg, rgba(79,142,247,0.12), rgba(155,135,245,0.08))",
            borderColor: "var(--border-bright)",
            marginBottom: "40px",
          }}
        >
          <TrendingUp size={26} color="var(--accent)" aria-hidden="true" />
          <h2 style={{ fontSize: "clamp(1.2rem, 3.5vw, 1.6rem)", fontWeight: 800, margin: "12px 0 8px" }}>
            {t("landing.cta.title")}
          </h2>
          <p style={{ color: "var(--text-secondary)", marginBottom: "20px" }}>
            {t("landing.cta.subtitle")}
          </p>
          <Link
            href="/research"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "13px 28px",
              borderRadius: "var(--radius-md)",
              background: "linear-gradient(135deg, var(--accent), var(--accent-dim))",
              color: "#fff",
              textDecoration: "none",
              fontWeight: 700,
            }}
          >
            {t("landing.cta.button")}
            <ArrowRight size={18} aria-hidden="true" />
          </Link>
        </section>

        {/* Footer */}
        <footer
          style={{
            borderTop: "1px solid var(--border)",
            paddingTop: "28px",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "20px",
          }}
        >
          <div>
            <h3 style={{ fontWeight: 700, marginBottom: "8px", fontSize: "0.95rem" }}>
              {t("brand.name")}
            </h3>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
              {t("landing.footer.desc")}
            </p>
          </div>
          <nav aria-label={t("landing.footer.links")}>
            <h4 style={{ fontWeight: 700, marginBottom: "8px", fontSize: "0.9rem" }}>
              {t("landing.footer.links")}
            </h4>
            <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "6px" }}>
              {[
                { href: "/research", key: "nav.research" },
                { href: "/advisor", key: "nav.advisor" },
                { href: "/schemes", key: "nav.schemes" },
              ].map((l) => (
                <li key={l.href}>
                  <Link href={l.href} style={{ color: "var(--text-secondary)", fontSize: "0.84rem", textDecoration: "none" }}>
                    {t(l.key)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div>
            <h4 style={{ fontWeight: 700, marginBottom: "8px", fontSize: "0.9rem" }}>
              {t("landing.footer.legal")}
            </h4>
            <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "6px" }}>
              <li style={{ color: "var(--text-muted)", fontSize: "0.84rem" }}>{t("landing.footer.privacy")}</li>
              <li style={{ color: "var(--text-muted)", fontSize: "0.84rem" }}>{t("landing.footer.terms")}</li>
              <li style={{ color: "var(--text-muted)", fontSize: "0.84rem" }}>{t("landing.footer.contact")}</li>
            </ul>
          </div>
        </footer>

        <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.78rem", marginTop: "28px" }}>
          {t("landing.footer.copyright")}
        </p>
      </main>
    </>
  );
}
