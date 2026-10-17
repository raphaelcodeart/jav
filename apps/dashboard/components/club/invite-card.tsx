"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useToast } from "@/components/ui/toast";
import { clubGet, type Invite, type Pricing } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";
import { shareOrCopyLink } from "@/lib/share-link";

/** Il link personale per invitare un amico nel club, e quanto ha reso: ogni
 *  mensilità pagata da una famiglia invitata dà credito nel wallet, da usare
 *  quando si pagano le quote (apps/api/app/domains/club/referrals.py). Si
 *  condivide con un tocco su WhatsApp, Facebook, Telegram, X o per email, o si
 *  copia. Sotto, che cosa comprende l'iscrizione annuale: le famiglie lo chiedono. */
export function InviteCard({ withNetwork = true }: { withNetwork?: boolean }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const { data: invite } = useQuery({ queryKey: ["club", "invite"], queryFn: () => clubGet<Invite>("/invite"), retry: false });
  const { data: pricing } = useQuery({ queryKey: ["club", "pricing"], queryFn: () => clubGet<Pricing>("/pricing"), retry: false });
  if (!invite) return null;
  const url = `${typeof window === "undefined" ? "" : window.location.origin}${invite.path}`;
  const text = t("invite.shareText");
  const enc = encodeURIComponent;

  const socials = [
    { name: "WhatsApp", bg: "bg-[#25D366]", href: `https://wa.me/?text=${enc(`${text} ${url}`)}`, icon: <path d="M17.5 14.4c-.3-.1-1.7-.8-2-.9-.3-.1-.5-.1-.7.1-.2.3-.8.9-.9 1.1-.2.2-.3.2-.6.1-.3-.1-1.2-.5-2.3-1.4-.9-.8-1.4-1.7-1.6-2-.2-.3 0-.5.1-.6l.4-.5c.1-.2.2-.3.3-.5.1-.2 0-.4 0-.5l-.9-2.2c-.2-.6-.5-.5-.7-.5h-.6c-.2 0-.5.1-.8.4-.3.3-1 1-1 2.4s1 2.8 1.2 3c.1.2 2 3.1 4.9 4.3.7.3 1.2.5 1.6.6.7.2 1.3.2 1.8.1.6-.1 1.7-.7 1.9-1.4.2-.7.2-1.2.2-1.4-.1-.1-.3-.2-.6-.3zM12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2zm0 18.2c-1.5 0-3-.4-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2z" /> },
    { name: "Facebook", bg: "bg-[#1877F2]", href: `https://www.facebook.com/sharer/sharer.php?u=${enc(url)}`, icon: <path d="M14 8.5V6.8c0-.8.2-1.3 1.4-1.3H17V2.6c-.3 0-1.3-.1-2.5-.1-2.5 0-4.2 1.5-4.2 4.3v1.7H7.5v3.2h2.8V21H14v-9.3h2.8l.4-3.2H14z" /> },
    { name: "Telegram", bg: "bg-[#229ED9]", href: `https://t.me/share/url?url=${enc(url)}&text=${enc(text)}`, icon: <path d="M21.9 4.6 18.7 19.7c-.2 1-.9 1.3-1.7.8l-4.7-3.5-2.3 2.2c-.3.3-.5.5-1 .5l.3-4.8 8.8-7.9c.4-.3-.1-.5-.6-.2L6.6 13.6 2 12.2c-1-.3-1-1 .2-1.5l18.1-7c.9-.3 1.6.2 1.3 1.6z" /> },
    { name: "X", bg: "bg-ink-950", href: `https://twitter.com/intent/tweet?text=${enc(text)}&url=${enc(url)}`, icon: <path d="M17.8 3h3.1l-6.8 7.8L22 21h-6.2l-4.9-6.4L5.3 21H2.2l7.3-8.3L2 3h6.4l4.4 5.8L17.8 3zm-1.1 16.2h1.7L7.4 4.7H5.6l11.1 14.5z" /> },
    { name: "Email", bg: "bg-brand-600", href: `mailto:?subject=${enc(t("invite.shareTitle"))}&body=${enc(`${text}\n\n${url}`)}`, icon: <path d="M3 5h18v14H3V5zm2 2v.5l7 4.5 7-4.5V7H5zm14 2.8-7 4.5-7-4.5V17h14V9.8z" /> },
  ];

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      toast({ tone: "success", title: t("invite.copied") });
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({ tone: "error", title: t("invite.copyFailed") });
    }
  }

  async function nativeShare() {
    const result = await shareOrCopyLink({ url, title: t("invite.shareTitle"), text });
    if (result === "copied") toast({ tone: "success", title: t("invite.copied") });
    if (result === "failed") toast({ tone: "error", title: t("invite.copyFailed") });
  }

  return (
    <div className="space-y-5">
    <section className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-emerald-500 via-teal-600 to-ink-900 p-6 text-white shadow-lift sm:p-7">
      <motion.span aria-hidden="true" className="pointer-events-none absolute -right-6 -top-8 select-none text-[8rem] leading-none opacity-20"
        animate={{ rotate: [-6, 6, -6] }} transition={{ duration: 6, repeat: Infinity }}>🤝</motion.span>
      <div className="relative grid gap-5 lg:grid-cols-[1fr_auto] lg:items-center">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-emerald-100">🎁 {t("invite.title")}</p>
          <h3 className="mt-1 font-display text-2xl leading-tight sm:text-3xl">
            +{fmt.euro(invite.credit_per_month_cents)} <span className="font-sans text-base font-semibold text-white/85">{t("invite.perMonth")}</span>
          </h3>
          <p className="mt-2 max-w-xl text-sm text-white/85">{t("invite.text", { amount: fmt.euro(invite.credit_per_month_cents) })}</p>
        </div>
        <div className="grid grid-cols-2 gap-2 text-center">
          <div className="rounded-2xl bg-white/15 px-4 py-3 ring-1 ring-white/20">
            <p className="font-display text-3xl leading-none">{invite.invited_count}</p>
            <p className="mt-1 text-[10px] font-bold uppercase tracking-wider text-white/75">{t("invite.invitedLabel")}</p>
          </div>
          <div className="rounded-2xl bg-white/15 px-4 py-3 ring-1 ring-white/20">
            <p className="font-display text-3xl leading-none">{fmt.euro(invite.earned_cents)}</p>
            <p className="mt-1 text-[10px] font-bold uppercase tracking-wider text-white/75">{t("invite.earnedLabel")}</p>
          </div>
        </div>
      </div>

      <div className="relative mt-5 flex flex-col gap-2 sm:flex-row">
        <code className="flex-1 truncate rounded-2xl bg-white/95 px-4 py-3 text-sm text-ink-800">{url}</code>
        <button type="button" onClick={copy}
          className="inline-flex h-12 cursor-pointer items-center justify-center gap-2 rounded-2xl bg-accent-400 px-5 font-bold text-ink-900 shadow transition hover:bg-accent-300">
          {copied ? "✓" : "📋"} {copied ? t("invite.copiedShort") : t("invite.copy")}
        </button>
      </div>

      <div className="relative mt-4 flex flex-wrap items-center gap-2">
        <span className="mr-1 text-xs font-semibold text-white/80">{t("invite.shareOn")}</span>
        {socials.map((s) => (
          <motion.a key={s.name} href={s.href} target="_blank" rel="noopener noreferrer" whileHover={{ y: -3, scale: 1.08 }} whileTap={{ scale: 0.95 }}
            title={s.name} aria-label={s.name}
            className={`flex h-11 w-11 items-center justify-center rounded-full text-white shadow-lg ring-2 ring-white/30 ${s.bg}`}>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">{s.icon}</svg>
          </motion.a>
        ))}
        <button type="button" onClick={nativeShare} title={t("invite.share")}
          className="flex h-11 cursor-pointer items-center gap-2 rounded-full bg-white/15 px-4 text-sm font-semibold ring-1 ring-white/30 hover:bg-white/25">
          ↗ {t("invite.more")}
        </button>
      </div>

      {pricing?.enrollment_includes && (
        <p className="relative mt-4 border-t border-white/20 pt-3 text-xs text-white/80">
          <span className="font-semibold text-white">{t("invite.enrollmentIncludes")}</span> {pricing.enrollment_includes}
        </p>
      )}
    </section>
    {withNetwork && <InviteNetwork invite={invite} />}
    </div>
  );
}

/** La rete di chi invita: gli atleti entrati dal suo link, con le mensilità
 *  pagate e quanto gli hanno reso, e il saldo JavCash da usare sulle quote. */
function InviteNetwork({ invite }: { invite: Invite }) {
  const { t, fmt } = useI18n();
  const network = invite.network ?? [];
  const months = network.reduce((s, n) => s + n.months_paid, 0);
  return (
    <section className="rounded-[2rem] bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-3xl bg-gradient-to-br from-accent-300 to-accent-500 p-4 text-ink-900 shadow-soft">
          <p className="text-[11px] font-bold uppercase tracking-widest opacity-75">🪙 {t("invite.balance")}</p>
          <p className="mt-1 font-display text-3xl">{fmt.euro(invite.balance_cents ?? 0)}</p>
          <p className="mt-1 text-xs opacity-80">{t("invite.balanceHint")}</p>
        </div>
        <div className="rounded-3xl bg-ink-50 p-4">
          <p className="text-[11px] font-bold uppercase tracking-widest text-ink-400">👥 {t("invite.networkPeople")}</p>
          <p className="mt-1 font-display text-3xl text-ink-900">{network.length}</p>
        </div>
        <div className="rounded-3xl bg-ink-50 p-4">
          <p className="text-[11px] font-bold uppercase tracking-widest text-ink-400">📅 {t("invite.networkMonths")}</p>
          <p className="mt-1 font-display text-3xl text-ink-900">{months}</p>
        </div>
      </div>

      <h3 className="mt-6 text-lg text-ink-900">{t("invite.networkTitle")}</h3>
      {network.length === 0 ? (
        <p className="mt-2 rounded-2xl bg-ink-50 p-4 text-sm text-ink-500">{t("invite.networkEmpty", { amount: fmt.euro(invite.credit_per_month_cents) })}</p>
      ) : (
        <ul className="mt-3 grid gap-3 sm:grid-cols-2">
          {network.map((n, i) => (
            <motion.li key={n.athlete_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.04 }}
              className="flex items-center gap-3 rounded-2xl bg-ink-50/70 p-3 ring-1 ring-ink-900/5">
              {n.photo_url ? (
                // eslint-disable-next-line @next/next/no-img-element -- foto della scheda dell'atleta
                <img src={n.photo_url} alt="" className="h-12 w-12 shrink-0 rounded-full object-cover ring-2 ring-white" />
              ) : (
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-emerald-500 to-teal-700 font-display text-white">{n.name.slice(0, 1)}</span>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-ink-900">{n.name}</p>
                <p className="text-xs text-ink-500">{t("invite.since", { date: fmt.shortDate(n.joined_on) })}{n.status !== "ACTIVE" ? ` · ${t("invite.inactive")}` : ""}</p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-sm font-bold text-ink-900">{t("invite.monthsPaid", { n: n.months_paid })}</p>
                <p className="text-xs font-semibold text-emerald-700">+{fmt.euro(n.credit_cents)}</p>
              </div>
            </motion.li>
          ))}
        </ul>
      )}
    </section>
  );
}
