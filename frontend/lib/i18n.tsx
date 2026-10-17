"use client";
/**
 * i18n.tsx — site-wide language layer.
 *
 * Every user-facing string in the app resolves through `t()`. Nothing is
 * hardcoded in JSX, so switching the language switches the *whole* site: hero,
 * check-up, timeline, verdicts, ledger, simulator, chat and voice panel.
 *
 * Two decisions worth knowing:
 *
 * 1. **Product nouns stay in English.** Udyam, MUDRA, PMEGP, CGTMSE, PM
 *    SVANidhi and GST are official terms users must recognise on a bank form,
 *    so they are never translated — only the sentence around them is.
 * 2. **Hindi is plain, not literary.** The audience is first-time
 *    micro-entrepreneurs; the wording is short, spoken-style Hindi, not the
 *    kind written for paperwork.
 *
 * Adding a language is one entry in DICT plus one line in LOCALES — no
 * component changes. A missing key falls back to English rather than showing
 * a raw key, so a half-finished translation degrades gracefully.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Locale = "en" | "hi";

export const LOCALES: { code: Locale; label: string; native: string }[] = [
  { code: "en", label: "English", native: "English" },
  { code: "hi", label: "Hindi", native: "हिंदी" },
];

const STORAGE_KEY = "grameenai_locale";

/** Flat dotted keys → copy. English is the source of truth. */
const EN: Record<string, string> = {
  // ── nav ───────────────────────────────────────────────────────────────────
  "nav.home": "Home",
  "nav.research": "Research",
  "nav.advisor": "Advisor",
  "nav.schemes": "Schemes",
  "nav.dpr": "Report",
  "nav.tracker": "Tracker",
  "nav.history": "History",
  "nav.aria": "Main navigation",
  "nav.openMenu": "Open menu",
  "nav.closeMenu": "Close menu",

  // ── brand / hero ────────────────────────────────────────────────────────
  "brand.name": "Your AI Business Saathi",
  "brand.tagline": "Market research, growth planning & schemes for small businesses",
  "hero.kicker":
    "Market research, growth planning & government schemes for small businesses",
  "hero.sub":
    "Describe your business in plain language — get live market research, a clear business road-map, matched government schemes, and a loan-readiness checklist in under 60 seconds.",

  // ── landing page ──────────────────────────────────────────────────────────
  "landing.hero.badge": "New: Offline mode + Hindi support",
  "landing.hero.title": "Your AI Business Saathi — Market research, growth planning & schemes for small businesses",
  "landing.hero.subtitle": "Describe your business in plain language. Get live market research, a clear roadmap, matched government schemes, and a loan-readiness checklist — all in under 60 seconds.",
  "landing.hero.cta": "Start Research",
  "landing.hero.ctaSecondary": "Browse Schemes",
  "landing.hero.trust": "No signup required · Works offline · Export or delete your session anytime",

  "landing.stats.1": "Businesses helped",
  "landing.stats.2": "Curated schemes",
  "landing.stats.3": "Typical research time",
  "landing.stats.4": "Free & open source",

  "landing.features.title": "Built for small businesses",
  "landing.features.subtitle": "Not a generic chatbot — Saathi is specialised for Indian micro-entrepreneurs",

  "landing.features.1.title": "Business-first advice",
  "landing.features.1.desc": "Saathi helps you build your business — pricing, costs, cash flow, customers, registration — not just answer questions.",

  "landing.features.2.title": "Live market research",
  "landing.features.2.desc": "Web-sourced facts, not memorised answers — the sources are listed so you can verify them yourself.",

  "landing.features.3.title": "Your Indian schemes",
  "landing.features.3.desc": "MUDRA, PMEGP, CGTMSE, PM SVANidhi — matched to your business type, business stage and loan size automatically.",

  "landing.features.4.title": "Loan-readiness checklist",
  "landing.features.4.desc": "A clear action ledger shows exactly what to do before you walk into a bank branch.",

  "landing.features.5.title": "Works offline",
  "landing.features.5.desc": "Free local AI models (Ollama) and an offline fallback keep Saathi answering even without internet. No subscription, no API keys.",

  "landing.features.6.title": "Your data, your control",
  "landing.features.6.desc": "Your session lives behind an anonymous ID on our server — export it or delete everything anytime. Auto-deleted after 7 days.",

  "landing.cta.title": "Ready to understand your business better?",
  "landing.cta.subtitle": "Start your free research in seconds. No signup, no credit card.",
  "landing.cta.button": "Start Research",

  "landing.footer.desc": "Specialised business advisory for Indian micro-entrepreneurs. Market research, scheme matching, and loan-readiness — all in one place.",
  "landing.footer.links": "Quick Links",
  "landing.footer.legal": "Legal",
  "landing.footer.privacy": "Privacy Policy",
  "landing.footer.terms": "Terms of Service",
  "landing.footer.contact": "Contact Us",
  "landing.footer.copyright": "© 2024 Your AI Business Saathi. All rights reserved.",

  // ── business check-up ───────────────────────────────────────────────────
  "quiz.title": "Business Check-up",
  "quiz.optional": "(optional)",
  "quiz.sub0": "A few quick questions, or type your own answers — Saathi asks the rest.",
  "quiz.subDone": "All {total} answered — your Saathi now knows your business.",
  "quiz.subPartial": "{answered}/{total} answered — Saathi will ask you about the rest.",
  "quiz.questionOf": "Question {n} of {total}",
  "quiz.typeOwn": "Or type your own answer",
  "quiz.yourAnswer": "Your answer",
  "quiz.back": "Back",
  "quiz.skip": "Skip",
  "quiz.allAnswered": "All {total} answered",
  "quiz.saveAnswer": "Save this answer and continue",
  "quiz.clearAnswer": "Clear this answer",
  "quiz.reset": "Reset check-up answers",
  "quiz.saveNext": "Tap when you have done this",
  "quiz.knownBefore": "We already know this from your answers",
  "quiz.askRest": "Your Saathi will ask you about the rest in chat: {list}.",
  "quiz.allSet": "Your Saathi has everything it needs — it will use these answers everywhere.",
  "quiz.staysLocal": "Your answers are used only for your own research — export or delete them anytime.",
  "quiz.liveTitle": "Your business type: {label}",
  "quiz.openForYou": "Open for you: {list}",
  "quiz.filledIn": "Details filled in: {pct}%",

  // ── benefit calculator (WS-3) ───────────────────────────────────────────
  "benefits.title": "What you could get (estimate)",
  "benefits.costLabel": "Your project cost (₹)",
  "benefits.costHint": "Enter your project cost to see the subsidy in rupees",
  "benefits.subsidy": "You may not have to repay",
  "benefits.credit": "Loans you match (ceiling)",
  "benefits.none": "No grant or subsidy scheme matched yet",
  "benefits.showAll": "Show all {count} matched schemes",
  "benefits.showLess": "Show fewer",
  "benefits.loading": "Calculating…",
  "benefits.disclaimerLabel": "Please note",
  "benefits.source": "Source",

  // ── document checklist (WS-4) ───────────────────────────────────────────
  "docs.title": "Documents to keep ready",
  "docs.print": "Print / Save as PDF",
  "docs.copyWhatsapp": "Copy for WhatsApp",
  "docs.copied": "Copied",
  "docs.generatedOn": "Generated {date}",
  "docs.loading": "Loading…",

  // ── Detailed Project Report (WS-5) ──────────────────────────────────────
  "dpr.title": "Bank-ready project report",
  "dpr.subtitle": "A Detailed Project Report (DPR) built from your own answers — the file a bank reads before sanctioning a loan. Every figure is computed from your numbers and printed with its source.",
  "dpr.needProfile": "First tell us about your business in the Business Check-up. Your answers fill the report automatically.",
  "dpr.goToCheckup": "Start the Business Check-up",
  "dpr.scheme": "Scheme to apply under",
  "dpr.cost": "Project cost (₹)",
  "dpr.sales": "Monthly sales (₹)",
  "dpr.expenses": "Monthly expenses (₹)",
  "dpr.optional": "optional",
  "dpr.optionalHint": "Fill the cost and sales figures to get real projections. Leave them empty and the report explains what is still needed instead of guessing.",
  "dpr.generate": "Build the report",
  "dpr.generating": "Building…",
  "dpr.download": "Download PDF",
  "dpr.failed": "Could not build the report just now. Please try again.",
  "dpr.source": "Scheme source",
  "dpr.pdfNote": "The PDF is in English — banks read English files.",
  "dpr.assumptions": "Assumptions used",
  "dpr.cta": "Build a bank-ready report",
  "dpr.noSchemes": "No scheme matched your check-up answers yet. Answer a few more Business Check-up questions and options will appear here.",

  // ── application tracker (WS-6) ──────────────────────────────────────────
  "tracker.title": "Application tracker",
  "tracker.subtitle": "Move each application from planning to approved and watch the windows that are closing. Deadlines come from each scheme's own documents.",
  "tracker.matchedHint": "These schemes match your business",
  "tracker.addTitle": "Add a scheme to track",
  "tracker.choose": "Choose a scheme",
  "tracker.add": "Add",
  "tracker.addAll": "Add every matched scheme",
  "tracker.tracking": "Tracking",
  "tracker.empty": "Nothing here yet. Add a scheme you are applying for, then move it forward as you go.",
  "tracker.stageHint": "Use the arrows on a card to move it along.",
  "tracker.moveNext": "Move forward",
  "tracker.moveNextAria": "Move {name} to the next stage",
  "tracker.movePrev": "Move back",
  "tracker.movePrevAria": "Move {name} to the previous stage",
  "tracker.markRejected": "Not approved",
  "tracker.markRejectedAria": "Mark {name} as not approved",
  "tracker.remove": "Remove",
  "tracker.removeAria": "Remove {name} from the tracker",
  "tracker.target": "Your target date",
  "tracker.targetAria": "Target date for {name}",
  "tracker.targetHint": "Optional. This is your own date, not the scheme's.",
  "tracker.notes": "Notes",
  "tracker.notesPlaceholder": "What is still missing?",
  "tracker.notesAria": "Notes for {name}",
  "tracker.stage.planning": "Planning",
  "tracker.stage.docs_ready": "Documents ready",
  "tracker.stage.submitted": "Submitted",
  "tracker.stage.approved": "Approved",
  "tracker.stage.rejected": "Not approved",
  "tracker.deadlines": "Upcoming deadlines",
  "tracker.noDeadlines": "No dated window to show. The schemes you are tracking accept applications continuously.",
  "tracker.daysLeft": "{days} days left",
  "tracker.dueToday": "Last day today",
  "tracker.overdueBy": "Ended {days} days ago",
  "tracker.state.closing_soon": "Closing soon",
  "tracker.state.open": "Open",
  "tracker.state.lapsed": "Window over",
  "tracker.state.lapsed_pending": "Awaiting confirmation",
  "tracker.state.rolling": "No closing date published",
  "tracker.yours": "Your date",
  "tracker.source": "Source",
  "tracker.verified": "checked {date}",
  "tracker.alertsTitle": "Deadline alerts",
  "tracker.alertsSubtitle": "Tell us how to reach you and we will prepare a message when a window is closing or a scheme changes.",
  "tracker.channel": "How should we reach you?",
  "tracker.channelNone": "Not now",
  "tracker.channelEmail": "Email",
  "tracker.saveAlerts": "Save alerts",
  "tracker.contact": "Phone or email",
  "tracker.contactPhoneHint": "Country code + number, digits only (e.g. 919876543210)",
  "tracker.contactEmailHint": "you@example.com",
  "tracker.events": "Alert me about",
  "tracker.event.deadline_soon": "A closing window",
  "tracker.event.new_match": "A newly matched scheme",
  "tracker.event.reverified": "A scheme whose rules we re-checked",
  "tracker.consent": "I agree to be contacted about these alerts.",
  "tracker.preview": "What we would send you",
  "tracker.alertsNote": "Alerts are prepared here. Messages are sent on WhatsApp or email once that channel is connected - until then you will see them on this page.",
  "tracker.noAlerts": "Good news - nothing needs your attention today.",
  "tracker.privacy": "Your tracker is kept under your session id. Delete the session from History to erase it.",
  "tracker.saveFailed": "We could not save to the server just now. Your list is kept in this browser.",
  "tracker.saved": "Saved",
  "tracker.saving": "Saving",
  "tracker.cta": "Track your applications",
  "tracker.loading": "Loading",
  "tracker.invalidContact": "Check the phone number or email address you entered.",
  "tracker.needContact": "Add a phone number or email address to switch alerts on.",
  "tracker.needConsent": "Please agree to be contacted before we save alerts.",

  // ── topic input ─────────────────────────────────────────────────────────
  "input.placeholder":
    "Describe your business — what you sell, roughly how much you earn, and where you're located",
  "input.examples": "Quick examples",
  "input.example1": "Vegetable seller in rural Maharashtra, earning ₹15k/month",
  "input.example2": "Tailor in tier-2 city, ₹25k/month, needs sewing machine loan",
  "input.example3": "Small dairy farmer in Gujarat, 3 cows, ₹20k/month",
  "input.depth": "Research depth:",
  "input.steps": "steps",
  "input.start": "Start Research",
  "input.stop": "Stop Research",
  "mic.speak": "Speak your business description",
  "mic.stop": "Stop recording",
  "mic.record": "Record voice description",
  "mic.stopAria": "Stop voice recording",
  "mic.recording": "Recording — click the mic again to stop",
  "mic.transcribing": "Transcribing…",
  "mic.done": "Transcribed — review it and submit",
  "mic.unheard": "Could not understand audio — please type instead.",
  "mic.unavailable": "Voice unavailable right now — please type instead.",
  "mic.denied": "Microphone access denied — please type instead.",
  "voice.private": "Voice runs privately on the server — open-source engines, your recording never leaves it.",
  "voice.stt": "Speech-to-text",
  "voice.tts": "text-to-speech",
  "voice.cloud": "Voice is powered by ElevenLabs cloud for the best quality.",

  // ── usps ────────────────────────────────────────────────────────────────
  "usps.kicker": "Why Your AI Business Saathi",
  "usps.title": "Built for your business — not a generic chatbot.",
  "usps.sub":
    "ChatGPT answers general questions. Your AI Business Saathi builds, advises and gets your business loan-ready.",
  "usps.1.title": "Your Personal Business Advisor",
  "usps.1.text":
    "It reads your research and remembers the conversation — then answers follow-ups about YOUR business, not generic trivia.",
  "usps.2.title": "Real Market Research",
  "usps.2.text":
    "Lives on the web. It searches fresh, current facts about your industry instead of guessing from memory.",
  "usps.3.title": "Matched Indian Schemes",
  "usps.3.text":
    "MUDRA, PMEGP, CGTMSE, PM SVANidhi — matched to your business and stage by a rules engine, each scheme with its own source and verification date.",
  "usps.4.title": "Works Offline & Free",
  "usps.4.text":
    "Runs on free + local AI models. No subscription, no paywall — and it still answers even when the internet drops.",
  "usps.5.title": "Whole site in your language",
  "usps.5.text":
    "Switch the entire site to Hindi — check-up, verdicts, ledger, everything — and the advisor answers in the same language, even offline.",
  "usps.6.title": "Your Data Stays Yours",
  "usps.6.text":
    "One-tap export and a full delete for your session, auto-removed after 7 days (GDPR-aligned). Nothing is ever sold.",

  // ── session history ─────────────────────────────────────────────────────
  "history.title": "Your research history",
  "history.subtitle":
    "Every research run in this session is saved here, in real time. Open one to revisit its report.",
  "history.loading": "Loading your history…",
  "history.error": "Could not load your history.",
  "history.retry": "Retry",
  "history.empty": "No research saved yet. Run your first research and it will appear here.",
  "history.inProgress": "In progress…",
  "history.savedOn": "Saved",
  "history.topicFallback": "Untitled research",
  "history.loanReady": "Loan-ready",
  "history.viewReport": "View report",
  "history.hideReport": "Hide report",
  "history.export": "Export",
  "history.noReport": "No report was saved for this run.",
  "history.limited": "Showing your latest {n} runs.",
  "history.viewAll": "Open full history",
  "history.clearTitle": "Delete this session",
  "history.clearDesc": "Permanently remove this session's history and chat (GDPR right to delete).",
  "history.clear": "Delete session data",
  "history.clearDone": "Session data deleted.",
  "history.clearFailed": "Could not delete your session data. Please try again.",

  // ── timeline ────────────────────────────────────────────────────────────
  "timeline.title": "What Saathi is doing",
  "timeline.waiting": "Ready when you are.",
  "timeline.plan": "Plan",
  "timeline.working": "Working…",
  "timeline.agentsDone": "{done} of {total} steps done",
  "timeline.statusPlan": "{n} research steps",
  "timeline.statusDone": "done",
  "timeline.pass": "pass {n}",
  "timeline.tools": "Tools used",
  "timeline.thought": "Thought",
  "timeline.reflection": "Self-check",
  "timeline.engine": "engine",
  "timeline.connecting": "Connecting…",
  "timeline.running": "Running {label}…",
  "timeline.cancelled": "Research cancelled.",
  "timeline.complete": "Research complete.",
  "timeline.lost":
    "The connection dropped while your research was running. Please try again.",
  "timeline.retry": "Connection lost. Retrying ({n}/{max})…",
  "timeline.offline":
    "We couldn't reach your Business Saathi just now. Please check your internet connection and try again.",

  // ── report ──────────────────────────────────────────────────────────────
  "report.sources": "Sources",
  "report.summary": "Business Summary",
  "report.cashflow": "Cash-Flow Snapshot",
  "report.schemes": "Matched Government Schemes",
  "report.docs": "Checklist of Documents Needed",
  "report.next": "Next Step",
  "report.simple": "In Simple Words — Read Aloud Version",
  "report.copy": "Copy",
  "report.copied": "Copied!",
  "report.copyAria": "Copy advisory text",
  "report.download": "Download .txt",
  "report.downloadAria": "Download advisory as .txt",
  "report.listen": "Listen to Advisory",
  "report.listening": "Playing…",
  "report.stopAudio": "Stop audio",
  "report.audioFailed": "Audio playback failed.",
  "report.audioBusy": "Please wait — the previous clip is still playing.",
  "report.parseError": "We couldn't read that report. Please run the research again.",
  "report.score": "Loan-Ready Score",
  "report.schemeNote":
    "Confirm current terms at your bank or the official scheme portal — details change by state and lender.",

  // ── eligibility ─────────────────────────────────────────────────────────
  "elig.title": "What you can actually apply for",
  "elig.yourBusiness": "Your business: {label}",
  "elig.asking": "asking {amount}",
  "elig.subtitle":
    "Checked against the official scheme rules in code — not guessed. Tap a card to see the rule and the source.",
  "elig.tapRule": "Rule: {rule}",
  "elig.matchScore": "Match {score}%",
  "elig.tiers": "Loan tiers",
  "elig.documents": "Documents",
  "elig.collateral": "Collateral:",
  "elig.source": "Official source",
  "elig.verified": "verified {date}",
  "elig.use": "Use: {name}",
  "elig.status.eligible": "Eligible",
  "elig.status.likely": "Likely eligible",
  "elig.status.blocked": "Blocked",
  "elig.status.not_eligible": "Not eligible",
  "elig.status.wrong_tier": "Wrong loan tier",

  // ── ledger ──────────────────────────────────────────────────────────────
  "ledger.title": "Your action checklist",
  "ledger.doneOf": "{done} of {total} done",
  "ledger.scoreLine":
    "Your score is {score}/100{level} — tick what you have actually done and the score updates straight away.",
  "ledger.levelReady": " — ready to apply",
  "ledger.levelAlmost": " — almost there",
  "ledger.levelGetting": " — getting there",
  "ledger.levelEarly": " — early days",
  "ledger.doNext": "Do this next: {title}",
  "ledger.opensUp": "Opens up: {list}",
  "ledger.markComplete": "Mark complete: {title}",
  "ledger.markCompleted": "Completed: {title}",
  "ledger.undo": "Tap to undo",
  "ledger.saveError": "We couldn't save that just now. Please try again.",
  "ledger.local": "Nothing here is shared anywhere.",

  // ── cash-flow simulator ─────────────────────────────────────────────────
  "cash.title": "Cash-Flow Simulator",
  "cash.sub": "Guess your numbers — see if the business survives and when it breaks even. No internet needed.",
  "cash.capital": "Starting capital (₹)",
  "cash.sales": "Weekly sales (₹)",
  "cash.expenses": "Weekly expenses (₹)",
  "cash.weeks": "Weeks to project",
  "cash.chartAria": "Projected cash balance over weeks",
  "cash.surplus": "Monthly surplus",
  "cash.breakeven": "Break-even",
  "cash.weekN": "Week {n}",
  "cash.never": "Not happening",
  "cash.immediate": "Immediate",
  "cash.balance": "Balance after {n} weeks",
  "cash.warn":
    "This projection is based on the numbers you entered. Treat it as a rough guide, not a forecast.",
  "cash.warnNegative":
    "Expenses are above sales — cash is draining every week. Cut costs or grow sales before applying for a loan.",
  "cash.foot":
    "Bankers like a consistent positive surplus — it proves the loan can be repaid.",

  // ── live market check ───────────────────────────────────────────────────
  "market.title": "Check today's market",
  "market.sub": "Published prices and lookups, always shown with the date they belong to. Nothing here is estimated.",
  "market.kind.mandi": "Mandi price",
  "market.kind.pincode": "Pincode",
  "market.kind.ifsc": "Bank branch (IFSC)",
  "market.crop.onion": "Onion",
  "market.crop.potato": "Potato",
  "market.crop.tomato": "Tomato",
  "market.crop.wheat": "Wheat",
  "market.crop.paddy": "Paddy",
  "market.crop.cotton": "Cotton",
  "market.ph.commodity": "Crop — e.g. Onion",
  "market.ph.market": "Mandi or market (optional)",
  "market.ph.state": "State (optional)",
  "market.ph.pincode": "6-digit pincode",
  "market.ph.ifsc": "IFSC — e.g. HDFC0001234",
  "market.check": "Check",
  "market.modal": "per quintal",
  "market.range": "Range {min} to {max}",
  "market.delivery": "Delivery",
  "market.badge.live": "Live",
  "market.badge.stale": "Not live",
  "market.badge.off": "No live data",
  "market.badge.undated": "Live, undated",
  "market.offline": "Live data could not be reached just now. Please try again in a few minutes.",
  "market.more": "{n} more rows on the official portal.",
  "market.official": "Official portal",
  "market.source": "Source",

  // ── advisor chat ────────────────────────────────────────────────────────
  "chat.title": "Your Personal Business Advisor",
  "chat.subReport": "Knows your “{topic}” business — follow-ups come straight from your report.",
  "chat.subReportIntake":
    "Knows your “{topic}” business and your Business Check-up answers ({intake}) — follow-ups come straight from your report.",
  "chat.subIntake": "Knows your Business Check-up answers ({intake}) — ask follow-ups about your plan anytime.",
  "chat.subMemory": "Remembers this conversation — run a research above and I'll learn your business.",
  "chat.subNoMemory": "Chatting without saved memory.",
  "chat.badgeReport":
    "Personalised for your “{topic}” business — answers are grounded in your report, not generic advice.",
  "chat.badgeIntake":
    "Personalised from your Business Check-up answers — advice and follow-up questions are shaped by them.",
  "chat.missing": "{list} — ask me now, or fill the Business Check-up above.",
  "chat.welcomeReport":
    "I've read your “{topic}” business report — I'm your personal advisor now.{intake} Ask me about your loan eligibility, the documents to carry, or your next steps. आप हिंदी में भी पूछ सकते हैं।",
  "chat.welcomeIntake":
    "Hi, I'm your personal business advisor. I have your Business Check-up answers: {intake}.{missing}",
  "chat.welcomeEmpty":
    "Hi, I'm your personal business advisor. Fill in the Business Check-up above or just tell me about your business — then ask me about loans, schemes, documents, or how to get loan-ready.",
  "chat.missingAsk": "Tell me and I'll get more specific.",
  "chat.noMemoryAsk":
    "That's everything I need — ask me anything about your business or loan.",
  "chat.send": "Send",
  "chat.clear": "Clear chat memory",
  "chat.placeholder": "Ask anything about your business or loan…",
  "chat.placeholderHi": "बिज़नेस या कर्ज़ के बारे में हिंदी में पूछें…",
  "chat.failed": "I couldn't answer that right now. Please rephrase and try again.",
  "chat.offline":
    "I'm having trouble connecting right now. Please check your internet connection and try again.",
  "chat.tip": "Tip: run a research above first — the advisor then remembers your actual business.",
  "chat.quick1": "Which loans can I get?",
  "chat.quick2": "Documents I need",
  "chat.quick3": "क्या मुद्रा लोन मिलेगा?",
  "chat.quick4": "Start with ₹1 lakh?",

  // ── advisor page ─────────────────────────────────────────────────────────
  "advisor.title": "Business Advisor",
  "advisor.subtitle": "Ask me anything about your business — loans, schemes, documents, cash flow, or how to grow. I remember your research context.",
  "advisor.backToResearch": "← Back to Research",
  "advisor.contextActive": "Research context active",
  "advisor.contextDesc": "Your Business Check-up answers are loaded. The advisor will use them to give personalised advice.",
  "advisor.welcome.title": "Welcome to your Business Advisor",
  "advisor.welcome.desc": "I'm your personal business Saathi. I can help with loans, government schemes, documents, cash flow planning, and growing your business.",
  "advisor.welcome.item1": "Loans & scheme eligibility (MUDRA, PMEGP, CGTMSE, PM SVANidhi)",
  "advisor.welcome.item2": "Document checklists for bank applications",
  "advisor.welcome.item3": "Cash flow, pricing, and business model questions",
  "advisor.welcome.item4": "Registration (Udyam, GST) and compliance",
  "advisor.welcome.gotIt": "Got it, let's start",

  // ── live voice ──────────────────────────────────────────────────────────
  "live.title": "Voice Advisor",
  "live.badge": "Live",
  "live.sub": "Talk to your Saathi out loud — it hears you and replies in your language.",
  "live.subConn": "Connected. Ask about loans, schemes and documents — the advisor will reply out loud.",
  "live.start": "Start Voice",
  "live.connecting": "Connecting.",
  "live.mute": "Mute microphone",
  "live.unmute": "Unmute microphone",
  "live.error":
    "Could not connect to the voice advisor. Please try again, or use the text chat below.",
  "live.hint": "Works only when the LiveKit voice stack is configured.",

  // ── misc ────────────────────────────────────────────────────────────────
  "misc.resumeNote": "Reopened your last advisory — run research again to refresh it.",
  "misc.dismissResume": "Dismiss resume notice",
  "misc.langLabel": "Language",
  "misc.langAria": "Change language",
  "misc.whatsappBadge": "Coming Next (Roadmap)",
  "misc.whatsappTitle": "WhatsApp Advisory Bot",
  "misc.whatsappText":
    "Deliver the same advisory via WhatsApp in Hindi, Marathi & Gujarati — no app install needed.",

  // ── schemes explorer ──────────────────────────────────────────────────────
  "schemes.title": "Government Schemes for Small Businesses",
  "schemes.subtitle": "Browse all curated schemes — MUDRA, PMEGP, CGTMSE, PM SVANidhi, and more. Filter by type, search by keyword, and see eligibility at a glance.",
  "schemes.backToResearch": "← Back to Research",
  "schemes.searchPlaceholder": "Search schemes by name or keyword…",
  "schemes.searchAria": "Search schemes",
  "schemes.filterAria": "Filter schemes by type",
  "schemes.filter.all": "All",
  "schemes.filter.loans": "Loans",
  "schemes.filter.subsidies": "Subsidies",
  "schemes.filter.guarantees": "Guarantees",
  "schemes.type.loan": "Loan",
  "schemes.type.subsidy": "Subsidy",
  "schemes.type.guarantee": "Guarantee",
  "schemes.type.other": "Other",
  "schemes.maxAmount": "Max Amount",
  "schemes.interestRate": "Interest Rate",
  "schemes.seeDetails": "See details",
  "schemes.showMore": "Show more",
  "schemes.showLess": "Show less",
  "schemes.purpose": "Purpose",
  "schemes.eligibility": "Eligibility",
  "schemes.eligibleFor": "Eligible for",
  "schemes.requiresUdyam": "Requires Udyam registration",
  "schemes.requiresGST": "Requires GST registration",
  "schemes.locations": "Locations",
  "schemes.excluded": "Excluded",
  "schemes.documents": "Documents Required",
  "schemes.verified": "Verified",
  "schemes.source": "Source",
  "schemes.errorTitle": "Could not load schemes",
  "schemes.retry": "Try Again",
  "schemes.noResults": "No schemes match your filters",
  "schemes.noResultsDesc": "Try a different search term or filter.",
  "schemes.cta.title": "Want a personalised match?",
  "schemes.cta.desc": "Run a research with your business details — Saathi will match the right schemes for you automatically.",
  "schemes.cta.button": "Start Research",
  "footer.aria": "Footer",
  "footer.tagline": "Market research, growth plans and government-scheme guidance for small businesses — in plain language.",
  "footer.trust": "Trust & legal",
  "footer.about": "About",
  "footer.privacy": "Privacy",
  "footer.terms": "Terms",
  "footer.disclaimer": "Disclaimer",
  "footer.dataNote": "Your session is saved under an anonymous ID and deleted automatically after 7 days.",
  "footer.rights": "Your data is yours — export or delete it any time from the research page.",
  "footer.copyright": "© {year} Your AI Business Saathi",
  "footer.analytics": "Usage analytics",
  "footer.analyticsNote": "Anonymous, aggregate counts only — no personal data and nothing you type is sent.",
  "footer.analyticsOn": "On",
  "footer.analyticsOff": "Off",
  "footer.analyticsToggle": "Toggle anonymous usage analytics",
  "legal.updated": "Last updated {date}",
  "legal.backHome": "Back to home",
  "about.title": "About Your AI Business Saathi",
  "about.subtitle": "A plain-language business advisor for shopkeepers, vendors, farmers and other micro-entrepreneurs.",
  "about.s1.title": "What this is",
  "about.s1.body": "Your AI Business Saathi turns a description of your business into a practical road-plan: a business check-up, a cash-flow view, the government schemes you can actually apply for, and the documents you will need. It is built for micro-entrepreneurs who are more comfortable describing their shop than filling in a form.",
  "about.s2.title": "How it works",
  "about.s2.body": "You answer a short business check-up in your own words. Eligibility is decided by deterministic code against a curated scheme dataset — never guessed by a language model. The model only writes the explanation around those verdicts, and every figure is traceable to a source.",
  "about.s3.title": "What this is not",
  "about.s3.body": "We are not a bank, a lender, a government body or a law firm. A verdict here is guidance, not an approval. The final decision on any loan or scheme always rests with the bank, the department or the official portal.",
  "about.s4.title": "Where our scheme data comes from",
  "about.s4.body": "Scheme details come only from the curated dataset in the product, and each scheme carries its official source link and the date we last read it. Figures can change — the app shows when each one was verified and warns when a review is due.",
  "about.s5.title": "Corrections",
  "about.s5.body": "If a figure looks outdated, open the source link on the scheme card and confirm it on the official portal. Government scheme amounts and rates change, and the official portal is always the final word.",
  "privacy.title": "Privacy",
  "privacy.subtitle": "What we store, why, and how to remove it.",
  "privacy.s1.title": "What we store",
  "privacy.s1.body": "When you run a check-up or research, we save your answers and the generated advisory as a JSON file on our server, keyed to an anonymous session ID that your browser creates. We do not ask for your name, phone number, email, Aadhaar or any government ID.",
  "privacy.s2.title": "No accounts, no selling",
  "privacy.s2.body": "There is no sign-up and no login. We do not sell your data, and we do not run third-party advertising or trackers. The app records anonymous, aggregate usage counts (for example, how many check-ups were started) so we can improve it — you can switch this off in the footer.",
  "privacy.s3.title": "AI providers",
  "privacy.s3.body": "To write explanations, your answers may be sent to a language-model provider — a local Ollama model, Hugging Face, or OpenRouter. When the local model is used, your text never leaves our server. If no provider is reachable, the app still answers using built-in rules and no text is sent anywhere.",
  "privacy.s4.title": "Voice",
  "privacy.s4.body": "If you use the microphone, your audio is sent only to our server for transcription. When no cloud voice key is configured, transcription and speech are handled by open-source engines running locally, so your audio is never shared with a third party.",
  "privacy.s5.title": "How long we keep it",
  "privacy.s5.body": "Sessions are deleted automatically after 7 days. You can delete yours at any time.",
  "privacy.s6.title": "Your rights",
  "privacy.s6.body": "You can export everything we hold for your session, or delete it permanently, from the research page. Deleting a session also clears its saved chat.",
  "privacy.s7.title": "Age and consent",
  "privacy.s7.body": "The service is meant for adults running or starting a business. By using it you confirm the information you enter is your own, or that you are allowed to share it.",
  "terms.title": "Terms of use",
  "terms.subtitle": "The simple rules for using Your AI Business Saathi.",
  "terms.s1.title": "Using the service",
  "terms.s1.body": "You may use the service to learn about your business, explore government schemes and prepare documents. Use it lawfully and do not enter anyone else's personal data without permission.",
  "terms.s2.title": "No professional advice",
  "terms.s2.body": "Nothing here is financial, legal, tax or investment advice. It is general guidance based on a curated dataset and your own answers. Consult a qualified professional or the official department before acting.",
  "terms.s3.title": "Accuracy",
  "terms.s3.body": "We work hard to keep scheme data accurate and sourced, but government rules, amounts and rates change. Always confirm the current position on the official portal linked on each scheme card before you apply or pay anything.",
  "terms.s4.title": "Availability",
  "terms.s4.body": "The service is provided as-is and may be changed, interrupted or withdrawn at any time. The free tier may be slow to start after a period of inactivity.",
  "terms.s5.title": "Liability",
  "terms.s5.body": "To the extent permitted by law, we are not liable for decisions you take based on the guidance, or for any loss arising from using the service.",
  "terms.s6.title": "Changes",
  "terms.s6.body": "We may update these terms. Continued use after a change means you accept the updated terms.",
  "disclaimer.title": "Disclaimer",
  "disclaimer.subtitle": "Please read this before acting on anything you see here.",
  "disclaimer.s1.title": "Guidance, not approval",
  "disclaimer.s1.body": "An eligibility verdict tells you whether a scheme's published rules appear to fit your business. It is not an offer of credit and not an approval. Only the bank, department or official portal can decide your application.",
  "disclaimer.s2.title": "Figures can change",
  "disclaimer.s2.body": "Loan amounts, subsidies and interest rates change, sometimes with the annual budget. Each scheme shows its source and the date we last verified it, and flags when a review is due.",
  "disclaimer.s3.title": "Documents are your responsibility",
  "disclaimer.s3.body": "The document list is a guide. Get the exact requirements from the bank or portal, and never share your OTP, PIN or passwords with anyone.",
  "disclaimer.s4.title": "No guarantee of benefit",
  "disclaimer.s4.body": "Meeting the published rules does not guarantee a benefit. Sanction depends on the lender's assessment and the available budget.",
  "disclaimer.s5.title": "Verify at source",
  "disclaimer.s5.body": "Before you apply, pay a fee or share documents, confirm every detail on the official website linked on the scheme card.",
};

const HI: Record<string, string> = {
  // ── nav ───────────────────────────────────────────────────────────────────
  "nav.home": "होम",
  "nav.research": "रिसर्च",
  "nav.advisor": "सलाहकार",
  "nav.schemes": "स्कीमें",
  "nav.dpr": "रिपोर्ट",
  "nav.tracker": "ट्रैकर",
  "nav.history": "इतिहास",
  "nav.aria": "मुख्य नेविगेशन",
  "nav.openMenu": "मेन्यू खोलें",
  "nav.closeMenu": "मेन्यू बंद करें",

  // ── brand / hero ────────────────────────────────────────────────────────
  "brand.name": "आपका AI बिज़नेस साथी",
  "brand.tagline": "छोटे बिज़नेस के लिए मार्केट रिसर्च, ग्रोथ प्लान और स्कीमें",

  "hero.kicker": "छोटे बिज़नेस के लिए मार्केट रिसर्च, ग्रोथ प्लान और सरकारी स्कीमें",
  "hero.sub":
    "अपने बिज़नेस को आसान भाषा में लिखिए — लाइव मार्केट रिसर्च, साफ़ बिज़नेस प्लान, आपकी स्कीमें और लोन की तैयारी की चेकलिस्ट 60 सेकंड में।",

  // ── landing page ──────────────────────────────────────────────────────────
  "landing.hero.badge": "नया: ऑफलाइन मोड + हिंदी सपोर्ट",
  "landing.hero.title": "आपका AI बिज़नेस साथी — छोटे बिज़नेस के लिए मार्केट रिसर्च, ग्रोथ प्लान और स्कीमें",
  "landing.hero.subtitle": "अपने बिज़नेस को आसान भाषा में बताइए। लाइव मार्केट रिसर्च, साफ़ रोडमैप, आपकी सरकारी स्कीमें और लोन की तैयारी की चेकलिस्ट — 60 सेकंड में।",
  "landing.hero.cta": "रिसर्च शुरू करें",
  "landing.hero.ctaSecondary": "स्कीमें देखें",
  "landing.hero.trust": "साइनअप नहीं · ऑफलाइन चलता है · कभी भी एक्सपोर्ट या डिलीट करें",

  "landing.stats.1": "बिज़नेस को मदद मिली",
  "landing.stats.2": "क्यूरेटेड स्कीमें",
  "landing.stats.3": "सामान्य रिसर्च समय",
  "landing.stats.4": "मुफ़्त और खुला सोर्स",

  "landing.features.title": "छोटे बिज़नेस के लिए बना",
  "landing.features.subtitle": "कोई आम चैटबॉट नहीं — साथी भारतीय माइक्रो-उद्यमियों के लिए खास है",

  "landing.features.1.title": "बिज़नेस-फर्स्ट सलाह",
  "landing.features.1.desc": "साथी आपका बिज़नेस बनाने में मदद करता है — दाम, खर्च, कैश फ्लो, ग्राहक, रजिस्ट्रेशन — सिर्फ सवालों के जवाब नहीं देता।",

  "landing.features.2.title": "लाइव मार्केट रिसर्च",
  "landing.features.2.desc": "वेब से लिए तथ्य, याद किए जवाब नहीं। स्रोत साथ दिए जाते हैं ताकि आप खुद जाँच सकें।",

  "landing.features.3.title": "आपकी भारतीय स्कीमें",
  "landing.features.3.desc": "MUDRA, PMEGP, CGTMSE, PM SVANidhi — आपके बिज़नेस, अवस्था और लोन राशि के हिसाब से अपने आप चुनी जाती हैं।",

  "landing.features.4.title": "लोन की तैयारी की चेकलिस्ट",
  "landing.features.4.desc": "साफ़ एक्शन लेजर बताता है कि बैंक जाने से पहले क्या-क्या करना है।",

  "landing.features.5.title": "ऑफलाइन भी चलता है",
  "landing.features.5.desc": "मुफ़्त लोकल AI मॉडल (Ollama) और ऑफ़लाइन फ़ॉलबैक — इंटरनेट न हो तब भी साथी जवाब देता है। कोई सब्सक्रिप्शन नहीं।",

  "landing.features.6.title": "आपका डेटा, आपका नियंत्रण",
  "landing.features.6.desc": "आपका सेशन सर्वर पर एक गुमनाम ID से जुड़ा रहता है — कभी भी एक्सपोर्ट या पूरा डिलीट करें। 7 दिन बाद अपने आप हट जाता है।",

  "landing.cta.title": "अपने बिज़नेस को बेहतर समझने को तैयार?",
  "landing.cta.subtitle": "मुफ़्त रिसर्च सेकंड में शुरू करें। साइनअप नहीं, क्रेडिट कार्ड नहीं।",
  "landing.cta.button": "रिसर्च शुरू करें",

  "landing.footer.desc": "भारतीय माइक्रो-उद्यमियों के लिए खास बिज़नेस सलाह। मार्केट रिसर्च, स्कीम मिलान और लोन की तैयारी — सब एक जगह।",
  "landing.footer.links": "त्वरित लिंक",
  "landing.footer.legal": "कानूनी",
  "landing.footer.privacy": "गोपनीयता नीति",
  "landing.footer.terms": "सेवा की शर्तें",
  "landing.footer.contact": "संपर्क करें",
  "landing.footer.copyright": "© 2024 आपका AI बिज़नेस साथी। सर्वाधिकार सुरक्षित।",

  "quiz.title": "बिज़नेस चेक-अप",
  "quiz.optional": "(ज़रूरी नहीं)",
  "quiz.sub0": "कुछ आसान सवाल, या अपने शब्दों में लिखिए — बाकी साथी पूछ लेगा।",
  "quiz.subDone": "{total} सवाल पूरे — आपका साथी अब आपका बिज़नेस जानता है।",
  "quiz.subPartial": "{answered}/{total} पूरे — बाकी आपके साथी chat में पूछेगा।",
  "quiz.questionOf": "सवाल {n} / {total}",
  "quiz.typeOwn": "या अपने शब्दों में लिखिए",
  "quiz.yourAnswer": "आपका जवाब",
  "quiz.back": "पीछे",
  "quiz.skip": "छोड़ें",
  "quiz.allAnswered": "{total} पूरे",
  "quiz.saveAnswer": "यह जवाब सेव करके आगे बढ़ें",
  "quiz.clearAnswer": "यह जवाब हटाएँ",
  "quiz.reset": "चेक-अप के जवाब मिटाएँ",
  "quiz.saveNext": "जब यह काम हो जाए तो टैप करें",
  "quiz.knownBefore": "यह हमें आपके जवाब से पता है",
  "quiz.askRest": "बाकी आपके साथी chat में पूछेगा: {list}।",
  "quiz.allSet": "आपके साथी के पास अब सब कुछ है — यही जवाब वह हर जगह इस्तेमाल करेगा।",
  "quiz.staysLocal": "आपके जवाब सिर्फ़ आपकी रिसर्च के लिए इस्तेमाल होते हैं — कभी भी एक्सपोर्ट या डिलीट करें।",
  "quiz.liveTitle": "आपका बिज़नेस: {label}",
  "quiz.openForYou": "आपके लिए खुली: {list}",
  "quiz.filledIn": "जानकारी भरी: {pct}%",

  // ── benefit calculator (WS-3) ───────────────────────────────────────────
  "benefits.title": "आपको क्या मिल सकता है (अनुमान)",
  "benefits.costLabel": "आपकी परियोजना लागत (₹)",
  "benefits.costHint": "लागत भरें तो सब्सिडी रुपये में दिखेगी",
  "benefits.subsidy": "जो राशि चुकानी नहीं पड़ सकती",
  "benefits.credit": "जिन कर्ज़ों से आप जुड़ते हैं (अधिकतम)",
  "benefits.none": "अभी कोई अनुदान या सब्सिडी स्कीम नहीं मिली",
  "benefits.showAll": "सभी {count} मिलती स्कीमें देखें",
  "benefits.showLess": "कम देखें",
  "benefits.loading": "गिनती हो रही है…",
  "benefits.disclaimerLabel": "ध्यान दें",
  "benefits.source": "स्रोत",

  // ── document checklist (WS-4) ───────────────────────────────────────────
  "docs.title": "कौन-कौन से कागज़ तैयार रखें",
  "docs.print": "प्रिंट / PDF सेव करें",
  "docs.copyWhatsapp": "WhatsApp के लिए कॉपी करें",
  "docs.copied": "कॉपी हो गया",
  "docs.generatedOn": "बना: {date}",
  "docs.loading": "लोड हो रहा है…",

  // ── Detailed Project Report (WS-5) ──────────────────────────────────────
  "dpr.title": "बैंक के लिए तैयार प्रोजेक्ट रिपोर्ट",
  "dpr.subtitle": "आपके ही जवाबों से बनी Detailed Project Report (DPR) — कर्ज़ मंज़ूर करने से पहले बैंक यही फ़ाइल पढ़ता है। हर आँकड़ा आपके नंबरों से बनता है और उसके स्रोत के साथ छपता है।",
  "dpr.needProfile": "पहले Business Check-up में अपने बिज़नेस की जानकारी दें। आपके जवाब अपने आप रिपोर्ट में भर जाएँगे।",
  "dpr.goToCheckup": "Business Check-up शुरू करें",
  "dpr.scheme": "किस स्कीम के लिए आवेदन",
  "dpr.cost": "परियोजना लागत (₹)",
  "dpr.sales": "महीने की बिक्री (₹)",
  "dpr.expenses": "महीने का ख़र्च (₹)",
  "dpr.optional": "वैकल्पिक",
  "dpr.optionalHint": "असली अनुमान के लिए लागत और बिक्री भरें। ख़ाली छोड़ने पर रिपोर्ट बताती है कि क्या जानकारी चाहिए — अंदाज़ा नहीं लगाती।",
  "dpr.generate": "रिपोर्ट बनाएँ",
  "dpr.generating": "बन रही है…",
  "dpr.download": "PDF डाउनलोड करें",
  "dpr.failed": "अभी रिपोर्ट नहीं बन सकी। कृपया दोबारा कोशिश करें।",
  "dpr.source": "स्कीम का स्रोत",
  "dpr.pdfNote": "PDF अंग्रेज़ी में है — बैंक अंग्रेज़ी फ़ाइल पढ़ते हैं।",
  "dpr.assumptions": "इस्तेमाल की गई मान्यताएँ",
  "dpr.cta": "बैंक के लिए तैयार रिपोर्ट बनाएँ",

  // ── application tracker (WS-6) ──────────────────────────────────────────
  "tracker.title": "आवेदन ट्रैकर",
  "tracker.subtitle": "हर आवेदन को सोचने से मंज़ूरी तक आगे बढ़ाइए और बंद होती अवधियों पर नज़र रखिए। तारीख़ें हर स्कीम के अपने दस्तावेज़ों से ली जाती हैं।",
  "tracker.matchedHint": "ये स्कीमें आपके बिज़नेस से मिलती हैं",
  "tracker.addTitle": "ट्रैक करने के लिए स्कीम जोड़ें",
  "tracker.choose": "स्कीम चुनें",
  "tracker.add": "जोड़ें",
  "tracker.addAll": "मिलती सभी स्कीमें जोड़ें",
  "tracker.tracking": "ट्रैक हो रहा है",
  "tracker.empty": "अभी कुछ नहीं है। जिस स्कीम के लिए आवेदन कर रहे हैं उसे जोड़ें, फिर काम के साथ आगे बढ़ाते रहें।",
  "tracker.stageHint": "कार्ड को आगे बढ़ाने के लिए तीरों का इस्तेमाल करें।",
  "tracker.moveNext": "आगे बढ़ाएँ",
  "tracker.moveNextAria": "{name} को अगले चरण में ले जाएँ",
  "tracker.movePrev": "पीछे लाएँ",
  "tracker.movePrevAria": "{name} को पिछले चरण में ले जाएँ",
  "tracker.markRejected": "नामंज़ूर",
  "tracker.markRejectedAria": "{name} को नामंज़ूर चिह्नित करें",
  "tracker.remove": "हटाएँ",
  "tracker.removeAria": "{name} को ट्रैकर से हटाएँ",
  "tracker.target": "आपकी तय तारीख़",
  "tracker.targetAria": "{name} के लिए तय तारीख़",
  "tracker.targetHint": "वैकल्पिक। यह आपकी अपनी तारीख़ है, स्कीम की नहीं।",
  "tracker.notes": "टिप्पणी",
  "tracker.notesPlaceholder": "अभी क्या बाक़ी है?",
  "tracker.notesAria": "{name} के लिए टिप्पणी",
  "tracker.stage.planning": "सोच रहे हैं",
  "tracker.stage.docs_ready": "कागज़ तैयार",
  "tracker.stage.submitted": "जमा किया",
  "tracker.stage.approved": "मंज़ूर",
  "tracker.stage.rejected": "नामंज़ूर",
  "tracker.deadlines": "आने वाली तारीख़ें",
  "tracker.noDeadlines": "दिखाने के लिए कोई तय तारीख़ नहीं है। आपकी ट्रैक की गई स्कीमें लगातार आवेदन लेती हैं।",
  "tracker.daysLeft": "{days} दिन बाक़ी",
  "tracker.dueToday": "आज आख़िरी दिन",
  "tracker.overdueBy": "{days} दिन पहले ख़त्म",
  "tracker.state.closing_soon": "जल्द बंद हो रहा है",
  "tracker.state.open": "खुला",
  "tracker.state.lapsed": "अवधि ख़त्म",
  "tracker.state.lapsed_pending": "पुष्टि बाक़ी",
  "tracker.state.rolling": "कोई अंतिम तिथि प्रकाशित नहीं",
  "tracker.yours": "आपकी तारीख़",
  "tracker.source": "स्रोत",
  "tracker.verified": "{date} को जाँचा",
  "tracker.alertsTitle": "तारीख़ की चेतावनियाँ",
  "tracker.alertsSubtitle": "बताइए हम आपसे कैसे संपर्क करें; अवधि बंद होने या स्कीम बदलने पर हम संदेश तैयार करेंगे।",
  "tracker.channel": "हम आपसे कैसे संपर्क करें?",
  "tracker.channelNone": "अभी नहीं",
  "tracker.channelEmail": "ईमेल",
  "tracker.saveAlerts": "चेतावनियाँ सेव करें",
  "tracker.contact": "फ़ोन या ईमेल",
  "tracker.contactPhoneHint": "देश कोड + नंबर, सिर्फ़ अंक (जैसे 919876543210)",
  "tracker.contactEmailHint": "you@example.com",
  "tracker.events": "किस बारे में बताएँ",
  "tracker.event.deadline_soon": "बंद होती अवधि",
  "tracker.event.new_match": "नई मिली स्कीम",
  "tracker.event.reverified": "जिस स्कीम के नियम दोबारा जाँचे गए",
  "tracker.consent": "मैं इन चेतावनियों के लिए संपर्क किए जाने से सहमत हूँ।",
  "tracker.preview": "हम आपको क्या भेजेंगे",
  "tracker.alertsNote": "चेतावनियाँ यहीं तैयार होती हैं। WhatsApp या ईमेल जुड़ने पर संदेश भेजे जाएँगे — तब तक ये इसी पेज पर दिखेंगी।",
  "tracker.noAlerts": "अच्छी ख़बर — आज कुछ ध्यान देने वाला नहीं है।",
  "tracker.privacy": "आपका ट्रैकर आपकी सेशन आईडी के तहत रखा जाता है। मिटाने के लिए History से सेशन डिलीट करें।",
  "tracker.saveFailed": "अभी सर्वर पर सेव नहीं हो सका। आपकी सूची इसी ब्राउज़र में रखी है।",
  "tracker.saved": "सेव हो गया",
  "tracker.saving": "सेव हो रहा है",
  "tracker.cta": "अपने आवेदन ट्रैक करें",
  "tracker.loading": "लोड हो रहा है",
  "tracker.invalidContact": "आपने जो फ़ोन नंबर या ईमेल डाला है उसे जाँच लें।",
  "tracker.needContact": "चेतावनी चालू करने के लिए फ़ोन नंबर या ईमेल डालें।",
  "tracker.needConsent": "चेतावनी सेव करने से पहले संपर्क की सहमति दें।",
  "dpr.noSchemes": "आपके चेक-अप जवाबों से अभी कोई स्कीम नहीं मिली। Business Check-up में कुछ और सवालों के जवाब दें, विकल्प यहाँ दिखेंगे।",

  "input.placeholder":
    "अपना बिज़नेस बताइए — क्या बेचते हैं, लगभग कितना कमाते हैं, और कहाँ हैं",
  "input.examples": "आसान उदाहरण",
  "input.example1": "गाँव में सब्ज़ी बेचने वाले, ₹15,000 प्रति महीने",
  "input.example2": "छोटे शहर में दर्ज़ी, ₹25,000 प्रति महीने, सिलाई मशीन का लोन चाहिए",
  "input.example3": "गुजरात में छोटा डेयरी फ़ार्म, 3 गायें, ₹20,000 प्रति महीने",
  "input.depth": "रिसर्च की गहराई:",
  "input.steps": "चरण",
  "input.start": "रिसर्च शुरू करें",
  "input.stop": "रिसर्च रोकें",
  "mic.speak": "अपने बिज़नेस के बारे में बोलिए",
  "mic.stop": "रिकॉर्डिंग बंद करें",
  "mic.record": "आवाज़ से लिखिए",
  "mic.stopAria": "आवाज़ रिकॉर्डिंग बंद करें",
  "mic.recording": "रिकॉर्ड हो रहा है — बंद करने के लिए फिर माइक दबाइए",
  "mic.transcribing": "लिखा जा रहा है…",
  "mic.done": "लिख लिया — देखकर भेजिए",
  "mic.unheard": "आवाज़ समझ नहीं आई — कृपया लिखिए।",
  "mic.unavailable": "अभी आवाज़ काम नहीं कर रही — कृपया लिखिए।",
  "mic.denied": "माइक की इजाज़त नहीं मिली — कृपया लिखिए।",
  "voice.private": "आवाज़ सर्वर पर ही प्रोसेस होती है — रिकॉर्डिंग कहीं नहीं जाती।",
  "voice.stt": "बोलकर लिखना",
  "voice.tts": "लिखकर बोलना",
  "voice.cloud": "बेहतर आवाज़ के लिए ElevenLabs क्लाउड इस्तेमाल हो रही है।",

  "usps.kicker": "आपका AI बिज़नेस साथी क्यों",
  "usps.title": "आपके बिज़नेस के लिए बना — कोई आम chatbot नहीं।",
  "usps.sub":
    "ChatGPT सामान्य सवालों के जवाब देता है। आपका AI बिज़नेस साथी बिज़नेस बनाता है, सलाह देता है और लोन के लिए तैयार करता है।",
  "usps.1.title": "आपका निजी बिज़नेस सलाहकार",
  "usps.1.text":
    "यह आपकी रिसर्च पढ़ता है और बातचीत याद रखता है — फिर आपके ही बिज़नेस के सवालों के जवाब देता है, आम बातें नहीं।",
  "usps.2.title": "असली मार्केट रिसर्च",
  "usps.2.text":
    "यह वेब पर लाइव तथ्य खोजता है — याद से अंदाज़ा नहीं लगाता।",
  "usps.3.title": "आपकी भारतीय स्कीम",
  "usps.3.text":
    "MUDRA, PMEGP, CGTMSE, PM SVANidhi — नियम-आधारित इंजन से आपके बिज़नेस और उसकी अवस्था के हिसाब से चुनी जाती हैं, हर स्कीम का अपना स्रोत और जाँच की तारीख।",
  "usps.4.title": "बिना इंटरनेट भी चलता है",
  "usps.4.text":
    "मुफ़्त और लोकल AI मॉडल पर चलता है। कोई सब्सक्रिप्शन नहीं — और इंटरनेट चले जाए तब भी जवाब देता है।",
  "usps.5.title": "पूरी साइट आपकी भाषा में",
  "usps.5.text":
    "चेक-अप, स्कीम, लिस्ट — पूरी साइट हिंदी में बदलिए, और साथी उसी भाषा में जवाब देगा, बिना इंटरनेट के भी।",
  "usps.6.title": "आपका डेटा आपका ही",
  "usps.6.text":
    "एक टैप में एक्सपोर्ट और पूरा डिलीट — सेशन 7 दिन बाद अपने आप हट जाता है (GDPR के मुताबिक)। किसी को कुछ नहीं बेचा जाता।",

  // ── session history ─────────────────────────────────────────────────────
  "history.title": "आपकी रिसर्च का इतिहास",
  "history.subtitle":
    "इस सेशन में की गई हर रिसर्च यहाँ रियल टाइम में सेव होती है। रिपोर्ट दोबारा देखने के लिए किसी एक को खोलिए।",
  "history.loading": "आपका इतिहास लोड हो रहा है…",
  "history.error": "आपका इतिहास लोड नहीं हो सका।",
  "history.retry": "दोबारा कोशिश करें",
  "history.empty": "अभी कोई रिसर्च सेव नहीं है। पहली रिसर्च चलाइए — वो यहाँ दिखेगी।",
  "history.inProgress": "चल रही है…",
  "history.savedOn": "सेव हुआ",
  "history.topicFallback": "बिना शीर्षक रिसर्च",
  "history.loanReady": "लोन-रेडी",
  "history.viewReport": "रिपोर्ट देखें",
  "history.hideReport": "रिपोर्ट छिपाएँ",
  "history.export": "एक्सपोर्ट",
  "history.noReport": "इस रन की कोई रिपोर्ट सेव नहीं हुई।",
  "history.limited": "आपके सबसे नए {n} रन दिखाए जा रहे हैं।",
  "history.viewAll": "पूरा इतिहास खोलें",
  "history.clearTitle": "यह सेशन डिलीट करें",
  "history.clearDesc": "इस सेशन का इतिहास और चैट हमेशा के लिए हटा दें (GDPR डिलीट का अधिकार)।",
  "history.clear": "सेशन डेटा डिलीट करें",
  "history.clearDone": "सेशन डेटा डिलीट हो गया।",
  "history.clearFailed": "सेशन डेटा डिलीट नहीं हो सका। दोबारा कोशिश करें।",

  "timeline.title": "साथी अभी क्या कर रहा है",
  "timeline.waiting": "आपके इंतज़ार में।",
  "timeline.working": "चल रहा है…",
  "timeline.plan": "प्लान",
  "timeline.agentsDone": "{total} में से {done} चरण पूरे",
  "timeline.statusPlan": "{n} रिसर्च चरण",
  "timeline.statusDone": "हो गया",
  "timeline.pass": "चक्कर {n}",
  "timeline.tools": "इस्तेमाल किए गए टूल",
  "timeline.thought": "सोच",
  "timeline.reflection": "खुद की जाँच",
  "timeline.engine": "इंजन",
  "timeline.connecting": "जुड़ रहा है…",
  "timeline.running": "{label} चल रहा है…",
  "timeline.cancelled": "रिसर्च रोक दी गई।",
  "timeline.complete": "रिसर्च पूरी हो गई।",
  "timeline.lost": "रिसर्च के बीच कनेक्शन टूट गया। कृपया फिर कोशिश करें।",
  "timeline.retry": "कनेक्शन टूटा — फिर कोशिश हो रही है ({n}/{max})…",
  "timeline.offline":
    "आपके बिज़नेस साथी से संपर्क नहीं हो पाया। कृपया इंटरनेट जाँचकर फिर कोशिश करें।",

  "report.sources": "स्रोत",
  "report.summary": "आपके बिज़नेस की झलक",
  "report.cashflow": "कैश-फ़्लो",
  "report.schemes": "मिलने वाली सरकारी स्कीमें",
  "report.docs": "काग़ज़ों की सूची",
  "report.next": "अगला कदम",
  "report.simple": "आसान भाषा में — सुनकर पढ़ने वाला",
  "report.copy": "कॉपी",
  "report.copied": "कॉपी हो गया!",
  "report.copyAria": "सलाह कॉपी करें",
  "report.download": "डाउनलोड .txt",
  "report.downloadAria": "सलाह .txt में डाउनलोड करें",
  "report.listen": "सलाह सुनें",
  "report.listening": "चल रहा है…",
  "report.stopAudio": "आवाज़ बंद करें",
  "report.audioFailed": "आवाज़ नहीं चल पाई।",
  "report.audioBusy": "कृपया रुकिए — पिछला हिस्सा अभी चल रहा है।",
  "report.parseError": "यह रिसर्च पढ़ी नहीं जा सकी। कृपया फिर से रिसर्च करें।",
  "report.score": "लोन-रेडी स्कोर",
  "report.schemeNote":
    "शर्तें बदलती रहती हैं — अपने बैंक या आधिकारिक स्कीम पोर्टल पर पक्का कर लें।",

  "elig.title": "आप असल में किस स्कीम के लिए पात्र हैं",
  "elig.yourBusiness": "आपका बिज़नेस: {label}",
  "elig.asking": "{amount} का लोन पूछ रहे हैं",
  "elig.subtitle":
    "यह सरकारी नियमों से कोड में जाँचा गया है — अंदाज़ा नहीं लगाया गया। कार्ड पर टैप करके नियम और स्रोत देखिए।",
  "elig.tapRule": "नियम: {rule}",
  "elig.matchScore": "मेल {score}%",
  "elig.tiers": "लोन के स्तर",
  "elig.documents": "काग़ज़",
  "elig.collateral": "ज़मानत:",
  "elig.source": "आधिकारिक स्रोत",
  "elig.verified": "जाँचा गया {date}",
  "elig.use": "यह लें: {name}",
  "elig.status.eligible": "पात्र",
  "elig.status.likely": "शायद पात्र",
  "elig.status.blocked": "रुका हुआ",
  "elig.status.not_eligible": "पात्र नहीं",
  "elig.status.wrong_tier": "गलत स्तर",

  "ledger.title": "आपकी काम की सूची",
  "ledger.doneOf": "{total} में से {done} पूरे",
  "ledger.scoreLine":
    "आपका स्कोर {score}/100 है{level} — जो काम हो गया है उसे टिक करें, स्कोर तुरंत बढ़ेगा।",
  "ledger.levelReady": " — आवेदन के लिए तैयार",
  "ledger.levelAlmost": " — लगभग पहुँचे",
  "ledger.levelGetting": " — रास्ते में हैं",
  "ledger.levelEarly": " — शुरुआत हो रही है",
  "ledger.doNext": "अगला काम: {title}",
  "ledger.opensUp": "यह खोलेगा: {list}",
  "ledger.markComplete": "पूरा हुआ: {title}",
  "ledger.markCompleted": "पूरा हो चुका: {title}",
  "ledger.undo": "वापस करने के लिए टैप करें",
  "ledger.saveError": "अभी सेव नहीं हो पाया। कृपया फिर कोशिश करें।",
  "ledger.local": "यहाँ कुछ भी कहीं नहीं भेजा जाता।",

  "cash.title": "कैश-फ़्लो सिम्युलेटर",
  "cash.sub": "अपने आँकड़े डालिए — देखिए बिज़नेस चलेगा या नहीं और कब। इंटरनेट की ज़रूरत नहीं।",
  "cash.capital": "शुरुआती पैसा (₹)",
  "cash.sales": "हफ़्ते की बिक्री (₹)",
  "cash.expenses": "हफ़्ते का खर्च (₹)",
  "cash.weeks": "कितने हफ़्ते देखना है",
  "cash.chartAria": "हफ़्तों के हिसाब से अनुमानित बैलेंस",
  "cash.surplus": "महीने का बचत",
  "cash.breakeven": "निकलने का हफ़्ता",
  "cash.weekN": "हफ़्ता {n}",
  "cash.never": "यह संभव नहीं",
  "cash.immediate": "तुरंत",
  "cash.balance": "{n} हफ़्तों बाद बैलेंस",
  "cash.warn": "यह हिसाब आपके दिए आँकड़ों पर है — इसे सिर्फ़ अनुमान समझें, भरोसा नहीं।",
  "cash.warnNegative":
    "ख़र्चा बिक्री से ज़्यादा है — हर हफ़्ते पैसा कम हो रहा है। लोन से पहले ख़र्चा घटाइए या बिक्री बढ़ाइए।",
  "cash.foot": "पूरी तरह आपके फ़ोन पर चलता है — कहीं कुछ नहीं भेजा जाता। कोई भी आँकड़ा बदलकर दूसरा प्लान आज़माइए।",

  "market.title": "आज का बाज़ार देखें",
  "market.sub": "सरकारी स्रोत से भाव और जानकारी — हमेशा उसी तारीख़ के साथ जिसकी वह है। यहाँ कुछ भी अंदाज़े से नहीं है।",
  "market.kind.mandi": "मंडी भाव",
  "market.kind.pincode": "पिनकोड",
  "market.kind.ifsc": "बैंक शाखा (IFSC)",
  "market.crop.onion": "प्याज़",
  "market.crop.potato": "आलू",
  "market.crop.tomato": "टमाटर",
  "market.crop.wheat": "गेहूँ",
  "market.crop.paddy": "धान",
  "market.crop.cotton": "कपास",
  "market.ph.commodity": "फ़सल — जैसे Onion",
  "market.ph.market": "मंडी या बाज़ार (वैकल्पिक)",
  "market.ph.state": "राज्य (वैकल्पिक)",
  "market.ph.pincode": "6 अंकों का पिनकोड",
  "market.ph.ifsc": "IFSC — जैसे HDFC0001234",
  "market.check": "देखें",
  "market.modal": "प्रति क्विंटल",
  "market.range": "{min} से {max} तक",
  "market.delivery": "डिलीवरी",
  "market.badge.live": "लाइव",
  "market.badge.stale": "लाइव नहीं",
  "market.badge.off": "लाइव डेटा नहीं",
  "market.badge.undated": "लाइव, बिना तारीख़",
  "market.offline": "अभी लाइव डेटा तक नहीं पहुँच पाए। कुछ मिनट बाद दोबारा कोशिश करें।",
  "market.more": "सरकारी पोर्टल पर {n} और पंक्तियाँ।",
  "market.official": "सरकारी पोर्टल",
  "market.source": "स्रोत",

  "chat.title": "आपका निजी बिज़नेस सलाहकार",
  "chat.subReport": "आपके “{topic}” बिज़नेस को जानता है — सवालों के जवाब आपकी ही रिसर्च से।",
  "chat.subReportIntake":
    "आपके “{topic}” बिज़नेस और चेक-अप के जवाब जानता है ({intake}) — सवालों के जवाब आपकी ही रिसर्च से।",
  "chat.subIntake": "आपके चेक-अप के जवाब जानता है ({intake}) — कभी भी सवाल पूछिए।",
  "chat.subMemory": "यह बातचीत याद रखता है — ऊपर रिसर्च करें, फिर आपका बिज़नेस जान लेगा।",
  "chat.subNoMemory": "बिना याद रखे बातचीत हो रही है।",
  "chat.badgeReport":
    "आपके “{topic}” बिज़नेस के लिए — जवाब आपकी रिसर्च पर आधारित, आम सलाह नहीं।",
  "chat.badgeIntake": "आपके चेक-अप के जवाब से — सलाह और सवाल उन्हीं से बनते हैं।",
  "chat.missing": "{list} — अभी बताइए, या ऊपर चेक-अप भरिए।",
  "chat.welcomeReport":
    "मैंने आपका “{topic}” बिज़नेस रिसर्च पढ़ लिया — अब मैं आपका निजी सलाहकार हूँ।{intake} लोन की पात्रता, काग़ज़ और अगला कदम पूछिए।",
  "chat.welcomeIntake":
    "नमस्ते, मैं आपका निजी बिज़नेस सलाहकार हूँ। आपके जवाब मेरे पास हैं: {intake}।{missing}",
  "chat.welcomeEmpty":
    "नमस्ते, मैं आपका निजी बिज़नेस सलाहकार हूँ। ऊपर चेक-अप भरिए या अपना बिज़नेस बताइए — फिर लोन, स्कीम और काग़ज़ के बारे में पूछिए।",
  "chat.missingAsk": "यह बताइए, मैं और साफ़ सलाह दे सकता हूँ।",
  "chat.noMemoryAsk": "मेरे पास ज़रूरी सब है — अब कुछ भी पूछिए।",
  "chat.send": "भेजें",
  "chat.clear": "बातचीत मिटाएँ",
  "chat.placeholder": "अपने बिज़नेस या लोन के बारे में कुछ भी पूछिए…",
  "chat.placeholderHi": "बिज़नेस या कर्ज़ के बारे में हिंदी में पूछें…",
  "chat.failed": "अभी जवाब नहीं मिल पाया। कृपया दोबारा लिखिए।",
  "chat.offline": "अभी संपर्क में समस्या है। इंटरनेट जाँचकर फिर कोशिश करें।",
  "chat.tip": "सुझाव: ऊपर पहले रिसर्च कर लें — फिर सलाहकार आपका असली बिज़नेस याद रखेगा।",
  "chat.quick1": "मुझे कौन-सा लोन मिलेगा?",
  "chat.quick2": "मुझे कौन-से काग़ज़ चाहिए?",
  "chat.quick3": "क्या मुद्रा लोन मिलेगा?",
  "chat.quick4": "₹1 लाख से शुरुआत करूँ?",

  // ── advisor page ─────────────────────────────────────────────────────────
  "advisor.title": "बिज़नेस सलाहकार",
  "advisor.subtitle": "अपने बिज़नेस के बारे में कुछ भी पूछिए — लोन, स्कीम, काग़ज़, कैश फ्लो या ग्रोथ। मैं आपकी रिसर्च याद रखता हूँ।",
  "advisor.backToResearch": "← रिसर्च पर वापस",
  "advisor.contextActive": "रिसर्च का संदर्भ सक्रिय",
  "advisor.contextDesc": "आपके बिज़नेस चेक-अप के जवाब लोड हो चुके हैं। सलाहकार इन्हीं से आपको निजी सलाह देगा।",
  "advisor.welcome.title": "आपका बिज़नेस सलाहकार में स्वागत है",
  "advisor.welcome.desc": "मैं आपका निजी बिज़नेस साथी हूँ। लोन, सरकारी स्कीम, काग़ज़, कैश फ्लो प्लानिंग और बिज़नेस बढ़ाने में मदद कर सकता हूँ।",
  "advisor.welcome.item1": "लोन और स्कीम पात्रता (MUDRA, PMEGP, CGTMSE, PM SVANidhi)",
  "advisor.welcome.item2": "बैंक एप्लिकेशन के लिए काग़ज़ की चेकलिस्ट",
  "advisor.welcome.item3": "कैश फ्लो, दाम और बिज़नेस मॉडल के सवाल",
  "advisor.welcome.item4": "रजिस्ट्रेशन (Udyam, GST) और अनुपालन",
  "advisor.welcome.gotIt": "समझ गया, शुरू करते हैं",

  // ── live voice ──────────────────────────────────────────────────────────
  "live.title": "आवाज़ वाली सलाह",
  "live.badge": "लाइव",
  "live.sub": "अपने साथी से बोलकर पूछिए — वह सुनेगा और आपकी भाषा में जवाब देगा।",
  "live.subConn": "जुड़ गया। लोन, स्कीम और काग़ज़ पूछिए — सलाहकार बोलकर जवाब देगा।",
  "live.start": "आवाज़ शुरू करें",
  "live.connecting": "जुड़ रहा है…",
  "live.mute": "माइक बंद करें",
  "live.unmute": "माइक चालू करें",
  "live.error": "आवाज़ वाले सलाहकार से संपर्क नहीं बना। फिर कोशिश करें, या नीचे टेक्स्ट chat इस्तेमाल करें।",
  "live.hint": "यह तभी चलता है जब LiveKit वॉइस सेटअप हो।",

  "misc.resumeNote": "पिछली सलाह दोबारा खोल दी — नई रिसर्च से ताज़ा होगी।",
  "misc.dismissResume": "यह संदेश हटाएँ",
  "misc.langLabel": "भाषा",
  "misc.langAria": "भाषा बदलें",
  "misc.whatsappBadge": "जल्द आ रहा है",
  "misc.whatsappTitle": "WhatsApp सलाहकार",
  "misc.whatsappText":
    "वही सलाह अब WhatsApp पर — हिंदी, मराठी और गुजराती में, बिना ऐप इंस्टॉल किए।",

  // ── schemes explorer ──────────────────────────────────────────────────────
  "schemes.title": "छोटे बिज़नेस के लिए सरकारी स्कीमें",
  "schemes.subtitle": "सभी क्यूरेटेड स्कीमें देखें — मुद्रा, PMEGP, CGTMSE, PM SVANidhi, और भी। टाइप से फ़िल्टर करें, कीवर्ड से खोजें, और पात्रता एक नज़र में देखें।",
  "schemes.backToResearch": "← रिसर्च पर वापस",
  "schemes.searchPlaceholder": "नाम या कीवर्ड से स्कीम खोजें…",
  "schemes.searchAria": "स्कीम खोजें",
  "schemes.filterAria": "टाइप से स्कीम फ़िल्टर करें",
  "schemes.filter.all": "सभी",
  "schemes.filter.loans": "लोन",
  "schemes.filter.subsidies": "सब्सिडी",
  "schemes.filter.guarantees": "गारंटी",
  "schemes.type.loan": "लोन",
  "schemes.type.subsidy": "सब्सिडी",
  "schemes.type.guarantee": "गारंटी",
  "schemes.type.other": "अन्य",
  "schemes.maxAmount": "अधिकतम राशि",
  "schemes.interestRate": "ब्याज दर",
  "schemes.seeDetails": "विवरण देखें",
  "schemes.showMore": "और दिखाएँ",
  "schemes.showLess": "कम दिखाएँ",
  "schemes.purpose": "उद्देश्य",
  "schemes.eligibility": "पात्रता",
  "schemes.eligibleFor": "पात्र",
  "schemes.requiresUdyam": "Udyam रजिस्ट्रेशन ज़रूरी",
  "schemes.requiresGST": "GST रजिस्ट्रेशन ज़रूरी",
  "schemes.locations": "स्थान",
  "schemes.excluded": "अपात्र",
  "schemes.documents": "ज़रूरी काग़ज़",
  "schemes.verified": "सत्यापित",
  "schemes.source": "स्रोत",
  "schemes.errorTitle": "स्कीमें लोड नहीं हुईं",
  "schemes.retry": "फिर कोशिश करें",
  "schemes.noResults": "आपके फ़िल्टर से कोई स्कीम नहीं मिली",
  "schemes.noResultsDesc": "अलग कीवर्ड या फ़िल्टर आज़माएँ।",
  "schemes.cta.title": "निजी मिलान चाहते हैं?",
  "schemes.cta.desc": "अपने बिज़नेस की डिटेल्स के साथ रिसर्च चलाएँ — साथी आपके लिए सही स्कीमें अपने आप मैच करेगा।",
  "schemes.cta.button": "रिसर्च शुरू करें",
  "footer.aria": "फ़ुटर",
  "footer.tagline": "छोटे कारोबारों के लिए आसान भाषा में मार्केट रिसर्च, ग्रोथ प्लान और सरकारी योजनाओं की जानकारी।",
  "footer.trust": "भरोसा और कानूनी",
  "footer.about": "हमारे बारे में",
  "footer.privacy": "प्राइवेसी",
  "footer.terms": "शर्तें",
  "footer.disclaimer": "अस्वीकरण",
  "footer.dataNote": "आपका सेशन बिना नाम वाली आईडी से सेव होता है और 7 दिन बाद अपने-आप मिट जाता है।",
  "footer.rights": "आपका डेटा आपका है — रिसर्च पेज से कभी भी एक्सपोर्ट या डिलीट करें।",
  "footer.copyright": "© {year} Your AI Business Saathi",
  "footer.analytics": "यूज़ एनालिटिक्स",
  "footer.analyticsNote": "सिर्फ़ बिना नाम वाली गिनती — न कोई निजी डेटा जाता है, न आपके लिखे शब्द।",
  "footer.analyticsOn": "चालू",
  "footer.analyticsOff": "बंद",
  "footer.analyticsToggle": "बिना नाम वाली एनालिटिक्स बदलें",
  "legal.updated": "आख़िरी बार अपडेट {date}",
  "legal.backHome": "होम पर वापस",
  "about.title": "Your AI Business Saathi के बारे में",
  "about.subtitle": "दुकानदारों, रेहड़ी-पटरी वालों, किसानों और छोटे कारोबारियों के लिए आसान भाषा का बिज़नेस सलाहकार।",
  "about.s1.title": "यह क्या है",
  "about.s1.body": "Your AI Business Saathi आपके कारोबार के विवरण को एक काम के रोड-प्लान में बदल देता है: बिज़नेस चेक-अप, कैश-फ़्लो का नज़रिया, वे सरकारी योजनाएँ जिनके लिए आप सचमुच आवेदन कर सकते हैं, और ज़रूरी कागज़। यह उन छोटे कारोबारियों के लिए बना है जिन्हें फ़ॉर्म भरने से ज़्यादा अपनी दुकान के बारे में बताना आसान लगता है।",
  "about.s2.title": "यह कैसे काम करता है",
  "about.s2.body": "आप अपने शब्दों में छोटा बिज़नेस चेक-अप भरते हैं। पात्रता तय होती है कोड से, एक तैयार योजना-डेटा के नियमों के आधार पर — कोई लैंग्वेज मॉडल इसका अंदाज़ा नहीं लगाता। मॉडल सिर्फ़ इन फ़ैसलों के आस-पास की व्याख्या लिखता है, और हर आँकड़ा किसी स्रोत तक जुड़ा रहता है।",
  "about.s3.title": "यह क्या नहीं है",
  "about.s3.body": "हम बैंक, लोन देने वाली संस्था, सरकारी विभाग या वकील नहीं हैं। यहाँ का फ़ैसला सिर्फ़ मार्गदर्शन है, मंज़ूरी नहीं। किसी भी लोन या योजना पर अंतिम फ़ैसला बैंक, विभाग या सरकारी पोर्टल का ही होता है।",
  "about.s4.title": "हमारा योजना-डेटा कहाँ से आता है",
  "about.s4.body": "योजनाओं की जानकारी सिर्फ़ ऐप के अंदर रखे तैयार डेटा से आती है, और हर योजना के साथ उसका सरकारी स्रोत लिंक और आख़िरी जाँच की तारीख़ होती है। आँकड़े बदल सकते हैं — ऐप बताता है कि कौन-सा आँकड़ा कब जाँचा गया और कब दोबारा जाँचना बाकी है।",
  "about.s5.title": "सुधार",
  "about.s5.body": "अगर कोई आँकड़ा पुराना लगे, तो योजना कार्ड पर दिए स्रोत लिंक से सरकारी पोर्टल पर जाकर पुष्टि करें। सरकारी योजनाओं की रकम और दरें बदलती रहती हैं, और सरकारी पोर्टल ही अंतिम सच है।",
  "privacy.title": "प्राइवेसी",
  "privacy.subtitle": "हम क्या सेव करते हैं, क्यों, और उसे कैसे हटाएँ।",
  "privacy.s1.title": "हम क्या सेव करते हैं",
  "privacy.s1.body": "जब आप चेक-अप या रिसर्च चलाते हैं, तो हम आपके जवाब और बनी हुई सलाह को हमारे सर्वर पर एक JSON फ़ाइल में सेव करते हैं, जो आपके ब्राउज़र से बनी बिना नाम वाली सेशन आईडी से जुड़ी होती है। हम आपका नाम, फ़ोन, ईमेल, आधार या कोई सरकारी पहचान नहीं माँगते।",
  "privacy.s2.title": "कोई अकाउंट नहीं, कोई डेटा बिक्री नहीं",
  "privacy.s2.body": "न साइन-अप है, न लॉगिन। हम आपका डेटा नहीं बेचते, और कोई बाहरी विज्ञापन या ट्रैकर नहीं चलाते। ऐप बिना नाम वाली सिर्फ़ गिनती वाली जानकारी दर्ज करता है (जैसे कितने चेक-अप शुरू हुए) ताकि हम इसे बेहतर बना सकें — आप इसे फ़ुटर से बंद कर सकते हैं।",
  "privacy.s3.title": "AI प्रोवाइडर",
  "privacy.s3.body": "व्याख्या लिखने के लिए आपके जवाब किसी लैंग्वेज-मॉडल प्रोवाइडर को भेजे जा सकते हैं — लोकल Ollama, Hugging Face या OpenRouter। जब लोकल मॉडल चलता है, आपका टेक्स्ट हमारे सर्वर से बाहर नहीं जाता। अगर कोई प्रोवाइडर उपलब्ध न हो, तो ऐप अपने नियमों से जवाब देता है और कहीं कुछ नहीं भेजा जाता।",
  "privacy.s4.title": "आवाज़",
  "privacy.s4.body": "अगर आप माइक इस्तेमाल करते हैं, तो आपकी आवाज़ सिर्फ़ लिखे जाने के लिए हमारे सर्वर पर भेजी जाती है। जब कोई क्लाउड वॉइस की सेट न हो, तो लिखना और बोलना लोकल ओपन-सोर्स इंजन करते हैं, इसलिए आपकी आवाज़ किसी बाहरी पक्ष से साझा नहीं होती।",
  "privacy.s5.title": "हम इसे कितने दिन रखते हैं",
  "privacy.s5.body": "सेशन 7 दिन बाद अपने-आप मिट जाते हैं। आप अपना सेशन कभी भी मिटा सकते हैं।",
  "privacy.s6.title": "आपके अधिकार",
  "privacy.s6.body": "आप रिसर्च पेज से अपने सेशन का पूरा डेटा एक्सपोर्ट कर सकते हैं या उसे हमेशा के लिए मिटा सकते हैं। सेशन मिटाने पर उसकी सेव की गई चैट भी मिट जाती है।",
  "privacy.s7.title": "उम्र और सहमति",
  "privacy.s7.body": "यह सेवा उन बड़ों के लिए है जो कारोबार चला रहे हैं या शुरू कर रहे हैं। इसका इस्तेमाल करके आप पुष्टि करते हैं कि आपकी दी जानकारी आपकी अपनी है या उसे साझा करने की आपको अनुमति है।",
  "terms.title": "इस्तेमाल की शर्तें",
  "terms.subtitle": "Your AI Business Saathi इस्तेमाल करने के आसान नियम।",
  "terms.s1.title": "सेवा का इस्तेमाल",
  "terms.s1.body": "आप इस सेवा का इस्तेमाल अपने कारोबार को समझने, सरकारी योजनाएँ देखने और कागज़ तैयार करने के लिए कर सकते हैं। इसे कानून के मुताबिक इस्तेमाल करें और किसी और का निजी डेटा बिना अनुमति दर्ज न करें।",
  "terms.s2.title": "यह पेशेवर सलाह नहीं है",
  "terms.s2.body": "यहाँ कुछ भी वित्तीय, कानूनी, कर या निवेश सलाह नहीं है। यह एक तैयार डेटा और आपके जवाबों पर आधारित सामान्य मार्गदर्शन है। कोई कदम उठाने या भुगतान करने से पहले किसी योग्य पेशेवर या सरकारी विभाग से सलाह लें।",
  "terms.s3.title": "सटीकता",
  "terms.s3.body": "हम योजना-डेटा को सटीक और स्रोत-सहित रखने की पूरी कोशिश करते हैं, पर सरकारी नियम, रकम और दरें बदलती रहती हैं। आवेदन या भुगतान से पहले हर योजना कार्ड पर दिए सरकारी पोर्टल पर मौजूदा जानकारी ज़रूर जाँचें।",
  "terms.s4.title": "उपलब्धता",
  "terms.s4.body": "यह सेवा जैसी है वैसी दी जाती है और इसे कभी भी बदला, रोका या हटाया जा सकता है। लंबे समय तक इस्तेमाल न होने पर फ़्री सेवा को शुरू होने में समय लग सकता है।",
  "terms.s5.title": "ज़िम्मेदारी",
  "terms.s5.body": "कानून की सीमा तक, इस मार्गदर्शन के आधार पर आपके फ़ैसलों या सेवा के इस्तेमाल से होने वाले किसी नुकसान के लिए हम ज़िम्मेदार नहीं हैं।",
  "terms.s6.title": "बदलाव",
  "terms.s6.body": "हम इन शर्तों को अपडेट कर सकते हैं। बदलाव के बाद सेवा का इस्तेमाल जारी रखने का मतलब है कि आप नई शर्तें मानते हैं।",
  "disclaimer.title": "अस्वीकरण",
  "disclaimer.subtitle": "यहाँ कुछ भी करने से पहले इसे पढ़ें।",
  "disclaimer.s1.title": "मार्गदर्शन, मंज़ूरी नहीं",
  "disclaimer.s1.body": "पात्रता का फ़ैसला बताता है कि किसी योजना के छपे नियम आपके कारोबार पर फिट लगते हैं या नहीं। यह लोन का प्रस्ताव या मंज़ूरी नहीं है। आपके आवेदन पर फ़ैसला सिर्फ़ बैंक, विभाग या सरकारी पोर्टल ले सकता है।",
  "disclaimer.s2.title": "आँकड़े बदल सकते हैं",
  "disclaimer.s2.body": "लोन की रकम, सब्सिडी और ब्याज दरें बदलती रहती हैं, कभी-कभी सालाना बजट के साथ। हर योजना अपना स्रोत और आख़िरी जाँच की तारीख़ दिखाती है, और जब समीक्षा बाकी हो तो चेतावनी देती है।",
  "disclaimer.s3.title": "कागज़ों की ज़िम्मेदारी आपकी है",
  "disclaimer.s3.body": "कागज़ों की सूची सिर्फ़ मार्गदर्शन है। सही ज़रूरतें बैंक या पोर्टल से लें, और अपना OTP, पिन या पासवर्ड किसी से साझा न करें।",
  "disclaimer.s4.title": "फ़ायदे की गारंटी नहीं",
  "disclaimer.s4.body": "छपे नियम पूरे करना फ़ायदे की गारंटी नहीं है। मंज़ूरी लोन देने वाले के आकलन और उपलब्ध बजट पर निर्भर करती है।",
  "disclaimer.s5.title": "स्रोत पर जाँचें",
  "disclaimer.s5.body": "आवेदन करने, फ़ीस भरने या कागज़ साझा करने से पहले, योजना कार्ड पर दी सरकारी वेबसाइट पर हर ब्यौरा ज़रूर जाँचें।",
};

const DICTIONARIES: Record<Locale, Record<string, string>> = { en: EN, hi: HI };

type Vars = Record<string, string | number>;

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, key) =>
    key in vars ? String(vars[key]) : match
  );
}

type LocaleContextValue = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, vars?: Vars) => string;
  /** Send the site language to the backend so the advisory matches the UI. */
  backendLang: "en" | "hi";
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

function detectLocale(): Locale {
  if (typeof window === "undefined") return "en";
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "hi" || saved === "en") return saved;
  } catch {
    /* private mode */
  }
  const nav = window.navigator?.language ?? "";
  return nav.toLowerCase().startsWith("hi") ? "hi" : "en";
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  // Starts as "en" so the server and client render identically; the real
  // preference is applied after mount, which avoids a hydration mismatch.
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    setLocaleState(detectLocale());
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* private mode — still works for this session */
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const t = useCallback(
    (key: string, vars?: Vars) => {
      const dict = DICTIONARIES[locale] ?? EN;
      const template = dict[key] ?? EN[key] ?? key;
      return interpolate(template, vars);
    },
    [locale]
  );

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, setLocale, t, backendLang: locale === "hi" ? "hi" : "en" }),
    [locale, setLocale, t]
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useI18n(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    // A component rendered outside the provider (e.g. in an isolated test
    // render) still gets working English rather than a crash.
    const t = (key: string, vars?: Vars) =>
      interpolate(EN[key] ?? key, vars);
    return { locale: "en", setLocale: () => {}, t, backendLang: "en" };
  }
  return ctx;
}