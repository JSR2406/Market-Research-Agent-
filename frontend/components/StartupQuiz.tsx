"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import { ChevronDown, RotateCcw, Stethoscope } from "lucide-react";

export type ProfileInit = {
  business?: string;
  age?: string;
  earnings?: string;
  loan?: string;
  need?: string;
};

export const PROFILE_LABELS: Record<string, string> = {
  kiosk: "shop or stall based business",
  vendor: "street vendor / cart business",
  home: "home-based or freelance business",
  service: "service / repair / tuition business",
  farm: "farm / dairy / agriculture business",
  new: "running the business for under 3 months",
  ramp: "running the business for 3-12 months",
  growing: "running the business for 1-3 years",
  settled: "running the business for over 3 years",
  low: "earning under ₹10,000 per month",
  mid: "earning ₹10,000-25,000 per month",
  good: "earning ₹25,000-50,000 per month",
  strong: "earning over ₹50,000 per month",
  none: "first-time borrower with no business loan before",
  mudra: "has taken a MUDRA loan before",
  bank: "has taken a bank loan before",
  family: "has only borrowed from family or friends",
  capital: "needs capital / a loan to grow",
  customers: "needs more customers and sales",
  licence: "needs help with documents and licences",
  plan: "needs a clear step-by-step business plan",
};

export function buildProfileSnippet(p: ProfileInit): string {
  const parts = Object.values(p)
    .map((v) => PROFILE_LABELS[v])
    .filter(Boolean);
  return parts.length ? "Business profile: " + parts.join("; ") : "";
}

const QUESTION_KEYS = ["business", "age", "earnings", "loan", "need"] as const;

const QUESTIONS: Record<keyof ProfileInit, { q: string; options: { value: string; label: string }[] }> = {
  business: {
    q: "What kind of business is this?",
    options: [
      { value: "kiosk", label: "Shop / stall" },
      { value: "vendor", label: "Street vendor / cart" },
      { value: "home", label: "Home-based / freelance" },
      { value: "service", label: "Service / repair" },
      { value: "farm", label: "Farm / dairy" },
    ],
  },
  age: {
    q: "How long has it been running?",
    options: [
      { value: "new", label: "Just started (< 3 mo)" },
      { value: "ramp", label: "3–12 months" },
      { value: "growing", label: "1–3 years" },
      { value: "settled", label: "3+ years" },
    ],
  },
  earnings: {
    q: "Rough monthly earning?",
    options: [
      { value: "low", label: "Under ₹10k" },
      { value: "mid", label: "₹10k–25k" },
      { value: "good", label: "₹25k–50k" },
      { value: "strong", label: "₹50k+" },
    ],
  },
  loan: {
    q: "Taken a business loan before?",
    options: [
      { value: "none", label: "No, first time" },
      { value: "mudra", label: "Yes, MUDRA" },
      { value: "bank", label: "Yes, bank loan" },
      { value: "family", label: "Only family / friends" },
    ],
  },
  need: {
    q: "What do you need most right now?",
    options: [
      { value: "capital", label: "Money to grow" },
      { value: "customers", label: "More customers" },
      { value: "licence", label: "Documents / licence help" },
      { value: "plan", label: "A clear plan" },
    ],
  },
};

export default function StartupQuiz({
  value,
  onChange,
}: {
  value: ProfileInit;
  onChange: (v: ProfileInit) => void;
}) {
  const [open, setOpen] = useState(false);
  const answered = QUESTION_KEYS.filter((k) => value[k]).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
      style={{
        marginBottom: "16px", width: "100%", maxWidth: "760px",
        background: "rgba(79,142,247,0.05)",
        border: `1px solid ${open ? "rgba(79,142,247,0.3)" : "rgba(79,142,247,0.18)"}`,
        borderRadius: "var(--radius-lg)",
        overflow: "hidden",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        style={{
          width: "100%", display: "flex", alignItems: "center", gap: "10px",
          background: "transparent", border: "none", padding: "12px 18px",
          cursor: "pointer", color: "var(--text-primary)", fontFamily: "inherit", textAlign: "left",
        }}
      >
        <div style={{ width: "30px", height: "30px", borderRadius: "9px", background: "linear-gradient(135deg, var(--accent), var(--accent2))", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Stethoscope size={15} color="#fff" />
        </div>
        <div style={{ flex: 1 }}>
          <p style={{ fontSize: "0.85rem", fontWeight: 700 }}>
            Startup Doctor — 5 quick questions{" "}
            <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>(optional)</span>
          </p>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            {answered === 0
              ? "Answer in 30 seconds — the very first report gets sharper."
              : `${answered}/5 answered — each one is already shaping your advice.`}
          </p>
        </div>
        {answered > 0 && (
          <button
            type="button"
            title="Reset answers"
            onClick={(e) => { e.stopPropagation(); onChange({}); }}
            style={{ border: "none", background: "rgba(255,255,255,0.06)", borderRadius: "8px", padding: "6px", cursor: "pointer", color: "var(--text-muted)", display: "flex", alignItems: "center" }}
          >
            <RotateCcw size={13} />
          </button>
        )}
        <motion.div animate={{ rotate: open ? 180 : 0 }} style={{ color: "var(--text-muted)", display: "flex" }}>
          <ChevronDown size={16} />
        </motion.div>
      </button>

      {open && (
        <div style={{ padding: "4px 18px 18px", display: "flex", flexDirection: "column", gap: "14px" }}>
          {QUESTION_KEYS.map((key) => {
            const q = QUESTIONS[key];
            return (
              <div key={key}>
                <p style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "7px" }}>{q.q}</p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                  {q.options.map((opt) => {
                    const selected = value[key] === opt.value;
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => onChange({ ...value, [key]: selected ? undefined : opt.value })}
                        style={{
                          fontSize: "0.76rem", fontWeight: 600,
                          color: selected ? "#fff" : "var(--text-secondary)",
                          background: selected ? "linear-gradient(135deg, var(--accent), var(--accent2))" : "var(--bg-surface)",
                          border: `1px solid ${selected ? "transparent" : "var(--border)"}`,
                          borderRadius: "20px", padding: "5px 13px", cursor: "pointer", transition: "all 0.15s",
                        }}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            These answers are added to your research automatically. Nothing is shared anywhere — it stays on your device.
          </p>
        </div>
      )}
    </motion.div>
  );
}