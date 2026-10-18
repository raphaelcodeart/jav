"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell, type NavItem } from "@/components/app-shell";
import { SchoolBadge, useGroupLine, useMethodLabel, usePeriodLabel } from "@/components/ext-courses/common";
import { ExtSignupForm } from "@/components/ext-courses/signup-form";
import { Badge, FeeStatusPill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { ProgressBar } from "@/components/ui/progress";
import { ProofPicker } from "@/components/ui/proof-picker";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { extGet, extSend, type ExtCourse, type ExtFamily, type ExtFee } from "@/lib/ext-courses";
import { useI18n } from "@/lib/i18n/provider";
import { celebrate } from "@/lib/motion";

const FAMILY_KEY = ["ext", "family"];
type Tab = "home" | "fees" | "enroll";

const emoji = (e: string) => <span className="text-base leading-none" aria-hidden="true">{e}</span>;

/** L'area del genitore dei corsi esterni (/cursos): avvisi, i figli con il
 *  loro corso, le mensilità con la prova di pagamento, l'iscrizione di un
 *  altro figlio. Nient'altro: niente JAVBOT, Shop, wallet, cinture. Pensata
 *  per il telefono: la cosa da fare (pagare) è un bottone grande in cima. */
export function ExtFamilyArea({ email }: { email?: string }) {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>("home");
  const [payOpen, setPayOpen] = useState(false);
  const { data, isLoading, error } = useQuery({ queryKey: FAMILY_KEY, queryFn: () => extGet<ExtFamily>("/family") });

  const navItems: NavItem[] = [
    { key: "home", label: t("ext.family.navHome"), icon: emoji("🏠") },
    { key: "fees", label: t("ext.family.navFees"), icon: emoji("💶") },
    { key: "enroll", label: t("ext.family.navEnroll"), icon: emoji("➕") },
  ];

  return (
    <AppShell roleLabel={t("ext.family.role")} email={email} navItems={navItems} activeKey={tab} onNavigate={(k) => setTab(k as Tab)}>
      <MotionConfig reducedMotion="user">
        {isLoading ? (
          <div className="mx-auto max-w-2xl space-y-4"><Skeleton className="h-40" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div>
        ) : error || !data ? (
          <EmptyState icon={<span className="text-3xl">🎒</span>} title={t("ext.family.loadFailed")} text={(error as Error | null)?.message} />
        ) : (
          <div className="mx-auto max-w-2xl">
            {tab === "home" && <FamilyHome data={data} onPay={() => setPayOpen(true)} onEnroll={() => setTab("enroll")} />}
            {tab === "fees" && <FamilyFees data={data} onPay={() => setPayOpen(true)} />}
            {tab === "enroll" && <EnrollAnother onDone={() => setTab("home")} />}
            <ProofModal open={payOpen} onClose={() => setPayOpen(false)} data={data} />
          </div>
        )}
      </MotionConfig>
    </AppShell>
  );
}

function FamilyHome({ data, onPay, onEnroll }: { data: ExtFamily; onPay: () => void; onEnroll: () => void }) {
  const { t, fmt } = useI18n();
  const groupLine = useGroupLine();
  const courses = new Map(data.courses.map((c) => [c.id, c]));

  if (data.children.length === 0) {
    return (
      <EmptyState icon={<span className="text-3xl">🎒</span>} title={t("ext.family.emptyTitle")} text={t("ext.family.emptyText")}
        action={<Button onClick={onEnroll}>{t("ext.family.enrollChild")}</Button>} />
    );
  }

  return (
    <div className="space-y-6">
      {data.notices.length > 0 && (
        <section aria-labelledby="ext-notices" className="space-y-2">
          <h2 id="ext-notices" className="px-1 text-xs font-bold uppercase tracking-[0.2em] text-brand-600">📣 {t("ext.family.notices")}</h2>
          {data.notices.map((n, i) => (
            <motion.article key={n.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
              className="rounded-2xl bg-accent-100/80 p-4 ring-1 ring-accent-300">
              <div className="flex items-start justify-between gap-3">
                <p className="font-semibold text-ink-900">{n.title}</p>
                <span className="shrink-0 text-xs text-ink-500">{fmt.shortDate(n.created_at)}</span>
              </div>
              {n.body && <p className="mt-1 whitespace-pre-line text-sm text-ink-700">{n.body}</p>}
              {n.course_id && courses.get(n.course_id) && <p className="mt-2 text-xs text-ink-500">🏫 {courses.get(n.course_id)?.school_name}</p>}
            </motion.article>
          ))}
        </section>
      )}

      {/* Il riquadro che conta: quanto c'è da pagare e il bottone per farlo. */}
      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-[28px] bg-gradient-to-br from-ink-900 via-ink-800 to-brand-800 p-6 text-white">
        <div className="absolute inset-0 opacity-30 bg-[radial-gradient(circle_at_85%_15%,#f9e40f,transparent_35%)]" aria-hidden="true" />
        <div className="relative space-y-4">
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-accent-300">🎒 {t("ext.family.eyebrow")}</p>
          {data.due_cents > 0 ? (
            <>
              <p className="text-3xl leading-tight sm:text-4xl">{t("ext.family.dueTitle", { amount: fmt.euro(data.due_cents) })}</p>
              {data.overdue_cents > 0 && <p className="text-sm text-accent-200">⚠️ {t("ext.family.overdue", { amount: fmt.euro(data.overdue_cents) })}</p>}
              <Button size="xl" variant="accent" className="w-full sm:w-auto" onClick={onPay} icon={<span aria-hidden="true">🧾</span>}>
                {t("ext.family.uploadProof")}
              </Button>
            </>
          ) : (
            <p className="text-3xl leading-tight sm:text-4xl">✓ {t("ext.family.allPaid")}</p>
          )}
        </div>
      </motion.section>

      <section className="space-y-3" aria-label={t("ext.family.children")}>
        {data.children.map((child, i) => {
          const course = courses.get(child.course_id);
          const pct = child.lessons_this_month > 0 ? Math.min(100, Math.round((child.present_this_month / child.lessons_this_month) * 100)) : 0;
          return (
            <Card key={child.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <div className="flex items-center gap-4">
                {course && <SchoolBadge course={course} className="h-14 w-14" />}
                <div className="min-w-0 flex-1">
                  <p className="font-display text-xl leading-tight text-ink-900">{child.first_name} {child.last_name}</p>
                  <p className="text-sm text-ink-500">{t("ext.family.age", { n: child.age })}{course ? ` · ${course.school_name}` : ""}</p>
                </div>
              </div>
              <div className="mt-4 rounded-2xl bg-ink-50 px-4 py-3 text-sm">
                {child.group ? (
                  <>
                    <p className="font-semibold text-ink-900">{child.group.name}</p>
                    <p className="capitalize text-ink-600">{groupLine(child.group)}</p>
                  </>
                ) : (
                  <p className="text-ink-600">{t("ext.family.noGroup")}</p>
                )}
              </div>
              {child.group && (
                <div className="mt-4 space-y-1.5">
                  <p className="flex justify-between text-sm">
                    <span className="text-ink-600">{t("ext.family.attendance")}</span>
                    <span className="font-semibold tabular-nums text-ink-900">{child.present_this_month}/{child.lessons_this_month}</span>
                  </p>
                  <ProgressBar value={pct} />
                </div>
              )}
            </Card>
          );
        })}
      </section>

      <Button variant="secondary" className="w-full" onClick={onEnroll}>➕ {t("ext.family.enrollAnother")}</Button>
    </div>
  );
}

function FamilyFees({ data, onPay }: { data: ExtFamily; onPay: () => void }) {
  const { t, fmt } = useI18n();
  const period = usePeriodLabel();
  const method = useMethodLabel();
  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("ext.family.eyebrow")} title={t("ext.family.navFees")} />
      <Card>
        <CardHeader title={t("ext.family.dueList")} subtitle={data.due_cents > 0 ? fmt.euro(data.due_cents) : t("ext.family.allPaid")} />
        {data.due_fees.length > 0 && (
          <>
            <FeeList fees={data.due_fees} />
            <Button size="lg" className="mt-4 w-full" onClick={onPay} icon={<span aria-hidden="true">🧾</span>}>{t("ext.family.uploadProof")}</Button>
          </>
        )}
      </Card>
      {data.proofs.length > 0 && (
        <Card>
          <CardHeader title={t("ext.family.proofs")} />
          <ul className="divide-y divide-ink-100">
            {data.proofs.map((p) => (
              <li key={p.id} className="py-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-ink-700">{fmt.shortDate(p.created_at)} · {method(p.method)}</span>
                  <span className="flex items-center gap-2">
                    <span className="font-semibold tabular-nums text-ink-900">{fmt.euro(p.amount_cents)}</span>
                    <Badge tone={p.status === "REJECTED" ? "danger" : "success"} dot>{t(p.status === "REJECTED" ? "ext.proof.rejected" : "ext.proof.accepted")}</Badge>
                  </span>
                </div>
                {p.status === "REJECTED" && p.rejection_reason && (
                  <p className="mt-1.5 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{t("ext.proof.reason", { reason: p.rejection_reason })}</p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
      {data.paid_fees.length > 0 && (
        <Card>
          <CardHeader title={t("ext.family.paidList")} />
          <ul className="divide-y divide-ink-100">
            {data.paid_fees.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <span className="min-w-0">
                  <span className="block font-semibold capitalize text-ink-900">{period(f.period)}</span>
                  <span className="block text-xs text-ink-500">{f.participant_name} · {method(f.method)} · {fmt.shortDate(f.paid_at)}</span>
                </span>
                <span className="font-semibold tabular-nums text-ink-900">{fmt.euro(f.amount_cents)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function FeeList({ fees }: { fees: ExtFee[] }) {
  const { fmt, t } = useI18n();
  const period = usePeriodLabel();
  return (
    <ul className="divide-y divide-ink-100">
      {fees.map((f) => (
        <li key={f.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
          <span className="min-w-0">
            <span className="block font-semibold capitalize text-ink-900">{period(f.period)} · {f.participant_name}</span>
            <span className="block text-xs text-ink-500">{t("ext.fee.dueOn", { date: fmt.shortDate(f.due_date) })}</span>
          </span>
          <span className="flex shrink-0 items-center gap-2">
            <span className="font-semibold tabular-nums text-ink-900">{fmt.euro(f.amount_cents)}</span>
            <FeeStatusPill status={f.status} overdue={f.overdue} />
          </span>
        </li>
      ))}
    </ul>
  );
}

type Method = "BANK_TRANSFER" | "MBWAY" | "CASH";

/** «Carregar comprovativo»: quali mensilità, come, la ricevuta. Una prova
 *  per corso (lo vuole il server): con figli in due scuole si carica due volte. */
function ProofModal({ open, onClose, data }: { open: boolean; onClose: () => void; data: ExtFamily }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const period = usePeriodLabel();
  const [selected, setSelected] = useState<Set<string>>(() => new Set(data.due_fees.map((f) => f.id)));
  const [how, setHow] = useState<Method>("BANK_TRANSFER");
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const courseOf = useMemo(() => new Map(data.children.map((c) => [c.id, c.course_id])), [data.children]);
  // Le mensilità spuntate che sono ancora da pagare (dopo un invio la lista cambia).
  const chosen = data.due_fees.filter((f) => selected.has(f.id));
  const total = chosen.reduce((s, f) => s + f.amount_cents, 0);
  const manyCourses = new Set(chosen.map((f) => courseOf.get(f.participant_id))).size > 1;
  const needsFile = how === "BANK_TRANSFER";
  const bank = data.payment_info;

  function toggle(id: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const form = new FormData();
      form.append("fee_ids", chosen.map((f) => f.id).join(","));
      form.append("method", how);
      if (note.trim()) form.append("note", note.trim());
      if (file) form.append("file", file);
      const fresh = await extSend<ExtFamily>("/family/proofs", "POST", form);
      queryClient.setQueryData(FAMILY_KEY, fresh);
      toast({ tone: "success", title: t("ext.proof.sent"), text: t("ext.proof.sentText") });
      void celebrate();
      setFile(null);
      setNote("");
      setSelected(new Set(fresh.due_fees.map((f) => f.id)));
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const methods: { key: Method; icon: string }[] = [
    { key: "BANK_TRANSFER", icon: "🏦" }, { key: "MBWAY", icon: "📱" }, { key: "CASH", icon: "💶" },
  ];

  return (
    <Modal open={open} onClose={onClose} title={t("ext.family.uploadProof")} subtitle={t("ext.proof.subtitle")} size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={submit} loading={busy} disabled={chosen.length === 0 || manyCourses || (needsFile && !file)}>
            {t("ext.proof.send", { amount: fmt.euro(total) })}
          </Button>
        </>
      }>
      <div className="space-y-5">
        {data.due_fees.length === 0 ? (
          <p className="text-sm text-ink-600">{t("ext.family.allPaid")}</p>
        ) : (
          <fieldset className="space-y-2">
            <legend className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-500">1 · {t("ext.proof.which")}</legend>
            {data.due_fees.map((f) => (
              <label key={f.id} className={cn("flex cursor-pointer items-center gap-3 rounded-2xl p-3 ring-1 transition-colors",
                selected.has(f.id) ? "bg-brand-50 ring-brand-300" : "bg-white ring-ink-200")}>
                <input type="checkbox" className="h-5 w-5 accent-brand-600" checked={selected.has(f.id)} onChange={() => toggle(f.id)} />
                <span className="min-w-0 flex-1 text-sm">
                  <span className="block font-semibold capitalize text-ink-900">{period(f.period)}</span>
                  <span className="block text-xs text-ink-500">{f.participant_name}{f.overdue ? ` · ${t("ext.fee.overdue")}` : ""}</span>
                </span>
                <span className="font-semibold tabular-nums text-ink-900">{fmt.euro(f.amount_cents)}</span>
              </label>
            ))}
            {manyCourses && <p className="text-sm font-medium text-amber-700">{t("ext.proof.oneCourse")}</p>}
          </fieldset>
        )}

        <div className="space-y-2">
          <p className="text-xs font-bold uppercase tracking-wide text-ink-500">2 · {t("ext.proof.how")}</p>
          <div className="grid grid-cols-3 gap-2" role="radiogroup">
            {methods.map((m) => (
              <button key={m.key} type="button" role="radio" aria-checked={how === m.key} onClick={() => setHow(m.key)}
                className={cn("flex cursor-pointer flex-col items-center gap-1 rounded-2xl p-3 text-center ring-1 transition-colors",
                  how === m.key ? "bg-brand-50 ring-2 ring-brand-400" : "bg-white ring-ink-200 hover:ring-ink-300")}>
                <span className="text-2xl" aria-hidden="true">{m.icon}</span>
                <span className="text-sm font-semibold text-ink-900">{t(`ext.method.${m.key}`)}</span>
              </button>
            ))}
          </div>
        </div>

        <AnimatePresence initial={false}>
          {how === "BANK_TRANSFER" && bank?.iban && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden rounded-2xl bg-ink-900 p-4 text-white">
              <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-accent-300">{t("ext.proof.bank")}</p>
              <p className="mt-1.5 break-all font-mono text-sm">{bank.iban}</p>
              {bank.holder && <p className="mt-0.5 text-xs text-ink-300">{t("ext.proof.holder", { holder: bank.holder })}</p>}
              {bank.instructions && <p className="mt-1 text-xs text-ink-300">{bank.instructions}</p>}
              <p className="mt-2 text-xs text-ink-300">{t("ext.proof.amountHint", { amount: fmt.euro(total) })}</p>
            </motion.div>
          )}
        </AnimatePresence>
        {how === "CASH" && <p className="rounded-2xl bg-ink-50 p-3 text-sm text-ink-600">{t("ext.proof.cashHint")}</p>}

        <div className="space-y-2">
          <p className="text-xs font-bold uppercase tracking-wide text-ink-500">3 · {t("ext.proof.receipt")}</p>
          <ProofPicker file={file} onFile={setFile} optional={!needsFile} />
        </div>
        <Textarea placeholder={t("ext.proof.note")} maxLength={500} className="min-h-16" value={note} onChange={(e) => setNote(e.target.value)} />
        {error && <p role="alert" className="rounded-xl bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700 ring-1 ring-rose-200">{error}</p>}
      </div>
    </Modal>
  );
}

/** «Inscrever outro filho»: i corsi pubblicati, poi lo stesso modulo del sito
 *  senza email e password. */
function EnrollAnother({ onDone }: { onDone: () => void }) {
  const { t, fmt } = useI18n();
  const queryClient = useQueryClient();
  const groupLine = useGroupLine();
  const [course, setCourse] = useState<ExtCourse | null>(null);
  const { data: courses, isLoading } = useQuery({
    queryKey: ["ext", "public-courses"],
    queryFn: async (): Promise<ExtCourse[]> => {
      const res = await fetch("/api/proxy/public/ext-courses");
      return res.ok ? res.json() : [];
    },
  });

  if (course) {
    return (
      <div className="space-y-4">
        <button type="button" onClick={() => setCourse(null)} className="cursor-pointer text-sm font-semibold text-brand-700 hover:underline">← {t("ext.family.otherCourse")}</button>
        <PageHeader eyebrow={course.school_name} title={t("ext.family.enrollChild")} subtitle={course.name} />
        <ExtSignupForm course={course} loggedIn onDone={async () => {
          await queryClient.invalidateQueries({ queryKey: FAMILY_KEY });
          onDone();
        }} />
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <PageHeader eyebrow={t("ext.family.eyebrow")} title={t("ext.family.enrollChild")} subtitle={t("ext.family.chooseCourse")} />
      {isLoading ? <Skeleton className="h-32" /> : (courses ?? []).length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🏫</span>} title={t("ext.family.noCourses")} />
      ) : (
        (courses ?? []).map((c) => (
          <Card key={c.id} interactive onClick={() => setCourse(c)}>
            <div className="flex items-center gap-4">
              <SchoolBadge course={c} />
              <div className="min-w-0 flex-1">
                <p className="font-display text-lg text-ink-900">{c.school_name}</p>
                <p className="text-sm text-ink-500">{[c.school_city, c.name].filter(Boolean).join(" · ")}</p>
                {c.groups.filter((g) => g.active).map((g) => <p key={g.id} className="text-xs capitalize text-ink-500">{g.name} · {groupLine(g)}</p>)}
              </div>
              <span className="shrink-0 text-right">
                <span className="block font-semibold text-ink-900">{fmt.euro(c.monthly_fee_cents)}</span>
                <span className="block text-xs text-ink-500">{t("ext.site.perMonth")}</span>
              </span>
            </div>
          </Card>
        ))
      )}
    </div>
  );
}
