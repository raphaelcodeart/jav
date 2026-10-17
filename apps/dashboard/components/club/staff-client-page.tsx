"use client";

import { useState } from "react";
import { AppShell, type NavItem } from "@/components/app-shell";
import { PageHeader } from "@/components/ui/page-header";
import { AttendanceTool } from "@/components/club/attendance-tool";
import { CalendarPanel, ClockPanel } from "@/components/club/coach-tools";
import { CoachHome } from "@/components/club/coach-home";
import { CoachNotebook } from "@/components/club/coach-notebook";
import { CoachBoard } from "@/components/club/coach-board";
import { CoachEventsPanel } from "@/components/club/event-reports";
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

/** L'area del treinador e del treinador adjunto: l'Início di ogni giorno,
 *  le presenze, il calendario delle sue lezioni, il quaderno (note delle
 *  lezioni e degli atleti), il cartellino, la bacheca, le cinture.
 *  Nei corsi JAV niente cinture e ranking, e al loro posto "I miei
 *  guadagni": il treinador lì è pagato a percentuale del suo corso. */
export function StaffClientPage({ email }: { email?: string }) {
  const { t } = useI18n();
  const [tab, setTab] = useState("home");
  // Dall'Início: le presenze di una lezione precisa, il quaderno sugli atleti.
  const [attendanceAt, setAttendanceAt] = useState<{ date: string; courseId: string } | null>(null);
  const [notebookTab, setNotebookTab] = useState<"lessons" | "athletes">("lessons");
  const go = (key: string, attendance?: { date: string; courseId: string }) => {
    setAttendanceAt(key === "attendance" ? attendance ?? null : null);
    if (key === "athletes" || key === "notebook") setNotebookTab(key === "athletes" ? "athletes" : "lessons");
    setTab(key === "athletes" ? "notebook" : key);
  };
  const features = useClubFeatures();
  const all: NavItem[] = [
    { key: "home", label: t("coach2.nav.home"), icon: icon("M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6") },
    { key: "attendance", label: t("coach.navToday"), icon: icon("M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4") },
    { key: "calendar", label: t("coach.navCalendar"), icon: icon("M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z") },
    { key: "events", label: t("evrep.nav"), icon: icon("M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4z") },
    { key: "notebook", label: t("coach2.nav.notebook"), icon: icon("M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253") },
    { key: "clock", label: t("coach.navClock"), icon: icon("M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z") },
    { key: "work", label: t("staffMgmt.navWork"), icon: icon("M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"), notificationTypes: ["CLUB_STAFF_TASK_PAID"] },
    { key: "messages", label: t("staffMsg.nav"), icon: icon("M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"), notificationTypes: ["CLUB_STAFF_MESSAGE"] },
    { key: "board", label: t("coach2.nav.board"), icon: icon("M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z") },
    { key: "belts", label: t("coach.navBelts"), icon: icon("M3 10h18M3 14h18M10 10v8l2-2 2 2v-8") },
    { key: "ranking", label: t("nav.club-ranking"), icon: icon("M8 21h8m-4-4v4m-5-17h10v5a5 5 0 01-10 0V4zm10 1h3v2a3 3 0 01-3 3M7 5H4v2a3 3 0 003 3") },
    { key: "earnings", label: t("javCourses.earningsNav"), icon: icon("M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z") },
  ];
  const hidden = features.courses ? ["belts", "ranking", "events"] : ["earnings"];
  const navItems = all.filter((n) => !hidden.includes(n.key));
  return (
    <AppShell clubBranding roleLabel={t("coach.role")} email={email} navItems={navItems} activeKey={tab} onNavigate={(k) => go(k)}>
      {tab === "home" && <CoachHome onNavigate={go} />}
      {tab === "attendance" && (
        <>
          <PageHeader eyebrow={t("coach.eyebrow")} title={t("coach.todayTitle")} subtitle={t("coach.todaySubtitle")} />
          <AttendanceTool key={attendanceAt ? `${attendanceAt.date}-${attendanceAt.courseId}` : "today"} initial={attendanceAt ?? undefined} />
        </>
      )}
      {tab === "notebook" && (
        <>
          <PageHeader eyebrow={t("coach.eyebrow")} title={t("coach2.nav.notebook")} subtitle={t("coach2.nb.subtitle")} />
          <CoachNotebook key={notebookTab} initialTab={notebookTab} />
        </>
      )}
      {tab === "events" && features.competitions && (
        <>
          <PageHeader eyebrow={t("coach.eyebrow")} title={t("evrep.nav")} subtitle={t("evrep.navSubtitle")} />
          <CoachEventsPanel />
        </>
      )}
      {tab === "board" && <CoachBoard />}
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
