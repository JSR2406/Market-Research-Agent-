"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import { ChevronDown, ChevronLeft, RotateCcw, Stethoscope } from "lucide-react";

export type ProfileInit = {
  business?: string;
  age?: string;
  earnings?: string;
  location?: string;
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
  // Location — drives state-specific scheme matching and local research.
  mh: "located in Maharashtra",
  gj: "located in Gujarat",
  rj: "located in Rajasthan",
  up: "located in Uttar Pradesh",
  br: "located in Bihar",
  wb: "located in West Bengal",
  tn: "located in Tamil Nadu",
  ka: "located in Karnataka",
  ts: "located in Telangana / Andhra Pradesh",
  mp: "located in Madhya Pradesh / Chhattisgarh",
  other: "located in another Indian state",
};

export function buildProfileSnippet(p: ProfileInit): string {
  const parts = Object.values(p)
    .map((v) => PROFILE_LABELS[v as string])
    .filter(Boolean);
  return parts.length ? "Business profile: " + parts.join("; ") : "";
}

const QUESTION_KEYS = [
  "business",
  "age",
  "earnings",
  "location",
  "loan",
  "need",
] as const;
const TOTAL = QUESTION_KEYS.length;

type QuestionKey = (typeof QUESTION_KEYS)[number];

const QUESTIONS: Record<QuestionKey, { q: string; options: { value: string; label: string }[] }> = {
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
  location: {
    q: "Where is your business?",
    options: [
      { value: "mh", label: "Maharashtra" },
      { value: "gj", label: "Gujarat" },
      { value: "rj", label: "Rajasthan" },
      { value: "up", label: "Uttar Pradesh" },
      { value: "br", label: "Bihar" },
      { value: "wb", label: "West Bengal" },
      { value: "tn", label: "Tamil Nadu" },
      { value: "ka", label: "Karnataka" },
      { value: "ts", label: "Telangana / AP" },
      { value: "mp", label: "MP / Chhattisgarh" },
      { value: "other", label: "Another state" },
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
  // Stepper: show ONE question at a time (progressive disclosure — much easier
  // on small screens and for low-literacy users than a wall of 6 questions).
  const [step, setStep] = useState(0);
  const answered = QUESTION_KEYS.filter((k) => value[k]).length;

  const toggleOpen = () => {
    const next = !open;
    if (next) {
      // Resume at the first unanswered question (or the last one if done).
      const firstUnanswered = QUESTION_KEYS.findIndex((k) => !value[k]);
      setStep(firstUnanswered === -1 ? TOTAL - 1 : firstUnanswered);
    }
    setOpen(next);
  };

  const choose = (key: QuestionKey, optionValue: string) => {
    onChange({ ...value, [key]: optionValue });
    if (step < TOTAL - 1) setStep(step + 1);
  };

  const key = QUESTION_KEYS[step];
  const q = QUESTIONS[key];
  const allDone = answered === TOTAL;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
      style={{
        marginBottom: "16px", width: "100%", maxWidth: "var(--content-max)",
        background: "rgba(79,142,247,0.05)",
        border: `1px solid ${open ? "rgba(79,142,247,0.3)" : "rgba(79,142,247,0.18)"}`,
        borderRadius: "var(--radius-lg)",
        overflow: "hidden",
      }}
    >
      {/* Header row — reset control is a SIBLING of the toggle, never nested
          (nested <button> is invalid HTML and breaks keyboard/AT semantics). */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "12px 18px" }}>
        <button
          type="button"
          onClick={toggleOpen}
          aria-expanded={open}
          style={{
            flex: 1, display: "flex", alignItems: "center", gap: "10px",
            background: "transparent", border: "none", padding: 0,
            cursor: "pointer", color: "var(--text-primary)", fontFamily: "inherit", textAlign: "left",
          }}
        >
          <div style={{ width: "30px", height: "30px", borderRadius: "9px", background: "linear-gradient(135deg, var(--accent), var(--accent2))", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <Stethoscope size={15} color="#fff" />
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: "0.85rem", fontWeight: 700 }}>
              Business Check-up — {TOTAL} quick questions{" "}
              <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>(optional)</span>
            </p>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
              {answered === 0
                ? "Answer in 30 seconds — the very first report gets sharper."
                : allDone
                  ? `All ${TOTAL} answered — your answers keep shaping your advice.`
                  : `${answered}/${TOTAL} answered — each one is already shaping your advice.`}
            </p>
          </div>
          <motion.div animate={{ rotate: open ? 180 : 0 }} style={{ color: "var(--text-muted)", display: "flex" }}>
            <ChevronDown size={16} />
          </motion.div>
        </button>
        {answered > 0 && (
          <button
            type="button"
            title="Reset answers"
            aria-label="Reset check-up answers"
            onClick={() => { onChange({}); setStep(0); }}
            style={{ border: "none", background: "rgba(255,255,255,0.06)", borderRadius: "8px", padding: "6px", cursor: "pointer", color: "var(--text-muted)", display: "flex", alignItems: "center", flexShrink: 0 }}
          >
            <RotateCcw size={13} />
          </button>
        )}
      </div>

      {open && (
        <div style={{ padding: "4px 18px 18px" }}>
          {/* Progress — announce it so screen readers track the step */}
          <div
            role="status"
            aria-live="polite"
            style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}
          >
            <div style={{ display: "flex", gap: "5px", flexShrink: 0 }}>
              {QUESTION_KEYS.map((k, i) => (
                <span
                  key={k}
                  aria-hidden="true"
                  style={{
                    width: i === step ? "18px" : "7px",
                    height: "7px",
                    borderRadius: "99px",
                    background:
                      value[k]
                        ? "var(--success)"
                        : i === step
                          ? "var(--accent)"
                          : "var(--border-bright)",
                    transition: "all 0.2s",
                  }}
                />
              ))}
            </div>
            <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 600 }}>
              Question {step + 1} of {TOTAL}
            </span>
          </div>

          <div>
            <p style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "9px" }}>{q.q}</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {q.options.map((opt) => {
                const selected = value[key] === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => choose(key, opt.value)}
                    aria-pressed={selected}
                    style={{
                      fontSize: "0.78rem", fontWeight: 600,
                      color: selected ? "#fff" : "var(--text-secondary)",
                      background: selected ? "linear-gradient(135deg, var(--accent), var(--accent2))" : "var(--bg-surface)",
                      border: `1px solid ${selected ? "transparent" : "var(--border)"}`,
                      borderRadius: "20px", padding: "6px 14px", cursor: "pointer", transition: "all 0.15s",
                    }}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Navigation — Back / Skip for the current step */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "14px" }}>
            <button
              type="button"
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
              style={{
                display: "flex", alignItems: "center", gap: "4px",
                fontSize: "0.74rem", fontWeight: 600,
                color: step === 0 ? "var(--text-muted)" : "var(--text-secondary)",
                background: "transparent", border: "1px solid var(--border)",
                borderRadius: "16px", padding: "5px 12px",
                cursor: step === 0 ? "default" : "pointer", opacity: step === 0 ? 0.5 : 1,
              }}
            >
              <ChevronLeft size={13} /> Back
            </button>
            {step < TOTAL - 1 && (
              <button
                type="button"
                onClick={() => setStep((s) => s + 1)}
                style={{
                  fontSize: "0.74rem", fontWeight: 600,
                  color: "var(--text-muted)", background: "transparent",
                  border: "none", padding: "5px 8px", cursor: "pointer",
                }}
              >
                Skip
              </button>
            )}
            {allDone && (
              <span style={{ fontSize: "0.74rem", fontWeight: 600, color: "var(--success)", marginLeft: "auto" }}>
                All {TOTAL} answered
              </span>
            )}
          </div>

          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "12px" }}>
            These answers are added to your research automatically. Nothing is shared anywhere — it stays on your device.
          </p>
        </div>
      )}
    </motion.div>
  );
}
