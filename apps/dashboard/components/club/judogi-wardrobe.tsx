"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import { COLOR_SWATCH, JUDOGI_COLORS, KIMONO_TYPES, STATUS_TONE, type JudogiColor, type KimonoType } from "@/lib/judogi";

// «Judogis dos atletas» (club/loja.py::staff_judogis): l'armadio di ogni
// atleta che la segreteria e il treinador guardano prima di una prova. Chi
// non ha il bianco o l'azul lo vede subito, e il treinador porta quello del
// club. Che atleti vede chi guarda lo decide il server (la segreteria tutti,
// il treinador quelli dei suoi corsi). Qui anche l'alta competizione, che si
// segna solo negli atleti di un piano che la permette (Grupo 3).

type WardrobeStatus = "PENDING" | "IN_PREPARATION" | "DELIVERED";
type RetireReason = "OUTGROWN" | "WORN_OUT" | "LOST" | "TRADED_IN";

interface OwnedJudogi {
  id: string; kimono_type: KimonoType; type_label: string; color: JudogiColor | null; color_label: string;
  brand: string; size_cm: number; kimono_name: string | null; status: WardrobeStatus; origin: "ORDER" | "MANUAL";
  delivered_on: string | null; small: boolean;
}
interface WardrobeRow {
  athlete_id: string; first_name: string; last_name: string; photo_url: string | null; sex: string; height_cm: number | null;
  white_judogi_declared: boolean; high_competition: boolean; high_competition_flag: boolean; high_competition_allowed: boolean;
  white: OwnedJudogi | null; blue: OwnedJudogi | null; fij: OwnedJudogi[]; judogis: OwnedJudogi[]; missing: ("WHITE" | "BLUE")[];
}
interface Competition { id: string; name: string; starts_on: string; location: string | null }
interface Wardrobe {
  competitions: Competition[]; competition: Competition | null; rows: WardrobeRow[];
  totals: { athletes: number; ready: number; missing_white: number; missing_blue: number };
}

const KEY = ["club", "staff", "loja", "judogis"];
const RETIRE_REASONS: RetireReason[] = ["OUTGROWN", "WORN_OUT", "LOST", "TRADED_IN"];

/** Il colore del chip: verde a posto, giallo piccolo o in arrivo, rosso manca. */
type ChipState = "ok" | "warn" | "missing" | "none";
const CHIP_TONE: Record<ChipState, Tone> = { ok: "success", warn: "warning", missing: "danger", none: "neutral" };

function judogiState(j: OwnedJudogi): ChipState {
  return j.status !== "DELIVERED" || j.small ? "warn" : "ok";
}

export function JudogiWardrobe() {
  const { t } = useI18n();
  const [view, setView] = useState<"race" | "all">("race");
  const [picked, setPicked] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  // Senza competition_id: tutti gli atleti e l'elenco delle prove in arrivo.
  const base = useQuery({ queryKey: [...KEY, "all"], queryFn: () => clubGet<Wardrobe>("/staff/loja/judogis") });
  const competitions = base.data?.competitions ?? [];
  // La prova scelta, o la prima in arrivo: derivata, non sincronizzata.
  const competitionId = picked && competitions.some((c) => c.id === picked) ? picked : competitions[0]?.id ?? null;
  const race = useQuery({
    queryKey: [...KEY, "race", competitionId],
    queryFn: () => clubGet<Wardrobe>(`/staff/loja/judogis?competition_id=${competitionId}`),
    enabled: view === "race" && competitionId != null,
  });
  const current = view === "race" ? race.data : base.data;
  const loading = base.isLoading || (view === "race" && competitionId != null && race.isLoading);
  const needle = q.trim().toLowerCase();
  const rows = (current?.rows ?? []).filter((r) => !needle || `${r.first_name} ${r.last_name}`.toLowerCase().includes(needle));
  // Il dettaglio legge la riga dai dati attuali: dopo un salvataggio si aggiorna da solo.
  const open = openId ? (current?.rows ?? []).find((r) => r.athlete_id === openId) ?? base.data?.rows.find((r) => r.athlete_id === openId) ?? null : null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t("lojaStaff.wardrobe.view")}>
          {(["race", "all"] as const).map((v) => (
            <button key={v} type="button" role="radio" aria-checked={view === v} onClick={() => setView(v)}
              className={cn("min-h-11 cursor-pointer rounded-2xl px-4 text-sm font-bold ring-2 transition-colors motion-reduce:transition-none",
                view === v ? "bg-brand-500 text-white ring-brand-500" : "bg-white text-ink-900 ring-ink-100 hover:ring-ink-200")}>
              {t(v === "race" ? "lojaStaff.wardrobe.viewRace" : "lojaStaff.wardrobe.viewAll")}
            </button>
          ))}
        </div>
        {view === "race" && competitions.length > 1 && (
          <Select value={competitionId ?? ""} onChange={(e) => setPicked(e.target.value)} aria-label={t("lojaStaff.wardrobe.competition")} className="w-auto min-w-0 max-w-xs">
            {competitions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        )}
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("lojaStaff.wardrobe.search")} aria-label={t("lojaStaff.wardrobe.search")}
          className="min-w-0 flex-1 sm:ml-auto sm:max-w-xs" />
      </div>

      {view === "race" && race.data?.competition && <RaceSummary data={race.data} />}

      {loading ? <Skeleton className="h-64" /> : view === "race" && competitionId == null ? (
        <EmptyState icon={<span className="text-3xl">🏆</span>} title={t("lojaStaff.wardrobe.noCompetitions")} text={t("lojaStaff.wardrobe.noCompetitionsText")}
          action={<Button variant="secondary" onClick={() => setView("all")}>{t("lojaStaff.wardrobe.viewAll")}</Button>} />
      ) : rows.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🥋</span>} title={needle ? t("lojaStaff.wardrobe.noMatch") : t("lojaStaff.wardrobe.empty")} />
      ) : (
        <>
          {/* Sul telefono una scheda per atleta, da tavolo la tabella */}
          <ul className="space-y-3 md:hidden">
            {rows.map((r) => (
              <li key={r.athlete_id} className="space-y-3 rounded-3xl bg-white p-4 shadow-soft ring-1 ring-ink-900/5">
                <button type="button" onClick={() => setOpenId(r.athlete_id)} className="flex w-full cursor-pointer items-center gap-3 text-left">
                  <Avatar row={r} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold text-ink-900">{r.first_name} {r.last_name}</span>
                    <span className="block text-xs text-ink-500">{r.height_cm ? `${r.height_cm} cm` : t("lojaStaff.wardrobe.noHeight")}</span>
                  </span>
                  <span className="text-xs font-bold text-brand-700">{t("lojaStaff.wardrobe.details")} ›</span>
                </button>
                <dl className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-1.5 text-xs">
                  <dt className="font-semibold text-ink-500">{t("lojaStaff.wardrobe.white")}</dt><dd><ColorChip row={r} color="WHITE" /></dd>
                  <dt className="font-semibold text-ink-500">{t("lojaStaff.wardrobe.blue")}</dt><dd><ColorChip row={r} color="BLUE" /></dd>
                  <dt className="font-semibold text-ink-500">{t("lojaStaff.wardrobe.fij")}</dt><dd><FijChip row={r} /></dd>
                </dl>
                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ink-100 pt-3">
                  <ForRace row={r} race={view === "race"} />
                  <HighCompetitionToggle row={r} />
                </div>
              </li>
            ))}
          </ul>
          <Table className="hidden md:block">
            <THead>
              <tr>
                <TH>{t("lojaStaff.wardrobe.athlete")}</TH>
                <TH>{t("lojaStaff.wardrobe.height")}</TH>
                <TH>{t("lojaStaff.wardrobe.white")}</TH>
                <TH>{t("lojaStaff.wardrobe.blue")}</TH>
                <TH>{t("lojaStaff.wardrobe.fij")}</TH>
                <TH>{view === "race" ? t("lojaStaff.wardrobe.forRace") : t("lojaStaff.wardrobe.judogis")}</TH>
                <TH>{t("lojaStaff.wardrobe.highCompetition")}</TH>
              </tr>
            </THead>
            <TBody>
              {rows.map((r) => (
                <TR key={r.athlete_id}>
                  <TD>
                    <button type="button" onClick={() => setOpenId(r.athlete_id)} className="flex cursor-pointer items-center gap-3 text-left">
                      <Avatar row={r} />
                      <span className="font-semibold text-ink-900 hover:text-brand-700">{r.first_name} {r.last_name}</span>
                    </button>
                  </TD>
                  <TD className="whitespace-nowrap text-ink-500">{r.height_cm ? `${r.height_cm} cm` : "—"}</TD>
                  <TD><ColorChip row={r} color="WHITE" /></TD>
                  <TD><ColorChip row={r} color="BLUE" /></TD>
                  <TD><FijChip row={r} /></TD>
                  <TD>{view === "race" ? <ForRace row={r} race /> : (
                    <button type="button" onClick={() => setOpenId(r.athlete_id)} className="cursor-pointer text-xs font-semibold text-brand-700 hover:underline">
                      {t("lojaStaff.wardrobe.count", { n: r.judogis.length })} ›
                    </button>
                  )}</TD>
                  <TD><HighCompetitionToggle row={r} /></TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </>
      )}
      <p className="text-xs leading-relaxed text-ink-500">{t("lojaStaff.wardrobe.footer")}</p>
      {open && <AthleteModal row={open} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function Avatar({ row }: { row: WardrobeRow }) {
  return row.photo_url
    // eslint-disable-next-line @next/next/no-img-element -- foto profilo dell'atleta
    ? <img src={row.photo_url} alt="" className="h-9 w-9 shrink-0 rounded-full object-cover ring-1 ring-ink-100" />
    : <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink-100 text-xs font-bold text-ink-600" aria-hidden="true">{row.first_name.slice(0, 1)}{row.last_name.slice(0, 1)}</span>;
}

/** La prova: quanti hanno tutto e che cosa il treinador porta dal clube. */
function RaceSummary({ data }: { data: Wardrobe }) {
  const { t, fmt } = useI18n();
  const c = data.competition!;
  const { totals } = data;
  return (
    <section className="flex flex-wrap items-center gap-6 rounded-3xl bg-ink-900 p-5 text-white">
      <div className="min-w-0 flex-[999_1_320px] space-y-1">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-accent-500">{t("lojaStaff.wardrobe.raceEyebrow", { date: fmt.shortDate(c.starts_on) })}</p>
        <p className="text-xl font-extrabold">{c.name}{c.location ? <span className="font-semibold text-ink-300"> · {c.location}</span> : null}</p>
        <p className="text-sm text-ink-300">{t("lojaStaff.wardrobe.raceText", { n: totals.athletes })}</p>
      </div>
      <div className="flex flex-[1_1_300px] gap-3">
        <div className="flex-1 rounded-2xl bg-ink-800 p-3.5">
          <p className="font-display text-3xl">{totals.ready}</p>
          <p className="text-xs text-ink-300">{t("lojaStaff.wardrobe.ready")}</p>
        </div>
        <div className={cn("flex-1 rounded-2xl p-3.5", totals.missing_white ? "bg-brand-500" : "bg-ink-800")}>
          <p className="font-display text-3xl">{totals.missing_white}</p>
          <p className="text-xs text-white/85">{t("lojaStaff.wardrobe.bringWhite")}</p>
        </div>
        <div className={cn("flex-1 rounded-2xl p-3.5", totals.missing_blue ? "bg-brand-500" : "bg-ink-800")}>
          <p className="font-display text-3xl">{totals.missing_blue}</p>
          <p className="text-xs text-white/85">{t("lojaStaff.wardrobe.bringBlue")}</p>
        </div>
      </div>
    </section>
  );
}

function ColorChip({ row, color }: { row: WardrobeRow; color: "WHITE" | "BLUE" }) {
  const { t } = useI18n();
  const j = color === "WHITE" ? row.white : row.blue;
  if (!j) {
    // Il bianco dichiarato all'iscrizione vale come «ce l'ha» (lo stesso conto del server).
    if (color === "WHITE" && row.white_judogi_declared) return <Badge tone="success">{t("lojaStaff.wardrobe.declared")}</Badge>;
    return <Badge tone="danger">{t("lojaStaff.wardrobe.none")}</Badge>;
  }
  const state = judogiState(j);
  const note = j.status !== "DELIVERED" ? t("lojaStaff.wardrobe.onTheWay") : j.small ? t("lojaStaff.wardrobe.small") : null;
  return (
    <Badge tone={CHIP_TONE[state]} className="whitespace-nowrap">
      {j.brand} {j.size_cm}{note ? ` · ${note}` : ""}
    </Badge>
  );
}

function FijChip({ row }: { row: WardrobeRow }) {
  const { t } = useI18n();
  if (!row.fij.length) return <Badge tone="neutral">—</Badge>;
  const state: ChipState = row.fij.some((j) => judogiState(j) === "ok") ? "ok" : "warn";
  const colors = [...new Set(row.fij.map((j) => j.color).filter((c): c is JudogiColor => c != null))];
  return (
    <Badge tone={CHIP_TONE[state]} className="whitespace-nowrap">
      {colors.map((c) => t(`judo.color.${c}` as "judo.color.WHITE")).join(" + ") || row.fij[0]!.color_label}
    </Badge>
  );
}

/** Per la prova: pronto, o che cosa portare (della taglia dell'atleta). */
function ForRace({ row, race }: { row: WardrobeRow; race: boolean }) {
  const { t } = useI18n();
  if (!row.missing.length) {
    const small = [row.white, row.blue].some((j) => j?.small);
    return <span className={cn("text-xs font-semibold", small ? "text-accent-800" : "text-emerald-700")}>{small ? t("lojaStaff.wardrobe.smallWarn") : t("lojaStaff.wardrobe.readyOne")}</span>;
  }
  const what = row.missing.map((m) => t(m === "WHITE" ? "lojaStaff.wardrobe.white" : "lojaStaff.wardrobe.blue").toLowerCase()).join(" + ");
  return (
    <span className="text-xs font-semibold text-brand-700">
      {race ? t("lojaStaff.wardrobe.bring", { what }) : t("lojaStaff.wardrobe.missing", { what })}
      {row.height_cm ? ` · ${row.height_cm} cm` : ""}
    </span>
  );
}

function HighCompetitionToggle({ row }: { row: WardrobeRow }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const on = row.high_competition_flag;
  // Un segno rimasto da un piano di prima si può sempre togliere.
  const locked = !row.high_competition_allowed && !on;

  async function toggle() {
    setBusy(true);
    try {
      await clubSend(`/staff/loja/athletes/${row.athlete_id}/high-competition`, "PUT", { value: !on });
      await queryClient.invalidateQueries({ queryKey: KEY });
      toast({ tone: "success", title: !on ? t("lojaStaff.high.on", { name: row.first_name }) : t("lojaStaff.high.off", { name: row.first_name }) });
    } catch (e) {
      toast({ tone: "error", title: t("lojaStaff.high.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const hint = locked ? t("lojaStaff.high.notAllowed") : on && !row.high_competition_allowed ? t("lojaStaff.high.stale") : undefined;
  return (
    <span className="inline-flex items-center gap-2" title={hint}>
      <button type="button" role="switch" aria-checked={on} disabled={locked || busy} onClick={() => void toggle()}
        aria-label={t("lojaStaff.high.label", { name: `${row.first_name} ${row.last_name}` })}
        className={cn("relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full transition-colors motion-reduce:transition-none disabled:cursor-not-allowed",
          on ? (row.high_competition_allowed ? "bg-brand-500" : "bg-accent-500") : "bg-ink-300", locked && "opacity-50", busy && "opacity-70")}>
        <span className={cn("absolute h-6 w-6 rounded-full bg-white shadow transition-all motion-reduce:transition-none", on ? "right-0.5" : "left-0.5")} />
      </button>
      {hint && <span className="max-w-[10rem] text-[11px] leading-tight text-ink-500">{hint}</span>}
    </span>
  );
}

// --- Il dettaglio di un atleta ---------------------------------------------------------------------

function AthleteModal({ row, onClose }: { row: WardrobeRow; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [retiring, setRetiring] = useState<string | null>(null);
  const [reason, setReason] = useState<RetireReason>("OUTGROWN");
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);

  async function retire(j: OwnedJudogi) {
    setBusy(true);
    try {
      await clubSend(`/staff/loja/judogis/${j.id}/retire`, "POST", { reason });
      await queryClient.invalidateQueries({ queryKey: KEY });
      toast({ tone: "success", title: t("lojaStaff.detail.retired") });
      setRetiring(null);
    } catch (e) {
      toast({ tone: "error", title: t("common.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} size="lg" title={`${row.first_name} ${row.last_name}`}
      subtitle={[row.height_cm ? `${row.height_cm} cm` : t("lojaStaff.wardrobe.noHeight"), row.high_competition ? `🏅 ${t("lojaStaff.wardrobe.highCompetition")}` : null].filter(Boolean).join(" · ")}
      footer={<Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>}>
      <div className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-ink-50 p-3">
          <span className="text-sm font-semibold text-ink-800">{t("lojaStaff.wardrobe.highCompetition")}</span>
          <HighCompetitionToggle row={row} />
        </div>

        <section className="space-y-2">
          <p className="text-xs font-bold uppercase tracking-wide text-ink-500">{t("lojaStaff.detail.title")}</p>
          {row.judogis.length === 0 ? (
            <p className="rounded-2xl bg-ink-50 p-4 text-sm text-ink-600">
              {row.white_judogi_declared ? t("lojaStaff.detail.emptyDeclared") : t("lojaStaff.detail.empty")}
            </p>
          ) : (
            <ul className="space-y-2">
              {row.judogis.map((j) => (
                <li key={j.id} className="space-y-2 rounded-2xl p-3 ring-1 ring-ink-100">
                  <div className="flex items-start gap-3">
                    <span className={cn("mt-0.5 h-7 w-7 shrink-0 rounded-full ring-2", j.color ? COLOR_SWATCH[j.color] : "bg-ink-100 ring-ink-200")} aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-ink-900">{j.brand} · {j.size_cm} cm</p>
                      <p className="text-xs text-ink-600">
                        {t(`judo.type.${j.kimono_type}` as "judo.type.TRAINING")} · {j.color ? t(`judo.color.${j.color}` as "judo.color.WHITE") : j.color_label}
                      </p>
                      <p className="text-xs text-ink-500">
                        {j.kimono_name ? <>✍️ «{j.kimono_name}» · </> : null}
                        {j.origin === "MANUAL" ? t("lojaStaff.detail.originManual") : t("lojaStaff.detail.originOrder")}
                        {j.delivered_on ? ` · ${fmt.shortDate(j.delivered_on)}` : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <Badge tone={STATUS_TONE[j.status]}>{t(`judo.status.${j.status}` as "judo.status.PENDING")}</Badge>
                      {j.small && <Badge tone="warning">{t("lojaStaff.wardrobe.small")}</Badge>}
                    </div>
                  </div>
                  {j.status === "DELIVERED" && (retiring === j.id ? (
                    <div className="flex flex-wrap items-center gap-2 rounded-xl bg-ink-50 p-2">
                      <Select value={reason} onChange={(e) => setReason(e.target.value as RetireReason)} aria-label={t("lojaStaff.detail.reason")} className="h-10 w-auto min-w-0 flex-1">
                        {RETIRE_REASONS.map((r) => <option key={r} value={r}>{t(`lojaStaff.retire.${r}` as "lojaStaff.retire.OUTGROWN")}</option>)}
                      </Select>
                      <Button size="sm" loading={busy} onClick={() => void retire(j)}>{t("lojaStaff.detail.retireConfirm")}</Button>
                      <Button size="sm" variant="ghost" onClick={() => setRetiring(null)}>{t("common.cancel")}</Button>
                    </div>
                  ) : (
                    <button type="button" onClick={() => { setRetiring(j.id); setReason(j.small ? "OUTGROWN" : "WORN_OUT"); }}
                      className="cursor-pointer text-xs font-semibold text-rose-700 hover:underline">{t("lojaStaff.detail.retire")}</button>
                  ))}
                </li>
              ))}
            </ul>
          )}
        </section>

        {adding ? <AddOwnedForm row={row} onDone={() => setAdding(false)} /> : (
          <Button variant="secondary" onClick={() => setAdding(true)}>＋ {t("lojaStaff.add.open")}</Button>
        )}
      </div>
    </Modal>
  );
}

/** Un judogi che l'atleta aveva già (comprato fuori, ereditato): entra
 *  nell'armadio senza prezzo né quota. */
function AddOwnedForm({ row, onDone }: { row: WardrobeRow; onDone: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [type, setType] = useState<KimonoType>("TRAINING");
  const [color, setColor] = useState<JudogiColor>(row.missing[0] ?? "WHITE");
  const [brand, setBrand] = useState("");
  const [size, setSize] = useState(row.height_cm ? String(row.height_cm) : "");
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const sizeCm = Number(size);
  const valid = brand.trim().length >= 2 && Number.isInteger(sizeCm) && sizeCm >= 80 && sizeCm <= 220;

  async function save() {
    setBusy(true);
    try {
      await clubSend("/staff/loja/judogis", "POST", {
        athlete_id: row.athlete_id, kimono_type: type, color, brand: brand.trim(), size_cm: sizeCm,
        kimono_name: name.trim() || null, notes: notes.trim() || null,
      });
      await queryClient.invalidateQueries({ queryKey: KEY });
      toast({ tone: "success", title: t("lojaStaff.add.saved") });
      onDone();
    } catch (e) {
      toast({ tone: "error", title: t("common.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded-2xl p-4 ring-1 ring-ink-100">
      <div>
        <p className="font-semibold text-ink-900">{t("lojaStaff.add.title")}</p>
        <p className="text-xs text-ink-500">{t("lojaStaff.add.hint")}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("lojaStaff.add.type")} htmlFor="jw-type">
          <Select id="jw-type" value={type} onChange={(e) => setType(e.target.value as KimonoType)}>
            {KIMONO_TYPES.map((k) => <option key={k} value={k}>{t(`judo.type.${k}` as "judo.type.TRAINING")}</option>)}
          </Select>
        </Field>
        <Field label={t("judo.trade.color")} htmlFor="jw-color">
          <Select id="jw-color" value={color} onChange={(e) => setColor(e.target.value as JudogiColor)}>
            {JUDOGI_COLORS.map((c) => <option key={c} value={c}>{t(`judo.color.${c}` as "judo.color.WHITE")}</option>)}
          </Select>
        </Field>
        <Field label={t("judo.trade.brand")} htmlFor="jw-brand">
          <Input id="jw-brand" value={brand} maxLength={60} onChange={(e) => setBrand(e.target.value)} placeholder="Adidas, Mizuno…" />
        </Field>
        <Field label={t("lojaStaff.add.size")} hint={t("lojaStaff.add.sizeHint")} htmlFor="jw-size">
          <Input id="jw-size" inputMode="numeric" maxLength={3} value={size} onChange={(e) => setSize(e.target.value.replace(/\D/g, ""))} />
        </Field>
        <Field label={t("lojaStaff.add.name")} hint={t("lojaStaff.add.nameHint")} htmlFor="jw-name">
          <Input id="jw-name" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label={t("lojaStaff.add.notes")} htmlFor="jw-notes">
          <Input id="jw-notes" value={notes} maxLength={2000} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>{t("common.cancel")}</Button>
        <Button loading={busy} disabled={!valid} onClick={() => void save()}>{t("lojaStaff.add.save")}</Button>
      </div>
    </section>
  );
}
