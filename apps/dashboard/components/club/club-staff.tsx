"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { useI18n } from "@/lib/i18n/provider";
import { shareOrCopyLink } from "@/lib/share-link";

/** L'indirizzo che il club dà alle sue famiglie per registrarsi. */
export function clubSignupUrl(slug: string): string {
  return `${typeof window === "undefined" ? "" : window.location.origin}/c/${slug}`;
}

/** Aggiunge un account di staff a un club: segreteria o istruttore. La
 *  persona riceve l'email per scegliersi la password. `onSubmit` risponde
 *  "requested" quando l'istruttore ha già l'account in un altro club: allora
 *  non si crea niente, parte la richiesta al superadmin (club/staff_clubs.py). */
export function StaffModal({ title, onClose, onSubmit }: { title: string; onClose: () => void; onSubmit: (email: string, role: string) => Promise<string | null | "requested"> }) {
  const { t } = useI18n();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("SECRETARY");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [handoff, setHandoff] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const link = await onSubmit(email.trim(), role);
      if (link === "requested") {
        toast({ tone: "info", title: t("staffClubs.requestSent"), text: t("staffClubs.requestSentText", { email: email.trim() }) });
        onClose();
        return;
      }
      if (link) {
        setHandoff(link);
        return;
      }
      toast({ tone: "success", title: t("clubs.staffAdded"), text: t("clubs.createdInvite", { email: email.trim() }) });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (handoff) return <InviteHandoff email={email.trim()} link={handoff} onClose={onClose} />;
  return (
    <Modal open onClose={onClose} title={title} subtitle={t("clubs.staffSubtitle")}
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button onClick={submit} loading={busy} disabled={!email.includes("@")}>{t("clubs.sendInvite")}</Button></>}
    >
      <div className="space-y-4">
        <Field label="Email" htmlFor="staff-email">
          <Input id="staff-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        </Field>
        <Field label={t("clubs.fieldRole")} htmlFor="staff-role">
          <Select id="staff-role" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="SECRETARY">{t("clubs.role.SECRETARY")}</option>
            <option value="INSTRUCTOR">{t("clubs.role.INSTRUCTOR")}</option>
          </Select>
        </Field>
        {error && <Badge tone="danger">{error}</Badge>}
      </div>
    </Modal>
  );
}

/** L'account c'è, ma l'email d'invito non è partita (SMTP non configurato):
 *  il link di primo accesso lo consegna chi ha creato l'account. */
export function InviteHandoff({ email, link, onClose }: { email: string; link: string; onClose: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  async function copy() {
    const result = await shareOrCopyLink({ url: link, preferClipboard: true });
    toast({ tone: result === "failed" ? "error" : "success", title: result === "failed" ? t("clubs.copyFailed") : t("clubs.copied") });
  }
  return (
    <Modal open onClose={onClose} title={t("clubs.handoffTitle")} subtitle={t("clubs.handoffText", { email })}
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.close")}</Button><Button onClick={copy}>{t("clubs.handoffCopy")}</Button></>}
    >
      <code className="block rounded-xl bg-ink-50 px-3 py-2 text-xs text-ink-900 break-all">{link}</code>
    </Modal>
  );
}
