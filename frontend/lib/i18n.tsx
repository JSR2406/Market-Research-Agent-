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
  // ── brand / hero ────────────────────────────────────────────────────────
  "brand.name": "Your AI Business Saathi",
  "brand.tagline": "Market research, growth planning & schemes for small businesses",
  "hero.kicker":
    "Market research, growth planning & government schemes for small businesses",
  "hero.sub":
    "Describe your business in plain language — get live market research, a clear business road-map, matched government schemes, and a loan-readiness checklist in under 60 seconds.",

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
  "quiz.staysLocal": "Nothing is shared anywhere — it stays on your device.",
  "quiz.liveTitle": "Your business type: {label}",
  "quiz.openForYou": "Open for you: {list}",
  "quiz.filledIn": "Details filled in: {pct}%",

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
    "MUDRA, PMEGP, CGTMSE and more — mapped to your business and stage, not a fixed list of a few schemes.",
  "usps.4.title": "Works Offline & Free",
  "usps.4.text":
    "Runs on free + local AI models. No subscription, no paywall — and it still answers even when the internet drops.",
  "usps.5.title": "Whole site in your language",
  "usps.5.text":
    "Switch the entire site to Hindi — check-up, verdicts, ledger, everything — and the advisor answers in the same language, even offline.",
  "usps.6.title": "Your Data Stays Yours",
  "usps.6.text":
    "Stored locally on your device, with one-tap export and full delete (GDPR-aligned). Nothing is sold to anyone.",

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
};

const HI: Record<string, string> = {
  "brand.name": "आपका AI बिज़नेस साथी",
  "brand.tagline": "छोटे बिज़नेस के लिए मार्केट रिसर्च, ग्रोथ प्लान और स्कीमें",

  "hero.kicker": "छोटे बिज़नेस के लिए मार्केट रिसर्च, ग्रोथ प्लान और सरकारी स्कीमें",
  "hero.sub":
    "अपने बिज़नेस को आसान भाषा में लिखिए — लाइव मार्केट रिसर्च, साफ़ बिज़नेस प्लान, आपकी स्कीमें और लोन की तैयारी की चेकलिस्ट 60 सेकंड में।",

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
  "quiz.staysLocal": "कुछ भी कहीं नहीं भेजा जाता — सब आपके फ़ोन पर ही रहता है।",
  "quiz.liveTitle": "आपका बिज़नेस: {label}",
  "quiz.openForYou": "आपके लिए खुली: {list}",
  "quiz.filledIn": "जानकारी भरी: {pct}%",

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
    "MUDRA, PMEGP, CGTMSE और दूसरी — आपके बिज़नेस और उसकी अवस्था के हिसाब से चुनी गईं।",
  "usps.4.title": "बिना इंटरनेट भी चलता है",
  "usps.4.text":
    "मुफ़्त और लोकल AI मॉडल पर चलता है। कोई सब्सक्रिप्शन नहीं — और इंटरनेट चले जाए तब भी जवाब देता है।",
  "usps.5.title": "पूरी साइट आपकी भाषा में",
  "usps.5.text":
    "चेक-अप, स्कीम, लिस्ट — पूरी साइट हिंदी में बदलिए, और साथी उसी भाषा में जवाब देगा, बिना इंटरनेट के भी।",
  "usps.6.title": "आपका डेटा आपका ही",
  "usps.6.text":
    "आपके फ़ोन पर सुरक्षित — एक टैप में एक्सपोर्ट और पूरा डिलीट। किसी को कुछ नहीं बेचा जाता।",

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

  "live.title": "आवाज़ वाला सलाहकार",
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