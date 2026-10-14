"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useEffect, useState } from "react";
import { NewVersionBanner } from "@/components/new-version-banner";
import { ToastProvider } from "@/components/ui/toast";
import type { Locale } from "@/lib/i18n/config";
import { I18nProvider } from "@/lib/i18n/provider";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient());
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** Session 85: when the BFF proxy says the session is over for good
 *  (`X-Session-Expired`, app/api/proxy), go to the login page -- whichever
 *  button made the call. One place instead of every fetch in the app, which
 *  is why it wraps window.fetch. A full page load, not router.push: it must
 *  work even on a page left open across a deploy, whose client code no
 *  longer matches the server. */
function SessionExpiryGuard() {
  useEffect(() => {
    const original = window.fetch;
    let leaving = false;
    window.fetch = async (...args: Parameters<typeof fetch>) => {
      const res = await original(...args);
      if (!leaving && res.status === 401 && res.headers.get("X-Session-Expired") === "1") {
        leaving = true;
        window.location.assign("/login?sessione=scaduta");
      }
      return res;
    };
    return () => {
      window.fetch = original;
    };
  }, []);
  return null;
}

export function AppProviders({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    // reducedMotion="user": every motion component in the app honours the
    // OS "reduce motion" setting without each one having to check it.
    <I18nProvider initialLocale={locale}>
      <MotionConfig reducedMotion="user">
        <SessionExpiryGuard />
        <NewVersionBanner />
        <QueryProvider>
          <ToastProvider>{children}</ToastProvider>
        </QueryProvider>
      </MotionConfig>
    </I18nProvider>
  );
}
