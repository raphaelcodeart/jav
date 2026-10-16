import type { Metadata, Viewport } from "next";
import { Audiowide, Inter } from "next/font/google";
import "./globals.css";
import { AppProviders } from "@/app/providers";
import { CookieBanner } from "@/components/legal/cookie-banner";
import { getLocale } from "@/lib/i18n/server";
import { makeTranslator } from "@/lib/i18n/translate";

// Inter for everything you read; Audiowide -- rounded, techno, the same family
// of shapes as the club's logo lettering -- for titles and the big numbers.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const audiowide = Audiowide({ subsets: ["latin"], weight: "400", variable: "--font-audiowide" });

export async function generateMetadata(): Promise<Metadata> {
  const t = makeTranslator(await getLocale());
  return {
    title: "Jav · Judo Arte e Vida",
    description: t("meta.description"),
  };
}

export const viewport: Viewport = {
  themeColor: "#e43f21",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  return (
    <html lang={locale} className={`${inter.variable} ${audiowide.variable}`}>
      <body className="min-h-screen antialiased text-ink-900">
        <div className="dojo-backdrop" aria-hidden="true" />
        <AppProviders locale={locale}>{children}<CookieBanner /></AppProviders>
      </body>
    </html>
  );
}
