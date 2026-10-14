"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, FeeStatusPill } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import {
  PERSON_KIND_ICONS,
  clubGet,
  clubSend,
  hoursLabel,
  type AbsenceRow,
  type DayAttendance,
  type Person,
  type PersonCard,
  type PersonKind,
  type StaffHours,
} from "@/lib/club";
import { MoveToClubModal, useClubFeatures } from "@/components/club/jav-courses";
import { useI18n } from "@/lib/i18n/provider";

const A = (path: string) => `/admin${path}`;
const KIND_ORDER: PersonKind[] = ["ATHLETE", "PARENT", "COACH", "ASSISTANT_COACH", "MONITOR", "ASSISTANT_MONITOR", "SECRETARY"];

/** I simboli di una persona, con il nome del tipo al passaggio del mouse. */
export function KindIcons({ kinds }: { kinds: PersonKind[] }) {
  const { t } = useI18n();
  return (
    <span className="inline-flex gap-1">
      {kinds.map((k) => (
        <span key={k} title={t.dyn(`people.kind.${k}`, k)} aria-label={t.dyn(`people.kind.${k}`, k)}
          className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-ink-50 text-base">
          {PERSON_KIND_ICONS[k]}
        </span>
      ))}
    </span>
  );
}

// --- Persone -------------------------------------------------------------------------------------

/** Tutte le persone del club in un elenco: un filtro per tipo (con il suo
 *  simbolo e quanti sono), la ricerca, e da ogni nome la scheda con debiti,
 *  pagamenti, risultati e investimenti. */
export function PeoplePanel({ canInvest = false }: { canInvest?: boolean }) {
  const { t, fmt } = useI18n();
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "people"], queryFn: () => clubGet<Person[]>(A("/people")) });
  const [kind, setKind] = useState<PersonKind | "ALL">("ALL");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Person | null>(null);
  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const p of data ?? []) for (const k of p.kinds) out[k] = (out[k] ?? 0) + 1;
    return out;
  }, [data]);
  const rows = (data ?? []).filter((p) =>
    (kind === "ALL" || p.kinds.includes(kind)) &&
    (!q || `${p.name} ${p.email ?? ""} ${p.guardian_name ?? ""}`.toLowerCase().includes(q.toLowerCase())),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => setKind("ALL")}
          className={`rounded-full px-4 py-2 text-sm font-semibold ring-1 cursor-pointer ${kind === "ALL" ? "bg-ink-900 text-white ring-ink-900" : "bg-white ring-ink-200"}`}>
          {t("people.all")} · {data?.length ?? 0}
        </button>
        {KIND_ORDER.map((k) => (
          <button key={k} type="button" onClick={() => setKind(k)}
            className={`rounded-full px-4 py-2 text-sm font-semibold ring-1 cursor-pointer ${kind === k ? "bg-brand-500 text-white ring-brand-500" : "bg-white ring-ink-200 hover:ring-ink-300"}`}>
            <span className="mr-1">{PERSON_KIND_ICONS[k]}</span>{t.dyn(`people.kind.${k}`, k)} · {counts[k] ?? 0}
          </button>
        ))}
      </div>
      <Input placeholder={t("people.search")} value={q} onChange={(e) => setQ(e.target.value)} />
      {isLoading ? <Skeleton className="h-64" /> : rows.length === 0 ? <EmptyState title={t("people.empty")} /> : (
        <Table>
          <THead><tr><TH>{t("people.colName")}</TH><TH>{t("people.colKinds")}</TH><TH>{t("people.colDetail")}</TH><TH className="text-right">{t("people.colDue")}</TH><TH /></tr></THead>
          <TBody>
            {rows.map((p) => (
              <TR key={`${p.kind}-${p.id}`} onClick={() => setOpen(p)} className="cursor-pointer">
                <TD>
                  <div className="flex items-center gap-3">
                    <span className="h-9 w-9 shrink-0 rounded-full overflow-hidden bg-gradient-to-br from-ink-200 to-ink-400 flex items-center justify-center font-display text-white">
                      {p.photo_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={p.photo_url} alt="" className="h-full w-full object-cover" />
                      ) : p.name.slice(0, 1)}
                    </span>
                    <span className="min-w-0">
                      <span className="block font-semibold text-ink-900 truncate">{p.name}</span>
                      <span className="block text-xs text-ink-500 truncate">{p.email ?? "—"}</span>
                    </span>
                  </div>
                </TD>
                <TD><KindIcons kinds={p.kinds} /></TD>
                <TD className="text-xs text-ink-600">
                  {p.kind === "ATHLETE" ? (
                    <span className="inline-flex items-center gap-2">
                      {p.belt && <BeltBadge code={p.belt} size="sm" showLabel={false} />}
                      {p.age != null && t("people.age", { n: p.age })}
                      {p.social_tier && <Badge tone="accent">Escalão {p.social_tier}</Badge>}
                      {p.adapted_judo && <Badge tone="info">{t("people.adapted")}</Badge>}
                      {p.status !== "ACTIVE" && <Badge tone="warning">{t.dyn(`people.status.${p.status}`, p.status)}</Badge>}
                    </span>
                  ) : p.children?.length ? t("people.children", { names: p.children.map((c) => c.name.split(" ")[0]).join(", ") }) : "—"}
                </TD>
                <TD className="text-right font-semibold">{p.due_cents > 0 ? <span className="text-rose-600">{fmt.euro(p.due_cents)}</span> : "—"}</TD>
                <TD className="text-right text-ink-400">›</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {open && <PersonDrawer person={open} canInvest={canInvest} onClose={() => setOpen(null)} />}
    </div>
  );
}

type CardTab = "debts" | "payments" | "results" | "investments" | "function";

function PersonDrawer({ person, canInvest, onClose }: { person: Person; canInvest: boolean; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const [tab, setTab] = useState<CardTab>("debts");
  const path = person.kind === "ATHLETE" ? `/people/athletes/${person.id}/card` : `/people/users/${person.id}/card`;
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "person", person.kind, person.id], queryFn: () => clubGet<PersonCard>(A(path)) });
  const tabs = [
    { key: "debts", label: `💶 ${t("people.debts")}` },
    { key: "payments", label: `✅ ${t("people.payments")}` },
    { key: "results", label: `🏆 ${t("people.results")}` },
    { key: "investments", label: `💎 ${t("people.investments")}` },
    { key: "function", label: `🏷️ ${t("people.function")}` },
  ];
  // Nei corsi JAV una famiglia può passare a un club ufficiale: si sposta
  // l'account, quindi serve l'account della famiglia (il genitore, o
  // l'atleta adulto che fa da sé).
  const { courses } = useClubFeatures();
  const familyUserId = person.kind === "USER" ? person.id : person.user_id;
  const [moving, setMoving] = useState(false);
  return (
    <Modal open onClose={onClose} size="xl" title={person.name}
      subtitle={<span className="inline-flex items-center gap-2"><KindIcons kinds={person.kinds} /> {person.email}</span>}
      footer={courses && familyUserId && person.kinds.some((k) => k === "PARENT" || k === "ATHLETE")
        ? <Button variant="secondary" onClick={() => setMoving(true)}>🏯 {t("javCourses.moveButton")}</Button> : undefined}>
      {moving && familyUserId && <MoveToClubModal userId={familyUserId} name={person.name} onClose={() => { setMoving(false); onClose(); }} />}
      <div className="space-y-4">
        {data && (
          <div className="grid grid-cols-3 gap-3">
            <Stat label={t("people.debts")} value={fmt.euro(data.totals.debt_cents)} tone={data.totals.debt_cents ? "text-rose-600" : "text-ink-900"} />
            <Stat label={t("people.payments")} value={fmt.euro(data.totals.paid_cents)} tone="text-emerald-700" />
            <Stat label={t("people.investments")} value={fmt.euro(data.totals.invested_cents)} tone="text-brand-700" />
          </div>
        )}
        <Tabs value={tab} onChange={(k) => setTab(k as CardTab)} items={tabs} />
        {isLoading || !data ? <Skeleton className="h-48" /> : (
          <>
            {tab === "debts" && <FeeList fees={data.debts} empty={t("people.noDebts")} />}
            {tab === "payments" && <FeeList fees={data.payments} empty={t("people.noPayments")} />}
            {tab === "results" && (
              data.results.length === 0 && data.belts.length === 0 ? <p className="text-sm text-ink-500">{t("people.noResults")}</p> : (
                <div className="space-y-3">
                  {data.belts.map((b) => <p key={b.athlete_name} className="text-sm">🥋 {b.athlete_name}: <strong>{b.belt}</strong></p>)}
                  <ul className="divide-y divide-ink-100">
                    {data.results.map((r) => (
                      <li key={`${r.competition_id}-${r.athlete_name}`} className="flex items-center justify-between py-2 text-sm">
                        <span>
                          <span className="font-semibold text-ink-900">{r.name}</span>
                          <span className="block text-xs text-ink-500">{fmt.shortDate(r.starts_on)} · {r.athlete_name}{r.kind === "STAGE" ? ` · ${t("event.stage")}` : ""}</span>
                        </span>
                        <span className="text-right">
                          {r.placement != null ? <Badge tone={r.placement === 1 ? "accent" : "neutral"}>{r.placement === 0 ? t("people.participation") : `${r.placement}º`}</Badge> : <span className="text-xs text-ink-400">{t.dyn(`people.entry.${r.status}`, r.status)}</span>}
                          {r.points > 0 && <span className="block text-xs text-ink-500">{r.points} pt</span>}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            )}
            {tab === "investments" && <Investments person={person} card={data} canInvest={canInvest} />}
            {tab === "function" && <FunctionEditor person={person} />}
          </>
        )}
      </div>
    </Modal>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="rounded-2xl bg-ink-50 p-3">
      <p className="text-[11px] uppercase tracking-wide text-ink-500 font-bold">{label}</p>
      <p className={`font-display text-xl ${tone}`}>{value}</p>
    </div>
  );
}

function FeeList({ fees, empty }: { fees: PersonCard["debts"]; empty: string }) {
  const { fmt } = useI18n();
  if (fees.length === 0) return <p className="text-sm text-ink-500">{empty}</p>;
  return (
    <ul className="divide-y divide-ink-100">
      {fees.map((f) => (
        <li key={f.id} className="flex items-center justify-between gap-3 py-2 text-sm">
          <span className="min-w-0">
            <span className="block font-semibold text-ink-900">{f.description}</span>
            <span className="block text-xs text-ink-500">{f.athlete_name ?? "—"} · {fmt.shortDate(f.due_date)}{f.discount_note ? ` · ${f.discount_note}` : ""}</span>
          </span>
          <span className="text-right shrink-0">
            <span className="block font-semibold">{fmt.euro(f.amount_cents)}</span>
            <FeeStatusPill status={f.status} overdue={f.overdue} />
          </span>
        </li>
      ))}
    </ul>
  );
}

function Investments({ person, card, canInvest }: { person: Person; card: PersonCard; canInvest: boolean }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function invest() {
    setBusy(true);
    try {
      await clubSend(A(`/athletes/${person.id}/investments`), "POST", { amount_cents: Math.round(Number(amount.replace(",", ".")) * 100), note });
      toast({ tone: "success", title: t("people.invested") });
      setAmount("");
      setNote("");
      await queryClient.invalidateQueries({ queryKey: ["club", "admin", "person"] });
    } catch (e) {
      toast({ tone: "error", title: t("people.investFailed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">{t("people.investmentsText")}</p>
      {card.investments.length === 0 ? <p className="text-sm text-ink-500">{t("people.noInvestments")}</p> : (
        <ul className="divide-y divide-ink-100">
          {card.investments.map((i) => (
            <li key={i.id} className="flex items-center justify-between py-2 text-sm">
              <span><span className="block font-semibold text-ink-900">{i.note}</span><span className="text-xs text-ink-500">{fmt.shortDate(i.created_at)}</span></span>
              <span className="font-semibold text-brand-700">+{fmt.euro(i.amount_cents)}</span>
            </li>
          ))}
        </ul>
      )}
      {person.kind === "ATHLETE" && canInvest && (
        <div className="rounded-2xl ring-1 ring-brand-200 bg-brand-50/50 p-4 space-y-3">
          <p className="text-sm font-semibold text-ink-900">💎 {t("people.newInvestment")}</p>
          <div className="grid sm:grid-cols-[140px_1fr] gap-3">
            <Field label="€" htmlFor="inv-amount"><Input id="inv-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
            <Field label={t("people.investmentReason")} htmlFor="inv-note"><Input id="inv-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("people.investmentPlaceholder")} /></Field>
          </div>
          <Button loading={busy} disabled={!Number(amount.replace(",", ".")) || note.trim().length < 3} onClick={invest}>{t("people.invest")}</Button>
        </div>
      )}
      {person.kind === "ATHLETE" && !canInvest && <p className="text-xs text-ink-400">{t("people.investOnlySuperadmin")}</p>}
    </div>
  );
}

function FunctionEditor({ person }: { person: Person }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const current = person.kinds.find((k) => ["COACH", "ASSISTANT_COACH", "MONITOR", "ASSISTANT_MONITOR"].includes(k)) ?? "";
  const [fn, setFn] = useState<string>(current);
  const options = person.kind === "ATHLETE" ? ["MONITOR", "ASSISTANT_MONITOR"] : ["COACH", "ASSISTANT_COACH", "MONITOR", "ASSISTANT_MONITOR"];
  async function save() {
    try {
      await clubSend(A("/functions"), "PUT", {
        function: fn || null, ...(person.kind === "ATHLETE" ? { athlete_id: person.id } : { user_id: person.id }),
      });
      await queryClient.invalidateQueries({ queryKey: ["club", "admin", "people"] });
      toast({ tone: "success", title: t("people.functionSaved") });
    } catch (e) {
      toast({ tone: "error", title: t("people.functionFailed"), text: (e as Error).message });
    }
  }
  return (
    <div className="space-y-3 max-w-md">
      <p className="text-sm text-ink-500">{t("people.functionText")}</p>
      <Select value={fn} onChange={(e) => setFn(e.target.value)} aria-label={t("people.function")}>
        <option value="">{t("people.noFunction")}</option>
        {options.map((o) => <option key={o} value={o}>{PERSON_KIND_ICONS[o as PersonKind]} {t.dyn(`people.kind.${o}`, o)}</option>)}
      </Select>
      <Button onClick={save}>{t("common.save")}</Button>
    </div>
  );
}

// --- Taxa de falta --------------------------------------------------------------------------------

/** Chi nel mese ha fatto poche lezioni: il sistema propone, la segreteria
 *  decide con un clic (metà mensilità, o niente). */
export function AbsencePanel() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 1);
    return d.toISOString().slice(0, 7);
  });
  const [onlySuggested, setOnlySuggested] = useState(true);
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "absence", period], queryFn: () => clubGet<AbsenceRow[]>(A(`/absence?period=${period}`)) });
  const rows = (data ?? []).filter((r) => !onlySuggested || r.suggestion || r.applied);
  async function apply(feeId: string, adjustment: "HALF" | "FULL" | null) {
    try {
      await clubSend(A(`/fees/${feeId}/absence`), "PUT", { adjustment });
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: adjustment ? t("absence.applied") : t("absence.removed") });
    } catch (e) {
      toast({ tone: "error", title: t("absence.failed"), text: (e as Error).message });
    }
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">{t("absence.intro")}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} className="w-48" aria-label={t("absence.month")} />
        <label className="flex items-center gap-2 text-sm text-ink-700">
          <input type="checkbox" checked={onlySuggested} onChange={(e) => setOnlySuggested(e.target.checked)} className="accent-brand-500 h-4 w-4" />
          {t("absence.onlySuggested")}
        </label>
      </div>
      {isLoading ? <Skeleton className="h-48" /> : rows.length === 0 ? <EmptyState title={t("absence.empty")} text={t("absence.emptyText")} /> : (
        <Table>
          <THead><tr><TH>{t("people.colName")}</TH><TH>{t("absence.lessons")}</TH><TH>{t("absence.suggestion")}</TH><TH className="text-right">{t("clubAdmin.colAmount")}</TH><TH className="text-right" /></tr></THead>
          <TBody>
            {rows.map((r) => (
              <TR key={r.fee.id}>
                <TD className="font-semibold text-ink-900">{r.athlete_name}</TD>
                <TD>{r.lessons_held ? t("absence.presences", { p: r.presences, n: r.lessons_held }) : <span className="text-ink-400">{t("absence.noMarks")}</span>}</TD>
                <TD>{r.applied ? <Badge tone="success">{t.dyn(`absence.kind.${r.applied}`, r.applied)} ✓</Badge> : r.suggestion ? <Badge tone="warning">{t.dyn(`absence.kind.${r.suggestion}`, r.suggestion)}</Badge> : "—"}</TD>
                <TD className="text-right"><span className="font-semibold">{fmt.euro(r.fee.amount_cents)}</span><FeeStatusPill status={r.fee.status} overdue={r.fee.overdue} /></TD>
                <TD className="text-right whitespace-nowrap space-x-1">
                  {r.fee.status === "DUE" && r.applied !== "HALF" && <Button size="sm" variant="secondary" onClick={() => apply(r.fee.id, "HALF")}>½</Button>}
                  {r.fee.status === "DUE" && <Button size="sm" variant="secondary" onClick={() => apply(r.fee.id, "FULL")}>0 €</Button>}
                  {r.applied && r.fee.status === "DUE" && <Button size="sm" variant="ghost" onClick={() => apply(r.fee.id, null)}>{t("absence.undo")}</Button>}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}

// --- Ore dello staff (cartellino) -----------------------------------------------------------------

export function WorkHoursPanel() {
  const { t, fmt } = useI18n();
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [open, setOpen] = useState<string | null>(null);
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "work-hours", month], queryFn: () => clubGet<StaffHours[]>(A(`/work-hours?month=${month}`)) });
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">{t("workHours.intro")}</p>
      <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-48" aria-label={t("absence.month")} />
      {isLoading ? <Skeleton className="h-48" /> : !data?.length ? <EmptyState title={t("workHours.empty")} /> : (
        <div className="space-y-3">
          {data.map((s) => (
            <div key={s.user_id} className="glass-card rounded-3xl p-4">
              <button type="button" onClick={() => setOpen(open === s.user_id ? null : s.user_id)} className="w-full flex items-center justify-between cursor-pointer">
                <span className="font-semibold text-ink-900">🧑‍🏫 {s.name}</span>
                <span className="font-display text-xl text-ink-900">{hoursLabel(s.minutes)}</span>
              </button>
              {open === s.user_id && (
                <ul className="mt-3 divide-y divide-ink-100 text-sm">
                  {s.sessions.map((w) => (
                    <li key={w.id} className="flex items-center justify-between py-2">
                      <span>{fmt.shortDate(w.started_at)} · {new Date(w.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}–{w.ended_at ? new Date(w.ended_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : t("workHours.open")}{w.note ? ` · ${w.note}` : ""}</span>
                      <span className="text-ink-500">{hoursLabel(w.minutes)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Registro presenze del giorno ------------------------------------------------------------------

export function DayLogPanel() {
  const { t } = useI18n();
  const [day, setDay] = useState(() => new Date().toISOString().slice(0, 10));
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "attendance", day], queryFn: () => clubGet<DayAttendance[]>(A(`/attendance?date=${day}`)) });
  const present = (data ?? []).filter((r) => r.present);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="w-48" aria-label={t("attendance.day")} />
        <Badge tone="success">{t("dayLog.present", { n: present.length })}</Badge>
        <Badge tone="warning">{t("dayLog.notes", { n: (data ?? []).filter((r) => r.note).length })}</Badge>
      </div>
      {isLoading ? <Skeleton className="h-48" /> : !data?.length ? <EmptyState title={t("dayLog.empty")} /> : (
        <Table>
          <THead><tr><TH>{t("people.colName")}</TH><TH>{t("dayLog.course")}</TH><TH>{t("dayLog.state")}</TH><TH>{t("dayLog.note")}</TH><TH>{t("dayLog.by")}</TH></tr></THead>
          <TBody>
            {data.map((r) => (
              <TR key={`${r.athlete_id}-${r.course_id}`}>
                <TD className="font-semibold text-ink-900">{r.athlete_name}</TD>
                <TD>{r.course_name}</TD>
                <TD>{r.present ? <Badge tone="success">✓ {t("dayLog.yes")}</Badge> : <Badge tone="neutral">{t("dayLog.no")}</Badge>}</TD>
                <TD className="text-sm text-amber-800">{r.note ?? ""}</TD>
                <TD className="text-xs text-ink-500">{r.recorded_by_kind === "FAMILY" ? `👪 ${t("dayLog.family")}` : `🧑‍🏫 ${t("dayLog.staff")}`}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
