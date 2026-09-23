import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "GrameenAI Advisor — Market Research & Business Advisor for Micro-Entrepreneurs",
  description:
    "Multi-agent AI research and advisory that turns a plain-language business description into market research, a business road-map, matched government schemes, and a loan-readiness checklist.",
  keywords: ["market research", "business advisor", "loan readiness", "MUDRA", "CGTMSE", "PMEGP", "micro-entrepreneur", "MSME schemes", "financial advisory"],
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
