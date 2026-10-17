"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Banknote,
  Bot,
  CircleHelp,
  FileText,
  Languages,
  Loader2,
  Mic,
  MicOff,
  Send,
  Sparkles,
  Trash2,
  TrendingUp,
  User,
} from "lucide-react";
import { API_BASE } from "@/lib/api";
import {
  buildIntakeSummary,
  describeMissingIntake,
  type IntakeAnswers,
} from "@/lib/intake";
import { useI18n, type Locale } from "@/lib/i18n";
import { speechSupport, startListening, type ListenSession } from "@/lib/speech";

type ChatMessage = { role: "user" | "assistant"; content: string };

const LANG_KEY = "grameenai_chat_lang";
const LANGS = [
  { value: "auto", label: "Auto" },
  { value: "hi", label: "हिंदी" },
  { value: "en", label: "EN" },
];

const QUICK_PROMPTS = [
  { icon: Banknote, key: "chat.quick1", label: "Which loans can I get?", lang: "en" },
  { icon: FileText, key: "chat.quick2", label: "Documents I need", lang: "en" },
  { icon: Languages, key: "chat.quick3", label: "क्या मुद्रा लोन मिलेगा?", lang: "hi" },
  { icon: TrendingUp, key: "chat.quick4", label: "Start with ₹1 lakh?", lang: "en" },
];

function welcome(topic: string, intake: IntakeAnswers, t: (k: string, v?: Record<string, string | number>) => string) {
  const known = buildIntakeSummary(intake);
  const missing = describeMissingIntake(intake);
  if (topic.trim()) {
    const extra = known ? t("chat.subIntake", { intake: known }) : "";
    return t("chat.welcomeReport", { topic, intake: extra });
  }
  if (known) {
    return t("chat.welcomeIntake", {
      intake: known,
      missing: missing
        ? ` ${t("chat.missingAsk")}`
        : ` ${t("chat.noMemoryAsk")}`,
    });
  }
  return t("chat.welcomeEmpty");
}

export default function ChatPanel({
  sessionId,
  topic,
  intake,
  locale,
}: {
  sessionId: string;
  topic: string;
  intake: IntakeAnswers;
  /** Site language. The advisor replies in it unless the user writes otherwise. */
  locale: Locale;
}) {
  const { t } = useI18n();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadedHistory, setLoadedHistory] = useState(false);
  const [lang, setLang] = useState("auto");
  const [listening, setListening] = useState(false);
  const [canSpeakOnDevice, setCanSpeakOnDevice] = useState(false);
  const [voiceMsg, setVoiceMsg] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listenRef = useRef<ListenSession | null>(null);

  // Voice-first, on the user's own device: no key, no upload, no round trip.
  useEffect(() => {
    setCanSpeakOnDevice(speechSupport().recognition);
  }, []);

  // Restore the language choice.
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(LANG_KEY);
      if (saved === "hi" || saved === "en" || saved === "auto") setLang(saved);
    } catch {
      /* noop */
    }
  }, []);

  const changeLang = (value: string) => {
    setLang(value);
    try {
      window.localStorage.setItem(LANG_KEY, value);
    } catch {
      /* noop */
    }
  };

  // Seed the reply language from the site language the first time, so a user
  // browsing in Hindi gets Hindi answers without touching this toggle.
  const seededLocale = useRef(false);
  useEffect(() => {
    if (seededLocale.current) return;
    try {
      const saved = window.localStorage.getItem(LANG_KEY);
      if (!saved) {
        setLang(locale);
        window.localStorage.setItem(LANG_KEY, locale);
      }
    } catch {
      /* noop */
    }
    seededLocale.current = true;
  }, [locale]);

  // Restore remembered chat for this session (chat memory).
  useEffect(() => {
    if (!sessionId || loadedHistory) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/chat/history?session_id=${encodeURIComponent(sessionId)}`);
        if (res.ok) {
          const body = await res.json();
          const hist = (body?.messages ?? []) as ChatMessage[];
          if (!cancelled && Array.isArray(hist) && hist.length) setMessages(hist);
        }
      } catch {
        /* keep local greeting */
      } finally {
        if (!cancelled) setLoadedHistory(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, loadedHistory]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isLoading]);

  const send = useCallback(
    async (preset?: string) => {
      const text = (preset ?? input).trim();
      if (!text || isLoading) return;
      setInput("");
      setMessages((prev) => [...prev, { role: "user", content: text }]);
      setIsLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, session_id: sessionId, topic, lang, intake }),
        });
        const body = await res.json();
        const reply =
          typeof body?.reply === "string" && body.reply.trim()
            ? body.reply
            : t("chat.failed");
        setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: t("chat.offline"),
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [input, isLoading, sessionId, topic, lang, intake, t]
  );

  const clearChat = useCallback(async () => {
    setMessages([]);
    if (sessionId) {
      try {
        await fetch(`${API_BASE}/api/chat/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
      } catch {
        /* local-only clear is still fine */
      }
    }
    inputRef.current?.focus();
  }, [sessionId]);

  // Speak the question instead of typing it — the transcript goes straight in
  // and is sent, because the whole point is not having to read or write.
  const startVoice = useCallback(() => {
    if (listening || isLoading) return;
    setVoiceMsg("");
    const session = startListening({
      locale,
      onInterim: (text) => setInput(text),
      onResult: (text) => {
        setInput("");
        void send(text);
      },
      onError: (code) => {
        const blocked = code === "not-allowed" || code === "service-not-allowed";
        setVoiceMsg(blocked ? t("chat.micDenied") : t("chat.micUnheard"));
        setTimeout(() => setVoiceMsg(""), 4000);
      },
      onEnd: () => {
        listenRef.current = null;
        setListening(false);
      },
    });
    if (!session) {
      setVoiceMsg(t("chat.micUnheard"));
      setTimeout(() => setVoiceMsg(""), 4000);
      return;
    }
    listenRef.current = session;
    setListening(true);
  }, [listening, isLoading, locale, send, t]);

  const stopVoice = useCallback(() => {
    listenRef.current?.stop();
  }, []);

  const intakeSummary = buildIntakeSummary(intake);
  const intakeMissing = describeMissingIntake(intake);

  const displayMessages: ChatMessage[] =
    messages.length === 0 && !isLoading
      ? [{ role: "assistant", content: welcome(topic, intake, t) }]
      : messages;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        marginTop: "16px",
        width: "100%",
        maxWidth: "760px",
        padding: "20px clamp(16px, 5vw, 24px)",
        background: "rgba(45,212,191,0.05)",
        border: "1px solid rgba(45,212,191,0.22)",
        borderRadius: "var(--radius-xl)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "14px" }}>
        <div
          style={{
            width: "40px",
            height: "40px",
            borderRadius: "20px",
            background: "linear-gradient(135deg,#2dd4bf,#0d9488)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Bot size={20} color="#fff" />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-primary)" }}>
            {t("chat.title")}
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            {topic.trim()
              ? intakeSummary
                ? t("chat.subReportIntake", { topic, intake: intakeSummary })
                : t("chat.subReport", { topic, extra: "" })
              : intakeSummary
                ? t("chat.subIntake", { intake: intakeSummary })
                : sessionId
                  ? t("chat.subMemory")
                  : t("chat.subNoMemory")}
          </div>
        </div>
        {/* Language toggle */}
        <div
          style={{
            display: "flex",
            gap: "2px",
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: "10px",
            padding: "3px",
          }}
        >
          {LANGS.map((l) => (
            <button
              key={l.value}
              type="button"
              onClick={() => changeLang(l.value)}
              title={l.value === "hi" ? "हिंदी में जवाब पाएँ" : l.label}
              style={{
                border: "none",
                background: lang === l.value ? "rgba(45,212,191,0.18)" : "transparent",
                color: lang === l.value ? "var(--accent)" : "var(--text-muted)",
                fontSize: "0.7rem",
                fontWeight: 700,
                padding: "4px 10px",
                borderRadius: "7px",
                cursor: "pointer",
              }}
            >
              {l.label}
            </button>
          ))}
        </div>
        {sessionId && (
          <button
            type="button"
            onClick={clearChat}
            title={t("chat.clear")}
            style={{
              border: "1px solid rgba(255,255,255,0.15)",
              background: "rgba(255,255,255,0.06)",
              borderRadius: "10px",
              padding: "8px",
              cursor: "pointer",
              color: "var(--text-muted)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>

      {/* Personalised context badge */}
      {(topic.trim() || intakeSummary) && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            marginBottom: "10px",
            padding: "6px 12px",
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "999px",
            alignSelf: "flex-start",
            maxWidth: "100%",
          }}
        >
          <Sparkles size={12} color="var(--accent)" style={{ flexShrink: 0 }} />
          <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)" }}>
            {topic.trim()
              ? t("chat.badgeReport", { topic })
              : t("chat.badgeIntake")}
          </span>
        </div>
      )}

      {/* What Saathi still needs — the same gap list the backend asks from */}
      {intakeMissing && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            marginBottom: "10px",
            padding: "6px 12px",
            background: "rgba(251,146,60,0.08)",
            border: "1px solid rgba(251,146,60,0.25)",
            borderRadius: "999px",
            alignSelf: "flex-start",
            maxWidth: "100%",
          }}
        >
          <CircleHelp size={12} color="var(--warn)" style={{ flexShrink: 0 }} />
          <span style={{ fontSize: "0.72rem", color: "var(--warn)" }}>
            {t("chat.missing", { list: intakeMissing })}
          </span>
        </div>
      )}

      {/* Messages */}
      <div
        style={{
          minHeight: "200px",
          maxHeight: "380px",
          overflowY: "auto",
          padding: "4px 2px",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
        }}
      >
        <AnimatePresence initial={false}>
          {displayMessages.map((m, i) => (
            <motion.div
              key={`${i}-${m.content.slice(0, 8)}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              style={{
                alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "86%",
                display: "flex",
                gap: "8px",
                alignItems: "flex-start",
              }}
            >
              {m.role === "assistant" && (
                <div
                  style={{
                    width: "26px",
                    height: "26px",
                    borderRadius: "13px",
                    background: "rgba(45,212,191,0.15)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    marginTop: "2px",
                  }}
                >
                  <Bot size={14} color="var(--accent)" />
                </div>
              )}
              <div
                style={{
                  padding: "10px 14px",
                  borderRadius:
                    m.role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                  fontSize: "0.84rem",
                  lineHeight: 1.55,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  color:
                    m.role === "user" ? "#fff" : "var(--text-primary)",
                  background:
                    m.role === "user"
                      ? "linear-gradient(135deg, var(--accent), #0d9488)"
                      : "rgba(255,255,255,0.06)",
                  border:
                    m.role === "assistant" ? "1px solid rgba(255,255,255,0.08)" : "none",
                }}
              >
                {m.content}
              </div>
            </motion.div>
          ))}
          {isLoading && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{ alignSelf: "flex-start", display: "flex", gap: "8px", alignItems: "center", padding: "6px 4px" }}
            >
              <div
                style={{
                  width: "26px",
                  height: "26px",
                  borderRadius: "13px",
                  background: "rgba(45,212,191,0.15)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Bot size={14} color="var(--accent)" />
              </div>
              <Loader2 size={14} className="spin" style={{ color: "var(--text-muted)" }} />
            </motion.div>
          )}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>

      {/* Quick prompts — tap to ask */}
      {messages.length === 0 && !isLoading && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "8px",
            marginTop: "12px",
          }}
        >
          {QUICK_PROMPTS.map((q) => {
            const Icon = q.icon;
            return (
              <motion.button
                key={q.label}
                type="button"
                whileTap={{ scale: 0.96 }}
                onClick={() => send(t(q.key))}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "7px 12px",
                  background: "rgba(255,255,255,0.05)",
                  border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: "999px",
                  fontSize: "0.74rem",
                  fontWeight: 600,
                  color: "var(--text-secondary)",
                  cursor: "pointer",
                }}
              >
                <Icon size={13} color="var(--accent)" />
                {t(q.key)}
              </motion.button>
            );
          })}
        </div>
      )}

      {/* Input */}
      <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send();
          }}
          placeholder={t("chat.placeholder")}
          aria-label={t("chat.title")}
          style={{
            flex: 1,
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: "12px",
            padding: "10px 14px",
            fontSize: "0.84rem",
            color: "var(--text-primary)",
            outline: "none",
          }}
        />
        {canSpeakOnDevice && (
          <button
            type="button"
            onClick={listening ? stopVoice : startVoice}
            disabled={isLoading}
            title={listening ? t("chat.micStop") : t("chat.mic")}
            aria-label={listening ? t("chat.micStop") : t("chat.mic")}
            aria-pressed={listening}
            style={{
              border: `1px solid ${listening ? "rgba(248,113,113,0.5)" : "rgba(255,255,255,0.12)"}`,
              background: listening ? "rgba(248,113,113,0.15)" : "rgba(255,255,255,0.06)",
              color: listening ? "var(--error)" : "var(--text-secondary)",
              borderRadius: "12px",
              padding: "0 12px",
              cursor: isLoading ? "not-allowed" : "pointer",
              opacity: isLoading ? 0.5 : 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {listening ? <MicOff size={16} /> : <Mic size={16} />}
          </button>
        )}
        <button
          type="button"
          onClick={() => send()}
          disabled={isLoading || !input.trim()}
          title={t("chat.send")}
          style={{
            border: "none",
            background: "linear-gradient(135deg,#2dd4bf,#0d9488)",
            color: "#fff",
            borderRadius: "12px",
            padding: "0 16px",
            cursor: isLoading || !input.trim() ? "not-allowed" : "pointer",
            opacity: isLoading || !input.trim() ? 0.5 : 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Send size={16} />
        </button>
      </div>
      {(listening || voiceMsg) && (
        <div style={{ marginTop: "8px", display: "flex", gap: "6px", alignItems: "center" }}>
          {listening ? (
            <Mic size={12} color="var(--error)" aria-hidden="true" />
          ) : (
            <CircleHelp size={12} color="var(--warn)" aria-hidden="true" />
          )}
          <span style={{ fontSize: "0.7rem", color: listening ? "var(--error)" : "var(--warn)" }}>
            {listening ? t("chat.listening") : voiceMsg}
          </span>
        </div>
      )}
      {messages.length === 0 && !isLoading && (
        <div style={{ marginTop: "10px", display: "flex", gap: "6px", alignItems: "center" }}>
          <User size={12} color="var(--text-muted)" />
          <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
            {t("chat.tip")}
          </span>
        </div>
      )}
    </motion.div>
  );
}