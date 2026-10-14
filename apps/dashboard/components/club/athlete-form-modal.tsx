"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { BELTS } from "@/lib/belts";
import { clubGet, clubSend, type AthleteCard, type Course } from "@/lib/club";
import { useClubFeatures } from "@/components/club/jav-courses";
import { readCoursePreference } from "@/lib/course-preference";
import { useI18n } from "@/lib/i18n/provider";
import { celebrate } from "@/lib/motion";
import { beltLabel } from "@/components/ui/belt";

/** Add a child (or yourself) to the family, or fix their data. Only what a
 *  parent knows by heart: the plan is chosen by the system from the age. */
export function AthleteFormModal({ open, onClose, athlete }: { open: boolean; onClose: () => void; athlete?: AthleteCard | null }) {
  const editing = Boolean(athlete);
  const [firstName, setFirstName] = useState(athlete?.first_name ?? "");
  const [lastName, setLastName] = useState(athlete?.last_name ?? "");
  const [birthDate, setBirthDate] = useState(athlete?.birth_date ?? "");
  const [sex, setSex] = useState(athlete?.sex ?? "M");
  const [isSelf, setIsSelf] = useState(athlete?.is_self ?? false);
  const [weight, setWeight] = useState(athlete?.weight_kg ? String(athlete.weight_kg) : "");
  const [fiscalCode, setFiscalCode] = useState(athlete?.fiscal_code ?? "");
  const [belt, setBelt] = useState("WHITE");
  // Nei corsi JAV si sceglie la scuola (il corso) e non c'è la cintura; il
  // corso scelto dal sito (/c/<slug>?curso=...) arriva già selezionato.
  const features = useClubFeatures();
  const { data: courses } = useQuery({
    queryKey: ["club", "courses"],
    queryFn: () => clubGet<Course[]>("/courses"),
    enabled: features.courses && !editing,
  });
  const [courseId, setCourseId] = useState(() => readCoursePreference() ?? "");
  const choices = (courses ?? []).filter((c) => c.published);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();
  const { t } = useI18n();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = {
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      birth_date: birthDate,
      sex,
      fiscal_code: fiscalCode.trim().toUpperCase() || null,
      weight_kg: weight ? Number(weight.replace(",", ".")) : null,
    };
    try {
      if (editing && athlete) {
        await clubSend(`/athletes/${athlete.id}`, "PATCH", body);
        toast({ tone: "success", title: t("athleteForm.updated") });
      } else {
        await clubSend("/athletes", "POST", features.courses
          ? { ...body, is_self: isSelf, course_id: courseId || null }
          : { ...body, is_self: isSelf, belt });
        void celebrate();
        toast({ tone: "success", title: t("athleteForm.welcome", { name: firstName.trim() }), text: t("athleteForm.planChosen") });
      }
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      onClose();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={editing ? t("athleteForm.editTitle") : t("athleteForm.addTitle")} subtitle={editing ? undefined : t("athleteForm.addSubtitle")}>
      <form onSubmit={submit} className="space-y-4">
        {!editing && (
          <div className="grid grid-cols-2 gap-2 rounded-2xl bg-ink-100/80 p-1">
            {[
              { v: false, label: `👧 ${t("athleteForm.myChild")}` },
              { v: true, label: `🙋 ${t("athleteForm.myself")}` },
            ].map((o) => (
              <button
                key={o.label}
                type="button"
                onClick={() => setIsSelf(o.v)}
                className={`h-11 rounded-xl text-sm font-semibold cursor-pointer transition ${isSelf === o.v ? "bg-white shadow-soft text-ink-900" : "text-ink-500"}`}
              >
                {o.label}
              </button>
            ))}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("athleteForm.firstName")} htmlFor="ath-first">
            <Input id="ath-first" required value={firstName} onChange={(e) => setFirstName(e.target.value)} />
          </Field>
          <Field label={t("athleteForm.lastName")} htmlFor="ath-last">
            <Input id="ath-last" required value={lastName} onChange={(e) => setLastName(e.target.value)} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("athleteForm.birthDate")} htmlFor="ath-birth">
            <Input id="ath-birth" type="date" required value={birthDate} onChange={(e) => setBirthDate(e.target.value)} />
          </Field>
          <Field label={t("athleteForm.sex")} htmlFor="ath-sex">
            <Select id="ath-sex" value={sex} onChange={(e) => setSex(e.target.value)}>
              <option value="M">{t("athleteForm.male")}</option>
              <option value="F">{t("athleteForm.female")}</option>
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("athleteForm.weight")} hint={t("athleteForm.weightHint")} htmlFor="ath-weight">
            <Input id="ath-weight" inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} placeholder={t("athleteForm.weightPlaceholder")} />
          </Field>
          {!editing && features.courses ? (
            <Field label={t("javCourses.chooseCourse")} htmlFor="ath-course">
              <Select id="ath-course" required={choices.length > 0} value={choices.some((c) => c.id === courseId) ? courseId : ""} onChange={(e) => setCourseId(e.target.value)}>
                <option value="">—</option>
                {choices.map((c) => (
                  <option key={c.id} value={c.id}>{[c.name, c.venue_name].filter(Boolean).join(" · ")}</option>
                ))}
              </Select>
            </Field>
          ) : !editing ? (
            <Field label={t("athleteForm.currentBelt")} htmlFor="ath-belt">
              <Select id="ath-belt" value={belt} onChange={(e) => setBelt(e.target.value)}>
                {BELTS.map((b) => (
                  <option key={b.code} value={b.code}>
                    {beltLabel(t, b.code, b.label)}
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            <div />
          )}
        </div>
        <Field label={t("athleteForm.fiscalCode")} hint={t("common.optional")} htmlFor="ath-cf">
          <Input id="ath-cf" value={fiscalCode} onChange={(e) => setFiscalCode(e.target.value)} maxLength={16} className="uppercase font-mono" />
        </Field>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <Button type="submit" size="lg" loading={busy} className="w-full">
          {editing ? t("common.save") : t("athleteForm.addToFamily")}
        </Button>
      </form>
    </Modal>
  );
}
