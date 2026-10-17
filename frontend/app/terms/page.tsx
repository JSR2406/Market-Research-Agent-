"use client";

import LegalPage from "@/components/LegalPage";

const UPDATED = "2026-10-17";

export default function TermsPage() {
  return (
    <LegalPage
      titleKey="terms.title"
      subtitleKey="terms.subtitle"
      updated={UPDATED}
      sections={[
        { titleKey: "terms.s1.title", bodyKey: "terms.s1.body" },
        { titleKey: "terms.s2.title", bodyKey: "terms.s2.body" },
        { titleKey: "terms.s3.title", bodyKey: "terms.s3.body" },
        { titleKey: "terms.s4.title", bodyKey: "terms.s4.body" },
        { titleKey: "terms.s5.title", bodyKey: "terms.s5.body" },
        { titleKey: "terms.s6.title", bodyKey: "terms.s6.body" },
      ]}
    />
  );
}
