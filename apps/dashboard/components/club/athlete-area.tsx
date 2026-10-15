"use client";

import Image from "next/image";
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
import { SeasonMonthsPanel } from "@/components/club/season-months";
import { ACHIEVEMENT_ICONS, clubGet, clubSend, type AthleteDetail } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

interface AreaRef { id: string; name: string; photo_url: string | null; is_own: boolean }
interface AreaLesson { date: string; course_id: string; course_name: string; starts_at: string; ends_at: string; status: "PRESENT" | "ABSENT" | "MISSED" | "TODAY" | "UPCOMING" }
interface AthleteArea extends AthleteDetail {
  is_minor: boolean;
  viewer_is_athlete: boolean;
  can_manage: boolean;
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
export function AthleteAreaPage({ initialId }: { initialId: string | null }) {
  const { t } = useI18n();
  const { data: list, isLoading } = useQuery({ queryKey: ["club", "athlete-area"], queryFn: () => clubGet<AreaRef[]>("/athlete-area") });
  const [picked, setPicked] = useState<string | null>(initialId);
  const current = list?.find((a) => a.id === picked) ?? list?.[0];

  return (
    <div className="min-h-screen bg-gradient-to-b from-brand-50/60 via-white to-white">
      <header className="sticky top-0 z-30 border-b border-ink-900/5 bg-white/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
          <a href="/area" className="shrink-0"><Image src="/judoartevida-logo.jpg" alt="Judo Arte e Vida" width={110} height={48} className="h-9 w-auto" /></a>
          <div className="ml-auto flex items-center gap-2">
            {list && list.length > 1 && (
              <div className="flex gap-1 overflow-x-auto rounded-2xl bg-ink-50 p-1">
                {list.map((a) => (
                  <button key={a.id} type="button" onClick={() => setPicked(a.id)}
                    className={cn("shrink-0 rounded-xl px-3 py-1.5 text-sm font-semibold transition", current?.id === a.id ? "bg-white text-brand-700 shadow-soft" : "text-ink-600 hover:text-ink-900")}>
                    {a.is_own ? t("athleteArea.me") : a.name.split(" ")[0]}
                  </button>
                ))}
              </div>
            )}
            <button type="button" className="rounded-xl px-3 py-2 text-sm font-semibold text-ink-600 hover:bg-ink-50"
              onClick={async () => { await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined); window.location.assign("/login"); }}>
              {t("athleteArea.logout")}
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:py-10">
        {isLoading ? <Skeleton className="h-96" /> : current ? <Area key={current.id} id={current.id} /> : (
          <div className="rounded-3xl bg-white p-8 text-center shadow-soft">{t("athleteArea.none")}</div>
        )}
      </main>
    </div>
  );
}

function Area({ id }: { id: string }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = ["club", "athlete-area", id];
  const { data: a, isLoading } = useQuery({ queryKey: key, queryFn: () => clubGet<AthleteArea>(`/athlete-area/${id}`) });
  const [busy, setBusy] = useState<string | null>(null);

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

  return (
    <div className="space-y-6">
      {/* --- Il judoca --- */}
      <section className="relative overflow-hidden rounded-[2rem] bg-gradient-to-br from-brand-500 via-brand-600 to-ink-900 p-6 text-white shadow-lift sm:p-8">
        <div className="absolute -bottom-12 -right-4 select-none font-display text-[11rem] leading-none text-white/10" aria-hidden="true">柔</div>
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center">
          <span className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white/20 ring-4 ring-white/80">
            {a.photo_url
              // eslint-disable-next-line @next/next/no-img-element -- foto caricata dalla famiglia
              ? <img src={a.photo_url} alt="" className="h-full w-full object-cover" />
              : <span className="font-display text-4xl">{a.first_name.slice(0, 1)}</span>}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-white/80">{a.viewer_is_athlete ? t("athleteArea.hello") : t("athleteArea.areaOf")}</p>
            <h1 className="text-3xl">{a.first_name} {a.last_name}</h1>
            <p className="mt-1 text-sm text-white/80">{a.plan?.name ?? ""}</p>
            {a.belt && <div className="mt-3 inline-flex rounded-full bg-white/95 px-3 py-1.5"><BeltBadge belt={a.belt} /></div>}
          </div>
          <div className="grid grid-cols-3 gap-2 sm:w-72">
            <Stat value={`${a.month_present}/${a.month_total}`} label={t("athleteArea.monthStat")} />
            <Stat value={String(a.medals.gold + a.medals.silver + a.medals.bronze)} label={t("athleteArea.medals")} />
            <Stat value={String(a.level)} label={t("athlete.levelLabel")} />
          </div>
        </div>
        <div className="relative mt-5">
          <div className="mb-1.5 flex justify-between text-[11px] font-semibold text-white/80">
            <span>{a.xp} XP</span><span>{t("athlete.nextLevelAt", { n: a.level + 1, xp: a.next_level_xp })}</span>
          </div>
          <ProgressBar value={a.xp - a.level_xp_floor} max={Math.max(1, a.next_level_xp - a.level_xp_floor)} tone="accent" />
        </div>
      </section>

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

      <div className="grid gap-6 lg:grid-cols-2">
        {/* --- Le quote, in lettura --- */}
        <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
          <h2 className="text-xl text-ink-900">{t("athleteArea.feesTitle")}</h2>
          <p className="mt-1 text-sm text-ink-500">
            {a.can_manage ? t("athleteArea.feesManage") : t("athleteArea.feesReadOnly")}
          </p>
          {dueFees.length === 0 ? (
            <p className="mt-4 rounded-2xl bg-emerald-50 p-4 text-sm font-semibold text-emerald-700">✓ {t("athleteArea.allPaid")}</p>
          ) : (
            <ul className="mt-4 space-y-2">
              {dueFees.slice(0, 6).map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-3 rounded-2xl bg-ink-50 px-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-ink-900">{f.description}</p>
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
          {a.can_manage && <a href="/customer" className="mt-4 inline-flex text-sm font-semibold text-brand-700 hover:underline">{t("athleteArea.goPay")} →</a>}
        </section>

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
      </div>

      {/* --- Le mensilità mese per mese, in lettura (paga il titolare) --- */}
      <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5 sm:p-6">
        <SeasonMonthsPanel athleteId={a.id} mode="area" />
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
