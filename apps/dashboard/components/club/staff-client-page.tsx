"use client";

import { useState } from "react";
import { AppShell, type NavItem } from "@/components/app-shell";
import { PageHeader } from "@/components/ui/page-header";
import { AttendanceTool } from "@/components/club/attendance-tool";
import { CalendarPanel, ClockPanel } from "@/components/club/coach-tools";
import { BeltAwardPanel } from "@/components/club/staff-tools";
import { RankingPanel } from "@/components/club/ranking-panel";
import { StaffMessagesPanel, StaffWorkPanel } from "@/components/club/staff-management";
import { CoachEarningsPanel, useClubFeatures } from "@/components/club/jav-courses";
import { useI18n } from "@/lib/i18n/provider";

const icon = (d: string) => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={d} />
  </svg>
);

/** L'area del treinador e del treinador adjunto: le presenze della lezione
 *  di oggi, il calendario delle sue lezioni, il cartellino, le cinture.
 *  Nei corsi JAV niente cinture e ranking, e al loro posto "I miei
 *  guadagni": il treinador lì è pagato a percentuale del suo corso. */
export function StaffClientPage({ email }: { email?: string }) {
  const { t } = useI18n();
  const [tab, setTab] = useState("attendance");
  const features = useClubFeatures();
  const all: NavItem[] = [
    { key: "attendance", label: t("coach.navToday"), icon: icon("M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4") },
    { key: "calendar", label: t("coach.navCalendar"), icon: icon("M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z") },
    { key: "clock", label: t("coach.navClock"), icon: icon("M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z") },
    { key: "work", label: t("staffMgmt.navWork"), icon: icon("M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"), notificationTypes: ["CLUB_STAFF_TASK_PAID"] },
    { key: "messages", label: t("staffMsg.nav"), icon: icon("M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"), notificationTypes: ["CLUB_STAFF_MESSAGE"] },
    { key: "belts", label: t("coach.navBelts"), icon: icon("M3 10h18M3 14h18M10 10v8l2-2 2 2v-8") },
    { key: "ranking", label: t("nav.club-ranking"), icon: icon("M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4zm10 1h3v2a3 3 0 01-3 3M7 5H4v2a3 3 0 003 3") },
    { key: "earnings", label: t("javCourses.earningsNav"), icon: icon("M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z") },
  ];
  const hidden = features.courses ? ["belts", "ranking"] : ["earnings"];
  const navItems = all.filter((n) => !hidden.includes(n.key));
  return (
    <AppShell roleLabel={t("coach.role")} email={email} navItems={navItems} activeKey={tab} onNavigate={setTab}>
      {tab === "attendance" && (
        <>
          <PageHeader eyebrow={t("coach.eyebrow")} title={t("coach.todayTitle")} subtitle={t("coach.todaySubtitle")} />
          <AttendanceTool />
        </>
      )}
      {tab === "calendar" && (
        <>
          <PageHeader eyebrow={t("coach.eyebrow")} title={t("coach.navCalendar")} subtitle={t("coach.calendarSubtitle")} />
          <CalendarPanel />
        </>
      )}
      {tab === "clock" && (
        <>
          <PageHeader eyebrow={t("coach.eyebrow")} title={t("coach.navClock")} subtitle={t("coach.clockSubtitle")} />
          <ClockPanel />
        </>
      )}
      {tab === "work" && (
        <>
          <PageHeader eyebrow={t("coach.eyebrow")} title={t("staffMgmt.navWork")} subtitle={t("staffMgmt.workSubtitle")} />
          <StaffWorkPanel />
        </>
      )}
      {tab === "messages" && (
        <>
          <PageHeader eyebrow={t("coach.eyebrow")} title={t("staffMsg.nav")} subtitle={t("staffMsg.subtitle")} />
          <StaffMessagesPanel />
        </>
      )}
      {tab === "belts" && features.belts && (
        <>
          <PageHeader eyebrow={t("coach.eyebrow")} title={t("coach.navBelts")} subtitle={t("coach.beltsSubtitle")} />
          <BeltAwardPanel />
        </>
      )}
      {tab === "ranking" && features.ranking && <RankingPanel admin />}
      {tab === "earnings" && features.courses && (
        <>
          <PageHeader eyebrow={t("coach.eyebrow")} title={t("javCourses.earningsNav")} subtitle={t("javCourses.earningsSubtitle")} />
          <CoachEarningsPanel />
        </>
      )}
    </AppShell>
  );
}
