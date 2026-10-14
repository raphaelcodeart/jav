"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { AuthLayout } from "@/components/auth/auth-layout";
import { translateErrorDetail } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [status, setStatus] = useState<"checking" | "success" | "error">(token ? "checking" : "error");
  const [error, setError] = useState<string | null>(null);
  const { t } = useI18n();

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/public/verify-email", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail ? translateErrorDetail(body.detail) : "");
        }
        if (!cancelled) setStatus("success");
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message || null);
          setStatus("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <AuthLayout>

        <div className="text-center space-y-3">
          {status === "checking" && (
            <>
              <div className="w-10 h-10 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto" />
              <h2 className="text-lg font-semibold text-slate-900">{t("verify.checking")}</h2>
            </>
          )}

          {status === "success" && (
            <div className="animate-scale-up space-y-3">
              <svg className="w-12 h-12 text-emerald-600 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <h2 className="text-lg font-semibold text-slate-900">{t("verify.done")}</h2>
              <p className="text-sm text-slate-500">
                {t("verify.doneText")}
              </p>
              <Link
                href="/login"
                className="inline-block w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 py-3 text-sm font-semibold text-white shadow-lg transition duration-300 mt-2"
              >
                {t("verify.goToLogin")}
              </Link>
            </div>
          )}

          {status === "error" && (
            <>
              <svg className="w-12 h-12 text-rose-700 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <h2 className="text-lg font-semibold text-slate-900">{t("reset.invalidLink")}</h2>
              <p className="text-sm text-slate-500">
                {error || t("verify.invalidText")}
              </p>
              <p className="text-xs text-slate-500">
                {t("verify.invalidHint")}
              </p>
              <Link href="/login" className="inline-block text-sm text-brand-600 hover:text-brand-600 transition mt-2">
                {t("forgot.backToLogin")}
              </Link>
            </>
          )}
        </div>
    </AuthLayout>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
