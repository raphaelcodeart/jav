"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Textarea } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";

interface Consent {
  athlete_id: string;
  display_name: string;
  consent: boolean;
  consent_given_at: string | null;
  show_photo: boolean;
  bio: string | null;
  published: boolean;
}

/** Il consenso del genitore a mostrare il figlio sul sito pubblico
 *  JudoArteVida (docs/club-portal.md, "Sito pubblico"). Dice in chiaro cosa
 *  si vede e cosa no, la foto è una scelta a parte, e ritirare il consenso
 *  è un clic: l'atleta sparisce subito dal sito. */
export function PublicProfileConsent({ athleteId }: { athleteId: string }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = ["club", "athlete", athleteId, "public-profile"];
  const url = `/api/proxy/club/athletes/${athleteId}/public-profile`;
  const { data, isLoading } = useQuery({
    queryKey: key,
    queryFn: async (): Promise<Consent> => {
      const res = await fetch(url);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });
  const [busy, setBusy] = useState(false);
  // La bio in modifica: null finché il genitore non tocca il campo, così il
  // valore mostrato è quello del server senza copiarlo in un effetto.
  const [bioDraft, setBioDraft] = useState<string | null>(null);

  async function update(changes: Partial<Pick<Consent, "consent" | "show_photo" | "bio">>, okTitle: string) {
    setBusy(true);
    try {
      const res = await fetch(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes) });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      queryClient.setQueryData(key, await res.json());
      setBioDraft(null);
      toast({ tone: "success", title: okTitle });
    } catch (e) {
      toast({ tone: "error", title: t("site.consent.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  if (isLoading || !data) return <Skeleton className="h-40" />;
  const bio = bioDraft ?? data.bio ?? "";

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base text-ink-900">{t("site.consent.title")}</h3>
          <p className="mt-1 text-sm text-ink-500">{t("site.consent.intro")}</p>
        </div>
        {data.published ? (
          <Badge tone="success" dot>{t("site.consent.statusPublic")}</Badge>
        ) : data.consent ? (
          <Badge tone="info" dot>{t("site.consent.statusWaiting")}</Badge>
        ) : (
          <Badge tone="neutral">{t("site.consent.statusPrivate")}</Badge>
        )}
      </div>

      <div className="mt-4 grid gap-3 rounded-2xl bg-ink-50 p-4 text-sm sm:grid-cols-2">
        <div>
          <p className="font-semibold text-emerald-700">{t("site.consent.shownTitle")}</p>
          <p className="mt-1 text-ink-600">{t("site.consent.shown", { name: data.display_name })}</p>
        </div>
        <div>
          <p className="font-semibold text-rose-700">{t("site.consent.neverTitle")}</p>
          <p className="mt-1 text-ink-600">{t("site.consent.never")}</p>
        </div>
      </div>

      {data.consent ? (
        <div className="mt-5 space-y-4">
          <p className="text-sm text-ink-600">{t("site.consent.givenOn", { date: fmt.shortDate(data.consent_given_at) })}</p>
          <label className="flex cursor-pointer items-start gap-3 text-sm text-ink-800">
            <input
              type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 rounded border-ink-200 accent-brand-500"
              checked={data.show_photo} disabled={busy}
              onChange={(e) => update({ show_photo: e.target.checked }, e.target.checked ? t("site.consent.photoOn") : t("site.consent.photoOff"))}
            />
            <span>{t("site.consent.photo")}</span>
          </label>
          <Field label={t("site.consent.bio")} htmlFor={`bio-${athleteId}`} hint={t("site.consent.bioHint")}>
            <Textarea id={`bio-${athleteId}`} rows={2} maxLength={280} value={bio} onChange={(e) => setBioDraft(e.target.value)} />
          </Field>
          <div className="flex flex-wrap gap-2">
            {bioDraft !== null && (
              <Button size="sm" loading={busy} onClick={() => update({ bio }, t("site.consent.bioSaved"))}>{t("site.consent.saveBio")}</Button>
            )}
            <Button size="sm" variant="ghost" className="text-rose-600" disabled={busy} onClick={() => update({ consent: false }, t("site.consent.withdrawn"))}>
              {t("site.consent.withdraw")}
            </Button>
          </div>
          {!data.published && <p className="text-xs text-ink-500">{t("site.consent.waitingClub")}</p>}
        </div>
      ) : (
        <div className="mt-5">
          <Button loading={busy} onClick={() => update({ consent: true }, t("site.consent.given"))}>{t("site.consent.give")}</Button>
          <p className="mt-2 text-xs text-ink-500">{t("site.consent.revocable")}</p>
        </div>
      )}
    </Card>
  );
}
