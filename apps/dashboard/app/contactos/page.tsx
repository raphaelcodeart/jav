import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { Container, PageIntro } from "@/components/site/blocks";
import { ContactForm } from "@/components/site/contact-form";
import { siteI18n } from "@/components/site/i18n";
import { Reveal } from "@/components/site/reveal";
import { SiteShell } from "@/components/site/site-shell";
import { JAV_CONTACTS } from "@/lib/jav-contacts";
import { publicSite } from "@/lib/public-site";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await siteI18n();
  return {
    title: `${t("site.contacts.title")} · Judo Arte e Vida`,
    description: t("site.contacts.metaDescription"),
    alternates: { canonical: "/contactos" },
    openGraph: { title: t("site.contacts.title"), description: t("site.contacts.metaDescription"), images: ["/judoartevida-logo.jpg"] },
  };
}

/** I contatti di JudoArteVida e il modulo per scriverci: chi scrive sceglie
 *  a chi (JudoArteVida o un club) e di che cosa. Il messaggio si salva nella
 *  casella "Messaggi" di chi lo riceve (la console, o la segreteria del club,
 *  e lo staff della piattaforma vede anche quelli dei club) e parte l'email. */
export default async function ContactsPage() {
  const [{ t }, clubs] = await Promise.all([siteI18n(), publicSite.clubs().catch(() => null)]);
  return (
    <SiteShell>
      <PageIntro eyebrow={t("site.contacts.eyebrow")} title={t("site.contacts.title")} text={t("site.contacts.text")} />
      <Container className="grid items-start gap-10 py-12 lg:grid-cols-[1fr_1.4fr]">
        <Reveal className="space-y-4">
          <ContactCard icon="✉️" label={t("site.contacts.email")}>
            <a href={`mailto:${JAV_CONTACTS.email}`} className="font-semibold text-ink-900 hover:text-brand-700">{JAV_CONTACTS.email}</a>
          </ContactCard>
          <ContactCard icon="📞" label={t("site.contacts.phone")}>
            <a href={JAV_CONTACTS.phoneHref} className="font-semibold text-ink-900 hover:text-brand-700">{JAV_CONTACTS.phone}</a>
          </ContactCard>
          <ContactCard icon="📍" label={t("site.contacts.where")}>
            <span className="font-semibold text-ink-900">{t("site.contacts.region")}</span>
          </ContactCard>
          <div className="rounded-3xl bg-gradient-to-br from-brand-500 to-brand-700 p-6 text-white shadow-brand">
            <p className="font-semibold">{t("site.contacts.clubTitle")}</p>
            <p className="mt-1 text-sm text-white/90">{t("site.contacts.clubText")}</p>
            <Link href="/clubes" className="mt-4 inline-flex h-10 items-center rounded-xl bg-white px-4 text-sm font-semibold text-ink-900 hover:bg-accent-50">
              {t("site.contacts.clubCta")}
            </Link>
          </div>
        </Reveal>
        <Reveal delay={0.1}>
          <h2 className="mb-4 text-2xl text-ink-900">{t("site.contacts.formTitle")}</h2>
          <ContactForm target={{ kind: "jav" }} chooseTopic recipients={(clubs ?? []).map((c) => ({ slug: c.slug, name: c.name }))} />
        </Reveal>
      </Container>
    </SiteShell>
  );
}

function ContactCard({ icon, label, children }: { icon: string; label: string; children: ReactNode }) {
  return (
    <div className="glass-card flex items-center gap-4 rounded-2xl p-5">
      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-xl" aria-hidden="true">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-400">{label}</p>
        <p className="break-all">{children}</p>
      </div>
    </div>
  );
}
