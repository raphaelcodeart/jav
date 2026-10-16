"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { WorkHoursPanel } from "@/components/club/club-console";
import { clubGet, clubSend, hoursLabel } from "@/lib/club";
import { friendlyApiError } from "@/lib/api-error";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// Il personale del club (apps/api/app/domains/club/staff_work.py): la
// segreteria vede il mese (ore × tariffa, compiti, lavoretti, quanto c'è da
// pagare) e le conversazioni con lo staff; lo staff dalla sua area scrive i
// compiti svolti e parla con il club o con JudoArteVida.

const A = (path: string) => `/admin${path}`;
const thisMonth = () => new Date().toISOString().slice(0, 7);
const today = () => new Date().toISOString().slice(0, 10);
const toCents = (v: string) => Math.round(Number(v.replace(",", ".")) * 100) || 0;

interface StaffTask {
  id: string; user_id: string | null; person_name: string; kind: "TASK" | "ODD_JOB"; title: string; done_on: string;
  minutes: number | null; cost_cents: number; note: string | null; paid_on: string | null;
}
interface MonthPerson {
  user_id: string | null; name: string; minutes: number; hours_cost_cents: number; hourly_rate_cents: number | null;
  tasks: number; jobs_cost_cents: number; unpaid_cents: number; total_cents: number;
}
interface StaffMonth {
  month: string; people: MonthPerson[]; tasks: StaffTask[];
  totals: { minutes: number; hours_cost_cents: number; jobs_cost_cents: number; unpaid_cents: number; total_cents: number };
}
interface MyMonth {
  month: string; minutes: number; hourly_rate_cents: number | null; hours_cost_cents: number; jobs_cost_cents: number;
  unpaid_cents: number; tasks: StaffTask[];
}
interface StaffMessage { id: string; channel: "CLUB" | "JAV"; from_staff: boolean; body: string; created_at: string; read_at: string | null }
interface InboxRow {
  club_id: string; club_name: string; staff_user_id: string; name: string; last_at: string; last_body: string;
  last_from_staff: boolean; unread: number;
}
interface StaffRow { user_id: string; email: string; role: string }

function Big({ label, value, tone = "text-ink-900" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
      <p className="text-[11px] font-bold uppercase tracking-wider text-ink-500">{label}</p>
      <p className={cn("mt-1 font-display text-2xl", tone)}>{value}</p>
    </div>
  );
}

// --- La segreteria --------------------------------------------------------------------------------

export function StaffManagementPanel() {
  const { t } = useI18n();
  const [tab, setTab] = useState("month");
  return (
    <div className="space-y-5">
      <Tabs value={tab} onChange={setTab} items={[
        { key: "month", label: `📊 ${t("staffMgmt.tabMonth")}` },
        { key: "hours", label: `⏱️ ${t("staffMgmt.tabHours")}` },
        { key: "messages", label: `💬 ${t("staffMgmt.tabMessages")}` },
      ]} />
      {tab === "month" && <StaffMonthPanel />}
      {tab === "hours" && <WorkHoursPanel />}
      {tab === "messages" && <StaffInbox mode="club" />}
    </div>
  );
}

function StaffMonthPanel() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [month, setMonth] = useState(thisMonth);
  const [adding, setAdding] = useState(false);
  const key = ["club", "admin", "staff-work", month];
  const { data, isLoading } = useQuery({ queryKey: key, queryFn: () => clubGet<StaffMonth>(A(`/staff-work?month=${month}`)) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["club", "admin", "staff-work"] });

  async function pay(task: StaffTask) {
    let cost: number | undefined;
    if (task.cost_cents <= 0) {
      const v = window.prompt(t("staffMgmt.askCost"), "");
      if (!v) return;
      cost = toCents(v);
      if (cost <= 0) return;
    }
    try {
      await clubSend(A(`/staff-work/tasks/${task.id}/pay`), "POST", cost ? { cost_cents: cost } : {});
      toast({ tone: "success", title: t("staffMgmt.paid") });
      await refresh();
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    }
  }
  async function remove(task: StaffTask) {
    if (!window.confirm(t("staffMgmt.deleteConfirm", { what: task.title }))) return;
    try {
      await clubSend(A(`/staff-work/tasks/${task.id}`), "DELETE");
      await refresh();
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Input type="month" value={month} onChange={(e) => setMonth(e.target.value || thisMonth())} className="w-48" aria-label={t("staffMgmt.month")} />
        <Button onClick={() => setAdding((x) => !x)}>➕ {t("staffMgmt.addJob")}</Button>
      </div>
      {adding && <AddJobForm onDone={() => { setAdding(false); void refresh(); }} />}
      {isLoading || !data ? <Skeleton className="h-48" /> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Big label={t("staffMgmt.hours")} value={hoursLabel(data.totals.minutes)} />
            <Big label={t("staffMgmt.hoursCost")} value={fmt.euro(data.totals.hours_cost_cents)} />
            <Big label={t("staffMgmt.jobsCost")} value={fmt.euro(data.totals.jobs_cost_cents)} />
            <Big label={t("staffMgmt.total")} value={fmt.euro(data.totals.total_cents)} tone="text-brand-700" />
          </div>
          {data.totals.unpaid_cents > 0 && (
            <p className="rounded-2xl bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900 ring-1 ring-amber-200">
              ⏳ {t("staffMgmt.unpaid", { amount: fmt.euro(data.totals.unpaid_cents) })}
            </p>
          )}
          {data.people.length === 0 ? <EmptyState title={t("staffMgmt.empty")} text={t("staffMgmt.emptyText")} /> : (
            <Table>
              <THead><tr>
                <TH>{t("people.colName")}</TH><TH className="text-right">{t("staffMgmt.hours")}</TH>
                <TH className="text-right">{t("staffMgmt.rate")}</TH><TH className="text-right">{t("staffMgmt.hoursCost")}</TH>
                <TH className="text-right">{t("staffMgmt.jobs")}</TH><TH className="text-right">{t("staffMgmt.total")}</TH>
              </tr></THead>
              <TBody>
                {data.people.map((p) => (
                  <TR key={p.user_id ?? p.name}>
                    <TD className="font-semibold text-ink-900">{p.name}{!p.user_id && <span className="ml-2 text-xs font-normal text-ink-400">{t("staffMgmt.external")}</span>}</TD>
                    <TD className="text-right">{p.minutes ? hoursLabel(p.minutes) : "—"}</TD>
                    <TD className="text-right">{p.hourly_rate_cents != null ? `${fmt.euro(p.hourly_rate_cents)}/h` : "—"}</TD>
                    <TD className="text-right">{fmt.euro(p.hours_cost_cents)}</TD>
                    <TD className="text-right">{p.tasks ? `${p.tasks} · ${fmt.euro(p.jobs_cost_cents)}` : "—"}</TD>
                    <TD className="text-right font-semibold">{fmt.euro(p.total_cents)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
          <section>
            <h3 className="mb-2 text-sm text-ink-900">{t("staffMgmt.tasksTitle")}</h3>
            {data.tasks.length === 0 ? <p className="text-sm text-ink-500">{t("staffMgmt.noTasks")}</p> : (
              <ul className="divide-y divide-ink-100 rounded-2xl bg-white shadow-soft ring-1 ring-ink-900/5">
                {data.tasks.map((task) => (
                  <li key={task.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                    <span aria-hidden="true">{task.kind === "TASK" ? "✅" : "🛠️"}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold text-ink-900">{task.title}</span>
                      <span className="block text-xs text-ink-500">
                        {task.person_name} · {fmt.shortDate(task.done_on)}{task.minutes ? ` · ${hoursLabel(task.minutes)}` : ""}{task.note ? ` · ${task.note}` : ""}
                      </span>
                    </span>
                    {task.cost_cents > 0 && <span className="font-semibold">{fmt.euro(task.cost_cents)}</span>}
                    {task.paid_on ? <Badge tone="success">✓ {t("staffMgmt.paidOn", { date: fmt.shortDate(task.paid_on) })}</Badge> : (
                      <span className="flex gap-1">
                        <Button size="sm" variant="secondary" onClick={() => pay(task)}>💶 {t("staffMgmt.pay")}</Button>
                        <Button size="sm" variant="ghost" onClick={() => remove(task)}>{t("acc.delete")}</Button>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function AddJobForm({ onDone }: { onDone: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const { data: staff } = useQuery({ queryKey: ["club", "admin", "staff"], queryFn: () => clubGet<StaffRow[]>(A("/staff")) });
  const [who, setWho] = useState("");
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [doneOn, setDoneOn] = useState(today);
  const [cost, setCost] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await clubSend(A("/staff-work/tasks"), "POST", {
        kind: "ODD_JOB", user_id: who || null, person_name: who ? null : name, title, done_on: doneOn,
        cost_cents: toCents(cost), note: note || null,
      });
      toast({ tone: "success", title: t("staffMgmt.saved") });
      onDone();
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="grid gap-3 rounded-2xl bg-ink-50 p-4 sm:grid-cols-2">
      <Field label={t("staffMgmt.who")}>
        <Select value={who} onChange={(e) => setWho(e.target.value)}>
          <option value="">{t("staffMgmt.someoneElse")}</option>
          {(staff ?? []).map((s) => <option key={s.user_id} value={s.user_id}>{s.email}</option>)}
        </Select>
      </Field>
      {!who && <Field label={t("staffMgmt.personName")}><Input value={name} maxLength={150} onChange={(e) => setName(e.target.value)} /></Field>}
      <Field label={t("staffMgmt.what")}><Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={t("staffMgmt.whatPlaceholder")} /></Field>
      <Field label={t("staffMgmt.when")}><Input type="date" value={doneOn} onChange={(e) => setDoneOn(e.target.value)} /></Field>
      <Field label={t("staffMgmt.cost")}><Input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} placeholder="30,00" /></Field>
      <Field label={t("support.note")}><Input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} /></Field>
      <div className="sm:col-span-2">
        <Button loading={busy} disabled={title.trim().length < 2 || (!who && name.trim().length < 2)} onClick={save}>{t("common.save")}</Button>
      </div>
    </motion.div>
  );
}

// --- Le conversazioni -----------------------------------------------------------------------------

async function platformGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api/proxy/club-platform${path}`);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function platformPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api/proxy/club-platform${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** La casella dei messaggi dello staff: la segreteria (`club`, il canale CLUB
 *  del suo club) o JudoArteVida (`platform`, il canale JAV di tutti i club). */
export function StaffInbox({ mode }: { mode: "club" | "platform" }) {
  const { t, fmt } = useI18n();
  const [open, setOpen] = useState<InboxRow | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["staff-inbox", mode],
    queryFn: () => mode === "club" ? clubGet<InboxRow[]>(A("/staff-messages")) : platformGet<InboxRow[]>("/staff-messages"),
    refetchInterval: 60_000,
  });
  if (isLoading) return <Skeleton className="h-48" />;
  if (!data || data.length === 0) return <EmptyState title={t("staffMsg.emptyInbox")} text={t(mode === "club" ? "staffMsg.emptyInboxClub" : "staffMsg.emptyInboxJav")} />;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <ul className="divide-y divide-ink-100 overflow-hidden rounded-2xl bg-white shadow-soft ring-1 ring-ink-900/5">
        {data.map((r) => (
          <li key={`${r.club_id}-${r.staff_user_id}`}>
            <button type="button" onClick={() => setOpen(r)}
              className={cn("flex w-full cursor-pointer items-start gap-3 px-4 py-3 text-left hover:bg-ink-50",
                open?.staff_user_id === r.staff_user_id && open.club_id === r.club_id && "bg-brand-50")}>
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-100 font-bold text-brand-700">{(r.name || "?").slice(0, 1).toUpperCase()}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate font-semibold text-ink-900">{r.name}</span>
                  <span className="shrink-0 text-[11px] text-ink-400">{fmt.shortDate(r.last_at)}</span>
                </span>
                {mode === "platform" && <span className="block text-xs text-brand-700">🏯 {r.club_name}</span>}
                <span className="block truncate text-xs text-ink-500">{r.last_from_staff ? "" : "↩ "}{r.last_body}</span>
              </span>
              {r.unread > 0 && <span className="rounded-full bg-rose-500 px-2 py-0.5 text-[11px] font-bold text-white">{r.unread}</span>}
            </button>
          </li>
        ))}
      </ul>
      {open ? <AdminThread key={`${open.club_id}-${open.staff_user_id}`} row={open} mode={mode} /> : (
        <div className="hidden items-center justify-center rounded-2xl bg-ink-50 p-8 text-sm text-ink-500 lg:flex">{t("staffMsg.pick")}</div>
      )}
    </div>
  );
}

function AdminThread({ row, mode }: { row: InboxRow; mode: "club" | "platform" }) {
  const qc = useQueryClient();
  const path = mode === "club" ? A(`/staff-messages/${row.staff_user_id}`) : `/staff-messages/${row.club_id}/${row.staff_user_id}`;
  const { data } = useQuery({
    queryKey: ["staff-thread", mode, row.club_id, row.staff_user_id],
    queryFn: async () => {
      const rows = mode === "club" ? await clubGet<StaffMessage[]>(path) : await platformGet<StaffMessage[]>(path);
      void qc.invalidateQueries({ queryKey: ["staff-inbox", mode] });
      return rows;
    },
  });
  return (
    <Conversation title={row.name} messages={data ?? []} mine={(m) => !m.from_staff}
      send={(body) => mode === "club" ? clubSend(path, "POST", { body }) : platformPost(path, { body })}
      onSent={() => qc.invalidateQueries({ queryKey: ["staff-thread", mode, row.club_id, row.staff_user_id] })} />
  );
}

function Conversation({ title, messages, mine, send, onSent }: {
  title: string; messages: StaffMessage[]; mine: (m: StaffMessage) => boolean;
  send: (body: string) => Promise<unknown>; onSent: () => void;
}) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [messages.length]);
  async function submit() {
    setBusy(true);
    try {
      await send(body.trim());
      setBody("");
      onSent();
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex h-[32rem] flex-col overflow-hidden rounded-2xl bg-white shadow-soft ring-1 ring-ink-900/5">
      <p className="border-b border-ink-100 px-4 py-3 font-semibold text-ink-900">{title}</p>
      <div className="flex-1 space-y-2 overflow-y-auto bg-ink-50/50 p-4">
        {messages.length === 0 && <p className="text-center text-sm text-ink-400">{t("staffMsg.noMessages")}</p>}
        {messages.map((m) => (
          <div key={m.id} className={cn("flex", mine(m) ? "justify-end" : "justify-start")}>
            <div className={cn("max-w-[80%] rounded-2xl px-3.5 py-2 text-sm shadow-sm",
              mine(m) ? "rounded-br-md bg-brand-600 text-white" : "rounded-bl-md bg-white text-ink-800 ring-1 ring-ink-900/5")}>
              <p className="whitespace-pre-wrap break-words">{m.body}</p>
              <p className={cn("mt-1 text-right text-[10px]", mine(m) ? "text-white/70" : "text-ink-400")}>
                {fmt.date(new Date(m.created_at), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                {mine(m) && m.read_at ? " ✓✓" : ""}
              </p>
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>
      <div className="flex gap-2 border-t border-ink-100 p-3">
        <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={2} maxLength={4000} placeholder={t("staffMsg.write")} className="flex-1" />
        <Button loading={busy} disabled={body.trim().length < 2} onClick={submit}>➤</Button>
      </div>
    </div>
  );
}

// --- L'area dello staff ---------------------------------------------------------------------------

/** «Il mio lavoro»: le ore del mese e quanto valgono, i compiti svolti. */
export function StaffWorkPanel() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [month, setMonth] = useState(thisMonth);
  const { data, isLoading } = useQuery({ queryKey: ["club", "staff-work", month], queryFn: () => clubGet<MyMonth>(`/staff/work?month=${month}`) });
  const [title, setTitle] = useState("");
  const [doneOn, setDoneOn] = useState(today);
  const [minutes, setMinutes] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await clubSend("/staff/work/tasks", "POST", { title, done_on: doneOn, minutes: Number(minutes) || null, note: note || null });
      setTitle("");
      setMinutes("");
      setNote("");
      toast({ tone: "success", title: t("staffMgmt.saved") });
      await qc.invalidateQueries({ queryKey: ["club", "staff-work"] });
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  async function remove(task: StaffTask) {
    if (!window.confirm(t("staffMgmt.deleteConfirm", { what: task.title }))) return;
    try {
      await clubSend(`/staff/work/tasks/${task.id}`, "DELETE");
      await qc.invalidateQueries({ queryKey: ["club", "staff-work"] });
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    }
  }
  return (
    <div className="space-y-5">
      <Input type="month" value={month} onChange={(e) => setMonth(e.target.value || thisMonth())} className="w-48" aria-label={t("staffMgmt.month")} />
      {isLoading || !data ? <Skeleton className="h-32" /> : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Big label={t("staffMgmt.hours")} value={hoursLabel(data.minutes)} />
          <Big label={t("staffMgmt.rate")} value={data.hourly_rate_cents != null ? `${fmt.euro(data.hourly_rate_cents)}/h` : "—"} />
          <Big label={t("staffMgmt.hoursCost")} value={fmt.euro(data.hours_cost_cents)} tone="text-brand-700" />
          <Big label={t("staffMgmt.jobsCost")} value={fmt.euro(data.jobs_cost_cents)} />
        </div>
      )}
      <div className="grid gap-3 rounded-2xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5 sm:grid-cols-2">
        <p className="text-sm font-semibold text-ink-900 sm:col-span-2">✅ {t("staffMgmt.logTask")}</p>
        <Field label={t("staffMgmt.what")}><Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={t("staffMgmt.taskPlaceholder")} /></Field>
        <Field label={t("staffMgmt.when")}><Input type="date" value={doneOn} onChange={(e) => setDoneOn(e.target.value)} /></Field>
        <Field label={t("staffMgmt.minutes")}><Input type="number" min={1} max={1440} value={minutes} onChange={(e) => setMinutes(e.target.value)} /></Field>
        <Field label={t("support.note")}><Input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} /></Field>
        <div className="sm:col-span-2"><Button loading={busy} disabled={title.trim().length < 2} onClick={save}>{t("common.save")}</Button></div>
      </div>
      {data && (data.tasks.length === 0 ? <p className="text-sm text-ink-500">{t("staffMgmt.noTasks")}</p> : (
        <ul className="divide-y divide-ink-100 rounded-2xl bg-white shadow-soft ring-1 ring-ink-900/5">
          {data.tasks.map((task) => (
            <li key={task.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <span aria-hidden="true">{task.kind === "TASK" ? "✅" : "🛠️"}</span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold text-ink-900">{task.title}</span>
                <span className="block text-xs text-ink-500">{fmt.shortDate(task.done_on)}{task.minutes ? ` · ${hoursLabel(task.minutes)}` : ""}</span>
              </span>
              {task.cost_cents > 0 && <span className="font-semibold">{fmt.euro(task.cost_cents)}</span>}
              {task.paid_on ? <Badge tone="success">✓ {t("staffMgmt.paidShort")}</Badge> : task.kind === "TASK" && (
                <Button size="sm" variant="ghost" onClick={() => remove(task)}>{t("acc.delete")}</Button>
              )}
            </li>
          ))}
        </ul>
      ))}
    </div>
  );
}

/** Le comunicazioni dello staff con la segreteria del club o con JudoArteVida. */
export function StaffMessagesPanel() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [channel, setChannel] = useState<"CLUB" | "JAV">("CLUB");
  const { data } = useQuery({
    queryKey: ["club", "staff-messages", channel],
    queryFn: () => clubGet<StaffMessage[]>(`/staff/messages?channel=${channel}`),
    refetchInterval: 60_000,
  });
  return (
    <div className="space-y-4">
      <Tabs value={channel} onChange={(k) => setChannel(k as "CLUB" | "JAV")} items={[
        { key: "CLUB", label: `🏯 ${t("staffMsg.toClub")}` },
        { key: "JAV", label: `🌍 ${t("staffMsg.toJav")}` },
      ]} />
      <p className="text-sm text-ink-500">{t(channel === "CLUB" ? "staffMsg.clubHint" : "staffMsg.javHint")}</p>
      <Conversation title={channel === "CLUB" ? t("staffMsg.toClub") : t("staffMsg.toJav")} messages={data ?? []} mine={(m) => m.from_staff}
        send={(body) => clubSend("/staff/messages", "POST", { channel, body })}
        onSent={() => qc.invalidateQueries({ queryKey: ["club", "staff-messages", channel] })} />
    </div>
  );
}
