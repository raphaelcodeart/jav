"use client";

import { MotionConfig, motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell, type NavItem } from "@/components/app-shell";
import { ExtAccountsTables, yearOptions } from "@/components/ext-courses/accounts";
import { SchoolBadge, useGroupLine, useMethodLabel, usePeriodLabel } from "@/components/ext-courses/common";
import { Badge, FeeStatusPill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import {
  apiWeekday, EXT_PAY_METHODS, extGet, extSend, fetchStaffCourses, isoDay, STAFF_COURSES_KEY,
  type ExtAccounts, type ExtAttendanceDay, type ExtAttendanceRow, type ExtClock, type ExtCourse, type ExtFee,
  type ExtParticipant, type ExtRoster, type ExtStaffCourse, type ExtStaffProof,
} from "@/lib/ext-courses";
import { useI18n } from "@/lib/i18n/provider";

type Tab = "participants" | "attendance" | "payments" | "notices" | "clock" | "earnings";

const emoji = (e: string) => <span className="text-base leading-none" aria-hidden="true">{e}</span>;
const rosterKey = (id: string) => ["ext", "staff", "course", id];

/** L'area della scuola e del treinador di un corso esterno (/escola). Chi
 *  vede che cosa lo decide il server dalle righe di ext_staff (`roles` della
 *  risposta): la scuola vede contatti, pagamenti e prove; il treinador nomi,
 *  età, gruppi e note, segna le presenze, timbra entrata e uscita e vede i
 *  suoi guadagni. Il superadmin vede tutto (da "Abrir como escola"). */
export function ExtSchoolArea({ email, initialCourse }: { email?: string; initialCourse?: string }) {
  const { t } = useI18n();
  const [picked, setPicked] = useState<string | null>(initialCourse ?? null);
  const [tab, setTab] = useState<Tab>("participants");
  const courses = useQuery({ queryKey: STAFF_COURSES_KEY, queryFn: fetchStaffCourses });
  const list = courses.data ?? [];
  const current = list.find((c) => c.id === picked) ?? list[0] ?? null;
  const roster = useQuery({
    queryKey: rosterKey(current?.id ?? ""),
    queryFn: () => extGet<ExtRoster>(`/staff/courses/${current?.id}`),
    enabled: !!current,
  });
  const roles = roster.data?.roles ?? current?.roles ?? [];
  const isSchool = roles.includes("SCHOOL") || roles.includes("ADMIN");
  // Il superadmin non timbra e non ha guadagni: entra per guardare.
  const isCoach = roles.includes("COACH") && !roles.includes("ADMIN");

  const navItems: NavItem[] = [
    { key: "participants", label: t("ext.school.navParticipants"), icon: emoji("🧒") },
    { key: "attendance", label: t("ext.school.navAttendance"), icon: emoji("✅") },
    ...(isSchool ? [{ key: "payments", label: t("ext.school.navPayments"), icon: emoji("💶") }] : []),
    { key: "notices", label: t("ext.school.navNotices"), icon: emoji("📣") },
    ...(isCoach ? [
      { key: "clock", label: t("ext.school.navClock"), icon: emoji("⏱️") },
      { key: "earnings", label: t("ext.school.navEarnings"), icon: emoji("💰") },
    ] : []),
  ];
  const active: Tab = navItems.some((n) => n.key === tab) ? tab : "participants";

  const switcher = list.length > 1 && current ? (
    <Select aria-label={t("ext.school.course")} value={current.id} onChange={(e) => setPicked(e.target.value)} className="w-auto min-w-56">
      {list.map((c) => <option key={c.id} value={c.id}>{c.school_name} · {c.name}</option>)}
    </Select>
  ) : undefined;

  return (
    <AppShell roleLabel={isSchool && !isCoach ? t("ext.school.roleSchool") : t("ext.school.roleCoach")} email={email}
      navItems={current ? navItems : []} activeKey={active} onNavigate={(k) => setTab(k as Tab)} headerActions={switcher}
      headerTitle={current?.school_name}>
      <MotionConfig reducedMotion="user">
        {courses.isLoading ? (
          <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-64" /></div>
        ) : courses.error ? (
          <EmptyState icon={<span className="text-3xl">🏫</span>} title={t("ext.school.loadFailed")} text={(courses.error as Error).message} />
        ) : !current ? (
          <EmptyState icon={<span className="text-3xl">🏫</span>} title={t("ext.school.none")} text={t("ext.school.noneText")} />
        ) : roster.isLoading || !roster.data ? (
          roster.error
            ? <EmptyState icon={<span className="text-3xl">🏫</span>} title={t("ext.school.loadFailed")} text={(roster.error as Error).message} />
            : <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-64" /></div>
        ) : (
          <div className="space-y-6">
            <CourseHeader course={roster.data.course} />
            {active === "participants" && <Participants roster={roster.data} school={isSchool} />}
            {active === "attendance" && <Attendance key={current.id} course={roster.data.course} />}
            {active === "payments" && isSchool && <Payments roster={roster.data} />}
            {active === "notices" && <Notices roster={roster.data} />}
            {active === "clock" && isCoach && <Clock course={current} courses={list} />}
            {active === "earnings" && isCoach && <Earnings />}
          </div>
        )}
      </MotionConfig>
    </AppShell>
  );
}

function CourseHeader({ course }: { course: ExtCourse }) {
  const groupLine = useGroupLine();
  return (
    <div className="flex items-center gap-4 rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
      <SchoolBadge course={course} className="h-14 w-14" />
      <div className="min-w-0 flex-1">
        <p className="font-display text-xl leading-tight text-ink-900">{course.school_name}</p>
        <p className="text-sm text-ink-500">{course.name}{course.school_city ? ` · ${course.school_city}` : ""}</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {course.groups.filter((g) => g.active).map((g) => (
            <span key={g.id} className="rounded-full bg-ink-50 px-2.5 py-0.5 text-xs capitalize text-ink-600 ring-1 ring-ink-100">{g.name} · {groupLine(g)}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

// --- Participantes --------------------------------------------------------------------------------

function Participants({ roster, school }: { roster: ExtRoster; school: boolean }) {
  const { t, fmt } = useI18n();
  const active = roster.participants.filter((p) => p.status === "ACTIVE");
  const sections = [
    ...roster.course.groups.map((g) => ({ id: g.id, name: g.name, people: active.filter((p) => p.group_id === g.id) })),
    { id: "none", name: t("ext.school.noGroup"), people: active.filter((p) => !p.group_id || !roster.course.groups.some((g) => g.id === p.group_id)) },
  ].filter((s) => s.people.length > 0);

  if (active.length === 0) return <EmptyState icon={<span className="text-3xl">🧒</span>} title={t("ext.school.noParticipants")} text={t("ext.school.noParticipantsText")} />;
  return (
    <div className="space-y-6">
      <PageHeader title={t("ext.school.navParticipants")} subtitle={t("ext.school.participantsCount", { n: active.length })} />
      {sections.map((s) => (
        <section key={s.id} className="space-y-2">
          <h3 className="px-1 text-xs font-bold uppercase tracking-[0.18em] text-ink-500">{s.name} · {s.people.length}</h3>
          <ul className="grid gap-2 md:grid-cols-2">
            {s.people.map((p) => (
              <li key={p.id} className="rounded-2xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-ink-900">{p.first_name} {p.last_name}</p>
                    <p className="text-xs text-ink-500">{t("ext.family.age", { n: p.age })} · {t("ext.school.presentMonth", { n: p.present_this_month })}</p>
                  </div>
                  {school && (p.overdue
                    ? <Badge tone="danger" dot>{t("ext.school.overdue", { amount: fmt.euro(p.due_cents ?? 0) })}</Badge>
                    : (p.due_cents ?? 0) > 0
                      ? <Badge tone="warning" dot>{t("ext.school.due", { amount: fmt.euro(p.due_cents ?? 0) })}</Badge>
                      : <Badge tone="success" dot>{t("ext.school.upToDate")}</Badge>)}
                </div>
                {p.notes && <p className="mt-2 rounded-xl bg-amber-50 px-3 py-1.5 text-xs text-amber-900">📝 {p.notes}</p>}
                {school && (p.guardian_name || p.guardian_phone || p.guardian_email) && (
                  <div className="mt-2 space-y-0.5 text-xs text-ink-600">
                    {p.guardian_name && <p>👤 {p.guardian_name}</p>}
                    {p.guardian_phone && <p>📞 <a className="font-semibold text-brand-700 hover:underline" href={`tel:${p.guardian_phone.replace(/\s+/g, "")}`}>{p.guardian_phone}</a></p>}
                    {p.guardian_email && <p className="truncate">✉️ <a className="font-semibold text-brand-700 hover:underline" href={`mailto:${p.guardian_email}`}>{p.guardian_email}</a></p>}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

// --- Presenças -----------------------------------------------------------------------------------

/** Oggi se oggi c'è lezione, altrimenti l'ultimo giorno di lezione (al
 *  massimo una settimana indietro). */
function lastLessonDay(course: ExtCourse): string {
  const days = new Set(course.groups.filter((g) => g.active).map((g) => g.weekday));
  const d = new Date();
  for (let i = 0; i < 7 && days.size > 0; i++) {
    if (days.has(apiWeekday(d))) return isoDay(d);
    d.setDate(d.getDate() - 1);
  }
  return isoDay(new Date());
}

function Attendance({ course }: { course: ExtCourse }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [date, setDate] = useState(() => lastLessonDay(course));
  // Le spunte cambiate e non ancora salvate, legate al giorno: cambiando data
  // si riparte da quello che dice il server, senza un effetto che le azzeri.
  const [edits, setEdits] = useState<{ date: string; marks: Record<string, boolean> }>({ date, marks: {} });
  const marks = edits.date === date ? edits.marks : {};
  const [busy, setBusy] = useState(false);
  const key = ["ext", "attendance", course.id, date];
  const { data, isLoading, error } = useQuery({ queryKey: key, queryFn: () => extGet<ExtAttendanceDay>(`/staff/courses/${course.id}/attendance?on=${date}`) });

  const value = (r: ExtAttendanceRow) => marks[r.id] ?? r.present ?? false;
  const set = (ids: string[], present: boolean) =>
    setEdits({ date, marks: { ...marks, ...Object.fromEntries(ids.map((id) => [id, present])) } });
  const dirty = Object.keys(marks).length > 0;
  const weekday = apiWeekday(new Date(`${date}T00:00:00`));
  const blocks = data ? [
    ...data.groups.filter((g) => g.participants.length > 0).map((g) => ({ id: g.id, title: `${g.name} · ${g.starts_at}–${g.ends_at}`, rows: g.participants, today: g.weekday === weekday })),
    ...(data.no_group.length > 0 ? [{ id: "none", title: t("ext.school.noGroup"), rows: data.no_group, today: true }] : []),
  ] : [];

  async function save() {
    if (!data) return;
    setBusy(true);
    try {
      // Un gruppo che quel giorno non ha lezione non si segna assente in
      // blocco: solo chi è stato toccato (o era già segnato).
      const all = blocks.flatMap((b) => (b.today ? b.rows : b.rows.filter((r) => marks[r.id] !== undefined || r.present !== null)));
      const fresh = await extSend<ExtAttendanceDay>(`/staff/courses/${course.id}/attendance`, "POST",
        { date, marks: Object.fromEntries(all.map((r) => [r.id, value(r)])) });
      queryClient.setQueryData(key, fresh);
      setEdits({ date, marks: {} });
      await queryClient.invalidateQueries({ queryKey: rosterKey(course.id) });
      toast({ tone: "success", title: t("ext.att.saved") });
    } catch (e) {
      toast({ tone: "error", title: t("ext.att.saveFailed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader title={t("ext.school.navAttendance")} subtitle={t("ext.att.subtitle")}
        actions={<Input type="date" aria-label={t("ext.att.date")} value={date} max={isoDay(new Date())} onChange={(e) => e.target.value && setDate(e.target.value)} className="w-auto" />} />
      <p className="px-1 text-sm font-semibold capitalize text-ink-700">{fmt.date(new Date(`${date}T00:00:00`), { weekday: "long", day: "numeric", month: "long" })}</p>
      {isLoading ? <Skeleton className="h-48" /> : error ? (
        <EmptyState title={t("ext.school.loadFailed")} text={(error as Error).message} />
      ) : blocks.length === 0 ? (
        // Il server dà solo i gruppi che hanno lezione in quel giorno della settimana.
        <EmptyState icon={<span className="text-3xl">🗓️</span>} title={t("ext.att.noLesson")} text={t("ext.att.noLessonText")} />
      ) : (
        <>
          {blocks.map((b) => (
            <Card key={b.id} className={cn(!b.today && "opacity-80")}>
              <CardHeader title={b.title} subtitle={b.today ? t("ext.att.presentCount", { n: b.rows.filter(value).length, total: b.rows.length }) : t("ext.att.notToday")}
                action={<Button size="sm" variant="secondary" onClick={() => set(b.rows.map((r) => r.id), true)}>{t("ext.att.allPresent")}</Button>} />
              <ul className="grid gap-2 sm:grid-cols-2">
                {b.rows.map((r) => {
                  const on = value(r);
                  return (
                    <li key={r.id}>
                      <motion.button type="button" whileTap={{ scale: 0.97 }} aria-pressed={on} onClick={() => set([r.id], !on)}
                        className={cn("flex w-full cursor-pointer items-center gap-3 rounded-2xl px-4 py-3 text-left ring-1 transition-colors",
                          on ? "bg-emerald-50 ring-emerald-300" : "bg-white ring-ink-200 hover:ring-ink-300")}>
                        <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold",
                          on ? "bg-emerald-500 text-white" : "bg-ink-100 text-ink-400")} aria-hidden="true">{on ? "✓" : ""}</span>
                        <span className="min-w-0 flex-1 truncate font-semibold text-ink-900">{r.first_name} {r.last_name}</span>
                        {r.present === null && marks[r.id] === undefined && <span className="text-[11px] text-ink-400">{t("ext.att.notMarked")}</span>}
                      </motion.button>
                    </li>
                  );
                })}
              </ul>
            </Card>
          ))}
          <div className="sticky bottom-24 z-10 lg:bottom-4">
            <Button size="lg" className="w-full shadow-lift" onClick={save} loading={busy} disabled={!data}>
              {dirty ? t("ext.att.save") : t("ext.att.saveAgain")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

// --- Pagamentos (scuola e superadmin) --------------------------------------------------------------

function Payments({ roster }: { roster: ExtRoster }) {
  const { t, fmt } = useI18n();
  const period = usePeriodLabel();
  const method = useMethodLabel();
  const toast = useToast();
  const [paying, setPaying] = useState<{ fee: ExtFee; who: ExtParticipant } | null>(null);
  const [rejecting, setRejecting] = useState<ExtStaffProof | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const people = roster.participants.filter((p) => (p.fees ?? []).length > 0 || p.status === "ACTIVE");
  const due = people.reduce((s, p) => s + (p.due_cents ?? 0), 0);

  async function openFile(proof: ExtStaffProof) {
    // La finestra si apre subito, nel clic: dopo l'attesa il browser la bloccherebbe.
    const win = window.open("", "_blank");
    try {
      const { url } = await extGet<{ url: string }>(`/staff/proofs/${proof.id}/url`);
      if (win) win.location.href = url;
      else window.location.assign(url);
    } catch (e) {
      win?.close();
      toast({ tone: "error", title: t("ext.pay.fileFailed"), text: (e as Error).message });
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t("ext.school.navPayments")} subtitle={due > 0 ? t("ext.pay.totalDue", { amount: fmt.euro(due) }) : t("ext.pay.allPaid")} />
      <Card padded={false}>
        <ul className="divide-y divide-ink-100">
          {people.map((p) => {
            const fees = p.fees ?? [];
            const expanded = open === p.id;
            return (
              <li key={p.id}>
                <button type="button" onClick={() => setOpen(expanded ? null : p.id)} aria-expanded={expanded}
                  className="flex w-full cursor-pointer items-center justify-between gap-3 px-5 py-3 text-left hover:bg-ink-50/60">
                  <span className="min-w-0">
                    <span className="block font-semibold text-ink-900">{p.first_name} {p.last_name}</span>
                    <span className="block truncate text-xs text-ink-500">{p.guardian_name ?? ""}{p.guardian_phone ? ` · ${p.guardian_phone}` : ""}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {(p.due_cents ?? 0) > 0
                      ? <Badge tone={p.overdue ? "danger" : "warning"} dot>{fmt.euro(p.due_cents ?? 0)}</Badge>
                      : <Badge tone="success" dot>{t("ext.school.upToDate")}</Badge>}
                    <span className={cn("text-ink-400 transition-transform", expanded && "rotate-90")} aria-hidden="true">›</span>
                  </span>
                </button>
                {expanded && (
                  <ul className="space-y-1.5 bg-ink-50/50 px-5 py-3">
                    {fees.length === 0 && <li className="text-sm text-ink-500">{t("ext.pay.noFees")}</li>}
                    {fees.map((f) => (
                      <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white px-3 py-2 text-sm ring-1 ring-ink-100">
                        <span className="min-w-0">
                          <span className="block font-semibold capitalize text-ink-900">{period(f.period)}</span>
                          <span className="block text-xs text-ink-500">
                            {f.status === "PAID" ? `${method(f.method)} · ${fmt.shortDate(f.paid_at)}` : t("ext.fee.dueOn", { date: fmt.shortDate(f.due_date) })}
                          </span>
                        </span>
                        <span className="flex items-center gap-2">
                          <span className="font-semibold tabular-nums">{fmt.euro(f.amount_cents)}</span>
                          <FeeStatusPill status={f.status} overdue={f.overdue} />
                          {f.status === "DUE" && <Button size="sm" onClick={() => setPaying({ fee: f, who: p })}>{t("ext.pay.markPaid")}</Button>}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      <Card>
        <CardHeader title={t("ext.pay.proofs")} subtitle={t("ext.pay.proofsText")} />
        {(roster.proofs ?? []).length === 0 ? <p className="text-sm text-ink-500">{t("ext.pay.noProofs")}</p> : (
          <ul className="divide-y divide-ink-100">
            {(roster.proofs ?? []).map((proof) => (
              <li key={proof.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
                <span className="min-w-0">
                  <span className="block font-semibold text-ink-900">{proof.parent_name ?? "—"} · {fmt.euro(proof.amount_cents)}</span>
                  <span className="block text-xs text-ink-500">{fmt.shortDate(proof.created_at)} · {method(proof.method)}{proof.note ? ` · ${proof.note}` : ""}</span>
                </span>
                <span className="flex items-center gap-2">
                  <Badge tone={proof.status === "REJECTED" ? "danger" : "success"} dot>{t(proof.status === "REJECTED" ? "ext.proof.rejected" : "ext.proof.accepted")}</Badge>
                  {proof.has_file && <Button size="sm" variant="secondary" onClick={() => openFile(proof)}>📄 {t("ext.pay.openFile")}</Button>}
                  {proof.status === "ACCEPTED" && <Button size="sm" variant="ghost" onClick={() => setRejecting(proof)}>{t("ext.pay.reject")}</Button>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {paying && <MarkPaidModal courseId={roster.course.id} fee={paying.fee} who={paying.who} onClose={() => setPaying(null)} />}
      {rejecting && <RejectModal courseId={roster.course.id} proof={rejecting} onClose={() => setRejecting(null)} />}
    </div>
  );
}

function MarkPaidModal({ courseId, fee, who, onClose }: { courseId: string; fee: ExtFee; who: ExtParticipant; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const period = usePeriodLabel();
  const [how, setHow] = useState<string>("CASH");
  const [busy, setBusy] = useState(false);
  async function confirm() {
    setBusy(true);
    try {
      await extSend(`/staff/courses/${courseId}/fees/${fee.id}/paid`, "POST", { method: how });
      await queryClient.invalidateQueries({ queryKey: rosterKey(courseId) });
      toast({ tone: "success", title: t("ext.pay.marked") });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: t("ext.pay.markFailed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open onClose={onClose} size="sm" title={t("ext.pay.markPaid")} subtitle={`${who.first_name} ${who.last_name} · ${period(fee.period)} · ${fmt.euro(fee.amount_cents)}`}
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button onClick={confirm} loading={busy}>{t("ext.pay.confirm")}</Button></>}>
      <div className="grid grid-cols-2 gap-2" role="radiogroup">
        {[...EXT_PAY_METHODS].sort((a, b) => (a === "CASH" ? -1 : b === "CASH" ? 1 : 0)).map((m) => (
          <button key={m} type="button" role="radio" aria-checked={how === m} onClick={() => setHow(m)}
            className={cn("cursor-pointer rounded-2xl p-3 text-sm font-semibold ring-1 transition-colors",
              how === m ? "bg-brand-50 text-brand-800 ring-2 ring-brand-400" : "bg-white text-ink-800 ring-ink-200 hover:ring-ink-300")}>
            {t(`ext.method.${m}`)}
          </button>
        ))}
      </div>
    </Modal>
  );
}

function RejectModal({ courseId, proof, onClose }: { courseId: string; proof: ExtStaffProof; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  async function confirm() {
    setBusy(true);
    try {
      await extSend(`/staff/courses/${courseId}/proofs/${proof.id}/reject`, "POST", { reason: reason.trim() });
      await queryClient.invalidateQueries({ queryKey: rosterKey(courseId) });
      toast({ tone: "success", title: t("ext.pay.rejected") });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: t("ext.pay.rejectFailed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open onClose={onClose} size="sm" title={t("ext.pay.rejectTitle")} subtitle={`${proof.parent_name ?? ""} · ${fmt.euro(proof.amount_cents)}`}
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button variant="danger" onClick={confirm} loading={busy} disabled={reason.trim().length < 3}>{t("ext.pay.reject")}</Button></>}>
      <Field label={t("ext.pay.rejectReason")} hint={t("ext.pay.rejectHint")} htmlFor="ext-reject">
        <Textarea id="ext-reject" maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
    </Modal>
  );
}

// --- Avisos ----------------------------------------------------------------------------------------

function Notices({ roster }: { roster: ExtRoster }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  async function post() {
    setBusy(true);
    try {
      await extSend(`/staff/courses/${roster.course.id}/notices`, "POST", { title: title.trim(), body: body.trim() || null });
      await queryClient.invalidateQueries({ queryKey: rosterKey(roster.course.id) });
      setTitle("");
      setBody("");
      toast({ tone: "success", title: t("ext.notice.posted"), text: t("ext.notice.postedText") });
    } catch (e) {
      toast({ tone: "error", title: t("ext.notice.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-6">
      <PageHeader title={t("ext.school.navNotices")} subtitle={t("ext.notice.subtitle")} />
      <Card>
        <div className="space-y-3">
          <Field label={t("ext.notice.title")} htmlFor="ext-n-title">
            <Input id="ext-n-title" maxLength={200} placeholder={t("ext.notice.titlePlaceholder")} value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label={t("ext.notice.body")} htmlFor="ext-n-body">
            <Textarea id="ext-n-body" maxLength={4000} value={body} onChange={(e) => setBody(e.target.value)} />
          </Field>
          <Button onClick={post} loading={busy} disabled={title.trim().length < 2}>📣 {t("ext.notice.post")}</Button>
        </div>
      </Card>
      {roster.notices.length === 0 ? <p className="px-1 text-sm text-ink-500">{t("ext.notice.none")}</p> : (
        <ul className="space-y-2">
          {roster.notices.map((n) => (
            <li key={n.id} className="rounded-2xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
              <div className="flex items-start justify-between gap-3">
                <p className="font-semibold text-ink-900">{n.title}</p>
                <span className="shrink-0 text-xs text-ink-500">{fmt.shortDate(n.created_at)}</span>
              </div>
              {n.body && <p className="mt-1 whitespace-pre-line text-sm text-ink-700">{n.body}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --- Entrada / Saída e ganhos del treinador --------------------------------------------------------

function Clock({ course, courses }: { course: ExtStaffCourse; courses: ExtStaffCourse[] }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["ext", "clock"], queryFn: () => extGet<ExtClock>("/staff/clock") });
  const names = new Map(courses.map((c) => [c.id, c.school_name]));
  const time = (iso: string) => new Date(iso).toLocaleTimeString(fmt.tag, { hour: "2-digit", minute: "2-digit" });
  const open = data?.open ?? null;

  async function act(action: "in" | "out") {
    setBusy(true);
    try {
      const fresh = await extSend<ExtClock>(`/staff/courses/${course.id}/clock`, "POST", { action });
      queryClient.setQueryData(["ext", "clock"], fresh);
      toast({ tone: "success", title: t(action === "in" ? "ext.clock.inDone" : "ext.clock.outDone") });
    } catch (e) {
      toast({ tone: "error", title: t("ext.clock.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t("ext.school.navClock")} subtitle={t("ext.clock.subtitle")} />
      {isLoading ? <Skeleton className="h-40" /> : (
        <Card className="text-center">
          <p className="text-sm text-ink-500">{open ? t("ext.clock.openSince", { time: time(open.started_at), school: names.get(open.course_id) ?? "" }) : t("ext.clock.closed")}</p>
          <Button size="xl" variant={open ? "dark" : "primary"} className="mt-4 w-full sm:w-auto" loading={busy} onClick={() => act(open ? "out" : "in")}>
            {open ? `⏹ ${t("ext.clock.out")}` : `▶ ${t("ext.clock.in")}`}
          </Button>
        </Card>
      )}
      {(data?.sessions ?? []).length > 0 && (
        <Card>
          <CardHeader title={t("ext.clock.last")} />
          <ul className="divide-y divide-ink-100">
            {data?.sessions.map((s) => (
              <li key={s.started_at} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <span className="min-w-0">
                  <span className="block font-semibold text-ink-900">{fmt.shortDate(s.started_at)} · {names.get(s.course_id) ?? ""}</span>
                  <span className="block text-xs text-ink-500">{time(s.started_at)}–{s.ended_at ? time(s.ended_at) : "…"}</span>
                </span>
                <span className="font-semibold tabular-nums text-ink-900">{s.minutes != null ? t("ext.clock.minutes", { n: s.minutes }) : t("ext.clock.running")}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function Earnings() {
  const { t } = useI18n();
  const years = yearOptions();
  const [year, setYear] = useState(years[0]);
  const { data, isLoading, error } = useQuery({ queryKey: ["ext", "earnings", year], queryFn: () => extGet<ExtAccounts>(`/staff/earnings?year=${year}`) });
  return (
    <div className="space-y-6">
      <PageHeader title={t("ext.school.navEarnings")} subtitle={t("ext.acc.coachSubtitle")}
        actions={<Select aria-label={t("ext.acc.year")} value={year} onChange={(e) => setYear(Number(e.target.value))} className="w-auto">{years.map((y) => <option key={y} value={y}>{y}</option>)}</Select>} />
      {isLoading ? <Skeleton className="h-48" /> : error || !data ? <EmptyState title={t("ext.school.loadFailed")} text={(error as Error | null)?.message} /> : <ExtAccountsTables data={data} coach />}
    </div>
  );
}
