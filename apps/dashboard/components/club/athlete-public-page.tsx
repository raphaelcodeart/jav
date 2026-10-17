"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useClubFeatures } from "@/components/club/jav-courses";
import { clubGet, clubSend } from "@/lib/club";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import { useThirdPartyAllowed } from "@/lib/cookie-consent";
import { ThirdPartyGate } from "@/components/legal/cookie-banner";

// La scheda pubblica di un atleta, per la segreteria (docs/club-portal.md,
// "Sito pubblico" → "La scheda del judoca"): profilo IJF, due righe,
// tecnica e guardia, e le foto e i video, ognuno pubblicato a parte. Il
// consenso resta della famiglia: qui si può preparare tutto, ma sul sito
// non esce niente senza consenso e pubblicazione, e foto e video solo con
// il permesso della foto.

interface Media {
  id: string;
  kind: "PHOTO" | "VIDEO";
  url: string | null;
  youtube_id: string | null;
  caption: string | null;
  published: boolean;
  created_at: string;
}

interface AthletePage {
  athlete_id: string;
  display_name: string;
  photo_url: string | null;
  consent: boolean;
  show_photo: boolean;
  published: boolean;
  live: boolean;
  public_path: string;
  bio: string | null;
  ijf_profile_url: string | null;
  favorite_technique: string | null;
  dominant_side: "LEFT" | "RIGHT" | null;
  media: Media[];
  max_photos: number;
  max_videos: number;
}

const path = (athleteId: string, rest = "") => `/admin/site/athletes/${athleteId}/page${rest}`;

/** La sezione "Pagina pubblica" nella scheda dell'atleta. Nell'unità dei
 *  corsi JAV non esiste: lo dice in una riga, invece di sparire senza
 *  spiegazione. */
export function AthletePublicPageSection({ athleteId }: { athleteId: string }) {
  const { t } = useI18n();
  const features = useClubFeatures();
  const [open, setOpen] = useState(false);
  if (features.courses) {
    return <p className="rounded-2xl bg-ink-50 p-4 text-sm text-ink-600">{t("athletePage.coursesNever")}</p>;
  }
  return (
    <div className="rounded-2xl ring-1 ring-ink-200 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-ink-900">{t("athletePage.title")}</p>
          <p className="text-xs text-ink-500">{t("athletePage.subtitle")}</p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? t("athletePage.close") : t("athletePage.open")}
        </Button>
      </div>
      {open && <div className="mt-4"><AthletePublicPageEditor athleteId={athleteId} /></div>}
    </div>
  );
}

export function AthletePublicPageEditor({ athleteId }: { athleteId: string }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const key = ["club", "site", "athlete-page", athleteId];
  const { data, isLoading, error } = useQuery({ queryKey: key, queryFn: () => clubGet<AthletePage>(path(athleteId)) });
  const store = (page: AthletePage) => {
    queryClient.setQueryData(key, page);
    // L'elenco "Judoka sul sito" mostra lo stesso stato.
    void queryClient.invalidateQueries({ queryKey: ["club", "site", "athletes"] });
  };

  if (isLoading) return <Skeleton className="h-48" />;
  if (error || !data) return <p className="text-sm text-rose-600">{(error as Error | null)?.message ?? t("athletePage.loadFailed")}</p>;

  const photos = data.media.filter((m) => m.kind === "PHOTO");
  const videos = data.media.filter((m) => m.kind === "VIDEO");
  return (
    <div className="space-y-5">
      <Status page={data} />
      {/* La chiave riparte dai valori del server dopo ogni salvataggio: lo
          stato iniziale si legge al montaggio, non si copia con un effetto. */}
      <TextsForm key={[data.ijf_profile_url, data.bio, data.favorite_technique, data.dominant_side].join("|")} page={data} onSaved={store} />
      <PhotosBlock page={data} photos={photos} onChange={store} />
      <VideosBlock page={data} videos={videos} onChange={store} />
    </div>
  );
}

function Status({ page }: { page: AthletePage }) {
  const { t } = useI18n();
  const reason = !page.consent
    ? t("athletePage.whyNoConsent")
    : !page.published
      ? t("athletePage.whyNotPublished")
      : t("athletePage.whyClubHidden");
  return (
    <div className={cn("rounded-2xl p-4 text-sm", page.live ? "bg-emerald-50 text-emerald-900" : "bg-amber-50 text-amber-900")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {page.live ? <Badge tone="success" dot>{t("athletePage.live")}</Badge> : <Badge tone="warning" dot>{t("athletePage.notLive")}</Badge>}
        </div>
        {page.live && (
          <a href={page.public_path} target="_blank" rel="noopener noreferrer" className="font-semibold underline underline-offset-2 hover:text-brand-700">
            {t("athletePage.preview")} ↗
          </a>
        )}
      </div>
      {!page.live && <p className="mt-2">{reason}</p>}
      {page.consent && !page.show_photo && <p className="mt-2">{t("athletePage.noPhotoPermission")}</p>}
    </div>
  );
}

function useSaver(onDone: (page: AthletePage) => void) {
  const { t } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  async function run(call: () => Promise<AthletePage>, okTitle?: string) {
    setBusy(true);
    try {
      onDone(await call());
      if (okTitle) toast({ tone: "success", title: okTitle });
      return true;
    } catch (e) {
      toast({ tone: "error", title: t("athletePage.saveFailed"), text: (e as Error).message });
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, run };
}

function TextsForm({ page, onSaved }: { page: AthletePage; onSaved: (page: AthletePage) => void }) {
  const { t } = useI18n();
  const [ijf, setIjf] = useState(page.ijf_profile_url ?? "");
  const [bio, setBio] = useState(page.bio ?? "");
  const [technique, setTechnique] = useState(page.favorite_technique ?? "");
  const [side, setSide] = useState<string>(page.dominant_side ?? "");
  const { busy, run } = useSaver(onSaved);
  const id = page.athlete_id;
  return (
    <div className="space-y-3">
      <Field label={t("athletePage.ijf")} htmlFor={`ijf-${id}`} hint={t("athletePage.ijfHint")}>
        <Input id={`ijf-${id}`} type="url" inputMode="url" maxLength={300} placeholder="https://www.ijf.org/judoka/..." value={ijf} onChange={(e) => setIjf(e.target.value)} />
      </Field>
      <Field label={t("athletePage.bio")} htmlFor={`bio-adm-${id}`} hint={t("athletePage.bioHint")}>
        <Textarea id={`bio-adm-${id}`} rows={6} maxLength={1500} value={bio} onChange={(e) => setBio(e.target.value)} />
        <p className="mt-1 text-right text-[11px] text-ink-400 tabular-nums">{bio.length}/1500</p>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("athletePage.technique")} htmlFor={`tech-${id}`}>
          <Input id={`tech-${id}`} maxLength={80} placeholder={t("athletePage.techniquePlaceholder")} value={technique} onChange={(e) => setTechnique(e.target.value)} />
        </Field>
        <Field label={t("athletePage.side")} htmlFor={`side-${id}`}>
          <Select id={`side-${id}`} value={side} onChange={(e) => setSide(e.target.value)}>
            <option value="">{t("athletePage.sideNone")}</option>
            <option value="RIGHT">{t("site.judoka.side.RIGHT")}</option>
            <option value="LEFT">{t("site.judoka.side.LEFT")}</option>
          </Select>
        </Field>
      </div>
      <div className="flex justify-end">
        <Button
          size="sm" loading={busy}
          onClick={() => run(
            () => clubSend<AthletePage>(path(id), "PUT", {
              ijf_profile_url: ijf.trim(), bio: bio.trim(), favorite_technique: technique.trim(), dominant_side: side,
            }),
            t("athletePage.saved"),
          )}
        >
          {t("athletePage.saveTexts")}
        </Button>
      </div>
    </div>
  );
}

function PublishToggle({ media, athleteId, onChange }: { media: Media; athleteId: string; onChange: (page: AthletePage) => void }) {
  const { t } = useI18n();
  const { busy, run } = useSaver(onChange);
  return (
    <div className="flex items-center justify-between gap-2">
      {media.published ? <Badge tone="success" dot>{t("athletePage.mediaLive")}</Badge> : <Badge tone="neutral">{t("athletePage.mediaDraft")}</Badge>}
      <div className="flex gap-1">
        <Button
          size="sm" variant={media.published ? "ghost" : "primary"} loading={busy}
          onClick={() => run(() => clubSend<AthletePage>(path(athleteId, `/media/${media.id}`), "PATCH", { published: !media.published }))}
        >
          {media.published ? t("athletePage.unpublish") : t("athletePage.publish")}
        </Button>
        <Button
          size="sm" variant="ghost" className="text-rose-600" disabled={busy}
          onClick={() => window.confirm(t("athletePage.removeConfirm")) && run(() => clubSend<AthletePage>(path(athleteId, `/media/${media.id}`), "DELETE"))}
        >
          {t("athletePage.remove")}
        </Button>
      </div>
    </div>
  );
}

function PhotosBlock({ page, photos, onChange }: { page: AthletePage; photos: Media[]; onChange: (page: AthletePage) => void }) {
  const { t } = useI18n();
  const ref = useRef<HTMLInputElement>(null);
  const { busy, run } = useSaver(onChange);
  const full = photos.length >= page.max_photos;
  async function upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    await run(() => clubSend<AthletePage>(path(page.athlete_id, "/photos"), "POST", form), t("athletePage.photoAdded"));
  }
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-ink-800">
          {t("athletePage.photos")} <span className="font-normal text-ink-500">({photos.length}/{page.max_photos})</span>
        </p>
        <input
          ref={ref} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" aria-hidden="true" tabIndex={-1}
          onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; if (file) void upload(file); }}
        />
        <Button size="sm" variant="secondary" loading={busy} disabled={full} onClick={() => ref.current?.click()}>{t("athletePage.addPhoto")}</Button>
      </div>
      <p className="mb-3 text-xs text-ink-500">{t("athletePage.photosHint")}</p>
      {photos.length === 0 ? (
        <p className="rounded-xl border border-dashed border-ink-200 p-4 text-center text-sm text-ink-500">{t("athletePage.photosEmpty")}</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {photos.map((m) => (
            <li key={m.id} className="rounded-2xl border border-ink-900/10 bg-white p-2">
              {/* eslint-disable-next-line @next/next/no-img-element -- foto caricata dal club */}
              <img src={m.url ?? ""} alt="" className="aspect-video w-full rounded-xl object-cover" />
              <div className="mt-2"><PublishToggle media={m} athleteId={page.athlete_id} onChange={onChange} /></div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function VideosBlock({ page, videos, onChange }: { page: AthletePage; videos: Media[]; onChange: (page: AthletePage) => void }) {
  const { t } = useI18n();
  const thirdParty = useThirdPartyAllowed();
  const [url, setUrl] = useState("");
  const [caption, setCaption] = useState("");
  const { busy, run } = useSaver(onChange);
  const full = videos.length >= page.max_videos;
  async function add() {
    const ok = await run(
      () => clubSend<AthletePage>(path(page.athlete_id, "/videos"), "POST", { url: url.trim(), caption: caption.trim() || null }),
      t("athletePage.videoAdded"),
    );
    if (ok) { setUrl(""); setCaption(""); }
  }
  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-ink-800">
        {t("athletePage.videos")} <span className="font-normal text-ink-500">({videos.length}/{page.max_videos})</span>
      </p>
      <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Field label={t("athletePage.videoUrl")} htmlFor={`yt-${page.athlete_id}`} hint={t("athletePage.videoHint")}>
          <Input id={`yt-${page.athlete_id}`} type="url" inputMode="url" maxLength={300} placeholder="https://youtu.be/..." value={url} onChange={(e) => setUrl(e.target.value)} />
        </Field>
        <Field label={t("athletePage.videoCaption")} htmlFor={`ytc-${page.athlete_id}`}>
          <Input id={`ytc-${page.athlete_id}`} maxLength={200} value={caption} onChange={(e) => setCaption(e.target.value)} />
        </Field>
        <Button size="sm" loading={busy} disabled={full || !url.trim()} onClick={add} className="sm:mb-6">{t("athletePage.addVideo")}</Button>
      </div>
      {videos.length > 0 && (
        <ul className="mt-3 grid gap-3 sm:grid-cols-2">
          {videos.map((m) => (
            <li key={m.id} className="rounded-2xl border border-ink-900/10 bg-white p-2">
              {thirdParty ? (
                // eslint-disable-next-line @next/next/no-img-element -- copertina servita da YouTube
                <img src={`https://i.ytimg.com/vi/${m.youtube_id}/hqdefault.jpg`} alt="" className="aspect-video w-full rounded-xl object-cover" />
              ) : <ThirdPartyGate provider="YouTube" className="aspect-video w-full rounded-xl" />}
              {m.caption && <p className="mt-1 truncate text-xs font-semibold text-ink-700">{m.caption}</p>}
              <div className="mt-2"><PublishToggle media={m} athleteId={page.athlete_id} onChange={onChange} /></div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
