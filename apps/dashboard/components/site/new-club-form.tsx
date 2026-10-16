"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useState, type FormEvent } from "react";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { friendlyApiError } from "@/lib/api-error";
import { cn } from "@/lib/cn";
import type { MessageKey } from "@/lib/i18n/messages/it";
import { useI18n } from "@/lib/i18n/provider";

/** «Crea il tuo club» (/criar-clube): due strade. EXISTING, un club che c'è
 *  già e vuole solo il supporto gestionale della rete (portale, quote,
 *  gare, ranking); FROM_ZERO, partire da zero con il Judo Team Matias
 *  Luwawa (corso, aiuto a trovare lo spazio, formazione amministrativa e
 *  tecnica: solo in Portogallo). La richiesta arriva a JudoArteVida come
 *  messaggio di contatto con argomento NEW_CLUB (club/contact.py): lo staff la
 *  legge nella casella dei messaggi e la valuta. */
type Path = "EXISTING" | "FROM_ZERO";

const EMPTY = { name: "", email: "", phone: "", city: "", club: "", athletes: "", experience: "", space: "", message: "", consent: false, website: "" };

export function NewClubForm() {
  const { t, locale } = useI18n();
  const [path, setPath] = useState<Path | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const set = (key: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  function body(): string {
    const lines = [
      `🏯 ${t(path === "EXISTING" ? "site.newClub.pathExisting" : "site.newClub.pathZero")}`,
      `${t("site.newClub.city")}: ${form.city}`,
    ];
    if (path === "EXISTING") {
      lines.push(`${t("site.newClub.clubName")}: ${form.club}`, `${t("site.newClub.athletes")}: ${form.athletes || "—"}`);
    } else {
      lines.push(`${t("site.newClub.experience")}: ${form.experience ? t(`site.newClub.exp.${form.experience}` as MessageKey) : "—"}`,
        `${t("site.newClub.space")}: ${form.space ? t(`site.newClub.space.${form.space}` as MessageKey) : "—"}`);
    }
    if (form.message.trim()) lines.push("", form.message.trim());
    return lines.join("\n");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.consent) {
      setError(t("site.contactForm.consentNeeded"));
      return;
    }
    setSending(true);
    setError(null);
    try {
      const res = await fetch("/api/public/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: form.name, email: form.email, phone: form.phone.trim() || null, message: body(),
          consent: true, website: form.website, locale, topic: "NEW_CLUB" }),
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

  const paths: { key: Path; icon: string; title: MessageKey; text: MessageKey; points: MessageKey[] }[] = [
    { key: "EXISTING", icon: "🤝", title: "site.newClub.pathExisting", text: "site.newClub.pathExistingText",
      points: ["site.newClub.pe1", "site.newClub.pe2", "site.newClub.pe3"] },
    { key: "FROM_ZERO", icon: "🌱", title: "site.newClub.pathZero", text: "site.newClub.pathZeroText",
      points: ["site.newClub.pz1", "site.newClub.pz2", "site.newClub.pz3", "site.newClub.pz4"] },
  ];

  return (
    <MotionConfig reducedMotion="user">
      <div className="grid gap-5 md:grid-cols-2">
        {paths.map((p) => (
          <motion.button key={p.key} type="button" onClick={() => { setPath(p.key); setSent(false); }} whileHover={{ y: -4 }}
            aria-pressed={path === p.key}
            className={cn("cursor-pointer rounded-3xl p-6 text-left shadow-soft ring-2 transition",
              path === p.key ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-ink-900 ring-ink-900/5 hover:ring-brand-300")}>
            <span className="text-4xl" aria-hidden="true">{p.icon}</span>
            <h3 className={cn("mt-3 text-xl", path === p.key ? "text-white" : "text-ink-900")}>{t(p.title)}</h3>
            <p className={cn("mt-2 text-sm", path === p.key ? "text-white/85" : "text-ink-600")}>{t(p.text)}</p>
            <ul className="mt-4 space-y-1.5 text-sm">
              {p.points.map((k) => <li key={k} className="flex gap-2"><span aria-hidden="true">✓</span>{t(k)}</li>)}
            </ul>
            {p.key === "FROM_ZERO" && (
              <p className={cn("mt-4 inline-block rounded-full px-3 py-1 text-xs font-bold", path === p.key ? "bg-white/20" : "bg-accent-100 text-accent-800")}>
                🇵🇹 {t("site.newClub.onlyPortugal")}
              </p>
            )}
          </motion.button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {sent ? (
          <motion.div key="sent" role="status" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
            className="mt-8 flex flex-col items-center rounded-3xl bg-white p-8 text-center shadow-soft ring-1 ring-ink-900/5">
            <span className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-600 text-3xl text-white" aria-hidden="true">✓</span>
            <h3 className="mt-4 text-xl text-ink-900">{t("site.newClub.sentTitle")}</h3>
            <p className="mt-2 max-w-md text-ink-600">{t("site.newClub.sentText")}</p>
          </motion.div>
        ) : path && (
          <motion.form key={path} onSubmit={submit} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="relative mt-8 space-y-4 rounded-3xl bg-white p-6 shadow-soft ring-1 ring-ink-900/5 sm:p-8">
            <h3 className="text-lg text-ink-900">{t("site.newClub.formTitle")}</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("site.contactForm.name")} htmlFor="nc-name">
                <Input id="nc-name" autoComplete="name" required minLength={2} maxLength={120} value={form.name} onChange={set("name")} />
              </Field>
              <Field label={t("site.contactForm.email")} htmlFor="nc-email">
                <Input id="nc-email" type="email" autoComplete="email" required maxLength={255} value={form.email} onChange={set("email")} />
              </Field>
              <Field label={t("site.contactForm.phone")} htmlFor="nc-phone">
                <Input id="nc-phone" type="tel" autoComplete="tel" maxLength={40} value={form.phone} onChange={set("phone")} />
              </Field>
              <Field label={t("site.newClub.city")} htmlFor="nc-city">
                <Input id="nc-city" required maxLength={120} value={form.city} onChange={set("city")} />
              </Field>
              {path === "EXISTING" ? (
                <>
                  <Field label={t("site.newClub.clubName")} htmlFor="nc-club">
                    <Input id="nc-club" required maxLength={160} value={form.club} onChange={set("club")} />
                  </Field>
                  <Field label={t("site.newClub.athletes")} htmlFor="nc-athletes">
                    <Input id="nc-athletes" type="number" min={0} max={5000} value={form.athletes} onChange={set("athletes")} />
                  </Field>
                </>
              ) : (
                <>
                  <Field label={t("site.newClub.experience")} htmlFor="nc-exp">
                    <Select id="nc-exp" value={form.experience} onChange={set("experience")}>
                      <option value="">—</option>
                      {["NONE", "PRACTITIONER", "BLACK_BELT", "COACH"].map((k) => <option key={k} value={k}>{t(`site.newClub.exp.${k}` as MessageKey)}</option>)}
                    </Select>
                  </Field>
                  <Field label={t("site.newClub.space")} htmlFor="nc-space">
                    <Select id="nc-space" value={form.space} onChange={set("space")}>
                      <option value="">—</option>
                      {["HAVE", "LOOKING", "NONE"].map((k) => <option key={k} value={k}>{t(`site.newClub.space.${k}` as MessageKey)}</option>)}
                    </Select>
                  </Field>
                </>
              )}
            </div>
            <Field label={t("site.newClub.message")} htmlFor="nc-message">
              <Textarea id="nc-message" rows={4} maxLength={3000} value={form.message} onChange={set("message")} placeholder={t("site.newClub.messagePlaceholder")} />
            </Field>
            <div className="absolute -left-[9999px] h-px w-px overflow-hidden" aria-hidden="true">
              <label htmlFor="nc-website">Website</label>
              <input id="nc-website" type="text" tabIndex={-1} autoComplete="off" value={form.website} onChange={set("website")} />
            </div>
            <label className="flex cursor-pointer items-start gap-3 rounded-2xl bg-ink-50 p-4">
              <input type="checkbox" className="mt-0.5 h-5 w-5 shrink-0 cursor-pointer accent-brand-600" checked={form.consent}
                onChange={(e) => setForm((f) => ({ ...f, consent: e.target.checked }))} />
              <span className="text-sm text-ink-700">{t("site.contactForm.consentJav")}</span>
            </label>
            {error && <p role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">{error}</p>}
            <button type="submit" disabled={sending}
              className="inline-flex h-12 w-full cursor-pointer items-center justify-center gap-2 rounded-2xl bg-brand-600 px-6 font-semibold text-white shadow-soft transition hover:-translate-y-px hover:bg-brand-700 disabled:cursor-wait disabled:opacity-70 sm:w-auto">
              {sending ? t("site.contactForm.sending") : t("site.newClub.send")} {!sending && <span aria-hidden="true">→</span>}
            </button>
          </motion.form>
        )}
      </AnimatePresence>
    </MotionConfig>
  );
}
