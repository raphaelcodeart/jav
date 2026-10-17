import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { siteI18n } from "@/components/site/i18n";
import { SiteHeader } from "@/components/site/site-header";
import { PublicJavbot } from "@/components/javbot/public-bot";
import { JAV_CONTACTS } from "@/lib/jav-contacts";
import { getSession } from "@/lib/session";
import { CookieSettingsButton } from "@/components/legal/cookie-settings-button";
import { LEGAL } from "@/lib/legal";
import { publicSite } from "@/lib/public-site";
import { SocialIcons, WhatsAppButton, type SocialLink } from "@/components/site/social-icons";

const NETWORK_SOCIALS = [
  ["facebook", "Facebook"], ["instagram", "Instagram"], ["youtube", "YouTube"], ["tiktok", "TikTok"],
] as const;

/** La cornice di ogni pagina del sito pubblico: barra, contenuto, piè di
 *  pagina. La sessione si legge solo per decidere tra "Entrar" e "A minha
 *  área": nessuna pagina del sito la richiede. */
export async function SiteShell({ children }: { children: ReactNode }) {
  const [session, { t }, network] = await Promise.all([getSession(), siteI18n(), publicSite.network().catch(() => null)]);
  const socials: SocialLink[] = NETWORK_SOCIALS
    .filter(([kind]) => network?.socials[kind])
    .map(([kind, label]) => ({ kind, label, url: network!.socials[kind] as string }));
  const year = new Date().getFullYear();
  return (
    // overflow-x-clip: niente (aloni, caroselli, nastri) allarga la pagina oltre
    // lo schermo del telefono, dove spingerebbe fuori JAVBOT e lascerebbe una
    // striscia bianca a destra. `clip` e non `hidden`: l'intestazione sticky
    // resta sticky.
    <div className="flex min-h-screen flex-col overflow-x-clip">
      <SiteHeader loggedIn={session !== null} />
      <main id="conteudo" className="flex-1">{children}</main>
      <footer className="mt-24 bg-ink-950 text-ink-300">
        <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr_1.2fr]">
          <div className="space-y-4">
            <div className="inline-flex rounded-2xl bg-white p-2">
              <Image src="/judoartevida-logo.jpg" alt="Judo Arte e Vida" width={138} height={60} className="h-12 w-auto" />
            </div>
            <p className="max-w-sm text-sm leading-relaxed">{t("site.footer.mission")}</p>
            {socials.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-ink-400">{t("site.footer.follow")}</p>
                <SocialIcons links={socials} tone="dark" />
              </div>
            )}
          </div>
          <nav aria-label={t("site.footer.explore")}>
            <h2 className="mb-3 text-sm text-white">{t("site.footer.explore")}</h2>
            <ul className="space-y-2 text-sm">
              <li><Link className="hover:text-white" href="/clubes">{t("site.nav.clubs")}</Link></li>
              <li><Link className="hover:text-white" href="/eventos">{t("site.nav.events")}</Link></li>
              <li><Link className="hover:text-white" href="/ranking">{t("site.nav.ranking")}</Link></li>
            </ul>
          </nav>
          <div>
            <h2 className="mb-3 text-sm text-white">{t("site.footer.access")}</h2>
            <ul className="space-y-2 text-sm">
              <li><Link className="hover:text-white" href="/login">{t("site.nav.login")}</Link></li>
              <li><Link className="hover:text-white" href="/clubes">{t("site.footer.join")}</Link></li>
            </ul>
          </div>
          {/* I contatti di JudoArteVida; per scrivere a un club c'è la sua pagina. */}
          <div>
            <h2 className="mb-3 text-sm text-white">{t("site.nav.contacts")}</h2>
            <ul className="space-y-2 text-sm">
              <li><a className="hover:text-white" href={`mailto:${JAV_CONTACTS.email}`}>{JAV_CONTACTS.email}</a></li>
              <li><a className="hover:text-white" href={JAV_CONTACTS.phoneHref}>{JAV_CONTACTS.phone}</a></li>
              <li><WhatsAppButton phone={JAV_CONTACTS.phone} label="WhatsApp" className="h-9 px-3" /></li>
              <li><Link className="font-semibold text-white hover:text-accent-300" href="/contactos">{t("site.footer.writeUs")} →</Link></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-white/10">
          <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-xs text-ink-400 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p>© {year} Judo Arte e Vida · {LEGAL.controller.name}</p>
            <nav aria-label={t("legal.nav")} className="flex flex-wrap gap-x-4 gap-y-1">
              <Link className="hover:text-white" href="/privacidade">{t("legal.privacy")}</Link>
              <Link className="hover:text-white" href="/cookies">{t("legal.cookies")}</Link>
              <Link className="hover:text-white" href="/termos">{t("legal.terms")}</Link>
              <a className="hover:text-white" href={LEGAL.disputes.url} target="_blank" rel="noopener noreferrer">{t("legal.complaints")}</a>
              <CookieSettingsButton variant="link" />
            </nav>
          </div>
        </div>
      </footer>
      {/* JAVBOT per chi non è ancora cliente: club, orari, iscrizione. Solo
          dati pubblici; quote e pagamenti stanno nell'area privata. */}
      <PublicJavbot />
    </div>
  );
}
