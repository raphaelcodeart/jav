"use client";

import { motion } from "motion/react";
import { useRef, useState, useSyncExternalStore } from "react";
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { Button, Spinner } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ImageCropDialog } from "@/components/ui/image-cropper";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { normalizeHex } from "@/lib/brand";
import { clubGet, clubSend } from "@/lib/club";
import { enterStaffClub, leaveStaffClub, readStaffClub, subscribeStaffClub } from "@/lib/club-cookie";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// Il treinador di più club (apps/api/app/domains/club/staff_clubs.py): un
// account solo, più club. Entrando nell'area sceglie il club con un bottone
// grande, e solo dopo vede i dati di quel club; "Trocar de clube" in testata
// lo riporta alla scelta.

export interface StaffClubOption {
  id: string;
  name: string;
  kind: string;
  /** Il club dell'account; falso = ci allena come ospite. */
  home: boolean;
  logo_url: string | null;
  brand_primary: string | null;
  brand_secondary: string | null;
  athletes: number;
  my_courses: number;
}

export interface MyClubs {
  me: { user_id: string; name: string; first_name: string | null; photo_url: string | null };
  clubs: StaffClubOption[];
}

// Fuori dal prefisso ["club"]: cambiando club si azzera tutto ciò che è
// "del club", ma l'elenco dei club tra cui scegliere resta lo stesso.
const MY_CLUBS_KEY = ["staff-clubs", "mine"];

export function useMyClubs() {
  return useQuery({
    queryKey: MY_CLUBS_KEY,
    queryFn: () => clubGet<MyClubs>("/staff/my-clubs"),
    retry: false,
    staleTime: 5 * 60_000,
  });
}

/** Il club scelto (cookie jav_staff_club); null sul server e prima di scegliere. */
export function useStaffClubCookie(): string | null {
  return useSyncExternalStore(subscribeStaffClub, readStaffClub, () => null);
}

/** Cambia club (o torna alla scelta, con `null`): il cookie prima, poi via
 *  tutto quello che era del club di prima, così niente resta sullo schermo. */
export async function switchStaffClub(queryClient: QueryClient, clubId: string | null) {
  if (clubId) enterStaffClub(clubId);
  else leaveStaffClub();
  await queryClient.resetQueries({ predicate: (q) => q.queryKey[0] !== MY_CLUBS_KEY[0] });
}

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";

export function greetingKey(hour: number) {
  return hour < 13 ? ("coach2.home.morning" as const) : hour < 20 ? ("coach2.home.afternoon" as const) : ("coach2.home.evening" as const);
}

/** La foto del treinador, tonda, con l'anello: toccandola se ne carica una
 *  nuova (si ritaglia nel cerchio prima di caricarla). Senza foto, le iniziali. */
export function CoachAvatar({ me, size = "lg", editable = true, className }: {
  me: MyClubs["me"]; size?: "md" | "lg"; editable?: boolean; className?: string;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const box = size === "lg" ? "h-24 w-24 sm:h-28 sm:w-28 text-3xl" : "h-16 w-16 text-xl";

  async function upload(file: File) {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      await clubSend("/staff/me/photo", "PUT", form);
      await queryClient.invalidateQueries({ queryKey: MY_CLUBS_KEY });
      toast({ tone: "success", title: t("staffClubs.photoSaved") });
    } catch (e) {
      toast({ tone: "error", title: t("staffClubs.photoFailed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const face = me.photo_url ? (
    // eslint-disable-next-line @next/next/no-img-element -- foto caricata dal treinador
    <img src={me.photo_url} alt={me.name} className="h-full w-full object-cover" />
  ) : (
    <span className="font-display text-white">{initials(me.name)}</span>
  );
  const ring = cn("relative flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-brand-500 to-brand-700 shadow-lift ring-4 ring-white/80 ring-offset-2 ring-offset-accent-300/60", box, className);

  if (!editable) return <span className={ring}>{face}</span>;
  return (
    <>
      <motion.button type="button" whileTap={{ scale: 0.95 }} onClick={() => input.current?.click()} disabled={busy}
        className={cn(ring, "group cursor-pointer")} aria-label={me.photo_url ? t("staffClubs.photoChange") : t("staffClubs.photoAdd")}
        title={me.photo_url ? t("staffClubs.photoChange") : t("staffClubs.photoAdd")}>
        {face}
        <span className="absolute inset-x-0 bottom-0 flex h-1/3 items-center justify-center bg-ink-950/45 text-sm text-white opacity-80 transition-opacity group-hover:opacity-100" aria-hidden="true">
          {busy ? <Spinner /> : "📷"}
        </span>
      </motion.button>
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) setPicked(f); }} />
      <ImageCropDialog file={picked} onCancel={() => setPicked(null)} onConfirm={async (f) => { setPicked(null); await upload(f); }} />
    </>
  );
}

/** Il logo del club in un cerchio bianco, intero (mai tagliato). */
export function ClubLogo({ club, className }: { club: Pick<StaffClubOption, "name" | "logo_url">; className?: string }) {
  return (
    <span className={cn("flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-white p-1.5 shadow-soft ring-1 ring-ink-100", className)}>
      {club.logo_url ? (
        // eslint-disable-next-line @next/next/no-img-element -- logo caricato dal club
        <img src={club.logo_url} alt="" className="h-full w-full object-contain" />
      ) : (
        <span className="font-display text-ink-700">{initials(club.name)}</span>
      )}
    </span>
  );
}

/** Il saluto del treinador con la sua foto a destra, e un bottone grande per
 *  ogni club in cui allena: si entra solo scegliendone uno. */
export function StaffClubPicker({ data, isLoading, error, onChoose }: {
  data: MyClubs | undefined; isLoading: boolean; error: Error | null; onChoose: (id: string) => void;
}) {
  const { t } = useI18n();
  const [entering, setEntering] = useState<string | null>(null);
  if (isLoading) return <div className="space-y-4"><Skeleton className="h-40" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div>;
  if (error || !data) return <EmptyState icon={<span className="text-3xl">🏯</span>} title={t("staffClubs.loadFailed")} text={error?.message} />;

  const name = data.me.first_name || data.me.name.split(" ")[0] || "";
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-ink-950 via-brand-800 to-brand-600 p-6 text-white shadow-lift sm:p-8">
        <div aria-hidden="true" className="pointer-events-none absolute -left-16 -top-24 h-64 w-64 rounded-full bg-accent-400/20 blur-3xl" />
        <div className="relative flex items-center justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-3xl leading-tight sm:text-4xl" suppressHydrationWarning>
              {t(greetingKey(new Date().getHours()))}{name ? `, ${name}` : ""} 👋
            </h2>
            <p className="mt-2 text-sm text-white/80 sm:text-base">{t("staffClubs.pickTitle")}</p>
          </div>
          <CoachAvatar me={data.me} />
        </div>
      </section>

      {data.clubs.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">🏯</span>} title={t("staffClubs.none")} text={t("staffClubs.noneText")} />
      ) : (
        <div className="space-y-3">
          <p className="px-1 text-sm text-ink-500">{t("staffClubs.pickSubtitle")}</p>
          {data.clubs.map((club, i) => {
            const color = normalizeHex(club.brand_primary) ?? undefined;
            return (
              <motion.button key={club.id} type="button" disabled={entering !== null}
                initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
                whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }}
                onClick={() => { setEntering(club.id); onChoose(club.id); }}
                className="group relative flex w-full cursor-pointer items-center gap-4 overflow-hidden rounded-3xl bg-white p-4 text-left shadow-soft ring-1 ring-ink-900/5 hover:shadow-lift hover:ring-brand-300 disabled:cursor-wait sm:gap-5 sm:p-5">
                {/* Il colore del club, come una fascia: si riconosce a colpo d'occhio. */}
                <span aria-hidden="true" className="absolute inset-y-0 left-0 w-2 bg-brand-500" style={color ? { background: color } : undefined} />
                <ClubLogo club={club} className="ml-1 h-16 w-16 sm:h-20 sm:w-20" />
                <span className="min-w-0 flex-1">
                  <span className="block font-display text-xl leading-tight text-ink-900 sm:text-2xl">{club.name}</span>
                  <span className="mt-2 flex flex-wrap gap-1.5 text-xs font-semibold">
                    <span className="rounded-full bg-ink-50 px-2.5 py-1 text-ink-700 ring-1 ring-ink-100">🥋 {t("staffClubs.athletes", { n: club.athletes })}</span>
                    <span className="rounded-full bg-ink-50 px-2.5 py-1 text-ink-700 ring-1 ring-ink-100">📚 {t("staffClubs.myCourses", { n: club.my_courses })}</span>
                    {club.home
                      ? <span className="rounded-full bg-brand-50 px-2.5 py-1 text-brand-700 ring-1 ring-brand-200">🏠 {t("staffClubs.homeClub")}</span>
                      : <span className="rounded-full bg-accent-50 px-2.5 py-1 text-accent-800 ring-1 ring-accent-200">🤝 {t("staffClubs.guest")}</span>}
                  </span>
                </span>
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-brand-500 text-2xl text-white shadow-brand transition-transform group-hover:translate-x-0.5" aria-hidden="true">
                  {entering === club.id ? <Spinner /> : "›"}
                </span>
              </motion.button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** In testata, in ogni scheda: il club in cui si sta lavorando e, per chi
 *  ne ha più d'uno, "Trocar de clube". */
export function StaffClubBar({ club, canSwitch, onSwitch }: { club: StaffClubOption; canSwitch: boolean; onSwitch: () => void }) {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-3 rounded-2xl bg-white px-3 py-2 shadow-soft ring-1 ring-ink-900/5">
      <ClubLogo club={club} className="h-10 w-10" />
      <span className="min-w-0 flex-1">
        <span className="block text-[10px] font-bold uppercase tracking-wider text-ink-400">{t("staffClubs.youAreIn")}</span>
        <span className="block truncate text-sm font-semibold text-ink-900">{club.name}</span>
      </span>
      {canSwitch && (
        <Button size="sm" variant="secondary" onClick={onSwitch} icon={<span aria-hidden="true">⇄</span>}>
          {t("staffClubs.switch")}
        </Button>
      )}
    </div>
  );
}
