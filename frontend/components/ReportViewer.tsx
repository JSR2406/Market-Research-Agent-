"use client";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Download, FileText, BookOpen, Share2, CheckCircle2 } from "lucide-react";
import { useState } from "react";

interface Props {
  report: string;
  topic: string;
}

export default function ReportViewer({ report, topic }: Props) {
  const [copied, setCopied] = useState(false);
  const download = () => {
    const blob = new Blob([report], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${topic.slice(0, 50).replace(/\s+/g, "-").toLowerCase()}-report.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyMarkdown = async () => {
    try {
      await navigator.clipboard.writeText(report);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  const wordCount = report.split(/\s+/).filter(Boolean).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 40 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      style={{
        width: "100%",
        maxWidth: "760px",
        margin: "20px auto 80px",
        background: "var(--bg-card)",
        borderRadius: "var(--radius-xl)",
        border: "1px solid var(--border-bright)",
        boxShadow: "0 32px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(79,142,247,0.08)",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "18px 24px",
          borderBottom: "1px solid var(--border)",
          background: "linear-gradient(135deg, rgba(79,142,247,0.06) 0%, rgba(139,92,246,0.04) 100%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "8px",
              background: "linear-gradient(135deg, var(--accent), var(--accent2))",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <BookOpen size={16} color="#fff" />
          </div>
          <div>
            <p style={{ fontSize: "0.88rem", fontWeight: 700, color: "var(--text-primary)" }}>
              Final Research Report
            </p>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
              ~{wordCount.toLocaleString()} words · Markdown
            </p>
          </div>
        </div>

        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={copyMarkdown}
            title="Copy Markdown"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "0.78rem",
              color: "var(--text-secondary)",
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              padding: "7px 12px",
              cursor: "pointer",
              transition: "all 0.15s",
              fontFamily: "inherit",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = "var(--accent)";
              e.currentTarget.style.color = "var(--accent)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = "var(--border)";
              e.currentTarget.style.color = "var(--text-secondary)";
            }}
          >
            {copied ? (
              <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }}>
                <CheckCircle2 size={12} color="var(--success)" />
              </motion.div>
            ) : (
              <Share2 size={12} />
            )}
            {copied ? "Copied!" : "Copy"}
          </button>
          <button
            onClick={download}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "0.78rem",
              color: "#fff",
              background: "linear-gradient(135deg, var(--accent), var(--accent2))",
              border: "none",
              borderRadius: "var(--radius-sm)",
              padding: "7px 14px",
              cursor: "pointer",
              fontWeight: 600,
              boxShadow: "0 4px 12px rgba(79,142,247,0.3)",
              fontFamily: "inherit",
            }}
          >
            <Download size={12} /> Download .md
          </button>
        </div>
      </div>

      {/* Topic pill */}
      <div style={{ padding: "14px 24px 0" }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            background: "rgba(79,142,247,0.08)",
            border: "1px solid rgba(79,142,247,0.2)",
            borderRadius: "20px",
            padding: "4px 12px",
            fontSize: "0.76rem",
            color: "var(--accent)",
          }}
        >
          <FileText size={11} />
          {topic}
        </div>
      </div>

      {/* Markdown body */}
      <div style={{ padding: "20px 28px 32px" }}>
        <div className="prose">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{report}</ReactMarkdown>
        </div>
      </div>
    </motion.div>
  );
}
