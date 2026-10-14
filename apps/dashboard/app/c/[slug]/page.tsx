"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { AuthLayout } from "@/components/auth/auth-layout";
import { PasswordInput } from "@/components/password-input";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { translateErrorDetail } from "@/lib/api-error";
import { saveCoursePreference } from "@/lib/course-preference";
import { useI18n } from "@/lib/i18n/provider";

interface PublicClub {
  name: string;
  slug: string;
}

/** La registrazione di una famiglia dal link del suo club (/c/<slug>). Il
 *  club lo dice il link: chi si registra qui è di quel club, e da lì vede
 *  quote, corsi e gare. I figli si aggiungono dal portale, dopo. */
export default function ClubSignupPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const router = useRouter();
  const { t } = useI18n();
  const { data: club, isLoading, error: notFound } = useQuery({
    queryKey: ["public-club", slug],
    queryFn: async (): Promise<PublicClub> => {
      const res = await fetch(`/api/public/club/${encodeURIComponent(slug)}`);
      if (!res.ok) throw new Error("not found");
      return res.json();
    },
    retry: false,
  });

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [acceptPrivacy, setAcceptPrivacy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== passwordConfirm) {
      setError(t("reset.mismatch"));
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/api/public/register-family", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          club_slug: slug, email, password, first_name: firstName, last_name: lastName,
          phone: phone || null, accept_privacy: acceptPrivacy,
          // Il link d'invito di un'altra famiglia (/c/<slug>?invito=<codice>).
          // Letto qui e non con useSearchParams, come nella pagina di login.
          invite_code: new URLSearchParams(window.location.search).get("invito") || null,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ? translateErrorDetail(body.detail) : t("signup.failed"));
      }
      // Il corso JAV scelto sul sito (?curso=<id>): il primo figlio che la
      // famiglia aggiunge lo trova già selezionato (lib/course-preference.ts).
      saveCoursePreference(new URLSearchParams(window.location.search).get("curso"));
      setDone(true);
      setTimeout(() => router.push("/login"), 4000);
    } catch (err) {
      setError((err as Error).message || t("signup.failed"));
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading) {
    return <AuthLayout title={t("signup.loading")}>{null}</AuthLayout>;
  }
  if (notFound || !club) {
    return (
      <AuthLayout title={t("signup.notFound")} subtitle={t("signup.notFoundText")}>
        <Link href="/login" className="text-sm font-semibold text-brand-700 hover:underline">{t("signup.toLogin")}</Link>
      </AuthLayout>
    );
  }
  if (done) {
    return (
      <AuthLayout title={t("signup.doneTitle")} subtitle={t("signup.doneText", { club: club.name })}>
        <Link href="/login" className="text-sm font-semibold text-brand-700 hover:underline">{t("signup.toLogin")}</Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={t("signup.title", { club: club.name })} subtitle={t("signup.subtitle")}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label={t("signup.firstName")} htmlFor="first-name">
            <Input id="first-name" required autoComplete="given-name" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
          </Field>
          <Field label={t("signup.lastName")} htmlFor="last-name">
            <Input id="last-name" required autoComplete="family-name" value={lastName} onChange={(e) => setLastName(e.target.value)} />
          </Field>
        </div>
        <Field label="Email" htmlFor="email">
          <Input id="email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label={t("signup.phone")} htmlFor="phone" hint={t("common.optional")}>
          <Input id="phone" type="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
        </Field>
        <Field label="Password" htmlFor="password" hint={t("reset.min8")}>
          <PasswordInput id="password" required minLength={8} autoComplete="new-password" value={password}
            onChange={(e) => setPassword(e.target.value)} className="glass-input w-full rounded-xl h-11 px-3.5 text-sm" />
        </Field>
        <Field label={t("signup.passwordConfirm")} htmlFor="password-confirm"
          error={passwordConfirm && password !== passwordConfirm ? t("reset.mismatchShort") : undefined}>
          <PasswordInput id="password-confirm" required minLength={8} autoComplete="new-password" value={passwordConfirm}
            onChange={(e) => setPasswordConfirm(e.target.value)} className="glass-input w-full rounded-xl h-11 px-3.5 text-sm" />
        </Field>
        <label className="flex items-start gap-2.5 text-xs text-ink-500 cursor-pointer pt-1">
          <input type="checkbox" checked={acceptPrivacy} onChange={(e) => setAcceptPrivacy(e.target.checked)}
            className="mt-0.5 w-4 h-4 rounded border-ink-200 accent-brand-500 shrink-0" />
          <span>{t("signup.privacy", { club: club.name })}</span>
        </label>
        <AnimatePresence>
          {error && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
              className="p-3 rounded-xl bg-rose-50 ring-1 ring-rose-200 text-rose-700 text-sm overflow-hidden" role="alert">
              {error}
            </motion.div>
          )}
        </AnimatePresence>
        <Button type="submit" size="lg" loading={submitting} disabled={!acceptPrivacy} className="w-full">
          {t("signup.submit")}
        </Button>
        <p className="text-center text-xs text-ink-500">
          {t("signup.haveAccount")} <Link href="/login" className="font-semibold text-brand-700 hover:underline">{t("signup.toLogin")}</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
