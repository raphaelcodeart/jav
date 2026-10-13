"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { NewVersionBanner } from "@/components/new-version-banner";
import { ThemeProvider } from "@/lib/theme";

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

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <SessionExpiryGuard />
      <NewVersionBanner />
      <QueryProvider>{children}</QueryProvider>
    </ThemeProvider>
  );
}
