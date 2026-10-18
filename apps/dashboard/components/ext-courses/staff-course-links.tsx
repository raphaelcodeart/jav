"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { SchoolBadge, useGroupLine } from "@/components/ext-courses/common";
import { fetchStaffCourses, STAFF_COURSES_KEY } from "@/lib/ext-courses";
import { useI18n } from "@/lib/i18n/provider";

export function useStaffExtCourses(enabled = true) {
  return useQuery({ queryKey: STAFF_COURSES_KEY, queryFn: fetchStaffCourses, enabled, staleTime: 5 * 60_000, retry: false });
}

/** Nella scelta del club del treinador, i corsi esterni in cui insegna:
 *  non sono club (niente cookie del club), si aprono nell'area /escola. */
export function ExtCourseLinks() {
  const { t } = useI18n();
  const groupLine = useGroupLine();
  const { data } = useStaffExtCourses();
  const courses = (data ?? []).filter((c) => c.roles.includes("COACH") && !c.roles.includes("ADMIN"));
  if (courses.length === 0) return null;
  return (
    <div className="space-y-3">
      <p className="px-1 text-sm text-ink-500">{t("ext.picker.title")}</p>
      {courses.map((course, i) => {
        const group = course.groups.find((g) => g.active);
        return (
          <motion.div key={course.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} whileHover={{ y: -2 }}>
            <Link href={`/escola?curso=${course.id}`}
              className="group relative flex w-full items-center gap-4 overflow-hidden rounded-3xl bg-white p-4 text-left shadow-soft ring-1 ring-ink-900/5 hover:shadow-lift hover:ring-accent-300 sm:gap-5 sm:p-5">
              <span aria-hidden="true" className="absolute inset-y-0 left-0 w-2 bg-accent-400" />
              <SchoolBadge course={course} className="ml-1 h-16 w-16 rounded-full sm:h-20 sm:w-20" />
              <span className="min-w-0 flex-1">
                <span className="block text-[11px] font-bold uppercase tracking-wider text-accent-700">🏫 {t("ext.picker.badge")}</span>
                <span className="block font-display text-xl leading-tight text-ink-900 sm:text-2xl">{course.school_name}</span>
                <span className="mt-2 flex flex-wrap gap-1.5 text-xs font-semibold">
                  <span className="rounded-full bg-ink-50 px-2.5 py-1 text-ink-700 ring-1 ring-ink-100">🧒 {t("ext.picker.participants", { n: course.participants })}</span>
                  {group && <span className="rounded-full bg-ink-50 px-2.5 py-1 capitalize text-ink-700 ring-1 ring-ink-100">🗓️ {groupLine(group)}</span>}
                </span>
              </span>
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-accent-400 text-2xl text-ink-900 shadow-accent transition-transform group-hover:translate-x-0.5" aria-hidden="true">›</span>
            </Link>
          </motion.div>
        );
      })}
    </div>
  );
}
