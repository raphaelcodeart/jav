"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell, type NavItem } from "@/components/app-shell";
import { AdminJavMarketPanel } from "@/components/admin-jav-market-panel";
import { AdminOrganizationSettingsPanel } from "@/components/admin-organization-settings-panel";
import { AdminTicketsPanel } from "@/components/admin-tickets-panel";
import { AdminWalletsPanel } from "@/components/admin-wallets-panel";
import { PlatformMoney } from "@/components/admin/platform-accounting";
import { ClubAdminPanel, sectionsFor, type ClubSection } from "@/components/club/club-admin-panel";
import { ContactInbox } from "@/components/club/contact-inbox";
import { KnowledgePanel } from "@/components/javbot/knowledge-panel";
import { CoursesUnitPanel } from "@/components/club/courses-unit-panel";
import { ClubList } from "@/components/club/clubs-panel";
import { useCurrentClub } from "@/components/club/current-club";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { friendlyApiError } from "@/lib/api-error";
import type { PlatformOverview } from "@/lib/club";
import { enterClub, leaveClub } from "@/lib/club-cookie";
import { useI18n } from "@/lib/i18n/provider";

type PlatformKey = "hq" | "clubs" | "jav-courses" | "messages" | "javbot" | "shop" | "wallets" | "support" | "settings";
type Key = PlatformKey | `club:${ClubSection}`;

const emoji = (e: string) => <span className="text-base leading-none" aria-hidden="true">{e}</span>;

/** La console della piattaforma JudoArteVida: chi la gestisce vede tutti i
 *  club (panoramica, elenco, creazione), entra in uno e lo amministra con le
 *  stesse sezioni della sua segreteria, e governa lo Shop unico, i wallet,
 *  l'assistenza. Niente contratti, pratiche o rete commerciale: quella era
 *  un'altra applicazione. */
export function AdminConsole({ email, isSuperAdmin }: { email?: string; isSuperAdmin: boolean }) {
  const { t } = useI18n();
  const [active, setActive] = useState<Key>("hq");
  const { data: current } = useCurrentClub();
  const queryClient = useQueryClient();

  async function choose(clubId: string | null, then: Key) {
    if (clubId) enterClub(clubId);
    else leaveClub();
    await queryClient.resetQueries({ queryKey: ["club"] });
    setActive(then);
  }

  const clubGroup = current ? `${current.kind === "JAV_COURSES" ? "🏫" : "🏯"} ${current.name}` : t("console.groupClub");
  const navItems: NavItem[] = [
    { key: "hq", label: t("console.hq"), icon: emoji("🌍"), group: "JudoArteVida" },
    { key: "clubs", label: t("console.clubs"), icon: emoji("🏯"), group: "JudoArteVida" },
    // I corsi nelle scuole non sono un club: un'entrata loro, accanto ai club.
    { key: "jav-courses", label: t("javCourses.navEntry"), icon: emoji("🏫"), group: "JudoArteVida" },
    // I messaggi scritti a JudoArteVida da /contactos.
    { key: "messages", label: t("console.messages"), icon: emoji("✉️"), group: "JudoArteVida", notificationTypes: ["CONTACT_MESSAGE"] },
    // La base di conoscenza comune di JAVBOT: la gestisce chi gestisce i club (clubs.manage).
    ...(isSuperAdmin ? [{ key: "javbot", label: t("console.javbot"), icon: emoji("🤖"), group: "JudoArteVida" }] : []),
    ...sectionsFor(current?.kind).map((s) => ({
      key: `club:${s.key}`, label: t.dyn(`clubNav.${s.key}`, s.key), icon: emoji(s.icon), group: clubGroup,
    })),
    { key: "shop", label: t("console.shop"), icon: emoji("🛍️"), group: t("console.groupShop"), notificationTypes: ["JAV_MARKET_ORDER_PAID", "ORDER_PAYMENT_PROOF_UPLOADED"] },
    { key: "wallets", label: t("console.wallets"), icon: emoji("💎"), group: t("console.groupPlatform") },
    { key: "support", label: t("console.support"), icon: emoji("🎧"), group: t("console.groupPlatform") },
    { key: "settings", label: t("console.settings"), icon: emoji("⚙️"), group: t("console.groupPlatform") },
  ];
  const clubSection = active.startsWith("club:") ? (active.slice(5) as ClubSection) : null;

  return (
    <AppShell
      roleLabel={isSuperAdmin ? t("console.roleSuper") : t("console.roleAdmin")}
      email={email}
      navItems={navItems}
      activeKey={active}
      onNavigate={(k) => setActive(k as Key)}
      headerActions={<ClubSwitcher currentId={current?.id ?? null} onChoose={(id) => choose(id, id ? (clubSection ? active : "club:overview") : "clubs")} />}
    >
      {active === "hq" && <PlatformOverviewPanel canEdit={isSuperAdmin} onEnter={(id) => choose(id, "club:overview")} />}
      {active === "clubs" && <ClubList onEnter={(id) => choose(id, "club:overview")} />}
      {active === "jav-courses" && <CoursesUnitPanel canCreate={isSuperAdmin} onEnter={(id) => choose(id, "jav-courses")} />}
      {active === "messages" && (
        <>
          <PageHeader eyebrow="JudoArteVida" title={t("console.messages")} subtitle={isSuperAdmin ? t("console.messagesSubtitleSuper") : t("console.messagesSubtitle")} />
          <ContactInbox mode="platform" canFilterClubs={isSuperAdmin} />
        </>
      )}
      {active === "javbot" && (
        <>
          <PageHeader eyebrow="JudoArteVida" title={t("console.javbot")} subtitle={t("console.javbotSubtitle")} />
          <KnowledgePanel mode="platform" />
        </>
      )}
      {clubSection && (current
        ? <ClubAdminPanel section={clubSection} onGo={(s) => setActive(`club:${s}`)} canInvest={isSuperAdmin} />
        : <ChooseClub onEnter={(id) => choose(id, active)} />)}
      {active === "shop" && (
        <>
          <PageHeader eyebrow={t("console.groupShop")} title={t("console.shop")} subtitle={t("console.shopSubtitle")} />
          <AdminJavMarketPanel />
        </>
      )}
      {active === "wallets" && (
        <>
          <PageHeader eyebrow={t("console.groupPlatform")} title={t("console.wallets")} subtitle={t("console.walletsSubtitle")} />
          <AdminWalletsPanel isSuperAdmin={isSuperAdmin} />
        </>
      )}
      {active === "support" && (
        <>
          <PageHeader eyebrow={t("console.groupPlatform")} title={t("console.support")} />
          <AdminTicketsPanel />
        </>
      )}
      {active === "settings" && (
        <>
          <PageHeader eyebrow={t("console.groupPlatform")} title={t("console.settings")} subtitle={t("console.settingsSubtitle")} />
          <AdminOrganizationSettingsPanel />
        </>
      )}
    </AppShell>
  );
}

/** Il club su cui si lavora, sempre in vista in testata: si cambia da qui. */
function ClubSwitcher({ currentId, onChoose }: { currentId: string | null; onChoose: (id: string | null) => void }) {
  const { t } = useI18n();
  const { data } = useQuery({ queryKey: ["clubs"], queryFn: () => fetchJson<{ id: string; name: string; kind?: string }[]>("/api/proxy/clubs") });
  return (
    <Select value={currentId ?? ""} onChange={(e) => onChoose(e.target.value || null)} className="w-60" aria-label={t("console.switchClub")}>
      <option value="">{t("console.noClub")}</option>
      {(data ?? []).map((c) => <option key={c.id} value={c.id}>{c.kind === "JAV_COURSES" ? "🏫" : "🏯"} {c.name}</option>)}
    </Select>
  );
}

function ChooseClub({ onEnter }: { onEnter: (id: string) => void }) {
  const { t } = useI18n();
  return (
    <div className="space-y-4">
      <EmptyState icon={<span className="text-3xl">🏯</span>} title={t("console.chooseClub")} text={t("console.chooseClubText")} />
      <ClubList onEnter={onEnter} />
    </div>
  );
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** La panoramica di tutta la piattaforma: il contatore di quanto spetta
 *  alla piattaforma, i conti di tutti i club insieme e uno per uno
 *  (platform-accounting.tsx), poi i prossimi eventi di tutti. */
function PlatformOverviewPanel({ onEnter, canEdit }: { onEnter: (id: string) => void; canEdit: boolean }) {
  const { t, fmt } = useI18n();
  const { data, isLoading, error } = useQuery({ queryKey: ["clubs", "overview"], queryFn: () => fetchJson<PlatformOverview>("/api/proxy/clubs/overview") });
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="JudoArteVida" title={t("console.hq")} subtitle={t("console.hqSubtitle")} />
      <PlatformMoney canEdit={canEdit} onEnter={onEnter} />
      <div>
        <div className="glass-card rounded-3xl p-5">
          <h3 className="text-base text-ink-900 mb-3">{t("console.upcoming")}</h3>
          {isLoading ? <Skeleton className="h-24" /> : error || !data ? <p className="text-sm text-ink-500">{t("console.overviewFailed")}</p> : data.upcoming_events.length === 0 ? <p className="text-sm text-ink-500">{t("console.noEvents")}</p> : (
            <ul className="space-y-2">
              {data.upcoming_events.map((e) => (
                <motion.li key={e.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-3 rounded-2xl bg-ink-50 p-3">
                  <span className="text-xl">{e.kind === "STAGE" ? "🤸" : "🏆"}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold text-ink-900 truncate">{e.name}</span>
                    <span className="block text-xs text-ink-500">{fmt.shortDate(e.starts_on)} · {e.club_name}{e.location ? ` · ${e.location}` : ""}</span>
                  </span>
                </motion.li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
