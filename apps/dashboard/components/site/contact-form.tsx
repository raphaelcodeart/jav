"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useState, type FormEvent } from "react";
import { Field, Input, Textarea } from "@/components/ui/field";
import { friendlyApiError } from "@/lib/api-error";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// Il modulo "scrivici" del sito pubblico: in fondo alla pagina di un club
// (il messaggio va a quel club) e su /contactos (va a JudoArteVida). Le
// regole vere le decide l'API (apps/api/app/domains/club/contact.py); qui
// solo ciò che aiuta a non sbagliare prima di premere "Enviar". I colori
// sono quelli del club (token club-*), o di JudoArteVida fuori da una
// pagina di club.

type Target = { kind: "club"; slug: string; name: string } | { kind: "jav" };

const EMPTY = { name: "", email: "", phone: "", message: "", consent: false, website: "" };

export function ContactForm({ target, className }: { target: Target; className?: string }) {
  const { t, locale } = useI18n();
  const [form, setForm] = useState(EMPTY);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const endpoint = target.kind === "club" ? `/api/public/club/${encodeURIComponent(target.slug)}/message` : "/api/public/contact";
  const set = (key: "name" | "email" | "phone" | "message" | "website") =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [key]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.consent) {
      setError(t("site.contactForm.consentNeeded"));
      return;
    }
    setSending(true);
    setError(null);
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, phone: form.phone.trim() || null, locale }),
      });
      if (res.status === 429) throw new Error(t("site.contactForm.tooMany"));
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setSent(true);
      setForm(EMPTY);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <MotionConfig reducedMotion="user">
      <div className={cn("relative", className)}>
        <AnimatePresence mode="wait" initial={false}>
          {sent ? (
            <motion.div
              key="sent" role="status"
              initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
              className="flex flex-col items-center rounded-3xl bg-white p-8 text-center shadow-soft ring-1 ring-ink-900/5"
            >
              <span className="flex h-16 w-16 items-center justify-center rounded-full bg-club text-3xl text-club-on animate-pop" aria-hidden="true">✓</span>
              <h3 className="mt-4 text-xl text-ink-900">{t("site.contactForm.sentTitle")}</h3>
              <p className="mt-2 max-w-sm text-ink-600">
                {target.kind === "club" ? t("site.contactForm.sentClub", { club: target.name }) : t("site.contactForm.sentJav")}
              </p>
              <button type="button" onClick={() => setSent(false)} className="mt-6 cursor-pointer text-sm font-semibold text-club-ink hover:underline">
                {t("site.contactForm.another")}
              </button>
            </motion.div>
          ) : (
            <motion.form
              key="form" onSubmit={submit}
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="space-y-4 rounded-3xl bg-white p-6 shadow-soft ring-1 ring-ink-900/5 sm:p-8"
              aria-describedby={error ? "contact-error" : undefined}
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("site.contactForm.name")} htmlFor="contact-name">
                  <Input id="contact-name" name="name" autoComplete="name" required minLength={2} maxLength={120} value={form.name} onChange={set("name")} />
                </Field>
                <Field label={t("site.contactForm.email")} htmlFor="contact-email" hint={t("site.contactForm.emailHint")}>
                  <Input id="contact-email" name="email" type="email" autoComplete="email" required maxLength={255} value={form.email} onChange={set("email")} />
                </Field>
              </div>
              <Field label={t("site.contactForm.phone")} htmlFor="contact-phone" hint={t("site.contactForm.phoneHint")}>
                <Input id="contact-phone" name="phone" type="tel" autoComplete="tel" maxLength={40} value={form.phone} onChange={set("phone")} />
              </Field>
              <Field label={t("site.contactForm.message")} htmlFor="contact-message">
                <Textarea
                  id="contact-message" name="message" rows={5} required minLength={10} maxLength={4000}
                  placeholder={target.kind === "club" ? t("site.contactForm.placeholderClub") : t("site.contactForm.placeholderJav")}
                  value={form.message} onChange={set("message")}
                />
              </Field>
              {/* La trappola per i robot: le persone non la vedono e non ci
                  arrivano con il tasto Tab; chi la riempie non manda niente. */}
              <div className="absolute -left-[9999px] h-px w-px overflow-hidden" aria-hidden="true">
                <label htmlFor="contact-website">Website</label>
                <input id="contact-website" name="website" type="text" tabIndex={-1} autoComplete="off" value={form.website} onChange={set("website")} />
              </div>
              <label className="flex cursor-pointer items-start gap-3 rounded-2xl bg-ink-50 p-4">
                <input
                  type="checkbox" name="consent" className="mt-0.5 h-5 w-5 shrink-0 cursor-pointer accent-club"
                  checked={form.consent} onChange={(e) => setForm((f) => ({ ...f, consent: e.target.checked }))}
                />
                <span className="text-sm text-ink-700">
                  {target.kind === "club" ? t("site.contactForm.consentClub", { club: target.name }) : t("site.contactForm.consentJav")}
                </span>
              </label>
              {error && <p id="contact-error" role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">{error}</p>}
              <button
                type="submit" disabled={sending}
                className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-club px-6 font-semibold text-club-on shadow-soft transition hover:-translate-y-px hover:brightness-110 disabled:cursor-wait disabled:opacity-70 sm:w-auto cursor-pointer focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-club/30"
              >
                {sending ? t("site.contactForm.sending") : t("site.contactForm.send")}
                {!sending && <span aria-hidden="true">→</span>}
              </button>
              <p className="text-xs text-ink-500">{t("site.contactForm.privacy")}</p>
            </motion.form>
          )}
        </AnimatePresence>
      </div>
    </MotionConfig>
  );
}
