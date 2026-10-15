import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { LocaleProvider } from "@/lib/i18n";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Your AI Business Saathi — Market Research, Growth Plans & Government Schemes for Small Businesses",
  description:
    "Market research, growth planning and government-scheme guidance for small businesses — describe your shop in plain language and get a business road-plan with matched schemes and a loan-readiness check.",
  keywords: ["market research", "business advisor", "small business", "loan readiness", "MUDRA", "CGTMSE", "PMEGP", "micro-entrepreneur", "MSME schemes", "government schemes"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // `lang` is also kept in sync by the provider on every language change, so
    // screen readers announce the right language for the whole page.
    <html lang="en" className={`${inter.variable} h-full`} suppressHydrationWarning>
      <body className="min-h-full flex flex-col" suppressHydrationWarning>
        <LocaleProvider>{children}</LocaleProvider>
      </body>
    </html>
  );
}
