"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bot, Loader2, Send, Trash2, User } from "lucide-react";

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_BASE =
  typeof window !== "undefined" &&
  window.location.protocol === "https:" &&
  rawApiBase.startsWith("http://")
    ? rawApiBase.replace("http://", "https://")
    : rawApiBase;

type ChatMessage = { role: "user" | "assistant"; content: string };

const LANG_KEY = "grameenai_chat_lang";
const LANGS = [
  { value: "auto", label: "Auto" },
  { value: "hi", label: "हिंदी" },
  { value: "en", label: "EN" },
];

const WELCOME: ChatMessage = {
  role: "assistant",
  content:
    "Hi, I'm your business advisor. Ask me how to build your business, which loan scheme fits you, what documents to carry, or anything to get you loan-ready.",
};

export default function ChatPanel({
  sessionId,
  topic,
}: {
  sessionId: string;
  topic: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [loadedHistory, setLoadedHistory] = useState(false);
  const [lang, setLang] = useState("auto");
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

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

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId, topic, lang }),
      });
      const body = await res.json();
      const reply =
        typeof body?.reply === "string" && body.reply.trim()
          ? body.reply
          : "I couldn't answer that right now. Please rephrase and try again.";
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "I couldn't reach the backend. Make sure the server is running on port 8000 and try again.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, sessionId, topic, lang]);

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

  const displayMessages: ChatMessage[] =
    messages.length === 0 && !isLoading
      ? [WELCOME]
      : messages;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        marginTop: "16px",
        width: "100%",
        maxWidth: "760px",
        padding: "20px 24px",
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
            Business Advisor Chat
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            {sessionId ? "Remembers this conversation — ask follow-ups freely." : "Chatting without saved memory."}
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
            title="Clear chat memory"
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

      {/* Input */}
      <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send();
          }}
          placeholder={lang === "hi" ? "बिज़नेस या कर्ज़ के बारे में हिंदी में पूछें…" : "Ask anything about your business or loan…"}
          aria-label="Chat message"
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
        <button
          type="button"
          onClick={send}
          disabled={isLoading || !input.trim()}
          title="Send"
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
      {messages.length === 0 && !isLoading && (
        <div style={{ marginTop: "10px", display: "flex", gap: "6px", alignItems: "center" }}>
          <User size={12} color="var(--text-muted)" />
          <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
            Tip: run a research above first — the advisor then remembers your actual business. हिंदी में भी लिख सकते हैं।
          </span>
        </div>
      )}
    </motion.div>
  );
}