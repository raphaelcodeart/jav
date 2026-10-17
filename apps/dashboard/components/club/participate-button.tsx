"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useState, type ReactNode } from "react";
import { PayModal } from "@/components/club/pay-modal";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { clubGet, clubSend, type Fee } from "@/lib/club";
import { feeLabel } from "@/lib/fee-label";
import { useI18n } from "@/lib/i18n/provider";

// «Quero participar» sulle schede degli eventi (sito e aree). Chi non è
// entrato va al login e torna qui; chi ha già qualcuno iscritto vede
// «Inscrito», spento. Il clic apre la finestra con gli atleti del conto: se
// ci sono quote scadute (non segnate «non bloccanti» dalla segreteria)
// spiega che con dei debiti non si va alle gare e offre di pagarle subito.
// Le regole stanno sul server (club/participation.py).

interface Mine { has_athletes: boolean; club_slug: string; registered: string[] }
interface AthleteState {
  athlete_id: string; name: string; photo_url: string | null;
  mode: "ENROLL" | "WISH";
  status: "REGISTERED" | "CAN" | "DEBTS" | "NO";
  reason: string | null;
  debts: Fee[]; debts_cents: number;
}
interface Participation {
  competition: { id: string; name: string; fee_cents: number; registration_deadline: string; status: string };
  athletes: AthleteState[];
}

/** Sul sito pubblico SiteShell sa (dal cookie, lato server) se si è entrati:
 *  senza sessione non si chiama il proxy, che risponderebbe «sessione scaduta»
 *  e porterebbe al login. Nelle aree si è sempre entrati (il default). */
const SignedIn = createContext(true);
export function SignedInProvider({ value, children }: { value: boolean; children: ReactNode }) {
  return <SignedIn.Provider value={value}>{children}</SignedIn.Provider>;
}

/** Le gare del mio conto già con un iscritto; null se non si è entrati (o
 *  l'account non è di un club). */
function useMine() {
  const signedIn = useContext(SignedIn);
  return useQuery({
    queryKey: ["club", "participation", "mine", signedIn],
    enabled: signedIn,
    queryFn: async (): Promise<Mine | null> => {
      try {
        return await clubGet<Mine>("/participation/mine");
      } catch {
        return null;
      }
    },
    staleTime: 30_000,
    retry: false,
  });
}

export function ParticipateButton({ competitionId, clubSlug, open, size = "sm", tone = "brand", className }: {
  competitionId: string;
  /** Il club dell'evento (null = rete): agli eventi degli altri club non ci si iscrive. */
  clubSlug: string | null;
  /** Iscrizioni aperte: senza, il bottone si vede solo come «Inscrito». */
  open: boolean;
  size?: "sm" | "lg";
  /** "light": bianco, su un riquadro colorato. */
  tone?: "brand" | "light";
  className?: string;
}) {
  const { t } = useI18n();
  const pathname = usePathname();
  const signedIn = useContext(SignedIn);
  const { data, isPending } = useMine();
  const mine = signedIn ? data : null;
  const [show, setShow] = useState(false);
  const registered = !!mine?.registered.includes(competitionId);
  const base = cn("relative z-10 inline-flex items-center justify-center gap-1.5 font-semibold transition",
    size === "sm" ? "h-8 rounded-full px-3 text-xs" : "h-12 w-full rounded-2xl px-5 text-base", className);

  if (signedIn && isPending) return null;
  if (registered) {
    return (
      <span aria-disabled="true" className={cn(base, "cursor-default bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200")}>
        ✓ {t("part.registered")}
      </span>
    );
  }
  // Entrato ma senza un club (o senza atleti), o evento di un altro club: niente bottone.
  if (!open || (signedIn && (!mine || !mine.has_athletes || (clubSlug && clubSlug !== mine.club_slug)))) return null;
  const look = tone === "light"
    ? "bg-white text-ink-900 shadow-soft hover:bg-accent-50"
    : "bg-brand-600 text-white shadow-soft hover:bg-brand-700";
  if (!mine) {
    return (
      <Link href={`/login?next=${encodeURIComponent(pathname || "/eventos")}`} className={cn(base, look)}>
        🥋 {t("part.want")}
      </Link>
    );
  }
  return (
    <>
      <button type="button" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setShow(true); }} className={cn(base, look)}>
        🥋 {t("part.want")}
      </button>
      {show && <ParticipateModal competitionId={competitionId} onClose={() => setShow(false)} />}
    </>
  );
}

function ParticipateModal({ competitionId, onClose }: { competitionId: string; onClose: () => void }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [paying, setPaying] = useState<Fee[] | null>(null);
  const { data, isPending, error } = useQuery({
    queryKey: ["club", "participation", competitionId],
    queryFn: () => clubGet<Participation>(`/participation/${competitionId}`),
  });

  async function go(a: AthleteState) {
    setBusy(a.athlete_id);
    try {
      const res = await clubSend<{ result: string }>(`/participation/${competitionId}`, "POST", { athlete_id: a.athlete_id });
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({
        tone: "success",
        title: res.result === "REGISTERED" ? t("part.done", { name: a.name }) : res.result === "WISH_SENT" ? t("part.wishSent") : t("part.wishAlready"),
      });
      if (res.result === "REGISTERED" && data && data.athletes.filter((x) => x.status === "CAN").length <= 1) onClose();
    } catch (e) {
      toast({ tone: "error", title: t("common.failed"), text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  if (paying) return <PayModal open onClose={() => { setPaying(null); void queryClient.invalidateQueries({ queryKey: ["club", "participation"] }); }} fees={paying} preselect={paying.map((f) => f.id)} />;

  const comp = data?.competition;
  return (
    <Modal open onClose={onClose} title={t("part.title")} subtitle={comp?.name}
      footer={<Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>}>
      {isPending && <p className="py-6 text-center text-sm text-ink-500">{t("part.loading")}</p>}
      {error && <p className="rounded-2xl bg-rose-50 p-4 text-sm text-rose-800">{(error as Error).message}</p>}
      {data && (
        <div className="space-y-3">
          {comp && (
            <p className="flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-ink-50 px-2.5 py-1 font-semibold text-ink-700 ring-1 ring-ink-200">⏳ {t("part.deadline", { date: fmt.shortDate(comp.registration_deadline) })}</span>
              {comp.fee_cents > 0 && <span className="rounded-full bg-brand-50 px-2.5 py-1 font-semibold text-brand-800 ring-1 ring-brand-200">💶 {t("part.fee", { amount: fmt.euro(comp.fee_cents) })}</span>}
            </p>
          )}
          {data.athletes.length === 0 && <p className="rounded-2xl bg-ink-50 p-4 text-sm text-ink-600">{t("part.noAthletes")}</p>}
          {data.athletes.map((a) => (
            <AthleteCard key={a.athlete_id} a={a} busy={busy === a.athlete_id} onGo={() => go(a)} onPay={() => setPaying(a.debts)} />
          ))}
        </div>
      )}
    </Modal>
  );
}

function AthleteCard({ a, busy, onGo, onPay }: { a: AthleteState; busy: boolean; onGo: () => void; onPay: () => void }) {
  const { t, fmt } = useI18n();
  return (
    <div className={cn("rounded-3xl p-4 ring-1",
      a.status === "DEBTS" ? "bg-rose-50/70 ring-rose-200" : a.status === "REGISTERED" ? "bg-emerald-50/70 ring-emerald-200" : "bg-white ring-ink-900/10")}>
      <div className="flex items-center gap-3">
        {a.photo_url
          // eslint-disable-next-line @next/next/no-img-element
          ? <img src={a.photo_url} alt="" className="h-11 w-11 shrink-0 rounded-2xl object-cover" />
          : <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-brand-100 font-display text-lg text-brand-800" aria-hidden="true">{a.name.slice(0, 1)}</span>}
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-ink-900">{a.name}</p>
          <p className="text-xs text-ink-500">
            {a.status === "REGISTERED" ? `✓ ${t("part.registered")}` : a.status === "CAN" ? (a.mode === "ENROLL" ? t("part.canEnroll") : t("part.canWish"))
              : a.status === "DEBTS" ? t("part.blocked") : a.reason}
          </p>
        </div>
        {a.status === "CAN" && (
          <Button size="sm" loading={busy} onClick={onGo}>{a.mode === "ENROLL" ? t("part.enroll") : t("part.ask")}</Button>
        )}
        {a.status === "REGISTERED" && <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-800">✓</span>}
      </div>
      {a.status === "DEBTS" && (
        <div className="mt-3 space-y-3">
          <p className="text-sm leading-relaxed text-rose-900">⚠️ {t("part.debtsExplain")}</p>
          <ul className="divide-y divide-rose-100 overflow-hidden rounded-2xl bg-white ring-1 ring-rose-100">
            {a.debts.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="block truncate font-medium text-ink-800">{feeLabel(f, t, fmt)}</span>
                  <span className="text-xs text-rose-700">{t("part.dueSince", { date: fmt.shortDate(f.due_date) })}</span>
                </span>
                <span className="shrink-0 font-semibold tabular-nums text-ink-900">{fmt.euro(f.amount_cents)}</span>
              </li>
            ))}
            <li className="flex items-center justify-between bg-rose-50 px-3 py-2 text-sm font-bold text-rose-900">
              <span>{t("part.total")}</span><span className="tabular-nums">{fmt.euro(a.debts_cents)}</span>
            </li>
          </ul>
          {a.mode === "ENROLL"
            ? <Button className="w-full" onClick={onPay}>💳 {t("part.payNow")}</Button>
            : <p className="rounded-2xl bg-white px-3 py-2 text-xs text-ink-600 ring-1 ring-rose-100">{t("part.askHolderToPay")}</p>}
          <p className="text-xs text-ink-500">{t("part.talkToClub")}</p>
        </div>
      )}
    </div>
  );
}
