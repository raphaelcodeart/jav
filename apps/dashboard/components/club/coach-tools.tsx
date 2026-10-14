"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend, hoursLabel, type Clock, type Lesson } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

const S = (path: string) => `/staff${path}`;
const hhmm = (t: string) => t.slice(0, 5);

function mondayOf(d: Date): Date {
  const out = new Date(d);
  out.setDate(out.getDate() - ((out.getDay() + 6) % 7));
  return out;
}
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Il calendario delle lezioni a cui il treinador deve esserci: la
 *  settimana, giorno per giorno, con iscritti e presenti. */
export function CalendarPanel() {
  const { t, fmt } = useI18n();
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()));
  const from = iso(weekStart);
  const to = iso(new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate() + 6));
  const { data, isLoading } = useQuery({
    queryKey: ["club", "staff", "lessons", from, to],
    queryFn: () => clubGet<Lesson[]>(S(`/lessons?from=${from}&to=${to}`)),
  });
  const shift = (days: number) => setWeekStart((w) => new Date(w.getFullYear(), w.getMonth(), w.getDate() + days));
  const days = Array.from({ length: 7 }, (_, i) => iso(new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate() + i)));
  const today = iso(new Date());
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button size="sm" variant="secondary" onClick={() => shift(-7)} aria-label={t("calendar.prev")}>‹</Button>
        <Button size="sm" variant="ghost" onClick={() => setWeekStart(mondayOf(new Date()))}>{t("calendar.thisWeek")}</Button>
        <Button size="sm" variant="secondary" onClick={() => shift(7)} aria-label={t("calendar.next")}>›</Button>
        <span className="ml-2 text-sm text-ink-500">{fmt.shortDate(from)} – {fmt.shortDate(to)}</span>
      </div>
      {isLoading ? <Skeleton className="h-64" /> : !data?.length ? (
        <EmptyState icon={<span className="text-3xl">📅</span>} title={t("calendar.empty")} text={t("attendance.noLessonsText")} />
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-7 gap-3">
          {days.map((d) => {
            const items = data.filter((l) => l.date === d);
            return (
              <div key={d} className={`rounded-3xl p-3 ring-1 ${d === today ? "bg-brand-50 ring-brand-300" : "bg-white ring-ink-200"}`}>
                <p className="text-xs font-bold uppercase tracking-wide text-ink-500 mb-2">
                  {new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric" })}
                </p>
                {items.length === 0 ? <p className="text-xs text-ink-300">—</p> : items.map((l) => (
                  <div key={`${l.course_id}-${l.slot_id}`} className="rounded-2xl bg-ink-50 p-2.5 mb-2">
                    <p className="text-sm font-semibold text-ink-900 leading-tight">{l.course_name}</p>
                    <p className="text-xs text-ink-500">{hhmm(l.starts_at)}–{hhmm(l.ends_at)}{l.room ? ` · ${l.room}` : ""}</p>
                    <p className="text-xs text-ink-500">👥 {l.present}/{l.enrolled}</p>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Il cartellino: un pulsante grande, "Entro" o "Esco", e le ore di oggi e
 *  del mese. */
export function ClockPanel() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["club", "staff", "clock"], queryFn: () => clubGet<Clock>(S("/clock")) });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  if (isLoading || !data) return <Skeleton className="h-64" />;
  const open = data.open_session;

  async function punch() {
    setBusy(true);
    try {
      const next = await clubSend<Clock>(S(open ? "/clock/out" : "/clock/in"), "POST", { note: note || null });
      queryClient.setQueryData(["club", "staff", "clock"], next);
      setNote("");
      toast({ tone: "success", title: open ? t("clock.outDone") : t("clock.inDone") });
    } catch (e) {
      toast({ tone: "error", title: t("clock.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid lg:grid-cols-[1fr_1.2fr] gap-6">
      <div className="glass-card rounded-3xl p-6 space-y-4 text-center">
        <p className="text-sm text-ink-500">
          {open ? t("clock.since", { time: new Date(open.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }) : t("clock.notIn")}
        </p>
        <motion.button type="button" whileTap={{ scale: 0.95 }} onClick={punch} disabled={busy}
          className={`mx-auto flex h-40 w-40 items-center justify-center rounded-full text-white font-display text-2xl shadow-brand cursor-pointer disabled:opacity-60 ${open ? "bg-gradient-to-br from-rose-500 to-rose-600" : "bg-gradient-to-br from-emerald-500 to-emerald-600"}`}>
          {open ? t("clock.out") : t("clock.in")}
        </motion.button>
        <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} placeholder={t("clock.notePlaceholder")} />
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-2xl bg-ink-50 p-3"><p className="text-xs text-ink-500">{t("clock.today")}</p><p className="font-display text-xl">{hoursLabel(data.today_minutes)}</p></div>
          <div className="rounded-2xl bg-ink-50 p-3"><p className="text-xs text-ink-500">{t("clock.month")}</p><p className="font-display text-xl">{hoursLabel(data.month_minutes)}</p></div>
        </div>
      </div>
      <div className="glass-card rounded-3xl p-5">
        <h3 className="text-base text-ink-900 mb-3">{t("clock.history")}</h3>
        {data.sessions.length === 0 ? <p className="text-sm text-ink-500">{t("clock.noSessions")}</p> : (
          <ul className="divide-y divide-ink-100 text-sm">
            {data.sessions.map((s) => (
              <li key={s.id} className="flex items-center justify-between py-2">
                <span>{fmt.shortDate(s.started_at)} · {new Date(s.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}–{s.ended_at ? new Date(s.ended_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "…"}{s.note ? ` · ${s.note}` : ""}</span>
                <span className="text-ink-500">{hoursLabel(s.minutes)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
