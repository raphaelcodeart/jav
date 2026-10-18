"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { clubGet, PERSON_KIND_ICONS, type PersonKind } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

// I piccoli simboli accanto ai nomi negli elenchi della segreteria: 🥋 atleta,
// 👪 genitore, 🧑‍🏫 istruttore, 🧑‍⚖️ árbitro (e le altre funzioni). Una persona
// che è più cose ha più simboli. Li dà l'elenco delle persone del club
// (club/people.py::list_people), nella versione senza soldi né contatti
// (/club/staff/people-kinds) che legge anche l'istruttore. Chi non la può
// leggere (una famiglia) semplicemente non vede i simboli.

interface PersonKinds { kind: "ATHLETE" | "USER"; id: string; user_id: string | null; kinds: PersonKind[] }

const ORDER: PersonKind[] = ["ATHLETE", "PARENT", "COACH", "ASSISTANT_COACH", "MONITOR", "ASSISTANT_MONITOR", "REFEREE", "SECRETARY"];

// Un treinador deve saltare all'occhio anche in mezzo agli atleti: un
// account solo può allenare in più club e comparire negli elenchi di tutti.
const COACHING: PersonKind[] = ["COACH", "ASSISTANT_COACH"];

export function usePersonKinds() {
  const { data } = useQuery({
    queryKey: ["club", "staff", "people-kinds"],
    queryFn: () => clubGet<PersonKinds[]>("/staff/people-kinds"),
    retry: false,
    staleTime: 60_000,
  });
  return useMemo(() => {
    const byAthlete = new Map<string, PersonKind[]>();
    const byUser = new Map<string, PersonKind[]>();
    for (const p of data ?? []) {
      if (p.kind === "ATHLETE") byAthlete.set(p.id, p.kinds);
      if (p.user_id) byUser.set(p.user_id, p.kinds);
    }
    return { athlete: (id?: string | null) => (id ? byAthlete.get(id) : undefined) ?? [],
             user: (id?: string | null) => (id ? byUser.get(id) : undefined) ?? [] };
  }, [data]);
}

/** Il colore di ogni ruolo nella versione grande (colonna «Ruolo»). */
const TONE: Record<PersonKind, string> = {
  ATHLETE: "bg-brand-50 ring-brand-200",
  PARENT: "bg-amber-50 ring-amber-200",
  COACH: "bg-emerald-50 ring-emerald-200",
  ASSISTANT_COACH: "bg-emerald-50 ring-emerald-200",
  MONITOR: "bg-sky-50 ring-sky-200",
  ASSISTANT_MONITOR: "bg-sky-50 ring-sky-200",
  REFEREE: "bg-violet-50 ring-violet-200",
  SECRETARY: "bg-ink-100 ring-ink-200",
};

/** I simboli, piccoli, da mettere dopo un nome; `size="md"`: grandi e
 *  colorati, per la colonna del ruolo nelle tabelle. */
export function PersonMarks({ kinds, className = "", size = "sm" }: { kinds: PersonKind[]; className?: string; size?: "sm" | "md" }) {
  const { t } = useI18n();
  if (!kinds.length) return null;
  const sorted = [...kinds].sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b));
  return (
    <span className={`inline-flex items-center align-middle ${size === "md" ? "gap-1" : "gap-0.5"} ${className}`}>
      {sorted.map((k) => {
        const label = t.dyn(`people.kind.${k}`, k);
        return (
          <span key={k} title={label} aria-label={label} role="img"
            className={size === "md"
              ? `inline-flex h-8 w-8 items-center justify-center rounded-xl text-base leading-none shadow-sm ring-1 ${TONE[k]}`
              : `inline-flex h-5 w-5 items-center justify-center rounded-md text-[12px] leading-none ring-1 ${COACHING.includes(k) ? TONE[k] : "bg-ink-50 ring-ink-100"}`}>
            {PERSON_KIND_ICONS[k]}
          </span>
        );
      })}
    </span>
  );
}

/** Il segno del treinador accanto al nome (elenco atleti della segreteria):
 *  il simbolo e la parola, perché lì i simboli piccoli si perdono. */
export function CoachMark({ kinds, className = "" }: { kinds: PersonKind[]; className?: string }) {
  const { t } = useI18n();
  const k = COACHING.find((c) => kinds.includes(c));
  if (!k) return null;
  const label = t.dyn(`people.kind.${k}`, k);
  return (
    <span title={label} className={`inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-bold text-emerald-800 ring-1 ${TONE[k]} ${className}`}>
      <span aria-hidden="true" className="text-[12px] leading-none">{PERSON_KIND_ICONS[k]}</span>{label}
    </span>
  );
}

/** I simboli di un atleta, cercati per id nell'elenco delle persone. */
export function AthleteMarks({ id, className }: { id?: string | null; className?: string }) {
  const kinds = usePersonKinds();
  return <PersonMarks kinds={kinds.athlete(id)} className={className} />;
}

/** I simboli di un account (genitore, staff), cercati per id. */
export function UserMarks({ id, className }: { id?: string | null; className?: string }) {
  const kinds = usePersonKinds();
  return <PersonMarks kinds={kinds.user(id)} className={className} />;
}

/** Il segno del treinador per un atleta, cercato per id (elenchi del treinador). */
export function AthleteCoachMark({ id, className }: { id?: string | null; className?: string }) {
  const kinds = usePersonKinds();
  return <CoachMark kinds={kinds.athlete(id)} className={className} />;
}
