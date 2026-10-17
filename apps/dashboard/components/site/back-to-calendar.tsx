"use client";

import Link from "next/link";
import { useEventsReturn } from "@/lib/events-return";
import { useI18n } from "@/lib/i18n/provider";

/** Nella pagina di un evento aperta dal calendario dell'area (?from=area):
 *  riporta alla sezione e al punto del calendario di prima
 *  (lib/events-return.ts). Senza quel punto (scaduto, altra scheda del
 *  browser), all'area. */
export function BackToCalendar() {
  const { t } = useI18n();
  const back = useEventsReturn();
  return (
    <Link href={back?.url ?? "/area"}
      className="mb-6 inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-ink-900 shadow-soft transition hover:-translate-x-0.5 hover:bg-accent-100">
      <span aria-hidden="true">←</span> {t("site.event.backToCalendar")}
    </Link>
  );
}
