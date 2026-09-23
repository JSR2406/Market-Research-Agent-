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

const USPS = [
  {
    icon: UserCheck,
    title: "Your Personal Business Advisor",
    text: "It reads your research and remembers the conversation — then answers follow-ups about YOUR business, not generic trivia.",
  },
  {
    icon: Globe,
    title: "Real Market Research",
    text: "Lives on the web. It searches fresh, current facts about your industry instead of guessing from memory.",
  },
  {
    icon: Landmark,
    title: "Matched Indian Schemes",
    text: "MUDRA, PMEGP, CGTMSE and more — mapped to your business and stage, not a fixed list of a few schemes.",
  },
  {
    icon: WifiOff,
    title: "Works Offline & Free",
    text: "Runs on free + local AI models. No subscription, no paywall — and it still answers even when the internet drops.",
  },
  {
    icon: Languages,
    title: "जानिए हिंदी में",
    text: "Asks in Hindi, Hinglish or English and gets an answer in the same language — even offline, with no extra cost.",
  },
  {
    icon: ShieldCheck,
    title: "Your Data Stays Yours",
    text: "Stored locally on your device, with one-tap export and full delete (GDPR-aligned). Nothing is sold to anyone.",
  },
];

export default function Usps() {
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
        Why GrameenAI
      </p>
      <p
        style={{
          fontSize: "1.1rem",
          fontWeight: 700,
          color: "var(--text-primary)",
          marginBottom: "4px",
        }}
      >
        Built for your business — not a generic chatbot.
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
        ChatGPT answers general questions. GrameenAI builds, advises and gets
        your business loan-ready.
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
              key={usp.title}
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
                  {usp.title}
                </p>
                <p
                  style={{
                    fontSize: "0.72rem",
                    lineHeight: 1.5,
                    color: "var(--text-muted)",
                  }}
                >
                  {usp.text}
                </p>
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.section>
  );
}