"use client";
import { motion } from "framer-motion";
import {
  Globe,
  Landmark,
  Languages,
  ShieldCheck,
  UserCheck,
  WifiOff,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";

const USPS = [
  { icon: UserCheck, key: "usps.1" },
  { icon: Globe, key: "usps.2" },
  { icon: Landmark, key: "usps.3" },
  { icon: WifiOff, key: "usps.4" },
  { icon: Languages, key: "usps.5" },
  { icon: ShieldCheck, key: "usps.6" },
];

export default function Usps() {
  const { t } = useI18n();
  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.15 }}
      style={{ width: "100%", maxWidth: "760px", marginTop: "28px" }}
    >
      <p
        style={{
          fontSize: "0.72rem",
          fontWeight: 700,
          color: "var(--accent)",
          textTransform: "uppercase",
          letterSpacing: "0.12em",
          marginBottom: "6px",
        }}
      >
        {t("usps.kicker")}
      </p>
      <p
        style={{
          fontSize: "1.1rem",
          fontWeight: 700,
          color: "var(--text-primary)",
          marginBottom: "4px",
        }}
      >
        {t("usps.title")}
      </p>
      <p
        style={{
          fontSize: "0.84rem",
          color: "var(--text-muted)",
          lineHeight: 1.5,
          maxWidth: "600px",
          marginBottom: "16px",
        }}
      >
        {t("usps.sub")}
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
          gap: "12px",
        }}
      >
        {USPS.map((usp, i) => {
          const Icon = usp.icon;
          return (
            <motion.div
              key={usp.key}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.2 + i * 0.07 }}
              whileHover={{ y: -3 }}
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: "var(--radius-md)",
                padding: "16px",
                display: "flex",
                gap: "12px",
                alignItems: "flex-start",
              }}
            >
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "10px",
                  background:
                    "linear-gradient(135deg, var(--accent), var(--accent2))",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                  boxShadow: "0 4px 12px var(--accent-glow)",
                }}
              >
                <Icon size={17} color="#fff" />
              </div>
              <div style={{ minWidth: 0 }}>
                <p
                  style={{
                    fontSize: "0.8rem",
                    fontWeight: 700,
                    color: "var(--text-primary)",
                    marginBottom: "4px",
                  }}
                >
                  {t(`${usp.key}.title`)}
                </p>
                <p
                  style={{
                    fontSize: "0.72rem",
                    lineHeight: 1.5,
                    color: "var(--text-muted)",
                  }}
                >
                  {t(`${usp.key}.text`)}
                </p>
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.section>
  );
}