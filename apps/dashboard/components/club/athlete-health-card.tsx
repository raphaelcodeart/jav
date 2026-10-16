"use client";

import { MotionConfig, motion } from "motion/react";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { BeltBadge } from "@/components/ui/belt";
import { useToast } from "@/components/ui/toast";
import { clubSend, type AthleteCard, type Obligations } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// La scheda «salute sportiva» dell'atleta: la foto (si carica toccando il
// cerchio, come su un social), i dati (età, gruppo, categoria, peso,
// cintura, club), i numeri (lezioni, gare, medaglie, punti) e la fascia
// degli obblighi (apps/api/app/domains/club/obligations.py): judogi
// colorato, judogi bianco, certificato medico, quota annuale, e se può fare
// gare. In cima all'area dell'atleta e, compatta, nella pagina della famiglia.

export type HealthCardAthlete = AthleteCard;

const ICON: Record<string, string> = { JUDOGI_COLOUR: "🥋", WHITE_JUDOGI: "🤍", CERTIFICATE: "🩺", ANNUAL_FEE: "🪪" };

export function AthleteHealthCard({ athlete: a, mode, onChanged, onAction }: {
  athlete: HealthCardAthlete;
  /** `area`: l'area dell'atleta (foto e judogi bianco da qui); `family`: la pagina del genitore. */
  mode: "area" | "family";
  onChanged?: () => void;
  /** Il tocco su un obbligo: certificato, quota, judogi (chi ospita decide dove portare). */
  onAction?: (code: string) => void;
}) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState(false);
  const o = a.obligations;
  const medals = a.medals.gold + a.medals.silver + a.medals.bronze;

  async function uploadPhoto(file: File) {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      await clubSend(mode === "area" ? `/athlete-area/${a.id}/photo` : `/athletes/${a.id}/photo`, "POST", form);
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: t("health.photoSaved") });
      onChanged?.();
    } catch (e) {
      toast({ tone: "error", title: t("health.photoFailed"), text: (e as Error).message });
    } finally {
      setUploading(false);
    }
  }

  async function setWhite(value: boolean) {
    try {
      if (mode === "area") await clubSend(`/athlete-area/${a.id}/white-judogi`, "PUT", { white_judogi: value });
      else await clubSend(`/athletes/${a.id}`, "PATCH", { white_judogi: value });
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      onChanged?.();
    } catch (e) {
      toast({ tone: "error", title: t("health.saveFailed"), text: (e as Error).message });
    }
  }

  const facts: [string, string][] = [
    [t("health.age"), `${a.age} · ${t("health.federal", { n: a.federal_age ?? a.season_age })}`],
    [t("health.group"), a.age_band ? t.dyn(`club.ageBand.${a.age_band}`, a.age_band) : "—"],
    [t("health.category"), a.weight_category ?? "—"],
    [t("health.weight"), a.weight_kg ? `${Number(a.weight_kg).toLocaleString()} kg` : "—"],
  ];
  const stats: [string, string, string][] = [
    ["🥋", String(a.attendances), t("health.lessons")],
    ["🏟️", String(a.competitions_count ?? 0), t("health.competitions")],
    ["🏅", String(medals), t("health.medals")],
    ["⭐", String(a.ranking_points), t("health.points")],
  ];

  return (
    <MotionConfig reducedMotion="user">
      <section className="overflow-hidden rounded-[2rem] bg-white shadow-lift ring-1 ring-ink-900/5">
        <div className="relative bg-gradient-to-br from-brand-500 via-brand-600 to-ink-900 p-5 text-white sm:p-7">
          <div className="pointer-events-none absolute -bottom-12 -right-4 select-none font-display text-[10rem] leading-none text-white/10" aria-hidden="true">柔</div>
          <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center">
            {/* La foto: un cerchio che si tocca per caricarla, come su un social. */}
            <label className={cn("group relative mx-auto h-28 w-28 shrink-0 cursor-pointer sm:mx-0", uploading && "pointer-events-none opacity-70")}
              title={t("health.changePhoto")}>
              <span className="absolute inset-0 rounded-full bg-gradient-to-tr from-accent-300 via-white to-accent-500 p-[3px]">
                <span className="flex h-full w-full items-center justify-center overflow-hidden rounded-full bg-ink-800">
                  {a.photo_url
                    // eslint-disable-next-line @next/next/no-img-element -- foto caricata dalla famiglia o dall'atleta
                    ? <img src={a.photo_url} alt="" className="h-full w-full object-cover" />
                    : <span className="font-display text-4xl">{a.first_name.slice(0, 1)}{a.last_name.slice(0, 1)}</span>}
                </span>
              </span>
              <span className="absolute bottom-0 right-0 flex h-9 w-9 items-center justify-center rounded-full bg-accent-400 text-lg text-ink-900 shadow-lg ring-4 ring-brand-700 transition group-hover:scale-110">
                {uploading ? "…" : "📷"}
              </span>
              <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void uploadPhoto(f); e.target.value = ""; }} />
            </label>
            <div className="min-w-0 flex-1 text-center sm:text-left">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-200">{a.club_name ?? ""}</p>
              <h2 className="font-display text-3xl leading-tight sm:text-4xl">{a.first_name} {a.last_name}</h2>
              <div className="mt-2 flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                {a.belt && <span className="inline-flex rounded-full bg-white/95 px-3 py-1"><BeltBadge belt={a.belt} size="sm" /></span>}
                {a.plan && <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-semibold ring-1 ring-white/25">{a.plan.name}</span>}
                <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-semibold ring-1 ring-white/25">{t("athlete.levelLabel")} {a.level}</span>
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-2 sm:w-72">
              {facts.map(([label, value]) => (
                <div key={label} className="rounded-2xl bg-white/12 px-3 py-2 ring-1 ring-white/20 backdrop-blur">
                  <dt className="text-[10px] font-bold uppercase tracking-wider text-white/70">{label}</dt>
                  <dd className="truncate text-sm font-semibold">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
          <ul className="relative mt-5 grid grid-cols-4 gap-2">
            {stats.map(([icon, value, label], i) => (
              <motion.li key={label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 * i }}
                className="rounded-2xl bg-white/10 px-2 py-2.5 text-center ring-1 ring-white/15">
                <p className="text-lg" aria-hidden="true">{icon}</p>
                <p className="font-display text-2xl leading-none">{value}</p>
                <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-white/75">{label}</p>
              </motion.li>
            ))}
          </ul>
        </div>

        {/* La fascia degli obblighi */}
        {o && (
          <div className="space-y-3 p-4 sm:p-5">
            <div className={cn("flex flex-wrap items-center justify-between gap-2 rounded-2xl px-4 py-3",
              o.can_compete ? "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200" : "bg-amber-50 text-amber-900 ring-1 ring-amber-300")}>
              <p className="font-semibold">
                {o.can_compete ? `✅ ${t("health.canCompete")}` : `⚠️ ${t("health.cannotCompete")}`}
              </p>
              {!o.can_compete && <p className="text-xs">{o.compete_missing.map((c) => t.dyn(`health.need.${c}`, c)).join(" · ")}</p>}
            </div>
            <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {o.items.map((i) => (
                <li key={i.code}>
                  <button type="button" onClick={() => onAction?.(i.code)}
                    className={cn("flex h-full w-full cursor-pointer items-start gap-3 rounded-2xl p-3 text-left ring-2 transition hover:-translate-y-0.5",
                      i.ok ? "bg-emerald-50/60 ring-emerald-200" : "bg-rose-50 ring-rose-300 animate-[pulse_3s_ease-in-out_infinite]")}>
                    <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-xl", i.ok ? "bg-emerald-500" : "bg-rose-500")}>
                      <span aria-hidden="true">{ICON[i.code]}</span>
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-ink-900">{i.ok ? "✓ " : "! "}{t.dyn(`health.item.${i.code}`, i.code)}</span>
                      <span className="block text-xs text-ink-600">{detail(i, t, fmt)}</span>
                    </span>
                  </button>
                  {i.code === "WHITE_JUDOGI" && (
                    <label className="mt-1.5 flex cursor-pointer items-center gap-2 px-1 text-xs text-ink-600">
                      <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={!!a.white_judogi} onChange={(e) => void setWhite(e.target.checked)} />
                      {t("health.haveWhite")}
                    </label>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </MotionConfig>
  );
}

function detail(i: Obligations["items"][number], t: ReturnType<typeof useI18n>["t"], fmt: ReturnType<typeof useI18n>["fmt"]): string {
  switch (i.code) {
    case "JUDOGI_COLOUR":
      return i.ok ? t.dyn(`health.orderStatus.${i.status ?? "DELIVERED"}`, i.status ?? "") : t.dyn(`health.rule.${i.rule ?? "BLUE"}`, "");
    case "WHITE_JUDOGI":
      return i.ok ? t("health.whiteOk") : t("health.whiteMissing");
    case "CERTIFICATE":
      return t.dyn(`health.cert.${i.state ?? "MISSING"}`, i.state ?? "");
    case "ANNUAL_FEE":
      return i.state === "DUE" ? t("health.annualDue", { amount: fmt.euro(i.due_cents ?? 0) }) : t.dyn(`health.annual.${i.state ?? "NOT_ISSUED"}`, i.state ?? "");
    default:
      return "";
  }
}
