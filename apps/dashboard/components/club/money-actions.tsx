"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { ProofPicker } from "@/components/ui/proof-picker";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { clubGet, clubSend, type Fee } from "@/lib/club";
import { toCents } from "@/lib/club-accounting";
import { feeLabel } from "@/lib/fee-label";
import { useI18n } from "@/lib/i18n/provider";

// «Pagamento parziale» e «Isenta este mês» del quadro del mese
// (apps/api/app/domains/club/fee_splits.py). Il browser manda quanto è stato
// pagato e perché; quanto resta, la ricevuta e il resto li fa il server. Il
// «resta da pagare» che si vede mentre si scrive è solo un'anteprima.

type Method = "CASH" | "MBWAY" | "BANK_TRANSFER" | "CARD";
const METHODS: { key: Method; icon: string }[] = [
  { key: "CASH", icon: "💶" }, { key: "MBWAY", icon: "📱" }, { key: "BANK_TRANSFER", icon: "🏦" }, { key: "CARD", icon: "💳" },
];

/** I motivi più comuni, a un tocco; si può sempre scrivere il proprio. */
function ReasonPicker({ value, onChange, chips, label, placeholder }: {
  value: string; onChange: (v: string) => void; chips: string[]; label: string; placeholder: string;
}) {
  return (
    <Field label={label}>
      <div className="mb-2 flex flex-wrap gap-2">
        {chips.map((c) => (
          <button key={c} type="button" onClick={() => onChange(c)}
            className={cn("cursor-pointer rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition",
              value === c ? "bg-ink-900 text-white ring-ink-900" : "bg-white text-ink-700 ring-ink-200 hover:ring-ink-300")}>
            {c}
          </button>
        ))}
      </div>
      <Textarea rows={2} maxLength={500} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

/** «Pagamento parziale»: quanto è stato pagato davvero, come, e perché non
 *  tutto. La parte pagata ha la sua ricevuta; il resto resta un debito. */
export function PartialPayModal({ fee, title, onClose }: { fee: Fee; title: string; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<Method>("CASH");
  const [receiver, setReceiver] = useState("");
  const [otherName, setOtherName] = useState("");
  const [reason, setReason] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: receivers } = useQuery({
    queryKey: ["club", "admin", "cash-receivers"],
    queryFn: () => clubGet<{ user_id: string; name: string }[]>("/admin/cash-receivers"),
  });
  const paid = toCents(amount);
  const validAmount = Number.isFinite(paid) && paid > 0 && paid < fee.amount_cents;
  const rest = validAmount ? fee.amount_cents - paid : null;
  const ready = validAmount && reason.trim().length >= 3
    && (method !== "CASH" || (receiver === "other" ? otherName.trim().length >= 2 : receiver !== ""));

  async function save() {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("amount_cents", String(paid));
      form.append("reason", reason.trim());
      form.append("method", method);
      if (method === "CASH") {
        if (receiver === "other") form.append("cash_received_by_name", otherName.trim());
        else form.append("cash_received_by_user_id", receiver);
      }
      if (file) form.append("file", file);
      const res = await clubSend<{ remainder: Fee }>(`/admin/fees/${fee.id}/partial-payment`, "POST", form);
      toast({
        tone: "success", title: t("money2.partial.done", { paid: fmt.euro(paid) }),
        text: t("money2.partial.stillDue", { amount: fmt.euro(res.remainder.amount_cents) }),
      });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: t("money2.partial.failed"), text: (e as Error).message });
    } finally {
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={`½ ${t("money2.partial.title")}`} subtitle={title}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        <Button loading={busy} disabled={!ready} onClick={save}>
          ✓ {validAmount ? t("money2.partial.confirm", { amount: fmt.euro(paid) }) : t("money2.partial.title")}
        </Button>
      </>}>
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3 rounded-2xl bg-ink-50 px-4 py-3 ring-1 ring-ink-100">
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold text-ink-900">{feeLabel(fee, t, fmt)}</span>
            <span className="block text-xs text-ink-500">{t("money2.partial.total")}</span>
          </span>
          <span className="font-display text-2xl text-ink-900">{fmt.euro(fee.amount_cents)}</span>
        </div>
        <Field label={t("money2.partial.amountLabel")} hint={t("money2.partial.amountHint")}
          error={amount && !validAmount ? t("money2.partial.amountError", { max: fmt.euro(fee.amount_cents) }) : undefined}>
          <Input inputMode="decimal" autoFocus placeholder="0,00" value={amount} onChange={(e) => setAmount(e.target.value)}
            className="text-lg font-semibold" />
        </Field>
        {/* Quanto resta: si vede subito, mentre si scrive. */}
        <motion.div layout className={cn("grid grid-cols-2 gap-2 text-center", !validAmount && "opacity-50")}>
          <div className="rounded-2xl bg-emerald-50 p-3 ring-1 ring-emerald-200">
            <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-700">{t("money2.partial.paidNow")}</p>
            <p className="font-display text-xl text-emerald-800">{validAmount ? fmt.euro(paid) : "—"}</p>
          </div>
          <div className="rounded-2xl bg-amber-50 p-3 ring-1 ring-amber-300">
            <p className="text-[10px] font-bold uppercase tracking-wider text-amber-800">{t("money2.partial.remaining")}</p>
            <p className="font-display text-xl text-amber-900">{rest !== null ? fmt.euro(rest) : "—"}</p>
          </div>
        </motion.div>
        <ReasonPicker value={reason} onChange={setReason} label={t("money2.partial.reasonLabel")}
          placeholder={t("money2.partial.reasonPlaceholder")}
          chips={[t("money2.partial.chipLater"), t("money2.partial.chipHardship"), t("money2.partial.chipAgreed")]} />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label={t("month.how")}>
          {METHODS.map((m) => (
            <button key={m.key} type="button" role="radio" aria-checked={method === m.key} onClick={() => setMethod(m.key)}
              className={cn("cursor-pointer rounded-2xl p-3 text-center ring-1", method === m.key ? "bg-brand-50 ring-2 ring-brand-400" : "bg-white ring-ink-200 hover:ring-ink-300")}>
              <span className="block text-2xl" aria-hidden="true">{m.icon}</span>
              <span className="block text-sm font-semibold text-ink-900">{t(`month.method.${m.key}`)}</span>
            </button>
          ))}
        </div>
        {method === "CASH" && (
          <Field label={t("month.cashTo")}>
            <Select value={receiver} onChange={(e) => setReceiver(e.target.value)}>
              <option value="">{t("month.choose")}</option>
              {(receivers ?? []).map((r) => <option key={r.user_id} value={r.user_id}>{r.name}</option>)}
              <option value="other">{t("month.someoneElse")}</option>
            </Select>
          </Field>
        )}
        {method === "CASH" && receiver === "other" && (
          <Field label={t("month.whoName")}><Input value={otherName} maxLength={120} onChange={(e) => setOtherName(e.target.value)} /></Field>
        )}
        <ProofPicker file={file} onFile={setFile} optional />
      </div>
    </Modal>
  );
}

/** «Isenta este mês»: quel mese l'atleta non paga (assente, infortunato).
 *  Esce dai conti del mese; si annulla con un tocco. */
export function ExemptMonthModal({ athleteId, name, period, periodName, amountCents, onClose }: {
  athleteId: string; name: string; period: string; periodName: string; amountCents: number | null; onClose: () => void;
}) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await clubSend("/admin/month/exempt", "POST", { athlete_id: athleteId, period, reason: reason.trim() });
      toast({ tone: "success", title: t("money2.exempt.done", { name, month: periodName }) });
      onClose();
    } catch (e) {
      toast({ tone: "error", title: t("money2.exempt.failed"), text: (e as Error).message });
    } finally {
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={`🎗️ ${t("money2.exempt.title")}`} subtitle={`${name} · ${periodName}`}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        <Button loading={busy} disabled={reason.trim().length < 3} onClick={save}>🎗️ {t("money2.exempt.confirm")}</Button>
      </>}>
      <div className="space-y-4">
        <p className="rounded-2xl bg-sky-50 px-4 py-3 text-sm text-sky-900 ring-1 ring-sky-200">
          {amountCents !== null ? t("money2.exempt.explainAmount", { amount: fmt.euro(amountCents) }) : t("money2.exempt.explain")}
        </p>
        <ReasonPicker value={reason} onChange={setReason} label={t("money2.exempt.reasonLabel")}
          placeholder={t("money2.exempt.reasonPlaceholder")}
          chips={[t("money2.exempt.chipAbsent"), t("money2.exempt.chipInjury"), t("money2.exempt.chipTravel")]} />
      </div>
    </Modal>
  );
}

/** Annulla un mese esente o un pagamento parziale, dopo una conferma. */
export function useMoneyUndo() {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  return async function undo(kind: "exempt" | "partial", feeId: string) {
    if (!window.confirm(kind === "exempt" ? t("money2.exempt.undoConfirm") : t("money2.partial.undoConfirm"))) return;
    try {
      await clubSend(kind === "exempt" ? `/admin/fees/${feeId}/unexempt` : `/admin/fees/${feeId}/undo-partial`, "POST");
      toast({ tone: "success", title: kind === "exempt" ? t("money2.exempt.undone") : t("money2.partial.undone") });
    } catch (e) {
      toast({ tone: "error", title: t("money2.undoFailed"), text: (e as Error).message });
    } finally {
      await queryClient.invalidateQueries({ queryKey: ["club"] });
    }
  };
}
