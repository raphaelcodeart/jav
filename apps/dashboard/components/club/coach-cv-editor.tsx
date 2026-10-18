"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Textarea } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { CV_QUERY, CvCard, DocumentStatusChip, PdfActions, Switch, useCv } from "@/components/club/coach-cv-common";
import { categoryLabel } from "@/components/club/coach-cv-documents";
import { CoachAvatar } from "@/components/club/staff-clubs";
import { clubSend } from "@/lib/club";
import {
  CATEGORY_ICONS, CV, cvDefaults, cvPayload,
  type CvData, type CvEducation, type CvExperience, type CvResponse, type CvShow,
} from "@/lib/coach-cv";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// L'editor del CV del treinador: quello che scrive lui (titolo, profilo,
// esperienze, formazione, competenze...) e, accanto, quello che il gestionale
// sa già e mette da solo nel PDF (nome, email, foto, club, cintura,
// certificazioni dell'archivio). Si salva tutto insieme con il bottone in
// basso, che resta sempre in vista.

const MAX_LINKS = 6;
// I nomi giapponesi delle tecniche non si traducono.
const TECHNICAL_SUGGESTIONS = ["Nage-waza", "Katame-waza", "Ne-waza", "Kata", "Randori", "Kumi-kata", "Ukemi"];
const SPECIALIZATION_KEYS = ["adapted", "children", "competition", "selfDefense", "conditioning", "refereeing"] as const;
const SHOW_KEYS: (keyof CvShow)[] = ["photo", "birth_date", "phone", "email", "clubs"];

export function CvEditorTab({ onGoDocuments }: { onGoDocuments: () => void }) {
  const { t } = useI18n();
  const { data, isLoading, error } = useCv();
  if (isLoading) return <div className="space-y-4"><Skeleton className="h-40" /><Skeleton className="h-64" /><Skeleton className="h-64" /></div>;
  if (error || !data) return <EmptyState icon={<span className="text-3xl">📄</span>} title={t("cv.loadFailed")} text={error?.message} />;
  return <CvEditor key={data.me.user_id} data={data} onGoDocuments={onGoDocuments} />;
}

function move<T>(list: T[], i: number, dir: -1 | 1): T[] {
  const j = i + dir;
  if (j < 0 || j >= list.length) return list;
  const out = [...list];
  [out[i], out[j]] = [out[j]!, out[i]!];
  return out;
}

function CvEditor({ data, onGoDocuments }: { data: CvResponse; onGoDocuments: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  // `base` è l'ultimo CV salvato, il termine di paragone di «non salvato». Si
  // aggiorna solo salvando, non a ogni ricarica della query (una foto nuova
  // non deve cancellare quello che si sta scrivendo), e il modulo non si
  // rimonta: l'anteprima del PDF, che salva prima di aprirsi, resta viva.
  const [base, setBase] = useState<Partial<CvData>>(() => data.data);
  const [draft, setDraft] = useState<CvData>(() => cvDefaults(data.data));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const saved = useMemo(() => JSON.stringify(cvPayload(cvDefaults(base))), [base]);
  const dirty = JSON.stringify(cvPayload(draft)) !== saved;

  // Chiudere la scheda con modifiche non salvate: il browser chiede conferma.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const set = <K extends keyof CvData>(key: K, value: CvData[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const setItem = <K extends "experiences" | "education" | "links" | "languages" | "custom_sections">(
    key: K, i: number, patch: Partial<CvData[K][number]>,
  ) => setDraft((d) => ({ ...d, [key]: (d[key] as CvData[K][number][]).map((x, j) => (j === i ? { ...x, ...patch } : x)) }));

  async function save(): Promise<boolean> {
    setSaving(true);
    setError(null);
    try {
      const res = await clubSend<CvResponse>(CV(), "PUT", cvPayload(draft));
      qc.setQueryData(CV_QUERY, res);
      setBase(res.data);
      setDraft(cvDefaults(res.data));
      toast({ tone: "success", title: t("cv.editor.saved") });
      return true;
    } catch (e) {
      setError((e as Error).message);
      toast({ tone: "error", title: t("cv.editor.saveFailed"), text: (e as Error).message });
      return false;
    } finally {
      setSaving(false);
    }
  }

  const certs = data.documents.filter((d) => d.show_in_cv);
  const monthYear = (iso: string | null) => (iso ? fmt.date(new Date(`${iso.slice(0, 10)}T12:00:00`), { month: "short", year: "numeric" }) : "");

  return (
    <div className="space-y-5">
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        {/* --- Quello che scrive il treinador --- */}
        <div className="space-y-5">
          <CvCard icon="✨" title={t("cv.editor.presentation")} hint={t("cv.editor.presentationHint")}>
            <div className="space-y-3">
              <Field label={t("cv.editor.headline")}>
                <Input value={draft.headline ?? ""} maxLength={150} onChange={(e) => set("headline", e.target.value)} placeholder={t("cv.editor.headlinePlaceholder")} />
              </Field>
              <Field label={t("cv.editor.summary")} hint={t("cv.editor.summaryHint")}>
                <Textarea rows={5} value={draft.summary ?? ""} maxLength={4000} onChange={(e) => set("summary", e.target.value)} placeholder={t("cv.editor.summaryPlaceholder")} />
              </Field>
            </div>
          </CvCard>

          <CvCard icon="🪪" title={t("cv.editor.personal")}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("cv.editor.birthDate")}>
                <Input value={draft.birth_date ?? ""} maxLength={20} onChange={(e) => set("birth_date", e.target.value)} placeholder={t("cv.editor.birthDatePlaceholder")} />
              </Field>
              <Field label={t("cv.editor.nationality")}>
                <Input value={draft.nationality ?? ""} maxLength={60} onChange={(e) => set("nationality", e.target.value)} placeholder={t("cv.editor.nationalityPlaceholder")} />
              </Field>
              <Field label={t("cv.editor.phone")}>
                <Input type="tel" inputMode="tel" autoComplete="tel" value={draft.phone ?? ""} maxLength={40} onChange={(e) => set("phone", e.target.value)} />
              </Field>
              <Field label={t("cv.editor.email")} hint={t("cv.editor.emailHint")}>
                <Input type="email" inputMode="email" value={draft.email ?? ""} maxLength={255} onChange={(e) => set("email", e.target.value)} placeholder={data.me.email} />
              </Field>
              <Field label={t("cv.editor.city")}>
                <Input value={draft.city ?? ""} maxLength={100} onChange={(e) => set("city", e.target.value)} />
              </Field>
            </div>
            <div className="mt-4">
              <p className="mb-2 text-sm font-semibold text-ink-800">{t("cv.editor.links")}</p>
              <div className="space-y-2">
                {draft.links.map((l, i) => (
                  <div key={i} className="flex gap-2">
                    <Input className="w-28 shrink-0 sm:w-36" value={l.label ?? ""} maxLength={60} onChange={(e) => setItem("links", i, { label: e.target.value })}
                      placeholder={t("cv.editor.linkLabel")} aria-label={t("cv.editor.linkLabel")} />
                    <Input type="url" inputMode="url" value={l.url} maxLength={300} onChange={(e) => setItem("links", i, { url: e.target.value })}
                      placeholder="https://" aria-label={t("cv.editor.linkUrl")} />
                    <RemoveButton onClick={() => set("links", draft.links.filter((_, j) => j !== i))} />
                  </div>
                ))}
              </div>
              {draft.links.length < MAX_LINKS && (
                <Button size="sm" variant="ghost" className="mt-2" onClick={() => set("links", [...draft.links, { label: "", url: "" }])}>
                  ＋ {t("cv.editor.addLink")}
                </Button>
              )}
            </div>
          </CvCard>

          <CvCard icon="💼" title={t("cv.editor.experience")} hint={t("cv.editor.experienceHint")}>
            <ItemList count={draft.experiences.length} empty={t("cv.editor.experienceEmpty")}
              addLabel={t("cv.editor.addExperience")}
              onAdd={() => set("experiences", [...draft.experiences, { role: "", organization: "", city: "", start: "", end: "", current: false, description: "" }])}>
              {draft.experiences.map((x, i) => (
                <ItemShell key={i} startOpen={!x.role} title={x.role || t("cv.editor.newItem")} subtitle={x.organization ?? ""} index={i} total={draft.experiences.length}
                  onMove={(dir) => set("experiences", move(draft.experiences, i, dir))}
                  onRemove={() => set("experiences", draft.experiences.filter((_, j) => j !== i))}>
                  <ExperienceFields value={x} onChange={(patch) => setItem("experiences", i, patch)} />
                </ItemShell>
              ))}
            </ItemList>
          </CvCard>

          <CvCard icon="🎓" title={t("cv.editor.education")} hint={t("cv.editor.educationHint")}>
            <ItemList count={draft.education.length} empty={t("cv.editor.educationEmpty")}
              addLabel={t("cv.editor.addEducation")}
              onAdd={() => set("education", [...draft.education, { title: "", institution: "", start: "", end: "", description: "" }])}>
              {draft.education.map((x, i) => (
                <ItemShell key={i} startOpen={!x.title} title={x.title || t("cv.editor.newItem")} subtitle={x.institution ?? ""} index={i} total={draft.education.length}
                  onMove={(dir) => set("education", move(draft.education, i, dir))}
                  onRemove={() => set("education", draft.education.filter((_, j) => j !== i))}>
                  <EducationFields value={x} onChange={(patch) => setItem("education", i, patch)} />
                </ItemShell>
              ))}
            </ItemList>
          </CvCard>

          <CvCard icon="🧠" title={t("cv.editor.skills")} hint={t("cv.editor.chipsHint")}>
            <div className="space-y-4">
              <ChipInput label={t("cv.editor.skillsTechnical")} values={draft.skills.technical} suggestions={TECHNICAL_SUGGESTIONS}
                placeholder={t("cv.editor.skillsTechnicalPlaceholder")} onChange={(v) => set("skills", { ...draft.skills, technical: v })} />
              <ChipInput label={t("cv.editor.skillsPedagogical")} values={draft.skills.pedagogical}
                placeholder={t("cv.editor.skillsPedagogicalPlaceholder")} onChange={(v) => set("skills", { ...draft.skills, pedagogical: v })} />
              <ChipInput label={t("cv.editor.skillsOrganizational")} values={draft.skills.organizational}
                placeholder={t("cv.editor.skillsOrganizationalPlaceholder")} onChange={(v) => set("skills", { ...draft.skills, organizational: v })} />
            </div>
          </CvCard>

          <CvCard icon="🎯" title={t("cv.editor.specializations")} hint={t("cv.editor.specializationsHint")}>
            <ChipInput values={draft.specializations} suggestions={SPECIALIZATION_KEYS.map((k) => t(`cv.spec.${k}`))}
              placeholder={t("cv.editor.specializationsPlaceholder")} onChange={(v) => set("specializations", v)} />
          </CvCard>

          <CvCard icon="🗣️" title={t("cv.editor.languages")}>
            <div className="space-y-2">
              {draft.languages.map((l, i) => (
                <div key={i} className="flex gap-2">
                  <Input value={l.name} maxLength={60} onChange={(e) => setItem("languages", i, { name: e.target.value })}
                    placeholder={t("cv.editor.languageName")} aria-label={t("cv.editor.languageName")} />
                  <Input className="w-32 shrink-0 sm:w-40" list="cv-language-levels" value={l.level ?? ""} maxLength={60}
                    onChange={(e) => setItem("languages", i, { level: e.target.value })} placeholder={t("cv.editor.languageLevel")} aria-label={t("cv.editor.languageLevel")} />
                  <RemoveButton onClick={() => set("languages", draft.languages.filter((_, j) => j !== i))} />
                </div>
              ))}
              <datalist id="cv-language-levels">
                {[t("cv.editor.languageNative"), "C2", "C1", "B2", "B1", "A2", "A1"].map((v) => <option key={v} value={v} />)}
              </datalist>
            </div>
            {draft.languages.length < 12 && (
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => set("languages", [...draft.languages, { name: "", level: "" }])}>
                ＋ {t("cv.editor.addLanguage")}
              </Button>
            )}
          </CvCard>

          <CvCard icon="🧩" title={t("cv.editor.custom")} hint={t("cv.editor.customHint")}>
            <ItemList count={draft.custom_sections.length} empty={t("cv.editor.customEmpty")} addLabel={t("cv.editor.addCustom")}
              onAdd={() => set("custom_sections", [...draft.custom_sections, { title: "", body: "" }])}>
              {draft.custom_sections.map((s, i) => (
                <ItemShell key={i} startOpen={!s.title} title={s.title || t("cv.editor.newItem")} index={i} total={draft.custom_sections.length}
                  onMove={(dir) => set("custom_sections", move(draft.custom_sections, i, dir))}
                  onRemove={() => set("custom_sections", draft.custom_sections.filter((_, j) => j !== i))}>
                  <div className="space-y-3">
                    <Field label={t("cv.editor.customTitle")}>
                      <Input value={s.title} maxLength={100} onChange={(e) => setItem("custom_sections", i, { title: e.target.value })} placeholder={t("cv.editor.customTitlePlaceholder")} />
                    </Field>
                    <Field label={t("cv.editor.customBody")}>
                      <Textarea rows={4} value={s.body} maxLength={4000} onChange={(e) => setItem("custom_sections", i, { body: e.target.value })} />
                    </Field>
                  </div>
                </ItemShell>
              ))}
            </ItemList>
          </CvCard>
        </div>

        {/* --- Quello che il gestionale sa già --- */}
        <div className="space-y-5 lg:sticky lg:top-6">
          <CvCard icon="🤖" title={t("cv.auto.title")} hint={t("cv.auto.hint")} className="bg-gradient-to-br from-white to-ink-50/80">
            <div className="flex items-center gap-4">
              <CoachAvatar me={data.me} size="md" onUploaded={() => void qc.invalidateQueries({ queryKey: CV_QUERY })} />
              <div className="min-w-0">
                <p className="truncate font-display text-lg text-ink-900">{data.me.name}</p>
                <p className="truncate text-sm text-ink-500">{data.me.email}</p>
                <p className="mt-1 text-xs text-ink-400">{t("cv.auto.photoHint")}</p>
              </div>
            </div>
            <div className="mt-4 rounded-2xl bg-white p-3 ring-1 ring-ink-100">
              <p className="mb-1 text-[11px] font-bold uppercase tracking-wider text-ink-500">{t("cv.auto.belt")}</p>
              {data.belt ? <BeltBadge code={data.belt.code} /> : <p className="text-sm text-ink-500">{t("cv.auto.noBelt")}</p>}
            </div>
          </CvCard>

          <CvCard icon="🏯" title={t("cv.auto.clubs")} hint={t("cv.auto.clubsHint")}>
            {data.clubs.length === 0 ? <p className="text-sm text-ink-500">{t("cv.auto.noClubs")}</p> : (
              <ul className="space-y-2">
                {data.clubs.map((c) => (
                  <li key={c.club_id} className="rounded-2xl bg-ink-50/70 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-semibold text-ink-900">{c.name}</p>
                      {!c.active && <Badge>{t("cv.auto.clubClosed")}</Badge>}
                    </div>
                    <p className="text-xs text-ink-500">
                      {c.since ? t("cv.auto.since", { date: monthYear(c.since) }) : ""}
                      {c.last_activity ? ` · ${t("cv.auto.lastActivity", { date: monthYear(c.last_activity) })}` : ""}
                    </p>
                    {c.courses.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {c.courses.map((name) => <span key={name} className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-ink-700 ring-1 ring-ink-200">📚 {name}</span>)}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CvCard>

          <CvCard icon="📜" title={t("cv.auto.certs")} hint={t("cv.auto.certsHint")}
            action={<Button size="sm" variant="ghost" onClick={onGoDocuments}>{t("cv.auto.manage")} ›</Button>}>
            {certs.length === 0 ? <p className="text-sm text-ink-500">{t("cv.auto.noCerts")}</p> : (
              <ul className="space-y-2">
                {certs.map((d) => (
                  <li key={d.id} className="flex items-start gap-2">
                    <span aria-hidden="true">{CATEGORY_ICONS[d.category] ?? "📄"}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-ink-900">{d.title}</span>
                      <span className="block text-xs text-ink-500">{categoryLabel(t, d.category, d.category_label)}{d.issuer ? ` · ${d.issuer}` : ""}</span>
                    </span>
                    {d.status !== "VALID" && <DocumentStatusChip doc={d} />}
                  </li>
                ))}
              </ul>
            )}
          </CvCard>

          <CvCard icon="👁️" title={t("cv.editor.showTitle")} hint={t("cv.editor.showHint")}>
            <div className="divide-y divide-ink-100">
              {SHOW_KEYS.map((k) => (
                <Switch key={k} checked={draft.show[k]} label={t(`cv.show.${k}`)} onChange={(v) => set("show", { ...draft.show, [k]: v })} />
              ))}
            </div>
          </CvCard>

          <CvCard icon="🖨️" title={t("cv.pdf.title")} hint={dirty ? t("cv.pdf.savesFirst") : t("cv.pdf.hint")}>
            <PdfActions kind="CV" beforeAction={async () => (dirty ? save() : true)} />
          </CvCard>
        </div>
      </div>

      {error && <p className="rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">{error}</p>}

      {/* Il bottone Guardar resta sempre in vista, sopra la barra del telefono. */}
      <div className="sticky bottom-[calc(max(env(safe-area-inset-bottom),12px)+88px)] z-30 lg:bottom-6">
        <div className={cn("mx-auto flex max-w-xl items-center gap-3 rounded-3xl p-2 pl-4 shadow-lift ring-1 backdrop-blur-xl transition-colors",
          dirty ? "bg-ink-950/95 text-white ring-ink-900" : "bg-white/95 text-ink-700 ring-ink-200")}>
          <span className="min-w-0 flex-1 text-sm">
            <AnimatePresence mode="wait" initial={false}>
              <motion.span key={dirty ? "dirty" : "clean"} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                className="flex items-center gap-2">
                <span className={cn("h-2 w-2 shrink-0 rounded-full", dirty ? "bg-accent-400" : "bg-emerald-500")} aria-hidden="true" />
                <span className="truncate">
                  {dirty ? t("cv.editor.unsaved")
                    : data.updated_at ? t("cv.editor.savedAt", { date: fmt.shortDate(data.updated_at) }) : t("cv.editor.notYet")}
                </span>
              </motion.span>
            </AnimatePresence>
          </span>
          <Button onClick={() => void save()} loading={saving} disabled={!dirty} className="shrink-0">💾 {t("common.save")}</Button>
        </div>
      </div>
    </div>
  );
}

function RemoveButton({ onClick }: { onClick: () => void }) {
  const { t } = useI18n();
  return (
    <button type="button" onClick={onClick} aria-label={t("cv.delete")} title={t("cv.delete")}
      className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-xl text-ink-400 hover:bg-rose-50 hover:text-rose-600">✕</button>
  );
}

function ItemList({ count, empty, addLabel, onAdd, children }: { count: number; empty: string; addLabel: string; onAdd: () => void; children: ReactNode }) {
  return (
    <div className="space-y-3">
      {count === 0 && <p className="text-sm text-ink-500">{empty}</p>}
      {children}
      <Button size="sm" variant="secondary" onClick={onAdd} disabled={count >= 40}>＋ {addLabel}</Button>
    </div>
  );
}

/** Una voce di un elenco (esperienza, formazione, sezione): si apre per
 *  scriverla e si chiude per vedere l'elenco intero; frecce per l'ordine. */
function ItemShell({ title, subtitle, index, total, startOpen, onMove, onRemove, children }: {
  title: string; subtitle?: string; index: number; total: number; startOpen: boolean;
  onMove: (dir: -1 | 1) => void; onRemove: () => void; children: ReactNode;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(startOpen);
  const arrow = "flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-ink-500 hover:bg-white hover:text-ink-900 disabled:cursor-default disabled:opacity-30";
  return (
    <div className="rounded-2xl bg-ink-50/70 ring-1 ring-ink-100">
      <div className="flex items-center gap-1 p-2 pl-3">
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left">
          <span className={cn("text-ink-400 transition-transform", open && "rotate-90")} aria-hidden="true">›</span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold text-ink-900">{title}</span>
            {subtitle && <span className="block truncate text-xs text-ink-500">{subtitle}</span>}
          </span>
        </button>
        <button type="button" className={arrow} disabled={index === 0} onClick={() => onMove(-1)} aria-label={t("cv.editor.moveUp")}>↑</button>
        <button type="button" className={arrow} disabled={index === total - 1} onClick={() => onMove(1)} aria-label={t("cv.editor.moveDown")}>↓</button>
        <button type="button" className={cn(arrow, "hover:text-rose-600")} onClick={() => { if (window.confirm(t("cv.editor.removeConfirm"))) onRemove(); }}
          aria-label={t("cv.delete")}>🗑️</button>
      </div>
      {open && <div className="border-t border-ink-100 p-3">{children}</div>}
    </div>
  );
}

/** Mese e anno: il selettore del mese del browser; un vecchio valore di solo
 *  anno ("2015") si mostra e si corregge come testo. */
function MonthInput({ value, onChange, label, disabled }: { value: string; onChange: (v: string) => void; label: string; disabled?: boolean }) {
  return (
    <Field label={label}>
      <Input type={/^\d{4}$/.test(value) ? "text" : "month"} value={value} onChange={(e) => onChange(e.target.value)}
        placeholder="AAAA-MM" pattern="\d{4}(-\d{2})?" disabled={disabled} />
    </Field>
  );
}

function ExperienceFields({ value: x, onChange }: { value: CvExperience; onChange: (patch: Partial<CvExperience>) => void }) {
  const { t } = useI18n();
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("cv.editor.role")}>
          <Input value={x.role} maxLength={150} onChange={(e) => onChange({ role: e.target.value })} placeholder={t("cv.editor.rolePlaceholder")} />
        </Field>
        <Field label={t("cv.editor.organization")}>
          <Input value={x.organization ?? ""} maxLength={200} onChange={(e) => onChange({ organization: e.target.value })} placeholder={t("cv.editor.organizationPlaceholder")} />
        </Field>
        <Field label={t("cv.editor.city")}>
          <Input value={x.city ?? ""} maxLength={100} onChange={(e) => onChange({ city: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <MonthInput label={t("cv.editor.start")} value={x.start ?? ""} onChange={(v) => onChange({ start: v })} />
          <MonthInput label={t("cv.editor.end")} value={x.current ? "" : x.end ?? ""} onChange={(v) => onChange({ end: v })} disabled={x.current} />
        </div>
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-ink-800">
        <input type="checkbox" className="h-5 w-5 accent-brand-600" checked={x.current} onChange={(e) => onChange({ current: e.target.checked })} />
        {t("cv.editor.current")}
      </label>
      <Field label={t("cv.editor.description")}>
        <Textarea rows={3} value={x.description ?? ""} maxLength={2000} onChange={(e) => onChange({ description: e.target.value })} placeholder={t("cv.editor.experienceDescPlaceholder")} />
      </Field>
    </div>
  );
}

function EducationFields({ value: x, onChange }: { value: CvEducation; onChange: (patch: Partial<CvEducation>) => void }) {
  const { t } = useI18n();
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("cv.editor.educationTitle")}>
          <Input value={x.title} maxLength={200} onChange={(e) => onChange({ title: e.target.value })} placeholder={t("cv.editor.educationTitlePlaceholder")} />
        </Field>
        <Field label={t("cv.editor.institution")}>
          <Input value={x.institution ?? ""} maxLength={200} onChange={(e) => onChange({ institution: e.target.value })} />
        </Field>
        <MonthInput label={t("cv.editor.start")} value={x.start ?? ""} onChange={(v) => onChange({ start: v })} />
        <MonthInput label={t("cv.editor.end")} value={x.end ?? ""} onChange={(v) => onChange({ end: v })} />
      </div>
      <Field label={t("cv.editor.description")}>
        <Textarea rows={3} value={x.description ?? ""} maxLength={2000} onChange={(e) => onChange({ description: e.target.value })} />
      </Field>
    </div>
  );
}

/** Un elenco di parole a pillole: si scrive e Invio (o la virgola) aggiunge;
 *  le proposte si toccano. Come le tecniche del quaderno. */
function ChipInput({ label, values, suggestions = [], placeholder, onChange }: {
  label?: string; values: string[]; suggestions?: string[]; placeholder?: string; onChange: (v: string[]) => void;
}) {
  const { t } = useI18n();
  const [input, setInput] = useState("");
  function add(raw: string) {
    const fresh = raw.split(",").map((x) => x.trim().slice(0, 100)).filter(Boolean);
    if (!fresh.length) return;
    const seen = new Set(values.map((x) => x.toLowerCase()));
    onChange([...values, ...fresh.filter((x) => !seen.has(x.toLowerCase()))].slice(0, 40));
    setInput("");
  }
  const quick = suggestions.filter((s) => !values.some((x) => x.toLowerCase() === s.toLowerCase()));
  return (
    <div className="space-y-2">
      {label && <p className="text-sm font-semibold text-ink-800">{label}</p>}
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {values.map((v) => (
            <button key={v} type="button" onClick={() => onChange(values.filter((x) => x !== v))}
              className="cursor-pointer rounded-full bg-accent-50 px-3 py-1 text-sm font-semibold text-ink-800 ring-1 ring-accent-300 hover:bg-rose-50 hover:ring-rose-300"
              aria-label={t("cv.editor.removeChip", { value: v })}>
              {v} <span className="text-ink-400" aria-hidden="true">✕</span>
            </button>
          ))}
        </div>
      )}
      <Input value={input} onChange={(e) => (e.target.value.includes(",") ? add(e.target.value) : setInput(e.target.value))}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(input); } }}
        onBlur={() => add(input)} placeholder={placeholder} enterKeyHint="done" aria-label={label ?? placeholder} />
      {quick.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {quick.map((s) => (
            <button key={s} type="button" onClick={() => add(s)}
              className="cursor-pointer rounded-full bg-white px-3 py-1 text-xs text-ink-600 ring-1 ring-ink-200 hover:ring-brand-300">＋ {s}</button>
          ))}
        </div>
      )}
    </div>
  );
}
