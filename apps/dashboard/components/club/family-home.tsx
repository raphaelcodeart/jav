"use client";

import { useJavbotPayRequest } from "@/lib/javbot";
import { motion } from "motion/react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge, FeeStatusPill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ActionButton } from "@/components/ui/gamification";
import { Skeleton } from "@/components/ui/skeleton";
import { StatTile } from "@/components/ui/stat-tile";
import { AthleteDetailModal } from "@/components/club/athlete-detail-modal";
import { AthleteFormModal } from "@/components/club/athlete-form-modal";
import { AthleteHealthCard } from "@/components/club/athlete-health-card";
import { FamilyAccountingCard } from "@/components/club/family-accounting";
import { FamilyToday } from "@/components/club/family-today";
import { InviteCard } from "@/components/club/invite-card";
import { useClubFeatures } from "@/components/club/jav-courses";
import { FamilyMonthCard } from "@/components/club/month-board";
import { PayModal } from "@/components/club/pay-modal";
import { clubGet, type AthleteSeasonMonths, type Family } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

/** The parent's home: one card per child, three big buttons, and what is
 *  due -- nothing else competes for attention. */
export function FamilyHome({ onNavigate, familyOverride }: { onNavigate: (key: string) => void; familyOverride?: Family }) {
  const { data: fetched, isLoading, error } = useQuery({
    queryKey: ["club", "family"],
    queryFn: () => clubGet<Family>("/family"),
    enabled: !familyOverride,
  });
  const family = familyOverride ?? fetched;
  // "choose": il genitore dice prima che cosa ha pagato (quote o ordine
  // dello Shop); "fees": arriva dalle quote, si va dritti a quelle.
  const [pay, setPay] = useState<"choose" | "fees" | null>(null);
  // Dalla card «Questo mese»: le quote del mese già scelte.
  const [payIds, setPayIds] = useState<string[] | null>(null);
  // Il pulsante "Carica un pagamento" di JAVBOT apre la stessa finestra.
  useJavbotPayRequest(setPay);
  const [addOpen, setAddOpen] = useState(false);
  const [openAthlete, setOpenAthlete] = useState<string | null>(null);
  // Dal grafico delle mensilità la scheda si apre sulle quote.
  const [openOnFees, setOpenOnFees] = useState(false);
  // Nei corsi JAV nelle scuole niente gare: al loro posto, i corsi.
  const features = useClubFeatures();
  const { t, fmt } = useI18n();
  const { euro, shortDate } = fmt;
  const euroFmt = (n: number) => fmt.euroUnits(n, { maximumFractionDigits: 0 });

  if (isLoading && !family) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-32" />
        <div className="grid sm:grid-cols-3 gap-4">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }
  if (error && !family) {
    return <EmptyState title={t("family.clubDown")} text={(error as Error).message} action={<Button onClick={() => location.reload()}>{t("common.retry")}</Button>} />;
  }
  if (!family) return null;

  const noAthletes = family.athletes.length === 0;

  return (
    <div className="space-y-8">
      {/* Hero */}
      <motion.section
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-[32px] bg-gradient-to-br from-ink-900 via-ink-800 to-brand-800 text-white p-6 sm:p-8"
      >
        <div className="absolute inset-0 opacity-30 bg-[radial-gradient(circle_at_85%_15%,#f9e40f,transparent_35%),radial-gradient(circle_at_10%_100%,#e43f21,transparent_45%)]" aria-hidden="true" />
        <div className="absolute -right-6 -top-10 font-display text-[11rem] leading-none text-white/5 select-none" aria-hidden="true">柔道</div>
        <div className="relative flex flex-col lg:flex-row lg:items-end justify-between gap-6">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-300">{t("club.season", { season: family.season_label })}</p>
            <h2 className="text-3xl sm:text-4xl mt-2 leading-tight">
              {t("family.heroTitle")}
              <br />
              <span className="text-accent-300">{t("family.heroTitleAccent")}</span>
            </h2>
            <p className="text-white/75 mt-3 max-w-md text-sm">
              {noAthletes
                ? t("family.heroEmpty")
                : family.due_cents > 0
                  ? t("family.heroDue", { amount: euro(family.due_cents) })
                  : t("family.heroAllPaid")}
            </p>
          </div>
          <div className="flex -space-x-3">
            {family.athletes.slice(0, 5).map((a, i) => (
              <motion.div
                key={a.id}
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.2 + i * 0.08, type: "spring" }}
                className="h-14 w-14 rounded-full ring-4 ring-ink-900 overflow-hidden bg-gradient-to-br from-brand-400 to-brand-700 flex items-center justify-center font-display text-lg"
              >
                {a.photo_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={a.photo_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  a.first_name.slice(0, 1)
                )}
              </motion.div>
            ))}
          </div>
        </div>
      </motion.section>

      {/* Prima di tutto il mese corrente: quanto paga ogni figlio e se è pagato. */}
      {!noAthletes && family.this_month && (
        <FamilyMonthCard board={family.this_month} onPay={(ids) => { setPayIds(ids); setPay("fees"); }} />
      )}

      {/* The three things a parent comes here to do */}
      <section className="grid sm:grid-cols-3 gap-4">
        <ActionButton icon="📸" title={t("family.actionPay")} text={t("family.actionPayText")} onClick={() => setPay("choose")} />
        {features.competitions ? (
          <ActionButton icon="🏆" title={t("family.actionCompete")} text={family.open_competitions > 0 ? t("family.actionCompeteOpen", { n: family.open_competitions }) : t("family.actionCompeteText")} tone="accent" onClick={() => onNavigate("club-competitions")} />
        ) : (
          <ActionButton icon="🏫" title={t("javCourses.familyAction")} text={t("javCourses.familyActionText")} tone="accent" onClick={() => onNavigate("club-courses")} />
        )}
        <ActionButton icon="🥋" title={t("family.actionShop")} text={t("family.actionShopText")} tone="ink" onClick={() => onNavigate("products")} />
      </section>

      {/* L'area di ogni atleta: la sua pagina (lezioni, presenza, traguardi),
          e da lì il genitore crea l'accesso del figlio. */}
      {!noAthletes && (
        <a href="/atleta" className="group flex items-center justify-between gap-4 rounded-3xl bg-ink-950 p-5 text-white shadow-lift transition hover:-translate-y-0.5">
          <span className="flex items-center gap-4">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-400 text-2xl" aria-hidden="true">🥋</span>
            <span>
              <span className="block font-semibold">{t("family.athleteArea")}</span>
              <span className="block text-sm text-white/70">{t("family.athleteAreaText")}</span>
            </span>
          </span>
          <span aria-hidden="true" className="text-xl transition-transform group-hover:translate-x-1">→</span>
        </a>
      )}

      {!noAthletes && <FamilyToday />}

      {/* Numbers */}
      <section className={`grid grid-cols-2 ${features.competitions ? "lg:grid-cols-4" : "lg:grid-cols-3"} gap-4`}>
        <StatTile label={t("family.statDue")} value={family.due_cents / 100} format={euroFmt} accent="brand" icon={<span className="text-lg">💶</span>} onClick={() => setPay("fees")} />
        <StatTile label={t("family.statOverdue")} value={family.overdue_cents / 100} format={euroFmt} accent="ink" icon={<span className="text-lg">⏰</span>} />
        <StatTile label={t("family.statPaid")} value={family.paid_season_cents / 100} format={euroFmt} accent="success" icon={<span className="text-lg">✅</span>} />
        {features.competitions && <StatTile label={t("family.statOpenCompetitions")} value={family.open_competitions} accent="accent" icon={<span className="text-lg">🏟️</span>} onClick={() => onNavigate("club-competitions")} />}
      </section>

      {!noAthletes && (family.season_months ?? []).length > 0 && (
        <SeasonChart rows={family.season_months!} season={family.season_label} onOpen={(id) => { setOpenOnFees(true); setOpenAthlete(id); }} />
      )}

      {!noAthletes && <FamilyAccountingCard onOpen={() => onNavigate("club-accounting")} />}

      {/* Athletes */}
      <section>
        <div className="flex items-end justify-between gap-3 mb-4">
          <div>
            <h2 className="text-xl text-ink-900">{t("family.athletesTitle")}</h2>
            <p className="text-sm text-ink-500">{t("family.athletesHint")}</p>
          </div>
          <Button variant="secondary" onClick={() => setAddOpen(true)} icon={<span>＋</span>}>
            {t("family.add")}
          </Button>
        </div>
        {noAthletes ? (
          <EmptyState
            icon={<span className="text-3xl">🥋</span>}
            title={t("family.noAthletes")}
            text={t("family.noAthletesText")}
            action={<Button size="lg" onClick={() => setAddOpen(true)}>{t("family.addFirst")}</Button>}
          />
        ) : (
          <div className="space-y-6">
            {family.athletes.map((a) => (
              <div key={a.id} className="space-y-2">
                <AthleteHealthCard athlete={a} mode="family" onAction={(code) => {
                  if (code === "ANNUAL_FEE") { setPay("fees"); return; }
                  if (code === "JUDOGI_COLOUR") { onNavigate("products"); return; }
                  setOpenOnFees(false); setOpenAthlete(a.id);
                }} />
                <div className="flex justify-end">
                  <Button size="sm" variant="secondary" onClick={() => { setOpenOnFees(false); setOpenAthlete(a.id); }}>{t("health.openCard")} →</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Due fees and recent payments */}
      {!noAthletes && (
        <section className="grid lg:grid-cols-2 gap-6">
          <div className="glass-card rounded-3xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base text-ink-900">{t("family.dueFees")}</h3>
              {family.due_fees.length > 0 && <Button size="sm" onClick={() => setPay("fees")}>{t("family.payNow")}</Button>}
            </div>
            {family.due_fees.length === 0 ? (
              <p className="text-sm text-ink-500 py-6 text-center">{t("family.noDueFees")}</p>
            ) : (
              <div className="space-y-2">
                {family.due_fees.slice(0, 6).map((f, i) => (
                  <motion.div key={f.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }} className="flex items-center justify-between gap-3 rounded-2xl bg-white ring-1 ring-ink-100 px-4 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-ink-900 truncate">{f.description}</p>
                      <p className="text-xs text-ink-500">{f.athlete_name} · {t("club.dueOn", { date: shortDate(f.due_date) })}</p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="font-display text-ink-900">{euro(f.amount_cents)}</p>
                      <FeeStatusPill status={f.status} overdue={f.overdue} />
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
          <div className="glass-card rounded-3xl p-5">
            <h3 className="text-base text-ink-900 mb-4">{t("family.proofsTitle")}</h3>
            {family.recent_proofs.length === 0 ? (
              <p className="text-sm text-ink-500 py-6 text-center">{t("family.proofsEmpty")}</p>
            ) : (
              <div className="space-y-2">
                {family.recent_proofs.slice(0, 6).map((p) => (
                  <div key={p.id} className="flex items-center justify-between gap-3 rounded-2xl bg-white ring-1 ring-ink-100 px-4 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-ink-900">{euro(p.amount_cents)} · {t(p.fees.length === 1 ? "club.feeCountOne" : "club.feeCountMany", { n: p.fees.length })}</p>
                      <p className="text-xs text-ink-500 truncate">{shortDate(p.created_at)} · {p.original_filename}</p>
                      {p.rejection_reason && <p className="text-xs text-rose-600 mt-0.5">{t("family.rejectionReason", { reason: p.rejection_reason })}</p>}
                    </div>
                    <Badge tone={p.status === "REJECTED" ? "danger" : "success"} dot>
                      {p.status === "REJECTED" ? t("family.proofRejected") : t("family.proofAccepted")}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      )}

      {!noAthletes && <InviteCard />}

      {pay && (
        <PayModal
          open
          onClose={() => { setPay(null); setPayIds(null); }}
          fees={family.due_fees}
          preselect={pay === "fees" ? (payIds ?? family.due_fees.map((f) => f.id)) : undefined}
        />
      )}
      {addOpen && <AthleteFormModal open={addOpen} onClose={() => setAddOpen(false)} />}
      <AthleteDetailModal key={`${openAthlete}-${openOnFees}`} athleteId={openAthlete} initialTab={openOnFees ? "fees" : "path"} onClose={() => setOpenAthlete(null)} />
    </div>
  );
}

const SEGMENTS = [
  { key: "paid_cents", months: "months_paid", label: "months.paid", color: "#1baf7a" },
  { key: "due_cents", months: "months_due", label: "months.due", color: "#eda100" },
  { key: "overdue_cents", months: "months_overdue", label: "months.overdue", color: "#d63a2f" },
] as const;

/** Una barra per atleta: la stagione divisa in pagato, da pagare e scaduto.
 *  Toccandola si apre la scheda dell'atleta, sulle sue mensilità. */
function SeasonChart({ rows, season, onOpen }: { rows: AthleteSeasonMonths[]; season: string; onOpen: (id: string) => void }) {
  const { t, fmt } = useI18n();
  const max = Math.max(1, ...rows.map((r) => r.paid_cents + r.due_cents + r.overdue_cents));
  return (
    <section className="glass-card rounded-3xl p-5">
      <h3 className="text-base text-ink-900">{t("family.seasonChartTitle")}</h3>
      <p className="text-sm text-ink-500">{t("family.seasonChartHint", { season })}</p>
      <ul className="mt-4 space-y-3">
        {rows.map((r, i) => {
          const total = r.paid_cents + r.due_cents + r.overdue_cents;
          return (
            <li key={r.athlete_id}>
              <button type="button" onClick={() => onOpen(r.athlete_id)} className="w-full text-left cursor-pointer group">
                <span className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="font-semibold text-ink-900 group-hover:text-brand-700">{r.first_name}</span>
                  <span className="text-xs text-ink-500">
                    {t("months.paidOf", { paid: r.months_paid, total: r.months_paid + r.months_due + r.months_overdue })}
                    {r.overdue_cents > 0 && <span className="ml-2 font-semibold text-rose-600">{t("months.overdue")}: {fmt.euro(r.overdue_cents)}</span>}
                  </span>
                </span>
                <span className="mt-1.5 flex h-4 overflow-hidden rounded-full bg-ink-100" style={{ width: `${Math.max(8, (total / max) * 100)}%` }}
                  role="img" aria-label={SEGMENTS.map((sg) => `${t(sg.label)} ${fmt.euro(r[sg.key])}`).join(", ")}>
                  {SEGMENTS.filter((sg) => r[sg.key] > 0).map((sg) => (
                    <motion.span key={sg.key} initial={{ width: 0 }} animate={{ width: `${(r[sg.key] / Math.max(1, total)) * 100}%` }}
                      transition={{ delay: i * 0.08 }} className="h-full" style={{ background: sg.color }} title={`${t(sg.label)}: ${fmt.euro(r[sg.key])}`} />
                  ))}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <ul className="mt-4 flex flex-wrap gap-4 text-xs text-ink-600">
        {SEGMENTS.map((sg) => (
          <li key={sg.key} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: sg.color }} />{t(sg.label)}</li>
        ))}
      </ul>
    </section>
  );
}
