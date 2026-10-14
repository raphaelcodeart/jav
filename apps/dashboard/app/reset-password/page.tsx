"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { AuthLayout } from "@/components/auth/auth-layout";
import { PasswordInput } from "@/components/password-input";
import { translateErrorDetail } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const { t } = useI18n();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError(t("reset.mismatch"));
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/api/public/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ? translateErrorDetail(body.detail) : t("reset.failed"));
      }
      setSuccess(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (err: any) {
      setError(err.message || t("reset.failed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>

        <div className="">
          {!token ? (
            <div className="text-center space-y-3">
              <h2 className="text-lg font-semibold text-slate-900">{t("reset.invalidLink")}</h2>
              <p className="text-sm text-slate-500">
                {t("reset.invalidLinkText")}
              </p>
              <Link href="/forgot-password" className="inline-block text-sm text-brand-600 hover:text-brand-600 transition mt-2">
                {t("reset.requestNew")}
              </Link>
            </div>
          ) : success ? (
            <div className="text-center space-y-3 animate-scale-up">
              <svg className="w-12 h-12 text-emerald-600 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <h2 className="text-lg font-semibold text-slate-900">{t("reset.done")}</h2>
              <p className="text-sm text-slate-500">{t("reset.redirecting")}</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <h2 className="text-xl font-semibold text-slate-800">{t("reset.title")}</h2>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase tracking-wider">{t("reset.newPassword")}</label>
                <PasswordInput required minLength={8} autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                  placeholder={t("reset.min8")}
                  className="w-full rounded-xl glass-input px-4 py-3 text-sm focus:border-brand-500" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase tracking-wider">{t("reset.repeat")}</label>
                <PasswordInput required minLength={8} autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder={t("reset.repeatPlaceholder")}
                  className={`w-full rounded-xl glass-input px-4 py-3 text-sm focus:border-brand-500 ${
                    confirmPassword && newPassword !== confirmPassword ? "border-rose-500/50" : ""
                  }`} />
                {confirmPassword && newPassword !== confirmPassword && (
                  <p className="text-[11px] text-rose-700">{t("reset.mismatchShort")}</p>
                )}
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-700 text-xs">{error}</div>
              )}

              <button type="submit" disabled={submitting}
                className="w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 py-3 text-sm font-semibold text-white shadow-lg transition-all duration-300 disabled:opacity-50 cursor-pointer">
                {submitting ? t("reset.saving") : t("reset.submit")}
              </button>
            </form>
          )}
        </div>
    </AuthLayout>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
