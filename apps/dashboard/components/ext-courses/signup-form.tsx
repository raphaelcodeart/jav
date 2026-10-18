"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useGroupLine } from "@/components/ext-courses/common";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/field";
import { PasswordInput } from "@/components/password-input";
import { friendlyApiError } from "@/lib/api-error";
import { guessGroup, isoDay, type ExtChildInput, type ExtCourse } from "@/lib/ext-courses";
import { useI18n } from "@/lib/i18n/provider";

const MAX_CHILDREN = 6; // extcourses/service.py::MAX_CHILDREN
const EMPTY_CHILD: ExtChildInput = { first_name: "", last_name: "", birth_date: "", notes: "" };

/** L'iscrizione a un corso esterno, più figli in una volta.
 *
 *  - Chi non ha un account scrive i suoi dati e una password: nasce l'account
 *    del genitore (EXT_FAMILY) e, subito dopo, entra da solo e va a /cursos.
 *    Se l'email ha già un account (409) gli si dice di entrare: il login lo
 *    riporta qui, e da dentro iscrive i figli senza password.
 *  - Chi è già dentro (anche una famiglia di un club: l'anagrafica è del
 *    corso, si riscrive) iscrive e basta.
 *
 *  Il gruppo accanto a ogni bambino è solo un'indicazione: lo sceglie il server. */
export function ExtSignupForm({ course, loggedIn, onDone }: {
  course: ExtCourse;
  loggedIn: boolean;
  /** Dentro l'area del genitore: dopo l'iscrizione si ricarica la famiglia invece di cambiare pagina. */
  onDone?: () => void;
}) {
  const { t } = useI18n();
  const groupLine = useGroupLine();
  const [guardian, setGuardian] = useState({ name: "", email: "", phone: "", password: "" });
  const [children, setChildren] = useState<ExtChildInput[]>([{ ...EMPTY_CHILD }]);
  const [privacy, setPrivacy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [created, setCreated] = useState(false);
  const today = isoDay(new Date());
  const back = `/cursos-externos/${course.id}`;

  const setChild = (i: number, key: keyof ExtChildInput, value: string) =>
    setChildren((list) => list.map((c, j) => (j === i ? { ...c, [key]: value } : c)));

  const payloadChildren = () => children.map((c) => ({
    first_name: c.first_name.trim(), last_name: c.last_name.trim(), birth_date: c.birth_date, notes: c.notes.trim() || null,
  }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setConflict(false);
    if (!loggedIn && !privacy) {
      setError(t("ext.signup.privacyNeeded"));
      return;
    }
    setBusy(true);
    try {
      if (loggedIn) {
        const res = await fetch(`/api/proxy/ext/family/courses/${course.id}/enroll`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ guardian_name: guardian.name.trim() || null, guardian_phone: guardian.phone.trim() || null, children: payloadChildren() }),
        });
        if (!res.ok) throw new Error(await friendlyApiError(res));
        if (onDone) onDone();
        else window.location.assign("/cursos?area=familia");
        return;
      }
      const res = await fetch(`/api/public/ext-courses/${course.id}/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: guardian.email.trim(), password: guardian.password, guardian_name: guardian.name.trim(),
          guardian_phone: guardian.phone.trim() || null, children: payloadChildren(), privacy_accepted: true,
        }),
      });
      if (res.status === 409) {
        setConflict(true);
        return;
      }
      if (res.status === 429) throw new Error(t("ext.signup.tooMany"));
      if (!res.ok) throw new Error(await friendlyApiError(res));
      // L'account c'è: si entra con la password appena scelta. Se il login
      // non riesce (rete, limite) l'iscrizione resta fatta: lo si dice.
      const login = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: guardian.email.trim(), password: guardian.password }),
      }).catch(() => null);
      if (login?.ok) window.location.assign("/cursos");
      else setCreated(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <div role="status" className="flex flex-col items-center rounded-3xl bg-white p-8 text-center shadow-soft ring-1 ring-ink-900/5">
        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-600 text-3xl text-white" aria-hidden="true">✓</span>
        <h3 className="mt-4 text-xl text-ink-900">{t("ext.signup.createdTitle")}</h3>
        <p className="mt-2 max-w-md text-ink-600">{t("ext.signup.createdText")}</p>
        <Link href="/login?next=/cursos" className="mt-5 inline-flex h-11 items-center rounded-xl bg-brand-600 px-5 font-semibold text-white">{t("ext.signup.login")}</Link>
      </div>
    );
  }

  return (
    <MotionConfig reducedMotion="user">
      <form onSubmit={submit} className="space-y-6 rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-8">
        <section className="space-y-4">
          <h3 className="text-lg text-ink-900">👤 {loggedIn ? t("ext.signup.guardianOptional") : t("ext.signup.guardian")}</h3>
          {loggedIn && <p className="text-sm text-ink-500">{t("ext.signup.loggedInNote")}</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("ext.signup.guardianName")} htmlFor="es-name" hint={loggedIn ? undefined : t("ext.signup.guardianNameHint")}>
              <Input id="es-name" autoComplete="name" required={!loggedIn} maxLength={160} value={guardian.name}
                onChange={(e) => setGuardian((g) => ({ ...g, name: e.target.value }))} />
            </Field>
            <Field label={t("ext.signup.phone")} htmlFor="es-phone">
              <Input id="es-phone" type="tel" autoComplete="tel" maxLength={40} value={guardian.phone}
                onChange={(e) => setGuardian((g) => ({ ...g, phone: e.target.value }))} />
            </Field>
            {!loggedIn && (
              <>
                <Field label={t("ext.signup.email")} htmlFor="es-email">
                  <Input id="es-email" type="email" autoComplete="email" required maxLength={255} value={guardian.email}
                    onChange={(e) => setGuardian((g) => ({ ...g, email: e.target.value }))} />
                </Field>
                <Field label={t("ext.signup.password")} htmlFor="es-password" hint={t("ext.signup.passwordHint")}>
                  <PasswordInput id="es-password" className="glass-input h-11 w-full rounded-xl px-3.5 text-sm text-ink-900" autoComplete="new-password" required minLength={8} maxLength={128} value={guardian.password}
                    onChange={(e) => setGuardian((g) => ({ ...g, password: e.target.value }))} />
                </Field>
              </>
            )}
          </div>
        </section>

        <section className="space-y-4">
          <h3 className="text-lg text-ink-900">🧒 {t("ext.signup.children")}</h3>
          <AnimatePresence initial={false}>
            {children.map((child, i) => {
              const group = child.birth_date ? guessGroup(course, child.birth_date) : null;
              return (
                <motion.fieldset key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}
                  className="space-y-3 rounded-2xl bg-ink-50/70 p-4 ring-1 ring-ink-100">
                  <legend className="sr-only">{t("ext.signup.childN", { n: i + 1 })}</legend>
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-bold text-ink-700">{t("ext.signup.childN", { n: i + 1 })}</p>
                    {children.length > 1 && (
                      <button type="button" onClick={() => setChildren((list) => list.filter((_, j) => j !== i))}
                        className="cursor-pointer rounded-lg px-2 py-1 text-xs font-semibold text-rose-600 hover:bg-white">
                        {t("ext.signup.removeChild")}
                      </button>
                    )}
                  </div>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Field label={t("ext.signup.firstName")} htmlFor={`es-c${i}-first`}>
                      <Input id={`es-c${i}-first`} required maxLength={80} value={child.first_name} onChange={(e) => setChild(i, "first_name", e.target.value)} />
                    </Field>
                    <Field label={t("ext.signup.lastName")} htmlFor={`es-c${i}-last`}>
                      <Input id={`es-c${i}-last`} required maxLength={80} value={child.last_name} onChange={(e) => setChild(i, "last_name", e.target.value)} />
                    </Field>
                    <Field label={t("ext.signup.birthDate")} htmlFor={`es-c${i}-birth`}>
                      <Input id={`es-c${i}-birth`} type="date" required max={today} value={child.birth_date} onChange={(e) => setChild(i, "birth_date", e.target.value)} />
                    </Field>
                  </div>
                  <Field label={t("ext.signup.notes")} htmlFor={`es-c${i}-notes`} hint={t("ext.signup.notesHint")}>
                    <Textarea id={`es-c${i}-notes`} maxLength={500} className="min-h-16" value={child.notes} onChange={(e) => setChild(i, "notes", e.target.value)} />
                  </Field>
                  {child.birth_date && (
                    <p className={group ? "rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800 ring-1 ring-emerald-200" : "rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800 ring-1 ring-amber-200"}>
                      {group ? <>✓ {t("ext.signup.groupWillBe", { group: group.name })} · <span className="capitalize">{groupLine(group)}</span></> : t("ext.signup.noGroup")}
                    </p>
                  )}
                </motion.fieldset>
              );
            })}
          </AnimatePresence>
          {children.length < MAX_CHILDREN && (
            <Button type="button" variant="secondary" onClick={() => setChildren((list) => [...list, { ...EMPTY_CHILD, last_name: list[0]?.last_name ?? "" }])}>
              ＋ {t("ext.signup.addChild")}
            </Button>
          )}
        </section>

        {!loggedIn && (
          <label className="flex cursor-pointer items-start gap-3 text-sm text-ink-700">
            <input type="checkbox" className="mt-0.5 h-5 w-5 accent-brand-600" checked={privacy} onChange={(e) => setPrivacy(e.target.checked)} />
            <span>
              {t("ext.signup.privacy")}{" "}
              <Link href="/privacidade" target="_blank" className="font-semibold text-brand-700 underline">{t("ext.signup.privacyLink")}</Link>
            </span>
          </label>
        )}

        {conflict && (
          <div role="alert" className="space-y-3 rounded-2xl bg-amber-50 p-4 text-sm text-amber-900 ring-1 ring-amber-200">
            <p className="font-semibold">{t("ext.signup.exists")}</p>
            <Link href={`/login?next=${encodeURIComponent(back)}`} className="inline-flex h-10 items-center rounded-xl bg-ink-900 px-4 font-semibold text-white">
              {t("ext.signup.loginToEnroll")}
            </Link>
          </div>
        )}
        {error && <p role="alert" className="rounded-xl bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700 ring-1 ring-rose-200">{error}</p>}

        <Button type="submit" size="lg" loading={busy} className="w-full sm:w-auto">
          {loggedIn ? t("ext.signup.enrollMine") : t("ext.signup.submit")}
        </Button>
        {!loggedIn && (
          <p className="text-sm text-ink-500">
            {t("ext.signup.haveAccount")}{" "}
            <Link href={`/login?next=${encodeURIComponent(back)}`} className="font-semibold text-brand-700 hover:underline">{t("ext.signup.login")}</Link>
          </p>
        )}
      </form>
    </MotionConfig>
  );
}
