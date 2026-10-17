"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  ChevronDown,
  ChevronLeft,
  CornerDownLeft,
  FileSpreadsheet,
  Gavel,
  PencilLine,
  RotateCcw,
  Stethoscope,
} from "lucide-react";
import { API_BASE } from "@/lib/api";
import BenefitCalculator from "@/components/BenefitCalculator";
import DocumentChecklist from "@/components/DocumentChecklist";
import { track } from "@/lib/analytics";
import { useI18n } from "@/lib/i18n";
import {
  activeQuestions,
  describeMissingIntake,
  intakeProgress,
  isCustomAnswer,
  optionLabel,
  questionPrompt,
  type IntakeAnswers,
  type IntakeQuestion,
} from "@/lib/intake";

export type { IntakeAnswers } from "@/lib/intake";

export type ProfileInit = IntakeAnswers;

export default function StartupQuiz({
  value,
  onChange,
}: {
  value: IntakeAnswers;
  onChange: (v: IntakeAnswers) => void;
}) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  // Stepper: show ONE question at a time (progressive disclosure — much easier
  // on small screens and for low-literacy users than a wall of questions).
  const [step, setStep] = useState(0);
  // Free-text answer being typed for the current question, committed on
  // Next / Enter / blur so a half-typed word never lands in the profile.
  const [draft, setDraft] = useState("");
  // Live verdicts from the deterministic rule engine — the user sees what they
  // qualify for while they answer, not only after a full research run.
  const [verdict, setVerdict] = useState<{
    business_label?: string;
    families?: { name: string; status: string; status_label: string }[];
    coverage?: { score?: number };
    questions?: Record<string, string>;
  } | null>(null);

  // The question list is dynamic — branching questions appear once the earlier
  // answers call for them, so it is derived from the answers, never hardcoded.
  const questions = useMemo(() => activeQuestions(value), [value]);
  const total = questions.length;
  const progress = intakeProgress(value);
  const answered = progress.answered;

  // Funnel edges (WS-12): "started" the first time the panel is opened, and
  // "complete" once every active question has an answer. Both fire once per
  // session, and neither ever sends what the user actually typed.
  const startedRef = useRef(false);
  const completedRef = useRef(false);

  useEffect(() => {
    if (open && !startedRef.current) {
      startedRef.current = true;
      track("checkup_start", { page: "/research" });
    }
  }, [open]);

  useEffect(() => {
    if (total > 0 && answered >= total && !completedRef.current) {
      completedRef.current = true;
      track("checkup_complete", { count: answered });
    }
  }, [total, answered]);

  // Keep the cursor on a question that still exists.
  const currentStep = Math.min(step, Math.max(0, total - 1));
  const question: IntakeQuestion | undefined = questions[currentStep];
  const custom = question ? isCustomAnswer(value, question) : false;

  // Load the stored answer into the text box whenever the step changes.
  useEffect(() => {
    if (!question) return;
    setDraft(value[question.id] && isCustomAnswer(value, question) ? value[question.id] : "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep, question?.id]);

  const toggleOpen = () => {
    const next = !open;
    if (next) {
      // Resume at the first unanswered question (or the last one if done).
      const firstUnanswered = questions.findIndex((q) => !(value[q.id] || "").trim());
      setStep(firstUnanswered === -1 ? total - 1 : firstUnanswered);
    }
    setOpen(next);
  };

  const choose = (key: string, answer: string) => {
    onChange({ ...value, [key]: answer });
    setDraft("");
    if (currentStep < total - 1) setStep(currentStep + 1);
  };

  const commitDraft = (advance = true) => {
    if (!question) return;
    const text = draft.trim();
    if (!text) return;
    onChange({ ...value, [question.id]: text });
    setDraft("");
    if (advance && currentStep < total - 1) setStep(currentStep + 1);
  };

  const clearAnswer = (key: string) => {
    const next = { ...value };
    delete next[key];
    onChange(next);
    setDraft("");
  };

  // Ask the rule engine what the answers so far mean. Debounced so typing a
  // free-text answer doesn't fire a request per keystroke. This also carries
  // the question wording, so it must load even with zero answers or the first
  // question would render in English on a Hindi page.
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      (async () => {
        try {
          const res = await fetch(`${API_BASE}/api/eligibility`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ intake: value, lang: locale }),
            signal: controller.signal,
          });
          if (!res.ok) return;
          setVerdict(await res.json());
        } catch {
          /* offline or aborted — the quiz still works without verdicts */
        }
      })();
    }, 700);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(value), locale]);

  const openNow = (verdict?.families ?? []).filter((f) => f.status === "eligible" || f.status === "likely");

  // Question wording comes from the backend so the stepper and the gap
  // detection can never drift; the local registry stays the fallback.
  const promptFor = (q: (typeof questions)[number]): string => {
    const fromApi = verdict?.questions?.[q.id];
    return typeof fromApi === "string" && fromApi ? fromApi : questionPrompt(q, value);
  };

  const nextQuestion = describeMissingIntake(value);

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
              {t("quiz.title")}{" "}
              <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>{t("quiz.optional")}</span>
            </p>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
              {answered === 0
                ? t("quiz.sub0")
                : answered >= total
                  ? t("quiz.subDone", { total: answered })
                  : t("quiz.subPartial", { answered, total })}
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
            aria-label={t("quiz.reset")}
            onClick={() => { onChange({}); setStep(0); setDraft(""); }}
            style={{ border: "none", background: "rgba(255,255,255,0.06)", borderRadius: "8px", padding: "6px", cursor: "pointer", color: "var(--text-muted)", display: "flex", alignItems: "center", flexShrink: 0 }}
          >
            <RotateCcw size={13} />
          </button>
        )}
      </div>

      {open && question && (
        <div style={{ padding: "4px 18px 18px" }}>
          {/* Progress — announce it so screen readers track the step */}
          <div
            role="status"
            aria-live="polite"
            style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px", flexWrap: "wrap" }}
          >
            <div style={{ display: "flex", gap: "5px", flexShrink: 0 }}>
              {questions.map((q, i) => (
                <span
                  key={q.id}
                  aria-hidden="true"
                  style={{
                    width: i === currentStep ? "18px" : "7px",
                    height: "7px",
                    borderRadius: "99px",
                    background:
                      (value[q.id] || "").trim()
                        ? "var(--success)"
                        : i === currentStep
                          ? "var(--accent)"
                          : "var(--border-bright)",
                    transition: "all 0.2s",
                  }}
                />
              ))}
            </div>
            <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 600 }}>
              {t("quiz.questionOf", { n: currentStep + 1, total })}
            </span>
          </div>

          <div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "8px", marginBottom: "9px" }}>
              <p style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)", margin: 0, flex: 1 }}>
                {promptFor(question)}
              </p>
              {(value[question.id] || "").trim() && (
                <button
                  type="button"
                  onClick={() => clearAnswer(question.id)}
                  title="Clear this answer"
                  aria-label={`${t("quiz.clearAnswer")}: ${promptFor(question)}`}
                  style={{
                    border: "none", background: "transparent", color: "var(--text-muted)",
                    cursor: "pointer", display: "flex", padding: "2px", flexShrink: 0,
                  }}
                >
                  <RotateCcw size={12} />
                </button>
              )}
            </div>

            {/* Quick chips — the fast path */}
            {question.options && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                {question.options.map((opt) => {
                  const selected = value[question.id] === opt.label;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => choose(question.id, opt.label)}
                      aria-pressed={selected}
                      style={{
                        fontSize: "0.78rem", fontWeight: 600,
                        color: selected ? "#fff" : "var(--text-secondary)",
                        background: selected ? "linear-gradient(135deg, var(--accent), var(--accent2))" : "var(--bg-surface)",
                        border: `1px solid ${selected ? "transparent" : "var(--border)"}`,
                        borderRadius: "20px", padding: "6px 14px", cursor: "pointer", transition: "all 0.15s",
                      }}
                    >
                      {optionLabel(opt.label, locale)}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Free text — the user's own words, which beat a chip for research */}
            <div style={{ marginTop: "10px" }}>
              <label
                htmlFor={`intake-${question.id}`}
                style={{
                  display: "flex", alignItems: "center", gap: "5px",
                  fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: "5px",
                }}
              >
                <PencilLine size={11} />
                {custom ? t("quiz.yourAnswer") : t("quiz.typeOwn")}
              </label>
              <div style={{ display: "flex", gap: "6px" }}>
                <input
                  id={`intake-${question.id}`}
                  type="text"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      commitDraft();
                    }
                  }}
                  placeholder={question.hint}
                  aria-label={`${promptFor(question)} — ${t("quiz.typeOwn")}`}
                  style={{
                    flex: 1, minWidth: 0,
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                    borderRadius: "10px",
                    padding: "8px 12px",
                    fontSize: "0.8rem",
                    color: "var(--text-primary)",
                    fontFamily: "inherit",
                  }}
                />
                {draft.trim() && (
                  <button
                    type="button"
                    onClick={() => commitDraft()}
                    title="Save this answer"
                    aria-label={t("quiz.saveAnswer")}
                    style={{
                      border: "none",
                      background: "linear-gradient(135deg, var(--accent), var(--accent2))",
                      color: "#fff", borderRadius: "10px", padding: "0 12px",
                      cursor: "pointer", display: "flex", alignItems: "center", flexShrink: 0,
                    }}
                  >
                    <CornerDownLeft size={14} />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Navigation — Back / Skip / Start over */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "14px" }}>
            <button
              type="button"
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={currentStep === 0}
              style={{
                display: "flex", alignItems: "center", gap: "4px",
                fontSize: "0.74rem", fontWeight: 600,
                color: currentStep === 0 ? "var(--text-muted)" : "var(--text-secondary)",
                background: "transparent", border: "1px solid var(--border)",
                borderRadius: "16px", padding: "5px 12px",
                cursor: currentStep === 0 ? "default" : "pointer", opacity: currentStep === 0 ? 0.5 : 1,
              }}
            >
              <ChevronLeft size={13} /> {t("quiz.back")}
            </button>
            {currentStep < total - 1 && (
              <button
                type="button"
                onClick={() => setStep((s) => s + 1)}
                style={{
                  fontSize: "0.74rem", fontWeight: 600,
                  color: "var(--text-muted)", background: "transparent",
                  border: "none", padding: "5px 8px", cursor: "pointer",
                }}
              >
                {t("quiz.skip")}
              </button>
            )}
            {answered >= total && (
              <span style={{ fontSize: "0.74rem", fontWeight: 600, color: "var(--success)", marginLeft: "auto" }}>
                {t("quiz.allAnswered", { total: answered })}
              </span>
            )}
          </div>

          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "12px" }}>
            {nextQuestion
              ? t("quiz.askRest", { list: nextQuestion.replace(/^Still to tell me: /, "") })
              : t("quiz.allSet")}{" "}
            {t("quiz.staysLocal")}
          </p>

          {/* Live rule-engine verdict — shown while they answer */}
          {verdict && (openNow.length > 0 || verdict.business_label) && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              style={{
                marginTop: "12px",
                padding: "10px 12px",
                borderRadius: "10px",
                background: "rgba(37,211,102,0.06)",
                border: "1px solid rgba(37,211,102,0.22)",
              }}
            >
              <p
                style={{
                  margin: 0,
                  fontSize: "0.72rem",
                  fontWeight: 700,
                  color: "var(--success)",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <Gavel size={12} />
                {t("quiz.liveTitle", { label: verdict.business_label ?? "" })}
              </p>
              {openNow.length > 0 && (
                <p style={{ margin: "4px 0 0", fontSize: "0.71rem", color: "var(--text-secondary)" }}>
                  {t("quiz.openForYou", { list: openNow.slice(0, 4).map((f) => f.name).join(", ") })}
                </p>
              )}
              {typeof verdict.coverage?.score === "number" && (
                <p style={{ margin: "3px 0 0", fontSize: "0.68rem", color: "var(--text-muted)" }}>
                  {t("quiz.filledIn", { pct: verdict.coverage.score })}
                </p>
              )}
            </motion.div>
          )}

          {/* "How much?" — the calculator only appears once a door is open */}
          {openNow.length > 0 && <BenefitCalculator intake={value} />}
          {openNow.length > 0 && <DocumentChecklist intake={value} />}
          {openNow.length > 0 && (
            <Link
              href="/dpr"
              style={{
                marginTop: "12px",
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                padding: "9px 16px",
                borderRadius: "10px",
                border: "1px solid var(--border-bright)",
                background: "var(--accent-glow)",
                color: "var(--accent)",
                textDecoration: "none",
                fontSize: "0.78rem",
                fontWeight: 700,
              }}
            >
              <FileSpreadsheet size={14} />
              {t("dpr.cta")}
            </Link>
          )}
        </div>
      )}
    </motion.div>
  );
}