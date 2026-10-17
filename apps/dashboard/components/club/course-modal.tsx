"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend, type Course } from "@/lib/club";
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
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    const body = {
      name, description: description || null, level: level || null,
      min_age: minAge ? Number(minAge) : null, max_age: maxAge ? Number(maxAge) : null,
      instructor_user_id: instructor || null, active,
    };
    try {
      await (c ? clubSend(A(`/courses/${c.id}`), "PATCH", body) : clubSend(A("/courses"), "POST", body));
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
      </div>
    </Modal>
  );
}
