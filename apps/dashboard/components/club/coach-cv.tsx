"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { BeltBadge } from "@/components/ui/belt";
import { Tabs } from "@/components/ui/tabs";
import { CV_QUERY, SavedVersions, useCv } from "@/components/club/coach-cv-common";
import { CvDocuments } from "@/components/club/coach-cv-documents";
import { CvEditorTab } from "@/components/club/coach-cv-editor";
import { CvSport } from "@/components/club/coach-cv-sport";
import { CoachAvatar } from "@/components/club/staff-clubs";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// «O meu currículo» (apps/api/app/domains/club/coach_cv.py): l'archivio
// professionale personale del treinador, in tre schede — i documenti, il CV
// da scrivere e il Curriculum Desportivo che si costruisce da solo. È suo e
// non del club: è lo stesso in qualunque club stia lavorando.

type CvTab = "docs" | "cv" | "sport";

export function CoachCv() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { data } = useCv();
  const [tab, setTab] = useState<CvTab>("docs");
  const firstName = data ? data.me.first_name || data.me.name.split(" ")[0] : "";
  const headline = typeof data?.data.headline === "string" ? data.data.headline : "";
  const certs = data?.documents.filter((d) => d.show_in_cv).length ?? 0;

  return (
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-ink-950 via-brand-800 to-brand-600 p-5 text-white shadow-lift sm:p-6">
        <div aria-hidden="true" className="pointer-events-none absolute -right-12 -top-20 h-64 w-64 rounded-full bg-accent-400/25 blur-3xl" />
        <div className="relative flex items-center gap-4">
          {data && <CoachAvatar me={data.me} size="md" className="sm:h-20 sm:w-20" onUploaded={() => void qc.invalidateQueries({ queryKey: CV_QUERY })} />}
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-white/75">{t("cv.hero.eyebrow")}</p>
            <h2 className="mt-1 truncate text-2xl sm:text-3xl">{data?.me.name ?? firstName}</h2>
            <p className="mt-1 line-clamp-2 text-sm text-white/80">{headline || t("cv.hero.noHeadline")}</p>
          </div>
        </div>
        {data && (
          <div className="relative mt-4 flex flex-wrap gap-2 text-sm">
            {data.belt && (
              <span className="inline-flex items-center rounded-full bg-white/90 px-3 py-1 text-ink-900"><BeltBadge code={data.belt.code} size="sm" /></span>
            )}
            <span className="rounded-full bg-white/15 px-3 py-1 backdrop-blur">🗂️ {t("cv.hero.documents", { n: data.documents.length })}</span>
            <span className="rounded-full bg-white/15 px-3 py-1 backdrop-blur">📜 {t("cv.hero.certs", { n: certs })}</span>
            <span className="rounded-full bg-white/15 px-3 py-1 backdrop-blur">🏯 {t("cv.hero.clubs", { n: data.clubs.length })}</span>
          </div>
        )}
      </section>

      <Tabs value={tab} onChange={(k) => setTab(k as CvTab)} className="w-full sm:w-auto" items={[
        { key: "docs", label: `🗂️ ${t("cv.tabs.docs")}` },
        { key: "cv", label: `📄 ${t("cv.tabs.cv")}` },
        { key: "sport", label: `🏅 ${t("cv.tabs.sport")}` },
      ]} />

      {tab === "docs" && <CvDocuments />}
      {/* L'editor resta montato cambiando scheda: le modifiche non salvate non si perdono. */}
      <div className={cn(tab !== "cv" && "hidden")}><CvEditorTab onGoDocuments={() => setTab("docs")} /></div>
      {tab === "sport" && <CvSport />}
      {tab !== "docs" && <SavedVersions />}
    </div>
  );
}
