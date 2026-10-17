"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { FeeStatusPill } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { AchievementBadge } from "@/components/ui/gamification";
import { ProgressBar } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { CertificatesTab } from "@/components/club/athlete-detail-modal";
import { ClubBoard } from "@/components/club/club-board";
import { InviteCard } from "@/components/club/invite-card";
import { GamesHub } from "@/components/game/games-hub";
import { AppShell, type NavItem } from "@/components/app-shell";
import { AreaCompetitions, AthleteMoneyCard } from "@/components/club/athlete-area-extras";
import { AreaEvents } from "@/components/club/area-events";
import { Tabs } from "@/components/ui/tabs";
import { AthleteHealthCard } from "@/components/club/athlete-health-card";
import { AthletePayModal } from "@/components/club/athlete-pay-modal";
import { SeasonMonthsPanel } from "@/components/club/season-months";
import { ACHIEVEMENT_ICONS, clubGet, clubSend, type AthleteDetail } from "@/lib/club";
import { cn } from "@/lib/cn";
import type { MessageKey } from "@/lib/i18n/messages/it";
import { useI18n } from "@/lib/i18n/provider";
import { feeLabel } from "@/lib/fee-label";
import { useEventsReturn } from "@/lib/events-return";

interface AreaRef { id: string; name: string; photo_url: string | null; is_own: boolean }
interface AreaLesson { date: string; course_id: string; course_name: string; starts_at: string; ends_at: string; status: "PRESENT" | "ABSENT" | "MISSED" | "TODAY" | "UPCOMING" }
interface AthleteArea extends AthleteDetail {
  is_minor: boolean;
  viewer_is_athlete: boolean;
  can_manage: boolean;
  /** Il titolare, o l'atleta stesso dai 18 anni federali: può caricare la prova. */
  can_pay?: boolean;
  can_become_holder: boolean;
  today: string;
  lessons: AreaLesson[];
  month_present: number;
  month_total: number;
}

const STATUS_STYLE: Record<AreaLesson["status"], string> = {
  PRESENT: "bg-emerald-500 text-white",
  ABSENT: "bg-rose-100 text-rose-700",
  MISSED: "bg-ink-100 text-ink-500",
  TODAY: "bg-accent-400 text-ink-900 ring-2 ring-accent-500",
  UPCOMING: "bg-white text-ink-600 ring-1 ring-ink-200",
};

/** L'area dell'atleta (docs/club-portal.md, "Il conto dell'atleta"): la vede
 *  l'atleta con il suo accesso (nome utente, email o QR) e il titolare del
 *  conto per ognuno dei suoi atleti. Lezioni del mese, presenza di oggi,
 *  cintura e traguardi, quote in lettura; la formazione arriverà qui. */
type AreaSection = "home" | "lessons" | "fees" | "certificate" | "competitions" | "board" | "games" | "achievements" | "invite";

const AREA_NAV: { key: AreaSection; icon: string; label: MessageKey }[] = [
  { key: "home", icon: "🏠", label: "area.nav.home" },
  { key: "lessons", icon: "🗓️", label: "area.nav.lessons" },
  { key: "competitions", icon: "🏆", label: "area.nav.competitions" },
  { key: "board", icon: "📰", label: "area.nav.board" },
  { key: "fees", icon: "💶", label: "area.nav.fees" },
  { key: "certificate", icon: "🩺", label: "area.nav.certificate" },
  { key: "achievements", icon: "🏅", label: "area.nav.achievements" },
  { key: "games", icon: "🎮", label: "area.nav.games" },
  { key: "invite", icon: "🤝", label: "area.nav.invite" },
];

/** L'area dell'atleta (docs/club-portal.md, "Il conto dell'atleta"): la vede
 *  l'atleta con il suo accesso (nome utente, email o QR) e il titolare del
 *  conto per ognuno dei suoi atleti. Con il menu a sinistra, come le altre
 *  aree: in home la scheda, oggi e le scorciatoie; lezioni, gare, bacheca,
 *  quote, certificato, traguardi, giochi e inviti nelle loro sezioni. */
export function AthleteAreaPage({ initialId }: { initialId: string | null }) {
  const { t } = useI18n();
  const { data: list, isLoading } = useQuery({ queryKey: ["club", "athlete-area"], queryFn: () => clubGet<AreaRef[]>("/athlete-area") });
  const [picked, setPicked] = useState<string | null>(initialId);
  const [section, setSection] = useState<AreaSection>("home");
  // Tornando dalla pagina di un evento aperta dal calendario: di nuovo su
  // «Gare e stage» (lib/events-return.ts). Durante il render, una volta.
  const back = useEventsReturn();
  const [backSeen, setBackSeen] = useState(false);
  if (!backSeen && back?.url.startsWith("/atleta")) {
    setBackSeen(true);
    setSection("competitions");
  }
  const current = list?.find((a) => a.id === picked) ?? list?.[0];
  const navItems: NavItem[] = AREA_NAV.map((n) => ({ key: n.key, label: t(n.label), icon: <span className="text-base leading-none" aria-hidden="true">{n.icon}</span> }));

  return (
    <AppShell
      roleLabel={t("area.roleLabel")}
      navItems={navItems}
      activeKey={section}
      onNavigate={(k) => setSection(k as AreaSection)}
      headerActions={list && list.length > 1 ? (
        <div className="flex gap-1 overflow-x-auto rounded-2xl bg-ink-50 p-1">
          {list.map((a) => (
            <button key={a.id} type="button" onClick={() => setPicked(a.id)}
              className={cn("shrink-0 rounded-xl px-3 py-1.5 text-sm font-semibold transition", current?.id === a.id ? "bg-white text-brand-700 shadow-soft" : "text-ink-600 hover:text-ink-900")}>
              {a.is_own ? t("athleteArea.me") : a.name.split(" ")[0]}
            </button>
          ))}
        </div>
      ) : undefined}
    >
      {isLoading ? <Skeleton className="h-96" /> : current ? <Area key={current.id} id={current.id} section={section} onGo={setSection} /> : (
        <div className="rounded-3xl bg-white p-8 text-center shadow-soft">{t("athleteArea.none")}</div>
      )}
    </AppShell>
  );
}

function Area({ id, section, onGo }: { id: string; section: AreaSection; onGo: (s: AreaSection) => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = ["club", "athlete-area", id];
  const { data: a, isLoading } = useQuery({ queryKey: key, queryFn: () => clubGet<AthleteArea>(`/athlete-area/${id}`) });
  const [busy, setBusy] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);

  if (isLoading || !a) return <Skeleton className="h-96" />;
  const today = a.lessons.filter((l) => l.date === a.today);
  const dueFees = a.fees.filter((f) => f.status === "DUE");

  async function mark(lesson: AreaLesson, present: boolean) {
    setBusy(lesson.course_id);
    try {
      if (present) await clubSend(`/athlete-area/${id}/attendance`, "POST", { course_id: lesson.course_id });
      else await clubSend(`/athlete-area/${id}/attendance/${lesson.course_id}`, "DELETE");
      await queryClient.invalidateQueries({ queryKey: key });
      if (present) toast({ tone: "success", title: t("athleteArea.markedTitle"), text: t("athleteArea.markedText") });
    } catch (e) {
      toast({ tone: "error", title: t("athleteArea.markFailed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  const minorSelf = a.viewer_is_athlete && a.is_minor;
  const goCert = () => onGo("certificate");
  const goFees = () => onGo("fees");

  return (
    <div className="space-y-6">
      {section === "home" && (
        <>
          {/* --- Il judoca: la scheda «salute sportiva» con gli obblighi --- */}
          <AthleteHealthCard athlete={a} mode="area" onAction={(code) => {
            if (code === "CERTIFICATE") goCert();
            if (code === "ANNUAL_FEE") goFees();
          }} />
          <AthleteMoneyCard athleteId={a.id} />
          <div className="rounded-2xl bg-white px-4 py-3 shadow-soft ring-1 ring-ink-900/5">
            <div className="mb-1.5 flex justify-between text-[11px] font-semibold text-ink-500">
              <span>{a.xp} XP</span><span>{t("athlete.nextLevelAt", { n: a.level + 1, xp: a.next_level_xp })}</span>
            </div>
            <ProgressBar value={a.xp - a.level_xp_floor} max={Math.max(1, a.next_level_xp - a.level_xp_floor)} tone="accent" />
          </div>
          {a.can_become_holder && <BecomeHolder id={id} />}
          {/* --- Oggi --- */}
          <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
            <h2 className="text-xl text-ink-900">{t("athleteArea.todayTitle")}</h2>
            {today.length === 0 ? (
              <p className="mt-2 text-sm text-ink-500">{t("athleteArea.noToday")}</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {today.map((l) => (
                  <li key={l.course_id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-ink-50 p-4">
                    <div>
                      <p className="font-display text-2xl text-ink-900">{l.starts_at.slice(0, 5)}<span className="text-base text-ink-500">–{l.ends_at.slice(0, 5)}</span></p>
                      <p className="text-sm text-ink-600">{l.course_name}</p>
                    </div>
                    {l.status === "PRESENT" ? (
                      <div className="flex items-center gap-2">
                        <motion.span initial={{ scale: 0.6 }} animate={{ scale: 1 }} className="rounded-2xl bg-emerald-500 px-4 py-3 font-semibold text-white">✓ {t("athleteArea.present")}</motion.span>
                        <Button variant="ghost" size="sm" disabled={busy !== null} onClick={() => mark(l, false)}>{t("athleteArea.undo")}</Button>
                      </div>
                    ) : (
                      <Button size="lg" loading={busy === l.course_id} onClick={() => mark(l, true)} className="animate-pulse-ring">
                        🥋 {t("athleteArea.imHere")}
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <ul className="grid gap-3 sm:grid-cols-3">
            {([["competitions", "🏆", t("area.nav.competitions")], ["board", "📰", t("area.nav.board")], ["games", "🎮", t("area.nav.games")]] as const).map(([key, icon, label]) => (
              <li key={key}>
                <button type="button" onClick={() => onGo(key)} className="flex w-full cursor-pointer items-center gap-3 rounded-2xl bg-white p-4 text-left shadow-soft ring-1 ring-ink-900/5 transition hover:-translate-y-0.5">
                  <span className="text-2xl" aria-hidden="true">{icon}</span><span className="font-semibold text-ink-900">{label}</span><span className="ml-auto text-ink-400">→</span>
                </button>
              </li>
            ))}
          </ul>

          {/* --- Segna la tua presenza: porta alle lezioni --- */}
          <motion.button type="button" onClick={() => onGo("lessons")} whileHover={{ y: -3 }} whileTap={{ scale: 0.98 }}
            className="relative flex w-full cursor-pointer items-center gap-4 overflow-hidden rounded-[2rem] bg-gradient-to-br from-brand-500 via-brand-600 to-ink-900 p-6 text-left text-white shadow-lift">
            <span aria-hidden="true" className="pointer-events-none absolute -right-4 -top-6 select-none font-display text-[8rem] leading-none text-white/10">柔</span>
            <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-white/15 text-4xl ring-1 ring-white/25 animate-pulse-ring" aria-hidden="true">🥋</span>
            <span className="relative min-w-0 flex-1">
              <span className="block font-display text-2xl leading-tight sm:text-3xl">{t("athleteArea.markCta")}</span>
              <span className="mt-1 block text-sm text-white/85">{t("athleteArea.markCtaText")}</span>
            </span>
            <span className="relative hidden rounded-2xl bg-accent-400 px-4 py-3 font-bold text-ink-900 shadow sm:block">{t("athleteArea.markCtaButton")} →</span>
          </motion.button>

          {/* --- Invita un amico, come nella sua pagina --- */}
          <InviteCard withNetwork={false} />
        </>
      )}

      {section === "lessons" && (
        <>
      {/* --- Oggi --- */}
      <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
        <h2 className="text-xl text-ink-900">{t("athleteArea.todayTitle")}</h2>
        {today.length === 0 ? (
          <p className="mt-2 text-sm text-ink-500">{t("athleteArea.noToday")}</p>
        ) : (
          <ul className="mt-4 space-y-3">
            {today.map((l) => (
              <li key={l.course_id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-ink-50 p-4">
                <div>
                  <p className="font-display text-2xl text-ink-900">{l.starts_at.slice(0, 5)}<span className="text-base text-ink-500">–{l.ends_at.slice(0, 5)}</span></p>
                  <p className="text-sm text-ink-600">{l.course_name}</p>
                </div>
                {l.status === "PRESENT" ? (
                  <div className="flex items-center gap-2">
                    <motion.span initial={{ scale: 0.6 }} animate={{ scale: 1 }} className="rounded-2xl bg-emerald-500 px-4 py-3 font-semibold text-white">✓ {t("athleteArea.present")}</motion.span>
                    <Button variant="ghost" size="sm" disabled={busy !== null} onClick={() => mark(l, false)}>{t("athleteArea.undo")}</Button>
                  </div>
                ) : (
                  <Button size="lg" loading={busy === l.course_id} onClick={() => mark(l, true)} className="animate-pulse-ring">
                    🥋 {t("athleteArea.imHere")}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* --- Il mese --- */}
      <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-xl text-ink-900">{t("athleteArea.monthTitle")}</h2>
          <p className="text-sm text-ink-500">{t("athleteArea.monthSummary", { present: a.month_present, total: a.month_total })}</p>
        </div>
        {a.lessons.length === 0 ? (
          <p className="mt-2 text-sm text-ink-500">{t("athleteArea.noLessons")}</p>
        ) : (
          <>
            <ul className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-7">
              {a.lessons.map((l) => (
                <li key={`${l.date}-${l.course_id}`} className={cn("rounded-2xl p-2.5 text-center", STATUS_STYLE[l.status])} title={l.course_name}>
                  <p className="text-[11px] font-semibold uppercase opacity-80">{fmt.date(new Date(`${l.date}T12:00:00`), { weekday: "short" })}</p>
                  <p className="font-display text-2xl leading-tight">{Number(l.date.slice(8, 10))}</p>
                  <p className="text-[11px] opacity-80">{l.starts_at.slice(0, 5)}</p>
                </li>
              ))}
            </ul>
            <ul className="mt-4 flex flex-wrap gap-3 text-xs text-ink-600">
              {(["PRESENT", "MISSED", "TODAY", "UPCOMING"] as const).map((s) => (
                <li key={s} className="flex items-center gap-1.5"><span className={cn("h-3 w-3 rounded", STATUS_STYLE[s])} />{t.dyn(`athleteArea.status.${s}`, s)}</li>
              ))}
            </ul>
          </>
        )}
      </section>

        </>
      )}

      {section === "competitions" && <AreaCompetitionsSection athlete={a} />}

      {section === "board" && (
        <section className="rounded-3xl bg-ink-50/60 p-5 ring-1 ring-ink-900/5 sm:p-6">
          <h2 className="mb-4 text-xl text-ink-900">📰 {t("board.title")}</h2>
          <ClubBoard compact />
        </section>
      )}

      {section === "certificate" && (
        <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
          <h2 className="mb-4 text-xl text-ink-900">🩺 {t("athleteArea.certificateTitle")}</h2>
          {minorSelf ? (
            <div className="space-y-3">
              <div className={cn("rounded-2xl p-4 text-sm font-semibold ring-1", a.certificate.status === "VALID" ? "bg-emerald-50 text-emerald-800 ring-emerald-200" : "bg-amber-50 text-amber-900 ring-amber-200")}>
                {t.dyn(`health.cert.${a.certificate.status}`, a.certificate.status)}
                {a.certificate.expires_on ? ` · ${t("club.dueOnCap", { date: fmt.shortDate(a.certificate.expires_on) })}` : ""}
              </div>
              <p className="rounded-2xl bg-sky-50 p-4 text-sm text-sky-900 ring-1 ring-sky-200">👨‍👩‍👧 {t("area.certMinor")}</p>
            </div>
          ) : (
            <CertificatesTab
              athlete={a}
              uploadPath={`/athlete-area/${id}/certificates`}
              urlPath={(certificateId) => `/athlete-area/${id}/certificates/${certificateId}/url`}
            />
          )}
        </section>
      )}

      {section === "fees" && (
        <>
        {/* --- Le quote, in lettura --- */}
        <section id="area-fees" className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
          <h2 className="text-xl text-ink-900">{t("athleteArea.feesTitle")}</h2>
          <p className="mt-1 text-sm text-ink-500">
            {a.can_manage ? t("athleteArea.feesManage") : a.can_pay ? t("proof.adultText") : t("athleteArea.feesReadOnly")}
          </p>
          {dueFees.length === 0 ? (
            <p className="mt-4 rounded-2xl bg-emerald-50 p-4 text-sm font-semibold text-emerald-700">✓ {t("athleteArea.allPaid")}</p>
          ) : (
            <ul className="mt-4 space-y-2">
              {dueFees.slice(0, 6).map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-3 rounded-2xl bg-ink-50 px-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-ink-900">{feeLabel(f, t, fmt)}</p>
                    <p className="text-xs text-ink-500">{t("club.dueOnCap", { date: fmt.shortDate(f.due_date) })}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-display text-ink-900">{fmt.euro(f.amount_cents)}</p>
                    <FeeStatusPill status={f.status} overdue={f.overdue} />
                  </div>
                </li>
              ))}
            </ul>
          )}
          {a.can_pay && dueFees.length > 0 && (
            <button type="button" onClick={() => setPaying(true)}
              className="mt-4 flex w-full cursor-pointer items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-brand-500 to-brand-700 px-5 py-4 text-base font-bold text-white shadow-brand transition hover:brightness-110">
              📸 {t("proof.payButton")}
            </button>
          )}
          {a.can_manage && <a href="/customer" className="mt-3 inline-flex text-sm font-semibold text-brand-700 hover:underline">{t("athleteArea.goPay")} →</a>}
          {paying && <AthletePayModal athleteId={a.id} fees={dueFees} onClose={() => setPaying(false)} />}
        </section>

          <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
            <SeasonMonthsPanel athleteId={a.id} mode="area" />
          </section>
        </>
      )}

      {section === "achievements" && (
        <>
        {/* --- Traguardi --- */}
        <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
          <h2 className="text-xl text-ink-900">{t("athlete.achievements")}</h2>
          <div className="mt-4 flex flex-wrap gap-3">
            {a.achievements.map((ach) => (
              <AchievementBadge key={ach.code} icon={ACHIEVEMENT_ICONS[ach.code] ?? "⭐"} label={t.dyn(`achievement.${ach.code}`, ach.label)}
                unlocked={ach.earned} hint={`${t.dyn(`achievement.${ach.code}.desc`, ach.description)} (${Math.min(ach.current, ach.target)}/${ach.target})`} />
            ))}
          </div>
        </section>
      {/* --- La formazione: il posto è pronto --- */}
      <section className="overflow-hidden rounded-3xl bg-ink-950 p-6 text-white shadow-lift sm:p-8">
        <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-300">{t("athleteArea.learnEyebrow")}</p>
        <h2 className="mt-1 text-2xl">{t("athleteArea.learnTitle")}</h2>
        <ul className="mt-5 grid gap-3 sm:grid-cols-3">
          {(["techniques", "rules", "games"] as const).map((k, i) => (
            <li key={k} className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/10">
              <p className="text-3xl" aria-hidden="true">{["🥋", "📜", "🎮"][i]}</p>
              <p className="mt-2 font-semibold">{t.dyn(`athleteArea.learn.${k}`, k)}</p>
              <p className="text-xs text-white/60">{t("athleteArea.soon")}</p>
            </li>
          ))}
        </ul>
      </section>
        </>
      )}

      {section === "games" && <GamesHub />}

      {section === "invite" && <InviteCard />}
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-2xl bg-white/15 px-2 py-2 text-center backdrop-blur">
      <p className="font-display text-xl leading-tight">{value}</p>
      <p className="text-[10px] uppercase tracking-wider text-white/80">{label}</p>
    </div>
  );
}

/** A 18 anni: "diventa titolare del tuo conto". Serve la sua email. */
function BecomeHolder({ id }: { id: string }) {
  const { t } = useI18n();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <section className="rounded-3xl bg-gradient-to-br from-accent-100 to-white p-5 ring-1 ring-accent-300 sm:p-6">
      <h2 className="text-xl text-ink-900">🎉 {t("athleteArea.holderTitle")}</h2>
      <p className="mt-1 max-w-2xl text-sm text-ink-700">{t("athleteArea.holderText")}</p>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <Field label={t("athleteArea.holderEmail")} htmlFor="holder-email">
            <Input id="holder-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
        </div>
        <Button loading={busy} onClick={async () => {
          setBusy(true);
          try {
            await clubSend(`/athlete-area/${id}/become-holder`, "POST", { email: email || null });
            // I ruoli sono cambiati: un login nuovo li porta nella sessione.
            toast({ tone: "success", title: t("athleteArea.holderDone") });
            await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
            window.location.assign("/login");
          } catch (e) {
            toast({ tone: "error", title: t("athleteArea.markFailed"), text: (e as Error).message });
          } finally {
            setBusy(false);
          }
        }}>{t("athleteArea.holderButton")}</Button>
      </div>
    </section>
  );
}

/** Gare e stage: il calendario degli eventi (come sul sito) e le prove a cui
 *  dire «Voglio partecipare». */
function AreaCompetitionsSection({ athlete }: { athlete: AthleteDetail }) {
  const { t } = useI18n();
  const [tab, setTab] = useState("events");
  return (
    <div className="space-y-5">
      <Tabs value={tab} onChange={setTab} items={[
        { key: "events", label: `🗓️ ${t("comp.eventsTab")}` },
        { key: "wish", label: `🙋 ${t("area.wishTab")}` },
      ]} />
      {tab === "events" ? <AreaEvents returnHref={`/atleta?a=${athlete.id}`} /> : <AreaCompetitions athlete={athlete} />}
    </div>
  );
}
