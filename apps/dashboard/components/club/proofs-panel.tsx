"use client";

import { AnimatePresence, motion } from "motion/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useDeferredValue, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { Pagination } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend, type AdminProof } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import { feeLabel } from "@/lib/fee-label";

// Le prove di pagamento del club, per la segreteria (e il superadmin entrato
// nel club). Le quote risultano pagate appena la famiglia carica la prova:
// qui si controlla, si cerca e, se serve, si rifiuta. La ricerca (atleta,
// email, nº della ricevuta, nota, chi ha preso i contanti), il metodo e il
// periodo li fa l'API (club/service.py::list_proofs); lo stato si sceglie
// dalle schede, con i conteggi dello stesso elenco.

type Status = "ACCEPTED" | "REJECTED" | "ALL";
type Method = "" | "BANK_TRANSFER" | "MBWAY" | "CASH";
type Period = "month" | "3m" | "season" | "all";

const PAGE = 12;
const A = (path: string) => `/admin${path}`;

const METHOD_STYLE: Record<string, { icon: string; stripe: string; chip: string }> = {
  BANK_TRANSFER: { icon: "🏦", stripe: "from-sky-500 to-sky-700", chip: "bg-sky-50 text-sky-800 ring-sky-200" },
  MBWAY: { icon: "📱", stripe: "from-rose-500 to-rose-700", chip: "bg-rose-50 text-rose-800 ring-rose-200" },
  CASH: { icon: "💶", stripe: "from-emerald-500 to-emerald-700", chip: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
};
const style = (m?: string) => METHOD_STYLE[m ?? "BANK_TRANSFER"] ?? METHOD_STYLE.BANK_TRANSFER!;

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Il periodo come date: la stagione parte a settembre. */
function range(period: Period): { from?: string; to?: string } {
  const now = new Date();
  if (period === "month") return { from: iso(new Date(now.getFullYear(), now.getMonth(), 1)) };
  if (period === "3m") return { from: iso(new Date(now.getFullYear(), now.getMonth() - 2, 1)) };
  if (period === "season") return { from: iso(new Date(now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1, 8, 1)) };
  return {};
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

export function ProofsPanel() {
  const { t, fmt } = useI18n();
  const [q, setQ] = useState("");
  const query = useDeferredValue(q.trim());
  const [method, setMethod] = useState<Method>("");
  const [period, setPeriod] = useState<Period>("season");
  const [status, setStatus] = useState<Status>("ACCEPTED");
  const [page, setPage] = useState(1);
  const [viewing, setViewing] = useState<AdminProof | null>(null);
  const [rejecting, setRejecting] = useState<AdminProof | null>(null);

  const params = new URLSearchParams({ ...(query ? { q: query } : {}), ...(method ? { method } : {}), ...range(period) }).toString();
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["club", "admin", "proofs", params],
    queryFn: () => clubGet<AdminProof[]>(A(`/payment-proofs${params ? `?${params}` : ""}`)),
    placeholderData: (prev) => prev,
  });

  const all = useMemo(() => data ?? [], [data]);
  const stats = useMemo(() => {
    const accepted = all.filter((p) => p.status === "ACCEPTED");
    return {
      ACCEPTED: accepted.length,
      REJECTED: all.length - accepted.length,
      ALL: all.length,
      total: accepted.reduce((s, p) => s + p.amount_cents, 0),
      cash: accepted.filter((p) => p.method === "CASH").reduce((s, p) => s + p.amount_cents, 0),
      transfer: accepted.filter((p) => p.method !== "CASH").reduce((s, p) => s + p.amount_cents, 0),
    };
  }, [all]);
  const rows = status === "ALL" ? all : all.filter((p) => p.status === status);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const current = Math.min(page, pages);
  const shown = rows.slice((current - 1) * PAGE, current * PAGE);
  const reset = () => setPage(1);
  const filtersOn = Boolean(q || method || period !== "season");

  const METHODS: { key: Method; label: string }[] = [
    { key: "", label: t("proofs.methodAll") },
    { key: "BANK_TRANSFER", label: `🏦 ${t("method.BANK_TRANSFER")}` },
    { key: "MBWAY", label: `📱 ${t("method.MBWAY")}` },
    { key: "CASH", label: `💶 ${t("method.CASH")}` },
  ];
  const PERIODS: { key: Period; label: string }[] = [
    { key: "month", label: t("proofs.periodMonth") },
    { key: "3m", label: t("proofs.period3m") },
    { key: "season", label: t("proofs.periodSeason") },
    { key: "all", label: t("proofs.periodAll") },
  ];
  const STATUSES: { key: Status; label: string; icon: string }[] = [
    { key: "ACCEPTED", label: t("proofs.statusAccepted"), icon: "✓" },
    { key: "REJECTED", label: t("proofs.statusRejected"), icon: "✕" },
    { key: "ALL", label: t("proofs.statusAll"), icon: "≡" },
  ];

  return (
    <div className="space-y-5">
      <p className="rounded-2xl bg-brand-50/70 p-4 text-sm text-ink-700 ring-1 ring-brand-100">💡 {t("proofs.intro")}</p>

      {/* Il riepilogo del periodo scelto */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { label: t("proofs.statTotal"), value: fmt.euro(stats.total), tone: "from-ink-900 to-ink-700 text-white" },
          { label: t("proofs.statCount"), value: String(stats.ACCEPTED), tone: "from-brand-500 to-brand-700 text-white" },
          { label: `🏦 ${t("proofs.statTransfer")}`, value: fmt.euro(stats.transfer), tone: "from-sky-50 to-white text-ink-900 ring-1 ring-sky-100" },
          { label: `💶 ${t("proofs.statCash")}`, value: fmt.euro(stats.cash), tone: "from-emerald-50 to-white text-ink-900 ring-1 ring-emerald-100" },
        ].map((s) => (
          <div key={s.label} className={cn("rounded-3xl bg-gradient-to-br p-4 shadow-soft", s.tone)}>
            <p className="text-[11px] font-bold uppercase tracking-widest opacity-75">{s.label}</p>
            <p className="mt-1 font-display text-2xl tabular-nums sm:text-3xl">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Cerca e filtra */}
      <div className="space-y-3 rounded-3xl bg-white p-3 shadow-soft ring-1 ring-ink-900/5">
        <label className="relative block">
          <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true">🔎</span>
          <input type="search" value={q} onChange={(e) => { setQ(e.target.value); reset(); }}
            placeholder={t("proofs.search")} aria-label={t("proofs.search")}
            className="h-12 w-full rounded-2xl bg-ink-50 pl-11 pr-10 text-sm text-ink-900 ring-1 ring-ink-900/5 placeholder:text-ink-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-300" />
          {isFetching && <span className="absolute right-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin rounded-full border-2 border-brand-300 border-t-transparent" aria-hidden="true" />}
        </label>
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex gap-1.5 overflow-x-auto [scrollbar-width:none]" role="group" aria-label={t("proofs.method")}>
            {METHODS.map((m) => (
              <button key={m.key || "all"} type="button" aria-pressed={method === m.key} onClick={() => { setMethod(m.key); reset(); }}
                className={cn("shrink-0 cursor-pointer rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition",
                  method === m.key ? "bg-ink-900 text-white ring-ink-900" : "bg-white text-ink-700 ring-ink-200 hover:ring-ink-300")}>
                {m.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5 overflow-x-auto [scrollbar-width:none]" role="group" aria-label={t("proofs.period")}>
            <span className="shrink-0 text-xs font-semibold text-ink-400">📅</span>
            {PERIODS.map((p) => (
              <button key={p.key} type="button" aria-pressed={period === p.key} onClick={() => { setPeriod(p.key); reset(); }}
                className={cn("shrink-0 cursor-pointer rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition",
                  period === p.key ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-ink-700 ring-ink-200 hover:ring-ink-300")}>
                {p.label}
              </button>
            ))}
            {filtersOn && (
              <button type="button" onClick={() => { setQ(""); setMethod(""); setPeriod("season"); reset(); }}
                className="shrink-0 cursor-pointer px-2 text-xs font-semibold text-brand-700 hover:underline">{t("proofs.clear")}</button>
            )}
          </div>
        </div>
      </div>

      {/* Stato, con i conteggi */}
      <div className="flex gap-2" role="tablist" aria-label={t("proofs.status")}>
        {STATUSES.map((s) => (
          <button key={s.key} type="button" role="tab" aria-selected={status === s.key} onClick={() => { setStatus(s.key); reset(); }}
            className={cn("relative inline-flex cursor-pointer items-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-semibold transition",
              status === s.key ? "text-white" : "bg-white text-ink-600 ring-1 ring-ink-200 hover:text-ink-900")}>
            {status === s.key && <motion.span layoutId="proof-status" className={cn("absolute inset-0 rounded-2xl shadow-soft",
              s.key === "REJECTED" ? "bg-rose-600" : s.key === "ACCEPTED" ? "bg-emerald-600" : "bg-ink-900")} transition={{ type: "spring", stiffness: 480, damping: 36 }} />}
            <span className="relative" aria-hidden="true">{s.icon}</span>
            <span className="relative">{s.label}</span>
            <span className={cn("relative rounded-full px-2 text-xs tabular-nums", status === s.key ? "bg-white/20" : "bg-ink-100 text-ink-500")}>{stats[s.key]}</span>
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-56" /><Skeleton className="h-56" /></div>
      ) : rows.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🧾</span>} title={t("proofs.empty")} text={filtersOn ? t("proofs.emptyFiltered") : t("proofs.emptyText")} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <AnimatePresence initial={false}>
            {shown.map((p, i) => <ProofCard key={p.id} proof={p} index={i} onView={() => setViewing(p)} onReject={() => setRejecting(p)} />)}
          </AnimatePresence>
        </div>
      )}
      <Pagination page={current} pages={pages} onChange={(n) => { setPage(n); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
      <ReceiptViewer proof={viewing} onClose={() => setViewing(null)} />
      <RejectModal proof={rejecting} onClose={() => setRejecting(null)} />
    </div>
  );
}

function ProofCard({ proof: p, index, onView, onReject }: { proof: AdminProof; index: number; onView: () => void; onReject: () => void }) {
  const { t, fmt } = useI18n();
  const m = style(p.method);
  const rejected = p.status === "REJECTED";
  // Le quote raggruppate per atleta: una famiglia paga spesso più figli insieme.
  const fees = p.fees;
  const byAthlete = useMemo(() => {
    const groups = new Map<string, AdminProof["fees"]>();
    for (const f of fees) {
      const key = f.athlete_name ?? t("proofs.familyFee");
      groups.set(key, [...(groups.get(key) ?? []), f]);
    }
    return [...groups.entries()];
  }, [fees, t]);
  const paidOn = p.paid_on ?? p.created_at;

  return (
    <motion.article layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
      transition={{ delay: Math.min(index, 8) * 0.03 }}
      className={cn("relative overflow-hidden rounded-3xl bg-white shadow-soft ring-1 transition hover:shadow-lift",
        rejected ? "ring-rose-200" : "ring-ink-900/5")}>
      <span aria-hidden="true" className={cn("absolute inset-y-0 left-0 w-1.5 bg-gradient-to-b", rejected ? "from-rose-400 to-rose-600" : m.stripe)} />
      <div className="space-y-4 p-5 pl-6">
        {/* Importo, numero, stato */}
        <header className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cn("font-display text-3xl leading-none tabular-nums", rejected ? "text-ink-400 line-through" : "text-ink-900")}>{fmt.euro(p.amount_cents)}</p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
              <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-semibold ring-1", m.chip)}>{m.icon} {t.dyn(`method.${p.method ?? "BANK_TRANSFER"}`, p.method ?? "")}</span>
              {p.receipt_number && <span className="rounded-full bg-ink-100 px-2 py-0.5 font-mono font-semibold text-ink-700">🧾 {p.receipt_number}</span>}
              {p.credit_cents > 0 && <span className="rounded-full bg-accent-100 px-2 py-0.5 font-semibold text-accent-900">🎁 {t("proofs.credit", { amount: fmt.euro(p.credit_cents) })}</span>}
            </div>
          </div>
          <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full px-3 py-1 text-xs font-bold",
            rejected ? "bg-rose-100 text-rose-800" : "bg-emerald-100 text-emerald-800")}>
            {rejected ? `✕ ${t("proofs.rejected")}` : `✓ ${t("proofs.accepted")}`}
          </span>
        </header>

        {/* Quando e chi */}
        <dl className="grid grid-cols-2 gap-2 rounded-2xl bg-ink-50/70 p-3 text-xs">
          <div>
            <dt className="font-semibold uppercase tracking-wider text-ink-400">{t("proofs.paidOn")}</dt>
            <dd className="mt-0.5 font-semibold text-ink-800">{fmt.shortDate(paidOn)}</dd>
          </div>
          <div className="min-w-0">
            <dt className="font-semibold uppercase tracking-wider text-ink-400">{t("proofs.by")}</dt>
            <dd className="mt-0.5 truncate font-semibold text-ink-800" title={p.uploaded_by_email ?? ""}>{p.uploaded_by_email ?? "—"}</dd>
          </div>
          {p.method === "CASH" && (
            <div className="col-span-2">
              <dt className="font-semibold uppercase tracking-wider text-ink-400">{t("proofs.cashTo")}</dt>
              <dd className="mt-0.5 font-semibold text-ink-800">💶 {p.cash_received_by_name ?? "—"}</dd>
            </div>
          )}
        </dl>

        {/* Che cosa copre */}
        <ul className="space-y-2">
          {byAthlete.map(([name, fees]) => (
            <li key={name} className="flex gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-[11px] font-bold text-white">{initials(name)}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink-900">{name}</p>
                <ul className="mt-0.5 space-y-0.5">
                  {fees.map((f) => (
                    <li key={f.id} className="flex justify-between gap-2 text-xs text-ink-600">
                      <span className="truncate" title={f.description}>{feeLabel(f, t, fmt)}</span>
                      <span className="shrink-0 font-semibold tabular-nums text-ink-800">{fmt.euro(f.amount_cents)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </li>
          ))}
        </ul>

        {p.note && <p className="rounded-xl bg-white p-3 text-xs italic text-ink-600 ring-1 ring-ink-100">💬 “{p.note}”</p>}
        {p.rejection_reason && (
          <p className="rounded-xl bg-rose-50 p-3 text-xs text-rose-800 ring-1 ring-rose-200"><strong>{t("proofs.reason")}:</strong> {p.rejection_reason}</p>
        )}

        <footer className="flex flex-wrap gap-2 border-t border-ink-100 pt-3">
          {p.original_filename ? (
            <Button size="sm" variant="secondary" onClick={onView}>👁 {t("proofs.view")}</Button>
          ) : (
            <span className="text-xs text-ink-400">{p.method === "CASH" ? t("proofs.noFileCash") : t("proofs.noFileCredit")}</span>
          )}
          {!rejected && <Button size="sm" variant="ghost" className="ml-auto text-rose-600" onClick={onReject}>✕ {t("proofs.reject")}</Button>}
        </footer>
      </div>
    </motion.article>
  );
}

/** La ricevuta dentro la pagina: l'immagine o il PDF, senza aprire schede.
 *  Basta l'id della prova: la si apre anche da una quota (lista delle quote,
 *  quadro del mese) per controllarla prima di segnarla pagata. */
export function ReceiptViewer({ proof, onClose }: {
  proof: { id: string; receipt_number?: string | null; original_filename?: string | null; status?: string | null } | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const { data, isLoading, error } = useQuery({
    queryKey: ["club", "admin", "proof-url", proof?.id],
    queryFn: () => clubGet<{ url: string }>(A(`/payment-proofs/${proof!.id}/url`)),
    enabled: !!proof,
    staleTime: 60_000,
  });
  const pdf = /\.pdf$/i.test(proof?.original_filename ?? "") || /\.pdf(\?|$)/i.test(data?.url ?? "");
  return (
    <Modal open={!!proof} onClose={onClose} size="xl" title={`🧾 ${proof?.receipt_number ?? t("proofs.receipt")}`}
      subtitle={proof?.status === "REJECTED" ? `✕ ${t("proofs.rejected")}` : (proof?.original_filename ?? undefined)}
      footer={data ? <a href={data.url} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-brand-700 hover:underline">{t("proofs.openNew")} ↗</a> : undefined}>
      {isLoading ? <Skeleton className="h-[60vh]" /> : error ? (
        <p className="rounded-2xl bg-rose-50 p-4 text-sm text-rose-700">{t("proofs.viewFailed")}</p>
      ) : data ? (
        pdf ? <iframe src={data.url} title={t("proofs.receipt")} className="h-[65vh] w-full rounded-2xl ring-1 ring-ink-200" />
        // eslint-disable-next-line @next/next/no-img-element -- ricevuta privata, URL firmato a tempo
          : <img src={data.url} alt={t("proofs.receipt")} className="mx-auto max-h-[65vh] rounded-2xl object-contain ring-1 ring-ink-200" />
      ) : null}
    </Modal>
  );
}

/** Rifiutare con un motivo che la famiglia legge: qualche motivo pronto. */
function RejectModal({ proof, onClose }: { proof: AdminProof | null; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const presets = [t("proofs.presetUnreadable"), t("proofs.presetAmount"), t("proofs.presetNotReceived"), t("proofs.presetWrongFile")];
  async function submit() {
    if (!proof || reason.trim().length < 3) return;
    setBusy(true);
    try {
      await clubSend(A(`/payment-proofs/${proof.id}/reject`), "POST", { reason: reason.trim() });
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: t("proofs.rejectedToast") });
      setReason("");
      onClose();
    } catch (e) {
      toast({ tone: "error", title: t("proofs.rejectFailed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open={!!proof} onClose={onClose} title={t("proofs.rejectTitle")}
      subtitle={proof ? `${fmt.euro(proof.amount_cents)} · ${proof.receipt_number ?? ""}` : undefined}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant="danger" loading={busy} disabled={reason.trim().length < 3} onClick={submit}>{t("proofs.rejectConfirm")}</Button>
      </>}>
      <p className="text-sm text-ink-600">{t("proofs.rejectText")}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {presets.map((r) => (
          <button key={r} type="button" onClick={() => setReason(r)} className="cursor-pointer rounded-full bg-ink-50 px-3 py-1 text-xs font-semibold text-ink-700 ring-1 ring-ink-200 hover:bg-white">{r}</button>
        ))}
      </div>
      <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={4} maxLength={500} aria-label={t("proofs.reason")}
        placeholder={t("proofs.reasonPlaceholder")}
        className="mt-3 w-full rounded-2xl bg-ink-50 p-3 text-sm text-ink-900 ring-1 ring-ink-200 focus:bg-white focus:outline-none focus:ring-2 focus:ring-rose-300" />
    </Modal>
  );
}
