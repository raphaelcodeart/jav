"use client";

import { useEffect } from "react";
import { useI18n } from "@/lib/i18n/provider";

/** Root error boundary -- without this, ANY uncaught client-side exception
    anywhere in the app (a bad API shape, a null a modal didn't expect, ...)
    unmounts the whole page silently: no error.tsx existed before this, so
    Next's default fallback left just the app's own dark background visible,
    with no button and no indication anything had gone wrong ("the screen
    goes dark and nothing opens"). This makes a crash visible and
    recoverable instead of a silent dead end. */
export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { t } = useI18n();
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-md w-full glass-card rounded-2xl p-8 border-slate-300 bg-white text-center">
        <svg className="w-12 h-12 text-rose-400 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h1 className="text-lg font-bold text-slate-900 mb-2">{t("acct.error.title")}</h1>
        <p className="text-sm text-slate-500 mb-6">
          {t("acct.error.text")}
        </p>
        <button
          onClick={reset}
          className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 text-sm font-semibold text-white shadow-lg transition cursor-pointer"
        >
          {t("common.retry")}
        </button>
      </div>
    </div>
  );
}
