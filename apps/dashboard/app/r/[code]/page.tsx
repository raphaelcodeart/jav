"use client";

import { use, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AuthLayout } from "@/components/auth/auth-layout";
import { PasswordInput } from "@/components/password-input";
import { translateErrorDetail } from "@/lib/api-error";
import type { PromoterCodeRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

// Labels: net.newCust.kind.<code>
const KINDS = ["PRIVATE", "SOLE_PROPRIETOR", "COMPANY", "CONDOMINIUM"];

const PRIVATE_LIKE = new Set(["PRIVATE", "SOLE_PROPRIETOR"]);

async function resolveReferralCode(code: string, organizationId: string, invalidMessage: string): Promise<PromoterCodeRead> {
  // `org` is optional: without it the API resolves the installation's club.
  const query = organizationId ? `?org=${encodeURIComponent(organizationId)}` : "";
  const res = await fetch(`/api/public/referral/${encodeURIComponent(code)}${query}`);
  if (!res.ok) throw new Error(invalidMessage);
  return res.json();
}

export default function ReferralLandingPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const organizationId = searchParams.get("org") ?? "";
  const productId = searchParams.get("product");
  const productName = searchParams.get("product_name");
  const router = useRouter();

  const { data: promoterCode, error: resolveErrorObj, isLoading: resolving } = useQuery({
    queryKey: ["referral", "resolve", code, organizationId],
    queryFn: () => resolveReferralCode(code, organizationId, t("net.ref.invalidLink")),
    retry: false,
  });
  const resolveError = resolveErrorObj instanceof Error ? resolveErrorObj.message : null;

  const [kind, setKind] = useState("PRIVATE");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [phone, setPhone] = useState("");
  const [acceptPrivacy, setAcceptPrivacy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    if (password !== passwordConfirm) {
      setSubmitError(t("reset.mismatch"));
      return;
    }
    if (!acceptPrivacy) {
      setSubmitError(t("net.ref.mustAccept"));
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/api/public/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId || undefined,
          referral_code: code,
          email,
          password,
          kind,
          first_name: PRIVATE_LIKE.has(kind) ? firstName : null,
          last_name: PRIVATE_LIKE.has(kind) ? lastName : null,
          company_name: PRIVATE_LIKE.has(kind) ? null : companyName,
          phone: phone || null,
          accept_privacy: acceptPrivacy,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ? translateErrorDetail(body.detail) : t("net.ref.failed"));
      }
      setSuccess(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (err: any) {
      setSubmitError(err.message || t("net.ref.failed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>

        {resolving && (
          <div className="text-center">
            <p className="text-sm text-slate-500">{t("net.ref.checking")}</p>
          </div>
        )}

        {!resolving && resolveError && (
          <div className="text-center border-rose-500/20">
            <svg className="w-12 h-12 text-rose-700 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h2 className="text-lg font-semibold text-slate-900 mb-2">{t("net.ref.invalidTitle")}</h2>
            <p className="text-sm text-slate-500">{resolveError}</p>
            <p className="text-xs text-slate-500 mt-4">
              {t("net.ref.invalidHint")}
            </p>
          </div>
        )}

        {!resolving && promoterCode && !success && (
          <div className="">
            <div className="mb-6 text-center">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-brand-500/10 text-brand-600 border border-brand-500/20">
                {promoterCode.promoter_display_name
                  ? t("net.ref.invitedBy", { name: promoterCode.promoter_display_name })
                  : t("net.ref.invitedGeneric")}
              </span>
              {productName && (
                <div className="mt-3">
                  <p className="text-xs text-slate-500">{t("net.ref.recommended")}</p>
                  <p className="text-sm font-semibold text-slate-900">{productName}</p>
                  {productId && <p className="font-mono text-[10px] text-slate-500">{productId}</p>}
                </div>
              )}
              <h1 className="text-xl font-bold text-slate-900 mt-2">{t("net.ref.title")}</h1>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("net.ref.kind")}</label>
                <select value={kind} onChange={(e) => setKind(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-white focus:border-brand-500">
                  {KINDS.map((code2) => (
                    <option key={code2} value={code2}>{t.dyn(`net.newCust.kind.${code2}`, code2)}</option>
                  ))}
                </select>
              </div>

              {PRIVATE_LIKE.has(kind) ? (
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-600 uppercase block">{t("signup.firstName")}</label>
                    <input required value={firstName} onChange={(e) => setFirstName(e.target.value)}
                      className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-600 uppercase block">{t("signup.lastName")}</label>
                    <input required value={lastName} onChange={(e) => setLastName(e.target.value)}
                      className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-600 uppercase block">{t("net.newCust.companyName")}</label>
                  <input required value={companyName} onChange={(e) => setCompanyName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
                </div>
              )}

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("signup.phone")}</label>
                <input value={phone} onChange={(e) => setPhone(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("net.newCust.email")}</label>
                <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("net.ref.password")}</label>
                <PasswordInput required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder={t("reset.min8")}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-600 uppercase block">{t("reset.repeat")}</label>
                <PasswordInput required minLength={8} autoComplete="new-password" value={passwordConfirm} onChange={(e) => setPasswordConfirm(e.target.value)}
                  placeholder={t("reset.repeatPlaceholder")}
                  className={`w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500 ${
                    passwordConfirm && password !== passwordConfirm ? "border-rose-500/50" : ""
                  }`} />
                {passwordConfirm && password !== passwordConfirm && (
                  <p className="text-[11px] text-rose-700">{t("reset.mismatchShort")}</p>
                )}
              </div>

              <label className="flex items-start gap-2.5 text-xs text-slate-500 cursor-pointer pt-1">
                <input
                  type="checkbox"
                  checked={acceptPrivacy}
                  onChange={(e) => setAcceptPrivacy(e.target.checked)}
                  className="mt-0.5 w-4 h-4 rounded border-slate-200 accent-brand-500 shrink-0"
                />
                <span>
                  {/* {privacy} / {terms} in the sentence become the two links. */}
                  {t("net.ref.consent").split(/(\{privacy\}|\{terms\})/).map((part, i) =>
                    part === "{privacy}" ? (
                      <a key={i} href="/privacidade" target="_blank" className="font-semibold text-brand-700 underline">{t("net.ref.privacyLink")}</a>
                    ) : part === "{terms}" ? (
                      <a key={i} href="/termos" target="_blank" className="font-semibold text-brand-700 underline">{t("net.ref.termsLink")}</a>
                    ) : (
                      part
                    ),
                  )}
                </span>
              </label>

              {submitError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-700 text-xs">{submitError}</div>
              )}

              <button type="submit" disabled={submitting || !acceptPrivacy}
                className="w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 py-3 text-sm font-semibold text-white shadow-lg transition duration-300 disabled:opacity-50 cursor-pointer mt-2">
                {submitting ? t("net.ref.submitting") : t("net.ref.submit")}
              </button>
            </form>
          </div>
        )}

        {success && (
          <div className="text-center border-emerald-500/20 animate-scale-up">
            <svg className="w-12 h-12 text-emerald-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <h2 className="text-lg font-semibold text-slate-900 mb-2">{t("net.ref.doneTitle")}</h2>
            <p className="text-sm text-slate-500 mb-2">
              {t("net.ref.doneText")}
            </p>
            <p className="text-sm text-slate-500">{t("reset.redirecting")}</p>
          </div>
        )}
    </AuthLayout>
  );
}
