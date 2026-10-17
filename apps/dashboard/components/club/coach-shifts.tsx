"use client";

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend, hoursLabel, type WorkSession } from "@/lib/club";
import { fromLocalInput, toLocalInput, type SessionChange } from "@/lib/coach";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// «Os seus turnos do mês»: i turni del cartellino, da correggere (entrata,
// uscita, nota), togliere o aggiungere se dimenticati
// (apps/api/app/domains/club/workclock.py, own_update/own_add/own_delete).
// Le regole vere le controlla il server (niente futuro, niente
// sovrapposizioni, solo questo mese e il mese scorso): qui si avvisa prima.

type Shift = WorkSession & { edited_at?: string | null; added_later?: boolean; corrected?: boolean };
interface MonthShifts { month: string; editable_from: string; minutes: number; sessions: Shift[] }

const hm = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const monthOf = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;

export function ShiftHistory() {
  const { t, fmt } = useI18n();
  const now = new Date();
  const months = [monthOf(now), monthOf(new Date(now.getFullYear(), now.getMonth() - 1, 1))];
  const [month, setMonth] = useState(months[0]!);
  const [editing, setEditing] = useState<Shift | "new" | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["club", "staff", "clock", "sessions", month],
    queryFn: () => clubGet<MonthShifts>(`/staff/clock/sessions?month=${month}`),
  });
  const editable = (s: Shift) => !!data && s.started_at >= data.editable_from;

  return (
    <div className="glass-card rounded-3xl p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base text-ink-900">{t("clock.history")}</h3>
        <Button size="sm" variant="secondary" onClick={() => setEditing("new")}>＋ {t("coach2.shift.addForgotten")}</Button>
      </div>
      <div className="mb-3 inline-flex rounded-2xl bg-ink-100/80 p-1 text-sm" role="tablist">
        {months.map((m) => (
          <button key={m} type="button" role="tab" aria-selected={m === month} onClick={() => setMonth(m)}
            className={cn("cursor-pointer rounded-xl px-3 py-1.5 font-semibold capitalize transition",
              m === month ? "bg-white text-ink-900 shadow-sm" : "text-ink-500 hover:text-ink-800")}>
            {fmt.date(new Date(`${m}-01T12:00:00`), { month: "long" })}
          </button>
        ))}
      </div>
      {isLoading || !data ? <Skeleton className="h-40" /> : data.sessions.length === 0 ? (
        <p className="text-sm text-ink-500">{t("clock.noSessions")}</p>
      ) : (
        <>
          <p className="mb-2 text-xs text-ink-500">{t("coach2.shift.monthTotal", { hours: hoursLabel(data.minutes) })}</p>
          <ul className="divide-y divide-ink-100 text-sm">
            <AnimatePresence initial={false}>
              {data.sessions.map((s) => (
                <motion.li key={s.id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }}
                  className="flex items-center gap-3 py-2.5">
                  <span className="flex h-10 w-10 shrink-0 flex-col items-center justify-center rounded-xl bg-ink-50 leading-none ring-1 ring-ink-100">
                    <span className="font-display text-base text-ink-900">{new Date(s.started_at).getDate()}</span>
                    <span className="text-[9px] font-bold uppercase text-ink-500">{fmt.date(new Date(s.started_at), { weekday: "short" })}</span>
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold text-ink-900 tabular-nums">
                      {hm(s.started_at)} → {s.ended_at ? hm(s.ended_at) : <span className="text-emerald-600">{t("coach2.shift.open")}</span>}
                      <span className="ml-2 font-normal text-ink-500">{hoursLabel(s.minutes)}</span>
                    </span>
                    <span className="flex flex-wrap items-center gap-1 text-xs text-ink-500">
                      {s.note && <span className="truncate">{s.note}</span>}
                      {s.added_later && <Badge tone="info">＋ {t("coach2.shift.addedLater")}</Badge>}
                      {!s.added_later && s.edited_at && <Badge tone="warning">✎ {t("coach2.shift.edited")}</Badge>}
                      {s.corrected && <Badge tone="neutral">{t("coach2.shift.correctedBySecretary")}</Badge>}
                    </span>
                  </span>
                  {editable(s) ? (
                    <Button size="sm" variant="ghost" onClick={() => setEditing(s)} aria-label={t("coach2.shift.edit")}>✎</Button>
                  ) : <span className="text-xs text-ink-300" title={t("coach2.shift.locked")}>🔒</span>}
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        </>
      )}
      <p className="mt-3 text-[11px] text-ink-400">{t("coach2.shift.rules")}</p>
      {editing && <ShiftModal shift={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ShiftModal({ shift, onClose }: { shift: Shift | null; onClose: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [start, setStart] = useState(() => toLocalInput(shift?.started_at) || toLocalInput(new Date(new Date().getTime() - 2 * 3600_000).toISOString()));
  const [end, setEnd] = useState(() => toLocalInput(shift?.ended_at) || (shift ? "" : toLocalInput(new Date(new Date().getTime() - 3600_000).toISOString())));
  const [note, setNote] = useState(shift?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = !!shift && !shift.ended_at;

  // Le stesse regole del server, per dirle subito.
  const startIso = fromLocalInput(start);
  const endIso = fromLocalInput(end);
  const soon = new Date().getTime() + 5 * 60_000;
  const problem = !startIso ? t("coach2.shift.needStart")
    : !endIso && !open ? t("coach2.shift.needEnd")
    : new Date(startIso).getTime() > soon || (endIso && new Date(endIso).getTime() > soon) ? t("coach2.shift.noFuture")
    : endIso && endIso <= startIso ? t("coach2.shift.endAfterStart")
    : endIso && new Date(endIso).getTime() - new Date(startIso).getTime() > 24 * 3600_000 ? t("coach2.shift.max24")
    : null;
  const duration = startIso && endIso && !problem
    ? hoursLabel(Math.round((new Date(endIso).getTime() - new Date(startIso).getTime()) / 60_000)) : null;

  async function done(promise: Promise<unknown>, ok: string) {
    setBusy(true);
    setError(null);
    try {
      await promise;
      await qc.invalidateQueries({ queryKey: ["club", "staff", "clock"] });
      void qc.invalidateQueries({ queryKey: ["club", "staff-work"] });
      toast({ tone: "success", title: ok });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function save() {
    const body = { started_at: startIso, ended_at: endIso, note: note.trim() || null };
    void done(shift ? clubSend(`/staff/clock/sessions/${shift.id}`, "PATCH", open && !endIso ? { started_at: startIso, note: body.note } : body)
      : clubSend("/staff/clock/sessions", "POST", body), shift ? t("coach2.shift.saved") : t("coach2.shift.added"));
  }
  function remove() {
    if (!shift || !window.confirm(t("coach2.shift.deleteConfirm"))) return;
    void done(clubSend(`/staff/clock/sessions/${shift.id}`, "DELETE"), t("coach2.shift.deleted"));
  }

  return (
    <Modal open onClose={onClose} size="sm" title={shift ? t("coach2.shift.editTitle") : t("coach2.shift.addTitle")}
      subtitle={shift ? undefined : t("coach2.shift.addHint")}
      footer={<>
        {shift && <Button variant="ghost" className="mr-auto text-rose-600" onClick={remove} disabled={busy}>{t("coach2.shift.delete")}</Button>}
        <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button onClick={save} loading={busy} disabled={!!problem}>{t("common.save")}</Button>
      </>}>
      <div className="space-y-4">
        <Field label={`🟢 ${t("coach2.shift.entry")}`}>
          <Input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} max={toLocalInput(new Date().toISOString())} />
        </Field>
        <Field label={`🔴 ${t("coach2.shift.exit")}`} hint={open ? t("coach2.shift.openHint") : undefined}>
          <Input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} max={toLocalInput(new Date().toISOString())} />
        </Field>
        <Field label={t("support.note")}>
          <Input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder={t("clock.notePlaceholder")} />
        </Field>
        {duration && <p className="rounded-2xl bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-800 ring-1 ring-emerald-200">⏱️ {duration}</p>}
        {(problem || error) && <p className="rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">{error ?? problem}</p>}
        <p className="text-xs text-ink-500">{t("coach2.shift.auditHint")}</p>
      </div>
    </Modal>
  );
}

// --- La segreteria: che cosa è stato cambiato -----------------------------------------------------

/** I segni su un turno nelle ore della segreteria: ritoccato, scritto dopo, corretto. */
export function ShiftBadges({ shift }: { shift: Shift }) {
  const { t, fmt } = useI18n();
  return (
    <>
      {shift.added_later && <Badge tone="info">＋ {t("coach2.shift.addedLater")}</Badge>}
      {!shift.added_later && shift.edited_at && <Badge tone="warning">✎ {t("coach2.shift.editedOn", { date: fmt.shortDate(shift.edited_at) })}</Badge>}
      {shift.corrected && <Badge tone="neutral">{t("coach2.shift.correctedBySecretary")}</Badge>}
    </>
  );
}

const ACTION_ICON: Record<SessionChange["action"], string> = { edited: "✎", added: "＋", deleted: "🗑️", corrected: "🛠️" };

/** L'elenco delle modifiche ai turni del mese (audit): chi, quando, prima → dopo. */
export function SessionChangesLog({ month }: { month: string }) {
  const { t, fmt } = useI18n();
  const [open, setOpen] = useState(false);
  const { data } = useQuery({
    queryKey: ["club", "admin", "work-session-changes", month],
    queryFn: () => clubGet<SessionChange[]>(`/admin/work-sessions/changes?month=${month}`),
  });
  if (!data?.length) return null;
  const span = (v: SessionChange["before"]) => v
    ? `${fmt.shortDate(v.started_at ?? "")} ${v.started_at ? hm(v.started_at) : ""}–${v.ended_at ? hm(v.ended_at) : "…"}${v.note ? ` · ${v.note}` : ""}`
    : "—";
  return (
    <section className="rounded-3xl bg-amber-50/60 p-4 ring-1 ring-amber-200">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full cursor-pointer items-center justify-between gap-2 text-left">
        <span className="font-semibold text-ink-900">✎ {t("coach2.shift.changesTitle", { n: data.length })}</span>
        <span className="text-ink-500">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <ul className="mt-3 divide-y divide-amber-100 text-sm">
          {data.map((c) => (
            <li key={c.id} className="py-2">
              <p className="text-xs text-ink-500">
                {ACTION_ICON[c.action]} <span className="font-semibold text-ink-800">{t.dyn(`coach2.shift.action.${c.action}`, c.action)}</span>
                {" · "}{c.user_name}{c.actor_name && c.actor_name !== c.user_name ? ` (${t("coach2.shift.by", { name: c.actor_name })})` : ""}
                {" · "}{fmt.date(new Date(c.at), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
              </p>
              <p className="tabular-nums text-ink-800">
                {c.before && <span className="text-ink-400 line-through">{span(c.before)}</span>}
                {c.before && c.after && " → "}
                {c.after && <span>{span(c.after)}</span>}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
