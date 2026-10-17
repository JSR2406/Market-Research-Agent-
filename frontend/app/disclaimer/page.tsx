"use client";

import LegalPage from "@/components/LegalPage";

const UPDATED = "2026-10-17";

export default function DisclaimerPage() {
  return (
    <LegalPage
      titleKey="disclaimer.title"
      subtitleKey="disclaimer.subtitle"
      updated={UPDATED}
      sections={[
        { titleKey: "disclaimer.s1.title", bodyKey: "disclaimer.s1.body" },
        { titleKey: "disclaimer.s2.title", bodyKey: "disclaimer.s2.body" },
        { titleKey: "disclaimer.s3.title", bodyKey: "disclaimer.s3.body" },
        { titleKey: "disclaimer.s4.title", bodyKey: "disclaimer.s4.body" },
        { titleKey: "disclaimer.s5.title", bodyKey: "disclaimer.s5.body" },
      ]}
    />
  );
}
