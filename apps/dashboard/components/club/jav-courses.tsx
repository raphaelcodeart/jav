"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, FeeStatusPill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { StatTile } from "@/components/ui/stat-tile";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { useCurrentClub } from "@/components/club/current-club";
import { useI18n } from "@/lib/i18n/provider";
import {
  clubGet,
  clubSend,
  kindFeatures,
  type AdminAthlete,
  type CoachEarnings,
  type Course,
  type CourseFigures,
  type CoursesReport,
  type Fee,
} from "@/lib/club";

/** I corsi JAV nelle scuole (docs/club-portal.md, "Cursos JAV"): l'unità
 *  è una sola, i corsi sono tanti, ognuno in una scuola e amministrato per
 *  conto suo. Qui la gestione corso per corso (segreteria dell'unità e
 *  superadmin), i guadagni del treinador e il passaggio di una famiglia a un
 *  club. Ogni importo arriva calcolato dal server: qui si sceglie solo il
 *  mese da guardare. */

const A = (path: string) => `/admin${path}`;

/** Se il club su cui si lavora è l'unità dei corsi JAV, e che cosa ha. */
export function useClubFeatures() {
  const { data: club } = useCurrentClub();
  return kindFeatures(club?.kind);
}

/** "Seg", "Ter"... dalla lingua di chi legge: il 1° gennaio 2024 era lunedì,
 *  e 0 è lunedì anche per l'API (date.weekday()). */
function useWeekday() {
  const { fmt } = useI18n();
  return (weekday: number, style: "short" | "long" = "short") =>
    fmt.date(new Date(2024, 0, 1 + weekday), { weekday: style });
}

function pctLabel(value: string | number | null | undefined): string {
  return value == null ? "—" : `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
}

function useRun() {
  const toast = useToast();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  return async function run(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn();
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: ok });
      return true;
    } catch (e) {
      toast({ tone: "error", title: t("common.failed"), text: (e as Error).message });
      return false;
    }
  };
}

// --- La gestione dei corsi ------------------------------------------------------------------------

/** I corsi dell'unità, ognuno con il suo cruscotto del mese: iscritti,
 *  presenze, incassato, parte del treinador, parte di JAV, debiti. */
export function CoursesManager() {
  const { t, fmt } = useI18n();
  const [period, setPeriod] = useState(() => new Date().toISOString().slice(0, 7));
  const { data: report, isLoading } = useQuery({
    queryKey: ["club", "admin", "courses-report", period],
    queryFn: () => clubGet<CoursesReport>(A(`/courses-report?period=${period}`)),
  });
  const { data: courses } = useQuery({
    queryKey: ["club", "admin", "courses", "all"],
    queryFn: () => clubGet<Course[]>(A("/courses?include_inactive=true")),
  });
  const [editing, setEditing] = useState<Course | "new" | null>(null);
  const [athletesOf, setAthletesOf] = useState<CourseFigures | null>(null);
  const [feesOf, setFeesOf] = useState<CourseFigures | null>(null);
  const byId = new Map((courses ?? []).map((c) => [c.id, c]));
  const totals = report?.totals;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-sm text-ink-500 max-w-2xl">{t("javCourses.intro")}</p>
        <div className="flex items-end gap-3">
          <Field label={t("javCourses.month")} htmlFor="jc-period">
            <Input id="jc-period" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} className="w-44" />
          </Field>
          <Button onClick={() => setEditing("new")} icon={<span>＋</span>}>{t("javCourses.new")}</Button>
        </div>
      </div>
      {totals && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatTile label={t("javCourses.income")} value={totals.income_cents} format={(n) => fmt.euro(n)} icon={<span>💶</span>} />
          <StatTile label={t("javCourses.coachShare")} value={totals.coach_share_cents} format={(n) => fmt.euro(n)} accent="accent" icon={<span>🥋</span>} />
          <StatTile label={t("javCourses.javShare")} value={totals.jav_share_cents} format={(n) => fmt.euro(n)} accent="success" icon={<span>🏫</span>} />
          <StatTile label={t("javCourses.debts")} value={totals.debt_cents} format={(n) => fmt.euro(n)} accent="ink" icon={<span>⏳</span>}
            hint={t("javCourses.pendingHint", { amount: fmt.euro(totals.pending_cents) })} />
        </div>
      )}
      {isLoading ? <Skeleton className="h-64" /> : (report?.courses ?? []).length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🏫</span>} title={t("javCourses.empty")} text={t("javCourses.emptyText")}
          action={<Button onClick={() => setEditing("new")}>{t("javCourses.new")}</Button>} />
      ) : (
        <div className="grid lg:grid-cols-2 gap-4">
          {(report?.courses ?? []).map((row) => {
            const course = row.course_id ? byId.get(row.course_id) : undefined;
            return (
              <CourseCard key={row.course_id ?? "none"} row={row} course={course}
                onEdit={course ? () => setEditing(course) : undefined}
                onAthletes={row.course_id ? () => setAthletesOf(row) : undefined}
                onFees={() => setFeesOf(row)} />
            );
          })}
        </div>
      )}
      {editing && <CourseEditor course={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {athletesOf && <CourseAthletesModal row={athletesOf} onClose={() => setAthletesOf(null)} />}
      {feesOf && <CourseFeesModal row={feesOf} onClose={() => setFeesOf(null)} />}
    </div>
  );
}

function CourseCard({ row, course, onEdit, onAthletes, onFees }: {
  row: CourseFigures; course?: Course; onEdit?: () => void; onAthletes?: () => void; onFees: () => void;
}) {
  const { t, fmt } = useI18n();
  const weekday = useWeekday();
  const orphan = row.course_id === null;
  const figures: [string, number][] = [
    [t("javCourses.income"), row.income_cents],
    [t("javCourses.coachShare"), row.coach_share_cents],
    [t("javCourses.javShare"), row.jav_share_cents],
    [t("javCourses.toCollect"), row.pending_cents],
    [t("javCourses.debts"), row.debt_cents],
  ];
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      className={`glass-card rounded-3xl p-5 space-y-3 ${orphan ? "ring-2 ring-amber-300" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base text-ink-900">{orphan ? t("javCourses.noCourse") : row.name}</h3>
          {orphan ? (
            <p className="text-sm text-amber-700">{t("javCourses.noCourseText")}</p>
          ) : (
            <p className="text-sm text-ink-500">
              🏫 {[row.venue_name, row.venue_city].filter(Boolean).join(", ") || t("javCourses.noVenue")}
            </p>
          )}
          {!orphan && (
            <p className="text-xs text-ink-500 mt-1">
              {row.coach_name ? t("javCourses.coachLine", { name: row.coach_name, pct: pctLabel(row.coach_share_pct) }) : t("javCourses.noCoach")}
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          {!orphan && (row.published ? <Badge tone="success" dot>{t("javCourses.published")}</Badge> : <Badge tone="neutral">{t("javCourses.notPublished")}</Badge>)}
          {!orphan && !row.active && <Badge tone="warning">{t("javCourses.inactive")}</Badge>}
        </div>
      </div>
      {course && course.slots.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {course.slots.map((s) => (
            <span key={s.id} className="rounded-full bg-brand-50 ring-1 ring-brand-200 px-2.5 py-0.5 text-xs font-semibold text-brand-800">
              {weekday(s.weekday)} {s.starts_at.slice(0, 5)}–{s.ends_at.slice(0, 5)}
            </span>
          ))}
        </div>
      )}
      {!orphan && (
        <p className="text-sm text-ink-700">
          {t("javCourses.athletesAttendances", { athletes: row.athletes, attendances: row.attendances })}
        </p>
      )}
      <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {figures.map(([label, cents]) => (
          <div key={label} className="rounded-2xl bg-ink-50 px-3 py-2">
            <dt className="text-[11px] uppercase tracking-wide text-ink-500">{label}</dt>
            <dd className="font-semibold text-ink-900 tabular-nums">{fmt.euro(cents)}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-wrap gap-2 pt-1">
        {onEdit && <Button size="sm" variant="secondary" onClick={onEdit}>{t("javCourses.edit")}</Button>}
        {onAthletes && <Button size="sm" variant="ghost" onClick={onAthletes}>{t("javCourses.athletes")}</Button>}
        <Button size="sm" variant="ghost" onClick={onFees}>{t("javCourses.fees")}</Button>
      </div>
    </motion.div>
  );
}

interface StaffRow { user_id: string; email: string; role: string }

/** Crea o modifica un corso: la scuola, gli orari, il treinador e la sua
 *  percentuale, il testo per il sito e se compare sul sito. */
function CourseEditor({ course: c, onClose }: { course: Course | null; onClose: () => void }) {
  const { t } = useI18n();
  const weekday = useWeekday();
  const run = useRun();
  const { data: staff } = useQuery({ queryKey: ["club", "admin", "staff"], queryFn: () => clubGet<StaffRow[]>(A("/staff")) });
  const [form, setForm] = useState({
    name: c?.name ?? "",
    venue_name: c?.venue_name ?? "",
    venue_address: c?.venue_address ?? "",
    venue_city: c?.venue_city ?? "",
    level: c?.level ?? "",
    min_age: c?.min_age != null ? String(c.min_age) : "",
    max_age: c?.max_age != null ? String(c.max_age) : "",
    instructor_user_id: c?.instructor_user_id ?? "",
    coach_share_pct: c?.coach_share_pct != null ? String(Number(c.coach_share_pct)) : "50",
    public_coach_name: c?.public_coach_name ?? "",
    public_description: c?.public_description ?? "",
    published: c?.published ?? false,
    active: c?.active ?? true,
  });
  const [slot, setSlot] = useState({ weekday: "0", from: "17:30", to: "18:30" });
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const pct = Number(form.coach_share_pct.replace(",", "."));
  const pctOk = form.coach_share_pct !== "" && pct >= 0 && pct <= 100;

  async function save() {
    setBusy(true);
    const body = {
      name: form.name.trim(), venue_name: form.venue_name || null, venue_address: form.venue_address || null,
      venue_city: form.venue_city || null, level: form.level || null,
      min_age: form.min_age ? Number(form.min_age) : null, max_age: form.max_age ? Number(form.max_age) : null,
      instructor_user_id: form.instructor_user_id || null, coach_share_pct: pct,
      public_coach_name: form.public_coach_name || null, public_description: form.public_description || null,
      published: form.published, active: form.active,
    };
    const ok = await run(
      () => (c ? clubSend(A(`/courses/${c.id}`), "PATCH", body) : clubSend(A("/courses"), "POST", body)),
      c ? t("javCourses.saved") : t("javCourses.created"),
    );
    setBusy(false);
    if (ok) onClose();
  }

  return (
    <Modal open onClose={onClose} size="lg" title={c ? t("javCourses.editTitle") : t("javCourses.newTitle")}
      subtitle={t("javCourses.editSubtitle")}
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button loading={busy} onClick={save} disabled={!form.name.trim() || !pctOk}>{t("common.save")}</Button></>}>
      <div className="space-y-4">
        <Field label={t("javCourses.fieldName")} htmlFor="jc-name">
          <Input id="jc-name" value={form.name} onChange={set("name")} placeholder={t("javCourses.fieldNamePh")} />
        </Field>
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label={t("javCourses.fieldVenue")} htmlFor="jc-venue">
            <Input id="jc-venue" value={form.venue_name} onChange={set("venue_name")} placeholder={t("javCourses.fieldVenuePh")} />
          </Field>
          <Field label={t("javCourses.fieldCity")} htmlFor="jc-city">
            <Input id="jc-city" value={form.venue_city} onChange={set("venue_city")} />
          </Field>
        </div>
        <Field label={t("javCourses.fieldAddress")} htmlFor="jc-address">
          <Input id="jc-address" value={form.venue_address} onChange={set("venue_address")} />
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label={t("javCourses.fieldMinAge")} htmlFor="jc-min"><Input id="jc-min" type="number" value={form.min_age} onChange={set("min_age")} /></Field>
          <Field label={t("javCourses.fieldMaxAge")} htmlFor="jc-max"><Input id="jc-max" type="number" value={form.max_age} onChange={set("max_age")} /></Field>
          <Field label={t("javCourses.fieldLevel")} htmlFor="jc-level"><Input id="jc-level" value={form.level} onChange={set("level")} /></Field>
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label={t("javCourses.fieldCoach")} htmlFor="jc-coach" hint={t("javCourses.fieldCoachHint")}>
            <Select id="jc-coach" value={form.instructor_user_id} onChange={set("instructor_user_id")}>
              <option value="">{t("javCourses.noCoachOption")}</option>
              {(staff ?? []).map((s) => <option key={s.user_id} value={s.user_id}>{s.email}</option>)}
            </Select>
          </Field>
          <Field label={t("javCourses.fieldShare")} htmlFor="jc-share" hint={t("javCourses.fieldShareHint")}>
            <Input id="jc-share" inputMode="decimal" value={form.coach_share_pct} onChange={set("coach_share_pct")} />
          </Field>
        </div>
        <Field label={t("javCourses.fieldPublicCoach")} htmlFor="jc-public-coach" hint={t("javCourses.fieldPublicCoachHint")}>
          <Input id="jc-public-coach" value={form.public_coach_name} onChange={set("public_coach_name")} />
        </Field>
        <Field label={t("javCourses.fieldDescription")} htmlFor="jc-desc" hint={t("javCourses.fieldDescriptionHint")}>
          <Textarea id="jc-desc" value={form.public_description} onChange={set("public_description")} />
        </Field>
        <div className="flex flex-wrap gap-5">
          <label className="flex items-center gap-2 text-sm text-ink-700">
            <input type="checkbox" checked={form.published} onChange={(e) => setForm((f) => ({ ...f, published: e.target.checked }))} className="accent-brand-500 h-4 w-4" />
            {t("javCourses.fieldPublished")}
          </label>
          <label className="flex items-center gap-2 text-sm text-ink-700">
            <input type="checkbox" checked={form.active} onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))} className="accent-brand-500 h-4 w-4" />
            {t("javCourses.fieldActive")}
          </label>
        </div>
        {c ? (
          <div className="rounded-2xl bg-ink-50 p-4 space-y-3">
            <p className="text-sm font-semibold text-ink-900">{t("javCourses.schedule")}</p>
            <div className="flex flex-wrap gap-1.5">
              {c.slots.length === 0 && <p className="text-sm text-ink-500">{t("javCourses.noSlots")}</p>}
              {c.slots.map((s) => (
                <span key={s.id} className="inline-flex items-center gap-1.5 rounded-full bg-white ring-1 ring-brand-200 px-2.5 py-1 text-xs font-semibold text-brand-800">
                  {weekday(s.weekday, "long")} {s.starts_at.slice(0, 5)}–{s.ends_at.slice(0, 5)}
                  <button type="button" aria-label={t("javCourses.removeSlot")} className="text-brand-500 hover:text-brand-800 cursor-pointer"
                    onClick={() => run(() => clubSend(A(`/slots/${s.id}`), "DELETE"), t("javCourses.slotRemoved"))}>✕</button>
                </span>
              ))}
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <Select value={slot.weekday} onChange={(e) => setSlot((x) => ({ ...x, weekday: e.target.value }))} className="w-40" aria-label={t("javCourses.day")}>
                {[0, 1, 2, 3, 4, 5, 6].map((d) => <option key={d} value={d}>{weekday(d, "long")}</option>)}
              </Select>
              <Input type="time" value={slot.from} onChange={(e) => setSlot((x) => ({ ...x, from: e.target.value }))} className="w-28" aria-label={t("javCourses.from")} />
              <Input type="time" value={slot.to} onChange={(e) => setSlot((x) => ({ ...x, to: e.target.value }))} className="w-28" aria-label={t("javCourses.to")} />
              <Button variant="secondary" onClick={() => run(
                () => clubSend(A(`/courses/${c.id}/slots`), "POST", { weekday: Number(slot.weekday), starts_at: slot.from, ends_at: slot.to, room: null }),
                t("javCourses.slotAdded"),
              )}>{t("javCourses.addSlot")}</Button>
            </div>
          </div>
        ) : (
          <p className="text-xs text-ink-500">{t("javCourses.slotsAfterCreate")}</p>
        )}
      </div>
    </Modal>
  );
}

/** Gli iscritti di un corso: chi è, quanto deve; e iscrivere qualcuno
 *  dell'unità che non ha ancora un corso. */
function CourseAthletesModal({ row, onClose }: { row: CourseFigures; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const run = useRun();
  const { data, isLoading } = useQuery({
    queryKey: ["club", "admin", "athletes", "course", row.course_id],
    queryFn: () => clubGet<AdminAthlete[]>(A(`/athletes?status=ACTIVE&course_id=${row.course_id}`)),
  });
  const { data: everyone } = useQuery({
    queryKey: ["club", "admin", "athletes", "ACTIVE-all"],
    queryFn: () => clubGet<AdminAthlete[]>(A("/athletes?status=ACTIVE")),
  });
  const [adding, setAdding] = useState("");
  const enrolled = new Set((data ?? []).map((a) => a.id));
  const others = (everyone ?? []).filter((a) => !enrolled.has(a.id));
  return (
    <Modal open onClose={onClose} size="lg" title={row.name} subtitle={t("javCourses.athletesSubtitle")}>
      <div className="space-y-4">
        {isLoading ? <Skeleton className="h-32" /> : (data ?? []).length === 0 ? <EmptyState title={t("javCourses.noAthletes")} /> : (
          <Table>
            <THead><tr><TH>{t("javCourses.colAthlete")}</TH><TH>{t("javCourses.colFamily")}</TH><TH className="text-right">{t("javCourses.colDue")}</TH><TH /></tr></THead>
            <TBody>
              {(data ?? []).map((a) => (
                <TR key={a.id}>
                  <TD className="font-semibold text-ink-900">{a.first_name} {a.last_name}<p className="text-xs text-ink-500">{t("javCourses.age", { n: a.age })}</p></TD>
                  <TD className="text-xs">{a.guardian_email ?? "—"}</TD>
                  <TD className="text-right">{a.due_cents ? <Badge tone="warning">{fmt.euro(a.due_cents)}</Badge> : "—"}</TD>
                  <TD className="text-right">
                    <Button size="sm" variant="ghost" onClick={() => window.confirm(t("javCourses.unenrolConfirm", { name: a.first_name }))
                      && run(() => clubSend(A(`/courses/${row.course_id}/athletes/${a.id}`), "DELETE"), t("javCourses.unenrolled"))}>
                      {t("javCourses.unenrol")}
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        {others.length > 0 && (
          <div className="flex flex-wrap items-end gap-2 border-t border-ink-100 pt-4">
            <div className="min-w-60 flex-1">
              <Field label={t("javCourses.enrolLabel")} htmlFor="jc-enrol">
                <Select id="jc-enrol" value={adding} onChange={(e) => setAdding(e.target.value)}>
                  <option value="">—</option>
                  {others.map((a) => <option key={a.id} value={a.id}>{a.first_name} {a.last_name}</option>)}
                </Select>
              </Field>
            </div>
            <Button variant="secondary" disabled={!adding} onClick={async () => {
              if (await run(() => clubSend(A(`/courses/${row.course_id}/athletes`), "POST", { athlete_id: adding }), t("javCourses.enrolled"))) setAdding("");
            }}>{t("javCourses.enrol")}</Button>
          </div>
        )}
      </div>
    </Modal>
  );
}

/** Le quote di un corso (o quelle senza corso), con lo stato. Segnare
 *  pagato o condonare resta nella sezione delle quote, con i suoi controlli. */
function CourseFeesModal({ row, onClose }: { row: CourseFigures; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const [status, setStatus] = useState("DUE");
  const course = row.course_id ?? "none";
  const qs = new URLSearchParams({ course, ...(status ? { status } : {}) }).toString();
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "fees", qs], queryFn: () => clubGet<Fee[]>(A(`/fees?${qs}`)) });
  const total = (data ?? []).reduce((s, f) => s + f.amount_cents, 0);
  return (
    <Modal open onClose={onClose} size="lg" title={row.course_id ? row.name : t("javCourses.noCourse")} subtitle={t("javCourses.feesSubtitle")}>
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-48" aria-label={t("javCourses.status")}>
            <option value="DUE">{t("javCourses.statusDue")}</option>
            <option value="PAID">{t("javCourses.statusPaid")}</option>
            <option value="">{t("javCourses.statusAll")}</option>
          </Select>
          <span className="text-sm text-ink-500">{t("javCourses.feesTotal", { n: data?.length ?? 0, amount: fmt.euro(total) })}</span>
        </div>
        {isLoading ? <Skeleton className="h-32" /> : (data ?? []).length === 0 ? <EmptyState title={t("javCourses.noFees")} /> : (
          <Table>
            <THead><tr><TH>{t("javCourses.colAthlete")}</TH><TH>{t("javCourses.colFee")}</TH><TH>{t("javCourses.colStatus")}</TH><TH className="text-right">{t("javCourses.colAmount")}</TH></tr></THead>
            <TBody>
              {(data ?? []).map((f) => (
                <TR key={f.id}>
                  <TD className="font-semibold text-ink-900">{f.athlete_name ?? "—"}</TD>
                  <TD>{f.description}<p className="text-xs text-ink-500">{fmt.shortDate(f.due_date)}</p></TD>
                  <TD><FeeStatusPill status={f.status} overdue={f.overdue} /></TD>
                  <TD className="text-right font-semibold">{fmt.euro(f.amount_cents)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </div>
    </Modal>
  );
}

// --- I guadagni del treinador ---------------------------------------------------------------------

/** "Os meus ganhos": mese per mese, corso per corso, incassato × la sua
 *  percentuale; e ciò che è emesso e non ancora pagato. */
export function CoachEarningsPanel() {
  const { t, fmt } = useI18n();
  const [year, setYear] = useState(() => new Date().getFullYear());
  const { data, isLoading } = useQuery({
    queryKey: ["club", "staff", "earnings", year],
    queryFn: () => clubGet<CoachEarnings>(`/staff/earnings?year=${year}`),
  });
  const monthLabel = (month: string) => fmt.date(new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1), { month: "long", year: "numeric" });
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-sm text-ink-500 max-w-2xl">{t("javCourses.earningsIntro")}</p>
        <Field label={t("javCourses.year")} htmlFor="jc-year">
          <Select id="jc-year" value={year} onChange={(e) => setYear(Number(e.target.value))} className="w-32">
            {[0, 1, 2].map((d) => new Date().getFullYear() - d).map((y) => <option key={y} value={y}>{y}</option>)}
          </Select>
        </Field>
      </div>
      {data && (
        <div className="grid sm:grid-cols-2 gap-4">
          <StatTile label={t("javCourses.earnedYear")} value={data.earned_year_cents} format={(n) => fmt.euro(n)} accent="success" icon={<span>💶</span>} />
          <StatTile label={t("javCourses.earnedPending")} value={data.pending_cents} format={(n) => fmt.euro(n)} accent="accent" icon={<span>⏳</span>}
            hint={t("javCourses.earnedPendingHint")} />
        </div>
      )}
      {isLoading ? <Skeleton className="h-48" /> : !data || data.rows.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🏫</span>} title={t("javCourses.earningsEmpty")} text={t("javCourses.earningsEmptyText")} />
      ) : (
        <Table>
          <THead><tr>
            <TH>{t("javCourses.colMonth")}</TH><TH>{t("javCourses.colCourse")}</TH><TH className="text-right">{t("javCourses.colCollected")}</TH>
            <TH className="text-right">{t("javCourses.colShare")}</TH><TH className="text-right">{t("javCourses.colEarned")}</TH><TH className="text-right">{t("javCourses.colPending")}</TH>
          </tr></THead>
          <TBody>
            {data.rows.map((r) => (
              <TR key={`${r.month}-${r.course_id}-${r.coach_share_pct}`}>
                <TD className="capitalize">{monthLabel(r.month)}</TD>
                <TD>{r.course_name || t("javCourses.noCourse")}{r.venue_name && <p className="text-xs text-ink-500">{r.venue_name}</p>}</TD>
                <TD className="text-right tabular-nums">{fmt.euro(r.collected_cents)}</TD>
                <TD className="text-right">{pctLabel(r.coach_share_pct)}</TD>
                <TD className="text-right font-semibold tabular-nums">{fmt.euro(r.earned_cents)}</TD>
                <TD className="text-right text-ink-500 tabular-nums">{r.pending_earning_cents ? fmt.euro(r.pending_earning_cents) : "—"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}

// --- Il passaggio a un club ufficiale -------------------------------------------------------------

/** Una famiglia dei corsi passa a un club: il server rifiuta se ci sono
 *  quote da pagare, e lo dice con le sue parole. */
export function MoveToClubModal({ userId, name, onClose }: { userId: string; name: string; onClose: () => void }) {
  const { t } = useI18n();
  const run = useRun();
  const { data: targets } = useQuery({
    queryKey: ["club", "admin", "move-targets"],
    queryFn: () => clubGet<{ id: string; name: string }[]>(A("/move-targets")),
  });
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  async function move() {
    setBusy(true);
    const ok = await run(() => clubSend(A(`/people/${userId}/move-to-club`), "POST", { target_club_id: target }), t("javCourses.moved"));
    setBusy(false);
    if (ok) onClose();
  }
  return (
    <Modal open onClose={onClose} title={t("javCourses.moveTitle", { name })} subtitle={t("javCourses.moveSubtitle")}
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button loading={busy} disabled={!target} onClick={move}>{t("javCourses.moveConfirm")}</Button></>}>
      <div className="space-y-4">
        <ul className="text-sm text-ink-700 list-disc pl-5 space-y-1">
          <li>{t("javCourses.moveRule1")}</li>
          <li>{t("javCourses.moveRule2")}</li>
          <li>{t("javCourses.moveRule3")}</li>
        </ul>
        <Field label={t("javCourses.moveTarget")} htmlFor="jc-target">
          <Select id="jc-target" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">—</option>
            {(targets ?? []).map((c) => <option key={c.id} value={c.id}>🏯 {c.name}</option>)}
          </Select>
        </Field>
      </div>
    </Modal>
  );
}
