"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend, type Course } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

const A = (path: string) => `/admin${path}`;

export interface StaffOption { user_id: string; email: string; role: string; name?: string | null }

/** I treinador che si possono scegliere per una turma: gli istruttori del club. */
export function useInstructors() {
  const { data } = useQuery({ queryKey: ["club", "admin", "staff"], queryFn: () => clubGet<StaffOption[]>(A("/staff")) });
  return (data ?? []).filter((s) => s.role === "INSTRUCTOR");
}

/** Una turma (un corso con i suoi orari): nome, livello, età, treinador,
 *  descrizione. Si apre dalla pagina «Turmas e horários» e dalla scheda di un
 *  gruppo in «Planos e preços»: lì `defaults` porta già le età del gruppo. */
export function CourseModal({ course: c, defaults, onClose }: {
  course: Course | null;
  defaults?: { name?: string; min_age?: number | null; max_age?: number | null };
  onClose: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const instructors = useInstructors();
  const [name, setName] = useState(c?.name ?? defaults?.name ?? "");
  const [description, setDescription] = useState(c?.description ?? "");
  const [level, setLevel] = useState(c?.level ?? "");
  const [minAge, setMinAge] = useState(c?.min_age != null ? String(c.min_age) : defaults?.min_age != null ? String(defaults.min_age) : "");
  const [maxAge, setMaxAge] = useState(c?.max_age != null ? String(c.max_age) : defaults?.max_age != null ? String(defaults.max_age) : "");
  const [instructor, setInstructor] = useState(c?.instructor_user_id ?? "");
  const [active, setActive] = useState(c?.active ?? true);
  const [assistants, setAssistants] = useState<string[]>(c?.staff_user_ids ?? []);
  const [hiddenFrom, setHiddenFrom] = useState<string[]>(c?.excluded_coach_ids ?? []);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    const body = {
      name, description: description || null, level: level || null,
      min_age: minAge ? Number(minAge) : null, max_age: maxAge ? Number(maxAge) : null,
      instructor_user_id: instructor || null, active,
    };
    try {
      const saved = await (c ? clubSend<Course>(A(`/courses/${c.id}`), "PATCH", body) : clubSend<Course>(A("/courses"), "POST", body));
      // Adjunto ed esclusioni hanno rotte loro: si mandano solo se cambiati.
      const wantedAssistants = assistants.filter((u) => u !== instructor);
      if (!sameSet(wantedAssistants, c?.staff_user_ids ?? [])) {
        await clubSend(A(`/courses/${saved.id}/staff`), "PUT", { user_ids: wantedAssistants });
      }
      if (!sameSet(hiddenFrom, c?.excluded_coach_ids ?? [])) {
        await clubSend(A(`/courses/${saved.id}/coach-exclusions`), "PUT", { user_ids: hiddenFrom });
      }
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: c ? t("ca.course.updated") : t("ca.course.created") });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: t("common.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={c ? t("ca.course.editTitle") : t("ca.course.new")}
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button loading={busy} onClick={save} disabled={!name}>{t("common.save")}</Button></>}>
      <div className="space-y-4">
        <Field label={t("ca.name")} htmlFor="co-name"><Input id="co-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("ca.course.namePh")} /></Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("ca.level")} htmlFor="co-level"><Input id="co-level" value={level} onChange={(e) => setLevel(e.target.value)} placeholder={t("ca.course.levelPh")} /></Field>
          <Field label={t("groups.coach")} htmlFor="co-coach">
            <Select id="co-coach" value={instructor} onChange={(e) => setInstructor(e.target.value)}>
              <option value="">{t("groups.noCoach")}</option>
              {instructors.map((s) => <option key={s.user_id} value={s.user_id}>{s.name || s.email}</option>)}
              {instructor && !instructors.some((s) => s.user_id === instructor) && <option value={instructor}>{c?.instructor_name ?? instructor}</option>}
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("ca.minAge")} htmlFor="co-min"><Input id="co-min" type="number" value={minAge} onChange={(e) => setMinAge(e.target.value)} /></Field>
          <Field label={t("ca.maxAge")} htmlFor="co-max"><Input id="co-max" type="number" value={maxAge} onChange={(e) => setMaxAge(e.target.value)} /></Field>
        </div>
        <Field label={t("ca.description")} htmlFor="co-desc"><Textarea id="co-desc" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <label className="flex items-center gap-2 text-sm text-ink-700"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="accent-brand-500 h-4 w-4" /> {t("ca.course.active")}</label>
        <CoachChecklist title={t("ca.course.assistants")} hint={t("ca.course.assistantsHint")}
          coaches={instructors.filter((s) => s.user_id !== instructor)} value={assistants} onChange={setAssistants} />
        <CoachChecklist title={t("ca.course.hiddenFrom")} hint={t("ca.course.hiddenFromHint")} tone="danger"
          summary={hiddenFrom.length ? t("ca.course.hiddenCount", { n: hiddenFrom.length }) : t("ca.course.everyoneSees")}
          coaches={instructors} value={hiddenFrom} onChange={setHiddenFrom} />
      </div>
    </Modal>
  );
}

function sameSet(a: string[], b: string[]) {
  return a.length === b.length && a.every((x) => b.includes(x));
}

/** Una lista di treinador da spuntare: gli adjunto della turma, o quelli che
 *  NON la vedono (`tone="danger"`; di regola ogni treinador vede tutto). */
function CoachChecklist({ title, hint, summary, coaches, value, onChange, tone = "brand" }: {
  title: string; hint: string; summary?: string; coaches: StaffOption[]; value: string[];
  onChange: (v: string[]) => void; tone?: "brand" | "danger";
}) {
  const { t } = useI18n();
  return (
    <fieldset className="space-y-2 rounded-2xl bg-ink-50/70 p-3 ring-1 ring-ink-100">
      <legend className="sr-only">{title}</legend>
      <div>
        <p className="text-sm font-semibold text-ink-900">{title}</p>
        <p className="text-xs text-ink-500">{hint}</p>
      </div>
      {coaches.length === 0 ? <p className="text-xs text-ink-400">{t("ca.course.noCoaches")}</p> : (
        <div className="flex flex-wrap gap-1.5">
          {coaches.map((s) => {
            const on = value.includes(s.user_id);
            return (
              <label key={s.user_id} className={cn(
                "flex min-h-9 cursor-pointer items-center gap-2 rounded-full px-3 py-1.5 text-sm ring-1 transition-colors",
                on ? (tone === "danger" ? "bg-rose-50 text-rose-800 ring-rose-300" : "bg-brand-50 text-brand-800 ring-brand-300")
                  : "bg-white text-ink-700 ring-ink-200 hover:ring-ink-300",
              )}>
                <input type="checkbox" checked={on} className={cn("h-4 w-4", tone === "danger" ? "accent-rose-600" : "accent-brand-500")}
                  onChange={(e) => onChange(e.target.checked ? [...value, s.user_id] : value.filter((u) => u !== s.user_id))} />
                {s.name || s.email}
              </label>
            );
          })}
        </div>
      )}
      {summary && <p className={cn("text-xs font-semibold", value.length ? "text-rose-700" : "text-emerald-700")}>{summary}</p>}
    </fieldset>
  );
}
