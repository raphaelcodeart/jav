"use client";

import { AnimatePresence, motion } from "motion/react";
import { useDeferredValue, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, type Tone } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend, type Course } from "@/lib/club";
import {
  COACH, NOTE_CATEGORIES, NOTE_ICONS, initials, isoDay,
  type AthleteNote, type AthleteSheet, type CertificateStatus, type LessonNote, type LessonNotesPage, type MyAthlete,
  type NoteCategory,
} from "@/lib/coach";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// Il quaderno del treinador (apps/api/app/domains/club/coach.py): le note
// delle lezioni (corso + giorno: tecniche, situazioni, osservazioni) come una
// linea del tempo da sfogliare e cercare, e «Os meus atletas» con la scheda di
// ognuno e le note personali, che vedono solo lo staff dei suoi corsi e la
// segreteria.

export const CERT_TONE: Record<CertificateStatus, Tone> = {
  VALID: "success", EXPIRING: "warning", EXPIRED: "danger", MISSING: "neutral",
};

function useCourses() {
  return useQuery({ queryKey: ["club", "staff", "courses"], queryFn: () => clubGet<Course[]>("/staff/courses"), staleTime: 60_000 });
}

/** Il quaderno: le lezioni e gli atleti. `manager`: la segreteria, che
 *  può togliere anche le note degli altri. */
export function CoachNotebook({ manager = false, initialTab = "lessons" }: { manager?: boolean; initialTab?: "lessons" | "athletes" }) {
  const { t } = useI18n();
  const [tab, setTab] = useState<string>(initialTab);
  return (
    <div className="space-y-5">
      <Tabs value={tab} onChange={setTab} items={[
        { key: "lessons", label: `📓 ${t("coach2.nb.tabLessons")}` },
        { key: "athletes", label: `🥋 ${manager ? t("clubNav.athletes") : t("coach2.nb.tabAthletes")}` },
      ]} />
      {tab === "lessons" ? <LessonTimeline manager={manager} /> : <MyAthletes manager={manager} />}
    </div>
  );
}

// --- Le note delle lezioni ------------------------------------------------------------------------

function LessonTimeline({ manager }: { manager: boolean }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const { data: courses } = useCourses();
  const [course, setCourse] = useState("");
  const [qInput, setQInput] = useState("");
  const q = useDeferredValue(qInput.trim());
  const [technique, setTechnique] = useState<string | null>(null);
  const [limit, setLimit] = useState(20);
  const [editing, setEditing] = useState<LessonNote | "new" | null>(null);
  const params = new URLSearchParams({ limit: String(limit) });
  if (course) params.set("course_id", course);
  if (q) params.set("q", q);
  if (technique) params.set("technique", technique);
  const { data, isLoading } = useQuery({
    queryKey: ["club", "staff", "lesson-notes", course, q, technique, limit],
    queryFn: () => clubGet<LessonNotesPage>(COACH(`/lesson-notes?${params.toString()}`)),
    placeholderData: (prev) => prev,
  });
  const groups = useMemo(() => {
    const out: { month: string; items: LessonNote[] }[] = [];
    for (const n of data?.items ?? []) {
      const m = n.lesson_date.slice(0, 7);
      const last = out[out.length - 1];
      if (last && last.month === m) last.items.push(n);
      else out.push({ month: m, items: [n] });
    }
    return out;
  }, [data]);

  async function remove(n: LessonNote) {
    if (!window.confirm(t("coach2.nb.deleteConfirm"))) return;
    try {
      await clubSend(COACH(`/lesson-notes/${n.id}`), "DELETE");
      await qc.invalidateQueries({ queryKey: ["club", "staff", "lesson-notes"] });
      void qc.invalidateQueries({ queryKey: ["club", "staff", "coach-home"] });
      toast({ tone: "success", title: t("coach2.nb.deleted") });
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Select value={course} onChange={(e) => setCourse(e.target.value)} className="sm:max-w-xs" aria-label={t("coach2.nb.course")}>
          <option value="">{t("coach2.nb.allCourses")}</option>
          {(courses ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <Input value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder={`🔎 ${t("coach2.nb.search")}`} className="sm:max-w-sm" type="search" />
        <Button className="sm:ml-auto" onClick={() => setEditing("new")}>＋ {t("coach2.nb.newLessonNote")}</Button>
      </div>
      {!!data?.techniques.length && (
        <div>
          <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-500">{t("coach2.nb.mostWorked")}</p>
          <div className="flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:thin]">
            {data.techniques.map((tag) => (
              <button key={tag.name} type="button" onClick={() => setTechnique(technique === tag.name ? null : tag.name)}
                title={t("coach2.nb.lastWorked", { date: fmt.shortDate(tag.last_date) })}
                className={cn("shrink-0 cursor-pointer rounded-full px-3 py-1 text-xs font-semibold ring-1 transition",
                  technique === tag.name ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-ink-700 ring-ink-200 hover:ring-brand-300")}>
                {tag.name} <span className="opacity-70">×{tag.count}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      {isLoading ? <Skeleton className="h-64" /> : !data?.items.length ? (
        <EmptyState icon={<span className="text-3xl">📓</span>} title={q || technique ? t("coach2.nb.noResults") : t("coach2.nb.empty")}
          text={q || technique ? undefined : t("coach2.nb.emptyText")}
          action={!q && !technique ? <Button onClick={() => setEditing("new")}>{t("coach2.nb.firstNote")}</Button> : undefined} />
      ) : (
        <div className="space-y-6">
          {groups.map((g) => (
            <section key={g.month}>
              <h3 className="mb-3 font-display text-lg capitalize text-ink-900">{fmt.date(new Date(`${g.month}-01T12:00:00`), { month: "long", year: "numeric" })}</h3>
              <ol className="relative space-y-3 border-l-2 border-brand-100 pl-5">
                {g.items.map((n, i) => (
                  <motion.li key={n.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }} className="relative">
                    <span className="absolute -left-[31px] top-3 flex h-5 w-5 items-center justify-center rounded-full bg-brand-500 ring-4 ring-white" aria-hidden="true" />
                    <LessonCard note={n} manager={manager} onEdit={() => setEditing(n)} onDelete={() => remove(n)} onTag={setTechnique} />
                  </motion.li>
                ))}
              </ol>
            </section>
          ))}
          {data.total > data.items.length && (
            <Button variant="secondary" onClick={() => setLimit((l) => Math.min(l + 20, 100))} disabled={limit >= 100}>
              {t("coach2.nb.showMore", { n: data.total - data.items.length })}
            </Button>
          )}
        </div>
      )}
      {editing && <LessonNoteModal note={editing === "new" ? null : editing} defaultCourse={course || undefined}
        suggestions={data?.techniques.map((x) => x.name) ?? []} onClose={() => setEditing(null)} />}
    </div>
  );
}

function LessonCard({ note: n, manager, onEdit, onDelete, onTag }: {
  note: LessonNote; manager: boolean; onEdit: () => void; onDelete: () => void; onTag: (tag: string) => void;
}) {
  const { t, fmt } = useI18n();
  const [open, setOpen] = useState(false);
  const long = (n.body ?? "").length > 280;
  return (
    <article className="rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-500">
        <span className="font-semibold text-ink-900">{fmt.date(new Date(`${n.lesson_date}T12:00:00`), { weekday: "short", day: "numeric", month: "short" })}</span>
        <Badge tone="brand">{n.course_name}</Badge>
        <span className="ml-auto">{n.mine ? t("coach2.nb.byMe") : n.author_name}{n.updated_at ? ` · ✎ ${t("coach2.nb.edited")}` : ""}</span>
      </div>
      {n.title && <h4 className="mt-2 text-base leading-snug text-ink-900">{n.title}</h4>}
      {n.techniques.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {n.techniques.map((tag) => (
            <button key={tag} type="button" onClick={() => onTag(tag)} className="cursor-pointer rounded-full bg-accent-50 px-2.5 py-0.5 text-xs font-semibold text-ink-800 ring-1 ring-accent-200 hover:ring-accent-400">🥋 {tag}</button>
          ))}
        </div>
      )}
      {n.body && (
        <p className={cn("mt-2 whitespace-pre-line text-sm leading-relaxed text-ink-700", !open && long && "line-clamp-4")}>{n.body}</p>
      )}
      <div className="mt-2 flex items-center gap-1">
        {long && <Button size="sm" variant="ghost" onClick={() => setOpen((o) => !o)}>{open ? t("coach2.nb.less") : t("coach2.nb.more")}</Button>}
        <span className="ml-auto flex gap-1">
          {n.mine && <Button size="sm" variant="ghost" onClick={onEdit}>✎ {t("coach2.nb.edit")}</Button>}
          {(n.mine || manager) && <Button size="sm" variant="ghost" className="text-rose-600" onClick={onDelete}>{t("coach2.nb.delete")}</Button>}
        </span>
      </div>
    </article>
  );
}

/** Scrivere (o correggere) la nota di una lezione. `defaultCourse` e
 *  `defaultDate` arrivano dalle presenze o dall'Início. */
export function LessonNoteModal({ note, defaultCourse, defaultDate, suggestions = [], onClose }: {
  note: LessonNote | null; defaultCourse?: string; defaultDate?: string; suggestions?: string[]; onClose: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const { data: courses } = useCourses();
  const [course, setCourse] = useState(note?.course_id ?? defaultCourse ?? "");
  const [day, setDay] = useState(note?.lesson_date ?? defaultDate ?? isoDay(new Date()));
  const [title, setTitle] = useState(note?.title ?? "");
  const [tags, setTags] = useState<string[]>(note?.techniques ?? []);
  const [tagInput, setTagInput] = useState("");
  const [body, setBody] = useState(note?.body ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chosenCourse = course || (courses?.length === 1 ? courses[0]!.id : "");

  function addTags(raw: string) {
    const fresh = raw.split(",").map((x) => x.trim()).filter(Boolean);
    if (!fresh.length) return;
    setTags((cur) => {
      const seen = new Set(cur.map((x) => x.toLowerCase()));
      return [...cur, ...fresh.filter((x) => !seen.has(x.toLowerCase()))].slice(0, 30);
    });
    setTagInput("");
  }
  const allTags = tagInput.trim() ? [...tags, ...tagInput.split(",").map((x) => x.trim()).filter(Boolean)] : tags;
  const empty = !title.trim() && !body.trim() && allTags.length === 0;

  async function save() {
    setBusy(true);
    setError(null);
    const payload = { lesson_date: day, title: title.trim() || null, techniques: allTags, body: body.trim() || null };
    try {
      if (note) await clubSend(COACH(`/lesson-notes/${note.id}`), "PATCH", payload);
      else await clubSend(COACH("/lesson-notes"), "POST", { ...payload, course_id: chosenCourse });
      await qc.invalidateQueries({ queryKey: ["club", "staff", "lesson-notes"] });
      void qc.invalidateQueries({ queryKey: ["club", "staff", "coach-home"] });
      toast({ tone: "success", title: t("coach2.nb.saved") });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const quick = suggestions.filter((s) => !tags.some((x) => x.toLowerCase() === s.toLowerCase())).slice(0, 12);
  return (
    <Modal open onClose={onClose} size="lg" title={note ? t("coach2.nb.editLessonNote") : t("coach2.nb.newLessonNote")}
      subtitle={t("coach2.nb.lessonNoteHint")}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button onClick={save} loading={busy} disabled={empty || (!note && !chosenCourse)}>{t("common.save")}</Button>
      </>}>
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("coach2.nb.course")}>
            <Select value={chosenCourse} onChange={(e) => setCourse(e.target.value)} disabled={!!note}>
              <option value="" disabled>{t("coach2.nb.pickCourse")}</option>
              {(courses ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              {note && !(courses ?? []).some((c) => c.id === note.course_id) && <option value={note.course_id}>{note.course_name}</option>}
            </Select>
          </Field>
          <Field label={t("coach2.nb.date")}><Input type="date" value={day} onChange={(e) => setDay(e.target.value)} /></Field>
        </div>
        <Field label={t("coach2.nb.theme")}>
          <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={t("coach2.nb.themePlaceholder")} />
        </Field>
        <Field label={t("coach2.nb.techniques")} hint={t("coach2.nb.techniquesHint")}>
          <div className="space-y-2">
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {tags.map((tag) => (
                  <button key={tag} type="button" onClick={() => setTags((cur) => cur.filter((x) => x !== tag))}
                    className="cursor-pointer rounded-full bg-accent-50 px-2.5 py-0.5 text-xs font-semibold text-ink-800 ring-1 ring-accent-300 hover:bg-rose-50 hover:ring-rose-300"
                    aria-label={t("coach2.nb.removeTag", { tag })}>
                    🥋 {tag} ✕
                  </button>
                ))}
              </div>
            )}
            <Input value={tagInput} onChange={(e) => (e.target.value.includes(",") ? addTags(e.target.value) : setTagInput(e.target.value))}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTags(tagInput); } }}
              onBlur={() => addTags(tagInput)} placeholder={t("coach2.nb.techniquesPlaceholder")} />
            {quick.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {quick.map((s) => (
                  <button key={s} type="button" onClick={() => addTags(s)} className="cursor-pointer rounded-full bg-white px-2.5 py-0.5 text-xs text-ink-600 ring-1 ring-ink-200 hover:ring-brand-300">＋ {s}</button>
                ))}
              </div>
            )}
          </div>
        </Field>
        <Field label={t("coach2.nb.whatHappened")}>
          <Textarea rows={6} value={body} maxLength={8000} onChange={(e) => setBody(e.target.value)} placeholder={t("coach2.nb.bodyPlaceholder")} />
        </Field>
        {error && <p className="rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">{error}</p>}
      </div>
    </Modal>
  );
}

// --- I miei atleti --------------------------------------------------------------------------------

function daysSince(day: string | null, today: Date): number | null {
  if (!day) return null;
  return Math.max(0, Math.round((today.getTime() - new Date(`${day}T12:00:00`).getTime()) / 86_400_000));
}

function Avatar({ first, last, photo, size = "md" }: { first: string; last: string; photo: string | null; size?: "md" | "lg" }) {
  const dims = size === "lg" ? "h-16 w-16 text-xl" : "h-11 w-11 text-sm";
  return photo ? (
    // eslint-disable-next-line @next/next/no-img-element -- foto profilo dell'atleta
    <img src={photo} alt="" className={cn("shrink-0 rounded-full object-cover ring-2 ring-white shadow", dims)} />
  ) : (
    <span className={cn("flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-700 font-display text-white shadow", dims)}>
      {initials(first, last)}
    </span>
  );
}

function MyAthletes({ manager }: { manager: boolean }) {
  const { t } = useI18n();
  const { data, isLoading } = useQuery({ queryKey: ["club", "staff", "my-athletes"], queryFn: () => clubGet<MyAthlete[]>(COACH("/athletes")) });
  const [q, setQ] = useState("");
  const [course, setCourse] = useState("");
  const [sort, setSort] = useState<"name" | "absent" | "notes">("name");
  const [open, setOpen] = useState<string | null>(null);
  const today = new Date();
  const courses = useMemo(() => [...new Set((data ?? []).flatMap((a) => a.courses))].sort(), [data]);
  const needle = q.trim().toLowerCase();
  const rows = (data ?? [])
    .filter((a) => !needle || `${a.first_name} ${a.last_name}`.toLowerCase().includes(needle))
    .filter((a) => !course || a.courses.includes(course))
    .sort((a, b) => sort === "notes" ? b.notes - a.notes
      : sort === "absent" ? (a.last_present ?? "").localeCompare(b.last_present ?? "")
      : `${a.first_name} ${a.last_name}`.localeCompare(`${b.first_name} ${b.last_name}`));

  if (isLoading) return <Skeleton className="h-64" />;
  if (!data?.length) return <EmptyState icon={<span className="text-3xl">🥋</span>} title={t("coach2.ath.empty")} text={t("coach2.ath.emptyText")} />;
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={`🔎 ${t("coach2.ath.search")}`} className="sm:max-w-xs" />
        <Select value={course} onChange={(e) => setCourse(e.target.value)} className="sm:max-w-xs" aria-label={t("coach2.nb.course")}>
          <option value="">{t("coach2.nb.allCourses")}</option>
          {courses.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
        <Select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} className="sm:max-w-[14rem]" aria-label={t("coach2.ath.sort")}>
          <option value="name">{t("coach2.ath.sortName")}</option>
          <option value="absent">{t("coach2.ath.sortAbsent")}</option>
          <option value="notes">{t("coach2.ath.sortNotes")}</option>
        </Select>
      </div>
      <p className="text-xs text-ink-500">{t("coach2.ath.count", { n: rows.length })}</p>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {rows.map((a, i) => {
          const since = daysSince(a.last_present, today);
          return (
            <motion.li key={a.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 12) * 0.02 }}>
              <button type="button" onClick={() => setOpen(a.id)}
                className="flex w-full cursor-pointer items-start gap-3 rounded-3xl bg-white p-4 text-left shadow-soft ring-1 ring-ink-900/5 transition hover:-translate-y-0.5 hover:ring-brand-300">
                <Avatar first={a.first_name} last={a.last_name} photo={a.photo_url} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-ink-900">{a.first_name} {a.last_name}</span>
                  <span className="mt-0.5 flex items-center gap-2">
                    <BeltBadge belt={a.belt} size="sm" showLabel={false} />
                    <span className="truncate text-xs text-ink-500">{a.courses.join(" · ") || "—"}</span>
                  </span>
                  <span className="mt-2 flex flex-wrap gap-1">
                    <Badge tone={a.attended_30d > 0 ? "success" : "neutral"}>📅 {t("coach2.ath.last30", { n: a.attended_30d })}</Badge>
                    {since != null && since >= 21 && <Badge tone="warning">⏳ {t("coach2.ath.daysAway", { n: since })}</Badge>}
                    {a.certificate_status !== "VALID" && <Badge tone={CERT_TONE[a.certificate_status]}>🩺 {t.dyn(`athTable.cert.${a.certificate_status}`, a.certificate_status)}</Badge>}
                    {a.notes > 0 && <Badge tone="info">📝 {a.notes}</Badge>}
                  </span>
                </span>
              </button>
            </motion.li>
          );
        })}
      </ul>
      {open && <AthleteSheetModal athleteId={open} manager={manager} onClose={() => setOpen(null)} />}
    </div>
  );
}

// --- La scheda di un atleta -----------------------------------------------------------------------

/** La scheda dell'atleta per il treinador: presenze degli ultimi 90 giorni,
 *  certificato, e le note personali (con la storia). Si apre dalle presenze
 *  e da «Os meus atletas». */
export function AthleteSheetModal({ athleteId, manager = false, onClose }: { athleteId: string; manager?: boolean; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const { data, isLoading, error } = useQuery({
    queryKey: ["club", "staff", "athlete-sheet", athleteId],
    queryFn: () => clubGet<AthleteSheet>(COACH(`/athletes/${athleteId}`)),
  });
  const today = new Date();
  const age = data ? Math.floor((today.getTime() - new Date(`${data.birth_date}T12:00:00`).getTime()) / (365.25 * 86_400_000)) : null;
  return (
    <Modal open onClose={onClose} size="lg" title={data ? `${data.first_name} ${data.last_name}` : t("coach2.ath.sheet")}>
      {isLoading ? <Skeleton className="h-64" /> : error || !data ? (
        <p className="text-sm text-rose-600">{(error as Error)?.message}</p>
      ) : (
        <div className="space-y-5">
          <div className="flex items-center gap-4">
            <Avatar first={data.first_name} last={data.last_name} photo={data.photo_url} size="lg" />
            <div className="min-w-0 space-y-1">
              <BeltBadge belt={data.belt} size="md" />
              <p className="text-sm text-ink-600">
                {t("coach2.ath.age", { n: age ?? 0 })}{data.weight_kg ? ` · ${data.weight_kg} kg` : ""}{data.adapted_judo ? ` · ♿ ${t("coach2.ath.adapted")}` : ""}
              </p>
              <p className="truncate text-xs text-ink-500">{data.courses.map((c) => c.name).join(" · ")}</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-2xl bg-emerald-50 p-3 ring-1 ring-emerald-100">
              <p className="text-[11px] font-bold uppercase tracking-wider text-emerald-800">{t("coach2.ath.present90")}</p>
              <p className="font-display text-2xl text-emerald-900">{data.present_90d}</p>
            </div>
            <div className="rounded-2xl bg-white p-3 ring-1 ring-ink-100">
              <p className="text-[11px] font-bold uppercase tracking-wider text-ink-500">{t("coach2.ath.certificate")}</p>
              <p className="mt-1"><Badge tone={CERT_TONE[data.certificate_status]}>{t.dyn(`athTable.cert.${data.certificate_status}`, data.certificate_status)}</Badge></p>
              {data.certificate_expires_on && <p className="mt-1 text-xs text-ink-500">{t("coach2.ath.expires", { date: fmt.shortDate(data.certificate_expires_on) })}</p>}
            </div>
          </div>
          <AttendanceDots marks={data.attendance} />
          <AthleteNotes athleteId={data.id} notes={data.notes} manager={manager} />
        </div>
      )}
    </Modal>
  );
}

/** Le presenze degli ultimi 90 giorni come puntini: verde c'era, grigio no. */
function AttendanceDots({ marks }: { marks: AthleteSheet["attendance"] }) {
  const { t, fmt } = useI18n();
  if (!marks.length) return <p className="text-sm text-ink-500">{t("coach2.ath.noAttendance")}</p>;
  const shown = [...marks].reverse();
  return (
    <section>
      <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-ink-500">{t("coach2.ath.attendance")}</p>
      <div className="flex flex-wrap gap-1">
        {shown.map((m) => (
          <span key={`${m.date}-${m.course_id}`} title={`${fmt.shortDate(m.date)} · ${m.course_name}${m.note ? ` · ${m.note}` : ""}`}
            className={cn("h-4 w-4 rounded", m.present ? "bg-emerald-500" : "bg-ink-200", m.note && "ring-2 ring-amber-400")} />
        ))}
      </div>
      {marks.some((m) => m.note) && (
        <ul className="mt-2 space-y-1 text-xs text-amber-800">
          {marks.filter((m) => m.note).slice(0, 4).map((m) => <li key={`n-${m.date}-${m.course_id}`}>📝 {fmt.shortDate(m.date)} · {m.note}</li>)}
        </ul>
      )}
    </section>
  );
}

function AthleteNotes({ athleteId, notes, manager }: { athleteId: string; notes: AthleteNote[]; manager: boolean }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [category, setCategory] = useState<NoteCategory>("TECHNIQUE");
  const [body, setBody] = useState("");
  const [editing, setEditing] = useState<{ id: string; body: string; category: NoteCategory } | null>(null);
  const [filter, setFilter] = useState<NoteCategory | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["club", "staff", "athlete-sheet", athleteId] });
    void qc.invalidateQueries({ queryKey: ["club", "staff", "my-athletes"] });
  };

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try {
      await fn();
      await refresh();
      toast({ tone: "success", title: ok });
      return true;
    } catch (e) {
      toast({ tone: "error", title: (e as Error).message });
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function add() {
    if (await run(() => clubSend(COACH(`/athletes/${athleteId}/notes`), "POST", { category, body: body.trim() }), t("coach2.nb.saved"))) setBody("");
  }
  async function saveEdit() {
    if (!editing) return;
    if (await run(() => clubSend(COACH(`/athlete-notes/${editing.id}`), "PATCH", { category: editing.category, body: editing.body.trim() }), t("coach2.nb.saved"))) setEditing(null);
  }
  async function remove(n: AthleteNote) {
    if (!window.confirm(t("coach2.nb.deleteConfirm"))) return;
    await run(() => clubSend(COACH(`/athlete-notes/${n.id}`), "DELETE"), t("coach2.nb.deleted"));
  }
  const shown = filter ? notes.filter((n) => n.category === filter) : notes;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-base text-ink-900">🔒 {t("coach2.ath.notesTitle")}</h3>
        <span className="text-xs text-ink-500">{t("coach2.ath.privateHint")}</span>
      </div>
      <div className="space-y-2 rounded-2xl bg-ink-50 p-3">
        <CategoryPicker value={category} onChange={setCategory} />
        <Textarea rows={3} value={body} maxLength={8000} onChange={(e) => setBody(e.target.value)} placeholder={t("coach2.ath.notePlaceholder")} />
        <div className="flex justify-end"><Button size="sm" loading={busy} disabled={body.trim().length < 2} onClick={add}>{t("coach2.ath.addNote")}</Button></div>
      </div>
      {notes.length > 1 && (
        <div className="flex flex-wrap gap-1">
          <button type="button" onClick={() => setFilter(null)} className={cn("cursor-pointer rounded-full px-2.5 py-0.5 text-xs ring-1", !filter ? "bg-ink-900 text-white ring-ink-900" : "bg-white ring-ink-200")}>{t("coach2.ath.allNotes")}</button>
          {NOTE_CATEGORIES.filter((c) => notes.some((n) => n.category === c)).map((c) => (
            <button key={c} type="button" onClick={() => setFilter(c)} className={cn("cursor-pointer rounded-full px-2.5 py-0.5 text-xs ring-1", filter === c ? "bg-ink-900 text-white ring-ink-900" : "bg-white ring-ink-200")}>
              {NOTE_ICONS[c]} {t.dyn(`coach2.cat.${c}`, c)}
            </button>
          ))}
        </div>
      )}
      {shown.length === 0 ? <p className="text-sm text-ink-500">{t("coach2.ath.noNotes")}</p> : (
        <ol className="relative space-y-3 border-l-2 border-ink-100 pl-5">
          <AnimatePresence initial={false}>
            {shown.map((n) => (
              <motion.li key={n.id} layout initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="relative">
                <span className="absolute -left-[33px] top-1 flex h-6 w-6 items-center justify-center rounded-full bg-white text-sm ring-2 ring-ink-100" aria-hidden="true">{NOTE_ICONS[n.category]}</span>
                <p className="text-xs text-ink-500">
                  <span className="font-semibold text-ink-800">{t.dyn(`coach2.cat.${n.category}`, n.category)}</span>
                  {" · "}{fmt.date(new Date(n.created_at), { day: "numeric", month: "short", year: "numeric" })}
                  {" · "}{n.mine ? t("coach2.nb.byMe") : n.author_name}{n.updated_at ? ` · ✎ ${t("coach2.nb.edited")}` : ""}
                </p>
                {editing?.id === n.id ? (
                  <div className="mt-1 space-y-2">
                    <CategoryPicker value={editing.category} onChange={(c) => setEditing({ ...editing, category: c })} />
                    <Textarea rows={3} value={editing.body} maxLength={8000} onChange={(e) => setEditing({ ...editing, body: e.target.value })} />
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>{t("common.cancel")}</Button>
                      <Button size="sm" loading={busy} disabled={editing.body.trim().length < 2} onClick={saveEdit}>{t("common.save")}</Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className="mt-0.5 whitespace-pre-line text-sm text-ink-800">{n.body}</p>
                    {(n.mine || manager) && (
                      <div className="mt-1 flex gap-1">
                        {n.mine && <Button size="sm" variant="ghost" onClick={() => setEditing({ id: n.id, body: n.body, category: n.category })}>✎ {t("coach2.nb.edit")}</Button>}
                        <Button size="sm" variant="ghost" className="text-rose-600" onClick={() => remove(n)}>{t("coach2.nb.delete")}</Button>
                      </div>
                    )}
                  </>
                )}
              </motion.li>
            ))}
          </AnimatePresence>
        </ol>
      )}
    </section>
  );
}

function CategoryPicker({ value, onChange }: { value: NoteCategory; onChange: (c: NoteCategory) => void }) {
  const { t } = useI18n();
  return (
    <div className="flex gap-1 overflow-x-auto pb-0.5" role="radiogroup" aria-label={t("coach2.ath.category")}>
      {NOTE_CATEGORIES.map((c) => (
        <button key={c} type="button" role="radio" aria-checked={value === c} onClick={() => onChange(c)}
          className={cn("shrink-0 cursor-pointer rounded-full px-2.5 py-1 text-xs font-semibold ring-1 transition",
            value === c ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-ink-700 ring-ink-200 hover:ring-brand-300")}>
          {NOTE_ICONS[c]} {t.dyn(`coach2.cat.${c}`, c)}
        </button>
      ))}
    </div>
  );
}
