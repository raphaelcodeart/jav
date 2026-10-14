"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { clubSignupUrl } from "@/components/club/club-staff";
import { useCurrentClub } from "@/components/club/current-club";
import { CoursesManager } from "@/components/club/jav-courses";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import { shareOrCopyLink } from "@/lib/share-link";

interface UnitRow { id: string; name: string; slug: string; kind?: string; athletes_active: number }

/** L'entrata "Cursos JAV" della console: l'unità dei corsi nelle scuole non
 *  è un club, e non sta nell'elenco dei club. Se non c'è ancora il
 *  superadmin la crea con un clic (con il piano da 25 € al mese); se c'è, ci
 *  si entra e si gestiscono i corsi uno per uno. */
export function CoursesUnitPanel({ canCreate, onEnter }: { canCreate: boolean; onEnter: (id: string) => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data: current } = useCurrentClub();
  const [busy, setBusy] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["clubs"],
    queryFn: async (): Promise<UnitRow[]> => {
      const res = await fetch("/api/proxy/clubs");
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });
  const unit = (data ?? []).find((c) => c.kind === "JAV_COURSES");

  async function create() {
    setBusy(true);
    try {
      const res = await fetch("/api/proxy/clubs/jav-courses", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const created: UnitRow = await res.json();
      await queryClient.invalidateQueries({ queryKey: ["clubs"] });
      toast({ tone: "success", title: t("javCourses.unitCreated") });
      onEnter(created.id);
    } catch (e) {
      toast({ tone: "error", title: t("common.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function copyLink(slug: string) {
    const result = await shareOrCopyLink({ url: clubSignupUrl(slug), title: t("javCourses.navEntry"), preferClipboard: true });
    toast({ tone: result === "failed" ? "error" : "success", title: result === "failed" ? t("clubs.copyFailed") : t("clubs.copied") });
  }

  const header = (
    <PageHeader eyebrow="JudoArteVida" title={`🏫 ${t("javCourses.navEntry")}`} subtitle={t("javCourses.unitSubtitle")}
      actions={unit ? <Button size="sm" variant="secondary" onClick={() => copyLink(unit.slug)}>{t("javCourses.copySignup")}</Button> : undefined} />
  );
  if (isLoading) return <Skeleton className="h-64" />;
  if (!unit) {
    return (
      <div className="space-y-6">
        {header}
        <EmptyState icon={<span className="text-3xl">🏫</span>} title={t("javCourses.noUnit")} text={t("javCourses.noUnitText")}
          action={canCreate ? <Button loading={busy} onClick={create}>{t("javCourses.createUnit")}</Button> : undefined} />
      </div>
    );
  }
  if (current?.id !== unit.id) {
    return (
      <div className="space-y-6">
        {header}
        <EmptyState icon={<span className="text-3xl">🏫</span>} title={unit.name}
          text={t("javCourses.enterText", { n: unit.athletes_active })}
          action={<Button onClick={() => onEnter(unit.id)}>{t("javCourses.enter")}</Button>} />
      </div>
    );
  }
  return (
    <div className="space-y-6">
      {header}
      <CoursesManager />
    </div>
  );
}
