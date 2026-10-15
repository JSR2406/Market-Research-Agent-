/**
 * intake.ts — the Business Check-up question set, shared by the stepper and the
 * advisor panel.
 *
 * Two capabilities the old fixed six-chip quiz did not have:
 *
 * 1. **Free text.** Every question keeps its quick chips (fast, low-literacy)
 *    but also accepts an answer typed in the user's own words — "I sell fruit
 *    near the bus stand in Nagpur" beats "Street vendor / cart" for research,
 *    scheme matching and cash-flow.
 * 2. **Branching.** `showIf` / `prompt` let later questions follow from earlier
 *    answers, so a farmer is asked what they grow and how much land they have,
 *    while a service business is asked what service they give.
 *
 * Field ids MUST match `backend/core/intake.py` — that module owns the canonical
 * snippet, the gap detection and the follow-up questions, and it only accepts
 * the ids declared there. `tests/test_intake.py` fails if the two drift apart.
 */

/**
 * Hindi chip labels. An answer is stored as the label the user actually saw,
 * so a Hindi session stores Hindi text — which is also what reaches the
 * eligibility engine, where it classifies correctly for the same reason.
 * Official terms (Udyam, GST) stay in English.
 */
export const OPTION_LABELS_HI: Record<string, string> = {
  "Shop / stall": "दुकान / स्टॉल",
  "Street vendor / cart": "रेहड़ी-पटरी / ठेला",
  "Home-based / freelance": "घर से काम / फ्रीलांस",
  "Service / repair": "सेवा / मरम्मत",
  "Farm / dairy": "खेती / डेयरी",
  "Something else": "कुछ और",
  "Just started (under 3 months)": "अभी शुरू किया (3 महीने से कम)",
  "3–12 months": "3–12 महीने",
  "1–3 years": "1–3 साल",
  "3+ years": "3 साल से ज़्यादा",
  "Under ₹10k": "₹10,000 से कम",
  "₹10k–25k": "₹10,000–25,000",
  "₹25k–50k": "₹25,000–50,000",
  "₹50k+": "₹50,000 से ज़्यादा",
  "No, first time": "नहीं, पहली बार",
  "Yes, MUDRA": "हाँ, मुद्रा लोन",
  "Yes, bank loan": "हाँ, बैंक लोन",
  "Only family / friends": "सिर्फ़ परिवार / दोस्तों से",
  "Money to grow": "बढ़ने के लिए पैसा",
  "More customers": "ज़्यादा ग्राहक",
  "Documents / licence help": "काग़ज़ / लाइसेंस में मदद",
  "A clear plan": "साफ़ प्लान",
  Maharashtra: "महाराष्ट्र",
  Gujarat: "गुजरात",
  Rajasthan: "राजस्थान",
  "Uttar Pradesh": "उत्तर प्रदेश",
  Bihar: "बिहार",
  "West Bengal": "पश्चिम बंगाल",
  "Tamil Nadu": "तमिलनाडु",
  Karnataka: "कर्नाटक",
  "Telangana / AP": "तेलंगाना / आंध्र प्रदेश",
  "MP / Chhattisgarh": "मध्य प्रदेश / छत्तीसगढ़",
  "Another state": "दूसरा राज्य",
  "Yes, registered": "हाँ, रजिस्टर्ड है",
  "No, not yet": "नहीं, अभी नहीं",
  "Working on it": "काम चल रहा है",
};

/** The label to show for a chip in the active language. */
export function optionLabel(label: string, lang: string): string {
  return lang === "hi" ? OPTION_LABELS_HI[label] ?? label : label;
}

/** Every label a Hindi session has ever stored — used by migrateIntake(). */
export const HINDI_LABELS = new Set(Object.values(OPTION_LABELS_HI));

export type IntakeAnswers = Record<string, string>;

export type IntakeOption = { value: string; label: string };

export type IntakeQuestion = {
  id: string;
  /** The question as most users see it. */
  q: string;
  /** Placeholder for the "or type your own" box. */
  hint: string;
  /** Quick chips. Absent = a pure free-text question. */
  options?: IntakeOption[];
  /** Branching: only ask this question when the earlier answers call for it. */
  showIf?: (answers: IntakeAnswers) => boolean;
  /** Branching: reword the question based on the business already described. */
  prompt?: (answers: IntakeAnswers) => string;
};

/** Label shown for an answer the user picked from the chips. */
export function answerLabel(answers: IntakeAnswers, id: string): string {
  return (answers[id] || "").trim();
}

// Strong business-type signals only. Bare animal/product words are excluded:
// someone who "makes goat milk soap from my home" is a home-based producer, not
// a farmer — asking them what they grow would read as nonsense. Must stay in
// sync with `_FARM_RE` / `_SERVICE_RE` in backend/core/intake.py.
const isFarm = (a: IntakeAnswers) =>
  /farm|farmland|dairy|cattle|poultry|goat\s*farm|cow\s*farm|chicken\s*farm|agr[iie]?|agriculture|kheti|khet|zameen|kisan|पशुपालन|पालन|डेयरी|खेती|किसान|खेत|ज़मीन/i.test(
    a.business || ""
  );
const isService = (a: IntakeAnswers) =>
  /service|repair|tuition|home[- ]?based|home\s*business|freelance|salon|tailor|सेवा|सिलाई|ट्यूशन|फ्रीलांस|घर\s*पर/i.test(
    a.business || ""
  );

export const INTAKE_QUESTIONS: IntakeQuestion[] = [
  {
    id: "business",
    q: "What kind of business is this?",
    hint: "e.g. fruit cart near the bus stand, tailoring work from home",
    options: [
      { value: "kiosk", label: "Shop / stall" },
      { value: "vendor", label: "Street vendor / cart" },
      { value: "home", label: "Home-based / freelance" },
      { value: "service", label: "Service / repair" },
      { value: "farm", label: "Farm / dairy" },
      { value: "other", label: "Something else" },
    ],
  },
  {
    id: "offering",
    q: "What exactly do you sell or do?",
    hint: "e.g. vegetables, milk, mobile accessories",
    showIf: (a) => !!a.business,
    prompt: (a) =>
      isFarm(a)
        ? "What do you grow or sell?"
        : isService(a)
          ? "What service or work do you do?"
          : "What exactly do you sell or do?",
  },
  {
    id: "scale",
    q: "Roughly how big is the business?",
    hint: "e.g. about ₹3,000 a day, 10 cows, 2 acres",
    showIf: (a) => !!a.business,
    prompt: (a) =>
      isFarm(a)
        ? "How much land, or how many animals do you have?"
        : "Roughly how much do you sell in a day?",
  },
  {
    id: "age",
    q: "How long has it been running?",
    hint: "e.g. started 4 months ago",
    options: [
      { value: "new", label: "Just started (under 3 months)" },
      { value: "ramp", label: "3–12 months" },
      { value: "growing", label: "1–3 years" },
      { value: "settled", label: "3+ years" },
    ],
  },
  {
    id: "earnings",
    q: "Roughly how much do you earn in a month?",
    hint: "e.g. 25,000 — an honest rough figure is fine",
    options: [
      { value: "low", label: "Under ₹10k" },
      { value: "mid", label: "₹10k–25k" },
      { value: "good", label: "₹25k–50k" },
      { value: "strong", label: "₹50k+" },
    ],
  },
  {
    id: "location",
    q: "Where is your business?",
    hint: "e.g. Nagpur, Maharashtra",
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
  {
    id: "loan",
    q: "Have you taken a business loan before?",
    hint: "e.g. took ₹50,000 from a bank 2 years ago",
    options: [
      { value: "none", label: "No, first time" },
      { value: "mudra", label: "Yes, MUDRA" },
      { value: "bank", label: "Yes, bank loan" },
      { value: "family", label: "Only family / friends" },
    ],
  },
  {
    id: "need",
    q: "What do you need most right now?",
    hint: "e.g. need money for a new freezer",
    options: [
      { value: "capital", label: "Money to grow" },
      { value: "customers", label: "More customers" },
      { value: "licence", label: "Documents / licence help" },
      { value: "plan", label: "A clear plan" },
    ],
  },
  {
    id: "registered",
    q: "Is the business registered (Udyam / GST)?",
    hint: "e.g. I have the Udyam certificate",
    options: [
      { value: "yes", label: "Yes, registered" },
      { value: "no", label: "No, not yet" },
      { value: "working", label: "Working on it" },
    ],
    // Only worth asking when it changes the advice: a brand-new business or one
    // chasing money or paperwork is the case where registration is the next step.
    showIf: (a) =>
      !!a.business &&
      (/just started|under 3|^new$/i.test(a.age || "") ||
        /money|paper|licence|document|पैसा|कागज़|कागज|लाइसेंस/i.test(a.need || "")),
  },
];

/** Field ids in display order — mirrors `FIELD_IDS` in backend/core/intake.py. */
export const INTAKE_IDS: string[] = INTAKE_QUESTIONS.map((q) => q.id);

/**
 * Order in which Saathi asks for what is still missing. Mirrors `GAP_PRIORITY`
 * in backend/core/intake.py — business identity first, because every downstream
 * decision depends on it.
 */
export const GAP_PRIORITY: string[] = [
  "business",
  "offering",
  "earnings",
  "location",
  "age",
  "loan",
  "need",
  "scale",
  "registered",
];

const QUESTION_BY_ID = new Map(INTAKE_QUESTIONS.map((q) => [q.id, q]));

/** The questions that apply right now, given the answers so far. */
export function activeQuestions(answers: IntakeAnswers): IntakeQuestion[] {
  return INTAKE_QUESTIONS.filter((q) => !q.showIf || q.showIf(answers));
}

/** The wording to show for a question, honouring branching. */
export function questionPrompt(question: IntakeQuestion, answers: IntakeAnswers): string {
  return question.prompt ? question.prompt(answers) : question.q;
}

export function intakeProgress(answers: IntakeAnswers): { answered: number; total: number } {
  const active = activeQuestions(answers);
  return { answered: active.filter((q) => (answers[q.id] || "").trim()).length, total: active.length };
}

/** Field ids still unanswered, most useful first. */
export function missingIntakeFields(answers: IntakeAnswers): string[] {
  return GAP_PRIORITY.filter((id) => !(answers[id] || "").trim());
}

/** Human label for a field, used in the "still to tell me" line. */
export function intakeFieldLabel(id: string): string {
  switch (id) {
    case "business":
      return "your business";
    case "offering":
      return "what you sell";
    case "earnings":
      return "monthly earning";
    case "location":
      return "location";
    case "age":
      return "time running";
    case "loan":
      return "past borrowing";
    case "need":
      return "main need";
    case "scale":
      return "size of the business";
    case "registered":
      return "registration";
    default:
      return id;
  }
}

/** "Still to tell me: monthly earning, location" — shown on the advisor panel. */
export function describeMissingIntake(answers: IntakeAnswers): string {
  const missing = missingIntakeFields(answers);
  if (!missing.length) return "";
  const shown = missing.slice(0, 4).map(intakeFieldLabel);
  const more = missing.length > 4 ? ` +${missing.length - 4} more` : "";
  return `Still to tell me: ${shown.join(", ")}${more}`;
}

/** True when the user typed their own words rather than picking a chip. */
export function isCustomAnswer(answers: IntakeAnswers, question: IntakeQuestion): boolean {
  const answer = (answers[question.id] || "").trim();
  if (!answer || !question.options) return !!answer;
  return !question.options.some((o) => o.label === answer);
}

/**
 * Read answers written by an older build, which stored opaque chip codes
 * ("kiosk", "mh") instead of the label the user actually saw.
 */
const LEGACY_CODES: Record<string, string> = {
  kiosk: "Shop / stall",
  vendor: "Street vendor / cart",
  home: "Home-based / freelance",
  service: "Service / repair",
  farm: "Farm / dairy",
  new: "Just started (under 3 months)",
  ramp: "3–12 months",
  growing: "1–3 years",
  settled: "3+ years",
  low: "Under ₹10k",
  mid: "₹10k–25k",
  good: "₹25k–50k",
  strong: "₹50k+",
  none: "No, first time",
  mudra: "Yes, MUDRA",
  bank: "Yes, bank loan",
  family: "Only family / friends",
  capital: "Money to grow",
  customers: "More customers",
  licence: "Documents / licence help",
  plan: "A clear plan",
  mh: "Maharashtra",
  gj: "Gujarat",
  rj: "Rajasthan",
  up: "Uttar Pradesh",
  br: "Bihar",
  wb: "West Bengal",
  tn: "Tamil Nadu",
  ka: "Karnataka",
  ts: "Telangana / AP",
  mp: "MP / Chhattisgarh",
  other: "Another state",
};

/** Coerce anything read from localStorage into the current shape. */
export function migrateIntake(raw: unknown): IntakeAnswers {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const out: IntakeAnswers = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!QUESTION_BY_ID.has(key)) continue;
    if (typeof value !== "string") continue;
    const text = value.trim();
    if (!text) continue;
    // Legacy chip codes ("kiosk") and the *other* language's label both map back
    // to a canonical label, so switching language never loses an answer.
    const canonical = LEGACY_CODES[text] ?? text;
    out[key] = toCanonicalLabel(canonical);
  }
  return out;
}

const ALL_OPTION_LABELS = new Set(
  INTAKE_QUESTIONS.flatMap((q) => (q.options ?? []).map((o) => o.label))
);

function toCanonicalLabel(label: string): string {
  for (const english of ALL_OPTION_LABELS) {
    if (OPTION_LABELS_HI[english] === label) return english;
  }
  return label;
}

/** One-line summary for the UI (the backend builds its own canonical snippet). */
export function buildIntakeSummary(answers: IntakeAnswers): string {
  const active = activeQuestions(answers);
  const parts = active
    .filter((q) => (answers[q.id] || "").trim())
    .map((q) => answers[q.id].trim());
  return parts.length ? parts.join(" · ") : "";
}