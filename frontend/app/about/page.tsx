"use client";

import LegalPage from "@/components/LegalPage";

const UPDATED = "2026-10-17";

export default function AboutPage() {
  return (
    <LegalPage
      titleKey="about.title"
      subtitleKey="about.subtitle"
      updated={UPDATED}
      sections={[
        { titleKey: "about.s1.title", bodyKey: "about.s1.body" },
        { titleKey: "about.s2.title", bodyKey: "about.s2.body" },
        { titleKey: "about.s3.title", bodyKey: "about.s3.body" },
        { titleKey: "about.s4.title", bodyKey: "about.s4.body" },
        { titleKey: "about.s5.title", bodyKey: "about.s5.body" },
      ]}
    />
  );
}
