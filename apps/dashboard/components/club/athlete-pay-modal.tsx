"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { ProofPicker } from "@/components/ui/proof-picker";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend, type CashReceiver, type Fee } from "@/lib/club";
import { cn } from "@/lib/cn";
import { celebrate } from "@/lib/motion";
import { useI18n } from "@/lib/i18n/provider";

// Pagare dall'area dell'atleta (POST /club/athlete-area/{id}/payment-proofs):
// il titolare, o l'atleta stesso dai 18 anni di età federale, per le quote di
// quell'atleta. Come il pagamento della famiglia: si sceglie come, si scatta
// o allega la prova, e le quote risultano pagate subito.

type How = "BANK_TRANSFER" | "MBWAY" | "CASH";

export function AthletePayModal({ athleteId, fees, onClose }: { athleteId: string; fees: Fee[]; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(() => new Set(fees.map((f) => f.id)));
  const [how, setHow] = useState<How>("BANK_TRANSFER");
  const [file, setFile] = useState<File | null>(null);
  const [receiver, setReceiver] = useState("");
  const [otherName, setOtherName] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: receivers } = useQuery({
    queryKey: ["club", "cash-receivers"], queryFn: () => clubGet<CashReceiver[]>("/cash-receivers"), enabled: how === "CASH",
  });
  const chosen = fees.filter((f) => selected.has(f.id));
  const total = chosen.reduce((s, f) => s + f.amount_cents, 0);
  const cash = how === "CASH";
  const ready = chosen.length > 0 && (cash ? (receiver === "other" ? otherName.trim().length >= 2 : receiver !== "") : !!file);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      for (const f of chosen) form.append("fee_ids", f.id);
      form.append("method", how);
      if (cash) {
        if (receiver === "other") form.append("cash_received_by_name", otherName.trim());
        else form.append("cash_received_by_user_id", receiver);
      } else if (file) {
        form.append("file", file);
      }
      if (note.trim()) form.append("note", note.trim());
      await clubSend(`/athlete-area/${athleteId}/payment-proofs`, "POST", form);
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      void celebrate();
      toast({ tone: "success", title: t("pay.recorded"), text: chosen.length === 1 ? t("pay.recordedOne") : t("pay.recordedMany", { n: chosen.length }) });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const tiles: { key: How; icon: string; label: string }[] = [
    { key: "BANK_TRANSFER", icon: "🏦", label: t("pay.howTransfer") },
    { key: "MBWAY", icon: "📱", label: t("pay.howMbway") },
    { key: "CASH", icon: "💶", label: t("pay.howCash") },
  ];

  return (
    <Modal open onClose={onClose} size="lg" title={t("pay.kindFees")} subtitle={t("pay.subtitle")}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        <Button onClick={submit} loading={busy} disabled={!ready}>{cash ? t("pay.cashSend") : t("pay.send")} · {fmt.euro(total)}</Button>
      </>}>
      <div className="space-y-5">
        <ul className="space-y-2">
          {fees.map((f) => (
            <li key={f.id}>
              <label className={cn("flex cursor-pointer items-center gap-3 rounded-2xl p-3.5 ring-1", selected.has(f.id) ? "bg-brand-50 ring-brand-300" : "bg-white ring-ink-200")}>
                <input type="checkbox" className="h-5 w-5 accent-brand-600" checked={selected.has(f.id)}
                  onChange={(e) => setSelected((s) => { const n = new Set(s); if (e.target.checked) n.add(f.id); else n.delete(f.id); return n; })} />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-ink-900">{f.description}</span>
                  <span className="block text-xs text-ink-500">{t("club.dueOn", { date: fmt.shortDate(f.due_date) })}</span>
                </span>
                <span className="font-display text-ink-900">{fmt.euro(f.amount_cents)}</span>
              </label>
            </li>
          ))}
        </ul>
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-500">{t("pay.howTitle")}</p>
          <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t("pay.howTitle")}>
            {tiles.map((tile) => (
              <button key={tile.key} type="button" role="radio" aria-checked={how === tile.key} onClick={() => setHow(tile.key)}
                className={cn("cursor-pointer rounded-2xl p-3 text-center ring-1", how === tile.key ? "bg-brand-50 ring-2 ring-brand-400" : "bg-white ring-ink-200 hover:ring-ink-300")}>
                <span className="block text-2xl" aria-hidden="true">{tile.icon}</span>
                <span className="block text-sm font-semibold text-ink-900">{tile.label}</span>
              </button>
            ))}
          </div>
        </div>
        {cash ? (
          <div className="space-y-3 rounded-2xl bg-white p-4 ring-1 ring-ink-200">
            <label htmlFor="ap-cash" className="block text-sm font-semibold text-ink-900">{t("pay.cashTo")}</label>
            <Select id="ap-cash" value={receiver} onChange={(e) => setReceiver(e.target.value)}>
              <option value="">{t("pay.cashPick")}</option>
              {(receivers ?? []).map((r) => <option key={r.user_id} value={r.user_id}>{r.name}</option>)}
              <option value="other">{t("pay.cashOther")}</option>
            </Select>
            {receiver === "other" && <Input placeholder={t("pay.cashOtherName")} value={otherName} maxLength={120} onChange={(e) => setOtherName(e.target.value)} />}
          </div>
        ) : (
          <ProofPicker file={file} onFile={setFile} />
        )}
        <Textarea placeholder={t("pay.notePlaceholder")} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
        {error && <p className="text-sm text-rose-600">{error}</p>}
      </div>
    </Modal>
  );
}
