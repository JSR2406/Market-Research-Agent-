"use client";

import LegalPage from "@/components/LegalPage";

const UPDATED = "2026-10-17";

export default function PrivacyPage() {
  return (
    <LegalPage
      titleKey="privacy.title"
      subtitleKey="privacy.subtitle"
      updated={UPDATED}
      sections={[
        { titleKey: "privacy.s1.title", bodyKey: "privacy.s1.body" },
        { titleKey: "privacy.s2.title", bodyKey: "privacy.s2.body" },
        { titleKey: "privacy.s3.title", bodyKey: "privacy.s3.body" },
        { titleKey: "privacy.s4.title", bodyKey: "privacy.s4.body" },
        { titleKey: "privacy.s5.title", bodyKey: "privacy.s5.body" },
        { titleKey: "privacy.s6.title", bodyKey: "privacy.s6.body" },
        { titleKey: "privacy.s7.title", bodyKey: "privacy.s7.body" },
      ]}
    />
  );
}
