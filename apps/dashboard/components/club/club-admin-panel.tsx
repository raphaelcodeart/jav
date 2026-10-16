"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, FeeStatusPill } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { RankingPanel } from "@/components/club/ranking-panel";
import { clubSignupUrl, StaffModal } from "@/components/club/club-staff";
import { useCurrentClub, type ClubSettings } from "@/components/club/current-club";
import { AttendanceTool } from "@/components/club/attendance-tool";
import { ClubAccounting, ClubMoneyHome } from "@/components/club/club-accounting";
import { ClubSiteEditor } from "@/components/club/club-site-editor";
import { KnowledgePanel } from "@/components/javbot/knowledge-panel";
import { NewsAdminPanel } from "@/components/club/club-board";
import { MonthBoardPanel } from "@/components/club/month-board";
import { ClubShopPanel } from "@/components/club/club-shop-panel";
import { EVENT_KIND_STYLE, EventIcon } from "@/components/club/event-icon";
import { ClubDocumentsPanel } from "@/components/club/club-documents";
import { AthleteMarks } from "@/components/club/person-marks";
import { SlotEditModal } from "@/components/club/slot-edit-modal";
import { ContactInbox } from "@/components/club/contact-inbox";
import { AthletePublicPageSection } from "@/components/club/athlete-public-page";
import { AbsencePanel, DayLogPanel, PeoplePanel } from "@/components/club/club-console";
import { StaffManagementPanel } from "@/components/club/staff-management";
import { CalendarPanel } from "@/components/club/coach-tools";
import { BeltAwardPanel } from "@/components/club/staff-tools";
import { CoursesManager } from "@/components/club/jav-courses";
import { SeasonMonthsPanel } from "@/components/club/season-months";
import { useI18n } from "@/lib/i18n/provider";
import { shareOrCopyLink } from "@/lib/share-link";
import {
  CERTIFICATE_LABELS,
  FEE_KIND_LABELS,
  LEVEL_LABELS,
  PLACEMENT_LABELS,
  clubGet,
  clubSend,
  euro,
  fullName,
  kindFeatures,
  shortDate,
  type AdminAthlete,
  type AdminCertificate,
  type AdminProof,
  type CashReceiver,
  type ClubStats,
  type Competition,
  type Course,
  type Entry,
  type Fee,
  type Plan,
  type Pricing,
  type SchoolLetter,
  type TransportRequest,
  PAYMENT_METHOD_ICONS,
} from "@/lib/club";

export type ClubSection =
  | "overview" | "people" | "athletes" | "plans" | "accounting" | "fees" | "proofs" | "absence" | "certificates"
  | "competitions" | "courses" | "calendar" | "attendance" | "daylog" | "belts" | "ranking" | "workhours"
  | "shop-orders" | "site" | "messages" | "news" | "javbot" | "documents" | "settings";
type Section = ClubSection;

/** Le sezioni del club, nell'ordine e con i gruppi del menu laterale: la
 *  stessa struttura per la segreteria e per il superadmin entrato nel club. */
export const CLUB_SECTIONS: { key: ClubSection; icon: string; group: "people" | "money" | "activity" | "club" }[] = [
  { key: "overview", icon: "🏠", group: "people" },
  { key: "people", icon: "👥", group: "people" },
  { key: "athletes", icon: "🥋", group: "people" },
  { key: "certificates", icon: "🩺", group: "people" },
  { key: "accounting", icon: "📒", group: "money" },
  { key: "fees", icon: "💶", group: "money" },
  { key: "proofs", icon: "🧾", group: "money" },
  { key: "absence", icon: "📉", group: "money" },
  { key: "plans", icon: "📋", group: "money" },
  { key: "shop-orders", icon: "🛍️", group: "money" },
  { key: "courses", icon: "🗓️", group: "activity" },
  { key: "calendar", icon: "📅", group: "activity" },
  { key: "attendance", icon: "✅", group: "activity" },
  { key: "daylog", icon: "📝", group: "activity" },
  { key: "competitions", icon: "🏆", group: "activity" },
  { key: "belts", icon: "🎖️", group: "activity" },
  { key: "ranking", icon: "📊", group: "activity" },
  { key: "workhours", icon: "👥", group: "club" },
  { key: "site", icon: "🌐", group: "club" },
  // I messaggi scritti al club dalla sua pagina pubblica (contact-inbox.tsx).
  { key: "messages", icon: "✉️", group: "club" },
  // La bacheca di atleti e famiglie: le notizie del club, come un post.
  { key: "news", icon: "📰", group: "club" },
  // Che cosa sa JAVBOT dell'area riservata: i PDF e le istruzioni del club.
  { key: "javbot", icon: "🤖", group: "club" },
  // Certidões, atas, rivalidazione FPJ, assicurazioni, statuto del club.
  { key: "documents", icon: "📁", group: "club" },
  { key: "settings", icon: "⚙️", group: "club" },
];

/** Le sezioni che esistono in un'unità: nei corsi JAV niente cinture, gare
 *  e ranking (club/kinds.py), e le stesse sezioni spariscono dal menu. */
// Niente "Messaggi": l'unità non ha una pagina di club, chi scrive dal sito
// scrive a JudoArteVida.
const COURSES_UNIT_HIDDEN: ClubSection[] = ["competitions", "belts", "ranking", "messages"];
export function sectionsFor(kind: string | null | undefined) {
  const { courses } = kindFeatures(kind);
  return courses ? CLUB_SECTIONS.filter((s) => !COURSES_UNIT_HIDDEN.includes(s.key)) : CLUB_SECTIONS;
}

const A = (path: string) => `/admin${path}`;

function useRun() {
  const toast = useToast();
  const queryClient = useQueryClient();
  return async function run(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn();
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: ok });
      return true;
    } catch (e) {
      toast({ tone: "error", title: "Operazione non riuscita", text: (e as Error).message });
      return false;
    }
  };
}

/** The club's back office. Built for exceptions: the monthly fees and the
 *  payments run by themselves (docs/club-portal.md), the secretary checks,
 *  corrects, and publishes competitions and results.
 *
 *  Con `section` la sezione la sceglie il menu laterale di chi lo ospita
 *  (area segreteria, console del superadmin); senza, ha le sue schede. */
export function ClubAdminPanel({ section: controlled, onGo, canInvest = false }: {
  section?: ClubSection; onGo?: (s: ClubSection) => void; canInvest?: boolean;
} = {}) {
  const [own, setOwn] = useState<Section>("overview");
  const section = controlled ?? own;
  const go = onGo ?? setOwn;
  const { data: club } = useCurrentClub();
  const { t } = useI18n();
  const features = kindFeatures(club?.kind);
  const sections = sectionsFor(club?.kind).map((s) => ({ key: s.key, label: `${s.icon} ${t.dyn(`clubNav.${s.key}`, s.key)}` }));
  return (
    <div>
      <PageHeader
        eyebrow={club?.name ?? "Club"}
        title={t.dyn(`clubNav.${section}`, section)}
        subtitle={t.dyn(`clubNav.${section}.subtitle`, "")}
      />
      {!controlled && <Tabs value={section} onChange={(k) => go(k as Section)} items={sections} className="mb-6" />}
      <motion.div key={section} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        {section === "overview" && <Overview onGo={go} />}
        {section === "people" && <PeoplePanel canInvest={canInvest} />}
        {section === "athletes" && <Athletes />}
        {section === "plans" && <Plans />}
        {section === "accounting" && <ClubAccounting />}
        {section === "fees" && <Fees />}
        {section === "proofs" && <Proofs />}
        {section === "absence" && <AbsencePanel />}
        {section === "certificates" && <Certificates />}
        {section === "competitions" && features.competitions && <Competitions />}
        {section === "courses" && (features.courses ? <CoursesManager /> : <Courses />)}
        {section === "calendar" && <CalendarPanel />}
        {section === "attendance" && <AttendanceTool />}
        {section === "daylog" && <DayLogPanel />}
        {section === "belts" && features.belts && <BeltAwardPanel />}
        {section === "ranking" && features.ranking && <RankingPanel admin />}
        {section === "workhours" && <StaffManagementPanel />}
        {section === "shop-orders" && <ClubShopPanel familyOrders={<ShopOrders />} />}
        {section === "site" && <ClubSiteEditor />}
        {section === "messages" && <ContactInbox mode="club" />}
        {section === "javbot" && <KnowledgePanel mode="club" />}
        {section === "news" && <NewsAdminPanel />}
        {section === "documents" && <ClubDocumentsPanel />}
        {section === "settings" && <ClubSettingsSection />}
      </motion.div>
    </div>
  );
}

// --- Panoramica -------------------------------------------------------------------------------

function Overview({ onGo }: { onGo: (s: Section) => void }) {
  const { t } = useI18n();
  const { data } = useQuery({ queryKey: ["club", "admin", "stats"], queryFn: () => clubGet<ClubStats>(A("/stats")) });
  const run = useRun();
  const [period, setPeriod] = useState(() => new Date().toISOString().slice(0, 7));
  return (
    <div className="space-y-6">
      {/* Prima di tutto il mese corrente: chi ha pagato la mensilità e chi
          manca (month-board.tsx). Poi i soldi del club e i lavori automatici. */}
      <MonthBoardPanel compact onOpen={() => onGo("fees")} />
      <ClubMoneyHome onGo={onGo} athletesActive={data?.athletes_active} />
      <div className="glass-card rounded-3xl p-5 space-y-3">
        <h3 className="text-base text-ink-900">Lavori automatici</h3>
        <p className="text-sm text-ink-500">
          {t("clubAdmin.jobsText")}
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Mese" htmlFor="gen-period">
            <Input id="gen-period" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} className="w-44" />
          </Field>
          <Button onClick={() => run(() => clubSend(A(`/jobs/generate-monthly-fees?period=${period}`), "POST"), "Quote del mese generate")}>Genera quote del mese</Button>
          <Button variant="secondary" onClick={() => window.confirm(t("clubAdmin.newSeasonConfirm")) && run(() => clubSend(A("/jobs/new-season"), "POST"), t("clubAdmin.newSeasonDone"))}>
            Avvia nuova stagione
          </Button>
          <Button variant="secondary" onClick={() => window.confirm(t("clubAdmin.newYearConfirm")) && run(() => clubSend(A("/jobs/new-year"), "POST"), t("clubAdmin.newYearDone"))}>
            {t("clubAdmin.newYear")}
          </Button>
        </div>
      </div>
    </div>
  );
}

// --- Atleti -----------------------------------------------------------------------------------

function Athletes() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("ACTIVE");
  const qs = new URLSearchParams({ ...(q ? { q } : {}), ...(status ? { status } : {}) }).toString();
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "athletes", qs], queryFn: () => clubGet<AdminAthlete[]>(A(`/athletes?${qs}`)) });
  const { data: plans } = useQuery({ queryKey: ["club", "admin", "plans"], queryFn: () => clubGet<Plan[]>(A("/plans")) });
  const [editing, setEditing] = useState<AdminAthlete | null>(null);
  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-3">
        <Input placeholder="Cerca per nome o email del genitore…" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="sm:w-48">
          <option value="ACTIVE">Attivi</option>
          <option value="SUSPENDED">Sospesi</option>
          <option value="LEFT">Usciti</option>
          <option value="">Tutti</option>
        </Select>
      </div>
      {isLoading ? <Skeleton className="h-64" /> : (data ?? []).length === 0 ? <EmptyState title="Nessun atleta" text="I genitori aggiungono i loro figli dalla propria area." /> : (
        <Table>
          <THead><tr><TH>Atleta</TH><TH>Cintura</TH><TH>Piano</TH><TH>Genitore</TH><TH>Certificato</TH><TH className="text-right">Da pagare</TH></tr></THead>
          <TBody>
            {(data ?? []).map((a) => {
              const cert = CERTIFICATE_LABELS[a.certificate.status] ?? CERTIFICATE_LABELS.MISSING!;
              return (
                <TR key={a.id} onClick={() => setEditing(a)} className="cursor-pointer">
                  <TD><p className="font-semibold text-ink-900">{fullName(a)} <AthleteMarks id={a.id} /></p><p className="text-xs text-ink-500"><span title="Età federale: gli anni compiuti entro il 31 dicembre">{a.federal_age ?? a.season_age} anni fed.</span> · {a.sex === "F" ? "F" : "M"}</p></TD>
                  <TD><BeltBadge belt={a.belt} size="sm" /></TD>
                  <TD>{a.plan?.name ?? <Badge tone="warning">Da assegnare</Badge>}{a.plan_locked && <span title="Piano bloccato" className="ml-1">🔒</span>}</TD>
                  <TD className="text-xs">{a.guardian_email ?? "—"}</TD>
                  <TD><Badge tone={cert.tone} dot>{cert.label.replace("Certificato ", "")}</Badge></TD>
                  <TD className="text-right font-semibold">{a.due_cents > 0 ? <span className={a.overdue_count ? "text-rose-600" : ""}>{euro(a.due_cents)}</span> : "—"}</TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      )}
      {editing && <AthleteAdminModal athlete={editing} plans={plans ?? []} onClose={() => setEditing(null)} />}
    </div>
  );
}

function AthleteAdminModal({ athlete, plans, onClose }: { athlete: AdminAthlete; plans: Plan[]; onClose: () => void }) {
  const [paying, setPaying] = useState<Fee | null>(null);
  const [planId, setPlanId] = useState(athlete.plan?.id ?? "");
  const [locked, setLocked] = useState(athlete.plan_locked);
  const [status, setStatus] = useState(athlete.status);
  const [fedNumber, setFedNumber] = useState(athlete.federation_number ?? "");
  const [fedExpires, setFedExpires] = useState(athlete.federation_expires_on ?? "");
  const [tier, setTier] = useState(athlete.social_tier ?? "");
  const [adapted, setAdapted] = useState(athlete.adapted_judo);
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const run = useRun();
  async function save() {
    setBusy(true);
    const ok = await run(
      () => clubSend(A(`/athletes/${athlete.id}`), "PATCH", {
        plan_id: planId || null, plan_locked: locked, status,
        federation_number: fedNumber || null, federation_expires_on: fedExpires || null,
        social_tier: tier || null, adapted_judo: adapted,
      }),
      "Atleta aggiornato",
    );
    setBusy(false);
    if (ok) onClose();
  }
  return (
    <Modal open onClose={onClose} size="xl" title={fullName(athlete)} subtitle={`Genitore: ${athlete.guardian_email ?? "—"}`} footer={<><Button variant="ghost" onClick={onClose}>Annulla</Button><Button loading={busy} onClick={save}>Salva</Button></>}>
      <div className="space-y-4">
        <Field label="Piano" hint="Scegliendo un piano a mano lo blocchi: il cambio stagione non lo ricalcolerà più per età." htmlFor="adm-plan">
          <Select id="adm-plan" value={planId} onChange={(e) => { setPlanId(e.target.value); setLocked(true); }}>
            <option value="">— nessuno —</option>
            {plans.map((p) => <option key={p.id} value={p.id}>{p.name} · {euro(p.monthly_fee_cents)}/mese</option>)}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm text-ink-700"><input type="checkbox" checked={locked} onChange={(e) => setLocked(e.target.checked)} className="accent-brand-500 h-4 w-4" /> Piano bloccato</label>
        <Field label="Stato" htmlFor="adm-status">
          <Select id="adm-status" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="ACTIVE">Attivo</option>
            <option value="SUSPENDED">Sospeso (niente quote)</option>
            <option value="LEFT">Uscito dal club</option>
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="N. tesseramento" htmlFor="adm-fed"><Input id="adm-fed" value={fedNumber} onChange={(e) => setFedNumber(e.target.value)} /></Field>
          <Field label="Scadenza tessera" htmlFor="adm-fed-exp"><Input id="adm-fed-exp" type="date" value={fedExpires} onChange={(e) => setFedExpires(e.target.value)} /></Field>
        </div>
        <div className="rounded-2xl ring-1 ring-ink-200 p-4 space-y-3">
          <p className="text-sm font-semibold text-ink-900">{t("clubAdmin.discountsTitle")}</p>
          <Field label={t("clubAdmin.socialTier")} hint={t("clubAdmin.socialTierHint")} htmlFor="adm-tier">
            <Select id="adm-tier" value={tier} onChange={(e) => setTier(e.target.value)}>
              <option value="">{t("clubAdmin.noTier")}</option>
              <option value="A">Escalão A</option>
              <option value="B">Escalão B</option>
              <option value="C">Escalão C</option>
            </Select>
          </Field>
          <label className="flex items-center gap-2 text-sm text-ink-700">
            <input type="checkbox" checked={adapted} onChange={(e) => setAdapted(e.target.checked)} className="accent-brand-500 h-4 w-4" />
            {t("clubAdmin.adaptedJudo")}
          </label>
        </div>
        {/* La scheda sul sito ha i suoi salvataggi: non aspetta "Salva". */}
        <AthletePublicPageSection athleteId={athlete.id} />
        {/* Le mensilità mese per mese: anche queste non aspettano "Salva". */}
        <div className="rounded-2xl ring-1 ring-ink-200 p-4">
          <SeasonMonthsPanel athleteId={athlete.id} mode="admin" onMarkPaid={setPaying} />
        </div>
      </div>
      {paying && <MarkPaidModal fee={paying} onClose={() => setPaying(null)} />}
    </Modal>
  );
}

// --- Piani ------------------------------------------------------------------------------------

function Plans() {
  const { t } = useI18n();
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "plans"], queryFn: () => clubGet<Plan[]>(A("/plans")) });
  const [editing, setEditing] = useState<Plan | "new" | null>(null);
  const run = useRun();
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => setEditing("new")} icon={<span>＋</span>}>Nuovo piano</Button></div>
      {isLoading ? <Skeleton className="h-48" /> : (data ?? []).length === 0 ? <EmptyState title="Nessun piano" text="Crea i piani per fascia d'età: il sistema li assegna da solo agli atleti." action={<Button onClick={() => setEditing("new")}>Crea il primo piano</Button>} /> : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {(data ?? []).map((p) => (
            <motion.div key={p.id} whileHover={{ y: -3 }} className="glass-card rounded-3xl p-5">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-base text-ink-900">{p.name}</h3>
                {!p.active && <Badge tone="neutral">Disattivo</Badge>}
              </div>
              <p className="text-sm text-ink-500">{p.min_age}{p.max_age != null ? `–${p.max_age}` : "+"} anni · scadenza il {p.due_day} del mese</p>
              <p className="font-display text-3xl text-ink-900 mt-3">{euro(p.monthly_fee_cents)}<span className="text-sm text-ink-500 font-sans"> /mese</span></p>
              <p className="text-xs text-ink-500">{t("clubAdmin.planEnrollment", { amount: euro(p.enrollment_fee_cents) })}</p>
              <div className="flex gap-2 mt-4">
                <Button size="sm" variant="secondary" onClick={() => setEditing(p)}>Modifica</Button>
                <Button size="sm" variant="ghost" onClick={() => window.confirm(`Eliminare il piano «${p.name}»?`) && run(() => clubSend(A(`/plans/${p.id}`), "DELETE"), "Piano eliminato")}>Elimina</Button>
              </div>
            </motion.div>
          ))}
        </div>
      )}
      {editing && <PlanModal plan={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function PlanModal({ plan, onClose }: { plan: Plan | null; onClose: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState(plan?.name ?? "");
  const [description, setDescription] = useState(plan?.description ?? "");
  const [minAge, setMinAge] = useState(String(plan?.min_age ?? 4));
  const [maxAge, setMaxAge] = useState(plan?.max_age != null ? String(plan.max_age) : "");
  const [monthly, setMonthly] = useState(plan ? String(plan.monthly_fee_cents / 100) : "");
  const [enrollment, setEnrollment] = useState(plan ? String(plan.enrollment_fee_cents / 100) : "0");
  const [dueDay, setDueDay] = useState(String(plan?.due_day ?? 10));
  const [active, setActive] = useState(plan?.active ?? true);
  const [busy, setBusy] = useState(false);
  const run = useRun();
  const cents = (v: string) => Math.round(Number(v.replace(",", ".")) * 100) || 0;
  async function save() {
    setBusy(true);
    const body = { name, description: description || null, min_age: Number(minAge), max_age: maxAge ? Number(maxAge) : null, monthly_fee_cents: cents(monthly), enrollment_fee_cents: cents(enrollment), due_day: Number(dueDay), active };
    const ok = await run(() => (plan ? clubSend(A(`/plans/${plan.id}`), "PATCH", body) : clubSend(A("/plans"), "POST", body)), plan ? "Piano aggiornato" : "Piano creato");
    setBusy(false);
    if (ok) onClose();
  }
  return (
    <Modal open onClose={onClose} title={plan ? "Modifica piano" : "Nuovo piano"} footer={<><Button variant="ghost" onClick={onClose}>Annulla</Button><Button loading={busy} onClick={save} disabled={!name || !monthly}>Salva</Button></>}>
      <div className="space-y-4">
        <Field label="Nome" htmlFor="pl-name"><Input id="pl-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="es. Bambini 4–7 anni" /></Field>
        <Field label="Descrizione" htmlFor="pl-desc"><Textarea id="pl-desc" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Età minima" hint="Al 1° settembre" htmlFor="pl-min"><Input id="pl-min" type="number" min={0} value={minAge} onChange={(e) => setMinAge(e.target.value)} /></Field>
          <Field label="Età massima" hint="Vuoto = nessun limite" htmlFor="pl-max"><Input id="pl-max" type="number" min={0} value={maxAge} onChange={(e) => setMaxAge(e.target.value)} /></Field>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Mensile (€)" htmlFor="pl-month"><Input id="pl-month" inputMode="decimal" value={monthly} onChange={(e) => setMonthly(e.target.value)} /></Field>
          <Field label="Iscrizione (€)" hint={t("clubAdmin.planEnrollmentHint")} htmlFor="pl-enr"><Input id="pl-enr" inputMode="decimal" value={enrollment} onChange={(e) => setEnrollment(e.target.value)} /></Field>
          <Field label="Scade il giorno" htmlFor="pl-due"><Input id="pl-due" type="number" min={1} max={28} value={dueDay} onChange={(e) => setDueDay(e.target.value)} /></Field>
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-700"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="accent-brand-500 h-4 w-4" /> Piano attivo</label>
      </div>
    </Modal>
  );
}

// --- Quote ------------------------------------------------------------------------------------

/** Le quote: prima il quadro del mese (chi manca questo mese), poi l'elenco
 *  completo con i filtri per chi cerca una quota precisa. */
function Fees() {
  const [view, setView] = useState<"month" | "list">("month");
  return (
    <div className="space-y-5">
      <Tabs value={view} onChange={(k) => setView(k as "month" | "list")}
        items={[{ key: "month", label: "📅 Il mese" }, { key: "list", label: "📋 Tutte le quote" }]} />
      {view === "month" ? <MonthBoardPanel /> : <FeesList />}
    </div>
  );
}

function FeesList() {
  const { t } = useI18n();
  const [status, setStatus] = useState("DUE");
  const [kind, setKind] = useState("");
  const [period, setPeriod] = useState("");
  const qs = new URLSearchParams({ ...(status ? { status } : {}), ...(kind ? { kind } : {}), ...(period ? { period } : {}) }).toString();
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "fees", qs], queryFn: () => clubGet<Fee[]>(A(`/fees?${qs}`)) });
  const run = useRun();
  const [paying, setPaying] = useState<Fee | null>(null);
  const total = (data ?? []).reduce((s, f) => s + f.amount_cents, 0);
  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-3">
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="sm:w-44">
          <option value="DUE">Da pagare</option><option value="PAID">Pagate</option><option value="WAIVED">Condonate</option><option value="">Tutte</option>
        </Select>
        <Select value={kind} onChange={(e) => setKind(e.target.value)} className="sm:w-44">
          <option value="">Ogni tipo</option>
          {Object.entries(FEE_KIND_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </Select>
        <Input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} className="sm:w-48" aria-label="Mese" />
        <div className="sm:ml-auto self-center text-sm text-ink-500">{data?.length ?? 0} quote · <strong className="text-ink-900">{euro(total)}</strong></div>
      </div>
      {isLoading ? <Skeleton className="h-64" /> : (data ?? []).length === 0 ? <EmptyState title="Nessuna quota" text="Nessuna quota corrisponde ai filtri." /> : (
        <Table>
          <THead><tr><TH>Atleta</TH><TH>Quota</TH><TH>Scadenza</TH><TH>Stato</TH><TH className="text-right">Importo</TH><TH className="text-right">Azioni</TH></tr></THead>
          <TBody>
            {(data ?? []).map((f) => (
              <TR key={f.id}>
                <TD className="font-semibold text-ink-900">{f.athlete_name ?? t("clubAdmin.parentMember")} <AthleteMarks id={f.athlete_id} /></TD>
                <TD>
                  {f.description}<p className="text-xs text-ink-500">{FEE_KIND_LABELS[f.kind] ?? f.kind}</p>
                  {f.discount_note && <p className="text-[11px] text-emerald-700">{f.discount_note}</p>}
                </TD>
                <TD>{shortDate(f.due_date)}</TD>
                <TD>
                  <FeeStatusPill status={f.status} overdue={f.overdue} />
                  {f.waive_reason && <p className="text-[11px] text-ink-500 mt-1">{f.waive_reason}</p>}
                  <PaidHow fee={f} />
                </TD>
                <TD className="text-right font-semibold">{euro(f.amount_cents)}</TD>
                <TD className="text-right whitespace-nowrap">
                  {f.status === "DUE" ? (
                    <>
                      <Button size="sm" variant="secondary" onClick={() => setPaying(f)}>Pagata</Button>{" "}
                      <Button size="sm" variant="ghost" onClick={() => { const reason = window.prompt("Motivo del condono"); if (reason && reason.length >= 3) void run(() => clubSend(A(`/fees/${f.id}/waive`), "POST", { reason }), "Quota condonata"); }}>Condona</Button>
                    </>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => run(() => clubSend(A(`/fees/${f.id}/reopen`), "POST"), "Quota riaperta")}>Riapri</Button>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {paying && <MarkPaidModal fee={paying} onClose={() => setPaying(null)} />}
    </div>
  );
}

const METHOD_LABELS: Record<string, string> = {
  BANK_TRANSFER: "Bonifico", CASH: "Contanti", CARD: "Carta", WALLET: "Credito del wallet",
};

/** Come è stata pagata una quota, in una riga sotto lo stato. */
function PaidHow({ fee }: { fee: Fee }) {
  if (fee.status !== "PAID" || !fee.payment_method) return null;
  return (
    <p className="text-[11px] text-ink-600 mt-1">
      {PAYMENT_METHOD_ICONS[fee.payment_method]} {METHOD_LABELS[fee.payment_method] ?? fee.payment_method}
      {fee.cash_received_by_name ? ` · a ${fee.cash_received_by_name}` : ""}
    </p>
  );
}

/** "Pagata": la segreteria dice come (bonifico arrivato, contanti, carta al
 *  POS) e, per i contanti, a chi sono stati dati: a una persona dello staff
 *  o a un nome scritto (il presidente, un allenatore senza account). */
function MarkPaidModal({ fee, onClose }: { fee: Fee; onClose: () => void }) {
  const [method, setMethod] = useState<"CASH" | "CARD" | "BANK_TRANSFER">("CASH");
  const [receiver, setReceiver] = useState("");
  const [otherName, setOtherName] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const run = useRun();
  const { data: receivers } = useQuery({ queryKey: ["club", "admin", "cash-receivers"], queryFn: () => clubGet<CashReceiver[]>(A("/cash-receivers")) });
  const ready = method !== "CASH" || (receiver === "other" ? otherName.trim().length >= 2 : receiver !== "");
  async function save() {
    setBusy(true);
    const ok = await run(() => clubSend(A(`/fees/${fee.id}/mark-paid`), "POST", {
      method, note: note.trim() || null,
      cash_received_by_user_id: method === "CASH" && receiver !== "other" ? receiver : null,
      cash_received_by_name: method === "CASH" && receiver === "other" ? otherName.trim() : null,
    }), "Quota segnata pagata");
    setBusy(false);
    if (ok) onClose();
  }
  return (
    <Modal open onClose={onClose} title="Segna pagata" subtitle={`${fee.athlete_name ?? "Quota socio"} · ${fee.description} · ${euro(fee.amount_cents)}`}
      footer={<><Button variant="ghost" onClick={onClose}>Annulla</Button><Button loading={busy} disabled={!ready} onClick={save}>Segna pagata</Button></>}>
      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Come è stata pagata">
          {(["CASH", "CARD", "BANK_TRANSFER"] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={method === m} onClick={() => setMethod(m)}
              className={`rounded-2xl p-3 text-center ring-1 cursor-pointer ${method === m ? "bg-brand-50 ring-2 ring-brand-400" : "bg-white ring-ink-200 hover:ring-ink-300"}`}>
              <span className="block text-2xl" aria-hidden="true">{PAYMENT_METHOD_ICONS[m]}</span>
              <span className="block text-sm font-semibold text-ink-900">{METHOD_LABELS[m]}</span>
            </button>
          ))}
        </div>
        {method === "CASH" && (
          <Field label="A chi sono stati consegnati i contanti" htmlFor="mp-receiver">
            <Select id="mp-receiver" value={receiver} onChange={(e) => setReceiver(e.target.value)}>
              <option value="">Scegli la persona</option>
              {(receivers ?? []).map((r) => <option key={r.user_id} value={r.user_id}>{r.name}</option>)}
              <option value="other">{"Un'altra persona…"}</option>
            </Select>
          </Field>
        )}
        {method === "CASH" && receiver === "other" && (
          <Field label="Nome di chi li ha ricevuti" htmlFor="mp-other"><Input id="mp-other" value={otherName} onChange={(e) => setOtherName(e.target.value)} maxLength={120} /></Field>
        )}
        <Field label="Nota (facoltativa)" htmlFor="mp-note"><Input id="mp-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="es. ricevuta n. 123" /></Field>
      </div>
    </Modal>
  );
}

// --- Prove caricate ---------------------------------------------------------------------------

function Proofs() {
  const [status, setStatus] = useState("ACCEPTED");
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "proofs", status], queryFn: () => clubGet<AdminProof[]>(A(`/payment-proofs${status ? `?status=${status}` : ""}`)) });
  const run = useRun();
  const toast = useToast();
  async function open(id: string) {
    try {
      const { url } = await clubGet<{ url: string }>(A(`/payment-proofs/${id}/url`));
      window.open(url, "_blank", "noopener");
    } catch (e) {
      toast({ tone: "error", title: "Impossibile aprire la ricevuta", text: (e as Error).message });
    }
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">Le quote risultano pagate appena il genitore carica la ricevuta del bonifico o dice a chi ha dato i contanti (quella persona riceve un avviso). Controlla quando vuoi: se una prova non è valida, rifiutala e le quote tornano da pagare (il genitore riceve il motivo).</p>
      <Tabs value={status || "ALL"} onChange={(k) => setStatus(k === "ALL" ? "" : k)} items={[{ key: "ACCEPTED", label: "Registrate" }, { key: "REJECTED", label: "Rifiutate" }, { key: "ALL", label: "Tutte" }]} />
      {isLoading ? <Skeleton className="h-64" /> : (data ?? []).length === 0 ? <EmptyState title="Nessuna prova" /> : (
        <div className="grid md:grid-cols-2 gap-4">
          {(data ?? []).map((p) => (
            <div key={p.id} className="glass-card rounded-3xl p-5 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-display text-2xl text-ink-900">{euro(p.amount_cents)}</p>
                  <p className="text-xs text-ink-500">{shortDate(p.created_at)} · {p.uploaded_by_email ?? "—"}</p>
                </div>
                <Badge tone={p.status === "REJECTED" ? "danger" : "success"} dot>{p.status === "REJECTED" ? "Rifiutata" : "Registrata"}</Badge>
              </div>
              <ul className="text-sm text-ink-700 space-y-0.5">{p.fees.map((f) => <li key={f.id}>• {f.athlete_name}: {f.description} ({euro(f.amount_cents)})</li>)}</ul>
              {p.method === "CASH" && <p className="text-sm font-semibold text-ink-800">💶 Contanti consegnati a {p.cash_received_by_name ?? "—"}</p>}
              {p.note && <p className="text-xs text-ink-500 italic">“{p.note}”</p>}
              {p.rejection_reason && <p className="text-xs text-rose-600">Motivo: {p.rejection_reason}</p>}
              <div className="flex gap-2">
                {p.original_filename && <Button size="sm" variant="secondary" onClick={() => open(p.id)}>Vedi ricevuta ↗</Button>}
                {p.status !== "REJECTED" && (
                  <Button size="sm" variant="ghost" onClick={() => { const reason = window.prompt("Perché la prova non è valida? Il genitore leggerà questo testo."); if (reason && reason.length >= 3) void run(() => clubSend(A(`/payment-proofs/${p.id}/reject`), "POST", { reason }), "Prova rifiutata, quote riaperte"); }}>Rifiuta</Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Certificati ------------------------------------------------------------------------------

function Certificates() {
  const [status, setStatus] = useState("EXPIRING");
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "certificates", status], queryFn: () => clubGet<AdminCertificate[]>(A(`/certificates${status ? `?status=${status}` : ""}`)) });
  return (
    <div className="space-y-4">
      <Tabs value={status || "ALL"} onChange={(k) => setStatus(k === "ALL" ? "" : k)} items={[{ key: "EXPIRING", label: "In scadenza" }, { key: "EXPIRED", label: "Scaduti" }, { key: "MISSING", label: "Mancanti" }, { key: "VALID", label: "Validi" }, { key: "ALL", label: "Tutti" }]} />
      {isLoading ? <Skeleton className="h-48" /> : (data ?? []).length === 0 ? <EmptyState icon={<span className="text-3xl">🩺</span>} title="Niente da segnalare" /> : (
        <Table>
          <THead><tr><TH>Atleta</TH><TH>Genitore</TH><TH>Stato</TH><TH>Scadenza</TH></tr></THead>
          <TBody>
            {(data ?? []).map((c) => {
              const s = CERTIFICATE_LABELS[c.certificate.status] ?? CERTIFICATE_LABELS.MISSING!;
              return (
                <TR key={c.athlete_id}>
                  <TD className="font-semibold text-ink-900">{c.athlete_name} <AthleteMarks id={c.athlete_id} /></TD>
                  <TD className="text-xs">{c.guardian_email ?? "—"}</TD>
                  <TD><Badge tone={s.tone} dot>{s.label}</Badge></TD>
                  <TD>{shortDate(c.certificate.expires_on)}</TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      )}
    </div>
  );
}

// --- Gare e risultati -------------------------------------------------------------------------

function Competitions() {
  const { t } = useI18n();
  const [transportFor, setTransportFor] = useState<Competition | null>(null);
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "competitions"], queryFn: () => clubGet<Competition[]>(A("/competitions")) });
  const [editing, setEditing] = useState<Competition | "new" | null>(null);
  const [results, setResults] = useState<Competition | null>(null);
  const run = useRun();
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => setEditing("new")} icon={<span>＋</span>}>Nuova gara</Button></div>
      {isLoading ? <Skeleton className="h-48" /> : (data ?? []).length === 0 ? <EmptyState icon={<span className="text-3xl">🏟️</span>} title="Nessuna gara" action={<Button onClick={() => setEditing("new")}>Pubblica la prima gara</Button>} /> : (
        <div className="space-y-3">
          {(data ?? []).map((c) => (
            <div key={c.id} className="glass-card rounded-3xl p-5 flex flex-col lg:flex-row lg:items-center gap-4">
              <EventIcon kind={c.kind} imageUrl={c.image_url} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap gap-1.5 mb-1">
                  {c.kind === "COMPETITION" ? <Badge tone="neutral">{LEVEL_LABELS[c.level] ?? c.level}</Badge> : <Badge tone="brand">{EVENT_KIND_STYLE[c.kind]?.icon} {t.dyn(`event.${({ STAGE: "stage", REFEREEING: "referee", EDUCATION: "education", MEETING: "meeting" } as Record<string, string>)[c.kind] ?? "other"}`, c.kind)}</Badge>}
                  {c.transport_needed && <Badge tone="info">🚌 {t("event.transport")}</Badge>}
                  <Badge tone={c.status === "OPEN" ? "success" : c.status === "DONE" ? "info" : "warning"}>{c.status === "OPEN" ? "Iscrizioni aperte" : c.status === "DONE" ? "Conclusa" : "Iscrizioni chiuse"}</Badge>
                </div>
                <h3 className="text-base text-ink-900">{c.name}</h3>
                <p className="text-sm text-ink-500">{shortDate(c.starts_on)} · {c.location ?? "—"} · iscrizioni entro il {shortDate(c.registration_deadline)} · {c.fee_cents ? euro(c.fee_cents) : "gratuita"}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" onClick={() => setEditing(c)}>Modifica</Button>
                <Button size="sm" variant="secondary" onClick={() => setResults(c)}>Iscritti e risultati</Button>
                {c.transport_needed && (
                  <Button size="sm" variant="secondary" onClick={() => setTransportFor(c)}>🚌 {t("event.transportRequest")}</Button>
                )}
                {c.status === "OPEN" ? (
                  <Button size="sm" variant="ghost" onClick={() => run(() => clubSend(A(`/competitions/${c.id}/close`), "POST"), "Iscrizioni chiuse")}>Chiudi iscrizioni</Button>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => run(() => clubSend(A(`/competitions/${c.id}/reopen`), "POST"), "Iscrizioni riaperte")}>Riapri</Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {editing && <CompetitionModal competition={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {results && <ResultsModal competition={results} onClose={() => setResults(null)} />}
      {transportFor && <TransportModal competition={transportFor} onClose={() => setTransportFor(null)} />}
    </div>
  );
}

/** La foto o la locandina della gara: si carica e si toglie subito, senza
 *  aspettare «Salva». Senza, negli elenchi c'è l'icona del tipo. */
function EventImageEditor({ competition: c, kind }: { competition: Competition; kind: string }) {
  const [image, setImage] = useState(c.image_url ?? null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const queryClient = useQueryClient();
  async function upload(file: File | null) {
    setBusy(true);
    try {
      let updated: Competition;
      if (file) {
        const form = new FormData();
        form.append("file", file);
        updated = await clubSend<Competition>(A(`/competitions/${c.id}/image`), "POST", form);
      } else {
        updated = await clubSend<Competition>(A(`/competitions/${c.id}/image`), "DELETE");
      }
      setImage(updated.image_url ?? null);
      await queryClient.invalidateQueries({ queryKey: ["club"] });
    } catch (e) {
      toast({ tone: "error", title: "Immagine non caricata", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex items-center gap-4 rounded-2xl bg-ink-50 p-3 ring-1 ring-ink-100">
      <EventIcon kind={kind} imageUrl={image} />
      <div className="min-w-0 flex-1 space-y-2">
        <p className="text-sm font-semibold text-ink-900">Foto o locandina</p>
        <p className="text-xs text-ink-500">Compare accanto al nome negli elenchi delle prove. Senza, l&apos;icona del tipo. JPG, PNG o WebP fino a 5 MB.</p>
        <div className="flex flex-wrap gap-2">
          <Input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void upload(file); }} className="max-w-xs" />
          {image && <Button size="sm" variant="ghost" loading={busy} onClick={() => upload(null)}>Togli</Button>}
        </div>
      </div>
    </div>
  );
}

function CompetitionModal({ competition: c, onClose }: { competition: Competition | null; onClose: () => void }) {
  const [f, setF] = useState({
    name: c?.name ?? "", description: c?.description ?? "", starts_on: c?.starts_on ?? "", ends_on: c?.ends_on ?? "",
    location: c?.location ?? "", organizer: c?.organizer ?? "", level: c?.level ?? "CLUB",
    registration_deadline: c?.registration_deadline ?? "", fee: c ? String(c.fee_cents / 100) : "0",
    requires: c?.requires_agonistic_certificate ?? true, min_age: c?.min_age != null ? String(c.min_age) : "", max_age: c?.max_age != null ? String(c.max_age) : "",
    categories: c?.categories ?? "",
    kind: c?.kind ?? "COMPETITION",
    transport_needed: c?.transport_needed ?? false,
    transport_entity_name: c?.transport_entity_name ?? "",
    transport_entity_email: c?.transport_entity_email ?? "",
    transport_departure: c?.transport_departure ?? "",
    transport_return: c?.transport_return ?? "",
    transport_companions: String(c?.transport_companions ?? 0),
    transport_notes: c?.transport_notes ?? "",
    transport_auto_send: c?.transport_auto_send ?? false,
  });
  const set = (patch: Partial<typeof f>) => setF((x) => ({ ...x, ...patch }));
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const run = useRun();
  async function save() {
    setBusy(true);
    const body = {
      name: f.name, description: f.description || null, starts_on: f.starts_on, ends_on: f.ends_on || null,
      location: f.location || null, organizer: f.organizer || null, level: f.level, registration_deadline: f.registration_deadline,
      fee_cents: Math.round(Number(f.fee.replace(",", ".")) * 100) || 0, requires_agonistic_certificate: f.requires,
      min_age: f.min_age ? Number(f.min_age) : null, max_age: f.max_age ? Number(f.max_age) : null, categories: f.categories || null,
      kind: f.kind, transport_needed: f.transport_needed,
      transport_entity_name: f.transport_entity_name || null, transport_entity_email: f.transport_entity_email || null,
      transport_departure: f.transport_departure || null, transport_return: f.transport_return || null,
      transport_companions: Number(f.transport_companions) || 0, transport_notes: f.transport_notes || null,
      transport_auto_send: f.transport_auto_send,
    };
    const ok = await run(() => (c ? clubSend(A(`/competitions/${c.id}`), "PATCH", body) : clubSend(A("/competitions"), "POST", body)), c ? "Gara aggiornata" : "Gara pubblicata");
    setBusy(false);
    if (ok) onClose();
  }
  return (
    <Modal open onClose={onClose} size="lg" title={c ? "Modifica gara" : "Nuova gara"} footer={<><Button variant="ghost" onClick={onClose}>Annulla</Button><Button loading={busy} onClick={save} disabled={!f.name || !f.starts_on || !f.registration_deadline}>Salva</Button></>}>
      <div className="grid sm:grid-cols-2 gap-4">
        {c && <div className="sm:col-span-2"><EventImageEditor competition={c} kind={f.kind} /></div>}
        <div className="sm:col-span-2"><Field label="Nome" htmlFor="cp-name"><Input id="cp-name" value={f.name} onChange={(e) => set({ name: e.target.value })} /></Field></div>
        <Field label={t("event.kind")} hint={t("event.kindHint")} htmlFor="cp-kind">
          <Select id="cp-kind" value={f.kind} onChange={(e) => set({ kind: e.target.value })}>
            <option value="COMPETITION">{t("event.competition")}</option>
            <option value="STAGE">{t("event.stage")}</option>
          </Select>
        </Field>
        <div />
        <Field label="Inizio" htmlFor="cp-start"><Input id="cp-start" type="date" value={f.starts_on} onChange={(e) => set({ starts_on: e.target.value })} /></Field>
        <Field label="Fine (facoltativa)" htmlFor="cp-end"><Input id="cp-end" type="date" value={f.ends_on} onChange={(e) => set({ ends_on: e.target.value })} /></Field>
        <Field label="Luogo" htmlFor="cp-loc"><Input id="cp-loc" value={f.location} onChange={(e) => set({ location: e.target.value })} /></Field>
        <Field label="Organizzatore" htmlFor="cp-org"><Input id="cp-org" value={f.organizer} onChange={(e) => set({ organizer: e.target.value })} /></Field>
        <Field label="Livello" hint="Moltiplica i punti del ranking" htmlFor="cp-level">
          <Select id="cp-level" value={f.level} onChange={(e) => set({ level: e.target.value })}>
            {Object.entries(LEVEL_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </Select>
        </Field>
        <Field label="Scadenza iscrizioni" htmlFor="cp-dead"><Input id="cp-dead" type="date" value={f.registration_deadline} onChange={(e) => set({ registration_deadline: e.target.value })} /></Field>
        <Field label="Quota iscrizione (€)" htmlFor="cp-fee"><Input id="cp-fee" inputMode="decimal" value={f.fee} onChange={(e) => set({ fee: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Età min" htmlFor="cp-min"><Input id="cp-min" type="number" value={f.min_age} onChange={(e) => set({ min_age: e.target.value })} /></Field>
          <Field label="Età max" htmlFor="cp-max"><Input id="cp-max" type="number" value={f.max_age} onChange={(e) => set({ max_age: e.target.value })} /></Field>
        </div>
        <div className="sm:col-span-2"><Field label="Categorie" htmlFor="cp-cat"><Input id="cp-cat" value={f.categories} onChange={(e) => set({ categories: e.target.value })} placeholder="es. Esordienti A/B, Cadetti" /></Field></div>
        <div className="sm:col-span-2"><Field label="Descrizione" htmlFor="cp-desc"><Textarea id="cp-desc" value={f.description} onChange={(e) => set({ description: e.target.value })} /></Field></div>
        <label className="sm:col-span-2 flex items-center gap-2 text-sm text-ink-700"><input type="checkbox" checked={f.requires} onChange={(e) => set({ requires: e.target.checked })} className="accent-brand-500 h-4 w-4" /> Serve il certificato agonistico valido alla data della gara</label>
        <div className="sm:col-span-2 rounded-2xl ring-1 ring-ink-200 p-4 space-y-4">
          <label className="flex items-center gap-2 text-sm font-semibold text-ink-900">
            <input type="checkbox" checked={f.transport_needed} onChange={(e) => set({ transport_needed: e.target.checked })} className="accent-brand-500 h-4 w-4" />
            🚌 {t("event.transportNeeded")}
          </label>
          {f.transport_needed && (
            <div className="grid sm:grid-cols-2 gap-4">
              <p className="sm:col-span-2 text-xs text-ink-500">{t("event.transportHint")}</p>
              <Field label={t("event.entityName")} htmlFor="cp-tr-name"><Input id="cp-tr-name" value={f.transport_entity_name} onChange={(e) => set({ transport_entity_name: e.target.value })} placeholder="Câmara Municipal de Lagos" /></Field>
              <Field label={t("event.entityEmail")} htmlFor="cp-tr-email"><Input id="cp-tr-email" type="email" value={f.transport_entity_email} onChange={(e) => set({ transport_entity_email: e.target.value })} /></Field>
              <Field label={t("event.departure")} htmlFor="cp-tr-dep"><Input id="cp-tr-dep" value={f.transport_departure} onChange={(e) => set({ transport_departure: e.target.value })} placeholder={t("event.departurePlaceholder")} /></Field>
              <Field label={t("event.return")} htmlFor="cp-tr-ret"><Input id="cp-tr-ret" value={f.transport_return} onChange={(e) => set({ transport_return: e.target.value })} /></Field>
              <Field label={t("event.companions")} hint={t("event.companionsHint")} htmlFor="cp-tr-comp"><Input id="cp-tr-comp" type="number" min={0} value={f.transport_companions} onChange={(e) => set({ transport_companions: e.target.value })} /></Field>
              <div className="sm:col-span-2"><Field label={t("event.notes")} htmlFor="cp-tr-notes"><Textarea id="cp-tr-notes" value={f.transport_notes} onChange={(e) => set({ transport_notes: e.target.value })} /></Field></div>
              <label className="sm:col-span-2 flex items-start gap-2 text-sm text-ink-700">
                <input type="checkbox" checked={f.transport_auto_send} onChange={(e) => set({ transport_auto_send: e.target.checked })} className="accent-brand-500 h-4 w-4 mt-0.5" />
                <span>{t("event.autoSend")}</span>
              </label>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}

/** La lettera al comune per il trasporto: si prepara da sola alla chiusura
 *  delle iscrizioni; qui la segreteria la rilegge, la corregge e la manda
 *  con un clic. */
function TransportModal({ competition: c, onClose }: { competition: Competition; onClose: () => void }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["club", "admin", "transport", c.id],
    queryFn: () => clubGet<TransportRequest>(A(`/competitions/${c.id}/transport`)),
  });
  if (isLoading || !data) {
    return <Modal open onClose={onClose} size="lg" title={t("event.transportRequest")}><Skeleton className="h-64" /></Modal>;
  }
  // La chiave rimonta l'editor quando la bozza viene riscritta: i campi
  // ripartono dal testo nuovo invece di sincronizzarsi con un effetto.
  return <TransportEditor key={`${data.id}-${data.subject}-${data.athletes_count}`} competition={c} request={data} onClose={onClose}
    onSaved={(r) => queryClient.setQueryData(["club", "admin", "transport", c.id], r)} />;
}

function TransportEditor({ competition: c, request, onClose, onSaved }: {
  competition: Competition; request: TransportRequest; onClose: () => void; onSaved: (r: TransportRequest) => void;
}) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const [to, setTo] = useState(request.to_email ?? "");
  const [subject, setSubject] = useState(request.subject);
  const [body, setBody] = useState(request.body_text);
  const [busy, setBusy] = useState<"save" | "send" | "regen" | null>(null);
  const [error, setError] = useState<string | null>(request.last_error);
  const stale = request.current_athletes_count !== request.athletes_count;

  async function act(kind: "save" | "send" | "regen") {
    setBusy(kind);
    setError(null);
    try {
      const r = kind === "regen"
        ? await clubSend<TransportRequest>(A(`/competitions/${c.id}/transport/regenerate`), "POST")
        : await clubSend<TransportRequest>(A(`/competitions/${c.id}/transport${kind === "send" ? "/send" : ""}`), kind === "send" ? "POST" : "PUT", { to_email: to, subject, body_text: body });
      onSaved(r);
      if (kind === "send") {
        toast({ tone: "success", title: t("event.sent"), text: t("event.sentText", { to }) });
        onClose();
      } else if (kind === "save") {
        toast({ tone: "success", title: t("event.saved") });
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal open onClose={onClose} size="xl" title={`${t("event.transportRequest")} · ${c.name}`}
      subtitle={request.status === "SENT" && request.sent_at ? t("event.sentOn", { date: fmt.shortDate(request.sent_at) }) : t("event.draftSubtitle")}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        <Button variant="secondary" loading={busy === "save"} onClick={() => act("save")}>{t("common.save")}</Button>
        <Button loading={busy === "send"} disabled={!to.includes("@") || subject.length < 3 || body.length < 10} onClick={() => window.confirm(t("event.sendConfirm", { to })) && act("send")}>
          {request.status === "SENT" ? t("event.resend") : t("event.send")}
        </Button>
      </>}
    >
      <div className="space-y-4">
        {stale && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-amber-50 ring-1 ring-amber-200 p-3 text-sm text-amber-900">
            <span>{t("event.stale", { then: request.athletes_count, now: request.current_athletes_count })}</span>
            <Button size="sm" variant="secondary" loading={busy === "regen"} onClick={() => window.confirm(t("event.regenConfirm")) && act("regen")}>{t("event.regenerate")}</Button>
          </div>
        )}
        {c.status === "OPEN" && <p className="text-xs text-ink-500">{t("event.stillOpen")}</p>}
        <Field label={t("event.to")} htmlFor="tr-to"><Input id="tr-to" type="email" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <Field label={t("event.subject")} htmlFor="tr-subject"><Input id="tr-subject" value={subject} onChange={(e) => setSubject(e.target.value)} /></Field>
        <Field label={t("event.body")} hint={t("event.bodyHint")} htmlFor="tr-body">
          <Textarea id="tr-body" value={body} onChange={(e) => setBody(e.target.value)} rows={16} className="font-mono text-xs" />
        </Field>
        {!stale && <Button size="sm" variant="ghost" loading={busy === "regen"} onClick={() => window.confirm(t("event.regenConfirm")) && act("regen")}>{t("event.regenerate")}</Button>}
        {error && <Badge tone="danger">{error}</Badge>}
      </div>
    </Modal>
  );
}

const PLACEMENT_OPTIONS = [1, 2, 3, 5, 7, 0];

function ResultsModal({ competition: c, onClose }: { competition: Competition; onClose: () => void }) {
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "entries", c.id], queryFn: () => clubGet<Entry[]>(A(`/competitions/${c.id}/entries`)) });
  const [placements, setPlacements] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [letterFor, setLetterFor] = useState<Entry | null>(null);
  const run = useRun();
  const value = (e: Entry) => placements[e.id] ?? (e.placement != null ? String(e.placement) : "");
  async function save() {
    setBusy(true);
    const results = (data ?? []).map((e) => ({ entry_id: e.id, placement: value(e) === "" ? null : Number(value(e)) }));
    const ok = await run(() => clubSend(A(`/competitions/${c.id}/results`), "PUT", { results }), "Risultati salvati: ranking aggiornato");
    setBusy(false);
    if (ok) onClose();
  }
  return (
    <Modal open onClose={onClose} size="lg" title={`Iscritti e risultati · ${c.name}`} footer={<><Button variant="ghost" onClick={onClose}>Chiudi</Button><Button loading={busy} onClick={save} disabled={!data?.length || c.kind === "STAGE"}>Salva risultati</Button></>}>
      {isLoading ? <Skeleton className="h-40" /> : (data ?? []).length === 0 ? <p className="text-sm text-ink-500">Nessun iscritto.</p> : (
        <div className="space-y-2">
          {(data ?? []).map((e) => (
            <div key={e.id} className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-2xl bg-white ring-1 ring-ink-100 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink-900">{e.athlete_name} <AthleteMarks id={e.athlete_id} /></p>
                <p className="text-xs text-ink-500">{e.category ?? "Categoria da definire"}{e.weight_kg ? ` · ${e.weight_kg} kg` : ""}{e.fee_status ? ` · quota ${e.fee_status === "PAID" ? "pagata" : e.fee_status === "DUE" ? "da pagare" : e.fee_status.toLowerCase()}` : ""}{e.status === "WITHDRAWN" ? " · ritirato" : ""}</p>
              </div>
              {e.status === "REGISTERED" && (
                <Button size="sm" variant="secondary" onClick={() => setLetterFor(e)} title="Giustificazione delle assenze per la scuola">
                  🏫 {e.school_letter_at ? "Giustificazione ✓" : "Giustificazione"}
                </Button>
              )}
              <Select value={value(e)} onChange={(ev) => setPlacements((p) => ({ ...p, [e.id]: ev.target.value }))} className="sm:w-48" aria-label={`Risultato di ${e.athlete_name}`} disabled={e.status === "WITHDRAWN"}>
                <option value="">— nessun risultato —</option>
                {PLACEMENT_OPTIONS.map((pl) => <option key={pl} value={pl}>{PLACEMENT_LABELS[pl]}</option>)}
              </Select>
            </div>
          ))}
        </div>
      )}
      {letterFor && <SchoolLetterModal competition={c} entry={letterFor} onClose={() => setLetterFor(null)} />}
    </Modal>
  );
}

/** La giustificazione per la scuola: il testo proposto si corregge (la
 *  classe, il nome della scuola, una riga in più), poi si genera il PDF su
 *  carta intestata. Il file resta nell'area privata: si apre con un link
 *  che scade dopo pochi minuti. */
function SchoolLetterModal({ competition: c, entry, onClose }: { competition: Competition; entry: Entry; onClose: () => void }) {
  const base = A(`/competitions/${c.id}/entries/${entry.id}/school-letter`);
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "school-letter", entry.id], queryFn: () => clubGet<SchoolLetter>(base) });
  if (isLoading || !data) {
    return <Modal open onClose={onClose} size="lg" title="Giustificazione per la scuola"><Skeleton className="h-64" /></Modal>;
  }
  // La chiave rimonta l'editor quando arriva un testo nuovo (proposta da
  // capo): il campo riparte da lì invece di sincronizzarsi con un effetto.
  return <SchoolLetterEditor key={data.body_text} base={base} competition={c} letter={data} onClose={onClose} />;
}

function SchoolLetterEditor({ base, competition: c, letter, onClose }: { base: string; competition: Competition; letter: SchoolLetter; onClose: () => void }) {
  const [body, setBody] = useState(letter.body_text);
  const [busy, setBusy] = useState<"generate" | "open" | "fresh" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();

  async function act(kind: "generate" | "open" | "fresh") {
    setBusy(kind);
    setError(null);
    // La finestra si apre subito, nel clic: aperta dopo l'await, il browser
    // la bloccherebbe come popup.
    const tab = kind === "fresh" ? null : window.open("", "_blank");
    if (tab) tab.opener = null;
    try {
      if (kind === "fresh") {
        const fresh = await clubGet<SchoolLetter>(`${base}?fresh=true`);
        queryClient.setQueryData(["club", "admin", "school-letter", letter.entry_id], fresh);
        return;
      }
      const { url } = kind === "generate"
        ? await clubSend<{ url: string }>(base, "POST", { body_text: body })
        : await clubGet<{ url: string }>(`${base}/url`);
      if (tab) tab.location.href = url;
      else window.location.href = url;
      if (kind === "generate") {
        await queryClient.invalidateQueries({ queryKey: ["club", "admin", "entries", c.id] });
        await queryClient.invalidateQueries({ queryKey: ["club", "admin", "school-letter", letter.entry_id] });
        toast({ tone: "success", title: "Giustificazione pronta", text: "Il PDF è salvato nell'area privata del club." });
      }
    } catch (e) {
      tab?.close();
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal open onClose={onClose} size="xl" title={`Giustificazione per la scuola · ${letter.athlete_name}`}
      subtitle={letter.generated_at ? `Ultimo PDF generato il ${shortDate(letter.generated_at)}` : `${c.name} · ${shortDate(c.starts_on)}`}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Chiudi</Button>
        {letter.generated_at && <Button variant="secondary" loading={busy === "open"} onClick={() => act("open")}>{"Scarica l'ultimo PDF ↗"}</Button>}
        <Button loading={busy === "generate"} disabled={body.trim().length < 20} onClick={() => act("generate")}>
          {letter.generated_at ? "Rigenera e scarica il PDF" : "Genera e scarica il PDF"}
        </Button>
      </>}
    >
      <div className="space-y-3">
        <p className="text-sm text-ink-500">
          {"Rileggi il testo e aggiungi quello che serve (la classe, la scuola, gli orari del viaggio). Il PDF esce su carta intestata del club e resta salvato nell'area privata: anche il genitore lo può scaricare dalla sua pagina delle gare."}
        </p>
        <Field label="Testo" hint="Una riga vuota separa i paragrafi." htmlFor="sl-body">
          <Textarea id="sl-body" value={body} onChange={(e) => setBody(e.target.value)} rows={18} maxLength={6000} className="text-sm leading-relaxed" />
        </Field>
        <Button size="sm" variant="ghost" loading={busy === "fresh"} onClick={() => window.confirm("Ripartire dal testo proposto? Le tue correzioni non salvate si perdono.") && act("fresh")}>
          ↺ Riparti dal testo proposto
        </Button>
        {error && <Badge tone="danger">{error}</Badge>}
      </div>
    </Modal>
  );
}

// --- Corsi ------------------------------------------------------------------------------------

function Courses() {
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "courses"], queryFn: () => clubGet<Course[]>(A("/courses")) });
  const [editing, setEditing] = useState<Course | "new" | null>(null);
  const run = useRun();
  const [slot, setSlot] = useState<Record<string, { weekday: string; from: string; to: string; room: string }>>({});
  const [editingSlot, setEditingSlot] = useState<{ slot: Course["slots"][number]; course: string } | null>(null);
  const days = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"];
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => setEditing("new")} icon={<span>＋</span>}>Nuovo corso</Button></div>
      {isLoading ? <Skeleton className="h-48" /> : (data ?? []).length === 0 ? <EmptyState icon={<span className="text-3xl">📅</span>} title="Nessun corso" action={<Button onClick={() => setEditing("new")}>Crea il primo corso</Button>} /> : (
        <div className="grid md:grid-cols-2 gap-4">
          {(data ?? []).map((c) => {
            const s = slot[c.id] ?? { weekday: "0", from: "17:00", to: "18:00", room: "" };
            return (
              <div key={c.id} className="glass-card rounded-3xl p-5 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-base text-ink-900">{c.name}</h3>
                    <p className="text-sm text-ink-500">{[c.level, c.instructor_name, `${c.athletes_count} iscritti`].filter(Boolean).join(" · ")}</p>
                  </div>
                  <Button size="sm" variant="secondary" onClick={() => setEditing(c)}>Modifica</Button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {c.slots.map((sl) => (
                    <span key={sl.id} className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 ring-1 ring-brand-200 px-2.5 py-1 text-xs font-semibold text-brand-800">
                      <button type="button" title="Modifica orario" className="cursor-pointer hover:underline" onClick={() => setEditingSlot({ slot: sl, course: c.name })}>
                        ✎ {days[sl.weekday]?.slice(0, 3)} {sl.starts_at.slice(0, 5)}–{sl.ends_at.slice(0, 5)}{sl.room ? ` · ${sl.room}` : ""}
                      </button>
                      <button aria-label="Togli orario" className="text-brand-500 hover:text-brand-800 cursor-pointer" onClick={() => run(() => clubSend(A(`/slots/${sl.id}`), "DELETE"), "Orario tolto")}>✕</button>
                    </span>
                  ))}
                </div>
                <div className="flex flex-wrap items-end gap-2 pt-2 border-t border-ink-100">
                  <Select value={s.weekday} onChange={(e) => setSlot((x) => ({ ...x, [c.id]: { ...s, weekday: e.target.value } }))} className="w-32" aria-label="Giorno">
                    {days.map((d, i) => <option key={d} value={i}>{d}</option>)}
                  </Select>
                  <Input type="time" value={s.from} onChange={(e) => setSlot((x) => ({ ...x, [c.id]: { ...s, from: e.target.value } }))} className="w-28" aria-label="Dalle" />
                  <Input type="time" value={s.to} onChange={(e) => setSlot((x) => ({ ...x, [c.id]: { ...s, to: e.target.value } }))} className="w-28" aria-label="Alle" />
                  <Input placeholder="Sala" value={s.room} onChange={(e) => setSlot((x) => ({ ...x, [c.id]: { ...s, room: e.target.value } }))} className="w-28" />
                  <Button size="md" variant="secondary" onClick={() => run(() => clubSend(A(`/courses/${c.id}/slots`), "POST", { weekday: Number(s.weekday), starts_at: s.from, ends_at: s.to, room: s.room || null }), "Orario aggiunto")}>＋ Orario</Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {editing && <CourseModal course={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {editingSlot && <SlotEditModal slot={editingSlot.slot} courseName={editingSlot.course} onClose={() => setEditingSlot(null)} />}
    </div>
  );
}

function CourseModal({ course: c, onClose }: { course: Course | null; onClose: () => void }) {
  const [name, setName] = useState(c?.name ?? "");
  const [description, setDescription] = useState(c?.description ?? "");
  const [level, setLevel] = useState(c?.level ?? "");
  const [minAge, setMinAge] = useState(c?.min_age != null ? String(c.min_age) : "");
  const [maxAge, setMaxAge] = useState(c?.max_age != null ? String(c.max_age) : "");
  const [active, setActive] = useState(c?.active ?? true);
  const [busy, setBusy] = useState(false);
  const run = useRun();
  async function save() {
    setBusy(true);
    const body = { name, description: description || null, level: level || null, min_age: minAge ? Number(minAge) : null, max_age: maxAge ? Number(maxAge) : null, active };
    const ok = await run(() => (c ? clubSend(A(`/courses/${c.id}`), "PATCH", body) : clubSend(A("/courses"), "POST", body)), c ? "Corso aggiornato" : "Corso creato");
    setBusy(false);
    if (ok) onClose();
  }
  return (
    <Modal open onClose={onClose} title={c ? "Modifica corso" : "Nuovo corso"} footer={<><Button variant="ghost" onClick={onClose}>Annulla</Button><Button loading={busy} onClick={save} disabled={!name}>Salva</Button></>}>
      <div className="space-y-4">
        <Field label="Nome" htmlFor="co-name"><Input id="co-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="es. Judo bambini" /></Field>
        <Field label="Livello" htmlFor="co-level"><Input id="co-level" value={level} onChange={(e) => setLevel(e.target.value)} placeholder="es. Principianti" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Età min" htmlFor="co-min"><Input id="co-min" type="number" value={minAge} onChange={(e) => setMinAge(e.target.value)} /></Field>
          <Field label="Età max" htmlFor="co-max"><Input id="co-max" type="number" value={maxAge} onChange={(e) => setMaxAge(e.target.value)} /></Field>
        </div>
        <Field label="Descrizione" htmlFor="co-desc"><Textarea id="co-desc" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <label className="flex items-center gap-2 text-sm text-ink-700"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} className="accent-brand-500 h-4 w-4" /> Corso attivo</label>
      </div>
    </Modal>
  );
}


// --- Ordini dello Shop ------------------------------------------------------------------------

interface ClubShopOrder {
  id: string;
  number: string;
  created_at: string;
  customer_email: string | null;
  athlete_name: string | null;
  items_summary: string;
  amount_cents: number;
  status: string;
  fulfillment_status: string;
  payment_proof_uploaded_at: string | null;
}

/** Gli ordini dello Shop delle famiglie del club, in sola lettura: lo Shop è
 *  della piattaforma, che conferma i bonifici e spedisce. Alla segreteria
 *  serve sapere chi ha ordinato che cosa, e se il judogi è partito. */
function ShopOrders() {
  const { t, fmt } = useI18n();
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "shop-orders"], queryFn: () => clubGet<ClubShopOrder[]>(A("/shop-orders")) });
  const statusTone = (s: string) => (s === "PAID" ? "success" : s === "CANCELLED" ? "danger" : "warning");
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">{t("clubAdmin.shopOrdersIntro")}</p>
      {isLoading ? <Skeleton className="h-64" /> : (data ?? []).length === 0 ? <EmptyState title={t("clubAdmin.shopOrdersEmpty")} /> : (
        <Table>
          <THead><tr><TH>{t("clubAdmin.colOrder")}</TH><TH>{t("clubAdmin.colFamily")}</TH><TH>{t("clubAdmin.colItems")}</TH><TH>{t("clubAdmin.colStatus")}</TH><TH className="text-right">{t("clubAdmin.colAmount")}</TH></tr></THead>
          <TBody>
            {(data ?? []).map((o) => (
              <TR key={o.id}>
                <TD><p className="font-semibold text-ink-900">{o.number}</p><p className="text-xs text-ink-500">{fmt.shortDate(o.created_at)}</p></TD>
                <TD className="text-xs">{o.customer_email ?? "—"}{o.athlete_name && <p className="text-ink-500">{t("pay.orderFor", { name: o.athlete_name })}</p>}</TD>
                <TD className="text-sm">{o.items_summary}</TD>
                <TD>
                  <Badge tone={statusTone(o.status)} dot>{t.dyn(`clubAdmin.orderStatus.${o.status}`, o.status)}</Badge>
                  {o.status === "AWAITING_PAYMENT" && o.payment_proof_uploaded_at && <p className="text-[11px] text-ink-500 mt-1">{t("clubAdmin.proofUploaded")}</p>}
                  {o.status === "PAID" && <p className="text-[11px] text-ink-500 mt-1">{t.dyn(`clubAdmin.fulfillment.${o.fulfillment_status}`, o.fulfillment_status)}</p>}
                </TD>
                <TD className="text-right font-semibold">{fmt.euro(o.amount_cents)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}

// --- Impostazioni del club --------------------------------------------------------------------

interface StaffRow {
  user_id: string;
  email: string;
  role: string;
}

/** Ciò che la segreteria cura del proprio club: le coordinate su cui le
 *  famiglie pagano le quote, il link da dare alle famiglie per registrarsi,
 *  e chi lavora nel club (segreteria e istruttori). */
function ClubSettingsSection() {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data: club } = useCurrentClub();
  const { data: staff } = useQuery({ queryKey: ["club", "admin", "staff"], queryFn: () => clubGet<StaffRow[]>(A("/staff")) });
  const [adding, setAdding] = useState(false);
  if (!club) return <Skeleton className="h-64" />;

  async function copyLink() {
    if (!club) return;
    const result = await shareOrCopyLink({ url: clubSignupUrl(club.slug), title: club.name, preferClipboard: true });
    toast({ tone: result === "failed" ? "error" : "success", title: result === "failed" ? t("clubs.copyFailed") : t("clubs.copied") });
  }

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <div className="space-y-6">
        <div className="glass-card rounded-3xl p-5 space-y-3">
          <h3 className="text-base text-ink-900">{t("clubAdmin.signupTitle")}</h3>
          <p className="text-sm text-ink-500">{t("clubAdmin.signupText")}</p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="rounded-xl bg-ink-50 px-3 py-2 text-sm text-ink-900 break-all">{clubSignupUrl(club.slug)}</code>
            <Button size="sm" variant="secondary" onClick={copyLink}>{t("clubs.copyLink")}</Button>
          </div>
        </div>
        <div className="glass-card rounded-3xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-base text-ink-900">{t("clubAdmin.staffTitle")}</h3>
            <Button size="sm" onClick={() => setAdding(true)}>{t("clubs.addStaff")}</Button>
          </div>
          {(staff ?? []).length === 0 ? <p className="text-sm text-ink-500">{t("clubs.noSecretary")}</p> : (
            <ul className="divide-y divide-ink-100">
              {(staff ?? []).map((s) => (
                <li key={s.user_id} className="flex items-center justify-between py-2 text-sm">
                  <span className="text-ink-900">{s.email}</span>
                  <Badge tone={s.role === "SECRETARY" ? "brand" : "neutral"}>{t.dyn(`clubs.role.${s.role}`, s.role)}</Badge>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div className="space-y-6">
        <BankForm key={club.id} initial={club.settings} />
        <PricingForm />
      </div>
      {adding && (
        <StaffModal
          title={t("clubs.addStaffTo", { name: club.name })}
          onClose={() => setAdding(false)}
          onSubmit={async (email, role) => {
            const created = await clubSend<{ invite_link: string | null }>(A("/staff"), "POST", { email, role });
            await queryClient.invalidateQueries({ queryKey: ["club", "admin", "staff"] });
            return created.invite_link;
          }}
        />
      )}
    </div>
  );
}

function BankForm({ initial }: { initial: ClubSettings }) {
  const { t } = useI18n();
  const run = useRun();
  const [iban, setIban] = useState(initial.bank_iban ?? "");
  const [holder, setHolder] = useState(initial.bank_account_holder ?? "");
  const [instructions, setInstructions] = useState(initial.bank_transfer_instructions ?? "");
  const [contact, setContact] = useState(initial.contact_email ?? "");
  const [entityName, setEntityName] = useState(initial.transport_entity_name ?? "");
  const [entityEmail, setEntityEmail] = useState(initial.transport_entity_email ?? "");
  const [language, setLanguage] = useState(initial.letters_language ?? "pt");
  const [lateOn, setLateOn] = useState(Boolean(initial.late_fee_enabled));
  const [lateFee, setLateFee] = useState(toEuro(initial.late_fee_cents ?? 1500));
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    await run(
      () => clubSend(A("/settings"), "PATCH", {
        bank_iban: iban, bank_account_holder: holder, bank_transfer_instructions: instructions, contact_email: contact,
        transport_entity_name: entityName, transport_entity_email: entityEmail, letters_language: language,
        late_fee_enabled: lateOn, late_fee_cents: toCents(lateFee) || 1500,
      }),
      t("clubAdmin.bankSaved"),
    );
    setBusy(false);
  }
  return (
    <div className="glass-card rounded-3xl p-5 space-y-4">
      <div>
        <h3 className="text-base text-ink-900">{t("clubAdmin.bankTitle")}</h3>
        <p className="text-sm text-ink-500">{t("clubAdmin.bankText")}</p>
      </div>
      <Field label="IBAN" htmlFor="club-bank-iban"><Input id="club-bank-iban" value={iban} onChange={(e) => setIban(e.target.value)} /></Field>
      <Field label={t("clubs.fieldHolder")} htmlFor="club-bank-holder"><Input id="club-bank-holder" value={holder} onChange={(e) => setHolder(e.target.value)} /></Field>
      <Field label={t("clubAdmin.bankInstructions")} htmlFor="club-bank-instr"><Textarea id="club-bank-instr" value={instructions} onChange={(e) => setInstructions(e.target.value)} maxLength={500} /></Field>
      <Field label={t("clubAdmin.contactEmail")} hint={t("clubAdmin.contactEmailHint")} htmlFor="club-contact"><Input id="club-contact" type="email" value={contact} onChange={(e) => setContact(e.target.value)} /></Field>
      <div className="border-t border-ink-100 pt-4 space-y-4">
        <div>
          <h3 className="text-base text-ink-900">🚌 {t("clubAdmin.transportTitle")}</h3>
          <p className="text-sm text-ink-500">{t("clubAdmin.transportText")}</p>
        </div>
        <Field label={t("event.entityName")} htmlFor="club-tr-name"><Input id="club-tr-name" value={entityName} onChange={(e) => setEntityName(e.target.value)} placeholder="Câmara Municipal de Lagos" /></Field>
        <Field label={t("event.entityEmail")} htmlFor="club-tr-email"><Input id="club-tr-email" type="email" value={entityEmail} onChange={(e) => setEntityEmail(e.target.value)} /></Field>
        <Field label={t("clubAdmin.lettersLanguage")} htmlFor="club-letters-lang">
          <Select id="club-letters-lang" value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="pt">Português</option>
            <option value="it">Italiano</option>
            <option value="en">English</option>
          </Select>
        </Field>
      </div>
      <div className="border-t border-ink-100 pt-4 space-y-3">
        <div>
          <h3 className="text-base text-ink-900">⏰ {t("lateFee.title")}</h3>
          <p className="text-sm text-ink-500">{t("lateFee.text")}</p>
        </div>
        <label className="flex cursor-pointer items-center gap-3 text-sm font-semibold text-ink-800">
          <input type="checkbox" className="h-5 w-5 accent-brand-600" checked={lateOn} onChange={(e) => setLateOn(e.target.checked)} />
          {t("lateFee.enable")}
        </label>
        {lateOn && (
          <Field label={t("lateFee.amount")} htmlFor="club-late-fee">
            <Input id="club-late-fee" inputMode="decimal" value={lateFee} onChange={(e) => setLateFee(e.target.value)} />
          </Field>
        )}
      </div>
      <Button onClick={save} loading={busy}>{t("common.save")}</Button>
    </div>
  );
}

/** Gli sconti e le quote del club (apps/api/app/domains/club/pricing.py).
 *  Valgono per le quote emesse da adesso: quelle già emesse non cambiano. */
function PricingForm() {
  const { data } = useQuery({ queryKey: ["club", "admin", "pricing"], queryFn: () => clubGet<Pricing>(A("/pricing")) });
  if (!data) return <Skeleton className="h-64" />;
  return <PricingEditor key={JSON.stringify(data)} initial={data} />;
}

const toEuro = (cents: number) => String(cents / 100).replace(".", ",");
const toCents = (value: string) => Math.round(Number(value.replace(",", ".")) * 100) || 0;

function PricingEditor({ initial }: { initial: Pricing }) {
  const { t } = useI18n();
  const run = useRun();
  const [tiers, setTiers] = useState({
    A: String(initial.tier_discount_pct.A ?? 0), B: String(initial.tier_discount_pct.B ?? 0), C: String(initial.tier_discount_pct.C ?? 0),
  });
  const [family, setFamily] = useState(toEuro(initial.family_discount_cents));
  const [familyMin, setFamilyMin] = useState(String(initial.family_min_athletes));
  const [referral, setReferral] = useState(toEuro(initial.referral_credit_cents));
  const [member, setMember] = useState(toEuro(initial.parent_member_fee_cents));
  const [includes, setIncludes] = useState(initial.enrollment_includes);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    await run(() => clubSend(A("/pricing"), "PATCH", {
      tier_discount_pct: { A: Number(tiers.A) || 0, B: Number(tiers.B) || 0, C: Number(tiers.C) || 0 },
      family_discount_cents: toCents(family), family_min_athletes: Number(familyMin) || 2,
      referral_credit_cents: toCents(referral), parent_member_fee_cents: toCents(member), enrollment_includes: includes,
    }), t("clubAdmin.pricingSaved"));
    setBusy(false);
  }
  return (
    <div className="glass-card rounded-3xl p-5 space-y-4">
      <div>
        <h3 className="text-base text-ink-900">{t("clubAdmin.pricingTitle")}</h3>
        <p className="text-sm text-ink-500">{t("clubAdmin.pricingText")}</p>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {(["A", "B", "C"] as const).map((tier) => (
          <Field key={tier} label={`Escalão ${tier} (%)`} htmlFor={`pr-tier-${tier}`}>
            <Input id={`pr-tier-${tier}`} type="number" min={0} max={100} value={tiers[tier]} onChange={(e) => setTiers((x) => ({ ...x, [tier]: e.target.value }))} />
          </Field>
        ))}
      </div>
      <p className="text-xs text-ink-500">{t("clubAdmin.adaptedHint")}</p>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t("clubAdmin.familyDiscount")} htmlFor="pr-family"><Input id="pr-family" inputMode="decimal" value={family} onChange={(e) => setFamily(e.target.value)} /></Field>
        <Field label={t("clubAdmin.familyMin")} htmlFor="pr-family-min"><Input id="pr-family-min" type="number" min={2} max={10} value={familyMin} onChange={(e) => setFamilyMin(e.target.value)} /></Field>
        <Field label={t("clubAdmin.referralCredit")} hint={t("clubAdmin.referralCreditHint")} htmlFor="pr-ref"><Input id="pr-ref" inputMode="decimal" value={referral} onChange={(e) => setReferral(e.target.value)} /></Field>
        <Field label={t("clubAdmin.parentMemberFee")} hint={t("clubAdmin.parentMemberFeeHint")} htmlFor="pr-member"><Input id="pr-member" inputMode="decimal" value={member} onChange={(e) => setMember(e.target.value)} /></Field>
      </div>
      <Field label={t("clubAdmin.enrollmentIncludes")} hint={t("clubAdmin.enrollmentIncludesHint")} htmlFor="pr-includes">
        <Textarea id="pr-includes" value={includes} onChange={(e) => setIncludes(e.target.value)} maxLength={300} />
      </Field>
      <Button onClick={save} loading={busy}>{t("common.save")}</Button>
    </div>
  );
}
