import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "GrameenAI Advisor — Loan Readiness for Micro-Entrepreneurs",
  description:
    "Multi-agent AI advisory that turns a plain-language business description into a loan readiness report, matched government schemes, and a document checklist.",
  keywords: ["loan readiness", "MUDRA", "CGTMSE", "PMEGP", "micro-entrepreneur", "MSME schemes", "financial advisory"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} h-full`} suppressHydrationWarning>
      <body className="min-h-full flex flex-col" suppressHydrationWarning>{children}</body>
    </html>
  );
}
