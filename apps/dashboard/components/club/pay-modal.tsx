"use client";

import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge, FeeStatusPill } from "@/components/ui/badge";
import { CountUp } from "@/components/ui/count-up";
import { CameraUploadButton } from "@/components/ui/gamification";
import { Modal } from "@/components/ui/modal";
import { Input, Select, Textarea } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { friendlyApiError } from "@/lib/api-error";
import { celebrate } from "@/lib/motion";
import { clubGet, clubSend, FEE_KIND_LABELS, type CashReceiver, type Fee } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";
import { useClubPaymentInfo, usePaymentInfo, type PaymentInfo } from "@/components/club/payment-info";
import { JavCashConfirmCode } from "@/components/javcash-confirm-code";

/** Un ordine dello Shop come lo restituisce GET /jav-market/orders/mine:
 *  solo i campi che servono a pagarlo. */
interface ShopOrder {
  id: string;
  order_code: string;
  product_name: string;
  athlete_name: string | null;
  amount_due_cents: number;
  status: string;
  payment_method: string;
  payment_proof_uploaded_at: string | null;
  created_at: string;
}

type Kind = "fees" | "order";

/** "Carica un pagamento". Prima si sceglie che cosa si è pagato, perché le
 *  due cose vanno in posti diversi:
 *  - le **quote del club** (mensilità, iscrizione, gare) si pagano al club e
 *    risultano pagate appena si carica la foto (docs/club-portal.md, regola
 *    di autogestione);
 *  - un **ordine dello Shop** (judogi, materiale) si paga alla piattaforma, e
 *    la foto accompagna il bonifico: l'ordine parte quando il pagamento è
 *    confermato. */
export function PayModal({ open, onClose, fees, preselect }: { open: boolean; onClose: () => void; fees: Fee[]; preselect?: string[] }) {
  const [kind, setKind] = useState<Kind | null>(preselect ? "fees" : null);
  const { t, fmt } = useI18n();
  const { data: orders } = useQuery({
    queryKey: ["jav-market", "orders", "mine"],
    queryFn: async (): Promise<ShopOrder[]> => {
      const res = await fetch("/api/proxy/jav-market/orders/mine");
      return res.ok ? res.json() : [];
    },
  });
  const payable = useMemo(
    () => (orders ?? []).filter((o) => o.status === "AWAITING_PAYMENT" && o.payment_method === "BANK_TRANSFER"),
    [orders],
  );
  const back = preselect ? undefined : () => setKind(null);

  if (kind === "fees") return <FeesStep open={open} onClose={onClose} onBack={back} fees={fees} preselect={preselect} />;
  if (kind === "order") return <OrderStep open={open} onClose={onClose} onBack={back} orders={payable} />;

  const feesTotal = fees.reduce((s, f) => s + f.amount_cents, 0);
  return (
    <Modal open={open} onClose={onClose} title={t("family.actionPay")} subtitle={t("pay.chooseSubtitle")} size="lg"
      footer={<Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <KindCard
          icon="🥋" title={t("pay.kindFees")} text={t("pay.kindFeesText")}
          status={fees.length ? t("pay.kindFeesDue", { n: fees.length, amount: fmt.euro(feesTotal) }) : t("pay.kindNothing")}
          disabled={fees.length === 0} onClick={() => setKind("fees")}
        />
        <KindCard
          icon="🛍️" title={t("pay.kindOrder")} text={t("pay.kindOrderText")}
          status={payable.length ? (payable.length === 1 ? t("pay.kindOrderDueOne") : t("pay.kindOrderDueMany", { n: payable.length })) : t("pay.kindOrderNothing")}
          disabled={payable.length === 0} onClick={() => setKind("order")}
        />
      </div>
    </Modal>
  );
}

function KindCard({ icon, title, text, status, disabled, onClick }: { icon: string; title: string; text: string; status: string; disabled: boolean; onClick: () => void }) {
  return (
    <motion.button
      type="button"
      whileTap={disabled ? undefined : { scale: 0.98 }}
      onClick={onClick}
      disabled={disabled}
      className="flex flex-col items-start gap-2 rounded-3xl p-5 text-left ring-1 ring-ink-200 bg-white transition-colors enabled:hover:ring-brand-300 enabled:hover:bg-brand-50 enabled:cursor-pointer disabled:opacity-50"
    >
      <span className="h-12 w-12 rounded-2xl bg-brand-50 flex items-center justify-center text-2xl">{icon}</span>
      <span className="block font-display text-lg text-ink-900">{title}</span>
      <span className="block text-sm text-ink-500">{text}</span>
      <span className="mt-1 block text-xs font-semibold text-brand-700">{status}</span>
    </motion.button>
  );
}

function BankBox({ bank, label }: { bank: PaymentInfo | undefined; label: string }) {
  const { t } = useI18n();
  if (!bank?.iban) return null;
  return (
    <div className="rounded-2xl bg-ink-900 text-white p-4">
      <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-accent-300">{label}</p>
      <p className="font-mono text-sm mt-1.5 break-all">{bank.iban}</p>
      {bank.holder && <p className="text-xs text-ink-300 mt-0.5">{t("pay.holder", { holder: bank.holder })}</p>}
      {bank.instructions && <p className="text-xs text-ink-300 mt-1">{bank.instructions}</p>}
    </div>
  );
}

function ReceiptPicker({ file, onFile }: { file: File | null; onFile: (f: File | null) => void }) {
  const { t } = useI18n();
  return file ? (
    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="flex items-center gap-3 rounded-2xl bg-emerald-50 ring-1 ring-emerald-200 p-4">
      <span className="h-11 w-11 rounded-xl bg-emerald-500 text-white flex items-center justify-center text-xl">✓</span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-ink-900 truncate">{file.name}</span>
        <span className="block text-xs text-ink-500">{t("pay.ready")}</span>
      </span>
      <Button variant="ghost" size="sm" onClick={() => onFile(null)}>{t("common.change")}</Button>
    </motion.div>
  ) : (
    <CameraUploadButton onFile={onFile} />
  );
}

function HowTile({ icon, title, text, on, disabled = false, onClick }: { icon: string; title: string; text: string; on: boolean; disabled?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      aria-disabled={disabled}
      disabled={disabled}
      onClick={onClick}
      className={`flex flex-col items-center gap-1 rounded-2xl p-3 text-center ring-1 transition-colors ${
        on ? "bg-brand-50 ring-brand-400 ring-2" : "bg-white ring-ink-200 enabled:hover:ring-ink-300"
      } enabled:cursor-pointer disabled:opacity-50`}
    >
      <span className="text-2xl" aria-hidden="true">{icon}</span>
      <span className="text-sm font-semibold text-ink-900">{title}</span>
      <span className="text-[11px] leading-tight text-ink-500">{text}</span>
    </button>
  );
}

function StepFooter({ onBack, onClose, children }: { onBack?: () => void; onClose: () => void; children: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <>
      {onBack ? <Button variant="ghost" onClick={onBack}>{t("pay.back")}</Button> : <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>}
      {children}
    </>
  );
}

// --- Quote del club ---------------------------------------------------------------------------

/** Spunta che cosa ha pagato il bonifico, fotografa la ricevuta, fatto: le
 *  quote risultano pagate nel momento in cui la foto arriva. Il credito del
 *  wallet (gli sconti degli inviti) si può usare per una parte o per tutto:
 *  si conferma con il PIN o il codice via email, come ogni spesa di JavCash,
 *  e se copre tutto la ricevuta non serve.
 *
 *  Oppure contanti: niente foto, si dice a chi del club sono stati dati (lo
 *  si avvisa). La carta online c'è ma è spenta finché il club non ha un
 *  pagamento online. */
function FeesStep({ open, onClose, onBack, fees, preselect }: { open: boolean; onClose: () => void; onBack?: () => void; fees: Fee[]; preselect?: string[] }) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set(preselect ?? fees.map((f) => f.id)));
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useCredit, setUseCredit] = useState(false);
  const [code, setCode] = useState("");
  const [codeRequested, setCodeRequested] = useState(false);
  const [how, setHow] = useState<"BANK_TRANSFER" | "CASH">("BANK_TRANSFER");
  const [receiver, setReceiver] = useState("");
  const [otherName, setOtherName] = useState("");
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data: bank } = useClubPaymentInfo();
  const { data: receivers } = useQuery({
    queryKey: ["club", "cash-receivers"],
    queryFn: () => clubGet<CashReceiver[]>("/cash-receivers"),
    enabled: how === "CASH",
  });
  const { data: wallet } = useQuery({
    queryKey: ["wallet", "me"],
    queryFn: async (): Promise<{ balance_cents: number }> => {
      const res = await fetch("/api/proxy/wallets/me");
      return res.ok ? res.json() : { balance_cents: 0 };
    },
  });
  const { t, fmt } = useI18n();
  const { euro, shortDate } = fmt;

  const total = useMemo(() => fees.filter((f) => selected.has(f.id)).reduce((s, f) => s + f.amount_cents, 0), [fees, selected]);
  const balance = wallet?.balance_cents ?? 0;
  const cash = how === "CASH";
  const credit = useCredit && !cash ? Math.min(balance, total) : 0;
  const needsFile = !cash && credit < total;
  const receiverChosen = receiver === "other" ? otherName.trim().length >= 2 : receiver !== "";
  const ready = selected.size > 0 && (cash
    ? receiverChosen
    : (!needsFile || !!file) && (credit === 0 || code.trim().length >= 4));
  const byAthlete = useMemo(() => {
    const map = new Map<string, Fee[]>();
    for (const f of fees) map.set(f.athlete_name ?? "", [...(map.get(f.athlete_name ?? "") ?? []), f]);
    return [...map.entries()];
  }, [fees]);

  function toggle(id: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function submit() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      if (file && needsFile) form.append("file", file);
      for (const id of selected) form.append("fee_ids", id);
      if (note.trim()) form.append("note", note.trim());
      form.append("method", how);
      if (cash) {
        if (receiver === "other") form.append("cash_received_by_name", otherName.trim());
        else form.append("cash_received_by_user_id", receiver);
      }
      if (credit > 0) {
        form.append("credit_cents", String(credit));
        form.append("spend_code", code.trim());
      }
      await clubSend("/payment-proofs", "POST", form);
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      await queryClient.invalidateQueries({ queryKey: ["wallet"] });
      void celebrate();
      toast({ tone: "success", title: t("pay.recorded"), text: selected.size === 1 ? t("pay.recordedOne") : t("pay.recordedMany", { n: selected.size }) });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("pay.kindFees")}
      subtitle={t("pay.subtitle")}
      size="lg"
      footer={
        <StepFooter onBack={onBack} onClose={onClose}>
          <Button onClick={submit} loading={busy} disabled={!ready}>
            {cash ? t("pay.cashSend") : t("pay.send")} · {euro(total)}
          </Button>
        </StepFooter>
      }
    >
      <div className="space-y-5">
        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-ink-500 mb-2">{t("pay.howTitle")}</p>
          <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t("pay.howTitle")}>
            <HowTile icon="🏦" title={t("pay.howTransfer")} text={t("pay.howTransferText")} on={how === "BANK_TRANSFER"} onClick={() => setHow("BANK_TRANSFER")} />
            <HowTile icon="💶" title={t("pay.howCash")} text={t("pay.howCashText")} on={how === "CASH"} onClick={() => setHow("CASH")} />
            {/* Spento finché il club non ha un pagamento online (Stripe). */}
            <HowTile icon="💳" title={t("pay.howCard")} text={t("pay.howCardText")} on={false} disabled onClick={() => undefined} />
          </div>
        </div>

        {!cash && <BankBox bank={bank} label={t("pay.bankDetails")} />}

        <div className="space-y-4">
          {fees.length === 0 && <p className="text-sm text-ink-500">{t("pay.nothingDue")}</p>}
          {byAthlete.map(([athlete, list]) => (
            <div key={athlete}>
              {athlete && <p className="text-xs font-bold uppercase tracking-wide text-ink-500 mb-2">{athlete}</p>}
              <div className="space-y-2">
                {list.map((fee) => {
                  const on = selected.has(fee.id);
                  return (
                    <motion.button
                      key={fee.id}
                      type="button"
                      whileTap={{ scale: 0.98 }}
                      onClick={() => toggle(fee.id)}
                      className={`w-full flex items-center gap-3 rounded-2xl p-3.5 text-left ring-1 cursor-pointer transition-colors ${
                        on ? "bg-brand-50 ring-brand-300" : "bg-white ring-ink-200 hover:ring-ink-300"
                      }`}
                    >
                      <span className={`h-6 w-6 shrink-0 rounded-lg flex items-center justify-center ring-2 ${on ? "bg-brand-500 ring-brand-500 text-white" : "ring-ink-300"}`}>
                        <AnimatePresence>{on && <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}>✓</motion.span>}</AnimatePresence>
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold text-ink-900">{fee.description}</span>
                        <span className="block text-xs text-ink-500">
                          {t.dyn(`club.feeKind.${fee.kind}`, FEE_KIND_LABELS[fee.kind] ?? fee.kind)} · {t("club.dueOn", { date: shortDate(fee.due_date) })}
                        </span>
                        {fee.discount_cents > 0 && fee.gross_amount_cents !== null && (
                          <span className="block text-xs text-emerald-700">
                            {t("pay.discounted", { list: euro(fee.gross_amount_cents), note: fee.discount_note ?? "" })}
                          </span>
                        )}
                      </span>
                      <span className="text-right shrink-0">
                        <span className="block font-display text-ink-900 tabular-nums">{euro(fee.amount_cents)}</span>
                        <FeeStatusPill status={fee.status} overdue={fee.overdue} />
                      </span>
                    </motion.button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between rounded-2xl bg-accent-50 ring-1 ring-accent-200 px-4 py-3">
          <span className="text-sm font-semibold text-ink-700">{t("pay.selectedTotal")}</span>
          <span className="font-display text-2xl text-ink-900">
            <CountUp value={total / 100} duration={0.5} format={(n) => fmt.euroUnits(n)} />
          </span>
        </div>

        {cash && (
          <div className="rounded-2xl ring-1 ring-ink-200 bg-white p-4 space-y-3">
            <label htmlFor="pay-cash-to" className="block text-sm font-semibold text-ink-900">{t("pay.cashTo")}</label>
            <Select id="pay-cash-to" value={receiver} onChange={(e) => setReceiver(e.target.value)}>
              <option value="">{t("pay.cashPick")}</option>
              {(receivers ?? []).map((r) => <option key={r.user_id} value={r.user_id}>{r.name}</option>)}
              <option value="other">{t("pay.cashOther")}</option>
            </Select>
            {receiver === "other" && (
              <Input placeholder={t("pay.cashOtherName")} aria-label={t("pay.cashOtherName")} value={otherName} onChange={(e) => setOtherName(e.target.value)} maxLength={120} />
            )}
            <p className="text-xs text-ink-500">{t("pay.cashHint")}</p>
          </div>
        )}

        {!cash && balance > 0 && total > 0 && (
          <div className="rounded-2xl ring-1 ring-emerald-200 bg-emerald-50 p-4 space-y-3">
            <label className="flex items-start gap-3 cursor-pointer">
              <input type="checkbox" checked={useCredit} onChange={(e) => setUseCredit(e.target.checked)} className="mt-1 h-4 w-4 accent-brand-500" />
              <span>
                <span className="block text-sm font-semibold text-ink-900">{t("pay.useCredit", { amount: euro(Math.min(balance, total)) })}</span>
                <span className="block text-xs text-ink-500">{t("pay.creditBalance", { amount: euro(balance) })}</span>
              </span>
            </label>
            {credit > 0 && (
              <>
                <p className="text-sm text-ink-700">
                  {needsFile ? t("pay.creditPartial", { transfer: euro(total - credit) }) : t("pay.creditFull")}
                </p>
                <JavCashConfirmCode
                  requestUrl="/api/proxy/club/payment-proofs/request-credit-code"
                  requestBody={{ credit_cents: credit }}
                  code={code}
                  onCodeChange={setCode}
                  requested={codeRequested}
                  onRequestedChange={setCodeRequested}
                />
              </>
            )}
          </div>
        )}

        {needsFile && <ReceiptPicker file={file} onFile={setFile} />}

        <Textarea placeholder={t("pay.notePlaceholder")} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />

        {error && <Badge tone="danger">{error}</Badge>}
      </div>
    </Modal>
  );
}

// --- Ordine dello Shop ------------------------------------------------------------------------

/** Un ordine alla volta: un bonifico paga un ordine, e la prova va a chi lo
 *  conferma. Ricaricarla sostituisce quella di prima. */
function OrderStep({ open, onClose, onBack, orders }: { open: boolean; onClose: () => void; onBack?: () => void; orders: ShopOrder[] }) {
  const [orderId, setOrderId] = useState<string | null>(orders.length === 1 ? orders[0]!.id : null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data: bank } = usePaymentInfo();
  const { t, fmt } = useI18n();
  const chosen = orders.find((o) => o.id === orderId);

  async function submit() {
    if (!file || !chosen) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`/api/proxy/jav-market/orders/mine/${chosen.id}/payment-proof`, { method: "POST", body: form });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["jav-market"] });
      await queryClient.invalidateQueries({ queryKey: ["orders"] });
      toast({ tone: "success", title: t("pay.orderSent"), text: t("pay.orderSentText") });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("pay.kindOrder")}
      subtitle={t("pay.orderSubtitle")}
      size="lg"
      footer={
        <StepFooter onBack={onBack} onClose={onClose}>
          <Button onClick={submit} loading={busy} disabled={!file || !chosen}>
            {t("pay.send")}{chosen ? ` · ${fmt.euro(chosen.amount_due_cents)}` : ""}
          </Button>
        </StepFooter>
      }
    >
      <div className="space-y-5">
        <BankBox bank={bank} label={t("pay.shopBankDetails")} />

        <div className="space-y-2">
          {orders.map((order) => {
            const on = order.id === orderId;
            return (
              <motion.button
                key={order.id}
                type="button"
                whileTap={{ scale: 0.98 }}
                onClick={() => setOrderId(order.id)}
                className={`w-full flex items-center gap-3 rounded-2xl p-3.5 text-left ring-1 cursor-pointer transition-colors ${
                  on ? "bg-brand-50 ring-brand-300" : "bg-white ring-ink-200 hover:ring-ink-300"
                }`}
              >
                <span className={`h-6 w-6 shrink-0 rounded-full flex items-center justify-center ring-2 ${on ? "bg-brand-500 ring-brand-500 text-white" : "ring-ink-300"}`}>
                  {on && <span className="h-2 w-2 rounded-full bg-white" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-ink-900">{order.product_name}</span>
                  <span className="block text-xs text-ink-500">
                    {t("pay.orderLine", { code: order.order_code, date: fmt.shortDate(order.created_at) })}
                    {order.athlete_name ? ` · ${t("pay.orderFor", { name: order.athlete_name })}` : ""}
                  </span>
                  {order.payment_proof_uploaded_at && (
                    <span className="block text-xs text-amber-700 mt-0.5">{t("pay.orderProofAlready")}</span>
                  )}
                </span>
                <span className="font-display text-ink-900 tabular-nums shrink-0">{fmt.euro(order.amount_due_cents)}</span>
              </motion.button>
            );
          })}
        </div>

        <ReceiptPicker file={file} onFile={setFile} />

        {error && <Badge tone="danger">{error}</Badge>}
      </div>
    </Modal>
  );
}
