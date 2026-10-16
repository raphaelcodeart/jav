"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { AccountingPanel } from "@/components/accounting-panel";
import { AppShell, type NavItem } from "@/components/app-shell";
import { ContractRequestWizard } from "@/components/contract-request-wizard";
import { ContractRequestsList, type WizardTarget } from "@/components/contract-requests-list";
import { DashboardWalletStats } from "@/components/dashboard-wallet-stats";
import { WelcomeBonusCard } from "@/components/welcome-bonus-card";
import { CustomerOrdersPanel } from "@/components/customer-orders-panel";
import { CustomerProductsPanel } from "@/components/customer-products-panel";
import { CustomerPromoterApplicationCard } from "@/components/customer-promoter-application-card";
import { FriendReferralsPanel } from "@/components/friend-referrals-panel";
import { DocumentationFeed } from "@/components/documentation-feed";
import { SectionBanner } from "@/components/section-banner";
import { SupportTicketsPanel } from "@/components/support-tickets-panel";
import { CustomerProductRequestsPanel } from "@/components/product-requests";
import { WalletPanel } from "@/components/wallet-panel";
import { CustomerSettingsPanel } from "@/components/customer-settings-panel";
import { ClubBoard } from "@/components/club/club-board";
import { GamesHub } from "@/components/game/games-hub";
import { CompetitionsPanel } from "@/components/club/competitions-panel";
import { CoursesPanel } from "@/components/club/courses-panel";
import { FamilyAccounting } from "@/components/club/family-accounting";
import { FamilyHome } from "@/components/club/family-home";
import { RankingPanel } from "@/components/club/ranking-panel";
import { useClubFeatures } from "@/components/club/jav-courses";
import { useI18n } from "@/lib/i18n/provider";
import type { ContractRead, CustomerRead } from "@/lib/types";

async function fetchMyCustomerRecord(): Promise<CustomerRead | null> {
  const res = await fetch("/api/proxy/customers/me");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Impossibile caricare la tua anagrafica.");
  return res.json();
}

interface CustomerClientPageProps {
  /** Server-fetched at page load. No longer rendered directly: since
      Session 52 contracts are shown inside their pratiche
      (contract-requests-list.tsx), which load themselves. */
  contracts: ContractRead[];
  email?: string;
  /** Needed to build the customer's own "Invita un amico" link, which
      carries ?org= exactly like a promoter's referral link does. */
  organizationId?: string;
}

// The club comes first (docs/club-portal.md): for a parent the home IS the
// family's club page -- athletes, fees, competitions. Everything that came
// before (wallet, contracts, shop orders...) stays, one tap further away.
const CLUB_NAV_ITEMS: NavItem[] = [
  {
    key: "club",
    label: "Il mio club",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l9-9 9 9M5 10v10a1 1 0 001 1h3a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1h3a1 1 0 001-1V10" />
      </svg>
    ),
  },
  {
    key: "club-competitions",
    label: "Gare",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
    ),
  },
  {
    key: "club-ranking",
    label: "Ranking",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4zm10 1h3v2a3 3 0 01-3 3M7 5H4v2a3 3 0 003 3" />
      </svg>
    ),
  },
];

const CLUB_COURSES_ITEM: NavItem = {
  key: "club-courses",
  label: "Corsi",
  icon: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
};

// "I miei conti": quanto si è pagato, quanto resta, sconti e wallet
// (family-accounting.tsx). Uno per account, persona per persona se ci sono figli.
const CLUB_ACCOUNTING_ITEM: NavItem = {
  key: "club-accounting",
  label: "I miei conti",
  icon: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  ),
};

// La bacheca del club: le notizie della segreteria e i documenti condivisi (club-board.tsx).
const CLUB_BOARD_ITEM: NavItem = {
  key: "club-board",
  label: "Bacheca",
  icon: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
    </svg>
  ),
};

// JAV Games: un mondo a parte (components/game, docs/games.md).
const GAMES_ITEM: NavItem = {
  key: "games",
  label: "Giochi",
  icon: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 11h4M8 9v4m7-1h.01M18 10h.01M7 6h10a4 4 0 014 4v4a4 4 0 01-4 4c-1.5 0-2.3-1-3-2h-4c-.7 1-1.5 2-3 2a4 4 0 01-4-4v-4a4 4 0 014-4z" />
    </svg>
  ),
};

const CLUB_TABS = ["club", "club-board", "games", "club-competitions", "club-ranking", "club-courses", "club-accounting"] as const;

const NAV_ITEMS: NavItem[] = [
  {
    key: "jav-contracts",
    // Was "Contratti Jav" -- accurate back when this tab was just
    // the contract-activation list, but since Session 33's redesign it's
    // the actual dashboard home (wallet stats, quick-access shortcuts,
    // THEN the contracts list), so the label and icon were updated to
    // match what a customer actually lands on -- "Home" reads clearer to
    // a non-technical user on a mobile tab bar than "Dashboard" would.
    label: "Wallet e bonus",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l9-9 9 9M5 10v10a1 1 0 001 1h3a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1h3a1 1 0 001-1V10" />
      </svg>
    ),
  },
  {
    key: "products",
    label: "Shop",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    key: "orders",
    label: "I miei Ordini",
    notificationTypes: ["ORDER_PAID", "ORDER_SHIPPED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 2l1 4H4a1 1 0 00-1 1v1a1 1 0 001 1h16a1 1 0 001-1V7a1 1 0 00-1-1h-6l1-4M5 9v9a2 2 0 002 2h10a2 2 0 002-2V9M10 13h4" />
      </svg>
    ),
  },
  {
    key: "contracts",
    label: "I miei Contratti",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    key: "product-requests",
    label: "Le mie richieste",
    notificationTypes: ["PRODUCT_REQUEST_REPLY"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0zM11 8v6m-3-3h6" />
      </svg>
    ),
  },
  {
    key: "support",
    label: "Supporto & Assistenza",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
  },
  {
    key: "friend-referrals",
    label: "Invita un amico",
    notificationTypes: ["FRIEND_REFERRAL_ACTIVATED", "FRIEND_REFERRAL_REWARD_HANDLED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
  },
  {
    key: "promoter-application",
    label: "Lavora con noi",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-8a4 4 0 11-8 0 4 4 0 018 0zm6 3a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
  },
  {
    key: "documentation",
    label: "Documentazione",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    key: "wallet",
    label: "Wallet",
    notificationTypes: ["CASHBACK_RECEIVED", "WALLET_TRANSFER_RECEIVED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
      </svg>
    ),
  },
  {
    key: "accounting",
    label: "Contabilità",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m-6 4h6m-6 4h4M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z" />
      </svg>
    ),
  },
  {
    // Session 87: per ora il metodo di conferma dei JavCash (PIN o codice
    // via email). Si apre anche dal menu dell'avatar in alto.
    key: "settings",
    label: "Impostazioni",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

/** Quick-access shortcuts on the dashboard home -- one click into the
    sections a customer actually returns to often, instead of only
    reachable via the sidebar. Same pattern as the promoter home and the
    admin Panoramica. */
// Club first, then the Shop (4th tab on phones: ordering a judogi is the
// other thing parents do here), then everything that came before.
// Della vecchia applicazione restano solo le voci che servono a una
// famiglia del club: contratti, pratiche, rete promoter, documentazione e
// contabilità non c'entrano più e non si mostrano.
const FAMILY_KEYS = new Set(["orders", "wallet", "support", "settings"]);
const [, SHOP_ITEM, ...OTHER_ITEMS] = NAV_ITEMS;
const FAMILY_NAV_ITEMS: NavItem[] = [
  CLUB_NAV_ITEMS[0]!,
  CLUB_BOARD_ITEM,
  ...CLUB_NAV_ITEMS.slice(1),
  GAMES_ITEM,
  ...(SHOP_ITEM ? [SHOP_ITEM] : []),
  CLUB_COURSES_ITEM,
  CLUB_ACCOUNTING_ITEM,
  ...OTHER_ITEMS.filter((item) => FAMILY_KEYS.has(item.key)),
];

const HOME_QUICK_LINKS: { key: string; label: string; description: string; icon: React.ReactNode }[] = [
  {
    key: "contracts",
    label: "Contratti",
    description: "Iscrizioni e abbonamenti",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    key: "products",
    label: "Shop",
    description: "Acquista prodotti",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    key: "orders",
    label: "I miei Ordini",
    description: "Dettaglio dei tuoi acquisti",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 2l1 4H4a1 1 0 00-1 1v1a1 1 0 001 1h16a1 1 0 001-1V7a1 1 0 00-1-1h-6l1-4M5 9v9a2 2 0 002 2h10a2 2 0 002-2V9M10 13h4" />
      </svg>
    ),
  },
  {
    key: "wallet",
    label: "Wallet",
    description: "Saldo e movimenti",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
      </svg>
    ),
  },
  {
    key: "accounting",
    label: "Contabilità",
    description: "Tutte le tue transazioni",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 7h6m-6 4h6m-6 4h4M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z" />
      </svg>
    ),
  },
  {
    key: "support",
    label: "Supporto",
    description: "Hai bisogno di aiuto?",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
  },
];

export function CustomerClientPage({ email, organizationId }: CustomerClientPageProps) {
  // "jav-contracts" is the customer's home -- matches the Shop's old default
  // landing tab, back when Jav contracts were its first category
  // (see NAV_ITEMS ordering below).
  const router = useRouter();
  const searchParams = useSearchParams();
  // Session 88: il link che il promoter manda al cliente dopo aver preparato
  // la pratica (/customer?pratica=<id>) apre direttamente il suo pagamento.
  // Letto all'avvio, non in un effetto: la pratica si apre al primo disegno.
  const linkedPratica = /^[0-9a-f-]{36}$/i.test(searchParams.get("pratica") ?? "") ? searchParams.get("pratica") : null;
  const [activeTab, setActiveTab] = useState<(typeof CLUB_TABS)[number] | "jav-contracts" | "contracts" | "products" | "orders" | "product-requests" | "support" | "promoter-application" | "friend-referrals" | "documentation" | "wallet" | "accounting" | "settings">(linkedPratica ? "contracts" : "club");
  // "Attiva nuovo contratto" / "Riprendi" / "Paga": the pratica wizard,
  // opened over whichever tab the customer is on.
  const [wizard, setWizard] = useState<WizardTarget | "new" | null>(
    linkedPratica ? { requestId: linkedPratica, step: "summary" } : null
  );

  // A deep-link from an email ("Vai al wallet" etc, ?tab=wallet) switches to
  // that tab. The query params are stripped right after reading them so a
  // page refresh lands on the home again.
  const VALID_TABS = [
    ...CLUB_TABS, "jav-contracts", "activate-contract", "contracts", "products", "orders", "product-requests", "support",
    "promoter-application", "friend-referrals", "documentation", "wallet", "accounting", "settings",
  ] as const;

  useEffect(() => {
    const tab = searchParams.get("tab");
    if (searchParams.get("pratica")) {
      // Già aperta dallo stato iniziale: qui si toglie solo il parametro,
      // così un ricaricamento non la riapre.
      router.replace("/customer", { scroll: false });
      return;
    }
    const isValidTab = (VALID_TABS as readonly string[]).includes(tab ?? "");
    if (!isValidTab) return;

    // "activate-contract" was its own tab until Session 52; old links and
    // emails still point at it.
    if (tab === "activate-contract") setActiveTab("contracts");
    else setActiveTab(tab as typeof activeTab);
    router.replace("/customer", { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const { data: myCustomer } = useQuery({
    queryKey: ["customer", "me", "record"],
    queryFn: fetchMyCustomerRecord,
  });

  const isClubTab = (CLUB_TABS as readonly string[]).includes(activeTab);
  const { t } = useI18n();
  // The labels above stay as the Italian source; the menu shows them in the
  // chosen language, falling back to them for a key not translated yet.
  // Nei corsi JAV nelle scuole non ci sono gare né ranking: le voci spariscono.
  const features = useClubFeatures();
  const navItems = useMemo(() => FAMILY_NAV_ITEMS
    .filter((item) => (item.key !== "club-competitions" || features.competitions) && (item.key !== "club-ranking" || features.ranking))
    .map((item) => ({ ...item, label: t.dyn(`nav.${item.key}`, item.label) })), [t, features.competitions, features.ranking]);

  return (
    <AppShell
      roleLabel={t("customer.roleLabel")}
      email={email}
      navItems={navItems}
      activeKey={activeTab}
      onNavigate={(key) => setActiveTab(key as typeof activeTab)}
      // The club pages carry their own hero/headers.
      headerTitle={isClubTab ? undefined : t("customer.headerTitle")}
      showCart
      // Not on Contabilità (Session 54): the page has its own heading, and the
      // space goes to the totals.
      headerSubtitle={
        activeTab === "accounting" || isClubTab
          ? undefined
          : t("customer.headerSubtitle")
      }
    >
      {activeTab === "contracts" && (
        <div className="space-y-6">
          <SectionBanner image="contracts" alt="I miei Contratti" />
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl border border-brand-500/25 bg-gradient-to-br from-brand-500/10 to-transparent">
            <div>
              <h3 className="text-base font-bold text-slate-900">Le tue pratiche di attivazione</h3>
              <p className="text-xs text-slate-500 mt-1">
                Una pratica può contenere uno o più contratti, ognuno con il suo pacchetto. Dati, documenti e
                pagamento li gestisci una volta sola.
              </p>
            </div>
            <button
              onClick={() => setWizard("new")}
              className="shrink-0 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-gradient-to-r from-brand-600 to-brand-400 hover:from-brand-500 hover:to-brand-400 text-white text-sm font-bold shadow-lg shadow-brand-500/20 transition cursor-pointer"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
              </svg>
              Attiva nuovo contratto
            </button>
          </div>
          {/* I pacchetti non si sfogliano più qui (Session 83): si scelgono,
              con i loro dettagli, solo nel passo «Contratti» della pratica. */}
          <ContractRequestsList mode="customer" onOpenWizard={(target) => setWizard(target)} />
        </div>
      )}

      {activeTab === "club" && <FamilyHome onNavigate={(key) => setActiveTab(key as typeof activeTab)} />}
      {activeTab === "club-board" && <ClubBoard />}
      {activeTab === "games" && <GamesHub />}
      {activeTab === "club-competitions" && features.competitions && <CompetitionsPanel />}
      {activeTab === "club-ranking" && features.ranking && <RankingPanel />}
      {activeTab === "club-courses" && <CoursesPanel />}
      {activeTab === "club-accounting" && <FamilyAccounting onNavigate={(key) => setActiveTab(key as typeof activeTab)} />}

      {activeTab === "jav-contracts" && (
        <div className="space-y-6">
          <SectionBanner image="contracts" alt="Area Cliente" compact>
            <div>
              <p className="text-[11px] font-semibold text-brand-600 uppercase tracking-wider">Bentornato</p>
              <h2 className="text-lg sm:text-xl font-bold text-slate-900 truncate max-w-[70vw] sm:max-w-none">{email}</h2>
            </div>
          </SectionBanner>

          <WelcomeBonusCard />


          <DashboardWalletStats />

          <div>
            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2.5">Accesso rapido</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {HOME_QUICK_LINKS.map((link) => (
                <button
                  key={link.key}
                  onClick={() => setActiveTab(link.key as typeof activeTab)}
                  className="group flex flex-col items-start gap-3 p-4 rounded-2xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 hover:border-brand-500/40 hover:shadow-lg hover:shadow-brand-500/10 transition-all duration-200 cursor-pointer text-left"
                >
                  <span className="p-2.5 rounded-xl bg-brand-500/10 text-brand-600 group-hover:bg-brand-500 group-hover:text-white transition-colors">
                    {link.icon}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-slate-900 truncate">
                      {link.label}
                    </span>
                    <span className="block text-[11px] text-slate-500 truncate">{link.description}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          <CustomerPromoterApplicationCard hideWhenActive />
        </div>
      )}

      {activeTab === "products" && (
        <div className="space-y-6">
          <SectionBanner image="products" alt="Shop" />
          <CustomerProductsPanel
            visibleCategories={["PARTNER", "DROPSHIPPING"]}
            showShopTab
            onOpenProductRequests={() => setActiveTab("product-requests")}
          />
        </div>
      )}

      {activeTab === "product-requests" && (
        <div className="space-y-6">
          <SectionBanner image="products" alt="Le mie richieste" />
          <CustomerProductRequestsPanel />
        </div>
      )}

      {activeTab === "orders" && (
        <div className="space-y-6">
          <SectionBanner image="products" alt="I miei Ordini" />
          <CustomerOrdersPanel />
        </div>
      )}

      {activeTab === "support" && (
        <div className="space-y-6">
          <SectionBanner image="support" alt="Supporto & Assistenza" />
          <SupportTicketsPanel
            title="Supporto & Assistenza"
            subtitle="Apri un ticket per problemi tecnici, fatturazione o domande sul tuo contratto: un operatore ti risponderà qui."
          />
        </div>
      )}

      {activeTab === "friend-referrals" && (
        <FriendReferralsPanel organizationId={organizationId} />
      )}

      {activeTab === "promoter-application" && (
        <div className="space-y-6">
          <CustomerPromoterApplicationCard />
        </div>
      )}

      {activeTab === "documentation" && (
        <div className="space-y-6">
          <SectionBanner image="documentation" alt="Documentazione" />
          <DocumentationFeed />
        </div>
      )}

      {activeTab === "wallet" && (
        <div className="space-y-6">
          <SectionBanner image="wallets" alt="Wallet" />
          <WalletPanel />
        </div>
      )}

      {activeTab === "settings" && <CustomerSettingsPanel />}

      {activeTab === "accounting" && (
        <AccountingPanel onOpenTab={(tab) => setActiveTab(tab as typeof activeTab)} />
      )}
      {wizard && (
        <ContractRequestWizard
          requestId={wizard === "new" ? undefined : wizard.requestId}
          initialStep={wizard === "new" ? undefined : wizard.step}
          customerKind={myCustomer?.kind ?? null}
          accountEmail={email}
          holder={{
            firstName: myCustomer?.first_name,
            lastName: myCustomer?.last_name,
            pec: myCustomer?.pec,
            fiscalCode: myCustomer?.fiscal_code,
          }}
          onClose={() => setWizard(null)}
        />
      )}
    </AppShell>
  );
}
