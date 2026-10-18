"use client";

import { motion } from "motion/react";
import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge, type Tone } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ClockCard } from "@/components/club/coach-tools";
import { EventNameButton } from "@/components/club/competition-detail-modal";
import { useClubFeatures } from "@/components/club/jav-courses";
import { AthleteSheetModal, CERT_TONE, LessonNoteModal } from "@/components/club/coach-notebook";
import { ClubLogo, CoachAvatar, greetingKey, type MyClubs, type StaffClubOption } from "@/components/club/staff-clubs";
import { clubGet, type Lesson } from "@/lib/club";
import { COACH, type AthleteBrief, type CoachHome as Home } from "@/lib/coach";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// L'Início del treinador (apps/api/app/domains/club/coach.py::home): quello
// che serve ogni giorno, in una schermata da telefono. Le lezioni di oggi con
// «Marcar presenças» in grande, i registri rimasti vuoti, il cartellino, le
// prove in arrivo, i messaggi, gli atleti a cui fare attenzione, il quaderno.

const hhmm = (v: string) => v.slice(0, 5);

export interface CoachHomeProps {
  /** Apre una sezione; per le presenze, il giorno e il corso. */
  onNavigate: (tab: string, attendance?: { date: string; courseId: string }) => void;
  /** Il treinador (nome e foto per il saluto) e il club scelto entrando. */
  me?: MyClubs["me"];
  club?: StaffClubOption;
}

function Card({ title, icon, action, className, children }: { title: ReactNode; icon: string; action?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className={cn("rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5", className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-base text-ink-900"><span aria-hidden="true">{icon}</span>{title}</h3>
        {action}
      </div>
      {children}
    </motion.section>
  );
}

export function CoachHome({ onNavigate, me, club }: CoachHomeProps) {
  const { t, fmt } = useI18n();
  const { data, isLoading } = useQuery({
    queryKey: ["club", "staff", "coach-home"],
    queryFn: () => clubGet<Home>(COACH("/home")),
    refetchInterval: 120_000,
  });
  const features = useClubFeatures();
  const [sheet, setSheet] = useState<string | null>(null);
  const [noteFor, setNoteFor] = useState<Lesson | "free" | null>(null);
  if (isLoading || !data) return <div className="grid gap-4 lg:grid-cols-2"><Skeleton className="h-56" /><Skeleton className="h-56" /><Skeleton className="h-40" /><Skeleton className="h-40" /></div>;

  const firstName = me ? me.first_name || me.name.split(" ")[0] : "";
  const greeting = `${t(greetingKey(new Date().getHours()))}${firstName ? `, ${firstName}` : ""}`;
  const current = data.lessons_today.find((l) => l.current) ?? data.lessons_today[0];
  const unread = data.unread_club + data.unread_jav;
  const open = (l: Lesson) => onNavigate("attendance", { date: l.date, courseId: l.course_id });

  return (
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-ink-950 via-brand-800 to-brand-600 p-6 text-white shadow-lift">
        <motion.div aria-hidden="true" className="pointer-events-none absolute -right-12 -top-20 h-64 w-64 rounded-full bg-accent-400/25 blur-3xl"
          animate={{ scale: [1, 1.12, 1] }} transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }} />
        {/* Il saluto a sinistra, la foto del treinador a destra (si cambia toccandola). */}
        <div className="relative flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-white/75">
              {fmt.date(new Date(`${data.today}T12:00:00`), { weekday: "long", day: "numeric", month: "long" })}
            </p>
            <h2 className="mt-1 text-3xl" suppressHydrationWarning>{greeting} 👋</h2>
            {club && (
              <p className="mt-2 inline-flex max-w-full items-center gap-2 rounded-full bg-white/15 py-1 pl-1 pr-3 text-sm font-semibold backdrop-blur">
                <ClubLogo club={club} className="h-7 w-7 p-0.5 text-[10px]" />
                <span className="truncate">{t("staffClubs.youAreInClub", { club: club.name })}</span>
              </p>
            )}
          </div>
          {me && <CoachAvatar me={me} size="md" className="sm:h-20 sm:w-20" />}
        </div>
        <div className="relative mt-4 flex flex-wrap gap-2 text-sm">
          <span className="rounded-full bg-white/15 px-3 py-1 backdrop-blur">🗓️ {t("coach2.home.lessonsToday", { n: data.lessons_today.length })}</span>
          <span className="rounded-full bg-white/15 px-3 py-1 backdrop-blur">🥋 {t("coach2.home.athletes", { n: data.athletes })}</span>
          <span className="rounded-full bg-white/15 px-3 py-1 backdrop-blur">📚 {t("coach2.home.courses", { n: data.courses })}</span>
          {unread > 0 && (
            <button type="button" onClick={() => onNavigate("messages")} className="cursor-pointer rounded-full bg-rose-500 px-3 py-1 font-semibold">
              💬 {t("coach2.home.unread", { n: unread })}
            </button>
          )}
        </div>
        {current && (
          <motion.button type="button" whileTap={{ scale: 0.97 }} onClick={() => open(current)}
            className="relative mt-5 flex w-full cursor-pointer items-center gap-4 rounded-3xl bg-white p-4 text-left text-ink-900 shadow-lg sm:max-w-md">
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-emerald-500 text-2xl text-white shadow">✓</span>
            <span className="min-w-0 flex-1">
              <span className="block font-display text-xl leading-tight">{t("coach2.home.markAttendance")}</span>
              <span className="block truncate text-sm text-ink-500">
                {current.course_name} · {hhmm(current.starts_at)}–{hhmm(current.ends_at)} · {current.present}/{current.enrolled}
              </span>
            </span>
            <span className="text-2xl text-brand-600" aria-hidden="true">›</span>
          </motion.button>
        )}
      </section>

      {data.missing_count > 0 && (
        <Card icon="⚠️" title={t("coach2.home.missingTitle", { n: data.missing_count })} className="bg-amber-50 ring-amber-200">
          <p className="-mt-1 mb-3 text-sm text-amber-900">{t("coach2.home.missingText")}</p>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {data.missing_registers.map((l) => (
              <button key={`${l.course_id}-${l.slot_id}-${l.date}`} type="button" onClick={() => open(l)}
                className="shrink-0 cursor-pointer rounded-2xl bg-white px-3 py-2 text-left ring-1 ring-amber-200 hover:ring-amber-400">
                <span className="block text-xs font-bold uppercase text-amber-700">{fmt.date(new Date(`${l.date}T12:00:00`), { weekday: "short", day: "numeric", month: "short" })}</span>
                <span className="block text-sm font-semibold text-ink-900">{l.course_name}</span>
                <span className="block text-xs text-ink-500">{hhmm(l.starts_at)} · {t("coach2.home.enrolled", { n: l.enrolled })}</span>
              </button>
            ))}
          </div>
        </Card>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <Card icon="🗓️" title={t("coach2.home.today")} action={<Button size="sm" variant="ghost" onClick={() => onNavigate("calendar")}>{t("coach2.home.week")} ›</Button>}>
            {data.lessons_today.length === 0 ? <p className="text-sm text-ink-500">{t("coach2.home.noLessons")}</p> : (
              <ul className="space-y-2">
                {data.lessons_today.map((l) => {
                  const done = l.present > 0;
                  return (
                    <li key={`${l.course_id}-${l.slot_id}`} className={cn("flex items-center gap-3 rounded-2xl p-3 ring-1", l.current ? "bg-brand-50 ring-brand-200" : "bg-ink-50/60 ring-ink-100")}>
                      <span className="w-14 shrink-0 text-center">
                        <span className="block font-display text-lg leading-none text-ink-900">{hhmm(l.starts_at)}</span>
                        <span className="text-[11px] text-ink-500">{hhmm(l.ends_at)}</span>
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-semibold text-ink-900">{l.course_name}</span>
                        <span className="text-xs text-ink-500">{l.room ? `${l.room} · ` : ""}👥 {l.present}/{l.enrolled}{l.current ? ` · ${t("attendance.now")}` : ""}</span>
                      </span>
                      <Button size="sm" variant={done ? "secondary" : "primary"} onClick={() => open(l)}>{done ? "✓" : t("coach2.home.mark")}</Button>
                      <Button size="sm" variant="ghost" onClick={() => setNoteFor(l)} aria-label={t("coach2.att.lessonNote")}>📓</Button>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <Card icon="🏆" title={t("coach2.home.events")} action={<Button size="sm" variant="ghost" onClick={() => onNavigate("calendar")}>{t("coach2.home.all")} ›</Button>}>
            {data.events.length === 0 ? <p className="text-sm text-ink-500">{t("coach2.home.noEvents")}</p> : (
              <ul className="divide-y divide-ink-100">
                {data.events.map((e) => {
                  const d = new Date(`${e.starts_on}T12:00:00`);
                  return (
                    <li key={e.id} className="flex items-center gap-3 py-2.5">
                      <span className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow">
                        <span className="font-display text-lg leading-none">{d.getDate()}</span>
                        <span className="text-[10px] font-bold uppercase">{fmt.date(d, { month: "short" })}</span>
                      </span>
                      <span className="min-w-0 flex-1">
                        <EventNameButton id={e.id} name={e.name} mode="staff" className="block max-w-full truncate text-sm font-semibold text-ink-900" />
                        <span className="block truncate text-xs text-ink-500">📍 {e.location ?? "—"}{e.network ? ` · ${t("jcal.network")}` : e.club_name ? ` · ${e.club_name}` : ""}</span>
                      </span>
                      {e.status === "OPEN" && <Badge tone="success">{t("coach2.home.until", { date: fmt.shortDate(e.registration_deadline) })}</Badge>}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <Card icon="📓" title={t("coach2.home.notebook")} action={<Button size="sm" variant="ghost" onClick={() => onNavigate("notebook")}>{t("coach2.home.all")} ›</Button>}>
            {data.recent_notes.length === 0 ? <p className="text-sm text-ink-500">{t("coach2.home.noNotes")}</p> : (
              <ul className="space-y-2">
                {data.recent_notes.map((n) => (
                  <li key={n.id} className="rounded-2xl bg-ink-50/70 p-3">
                    <p className="text-xs text-ink-500">{fmt.shortDate(n.lesson_date)} · {n.course_name}</p>
                    <p className="text-sm font-semibold text-ink-900">{n.title || n.techniques.join(", ")}</p>
                    {n.body && <p className="line-clamp-2 text-xs text-ink-600">{n.body}</p>}
                  </li>
                ))}
              </ul>
            )}
            <Button className="mt-3" size="sm" variant="secondary" onClick={() => setNoteFor(current ?? "free")}>✍️ {t("coach2.home.writeNote")}</Button>
          </Card>
        </div>

        <div className="space-y-5">
          <ClockCard compact />
          <Card icon="👀" title={t("coach2.home.attention")}>
            {data.absent_count === 0 && data.certificates_count === 0 ? <p className="text-sm text-ink-500">✨ {t("coach2.home.allGood")}</p> : (
              <div className="space-y-4">
                {data.absent_count > 0 && (
                  <AthleteGroup title={t("coach2.home.absent", { n: data.absent_count })} rows={data.absent} onOpen={setSheet}
                    detail={(a) => a.last_present ? t("coach2.home.lastSeen", { date: fmt.shortDate(a.last_present) }) : ""} />
                )}
                {data.certificates_count > 0 && (
                  <AthleteGroup title={t("coach2.home.certificates", { n: data.certificates_count })} rows={data.certificates} onOpen={setSheet}
                    detail={(a) => t.dyn(`athTable.cert.${a.certificate_status}`, a.certificate_status)} tone={(a) => CERT_TONE[a.certificate_status]} />
                )}
              </div>
            )}
            <Button className="mt-3" size="sm" variant="ghost" onClick={() => onNavigate("athletes")}>🥋 {t("coach2.home.myAthletes")} ›</Button>
          </Card>
          <Card icon="⚡" title={t("coach2.home.quick")}>
            <div className="grid grid-cols-3 gap-2">
              {([
                ["calendar", "🗓️", t("coach.navCalendar")], ["events", "🏆", t("evrep.nav")], ["notebook", "📓", t("coach2.nav.notebook")],
                ["board", "📰", t("coach2.nav.board")], ["messages", "💬", t("staffMsg.nav")], ["ranking", "🥇", t("nav.club-ranking")],
              ] as const).filter(([key]) => (key !== "ranking" || features.ranking) && (key !== "events" || features.competitions)).map(([key, icon, label]) => (
                <motion.button key={key} type="button" whileTap={{ scale: 0.95 }} onClick={() => onNavigate(key)}
                  className="flex cursor-pointer flex-col items-center gap-1 rounded-2xl bg-ink-50 px-2 py-3 text-center text-xs font-semibold text-ink-700 ring-1 ring-ink-100 hover:ring-brand-300">
                  <span className="text-2xl" aria-hidden="true">{icon}</span>{label}
                </motion.button>
              ))}
            </div>
          </Card>
        </div>
      </div>
      {sheet && <AthleteSheetModal athleteId={sheet} onClose={() => setSheet(null)} />}
      {noteFor && <LessonNoteModal note={null} defaultCourse={noteFor === "free" ? undefined : noteFor.course_id}
        defaultDate={noteFor === "free" ? undefined : noteFor.date} onClose={() => setNoteFor(null)} />}
    </div>
  );
}

function AthleteGroup({ title, rows, onOpen, detail, tone }: {
  title: string; rows: AthleteBrief[]; onOpen: (id: string) => void; detail: (a: AthleteBrief) => string;
  tone?: (a: AthleteBrief) => Tone;
}) {
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-500">{title}</p>
      <ul className="space-y-1">
        {rows.map((a) => (
          <li key={a.id}>
            <button type="button" onClick={() => onOpen(a.id)} className="flex w-full cursor-pointer items-center gap-2 rounded-xl px-2 py-1.5 text-left hover:bg-ink-50">
              <BeltBadge belt={a.belt} size="sm" showLabel={false} />
              <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink-900">{a.first_name} {a.last_name}</span>
              {tone ? <Badge tone={tone(a)}>{detail(a)}</Badge> : <span className="text-xs text-ink-500">{detail(a)}</span>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
