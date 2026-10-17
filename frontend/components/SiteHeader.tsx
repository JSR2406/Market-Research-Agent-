"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Search, MessageSquare, FileText, Home, Handshake, Menu, X, History, FileSpreadsheet, ListChecks } from "lucide-react";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { useI18n } from "@/lib/i18n";

const NAV_ITEMS = [
  { href: "/", labelKey: "nav.home", icon: Home },
  { href: "/research", labelKey: "nav.research", icon: Search },
  { href: "/advisor", labelKey: "nav.advisor", icon: MessageSquare },
  { href: "/schemes", labelKey: "nav.schemes", icon: FileText },
  { href: "/dpr", labelKey: "nav.dpr", icon: FileSpreadsheet },
  { href: "/tracker", labelKey: "nav.tracker", icon: ListChecks },
  { href: "/history", labelKey: "nav.history", icon: History },
] as const;

/**
 * Site-wide navigation: one header for every route so the product reads as a
 * single place rather than four unrelated screens. Reuses the same language
 * control (`LanguageSwitcher`) as the research page.
 */
export function SiteHeader() {
  const { t } = useI18n();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        width: "100%",
        background: "rgba(13,13,16,0.82)",
        backdropFilter: "blur(10px)",
        WebkitBackdropFilter: "blur(10px)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <nav
        aria-label={t("nav.aria")}
        style={{
          width: "100%",
          maxWidth: "1080px",
          marginInline: "auto",
          padding: "0 clamp(12px, 4vw, 20px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
          minHeight: "62px",
        }}
      >
        {/* Brand */}
        <Link
          href="/"
          aria-label={t("brand.name")}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "9px",
            textDecoration: "none",
            color: "var(--text-primary)",
            minWidth: 0,
          }}
        >
          <span
            aria-hidden="true"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "32px",
              height: "32px",
              borderRadius: "10px",
              background: "linear-gradient(135deg, var(--accent), #9b87f5)",
              flexShrink: 0,
            }}
          >
            <Handshake size={18} color="#fff" />
          </span>
          <span
            style={{
              fontWeight: 700,
              fontSize: "0.95rem",
              letterSpacing: "-0.01em",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {t("brand.name")}
          </span>
        </Link>

        {/* Desktop nav */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
          }}
          className="site-nav-desktop"
        >
          {NAV_ITEMS.map(({ href, labelKey, icon: Icon }) => {
            const active = isActive(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "7px 12px",
                  borderRadius: "999px",
                  textDecoration: "none",
                  fontSize: "0.84rem",
                  fontWeight: 600,
                  color: active ? "var(--accent)" : "var(--text-secondary)",
                  background: active ? "var(--accent-glow)" : "transparent",
                  transition: "color 0.15s, background 0.15s",
                }}
              >
                <Icon size={15} aria-hidden="true" />
                <span>{t(labelKey)}</span>
              </Link>
            );
          })}
          <div style={{ marginLeft: "6px" }}>
            <LanguageSwitcher compact />
          </div>
        </div>

        {/* Mobile toggle */}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="site-mobile-menu"
          aria-label={open ? t("nav.closeMenu") : t("nav.openMenu")}
          style={{
            display: "none",
            alignItems: "center",
            justifyContent: "center",
            padding: "8px",
            background: "transparent",
            border: "1px solid var(--border)",
            borderRadius: "10px",
            color: "var(--text-secondary)",
            cursor: "pointer",
          }}
          className="site-nav-toggle"
        >
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </nav>

      {/* Mobile menu */}
      <AnimatePresence>
        {open && (
          <motion.div
            id="site-mobile-menu"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: "hidden", borderTop: "1px solid var(--border)" }}
            className="site-nav-mobile"
          >
            <div
              style={{
                maxWidth: "1080px",
                marginInline: "auto",
                padding: "12px clamp(12px, 4vw, 20px) 18px",
                display: "flex",
                flexDirection: "column",
                gap: "6px",
              }}
            >
              {NAV_ITEMS.map(({ href, labelKey, icon: Icon }) => {
                const active = isActive(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setOpen(false)}
                    aria-current={active ? "page" : undefined}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      padding: "11px 12px",
                      borderRadius: "10px",
                      textDecoration: "none",
                      fontSize: "0.95rem",
                      fontWeight: 600,
                      color: active ? "var(--accent)" : "var(--text-secondary)",
                      background: active ? "var(--accent-glow)" : "transparent",
                    }}
                  >
                    <Icon size={18} aria-hidden="true" />
                    <span>{t(labelKey)}</span>
                  </Link>
                );
              })}
              <div style={{ marginTop: "8px", display: "flex" }}>
                <LanguageSwitcher compact />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
