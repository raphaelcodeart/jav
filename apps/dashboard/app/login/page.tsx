"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthLayout } from "@/components/auth/auth-layout";
import { PasswordInput } from "@/components/password-input";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { useI18n } from "@/lib/i18n/provider";

/** Sent here by app/providers.tsx::SessionExpiryGuard (Session 85): says
 *  why, so a login page appearing mid-task is not a mystery. */
function ExpiredNotice() {
  const params = useSearchParams();
  const { t } = useI18n();
  if (params.get("sessione") !== "scaduta") return null;
  return (
    <div className="p-3 rounded-xl bg-amber-50 ring-1 ring-amber-200 text-amber-800 text-sm">
      {t("login.expired")}
    </div>
  );
}

/** Dove andare dopo il login, se la pagina di prima lo dice (?next=) e se è
 *  una pagina nostra dell'area giusta per questi ruoli: mai un indirizzo
 *  esterno («//altro-sito») e mai l'area di un altro ruolo, che darebbe 403. */
function safeNext(next: string | null, roles: string[], adminRoles: string[]): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return null;
  if (next.startsWith("/customer")) return roles.includes("CUSTOMER") ? next : null;
  if (next.startsWith("/promoter")) return roles.includes("PROMOTER") ? next : null;
  if (next.startsWith("/admin")) return roles.some((r) => adminRoles.includes(r)) ? next : null;
  if (next.startsWith("/staff")) return roles.includes("INSTRUCTOR") ? next : null;
  if (next.startsWith("/club")) return roles.includes("SECRETARY") ? next : null;
  if (next.startsWith("/atleta")) return roles.includes("ATHLETE") || roles.includes("CUSTOMER") ? next : null;
  return null;
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { t } = useI18n();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.code ? t.dyn(`login.error.${body.code}`, body.error ?? t("login.failed")) : (body.error ?? t("login.failed")));
        return;
      }
      // Redirect based on the roles the API actually granted this user (see
      // /api/auth/login), not a guess from the email address -- a customer
      // signed up via a promoter's invite link has no "customer" in their
      // address and was landing on /promoter, which 403s for their role.
      const roles: string[] = body.roles ?? [];
      const ADMIN_ROLES = [
        "SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN",
        "BACK_OFFICE_OPERATOR", "ACCOUNTING_OPERATOR", "SALES_MANAGER",
      ];
      // Letto qui e non con useSearchParams: la pagina di login è statica, e
      // l'hook vorrebbe un Suspense intorno a tutto il modulo.
      const next = safeNext(new URLSearchParams(window.location.search).get("next"), roles, ADMIN_ROLES);
      if (next) {
        router.push(next);
      } else if (roles.some((r) => ADMIN_ROLES.includes(r))) {
        router.push("/admin");
      } else if (roles.includes("SECRETARY")) {
        router.push("/club");
      } else if (roles.includes("CUSTOMER")) {
        router.push("/customer");
      } else if (roles.includes("INSTRUCTOR")) {
        router.push("/staff");
      } else if (roles.includes("ATHLETE")) {
        router.push("/atleta");
      } else {
        router.push("/promoter");
      }
      router.refresh();
    } catch (err: any) {
      setError(t("login.connectionError"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout title={t("login.title")} subtitle={t("login.subtitle")}>
      <form onSubmit={handleSubmit} className="space-y-5">
        <Field label={t("login.identifier")} htmlFor="email">
          <Input
            id="email"
            type="text"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("login.emailPlaceholder")}
            required
          />
        </Field>

        <Field label="Password" htmlFor="password">
          <PasswordInput
            id="password"
            autoComplete="current-password"
            className="glass-input w-full rounded-xl h-11 px-3.5 text-sm"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
          />
          <div className="text-right pt-1">
            <Link href="/forgot-password" className="text-xs font-semibold text-ink-500 hover:text-brand-600">
              {t("login.forgot")}
            </Link>
          </div>
        </Field>

        <Suspense fallback={null}>
          <ExpiredNotice />
        </Suspense>

        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0, x: 0 }}
              animate={{ opacity: 1, height: "auto", x: [0, -8, 8, -5, 5, 0] }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.4 }}
              className="flex items-start gap-2.5 p-3 rounded-xl bg-rose-50 ring-1 ring-rose-200 text-rose-700 text-sm overflow-hidden"
              role="alert"
            >
              <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>{error}</span>
            </motion.div>
          )}
        </AnimatePresence>

        <Button type="submit" size="lg" loading={submitting} className="w-full">
          {submitting ? t("login.checking") : t("login.submit")}
        </Button>
      </form>
    </AuthLayout>
  );
}
