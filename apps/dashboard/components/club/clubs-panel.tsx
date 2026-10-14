"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { ClubAdminPanel } from "@/components/club/club-admin-panel";
import { clubSignupUrl, InviteHandoff, StaffModal } from "@/components/club/club-staff";
import { useCurrentClub, type ClubSettings } from "@/components/club/current-club";
import { friendlyApiError } from "@/lib/api-error";
import { enterClub, leaveClub } from "@/lib/club-cookie";
import { useI18n } from "@/lib/i18n/provider";
import { shareOrCopyLink } from "@/lib/share-link";

interface ClubRow {
  id: string;
  name: string;
  slug: string;
  status: "ACTIVE" | "SUSPENDED" | string;
  created_at: string;
  settings: ClubSettings;
  athletes_active: number;
  staff: { user_id: string; email: string; role: string }[];
  kind?: string;
}

async function send<T>(path: string, method: "POST" | "PATCH", body: unknown): Promise<T> {
  const res = await fetch(`/api/proxy/clubs${path}`, {
    method, body: JSON.stringify(body), headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** Il pannello Club dello staff della piattaforma. Finché non si sceglie un
 *  club mostra l'elenco (crea, sospendi, aggiungi la segreteria); "Entra"
 *  apre la gestione di quel club come la vede la sua segreteria, con una
 *  fascia in alto per tornare all'elenco. */
export function ClubsPanel() {
  const { data: current, isLoading } = useCurrentClub();
  const queryClient = useQueryClient();
  const { t } = useI18n();

  async function choose(id: string | null) {
    if (id) enterClub(id);
    else leaveClub();
    // Tutto ciò che è "del club" va riletto: è un altro club.
    await queryClient.resetQueries({ queryKey: ["club"] });
  }

  if (isLoading) return <Skeleton className="h-64" />;
  if (current) {
    return (
      <div className="space-y-6">
        <motion.div
          initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
          className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-ink-900 text-white px-5 py-3"
        >
          <p className="text-sm">
            <span className="text-ink-300">{t("clubs.managing")}</span>{" "}
            <span className="font-semibold">{current.name}</span>
          </p>
          <Button size="sm" variant="secondary" onClick={() => choose(null)}>{t("clubs.backToList")}</Button>
        </motion.div>
        <ClubAdminPanel />
      </div>
    );
  }
  return <ClubList onEnter={(id) => choose(id)} />;
}

export function ClubList({ onEnter }: { onEnter: (id: string) => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["clubs"],
    queryFn: async (): Promise<ClubRow[]> => {
      const res = await fetch("/api/proxy/clubs");
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });
  const [creating, setCreating] = useState(false);
  const [staffFor, setStaffFor] = useState<ClubRow | null>(null);

  async function toggleStatus(club: ClubRow) {
    const status = club.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE";
    if (status === "SUSPENDED" && !window.confirm(t("clubs.suspendConfirm", { name: club.name }))) return;
    try {
      await send(`/${club.id}`, "PATCH", { status });
      await queryClient.invalidateQueries({ queryKey: ["clubs"] });
      toast({ tone: "success", title: status === "ACTIVE" ? t("clubs.reactivated") : t("clubs.suspended") });
    } catch (e) {
      toast({ tone: "error", title: t("clubs.failed"), text: (e as Error).message });
    }
  }

  async function copyLink(club: ClubRow) {
    const result = await shareOrCopyLink({ url: clubSignupUrl(club.slug), title: club.name, preferClipboard: true });
    toast({ tone: result === "failed" ? "error" : "success", title: result === "failed" ? t("clubs.copyFailed") : t("clubs.copied") });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={t("clubs.eyebrow")} title={t("clubs.title")} subtitle={t("clubs.subtitle")}
        actions={<Button onClick={() => setCreating(true)}>{t("clubs.new")}</Button>}
      />
      {isLoading ? <Skeleton className="h-64" /> : error ? (
        <EmptyState title={t("clubs.failed")} text={(error as Error).message} />
      ) : (data ?? []).length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🥋</span>} title={t("clubs.empty")} text={t("clubs.emptyText")}
          action={<Button onClick={() => setCreating(true)}>{t("clubs.new")}</Button>} />
      ) : (
        <Table>
          <THead><tr><TH>{t("clubs.colClub")}</TH><TH>{t("clubs.colAthletes")}</TH><TH>{t("clubs.colStaff")}</TH><TH>{t("clubs.colStatus")}</TH><TH /></tr></THead>
          <TBody>
            {(data ?? []).map((club) => (
              <TR key={club.id}>
                <TD>
                  <p className="font-semibold text-ink-900">
                    {club.name}
                    {club.kind === "JAV_COURSES" && <Badge tone="accent" className="ml-2">🏫 {t("javCourses.navEntry")}</Badge>}
                  </p>
                  <button type="button" onClick={() => copyLink(club)} className="text-xs text-brand-700 hover:underline cursor-pointer" title={t("clubs.copyLink")}>
                    /c/{club.slug}
                  </button>
                  <p className="text-[11px] text-ink-400">{t("clubs.since", { date: fmt.shortDate(club.created_at) })}</p>
                </TD>
                <TD className="font-semibold">{club.athletes_active}</TD>
                <TD className="text-xs">
                  {club.staff.length === 0 ? <Badge tone="warning">{t("clubs.noSecretary")}</Badge> : club.staff.map((s) => (
                    <p key={s.user_id}>{s.email} <span className="text-ink-400">· {t.dyn(`clubs.role.${s.role}`, s.role)}</span></p>
                  ))}
                </TD>
                <TD>
                  <Badge tone={club.status === "ACTIVE" ? "success" : "danger"} dot>
                    {club.status === "ACTIVE" ? t("clubs.statusActive") : t("clubs.statusSuspended")}
                  </Badge>
                </TD>
                <TD className="text-right whitespace-nowrap space-x-1">
                  <Button size="sm" onClick={() => onEnter(club.id)}>{t("clubs.enter")}</Button>
                  <Button size="sm" variant="ghost" onClick={() => setStaffFor(club)}>{t("clubs.addStaff")}</Button>
                  <Button size="sm" variant="ghost" onClick={() => toggleStatus(club)}>
                    {club.status === "ACTIVE" ? t("clubs.suspend") : t("clubs.reactivate")}
                  </Button>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {creating && <CreateClubModal onClose={() => setCreating(false)} />}
      {staffFor && (
        <StaffModal
          title={t("clubs.addStaffTo", { name: staffFor.name })}
          onClose={() => setStaffFor(null)}
          onSubmit={async (email, role) => {
            const created = await send<{ invite_link: string | null }>(`/${staffFor.id}/staff`, "POST", { email, role });
            await queryClient.invalidateQueries({ queryKey: ["clubs"] });
            return created.invite_link;
          }}
        />
      )}
    </div>
  );
}

function slugPreview(name: string): string {
  return name.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
}

function CreateClubModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [secretary, setSecretary] = useState("");
  const [iban, setIban] = useState("");
  const [holder, setHolder] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [handoff, setHandoff] = useState<string | null>(null);
  const effectiveSlug = slug || slugPreview(name);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const created = await send<{ invite_link: string | null }>("", "POST", {
        name, slug: effectiveSlug || null, secretary_email: secretary.trim() || null,
        settings: { bank_iban: iban || null, bank_account_holder: holder || null },
      });
      await queryClient.invalidateQueries({ queryKey: ["clubs"] });
      if (created.invite_link) {
        setHandoff(created.invite_link);
        return;
      }
      toast({ tone: "success", title: t("clubs.created", { name }), text: secretary ? t("clubs.createdInvite", { email: secretary }) : undefined });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (handoff) return <InviteHandoff email={secretary.trim()} link={handoff} onClose={onClose} />;
  return (
    <Modal open onClose={onClose} title={t("clubs.new")} subtitle={t("clubs.newSubtitle")} size="lg"
      footer={<><Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button><Button onClick={submit} loading={busy} disabled={name.trim().length < 3}>{t("clubs.create")}</Button></>}
    >
      <div className="space-y-4">
        <Field label={t("clubs.fieldName")} htmlFor="club-name">
          <Input id="club-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Judo Clube de Lagos" autoFocus />
        </Field>
        <Field label={t("clubs.fieldSlug")} htmlFor="club-slug" hint={effectiveSlug ? clubSignupUrl(effectiveSlug) : undefined}>
          <Input id="club-slug" value={slug} onChange={(e) => setSlug(slugPreview(e.target.value))} placeholder={slugPreview(name) || "judo-clube-de-lagos"} />
        </Field>
        <Field label={t("clubs.fieldSecretary")} htmlFor="club-secretary" hint={t("clubs.fieldSecretaryHint")}>
          <Input id="club-secretary" type="email" value={secretary} onChange={(e) => setSecretary(e.target.value)} placeholder="secretaria@clube.pt" />
        </Field>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label={t("clubs.fieldIban")} htmlFor="club-iban" hint={t("clubs.fieldIbanHint")}>
            <Input id="club-iban" value={iban} onChange={(e) => setIban(e.target.value)} placeholder="PT50 …" />
          </Field>
          <Field label={t("clubs.fieldHolder")} htmlFor="club-holder">
            <Input id="club-holder" value={holder} onChange={(e) => setHolder(e.target.value)} />
          </Field>
        </div>
        {error && <Badge tone="danger">{error}</Badge>}
      </div>
    </Modal>
  );
}
