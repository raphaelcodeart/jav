"use client";

import { useState } from "react";
import { AppShell, type NavItem } from "@/components/app-shell";
import { ClubAdminPanel, sectionsFor, type ClubSection } from "@/components/club/club-admin-panel";
import { useCurrentClub } from "@/components/club/current-club";
import { useI18n } from "@/lib/i18n/provider";

const GROUPS = { people: "clubGroup.people", money: "clubGroup.money", activity: "clubGroup.activity", club: "clubGroup.club" } as const;

/** La segreteria lavora su un club solo: il menu laterale sono le sezioni
 *  del club, raggruppate (persone, soldi, attività, club). */
export function SecretaryClientPage({ email }: { email?: string }) {
  const { t } = useI18n();
  const { data: club } = useCurrentClub();
  const [section, setSection] = useState<ClubSection>("overview");
  const navItems: NavItem[] = sectionsFor(club?.kind).map((s) => ({
    key: s.key,
    label: t.dyn(`clubNav.${s.key}`, s.key),
    icon: <span className="text-base leading-none" aria-hidden="true">{s.icon}</span>,
    group: t(GROUPS[s.group]),
    // Il pallino sui "Messaggi" quando ne arriva uno dal sito.
    notificationTypes: s.key === "messages" ? ["CONTACT_MESSAGE"] : undefined,
  }));
  return (
    <AppShell roleLabel={club ? `${t("clubs.role.SECRETARY")} · ${club.name}` : t("clubs.role.SECRETARY")} email={email}
      navItems={navItems} activeKey={section} onNavigate={(k) => setSection(k as ClubSection)} wide={section === "athletes"}>
      <ClubAdminPanel section={section} onGo={setSection} />
    </AppShell>
  );
}
