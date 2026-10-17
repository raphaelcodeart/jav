"use client";

import { AthleteAccess } from "@/components/club/athlete-access";
import { PublicProfileConsent } from "@/components/club/public-profile-consent";
import { motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge, FeeStatusPill } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { Field, Input, Select } from "@/components/ui/field";
import { AchievementBadge } from "@/components/ui/gamification";
import { ImageCropDialog } from "@/components/ui/image-cropper";
import { Modal } from "@/components/ui/modal";
import { ProgressBar } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { AthleteFormModal } from "@/components/club/athlete-form-modal";
import { useClubFeatures } from "@/components/club/jav-courses";
import { PayModal } from "@/components/club/pay-modal";
import { SeasonMonthsPanel } from "@/components/club/season-months";
import {
  ACHIEVEMENT_ICONS,
  CERTIFICATE_LABELS,
  CERTIFICATE_TYPES,
  LEVEL_LABELS,
  PLACEMENT_LABELS,
  clubGet,
  clubSend,
  type AthleteDetail,
  type Fee,
} from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";
import { feeLabel } from "@/lib/fee-label";

type Tab = "path" | "certificates" | "fees" | "competitions" | "access";

/** Everything about one athlete: the judo path (belts, medals, traguardi),
 *  the medical certificate, the fees, the competitions. */
export function AthleteDetailModal({ athleteId, onClose, initialTab = "path" }: { athleteId: string | null; onClose: () => void; initialTab?: Tab }) {
  const [tab, setTab] = useState<Tab>(initialTab);
  // Nei corsi JAV niente cinture, punti, gare né sito: si mostra il resto.
  const features = useClubFeatures();
  const [editing, setEditing] = useState(false);
  const [payFee, setPayFee] = useState<Fee | null>(null);
  const [pickedPhoto, setPickedPhoto] = useState<File | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();
  const { t, fmt } = useI18n();
  const { euro, shortDate } = fmt;
  const { data: a, isLoading } = useQuery({
    queryKey: ["club", "athlete", athleteId],
    queryFn: () => clubGet<AthleteDetail>(`/athletes/${athleteId}`),
    enabled: !!athleteId,
  });

  async function uploadPhoto(file: File) {
    if (!a) return;
    const form = new FormData();
    form.append("file", file);
    try {
      await clubSend(`/athletes/${a.id}/photo`, "POST", form);
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: t("athlete.photoUpdated") });
    } catch (e) {
      toast({ tone: "error", title: t("athlete.photoFailed"), text: (e as Error).message });
    }
  }

  return (
    <Modal open={!!athleteId} onClose={onClose} size="xl">
      {isLoading || !a ? (
        <div className="space-y-4 py-4">
          <Skeleton className="h-28" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className="space-y-6 pt-4">
          <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-500 via-brand-600 to-ink-900 p-5 sm:p-6 text-white">
            <div className="absolute -right-6 -bottom-10 font-display text-[9rem] leading-none text-white/10 select-none" aria-hidden="true">柔</div>
            <div className="relative flex flex-col sm:flex-row sm:items-center gap-5">
              <label className="relative h-24 w-24 shrink-0 rounded-full ring-4 ring-white/80 overflow-hidden bg-white/20 cursor-pointer group" title={t("athlete.changePhoto")}>
                {a.photo_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={a.photo_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  <span className="h-full w-full flex items-center justify-center font-display text-4xl">{a.first_name.slice(0, 1)}</span>
                )}
                <span className="absolute inset-0 bg-ink-900/50 opacity-0 group-hover:opacity-100 flex items-center justify-center text-xs font-bold transition">📷 {t("common.change")}</span>
                <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) setPickedPhoto(f); e.target.value = ""; }} />
              </label>
              <ImageCropDialog file={pickedPhoto} onCancel={() => setPickedPhoto(null)}
                onConfirm={async (f) => { await uploadPhoto(f); setPickedPhoto(null); }} />
              <div className="min-w-0 flex-1">
                <h2 className="text-2xl">{a.first_name} {a.last_name}</h2>
                <p className="text-sm text-white/80 mt-0.5">
                  {t("club.yearsOld", { n: a.age })} · {a.plan?.name ?? t("club.noPlan")}
                  {a.plan ? ` · ${t("athlete.perMonth", { amount: euro(a.plan.monthly_fee_cents) })}` : ""}
                </p>
                {features.belts && (
                  <div className="mt-3 inline-flex rounded-full bg-white/95 px-3 py-1.5">
                    <BeltBadge belt={a.belt} />
                  </div>
                )}
              </div>
              <div className="flex sm:flex-col gap-3 sm:items-end">
                <div className="rounded-2xl bg-white/15 backdrop-blur px-4 py-2 text-center">
                  <p className="font-display text-2xl">{a.level}</p>
                  <p className="text-[10px] uppercase tracking-widest text-white/80">{t("athlete.levelLabel")}</p>
                </div>
                {features.ranking && (
                  <div className="rounded-2xl bg-accent-400 text-ink-900 px-4 py-2 text-center">
                    <p className="font-display text-2xl">{a.ranking_points}</p>
                    <p className="text-[10px] uppercase tracking-widest">{t("athlete.points")}</p>
                  </div>
                )}
              </div>
            </div>
            <div className="relative mt-5">
              <div className="flex justify-between text-[11px] font-semibold text-white/80 mb-1.5">
                <span>{a.xp} XP</span>
                <span>{t("athlete.nextLevelAt", { n: a.level + 1, xp: a.next_level_xp })}</span>
              </div>
              <ProgressBar value={a.xp - a.level_xp_floor} max={Math.max(1, a.next_level_xp - a.level_xp_floor)} tone="accent" />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <Tabs
              value={tab}
              onChange={(k) => setTab(k as Tab)}
              items={[
                { key: "path", label: t("athlete.tabPath") },
                { key: "certificates", label: t("athlete.tabCertificate") },
                { key: "fees", label: t("athlete.tabFees"), count: a.fees.filter((f) => f.status === "DUE").length },
                ...(features.competitions ? [{ key: "competitions", label: t("athlete.tabCompetitions") }] : []),
                { key: "access", label: t("athleteAccess.tab") },
              ]}
            />
            <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>✏️ {t("athlete.editData")}</Button>
          </div>

          {tab === "path" && (
            <div className="space-y-6">
              <section>
                <h3 className="text-sm text-ink-900 mb-3">{t("athlete.achievements")}</h3>
                <div className="flex flex-wrap gap-3 justify-center sm:justify-start">
                  {a.achievements.map((ach, i) => (
                    <motion.div key={ach.code} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
                      <AchievementBadge
                        icon={ACHIEVEMENT_ICONS[ach.code] ?? "⭐"}
                        label={t.dyn(`achievement.${ach.code}`, ach.label)}
                        unlocked={ach.earned}
                        hint={`${t.dyn(`achievement.${ach.code}.desc`, ach.description)} (${Math.min(ach.current, ach.target)}/${ach.target})`}
                      />
                    </motion.div>
                  ))}
                </div>
              </section>
              {features.belts && <section>
                <h3 className="text-sm text-ink-900 mb-3">{t("athlete.belts")}</h3>
                <ol className="relative border-l-2 border-ink-100 ml-3 space-y-4">
                  {[...a.belt_history].reverse().map((b, i) => (
                    <motion.li key={b.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }} className="pl-5 relative">
                      <span className="absolute -left-[9px] top-1.5 h-4 w-4 rounded-full ring-4 ring-white" style={{ background: b.color }} />
                      <BeltBadge belt={b} size="sm" />
                      <p className="text-xs text-ink-500 mt-1">{shortDate(b.awarded_on)}{b.note ? ` · ${b.note}` : ""}</p>
                    </motion.li>
                  ))}
                </ol>
              </section>}
              {/* Il consenso a comparire sul sito pubblico del club: lo dà
                  il genitore, qui, e lo può ritirare quando vuole. Gli
                  atleti dei corsi JAV non compaiono mai sul sito. */}
              {features.belts && <PublicProfileConsent athleteId={a.id} />}
            </div>
          )}

          {tab === "certificates" && <CertificatesTab athlete={a} />}

          {tab === "access" && <AthleteAccess athleteId={a.id} firstName={a.first_name} />}

          {tab === "fees" && (
            <div className="space-y-6">
              <SeasonMonthsPanel athleteId={a.id} mode="family" onPay={setPayFee} />
              {/* Iscrizione, gare, quota socio: non sono mesi, restano in lista. */}
              {a.fees.some((f) => f.kind !== "MONTHLY") && (
                <section>
                  <h3 className="text-sm text-ink-900 mb-2">{t("months.otherFees")}</h3>
                  <div className="space-y-2">
                    {a.fees.filter((f) => f.kind !== "MONTHLY").map((f) => (
                      <div key={f.id} className="flex items-center justify-between gap-3 rounded-2xl bg-white ring-1 ring-ink-100 px-4 py-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-ink-900">{feeLabel(f, t, fmt)}</p>
                          <p className="text-xs text-ink-500">
                            {f.status === "PAID" && f.paid_at ? t("club.paidOn", { date: shortDate(f.paid_at) }) : t("club.dueOnCap", { date: shortDate(f.due_date) })}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="font-display text-ink-900">{euro(f.amount_cents)}</p>
                          <FeeStatusPill status={f.status} overdue={f.overdue} />
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}

          {tab === "competitions" && (
            <div className="space-y-2">
              {a.competitions.length === 0 && <p className="text-sm text-ink-500">{t("athlete.noCompetitions")}</p>}
              {a.competitions.map((c) => (
                <div key={c.entry_id} className="flex items-center justify-between gap-3 rounded-2xl bg-white ring-1 ring-ink-100 px-4 py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-ink-900">{c.name}</p>
                    <p className="text-xs text-ink-500">
                      {shortDate(c.starts_on)} · {t.dyn(`club.level.${c.level}`, LEVEL_LABELS[c.level] ?? c.level)}
                      {c.category ? ` · ${c.category}` : ""}
                    </p>
                  </div>
                  <div className="text-right">
                    {c.placement != null ? (
                      <Badge tone={c.placement === 1 ? "accent" : c.placement <= 3 ? "brand" : "neutral"}>
                        {c.placement === 1 ? "🥇 " : c.placement === 2 ? "🥈 " : c.placement === 3 ? "🥉 " : ""}
                        {t.dyn(`club.placement.${c.placement}`, PLACEMENT_LABELS[c.placement] ?? `${c.placement}°`)}
                      </Badge>
                    ) : (
                      <Badge tone="info">{t("athlete.registered")}</Badge>
                    )}
                    {c.points > 0 && <p className="text-xs font-bold text-brand-600 mt-1">+{c.points} pt</p>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {a && editing && <AthleteFormModal open={editing} onClose={() => setEditing(false)} athlete={a} />}
      {payFee && <PayModal open onClose={() => setPayFee(null)} fees={[payFee]} preselect={[payFee.id]} />}
    </Modal>
  );
}

/** Il certificato medico: lo stato, lo storico, e il caricamento di uno
 *  nuovo. Lo usa la famiglia (default) e l'area dell'atleta, che passa i suoi
 *  indirizzi: stesso servizio sul server, stesso bucket privato. */
export function CertificatesTab({ athlete, uploadPath, urlPath }: {
  athlete: AthleteDetail; uploadPath?: string; urlPath?: (certificateId: string) => string;
}) {
  const [type, setType] = useState("AGONISTIC");
  const [issued, setIssued] = useState("");
  const [expires, setExpires] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();
  const { t, fmt } = useI18n();
  const { shortDate } = fmt;
  const statusCode = CERTIFICATE_LABELS[athlete.certificate.status] ? athlete.certificate.status : "MISSING";
  const status = CERTIFICATE_LABELS[statusCode]!;
  const certType = (code: string) => t.dyn(`club.certType.${code}`, CERTIFICATE_TYPES[code] ?? code);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("type", type);
    form.append("issued_on", issued);
    form.append("expires_on", expires);
    try {
      await clubSend(uploadPath ?? `/athletes/${athlete.id}/certificates`, "POST", form);
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: t("cert.uploaded") });
      setFile(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function open(id: string) {
    try {
      const { url } = await clubGet<{ url: string }>(urlPath ? urlPath(id) : `/certificates/${id}/url`);
      window.open(url, "_blank", "noopener");
    } catch (e) {
      toast({ tone: "error", title: t("cert.openFailed"), text: (e as Error).message });
    }
  }

  return (
    <div className="grid lg:grid-cols-2 gap-5">
      <div className="space-y-3">
        <div className="rounded-2xl ring-1 ring-ink-100 bg-white p-4">
          <Badge tone={status.tone} dot>{t.dyn(`club.cert.${statusCode}`, status.label)}</Badge>
          {athlete.certificate.expires_on && (
            <p className="text-sm text-ink-700 mt-2">
              {athlete.certificate.type ? certType(athlete.certificate.type) : ""} · {t("cert.expiresOn")} <strong>{shortDate(athlete.certificate.expires_on)}</strong>
            </p>
          )}
        </div>
        {athlete.certificates.map((c) => (
          <button key={c.id} onClick={() => open(c.id)} className="w-full flex items-center justify-between gap-3 rounded-2xl bg-white ring-1 ring-ink-100 px-4 py-3 text-left hover:ring-brand-300 cursor-pointer">
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-ink-900 truncate">{certType(c.type)}</span>
              <span className="block text-xs text-ink-500">{shortDate(c.issued_on)} → {shortDate(c.expires_on)}</span>
            </span>
            <span className="text-xs font-semibold text-brand-600">{t("cert.open")} ↗</span>
          </button>
        ))}
      </div>
      <form onSubmit={submit} className="rounded-2xl bg-ink-50 ring-1 ring-ink-100 p-4 space-y-3">
        <p className="font-display text-sm text-ink-900">{t("cert.uploadNew")}</p>
        <Field label={t("cert.type")} htmlFor="cert-type">
          <Select id="cert-type" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="AGONISTIC">{t("cert.agonisticOption")}</option>
            <option value="NON_AGONISTIC">{certType("NON_AGONISTIC")}</option>
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("cert.issuedOn")} htmlFor="cert-issued">
            <Input id="cert-issued" type="date" required value={issued} onChange={(e) => setIssued(e.target.value)} />
          </Field>
          <Field label={t("cert.expiresOnLabel")} htmlFor="cert-expires">
            <Input id="cert-expires" type="date" required value={expires} onChange={(e) => setExpires(e.target.value)} />
          </Field>
        </div>
        <label className="flex items-center gap-3 rounded-xl bg-white ring-1 ring-dashed ring-brand-300 px-4 py-3 cursor-pointer hover:bg-brand-50">
          <span className="text-2xl">📄</span>
          <span className="text-sm font-semibold text-ink-800 truncate">{file ? file.name : t("cert.pickFile")}</span>
          <input type="file" accept="image/*,application/pdf" capture="environment" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <Button type="submit" loading={busy} disabled={!file} className="w-full">{t("cert.upload")}</Button>
      </form>
    </div>
  );
}
