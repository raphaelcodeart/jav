import type { useI18n } from "@/lib/i18n/provider";

type T = ReturnType<typeof useI18n>["t"];
type Fmt = ReturnType<typeof useI18n>["fmt"];

/** La quota nella lingua di chi guarda. Il server scrive la descrizione in
 *  italiano («Quota di ottobre 2026», «Iscrizione 2026 · rata 2/2»,
 *  «Iscrizione gara: Torneio…»): qui si ricostruisce da tipo, periodo e
 *  descrizione quando hanno una di queste forme; per il resto resta la sua. */
export function feeLabel(f: { kind: string; period: string; description: string }, t: T, fmt: Fmt): string {
  const kind = t.dyn(`club.feeKind.${f.kind}`, "");
  if (!kind) return f.description;
  const month = /^(\d{4})-(\d{2})$/.exec(f.period);
  if (f.kind === "MONTHLY" && month) {
    return `${kind} · ${fmt.date(new Date(Number(month[1]), Number(month[2]) - 1, 1), { month: "long", year: "numeric" })}`;
  }
  const year = /^(\d{4})(?:\/\d+)?$/.exec(f.period);
  if ((f.kind === "ENROLLMENT" || f.kind === "MEMBERSHIP") && year) {
    const part = /rata (\d+)\/(\d+)/.exec(f.description);
    return part ? `${kind} ${year[1]} · ${t("fees.installment", { n: part[1]!, total: part[2]! })}` : `${kind} ${year[1]}`;
  }
  const entry = /^Iscrizione(?: (?:gara|stage))?: (.+)$/.exec(f.description);
  if (f.kind === "COMPETITION" && entry) return `${kind}: ${entry[1]}`;
  return f.description;
}
