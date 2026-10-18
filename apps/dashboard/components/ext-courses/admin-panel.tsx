"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExtAccountsTables, yearOptions } from "@/components/ext-courses/accounts";
import { SchoolBadge, useGroupLine, useWeekdayName } from "@/components/ext-courses/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { extGet, extSend, type ExtAccounts, type ExtAdminCourse, type ExtGroup, type ExtStaffMember } from "@/lib/ext-courses";
import { useI18n } from "@/lib/i18n/provider";

const ADMIN_KEY = ["ext", "admin", "courses"];
// L'anno scolastico da settembre ad agosto: i mesi in quest'ordine.
const SCHOOL_MONTHS = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8];

/** "Cursos externos" nella console (clubs.manage): i corsi nelle scuole,
 *  separati dai club — scuola, gruppi, persone (treinador con la sua
 *  percentuale, segreteria della scuola) e la contabilità a parte. Ogni
 *  importo dei conti arriva dal server. */
export function ExtCoursesAdminPanel() {
  const { t } = useI18n();
  const [editing, setEditing] = useState<ExtAdminCourse | "new" | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const { data, isLoading, error } = useQuery({ queryKey: ADMIN_KEY, queryFn: () => extGet<ExtAdminCourse[]>("/admin/courses") });
  const courses = data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="JudoArteVida" title={t("ext.admin.title")} subtitle={t("ext.admin.subtitle")}
        actions={<Button onClick={() => setEditing("new")}>＋ {t("ext.admin.new")}</Button>} />
      {isLoading ? <Skeleton className="h-40" /> : error ? (
        <EmptyState title={t("ext.school.loadFailed")} text={(error as Error).message} />
      ) : courses.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🎒</span>} title={t("ext.admin.empty")} text={t("ext.admin.emptyText")}
          action={<Button onClick={() => setEditing("new")}>{t("ext.admin.new")}</Button>} />
      ) : (
        <div className="space-y-3">
          {courses.map((c) => (
            <CourseRow key={c.id} course={c} open={openId === c.id} onToggle={() => setOpenId(openId === c.id ? null : c.id)} onEdit={() => setEditing(c)} />
          ))}
        </div>
      )}
      <AccountsCard courses={courses} />
      {editing && <CourseFormModal course={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function CourseRow({ course, open, onToggle, onEdit }: { course: ExtAdminCourse; open: boolean; onToggle: () => void; onEdit: () => void }) {
  const { t, fmt } = useI18n();
  const coach = course.staff.find((s) => s.role === "COACH");
  return (
    <Card padded={false}>
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full cursor-pointer items-center gap-4 p-5 text-left">
        <SchoolBadge course={course} />
        <span className="min-w-0 flex-1">
          <span className="block font-display text-lg leading-tight text-ink-900">{course.school_name}</span>
          <span className="block text-sm text-ink-500">{[course.name, course.school_city].filter(Boolean).join(" · ")}</span>
          <span className="mt-1.5 flex flex-wrap gap-1.5">
            <Badge tone={course.active ? "success" : "neutral"} dot>{t(course.active ? "ext.admin.active" : "ext.admin.inactive")}</Badge>
            <Badge tone={course.published ? "brand" : "neutral"}>{t(course.published ? "ext.admin.published" : "ext.admin.hidden")}</Badge>
            <Badge>🧒 {course.participants}</Badge>
            {course.due_cents > 0 && <Badge tone="warning">{t("ext.admin.dueBadge", { amount: fmt.euro(course.due_cents) })}</Badge>}
            {coach && <Badge tone="info">🧑‍🏫 {coach.name ?? coach.email}</Badge>}
          </span>
        </span>
        <span className={cn("text-xl text-ink-400 transition-transform", open && "rotate-90")} aria-hidden="true">›</span>
      </button>
      {open && (
        <div className="space-y-6 border-t border-ink-100 p-5">
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={onEdit}>✏️ {t("ext.admin.edit")}</Button>
            <LogoButtons course={course} />
            <Link href={`/escola?curso=${course.id}`} className="inline-flex h-10 items-center gap-2 rounded-xl bg-ink-900 px-4 text-sm font-semibold text-white hover:bg-ink-800">
              🏫 {t("ext.admin.openAsSchool")}
            </Link>
            {course.published && (
              <Link href={`/cursos-externos/${course.id}`} target="_blank" className="inline-flex h-10 items-center rounded-xl px-4 text-sm font-semibold text-brand-700 hover:bg-brand-50">
                ↗ {t("ext.admin.publicPage")}
              </Link>
            )}
          </div>
          <GroupsEditor course={course} />
          <StaffEditor course={course} />
        </div>
      )}
    </Card>
  );
}

function LogoButtons({ course }: { course: ExtAdminCourse }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  async function send(file: File | null) {
    setBusy(true);
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      await extSend(`/admin/courses/${course.id}/logo`, "POST", form);
      await queryClient.invalidateQueries({ queryKey: ADMIN_KEY });
      toast({ tone: "success", title: t(file ? "ext.admin.logoSaved" : "ext.admin.logoRemoved") });
    } catch (e) {
      toast({ tone: "error", title: t("ext.admin.saveFailed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button variant="secondary" loading={busy} onClick={() => input.current?.click()}>🖼️ {t(course.school_logo_url ? "ext.admin.logoChange" : "ext.admin.logoAdd")}</Button>
      {course.school_logo_url && <Button variant="ghost" disabled={busy} onClick={() => void send(null)}>{t("ext.admin.logoRemove")}</Button>}
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void send(f); }} />
    </>
  );
}

// --- Il corso ----------------------------------------------------------------------------------------

function defaultDates() {
  const now = new Date();
  const y = now.getMonth() >= 7 ? now.getFullYear() : now.getFullYear() - 1;
  return { starts_on: `${y}-10-01`, ends_on: `${y + 1}-07-31` };
}

function CourseFormModal({ course, onClose }: { course: ExtAdminCourse | null; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(() => ({
    name: course?.name ?? "",
    school_name: course?.school_name ?? "",
    school_address: course?.school_address ?? "",
    school_city: course?.school_city ?? "",
    description: course?.description ?? "",
    // In euro come li scrive chi compila: in centesimi solo all'invio.
    fee: course ? String(course.monthly_fee_cents / 100).replace(".", ",") : "25",
    billing_months: course?.billing_months ?? [10, 11, 12, 1, 2, 3, 4, 5, 6, 7],
    due_day: String(course?.due_day ?? 8),
    ...(course ? { starts_on: course.starts_on, ends_on: course.ends_on } : defaultDates()),
    active: course?.active ?? true,
    published: course?.published ?? false,
    public_coach_name: course?.public_coach_name ?? "",
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm((f) => ({ ...f, [key]: value }));
  const toggleMonth = (m: number) => set("billing_months", form.billing_months.includes(m) ? form.billing_months.filter((x) => x !== m) : [...form.billing_months, m]);

  async function submit() {
    setError(null);
    const euros = Number(form.fee.replace(",", ".").trim());
    if (!Number.isFinite(euros) || euros < 0) {
      setError(t("ext.admin.feeInvalid"));
      return;
    }
    const body = {
      name: form.name.trim(), school_name: form.school_name.trim(), school_address: form.school_address.trim() || null,
      school_city: form.school_city.trim() || null, description: form.description.trim() || null,
      monthly_fee_cents: Math.round(euros * 100), billing_months: form.billing_months, due_day: Number(form.due_day),
      starts_on: form.starts_on, ends_on: form.ends_on, active: form.active, published: form.published,
      public_coach_name: form.public_coach_name.trim() || null,
    };
    setBusy(true);
    try {
      if (course) await extSend(`/admin/courses/${course.id}`, "PATCH", body);
      else await extSend("/admin/courses", "POST", body);
      await queryClient.invalidateQueries({ queryKey: ADMIN_KEY });
      toast({ tone: "success", title: t("ext.admin.saved") });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} size="lg" title={course ? t("ext.admin.edit") : t("ext.admin.new")}
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button onClick={submit} loading={busy} disabled={!form.name.trim() || !form.school_name.trim() || form.billing_months.length === 0}>{t("ext.admin.save")}</Button></>}>
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("ext.admin.schoolName")} htmlFor="xa-school"><Input id="xa-school" maxLength={200} value={form.school_name} onChange={(e) => set("school_name", e.target.value)} /></Field>
          <Field label={t("ext.admin.courseName")} htmlFor="xa-name"><Input id="xa-name" maxLength={150} value={form.name} onChange={(e) => set("name", e.target.value)} /></Field>
          <Field label={t("ext.admin.address")} htmlFor="xa-addr"><Input id="xa-addr" maxLength={300} value={form.school_address} onChange={(e) => set("school_address", e.target.value)} /></Field>
          <Field label={t("ext.admin.city")} htmlFor="xa-city"><Input id="xa-city" maxLength={120} value={form.school_city} onChange={(e) => set("school_city", e.target.value)} /></Field>
        </div>
        <Field label={t("ext.admin.description")} htmlFor="xa-desc"><Textarea id="xa-desc" maxLength={4000} value={form.description} onChange={(e) => set("description", e.target.value)} /></Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("ext.admin.fee")} htmlFor="xa-fee" hint={t("ext.admin.feeHint")}><Input id="xa-fee" inputMode="decimal" value={form.fee} onChange={(e) => set("fee", e.target.value)} /></Field>
          <Field label={t("ext.admin.dueDay")} htmlFor="xa-due"><Input id="xa-due" type="number" min={1} max={28} value={form.due_day} onChange={(e) => set("due_day", e.target.value)} /></Field>
          <Field label={t("ext.admin.coachName")} htmlFor="xa-coach" hint={t("ext.admin.coachNameHint")}><Input id="xa-coach" maxLength={80} value={form.public_coach_name} onChange={(e) => set("public_coach_name", e.target.value)} /></Field>
          <Field label={t("ext.admin.startsOn")} htmlFor="xa-start"><Input id="xa-start" type="date" value={form.starts_on} onChange={(e) => set("starts_on", e.target.value)} /></Field>
          <Field label={t("ext.admin.endsOn")} htmlFor="xa-end"><Input id="xa-end" type="date" value={form.ends_on} onChange={(e) => set("ends_on", e.target.value)} /></Field>
        </div>
        <fieldset>
          <legend className="mb-1.5 text-sm font-semibold text-ink-800">{t("ext.admin.months")}</legend>
          <div className="flex flex-wrap gap-1.5">
            {SCHOOL_MONTHS.map((m) => {
              const on = form.billing_months.includes(m);
              return (
                <button key={m} type="button" aria-pressed={on} onClick={() => toggleMonth(m)}
                  className={cn("cursor-pointer rounded-full px-3 py-1.5 text-xs font-semibold capitalize ring-1 transition-colors",
                    on ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-ink-600 ring-ink-200 hover:ring-ink-300")}>
                  {fmt.date(new Date(2024, m - 1, 1), { month: "short" })}
                </button>
              );
            })}
          </div>
        </fieldset>
        <div className="flex flex-wrap gap-5 text-sm text-ink-800">
          <label className="flex cursor-pointer items-center gap-2"><input type="checkbox" className="h-5 w-5 accent-brand-600" checked={form.active} onChange={(e) => set("active", e.target.checked)} />{t("ext.admin.activeLabel")}</label>
          <label className="flex cursor-pointer items-center gap-2"><input type="checkbox" className="h-5 w-5 accent-brand-600" checked={form.published} onChange={(e) => set("published", e.target.checked)} />{t("ext.admin.publishedLabel")}</label>
        </div>
        {error && <p role="alert" className="rounded-xl bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700 ring-1 ring-rose-200">{error}</p>}
      </div>
    </Modal>
  );
}

// --- I gruppi ----------------------------------------------------------------------------------------

type GroupDraft = { name: string; min_age: string; max_age: string; weekday: string; starts_at: string; ends_at: string; active: boolean };
const toDraft = (g?: ExtGroup): GroupDraft => ({
  name: g?.name ?? "", min_age: g?.min_age != null ? String(g.min_age) : "", max_age: g?.max_age != null ? String(g.max_age) : "",
  weekday: String(g?.weekday ?? 0), starts_at: g?.starts_at ?? "15:30", ends_at: g?.ends_at ?? "16:00", active: g?.active ?? true,
});

function GroupsEditor({ course }: { course: ExtAdminCourse }) {
  const { t } = useI18n();
  const groupLine = useGroupLine();
  const [editing, setEditing] = useState<string | "new" | null>(null);
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-bold uppercase tracking-wide text-ink-500">{t("ext.admin.groups")}</h4>
        {editing !== "new" && <Button size="sm" variant="secondary" onClick={() => setEditing("new")}>＋ {t("ext.admin.addGroup")}</Button>}
      </div>
      {course.groups.length === 0 && editing !== "new" && <p className="text-sm text-ink-500">{t("ext.admin.noGroups")}</p>}
      <ul className="space-y-2">
        {course.groups.map((g) => (
          <li key={g.id}>
            {editing === g.id ? <GroupForm courseId={course.id} group={g} onDone={() => setEditing(null)} /> : (
              <div className={cn("flex items-center justify-between gap-3 rounded-xl bg-ink-50 px-3 py-2 text-sm", !g.active && "opacity-60")}>
                <span className="min-w-0"><span className="font-semibold text-ink-900">{g.name}</span> <span className="capitalize text-ink-500">· {groupLine(g)}</span></span>
                <Button size="sm" variant="ghost" onClick={() => setEditing(g.id)}>✏️</Button>
              </div>
            )}
          </li>
        ))}
        {editing === "new" && <li><GroupForm courseId={course.id} onDone={() => setEditing(null)} /></li>}
      </ul>
    </section>
  );
}

function GroupForm({ courseId, group, onDone }: { courseId: string; group?: ExtGroup; onDone: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const weekday = useWeekdayName();
  const [d, setD] = useState<GroupDraft>(() => toDraft(group));
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof GroupDraft>(k: K, v: GroupDraft[K]) => setD((x) => ({ ...x, [k]: v }));
  async function save() {
    setBusy(true);
    try {
      const body = {
        name: d.name.trim(), min_age: d.min_age === "" ? null : Number(d.min_age), max_age: d.max_age === "" ? null : Number(d.max_age),
        weekday: Number(d.weekday), starts_at: d.starts_at, ends_at: d.ends_at, active: d.active,
      };
      if (group) await extSend(`/admin/courses/${courseId}/groups/${group.id}`, "PATCH", body);
      else await extSend(`/admin/courses/${courseId}/groups`, "POST", body);
      await queryClient.invalidateQueries({ queryKey: ADMIN_KEY });
      toast({ tone: "success", title: t("ext.admin.saved") });
      onDone();
    } catch (e) {
      toast({ tone: "error", title: t("ext.admin.saveFailed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-3 rounded-2xl bg-white p-4 ring-1 ring-brand-200">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label={t("ext.admin.groupName")}><Input maxLength={120} value={d.name} onChange={(e) => set("name", e.target.value)} placeholder={t("ext.admin.groupNamePlaceholder")} /></Field>
        <Field label={t("ext.admin.minAge")}><Input type="number" min={0} max={99} value={d.min_age} onChange={(e) => set("min_age", e.target.value)} /></Field>
        <Field label={t("ext.admin.maxAge")}><Input type="number" min={0} max={99} value={d.max_age} onChange={(e) => set("max_age", e.target.value)} /></Field>
        <Field label={t("ext.admin.weekday")}>
          <Select value={d.weekday} onChange={(e) => set("weekday", e.target.value)}>
            {[0, 1, 2, 3, 4, 5, 6].map((w) => <option key={w} value={w}>{weekday(w)}</option>)}
          </Select>
        </Field>
        <Field label={t("ext.admin.startsAt")}><Input type="time" value={d.starts_at} onChange={(e) => set("starts_at", e.target.value)} /></Field>
        <Field label={t("ext.admin.endsAt")}><Input type="time" value={d.ends_at} onChange={(e) => set("ends_at", e.target.value)} /></Field>
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-800"><input type="checkbox" className="h-5 w-5 accent-brand-600" checked={d.active} onChange={(e) => set("active", e.target.checked)} />{t("ext.admin.groupActive")}</label>
      <div className="flex gap-2">
        <Button size="sm" onClick={save} loading={busy} disabled={!d.name.trim()}>{t("ext.admin.save")}</Button>
        <Button size="sm" variant="ghost" onClick={onDone}>{t("common.cancel")}</Button>
      </div>
    </div>
  );
}

// --- Le persone --------------------------------------------------------------------------------------

function StaffEditor({ course }: { course: ExtAdminCourse }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"COACH" | "SCHOOL">("COACH");
  const [share, setShare] = useState("50");
  const [busy, setBusy] = useState(false);
  const [invite, setInvite] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function add() {
    setBusy(true);
    setInvite(null);
    try {
      const res = await extSend<{ staff: ExtStaffMember[]; invite_link: string | null }>(`/admin/courses/${course.id}/staff`, "POST",
        { email: email.trim(), role, share_pct: role === "COACH" && share.trim() ? Number(share.replace(",", ".")) : null });
      await queryClient.invalidateQueries({ queryKey: ADMIN_KEY });
      setInvite(res.invite_link);
      setEmail("");
      toast({ tone: "success", title: t("ext.admin.staffAdded") });
    } catch (e) {
      toast({ tone: "error", title: t("ext.admin.saveFailed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function remove(s: ExtStaffMember) {
    if (!window.confirm(t("ext.admin.staffRemoveConfirm", { name: s.name ?? s.email ?? "" }))) return;
    try {
      await extSend(`/admin/courses/${course.id}/staff/${s.id}`, "DELETE");
      await queryClient.invalidateQueries({ queryKey: ADMIN_KEY });
    } catch (e) {
      toast({ tone: "error", title: t("ext.admin.saveFailed"), text: (e as Error).message });
    }
  }

  return (
    <section className="space-y-2">
      <h4 className="text-sm font-bold uppercase tracking-wide text-ink-500">{t("ext.admin.staff")}</h4>
      {course.staff.length === 0 ? <p className="text-sm text-ink-500">{t("ext.admin.noStaff")}</p> : (
        <ul className="space-y-1.5">
          {course.staff.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-3 rounded-xl bg-ink-50 px-3 py-2 text-sm">
              <span className="min-w-0">
                <span className="block font-semibold text-ink-900">{s.name ?? s.email}</span>
                <span className="block truncate text-xs text-ink-500">
                  {t(s.role === "COACH" ? "ext.admin.roleCoach" : "ext.admin.roleSchool")}
                  {s.role === "COACH" && s.share_pct != null ? ` · ${Number(s.share_pct)}%` : ""} · {s.email}
                </span>
              </span>
              <Button size="sm" variant="ghost" onClick={() => void remove(s)}>{t("ext.admin.remove")}</Button>
            </li>
          ))}
        </ul>
      )}
      <div className="grid gap-2 rounded-2xl bg-white p-3 ring-1 ring-ink-100 sm:grid-cols-[1fr_auto_auto_auto] sm:items-end">
        <Field label={t("ext.admin.staffEmail")}><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label={t("ext.admin.staffRole")}>
          <Select value={role} onChange={(e) => setRole(e.target.value as "COACH" | "SCHOOL")}>
            <option value="COACH">{t("ext.admin.roleCoach")}</option>
            <option value="SCHOOL">{t("ext.admin.roleSchool")}</option>
          </Select>
        </Field>
        {role === "COACH" && <Field label={t("ext.admin.share")}><Input inputMode="decimal" className="w-24" value={share} onChange={(e) => setShare(e.target.value)} /></Field>}
        <Button onClick={add} loading={busy} disabled={!email.includes("@")}>{t("ext.admin.addStaff")}</Button>
      </div>
      <p className="text-xs text-ink-500">{t("ext.admin.staffHint")}</p>
      {invite && (
        <div className="space-y-2 rounded-2xl bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200">
          <p>{t("ext.admin.inviteLink")}</p>
          <div className="flex gap-2">
            <Input readOnly value={invite} onFocus={(e) => e.target.select()} />
            <Button variant="secondary" onClick={async () => { await navigator.clipboard.writeText(invite).catch(() => undefined); setCopied(true); }}>
              {copied ? t("hold.copied") : t("hold.copy")}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}

// --- La contabilità ----------------------------------------------------------------------------------

function AccountsCard({ courses }: { courses: ExtAdminCourse[] }) {
  const { t } = useI18n();
  const years = yearOptions();
  const [year, setYear] = useState(years[0]);
  const [courseId, setCourseId] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["ext", "admin", "accounts", year, courseId],
    queryFn: () => extGet<ExtAccounts>(`/admin/accounts?year=${year}${courseId ? `&course_id=${courseId}` : ""}`),
  });
  return (
    <Card>
      <CardHeader title={`📒 ${t("ext.acc.title")}`} subtitle={t("ext.acc.subtitle")}
        action={
          <div className="flex flex-wrap gap-2">
            {courses.length > 1 && (
              <Select aria-label={t("ext.acc.course")} value={courseId} onChange={(e) => setCourseId(e.target.value)} className="w-auto">
                <option value="">{t("ext.acc.allCourses")}</option>
                {courses.map((c) => <option key={c.id} value={c.id}>{c.school_name}</option>)}
              </Select>
            )}
            <Select aria-label={t("ext.acc.year")} value={year} onChange={(e) => setYear(Number(e.target.value))} className="w-auto">
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </Select>
          </div>
        } />
      {isLoading ? <Skeleton className="h-40" /> : error || !data ? <p className="text-sm text-rose-700">{(error as Error | null)?.message}</p> : <ExtAccountsTables data={data} />}
    </Card>
  );
}
