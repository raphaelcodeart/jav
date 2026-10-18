"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { clubGet } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

// Il regolamento PDF di un evento (club/router.py::_regulation_link): sta nel
// bucket privato, quindi non c'è un link fisso da mettere nella pagina; si
// chiede un URL di pochi minuti al momento del clic. Famiglie e atleti
// passano da /competitions, lo staff (treinadores e segreteria) da
// /staff/competitions: sono permessi diversi.

export type RegulationArea = "member" | "staff";

/** Apre il regolamento in una scheda nuova. Lancia l'errore dell'API (già
 *  tradotto da friendlyApiError) se l'evento non ce l'ha o non si può aprire. */
export async function openRegulation(competitionId: string, area: RegulationArea): Promise<void> {
  // La finestra si apre nel clic: dopo l'await il browser la bloccherebbe.
  const tab = window.open("", "_blank");
  if (tab) tab.opener = null;
  try {
    const { url } = await clubGet<{ url: string; filename: string | null }>(
      `${area === "staff" ? "/staff" : ""}/competitions/${competitionId}/regulation`,
    );
    if (tab) tab.location.href = url;
    else window.location.href = url;
  } catch (e) {
    tab?.close();
    throw e;
  }
}

/** Il bottone «Regulamento (PDF)» delle schede degli eventi. */
export function RegulationButton({ competitionId, area, filename, size = "sm", variant = "secondary" }: {
  competitionId: string; area: RegulationArea; filename?: string | null;
  size?: "sm" | "md"; variant?: "secondary" | "ghost";
}) {
  const { t } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  async function open() {
    setBusy(true);
    try {
      await openRegulation(competitionId, area);
    } catch (e) {
      toast({ tone: "error", title: t("jbx.reg.openError"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Button size={size} variant={variant} loading={busy} onClick={open} title={filename ?? undefined}
      icon={<span aria-hidden="true">📄</span>}>
      {t("jbx.reg.download")} <span aria-hidden="true">↗</span>
    </Button>
  );
}
