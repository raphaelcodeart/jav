"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatTile } from "@/components/ui/stat-tile";
import { friendlyApiError } from "@/lib/api-error";
import { cn } from "@/lib/cn";
import type { MessageKey } from "@/lib/i18n/messages/it";
import { useI18n } from "@/lib/i18n/provider";

// «Consumo do JAVBOT» (javbot/llm.py::usage_summary): quante risposte negli
// ultimi 30 giorni e per quale strada. Regole, azioni e cache non costano
// niente; i documenti costano poco (il modello riassume i passaggi trovati);
// il modello libero è il caso caro. Serve a vedere che il budget regge e
// quali domande converrebbe trasformare in una regola.

type Route = "RULES" | "ACTION" | "CACHE" | "RAG" | "AGENT" | "EXTRACT" | "ARTICLE";

interface Usage {
  days: number;
  answers: number;
  free_answers: number;
  free_share: number | null;
  tokens: number;
  routes: Partial<Record<Route | string, { answers: number; input_tokens: number; output_tokens: number }>>;
  daily: { day: string; answers: number; tokens: number }[];
  top_intents: { intent: string; answers: number }[];
  model: string | null;
  budget_per_day: number | null;
}

// L'ordine è quello della legenda e della barra: prima le strade gratis
// (verdi), poi quelle che spendono token, dalla più economica.
const ROUTES: { key: Route; label: MessageKey; color: string; free: boolean }[] = [
  { key: "RULES", label: "jbx.use.route.RULES", color: "bg-emerald-600", free: true },
  { key: "ACTION", label: "jbx.use.route.ACTION", color: "bg-emerald-400", free: true },
  { key: "CACHE", label: "jbx.use.route.CACHE", color: "bg-teal-300", free: true },
  { key: "RAG", label: "jbx.use.route.RAG", color: "bg-sky-500", free: false },
  { key: "EXTRACT", label: "jbx.use.route.EXTRACT", color: "bg-accent-400", free: false },
  { key: "ARTICLE", label: "jbx.use.route.ARTICLE", color: "bg-violet-500", free: false },
  { key: "AGENT", label: "jbx.use.route.AGENT", color: "bg-brand-500", free: false },
];

export function UsageCard({ mode, provider, model }: { mode: "club" | "platform"; provider: string | null; model: string | null }) {
  const { t, fmt } = useI18n();
  const url = mode === "club" ? "/api/proxy/club/admin/javbot/usage" : "/api/proxy/javbot/admin/usage";
  const { data, isLoading, error } = useQuery({
    queryKey: mode === "club" ? ["club", "javbot", "usage"] : ["javbot", "usage"],
    queryFn: async () => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return (await res.json()) as Usage;
    },
  });
  const num = (n: number) => n.toLocaleString(fmt.tag);
  const compact = (n: number) => n.toLocaleString(fmt.tag, { notation: "compact", maximumFractionDigits: 1 });
  const engine = data?.model ?? model;

  return (
    <Card>
      <CardHeader icon={<span aria-hidden="true">📊</span>} title={t("jbx.use.title")} subtitle={t("jbx.use.subtitle")} />
      {isLoading ? <Skeleton className="h-48" /> : error || !data ? (
        <p className="text-sm text-ink-500">{(error as Error | null)?.message ?? t("jbx.use.loadError")}</p>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-3">
            <StatTile label={t("jbx.use.answers", { days: data.days })} value={data.answers} format={num} icon={<span aria-hidden="true">💬</span>} />
            <StatTile label={t("jbx.use.free")} value={Math.round((data.free_share ?? 0) * 100)} format={(n) => (data.free_share == null ? "—" : `${n}%`)}
              accent="success" icon={<span aria-hidden="true">🌱</span>} hint={t("jbx.use.freeHint", { n: num(data.free_answers) })} />
            <StatTile label={t("jbx.use.tokens")} value={data.tokens} format={compact} accent="ink" icon={<span aria-hidden="true">🔢</span>} />
          </div>
          <RouteBreakdown usage={data} />
          <DailyTokens usage={data} />
          <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-2xl bg-ink-50 p-3 text-sm text-ink-700 ring-1 ring-ink-100">
            <span>🧠 {t("jbx.use.model")}: <strong className="font-semibold text-ink-900">{engine ? `${engine}${provider ? ` · ${provider}` : ""}` : t("jbx.use.noModel")}</strong></span>
            <span>🎯 {t("jbx.use.budget")}: <strong className="font-semibold text-ink-900">{data.budget_per_day ? t("jbx.use.budgetValue", { n: num(data.budget_per_day) }) : "—"}</strong></span>
          </div>
          {data.top_intents.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-500">{t("jbx.use.topIntents")}</p>
              <ul className="flex flex-wrap gap-1.5">
                {data.top_intents.slice(0, 8).map((i) => (
                  <li key={i.intent} className="rounded-full bg-white px-2.5 py-1 text-xs text-ink-700 ring-1 ring-ink-200">
                    {t.dyn(`jbx.intent.${i.intent}`, i.intent.replace(/_/g, " "))} <span className="font-semibold tabular-nums text-ink-900">{num(i.answers)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

/** Le risposte per strada: una barra sola divisa in pezzi, e sotto la
 *  legenda con i numeri (il colore non è mai l'unico modo di leggerla). */
function RouteBreakdown({ usage }: { usage: Usage }) {
  const { t, fmt } = useI18n();
  const total = usage.answers || 1;
  const rows = ROUTES.map((r) => ({ ...r, n: usage.routes[r.key]?.answers ?? 0, tokens: (usage.routes[r.key]?.input_tokens ?? 0) + (usage.routes[r.key]?.output_tokens ?? 0) }));
  const pct = (n: number) => Math.round((n / total) * 100);
  return (
    <div>
      <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-500">{t("jbx.use.byRoute")}</p>
      {usage.answers === 0 ? <p className="text-sm text-ink-500">{t("jbx.use.none")}</p> : (
        <>
          <div className="flex h-4 gap-0.5 overflow-hidden rounded-full bg-ink-100" aria-hidden="true">
            {rows.filter((r) => r.n > 0).map((r) => (
              <span key={r.key} className={cn("h-full first:rounded-l-full last:rounded-r-full", r.color)} style={{ width: `${(r.n / total) * 100}%` }}
                title={`${t(r.label)}: ${r.n.toLocaleString(fmt.tag)} (${pct(r.n)}%)`} />
            ))}
          </div>
          <ul className="mt-3 grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
            {rows.map((r) => (
              <li key={r.key} className={cn("flex items-center gap-2 text-sm", r.n === 0 && "opacity-50")}>
                <span aria-hidden="true" className={cn("h-2.5 w-2.5 shrink-0 rounded-full", r.color)} />
                <span className="min-w-0 flex-1 truncate text-ink-700">
                  {t(r.label)}
                  {r.free && <span className="ml-1.5 rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">{t("jbx.use.noCost")}</span>}
                </span>
                <span className="tabular-nums font-semibold text-ink-900">{r.n.toLocaleString(fmt.tag)}</span>
                <span className="w-10 text-right tabular-nums text-xs text-ink-500">{pct(r.n)}%</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

/** I token spesi giorno per giorno: anche i giorni a zero, così si vede il
 *  ritmo vero; la linea tratteggiata è il budget giornaliero, se ci sta. */
function DailyTokens({ usage }: { usage: Usage }) {
  const { t, fmt } = useI18n();
  const byDay = new Map(usage.daily.map((d) => [d.day.slice(0, 10), d]));
  const today = new Date();
  const days = Array.from({ length: usage.days }, (_, i) => {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (usage.days - 1 - i), 12);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return { key, date: d, tokens: byDay.get(key)?.tokens ?? 0, answers: byDay.get(key)?.answers ?? 0 };
  });
  if (days.length === 0) return null;
  const max = Math.max(1, ...days.map((d) => d.tokens));
  // Un budget molto più alto dei consumi schiaccerebbe le barre: allora la
  // linea non si disegna e il budget resta scritto sotto.
  const budget = usage.budget_per_day && usage.budget_per_day <= max * 1.5 ? usage.budget_per_day : null;
  const scale = Math.max(max, budget ?? 0);
  const label = (d: (typeof days)[number]) =>
    `${fmt.date(d.date, { day: "numeric", month: "short" })}: ${t("jbx.use.dayTip", { tokens: d.tokens.toLocaleString(fmt.tag), answers: d.answers })}`;
  return (
    <div>
      <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-500">{t("jbx.use.daily")}</p>
      <div className="relative h-28 border-b border-ink-200" role="img"
        aria-label={t("jbx.use.dailyAria", { days: usage.days, total: usage.tokens.toLocaleString(fmt.tag), max: max.toLocaleString(fmt.tag) })}>
        {budget && (
          <div className="absolute inset-x-0 border-t border-dashed border-brand-400" style={{ bottom: `${(budget / scale) * 100}%` }} aria-hidden="true">
            <span className="absolute -top-4 right-0 text-[10px] font-semibold text-brand-700">{t("jbx.use.budget")}</span>
          </div>
        )}
        <div className="flex h-full items-end gap-[2px]">
          {days.map((d) => (
            <div key={d.key} className="group flex h-full min-w-0 flex-1 items-end" title={label(d)}>
              <div className={cn("w-full rounded-t-[3px] transition-colors", d.tokens ? "bg-ink-400 group-hover:bg-brand-500" : "bg-ink-100")}
                style={{ height: d.tokens ? `${Math.max(3, (d.tokens / scale) * 100)}%` : "2px" }} />
            </div>
          ))}
        </div>
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-ink-400">
        <span>{fmt.date(days[0]!.date, { day: "numeric", month: "short" })}</span>
        <span>{fmt.date(days[days.length - 1]!.date, { day: "numeric", month: "short" })}</span>
      </div>
    </div>
  );
}
