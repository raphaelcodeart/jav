"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { clubSend } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

export interface EditableSlot { id: string; weekday: number; starts_at: string; ends_at: string; room: string | null }

/** Corregge un orario di un corso (giorno, ore, sala) senza toglierlo e
 *  rifarlo (PATCH /club/admin/slots/{id}); da qui si può anche togliere. */
export function SlotEditModal({ slot, courseName, onClose }: { slot: EditableSlot; courseName: string; onClose: () => void }) {
  // Il 1° gennaio 2024 era lunedì, e 0 è lunedì anche per l'API.
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [weekday, setWeekday] = useState(String(slot.weekday));
  const [from, setFrom] = useState(slot.starts_at.slice(0, 5));
  const [to, setTo] = useState(slot.ends_at.slice(0, 5));
  const [room, setRoom] = useState(slot.room ?? "");
  const [busy, setBusy] = useState<"save" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(kind: "save" | "delete") {
    if (kind === "delete" && !window.confirm(t("slots.confirmDelete"))) return;
    setBusy(kind);
    setError(null);
    try {
      if (kind === "save") {
        await clubSend(`/admin/slots/${slot.id}`, "PATCH", { weekday: Number(weekday), starts_at: from, ends_at: to, room: room.trim() || null });
      } else {
        await clubSend(`/admin/slots/${slot.id}`, "DELETE");
      }
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: kind === "save" ? t("slots.saved") : t("slots.deleted") });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal open onClose={onClose} size="sm" title={t("slots.editTitle")} subtitle={courseName}
      footer={<>
        <Button variant="ghost" onClick={() => act("delete")} loading={busy === "delete"} className="mr-auto text-rose-600">{t("slots.delete")}</Button>
        <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        <Button onClick={() => act("save")} loading={busy === "save"} disabled={!from || !to || to <= from}>{t("slots.save")}</Button>
      </>}
    >
      <div className="space-y-4">
        <Field label={t("slots.day")}>
          <Select value={weekday} onChange={(e) => setWeekday(e.target.value)}>
            {[0, 1, 2, 3, 4, 5, 6].map((d) => <option key={d} value={d}>{fmt.date(new Date(2024, 0, 1 + d), { weekday: "long" })}</option>)}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("slots.from")}><Input type="time" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
          <Field label={t("slots.to")}><Input type="time" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        </div>
        <Field label={t("slots.room")}><Input value={room} maxLength={60} onChange={(e) => setRoom(e.target.value)} /></Field>
        {to && from && to <= from && <p className="text-sm text-rose-600">{t("slots.endAfterStart")}</p>}
        {error && <p className="text-sm text-rose-600">{error}</p>}
      </div>
    </Modal>
  );
}
