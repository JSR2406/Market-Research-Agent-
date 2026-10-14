"use client";
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  ChevronDown,
  ChevronLeft,
  CornerDownLeft,
  PencilLine,
  RotateCcw,
  Stethoscope,
} from "lucide-react";
import {
  activeQuestions,
  describeMissingIntake,
  intakeProgress,
  isCustomAnswer,
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
  const [open, setOpen] = useState(false);
  // Stepper: show ONE question at a time (progressive disclosure — much easier
  // on small screens and for low-literacy users than a wall of questions).
  const [step, setStep] = useState(0);
  // Free-text answer being typed for the current question, committed on
  // Next / Enter / blur so a half-typed word never lands in the profile.
  const [draft, setDraft] = useState("");

  // The question list is dynamic — branching questions appear once the earlier
  // answers call for them, so it is derived from the answers, never hardcoded.
  const questions = useMemo(() => activeQuestions(value), [value]);
  const total = questions.length;
  const progress = intakeProgress(value);
  const answered = progress.answered;

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
              Business Check-up{" "}
              <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>(optional)</span>
            </p>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
              {answered === 0
                ? "A few quick questions, or type your own answers — Saathi asks the rest."
                : answered >= total
                  ? `All ${answered} answered — your Saathi now knows your business.`
                  : `${answered}/${total} answered — Saathi will ask you about the rest.`}
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
              Question {currentStep + 1} of {total}
            </span>
          </div>

          <div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "8px", marginBottom: "9px" }}>
              <p style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)", margin: 0, flex: 1 }}>
                {questionPrompt(question, value)}
              </p>
              {(value[question.id] || "").trim() && (
                <button
                  type="button"
                  onClick={() => clearAnswer(question.id)}
                  title="Clear this answer"
                  aria-label={`Clear answer: ${questionPrompt(question, value)}`}
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
                      {opt.label}
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
                {custom ? "Your answer" : "Or type your own answer"}
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
                  aria-label={`${questionPrompt(question, value)} — type your own answer`}
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
                    aria-label="Save this answer and continue"
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
              <ChevronLeft size={13} /> Back
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
                Skip
              </button>
            )}
            {answered >= total && (
              <span style={{ fontSize: "0.74rem", fontWeight: 600, color: "var(--success)", marginLeft: "auto" }}>
                All {answered} answered
              </span>
            )}
          </div>

          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "12px" }}>
            {nextQuestion
              ? `Your Saathi will ask you about the rest in chat: ${nextQuestion.replace(/^Still to tell me: /, "")}.`
              : "Your Saathi has everything it needs — it will use these answers everywhere."}{" "}
            Nothing is shared anywhere — it stays on your device.
          </p>
        </div>
      )}
    </motion.div>
  );
}