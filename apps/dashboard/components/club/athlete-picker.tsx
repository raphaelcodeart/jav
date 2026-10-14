"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { clubGet, type AthleteCard } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

/** "Per chi è?": the family's athletes as chips, for equipment orders. Hidden
 *  for accounts with no athletes (or no club access): the order works the same. */
export function AthletePicker({ value, onChange }: { value: string | null; onChange: (id: string | null) => void }) {
  const { data } = useQuery({
    queryKey: ["club", "athletes"],
    queryFn: () => clubGet<AthleteCard[]>("/athletes"),
    retry: false,
  });
  const { t } = useI18n();
  const athletes = data ?? [];
  if (athletes.length === 0) return null;
  const chip = (active: boolean) =>
    `inline-flex items-center gap-2 rounded-full px-3.5 h-9 text-sm font-semibold ring-1 cursor-pointer transition ${
      active ? "bg-brand-500 text-white ring-brand-500 shadow-brand" : "bg-white text-ink-700 ring-ink-200 hover:ring-brand-300"
    }`;
  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold text-ink-800">{t("picker.forWhom")}</p>
      <div className="flex flex-wrap gap-2">
        {athletes.map((a) => (
          <motion.button key={a.id} type="button" whileTap={{ scale: 0.94 }} className={chip(value === a.id)} onClick={() => onChange(value === a.id ? null : a.id)}>
            🥋 {a.first_name}
          </motion.button>
        ))}
        <button type="button" className={chip(value === null)} onClick={() => onChange(null)}>
          {t("picker.forFamily")}
        </button>
      </div>
    </div>
  );
}
