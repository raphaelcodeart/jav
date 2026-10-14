"use client";

import { useState } from "react";
import Link from "next/link";
import { AuthLayout } from "@/components/auth/auth-layout";
import { translateErrorDetail } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { t } = useI18n();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/public/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ? translateErrorDetail(body.detail) : t("forgot.failed"));
      }
      setSubmitted(true);
    } catch (err: any) {
      setError(err.message || t("forgot.failed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>

        <div className="">
          {submitted ? (
            <div className="text-center space-y-3">
              <svg className="w-12 h-12 text-emerald-600 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <h2 className="text-lg font-semibold text-slate-900">{t("forgot.checkEmail")}</h2>
              <p className="text-sm text-slate-500">
                {t("forgot.sentText")}
              </p>
              <Link href="/login" className="inline-block text-sm text-brand-600 hover:text-brand-600 transition mt-2">
                {t("forgot.backToLogin")}
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <h2 className="text-xl font-semibold text-slate-800">{t("forgot.title")}</h2>
                <p className="text-sm text-slate-500 mt-1">
                  {t("forgot.subtitle")}
                </p>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Email</label>
                <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl glass-input px-4 py-3 text-sm focus:border-brand-500" />
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-700 text-xs">{error}</div>
              )}

              <button type="submit" disabled={submitting}
                className="w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 py-3 text-sm font-semibold text-white shadow-lg transition-all duration-300 disabled:opacity-50 cursor-pointer">
                {submitting ? t("forgot.sending") : t("forgot.submit")}
              </button>

              <Link href="/login" className="block text-center text-xs text-slate-400 hover:text-slate-900 transition">
                {t("forgot.backToLogin")}
              </Link>
            </form>
          )}
        </div>
    </AuthLayout>
  );
}
