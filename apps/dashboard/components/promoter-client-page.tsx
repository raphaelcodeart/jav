"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ShareButtons } from "@/components/share-buttons";
import { AppShell, type NavItem } from "@/components/app-shell";
import { BranchTable } from "@/components/branch-table";
import { DashboardWalletStats } from "@/components/dashboard-wallet-stats";
import { WelcomeBonusCard } from "@/components/welcome-bonus-card";
import { BranchVisualizer } from "@/components/branch-visualizer";
import { MyCommissions } from "@/components/my-commissions";
import { CommissionSimulator } from "@/components/commission-simulator";
import { FriendReferralsPanel } from "@/components/friend-referrals-panel";
import { NetworkCustomersPanel } from "@/components/network-customers-panel";
import { NewCustomerBanner } from "@/components/new-customer-banner";
import { DocumentationFeed } from "@/components/documentation-feed";
import { PromoterAziendaPanel } from "@/components/promoter-azienda-panel";
import { RecruitForm } from "@/components/recruit-form";
import { SectionBanner } from "@/components/section-banner";
import { SupportTicketsPanel } from "@/components/support-tickets-panel";
import { WalletPanel } from "@/components/wallet-panel";
import type { AgentProfileRead, BranchMemberRead, PromoterCodeRead, RankRead } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

interface PromoterClientPageProps {
  me: AgentProfileRead | null;
  branch: BranchMemberRead[];
  email?: string;
  organizationId?: string;
}

async function fetchMyReferralCode(): Promise<PromoterCodeRead | null> {
  const res = await fetch("/api/proxy/referral/mine");
  if (!res.ok) throw new Error("Impossibile caricare il link referral.");
  return res.json();
}

async function fetchRanks(): Promise<RankRead[]> {
  const res = await fetch("/api/proxy/commissions/ranks");
  if (!res.ok) throw new Error("Impossibile caricare le qualifiche.");
  return res.json();
}

const NAV_ITEMS: NavItem[] = [
  {
    key: "azienda",
    label: "La mia Azienda",
    notificationTypes: ["PROMOTER_APPROVED", "PROMOTER_REJECTED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-4" />
      </svg>
    ),
  },
  {
    key: "network",
    label: "Rete Commerciale",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
      </svg>
    ),
  },
  {
    // Separate from "Rete Commerciale" on purpose: that one is the tree that
    // pays commissions, this one is the flat "chi ho invitato" list every
    // account has, promoter or not (see friend_referrals/models.py).
    key: "invita-amici",
    label: "Invita un amico",
    notificationTypes: ["FRIEND_REFERRAL_ACTIVATED", "FRIEND_REFERRAL_REWARD_HANDLED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
  },
  {
    key: "customers",
    label: "Miei Clienti",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    key: "commissions",
    label: "Movimenti Provvigioni",
    notificationTypes: ["COMMISSION_EARNED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3v-6m-3 6v-1m6-13H9a2 2 0 00-2 2v14a2 2 0 002 2h6a2 2 0 002-2V6a2 2 0 00-2-2z" />
      </svg>
    ),
  },
  {
    key: "simulator",
    label: "Simulatore Provvigioni",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
  },
  {
    key: "support",
    label: "Supporto",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
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
];

const QUICK_LINKS: { key: string; label: string; description: string; icon: React.ReactNode }[] = [
  {
    key: "customers",
    label: "Miei Clienti",
    description: "Clienti e nuovi contratti",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    key: "network",
    label: "Rete Commerciale",
    description: "Il tuo albero commerciale",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
      </svg>
    ),
  },
  {
    key: "commissions",
    label: "Movimenti Provvigioni",
    description: "Il tuo estratto conto",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 7h6m0 10v-3m-3 3v-6m-3 6v-1m6-13H9a2 2 0 00-2 2v14a2 2 0 002 2h6a2 2 0 002-2V6a2 2 0 00-2-2z" />
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
];

const PROMOTER_VALID_TABS = [
  "azienda", "network", "invita-amici", "customers", "commissions", "simulator", "support", "documentation", "wallet",
] as const;

export function PromoterClientPage({ me, branch, email, organizationId }: PromoterClientPageProps) {
  const { t } = useI18n();
  const navLabel = (key: string, fallback: string) => t.dyn(`net.promoter.nav.${key.replace(/-/g, "_")}`, fallback);
  const navItems = useMemo(
    () => NAV_ITEMS.map((item) => ({ ...item, label: t.dyn(`net.promoter.nav.${item.key.replace(/-/g, "_")}`, item.label) })),
    [t],
  );
  const [activeTab, setActiveTab] = useState<"azienda" | "network" | "invita-amici" | "customers" | "commissions" | "simulator" | "support" | "documentation" | "wallet">("azienda");
  // «Inserisci un nuovo cliente» dalla home: apre «Miei Clienti» gia' sul
  // form del nuovo cliente. Qualsiasi altra navigazione lo spegne, cosi'
  // chi apre «Miei Clienti» dal menu trova la lista come sempre.
  const [openNewCustomer, setOpenNewCustomer] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();
  const maxDepth = branch.reduce((max, m) => Math.max(max, m.depth), 0);

  // Deep-link into a specific tab, e.g. "Vai al wallet" from an email --
  // same pattern as customer-client-page.tsx's own tab-from-URL effect.
  useEffect(() => {
    // "pratiche" was a tab of its own in Session 66; now part of "Miei Clienti".
    const requested = searchParams.get("tab");
    const tab = requested === "pratiche" ? "customers" : requested;
    if (!tab || !(PROMOTER_VALID_TABS as readonly string[]).includes(tab)) return;
    setActiveTab(tab as typeof activeTab);
    router.replace("/promoter", { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { data: referralCode } = useQuery({
    queryKey: ["promoter", "referral-mine"],
    queryFn: fetchMyReferralCode,
    enabled: !!me,
  });
  const { data: ranks } = useQuery({
    queryKey: ["promoter", "ranks"],
    queryFn: fetchRanks,
    enabled: !!me,
  });
  const rankName = ranks?.find((r) => r.code === me?.rank_code)?.name;
  // Derived, not stored: the link is a pure function of the code and the org.
  const personalLink = (() => {
    if (!referralCode || typeof window === "undefined") return "";
    const url = new URL(`/r/${referralCode.code}`, window.location.origin);
    if (organizationId) url.searchParams.set("org", organizationId);
    return url.toString();
  })();

  return (
    <AppShell
      roleLabel={t("net.promoter.roleLabel")}
      email={email}
      navItems={navItems}
      activeKey={activeTab}
      onNavigate={(key) => {
        setOpenNewCustomer(false);
        setActiveTab(key as typeof activeTab);
      }}
      headerTitle={t("net.promoter.welcome", { name: me?.display_name || t("net.promoter.fallbackName") })}
      centerHeaderActions
      headerActions={
        me ? (
          <div className="w-full flex flex-wrap items-center justify-between gap-4 bg-slate-50 border border-slate-200 rounded-2xl px-5 py-3 glass-card">
            <div className="flex flex-wrap items-center gap-4">
              <div>
                <p className=" font-bold text-slate-500 uppercase tracking-wider">{t("net.promoter.code")}</p>
                <p className="font-mono text-base text-amber-700 font-semibold">{me.promoter_code}</p>
              </div>
              <div className="h-8 w-px bg-slate-200" />
              <div>
                <p className=" font-bold text-slate-500 uppercase tracking-wider">{t("net.promoter.currentRank")}</p>
                <p className="text-2xl text-brand-600 font-bold leading-tight">{me.rank_code || t("net.promoter.noRank")}</p>
                {rankName && <p className="text-[10px] text-slate-500 mt-0.5">{rankName}</p>}
              </div>
            </div>
            {/* The destinations in full, not behind a menu -- a promoter
                sends this link many times a day, and a tap saved on every
                send is the whole point. Icons only on a phone: this header
                is on every page of the promoter dashboard, and six labelled
                pills would wrap onto three lines and push the page down. */}
            <div className="flex flex-col items-start sm:items-end gap-1.5">
              <p className=" font-bold text-slate-500 uppercase tracking-wider">
                {t("net.promoter.shareLink")}
              </p>
              <ShareButtons
                url={personalLink}
                text={t("net.promoter.shareText")}
                hideLabelsOnMobile
              />
            </div>
          </div>
        ) : undefined
      }
    >
      {!me ? (
        <div className="glass-card rounded-2xl p-8 border-rose-500/10 text-center max-w-xl mx-auto mt-12">
          <svg className="w-12 h-12 text-rose-400 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <h3 className="text-lg font-semibold text-slate-900">{t("net.promoter.noProfile.title")}</h3>
          <p className="text-sm text-slate-500 mt-2">
            {t("net.promoter.noProfile.body")}
          </p>
        </div>
      ) : (
        <div>
          {activeTab === "azienda" && (
            <div className="space-y-6">
              <SectionBanner image="contracts" alt={navLabel("azienda", "La mia Azienda")} compact>
                <div>
                  <p className="text-[11px] font-semibold text-brand-600 uppercase tracking-wider">{t("net.promoter.welcomeBack")}</p>
                  <h2 className="text-lg sm:text-xl font-bold text-slate-900 truncate max-w-[70vw] sm:max-w-none">{me.display_name}</h2>
                </div>
              </SectionBanner>

              <WelcomeBonusCard />

              <NewCustomerBanner
                onClick={() => {
                  setOpenNewCustomer(true);
                  setActiveTab("customers");
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              />


              <DashboardWalletStats />

              {/* Quick-access section shortcuts, same pattern as the admin
                  Panoramica -- makes the rest of the promoter area one click
                  away instead of only reachable via the sidebar. */}
              <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">{t("net.promoter.quickAccess")}</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                {QUICK_LINKS.map((link) => (
                  <button
                    key={link.key}
                    onClick={() => {
                      setOpenNewCustomer(false);
                      setActiveTab(link.key as typeof activeTab);
                    }}
                    className="group flex flex-col items-start gap-3 p-4 rounded-2xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 hover:border-brand-500/40 hover:shadow-lg hover:shadow-brand-500/10 transition-all duration-200 cursor-pointer text-left"
                  >
                    <span className="p-2.5 rounded-xl bg-brand-500/10 text-brand-600 group-hover:bg-brand-500 group-hover:text-white transition-colors">
                      {link.icon}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-slate-900 truncate">
                        {navLabel(link.key, link.label)}
                      </span>
                      <span className="block text-[11px] text-slate-500 truncate">{t.dyn(`net.promoter.quick.${link.key}`, link.description)}</span>
                    </span>
                  </button>
                ))}
              </div>

              <PromoterAziendaPanel agentId={me.id} />
            </div>
          )}

          {activeTab === "invita-amici" && (
            <div className="space-y-6">
              <FriendReferralsPanel organizationId={organizationId} />
            </div>
          )}

          {activeTab === "customers" && (
            <div className="space-y-6">
              <SectionBanner image="customers" alt={navLabel("customers", "Miei Clienti")} />
              <NetworkCustomersPanel
                key={openNewCustomer ? "new-customer" : "list"}
                startWithNewCustomer={openNewCustomer}
              />
            </div>
          )}

          {activeTab === "network" && (
            <div className="space-y-6">
              <SectionBanner image="network" alt={navLabel("network", "Rete Commerciale")} />
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="flex items-center gap-3 text-xs">
                  <span className="px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-700 border border-amber-500/20 font-semibold">
                    {t("net.promoter.agentsInBranch", { n: branch.length })}
                  </span>
                  <span className="px-2.5 py-1 rounded-full bg-brand-500/10 text-brand-600 border border-brand-500/20 font-semibold">
                    {t("net.promoter.maxDepth", { n: maxDepth })}
                  </span>
                </div>
                <RecruitForm onRecruited={() => router.refresh()} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                  <BranchVisualizer members={branch} />
                </div>
                <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
                  <h3 className="text-lg font-semibold text-slate-900 mb-2">{t("net.promoter.branchDetail")}</h3>
                  <p className="text-xs text-slate-500 mb-6">
                    {t("net.promoter.branchDetailHint")}
                  </p>
                  <div className="overflow-x-auto">
                    <BranchTable members={branch} />
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === "commissions" && (
            <div className="max-w-4xl mx-auto space-y-6">
              <SectionBanner image="commissions" alt={navLabel("commissions", "Movimenti Provvigioni")} />
              <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
                <h3 className="text-lg font-semibold text-slate-900 mb-2">{t("net.promoter.statementTitle")}</h3>
                <p className="text-xs text-slate-500 mb-6">
                  {t("net.promoter.statementHint")}
                </p>
                <MyCommissions />
              </div>
            </div>
          )}

          {activeTab === "simulator" && (
            <div className="max-w-5xl mx-auto space-y-6">
              <SectionBanner image="commissions" alt={navLabel("simulator", "Simulatore Provvigioni")} />
              <CommissionSimulator agentId={me.id} />
            </div>
          )}

          {activeTab === "support" && (
            <div className="space-y-6">
              <SectionBanner image="support" alt={navLabel("support", "Supporto")} />
              <SupportTicketsPanel
                title={navLabel("support", "Supporto")}
                subtitle={t("net.promoter.supportSubtitle")}
              />
            </div>
          )}

          {activeTab === "documentation" && (
            <div className="space-y-6">
              <SectionBanner image="documentation" alt={navLabel("documentation", "Documentazione")} />
              <DocumentationFeed />
            </div>
          )}

          {activeTab === "wallet" && (
            <div className="space-y-6">
              <SectionBanner image="wallets" alt={navLabel("wallet", "Wallet")} />
              <WalletPanel />
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
