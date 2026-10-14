"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend, type FamilyLesson } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

/** "Oggi in palestra": le lezioni di oggi dei figli, con un tocco per dire
 *  "è arrivato" e una nota per la segreteria. Solo oggi: i giorni passati li
 *  corregge la segreteria. Non compare se oggi non c'è lezione. */
export function FamilyToday() {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["club", "attendance", "today"], queryFn: () => clubGet<FamilyLesson[]>("/attendance/today") });
  const [notes, setNotes] = useState<Record<string, string>>({});
  if (!data?.length) return null;

  async function toggle(l: FamilyLesson) {
    try {
      if (l.present) await clubSend(`/attendance/today/${l.athlete_id}/${l.course_id}`, "DELETE");
      else await clubSend("/attendance/today", "POST", { athlete_id: l.athlete_id, course_id: l.course_id, note: notes[`${l.athlete_id}-${l.course_id}`] || null });
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: l.present ? t("familyToday.removed") : t("familyToday.marked", { name: l.athlete_name.split(" ")[0] ?? l.athlete_name }) });
    } catch (e) {
      toast({ tone: "error", title: t("attendance.notSaved"), text: (e as Error).message });
    }
  }

  return (
    <section className="glass-card rounded-3xl p-5 space-y-3">
      <h3 className="text-base text-ink-900">🥋 {t("familyToday.title")}</h3>
      <ul className="space-y-2">
        {data.map((l) => {
          const key = `${l.athlete_id}-${l.course_id}`;
          return (
            <li key={key} className={`rounded-2xl p-3 ring-1 ${l.present ? "bg-emerald-50 ring-emerald-200" : "bg-white ring-ink-200"}`}>
              <div className="flex items-center gap-3">
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-ink-900">{l.athlete_name}</span>
                  <span className="block text-xs text-ink-500">{l.course_name} · {l.starts_at.slice(0, 5)}–{l.ends_at.slice(0, 5)}</span>
                </span>
                <motion.div whileTap={{ scale: 0.95 }}>
                  <Button size="sm" variant={l.present ? "secondary" : "primary"} onClick={() => toggle(l)}>
                    {l.present ? `✓ ${t("familyToday.present")}` : t("familyToday.mark")}
                  </Button>
                </motion.div>
              </div>
              {!l.present && (
                <Input className="mt-2" value={notes[key] ?? ""} maxLength={300} placeholder={t("familyToday.notePlaceholder")}
                  onChange={(e) => setNotes((n) => ({ ...n, [key]: e.target.value }))} />
              )}
              {l.present && l.note && <p className="mt-1 text-xs text-amber-800">📝 {l.note}</p>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
