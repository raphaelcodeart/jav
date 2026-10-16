"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { LanguageSwitcher } from "@/components/language-switcher";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

/** Le pagine che raccontano il progetto, raccolte sotto una voce sola: il
 *  menu resta corto anche con tutto quello che c'è da dire. */
const ABOUT = [
  { href: "/quem-somos", key: "site.nav.about", hint: "site.nav.aboutHint" },
  { href: "/visao", key: "site.nav.vision", hint: "site.nav.visionHint" },
  { href: "/projeto", key: "site.nav.project", hint: "site.nav.projectHint" },
  // I corsi nelle scuole stanno qui e non nella barra: il menu resta corto.
  { href: "/cursos", key: "site.nav.courses", hint: "site.nav.coursesHint" },
  { href: "/criar-clube", key: "site.nav.newClub", hint: "site.nav.newClubHint" },
  { href: "/contactos", key: "site.nav.contacts", hint: "site.nav.contactsHint" },
] as const;

const NAV = [
  { href: "/clubes", key: "site.nav.clubs" },
  { href: "/eventos", key: "site.nav.events" },
  { href: "/ranking", key: "site.nav.ranking" },
  { href: "/loja", key: "site.nav.shop" },
] as const;

/** I contatti di JudoArteVida: nel menu "Chi siamo" (e quindi nel menu del
 *  telefono) e, dove lo schermo è abbastanza largo, anche come voce a sé. */
const CONTACTS = { href: "/contactos", key: "site.nav.contacts", hint: "site.nav.contactsHint" } as const;

const SPONSOR = { href: "/patrocinadores", key: "site.nav.sponsor" } as const;

/** La barra del sito pubblico. Chi ha già un account trova subito la sua
 *  area (/area lo porta in quella del suo ruolo); chi non ce l'ha trova
 *  "Entrar", sempre visibile anche sul telefono. Il menu completo da schermo
 *  grande in su; sotto, il pannello a tendina. */
export function SiteHeader({ loggedIn }: { loggedIn: boolean }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const account = loggedIn
    ? { href: "/area", label: t("site.nav.myArea") }
    : { href: "/login", label: t("site.nav.login") };
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const aboutActive = ABOUT.some((a) => isActive(a.href));
  const itemClass = (active: boolean) => cn(
    "rounded-xl px-3.5 py-2 text-[15px] font-semibold transition-colors",
    active ? "bg-brand-50 text-brand-700" : "text-ink-700 hover:bg-ink-100 hover:text-ink-900",
  );

  return (
    <header className="sticky top-0 z-40 border-b border-ink-900/10 bg-white shadow-[0_1px_12px_rgba(10,10,10,0.06)]">
      <a href="#conteudo" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 rounded-lg bg-ink-900 px-3 py-2 text-sm font-semibold text-white">
        {t("site.skipToContent")}
      </a>
      <div className="mx-auto flex h-20 max-w-7xl items-center gap-4 px-4 sm:h-24 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center" aria-label={t("site.homeLink")}>
          <Image src="/judoartevida-logo.jpg" alt="Judo Arte e Vida" width={184} height={80} priority className="h-14 w-auto sm:h-[4.5rem]" />
        </Link>

        <nav className="ml-6 hidden items-center gap-1 lg:flex" aria-label={t("site.nav.label")}>
          <Link href="/" aria-current={isActive("/") ? "page" : undefined} className={itemClass(isActive("/"))}>{t("site.nav.home")}</Link>
          <div
            className="relative"
            onMouseEnter={() => setAboutOpen(true)}
            onMouseLeave={() => setAboutOpen(false)}
            onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setAboutOpen(false); }}
            onKeyDown={(e) => { if (e.key === "Escape") setAboutOpen(false); }}
          >
            <button
              type="button"
              aria-expanded={aboutOpen}
              aria-controls="site-about-menu"
              onClick={() => setAboutOpen((v) => !v)}
              className={cn(itemClass(aboutActive), "inline-flex items-center gap-1 cursor-pointer")}
            >
              {t("site.nav.aboutGroup")}
              <svg className={cn("h-4 w-4 transition-transform", aboutOpen && "rotate-180")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" /></svg>
            </button>
            <AnimatePresence>
              {aboutOpen && (
                <motion.div
                  id="site-about-menu"
                  initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 6 }} transition={{ duration: 0.15 }}
                  className="absolute left-0 top-full w-80 pt-2"
                >
                  <ul className="rounded-2xl bg-white p-2 shadow-lift ring-1 ring-ink-900/5">
                    {ABOUT.map((a) => (
                      <li key={a.href}>
                        <Link href={a.href} onClick={() => setAboutOpen(false)}
                          className={cn("block rounded-xl px-4 py-3 transition-colors", isActive(a.href) ? "bg-brand-50" : "hover:bg-ink-50")}>
                          <span className="block text-sm font-semibold text-ink-900">{t(a.key)}</span>
                          <span className="block text-xs text-ink-500">{t(a.hint)}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} aria-current={isActive(item.href) ? "page" : undefined} className={itemClass(isActive(item.href))}>
              {t(item.key)}
            </Link>
          ))}
          <Link href={CONTACTS.href} aria-current={isActive(CONTACTS.href) ? "page" : undefined} className={cn(itemClass(isActive(CONTACTS.href)), "hidden xl:block")}>
            {t(CONTACTS.key)}
          </Link>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <Link href={SPONSOR.href}
            className="hidden items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-semibold text-accent-700 ring-1 ring-accent-400 transition hover:bg-accent-50 xl:inline-flex">
            ★ {t(SPONSOR.key)}
          </Link>
          <LanguageSwitcher />
          {/* L'ingresso all'area riservata: rosso del club, il bottone che si
              deve trovare per primo. */}
          <Link href={account.href}
            className="group inline-flex items-center gap-2 rounded-xl bg-gradient-to-br from-brand-500 via-brand-600 to-brand-800 px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-brand-600/30 ring-1 ring-white/20 transition hover:-translate-y-0.5 hover:shadow-xl hover:shadow-brand-600/40 motion-reduce:transition-none motion-reduce:hover:translate-y-0">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} aria-hidden="true">
              <circle cx="12" cy="8" r="4" /><path strokeLinecap="round" d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" />
            </svg>
            {account.label}
            <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none">→</span>
          </Link>
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-xl text-ink-700 hover:bg-ink-100 cursor-pointer lg:hidden"
            aria-expanded={open}
            aria-controls="site-mobile-nav"
            aria-label={open ? t("site.nav.close") : t("site.nav.open")}
            onClick={() => setOpen((v) => !v)}
          >
            <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              {open ? <path strokeLinecap="round" d="M6 6l12 12M18 6 6 18" /> : <path strokeLinecap="round" d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.nav
            id="site-mobile-nav"
            aria-label={t("site.nav.label")}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-t border-ink-900/5 bg-white lg:hidden"
          >
            <ul className="space-y-1 px-4 py-3">
              {[{ href: "/", key: "site.nav.home" } as const, ...ABOUT, ...NAV].map((item) => (
                <li key={item.href}>
                  <Link href={item.href} onClick={() => setOpen(false)}
                    className={cn("block rounded-xl px-3 py-2.5 text-base font-semibold", isActive(item.href) ? "bg-brand-50 text-brand-700" : "text-ink-800 hover:bg-ink-100")}>
                    {t(item.key)}
                  </Link>
                </li>
              ))}
              <li className="pt-2">
                <Link href={SPONSOR.href} onClick={() => setOpen(false)}
                  className="block rounded-xl bg-accent-50 px-3 py-3 text-base font-semibold text-accent-800 ring-1 ring-accent-300">
                  ★ {t(SPONSOR.key)}
                </Link>
              </li>
            </ul>
          </motion.nav>
        )}
      </AnimatePresence>
    </header>
  );
}
