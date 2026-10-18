"use client";

import { motion } from "motion/react";
import { useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { CvCard, DeclaredBadge, PdfActions, SPORT_QUERY, useCvDocuments, useSport } from "@/components/club/coach-cv-common";
import { clubSend } from "@/lib/club";
import {
  CV, EVENT_LEVELS, EVENT_ROLES, EVENT_TYPES, PLACEMENTS, openPresigned, todayIso,
  type CvClub, type EventWrite, type Medal, type SportGrade, type SportItem,
} from "@/lib/coach-cv";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import type { Translator } from "@/lib/i18n/translate";

// Il Curriculum Desportivo: si ricostruisce da solo dallo storico del
// gestionale (gare da atleta, prove da treinador, club e corsi, cinture), e
// il treinador aggiunge quello che il gestionale non sa: le gare di prima, gli
// stage, l'arbitraggio. Le voci scritte a mano restano solo nel suo CV, con
// «Declarado», e non entrano mai in calendario, gare o ranking del club.

const MEDAL_ICON: Record<Medal, string> = { GOLD: "🥇", SILVER: "🥈", BRONZE: "🥉" };
const KIND_ICON: Record<string, string> = {
  COMPETITION: "🏆", STAGE: "🥋", SEMINAR: "🎤", COURSE: "🎓", GRADING: "🎖️", REFEREEING: "🏳️", EDUCATION: "📚", MEETING: "🤝", OTHER: "📌",
};

const kindLabel = (t: Translator, code: string, fallback: string) => t.dyn(`cv.kind.${code}`, fallback);
const roleLabel = (t: Translator, code: string, fallback: string) => t.dyn(`cv.role.${code}`, fallback);
const levelLabel = (t: Translator, code: string, fallback: string) => t.dyn(`club.level.${code}`, fallback);
const placementLabel = (t: Translator, n: number, fallback: string) => t.dyn(`club.placement.${n}`, fallback);

export function CvSport() {
  const { t } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const { data, isLoading, error } = useSport();
  const [editing, setEditing] = useState<SportItem | "new" | null>(null);
  if (isLoading) return <div className="space-y-4"><Skeleton className="h-28" /><Skeleton className="h-64" /></div>;
  if (error || !data) return <EmptyState icon={<span className="text-3xl">🏅</span>} title={t("cv.loadFailed")} text={error?.message} />;

  async function remove(item: SportItem) {
    if (!window.confirm(t("cv.sport.deleteConfirm", { title: item.title }))) return;
    try {
      await clubSend(CV(`/sport/events/${item.id}`), "DELETE");
      await qc.invalidateQueries({ queryKey: SPORT_QUERY });
      toast({ tone: "success", title: t("cv.sport.deleted") });
    } catch (e) {
      toast({ tone: "error", title: t("cv.failed"), text: (e as Error).message });
    }
  }

  // Una graduazione dichiarata è l'evento GRADING con il suo stesso id.
  const gradingItem = (g: SportGrade) =>
    data.items.find((i) => i.source === "MANUAL" && i.kind === "GRADING" && i.id === g.id);
  const medals = data.athlete.medals;
  const actions = { onEdit: (i: SportItem) => setEditing(i), onDelete: (i: SportItem) => void remove(i) };

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3 rounded-3xl bg-sky-50 p-4 text-sm text-sky-900 ring-1 ring-sky-200">
        <span className="text-xl" aria-hidden="true">ℹ️</span>
        <p>{t("cv.sport.note")}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat className="col-span-2 sm:col-span-1 lg:col-span-2" label={t("cv.sport.grade")}>
          {data.belt ? <BeltBadge code={data.belt.code} size="lg" /> : <span className="text-sm text-ink-500">{t("cv.auto.noBelt")}</span>}
        </Stat>
        <Stat label={t("cv.sport.competitions")}><span className="font-display text-3xl text-ink-900">{data.athlete.competitions}</span></Stat>
        {(["GOLD", "SILVER", "BRONZE"] as const).map((m) => (
          <Stat key={m} label={t(`cv.sport.medal.${m}`)}>
            <span className="flex items-center gap-1.5 font-display text-3xl text-ink-900"><span className="text-2xl" aria-hidden="true">{MEDAL_ICON[m]}</span>{medals[m]}</span>
          </Stat>
        ))}
      </div>

      <div className="flex flex-col gap-3 rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5 sm:flex-row sm:items-center sm:justify-between">
        <Button size="lg" onClick={() => setEditing("new")} icon={<span aria-hidden="true">＋</span>}>{t("cv.sport.add")}</Button>
        <PdfActions kind="SPORT" />
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-2">
        <CvCard icon="🥋" title={t("cv.sport.athleteCareer")} hint={t("cv.sport.athleteHint")}>
          {data.athlete.items.length === 0
            ? <p className="text-sm text-ink-500">{data.is_athlete ? t("cv.sport.athleteEmpty") : t("cv.sport.notAthlete")}</p>
            : <Timeline items={data.athlete.items} {...actions} />}
        </CvCard>

        <div className="space-y-5">
          <CvCard icon="📋" title={t("cv.sport.coachCareer")} hint={t("cv.sport.coachHint")}>
            {data.coach.clubs.length > 0 && (
              <ul className="mb-4 space-y-2">
                {data.coach.clubs.map((c) => <ClubPeriod key={c.club_id} club={c} />)}
              </ul>
            )}
            {data.coach.items.length === 0
              ? <p className="text-sm text-ink-500">{t("cv.sport.coachEmpty")}</p>
              : <Timeline items={data.coach.items} {...actions} />}
          </CvCard>

          <CvCard icon="🎖️" title={t("cv.sport.grades")} hint={t("cv.sport.gradesHint")}>
            {data.grades.length === 0 ? <p className="text-sm text-ink-500">{t("cv.sport.gradesEmpty")}</p> : (
              <ol className="relative space-y-3 border-l-2 border-accent-200 pl-5">
                {data.grades.map((g, i) => {
                  const item = g.source === "MANUAL" ? gradingItem(g) : undefined;
                  return (
                    <li key={`${g.label}-${g.date}-${i}`} className="relative">
                      <span className="absolute -left-[29px] top-1.5 h-4 w-4 rounded-full bg-accent-400 ring-4 ring-white" aria-hidden="true" />
                      <div className="flex flex-wrap items-center gap-2">
                        {g.grade ? <BeltBadge code={g.grade} size="sm" /> : <span className="text-sm font-semibold text-ink-900">{g.label}</span>}
                        {g.source === "MANUAL" && <DeclaredBadge />}
                      </div>
                      <p className="text-xs text-ink-500"><DateText iso={g.date} />{g.club ? ` · ${g.club}` : ""}</p>
                      {item && (
                        <div className="mt-1 flex gap-1">
                          <Button size="sm" variant="ghost" onClick={() => setEditing(item)}>✎ {t("cv.edit")}</Button>
                          <Button size="sm" variant="ghost" className="text-rose-600" onClick={() => void remove(item)}>{t("cv.delete")}</Button>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
          </CvCard>
        </div>
      </div>
      {editing && <EventModal item={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function Stat({ label, className, children }: { label: string; className?: string; children: ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className={cn("flex flex-col justify-between gap-2 rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5", className)}>
      <span className="text-[11px] font-bold uppercase tracking-wider text-ink-500">{label}</span>
      {children}
    </motion.div>
  );
}

function DateText({ iso }: { iso: string }) {
  const { fmt } = useI18n();
  return <>{fmt.shortDate(`${iso.slice(0, 10)}T12:00:00`)}</>;
}

function ClubPeriod({ club: c }: { club: CvClub }) {
  const { t, fmt } = useI18n();
  const my = (iso: string | null) => (iso ? fmt.date(new Date(`${iso.slice(0, 10)}T12:00:00`), { month: "short", year: "numeric" }) : "…");
  // Un club ancora attivo arriva fino a oggi; uno chiuso fino all'ultimo turno.
  const end = c.active ? t("cv.sport.today") : my(c.last_activity);
  return (
    <li className="rounded-2xl bg-ink-50/70 p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="font-semibold text-ink-900">🏯 {c.name}</p>
        <span className="shrink-0 text-xs font-semibold text-ink-500">{my(c.since)} – {end}</span>
      </div>
      {c.courses.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {c.courses.map((name) => <span key={name} className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-ink-700 ring-1 ring-ink-200">📚 {name}</span>)}
        </div>
      )}
    </li>
  );
}

function Timeline({ items, onEdit, onDelete }: { items: SportItem[]; onEdit: (i: SportItem) => void; onDelete: (i: SportItem) => void }) {
  return (
    <ol className="relative space-y-3 border-l-2 border-brand-100 pl-5">
      {items.map((item, i) => (
        <motion.li key={`${item.source}-${item.id}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }} className="relative">
          <span className={cn("absolute -left-[29px] top-3 h-4 w-4 rounded-full ring-4 ring-white", item.source === "MANUAL" ? "bg-accent-400" : "bg-brand-500")} aria-hidden="true" />
          <SportItemCard item={item} onEdit={() => onEdit(item)} onDelete={() => onDelete(item)} />
        </motion.li>
      ))}
    </ol>
  );
}

function SportItemCard({ item, onEdit, onDelete }: { item: SportItem; onEdit: () => void; onDelete: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const manual = item.source === "MANUAL";
  const meta = [
    roleLabel(t, item.role, item.role_label),
    item.level ? levelLabel(t, item.level, item.level_label ?? item.level) : null,
    item.category,
  ].filter(Boolean).join(" · ");
  const where = [item.location, item.club].filter(Boolean).join(" · ");

  async function openDocument(id: string) {
    try {
      await openPresigned(CV(`/documents/${id}/url`));
    } catch (e) {
      toast({ tone: "error", title: t("cv.docs.openFailed"), text: (e as Error).message });
    }
  }

  return (
    <article className={cn("rounded-2xl p-3 ring-1", manual ? "bg-accent-50/40 ring-accent-200" : "bg-ink-50/60 ring-ink-100")}>
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-500">
        <span className="font-semibold text-ink-900">
          <DateText iso={item.date} />{item.end_date && item.end_date !== item.date ? <> – <DateText iso={item.end_date} /></> : null}
        </span>
        <Badge tone="neutral"><span aria-hidden="true">{KIND_ICON[item.kind] ?? "📌"}</span> {kindLabel(t, item.kind, item.kind_label)}</Badge>
        {manual && <DeclaredBadge />}
      </div>
      <div className="mt-1 flex items-start gap-2">
        <h4 className="min-w-0 flex-1 text-sm leading-snug text-ink-900 sm:text-base">{item.title}</h4>
        {item.medal ? (
          <span className="shrink-0 text-2xl" title={placementLabel(t, item.placement ?? 0, item.placement_label ?? "")}>{MEDAL_ICON[item.medal]}</span>
        ) : item.placement != null ? (
          <Badge tone="info">{placementLabel(t, item.placement, item.placement_label ?? "")}</Badge>
        ) : null}
      </div>
      {meta && <p className="text-xs text-ink-600">{meta}</p>}
      {where && <p className="text-xs text-ink-500">📍 {where}</p>}
      {item.result && <p className="mt-1 text-sm text-ink-700">{item.result}</p>}
      {item.description && <p className="mt-1 line-clamp-3 whitespace-pre-line text-xs text-ink-600">{item.description}</p>}
      {(manual || item.document_id) && (
        <div className="mt-2 flex flex-wrap gap-1">
          {item.document_id && <Button size="sm" variant="ghost" onClick={() => void openDocument(item.document_id!)}>📎 {t("cv.sport.document")}</Button>}
          {manual && <>
            <Button size="sm" variant="ghost" onClick={onEdit}>✎ {t("cv.edit")}</Button>
            <Button size="sm" variant="ghost" className="text-rose-600" onClick={onDelete}>{t("cv.delete")}</Button>
          </>}
        </div>
      )}
    </article>
  );
}

/** Un evento dichiarato: gara, stage, seminario, esame, arbitraggio. Mai nel
 *  futuro (l'API lo rifiuta): il curriculum racconta quello che è successo. */
function EventModal({ item, onClose }: { item: SportItem | null; onClose: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const { data: documents } = useCvDocuments();
  const today = todayIso();
  const [form, setForm] = useState<EventWrite>(() => ({
    title: item?.title ?? "", event_type: item?.kind ?? "COMPETITION", role: item?.role ?? "ATHLETE",
    starts_on: item?.date?.slice(0, 10) ?? "", ends_on: item?.end_date?.slice(0, 10) ?? null, location: item?.location ?? null,
    organization_name: item?.club ?? null, level: item?.level ?? null, category: item?.category ?? null,
    placement: item?.placement ?? null, result: item?.result ?? null, description: item?.description ?? null,
    document_id: item?.document_id ?? null,
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof EventWrite>(k: K, v: EventWrite[K]) => setForm((f) => ({ ...f, [k]: v }));
  const text = (k: "location" | "organization_name" | "category" | "result" | "description") => ({
    value: form[k] ?? "", onChange: (e: { target: { value: string } }) => set(k, e.target.value || null),
  });
  const competition = form.event_type === "COMPETITION";
  const future = (!!form.starts_on && form.starts_on > today) || (!!form.ends_on && form.ends_on > today);
  const backwards = !!form.ends_on && !!form.starts_on && form.ends_on < form.starts_on;
  const problem = future ? t("cv.sport.futureDate") : backwards ? t("cv.sport.endBeforeStart") : null;

  async function save() {
    setBusy(true);
    setError(null);
    const body: EventWrite = {
      ...form, title: form.title.trim(),
      // Il piazzamento ha senso solo per una gara: cambiando tipo si lascia cadere.
      placement: competition ? form.placement : null,
      level: form.level || null,
      document_id: form.document_id || null,
    };
    try {
      if (item) await clubSend(CV(`/sport/events/${item.id}`), "PUT", body);
      else await clubSend(CV("/sport/events"), "POST", body);
      await qc.invalidateQueries({ queryKey: SPORT_QUERY });
      toast({ tone: "success", title: t("cv.sport.saved") });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} size="lg" title={item ? t("cv.sport.editTitle") : t("cv.sport.add")} subtitle={t("cv.sport.formHint")}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button onClick={() => void save()} loading={busy} disabled={!form.title.trim() || !form.starts_on || !!problem}>{t("common.save")}</Button>
      </>}>
      <div className="space-y-4">
        <Field label={t("cv.sport.eventTitle")}>
          <Input value={form.title} maxLength={200} onChange={(e) => set("title", e.target.value)} placeholder={t("cv.sport.eventTitlePlaceholder")} autoFocus />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("cv.sport.eventType")}>
            <Select value={form.event_type} onChange={(e) => set("event_type", e.target.value)}>
              {EVENT_TYPES.map((k) => <option key={k} value={k}>{KIND_ICON[k]} {kindLabel(t, k, k)}</option>)}
            </Select>
          </Field>
          <Field label={t("cv.sport.role")}>
            <Select value={form.role} onChange={(e) => set("role", e.target.value)}>
              {EVENT_ROLES.map((k) => <option key={k} value={k}>{roleLabel(t, k, k)}</option>)}
            </Select>
          </Field>
          <Field label={t("cv.sport.startsOn")}>
            <Input type="date" max={today} value={form.starts_on} onChange={(e) => set("starts_on", e.target.value)} />
          </Field>
          <Field label={t("cv.sport.endsOn")} hint={t("common.optional")}>
            <Input type="date" max={today} min={form.starts_on || undefined} value={form.ends_on ?? ""} onChange={(e) => set("ends_on", e.target.value || null)} />
          </Field>
          <Field label={t("cv.sport.location")}><Input maxLength={200} {...text("location")} /></Field>
          <Field label={t("cv.sport.organization")}><Input maxLength={200} {...text("organization_name")} placeholder={t("cv.sport.organizationPlaceholder")} /></Field>
          <Field label={t("cv.sport.level")}>
            <Select value={form.level ?? ""} onChange={(e) => set("level", e.target.value || null)}>
              <option value="">—</option>
              {EVENT_LEVELS.map((k) => <option key={k} value={k}>{levelLabel(t, k, k)}</option>)}
            </Select>
          </Field>
          <Field label={t("cv.sport.category")}><Input maxLength={120} {...text("category")} placeholder={t("cv.sport.categoryPlaceholder")} /></Field>
          {competition && (
            <Field label={t("cv.sport.placement")}>
              <Select value={form.placement ?? ""} onChange={(e) => set("placement", e.target.value === "" ? null : Number(e.target.value))}>
                <option value="">—</option>
                {PLACEMENTS.map((n) => <option key={n} value={n}>{placementLabel(t, n, String(n))}</option>)}
              </Select>
            </Field>
          )}
          <Field label={t("cv.sport.result")}><Input maxLength={300} {...text("result")} placeholder={t("cv.sport.resultPlaceholder")} /></Field>
        </div>
        <Field label={t("cv.sport.description")} hint={t("common.optional")}>
          <Textarea rows={3} maxLength={4000} {...text("description")} />
        </Field>
        <Field label={t("cv.sport.supportingDoc")} hint={t("cv.sport.supportingDocHint")}>
          <Select value={form.document_id ?? ""} onChange={(e) => set("document_id", e.target.value || null)}>
            <option value="">{t("cv.sport.noDocument")}</option>
            {(documents ?? []).map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
          </Select>
        </Field>
        {(problem || error) && <p className="rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">{problem ?? error}</p>}
      </div>
    </Modal>
  );
}
