"use client";

import { useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { BeltBadge } from "@/components/ui/belt";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { AthletePublicPageEditor } from "@/components/club/athlete-public-page";
import { useClubFeatures } from "@/components/club/jav-courses";
import { friendlyApiError } from "@/lib/api-error";
import { brandTheme, contrast, normalizeHex, themeStyle } from "@/lib/brand";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// L'editor della pagina pubblica del club (docs/club-portal.md, "Sito
// pubblico"). La segreteria scrive testi, carica foto, mette contatti e
// social, decide quando pubblicare e quali atleti (con il consenso della
// famiglia) compaiono. Orari, eventi e risultati non si scrivono qui:
// arrivano da soli dal gestionale.

const BASE = "/api/proxy/club/admin/site";

interface GalleryItem { url: string; caption: string | null }
interface Coach { name: string; role: string | null; photo_url: string | null; grade?: string | null; bio?: string | null }
interface Highlight { value: string; label: string }
interface HistoryStep { year: number | string; title: string; text: string | null }
interface Pillar { title: string; text: string | null }
interface NewsPost { date: string; title: string; text: string | null; image_url: string | null; link_url: string | null }
/** Nell'editor un video è il link che si incolla; l'API salva solo l'id. */
interface VideoRow { url: string; caption: string | null }

interface SiteAdmin {
  name: string;
  slug: string;
  published: boolean;
  /** I prezzi dei piani si possono dire sul sito (JAVBOT). */
  show_prices: boolean;
  updated_at: string;
  tagline: string | null;
  about: string | null;
  city: string | null;
  hero_image_url: string | null;
  logo_url: string | null;
  gallery: GalleryItem[];
  coaches: Coach[];
  contact_phone: string | null;
  contact_email: string | null;
  address: string | null;
  map_url: string | null;
  instagram_url: string | null;
  facebook_url: string | null;
  youtube_url: string | null;
  tiktok_url?: string | null;
  website_url: string | null;
  brand_primary: string | null;
  brand_secondary: string | null;
  brand_accent: string | null;
  founded_year: number | null;
  venue: string | null;
  highlights: Highlight[];
  history: HistoryStep[];
  pillars: Pillar[];
  news: NewsPost[];
  videos: { youtube_id: string; caption: string | null }[];
}

const BRAND_KEYS = ["brand_primary", "brand_secondary", "brand_accent"] as const;
type BrandKey = (typeof BRAND_KEYS)[number];

interface AthleteStatus {
  athlete_id: string;
  first_name: string;
  last_name: string;
  display_name: string;
  photo_url: string | null;
  belt: string | null;
  consent: boolean;
  consent_given_at: string | null;
  show_photo: boolean;
  published: boolean;
}

const TEXT_KEYS = [
  "tagline", "city", "venue", "about", "contact_phone", "contact_email", "address", "map_url",
  "instagram_url", "facebook_url", "youtube_url", "tiktok_url", "website_url",
] as const;
type TextKey = (typeof TEXT_KEYS)[number];

async function send<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

async function uploadImage(slot: "hero" | "logo" | "gallery" | "coach" | "news", file: File): Promise<{ url: string; site: SiteAdmin }> {
  const form = new FormData();
  form.append("slot", slot);
  form.append("file", file);
  return send("/images", { method: "POST", body: form });
}

/** La pagina pubblica del club, per la segreteria. Si monta da sola: legge
 *  e scrive tutto attraverso il proxy BFF. */
export function ClubSiteEditor() {
  const { t } = useI18n();
  const { data, isLoading, error } = useQuery({
    queryKey: ["club", "site"],
    queryFn: async (): Promise<SiteAdmin> => {
      const res = await fetch(BASE);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });

  if (isLoading) return <Skeleton className="h-96" />;
  if (error || !data) return <EmptyState title={t("siteEditor.loadFailed")} text={(error as Error | null)?.message} />;
  return (
    <div className="space-y-6">
      {/* La chiave azzera il modulo quando la pagina cambia sul server (dopo
          un salvataggio): i valori iniziali si leggono al montaggio, non si
          sincronizzano con un effetto. */}
      <SiteForm key={data.updated_at} site={data} />
      <AthletesCard />
    </div>
  );
}

function SiteForm({ site }: { site: SiteAdmin }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [text, setText] = useState<Record<TextKey, string>>(
    () => Object.fromEntries(TEXT_KEYS.map((k) => [k, site[k] ?? ""])) as Record<TextKey, string>,
  );
  const [hero, setHero] = useState(site.hero_image_url);
  const [logo, setLogo] = useState(site.logo_url);
  const [gallery, setGallery] = useState<GalleryItem[]>(site.gallery);
  const [coaches, setCoaches] = useState<Coach[]>(site.coaches);
  const [foundedYear, setFoundedYear] = useState(site.founded_year ? String(site.founded_year) : "");
  const [highlights, setHighlights] = useState<Highlight[]>(site.highlights ?? []);
  const [history, setHistory] = useState<HistoryStep[]>(site.history ?? []);
  const [pillars, setPillars] = useState<Pillar[]>(site.pillars ?? []);
  const [news, setNews] = useState<NewsPost[]>(site.news ?? []);
  const [videos, setVideos] = useState<VideoRow[]>(
    () => (site.videos ?? []).map((v) => ({ url: `https://www.youtube.com/watch?v=${v.youtube_id}`, caption: v.caption })),
  );
  const [colors, setColors] = useState<Record<BrandKey, string>>(
    () => Object.fromEntries(BRAND_KEYS.map((k) => [k, site[k] ?? ""])) as Record<BrandKey, string>,
  );
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [savingPrices, setSavingPrices] = useState(false);
  const [dirty, setDirty] = useState(false);

  const publicUrl = `/clubes/${site.slug}`;
  const set = (key: TextKey) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setText((prev) => ({ ...prev, [key]: e.target.value }));
    setDirty(true);
  };

  async function save() {
    setSaving(true);
    try {
      const saved = await send<SiteAdmin>("", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...Object.fromEntries(TEXT_KEYS.map((k) => [k, text[k].trim() || null])),
          hero_image_url: hero, logo_url: logo, gallery, coaches: coaches.filter((c) => c.name.trim()),
          founded_year: foundedYear.trim() ? Number(foundedYear) : null,
          highlights: highlights.filter((h) => h.value.trim() && h.label.trim()),
          history: history.filter((h) => String(h.year).trim() && h.title.trim()).map((h) => ({ ...h, year: Number(h.year) })),
          pillars: pillars.filter((p) => p.title.trim()),
          news: news.filter((n) => n.date && n.title.trim()),
          videos: videos.filter((v) => v.url.trim()),
          ...Object.fromEntries(BRAND_KEYS.map((k) => [k, colors[k].trim() || null])),
        }),
      });
      queryClient.setQueryData(["club", "site"], saved);
      toast({ tone: "success", title: t("siteEditor.saved"), text: saved.published ? t("siteEditor.savedLive") : t("siteEditor.savedDraft") });
    } catch (e) {
      toast({ tone: "error", title: t("siteEditor.saveFailed"), text: (e as Error).message });
    } finally {
      setSaving(false);
    }
  }

  async function togglePublished() {
    if (dirty) await save();
    setPublishing(true);
    try {
      const saved = await send<SiteAdmin>("/publish", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ published: !site.published }),
      });
      queryClient.setQueryData(["club", "site"], saved);
      toast({ tone: saved.published ? "success" : "info", title: saved.published ? t("siteEditor.publishedToast") : t("siteEditor.unpublishedToast") });
    } catch (e) {
      toast({ tone: "error", title: t("siteEditor.saveFailed"), text: (e as Error).message });
    } finally {
      setPublishing(false);
    }
  }

  // Una scelta a sé, salvata subito: non aspetta "Salva" e non porta con sé
  // i testi ancora in modifica.
  async function toggleShowPrices() {
    setSavingPrices(true);
    try {
      const saved = await send<SiteAdmin>("", {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ show_prices: !site.show_prices }),
      });
      queryClient.setQueryData(["club", "site"], saved);
      toast({ tone: "success", title: saved.show_prices ? t("siteEditor.showPricesOn") : t("siteEditor.showPricesOff") });
    } catch (e) {
      toast({ tone: "error", title: t("siteEditor.saveFailed"), text: (e as Error).message });
    } finally {
      setSavingPrices(false);
    }
  }

  function moveGallery(i: number, delta: number) {
    setGallery((items) => {
      const next = [...items];
      const j = i + delta;
      if (j < 0 || j >= next.length) return items;
      [next[i], next[j]] = [next[j] as GalleryItem, next[i] as GalleryItem];
      return next;
    });
    setDirty(true);
  }

  return (
    <>
      {/* --- Stato della pagina --- */}
      <Card className={cn(site.published ? "ring-1 ring-emerald-200" : "ring-1 ring-amber-200")}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base text-ink-900">{t("siteEditor.title")}</h3>
              {site.published ? <Badge tone="success" dot>{t("siteEditor.statusLive")}</Badge> : <Badge tone="warning" dot>{t("siteEditor.statusDraft")}</Badge>}
            </div>
            <p className="mt-1 max-w-xl text-sm text-ink-500">{site.published ? t("siteEditor.liveText") : t("siteEditor.draftText")}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {site.published && (
              <a href={publicUrl} target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center rounded-xl border border-ink-200 bg-white px-4 text-sm font-semibold text-ink-900 shadow-soft hover:border-brand-300 hover:text-brand-700">
                {t("siteEditor.viewPublic")}
              </a>
            )}
            <Button variant={site.published ? "secondary" : "primary"} loading={publishing} onClick={togglePublished}>
              {site.published ? t("siteEditor.unpublish") : t("siteEditor.publish")}
            </Button>
          </div>
        </div>
        <label className="mt-4 flex cursor-pointer items-start gap-3 border-t border-ink-100 pt-4">
          <input
            type="checkbox"
            className="mt-0.5 h-5 w-5 shrink-0 cursor-pointer accent-brand-500"
            checked={site.show_prices}
            disabled={savingPrices}
            onChange={toggleShowPrices}
          />
          <span>
            <span className="block text-sm font-semibold text-ink-900">{t("siteEditor.showPrices")}</span>
            <span className="block text-xs text-ink-500">{t("siteEditor.showPricesHint")}</span>
          </span>
        </label>
      </Card>

      {/* --- Testi --- */}
      <Card>
        <CardHeader title={t("siteEditor.textsTitle")} subtitle={t("siteEditor.textsHint")} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("siteEditor.tagline")} htmlFor="site-tagline" hint={t("siteEditor.taglineHint")}>
            <Input id="site-tagline" maxLength={200} value={text.tagline} onChange={set("tagline")} />
          </Field>
          <Field label={t("siteEditor.city")} htmlFor="site-city">
            <Input id="site-city" maxLength={120} value={text.city} onChange={set("city")} />
          </Field>
          <Field label={t("siteEditor.venue")} htmlFor="site-venue" hint={t("siteEditor.venueHint")}>
            <Input id="site-venue" maxLength={160} value={text.venue} onChange={set("venue")} />
          </Field>
          <Field label={t("siteEditor.foundedYear")} htmlFor="site-founded" hint={t("siteEditor.foundedYearHint")}>
            <Input id="site-founded" type="number" inputMode="numeric" min={1882} max={2100} value={foundedYear}
              onChange={(e) => { setFoundedYear(e.target.value); setDirty(true); }} />
          </Field>
          <div className="sm:col-span-2">
            <Field label={t("siteEditor.about")} htmlFor="site-about" hint={t("siteEditor.aboutHint")}>
              <Textarea id="site-about" rows={8} maxLength={8000} value={text.about} onChange={set("about")} />
            </Field>
          </div>
        </div>
      </Card>

      {/* --- Foto --- */}
      <Card>
        <CardHeader title={t("siteEditor.photosTitle")} subtitle={t("siteEditor.photosHint")} />
        <div className="grid gap-6 sm:grid-cols-[2fr_1fr]">
          <ImageSlot
            label={t("siteEditor.hero")} hint={t("siteEditor.heroHint")} url={hero} wide
            onUpload={async (file) => { const r = await uploadImage("hero", file); setHero(r.url); }}
            onRemove={() => { setHero(null); setDirty(true); }}
          />
          <ImageSlot
            label={t("siteEditor.logo")} hint={t("siteEditor.logoHint")} url={logo}
            onUpload={async (file) => { const r = await uploadImage("logo", file); setLogo(r.url); }}
            onRemove={() => { setLogo(null); setDirty(true); }}
          />
        </div>

        <div className="mt-8">
          <div className="mb-3 flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-ink-800">{t("siteEditor.gallery")} <span className="font-normal text-ink-500">({gallery.length}/24)</span></p>
            <UploadButton
              label={t("siteEditor.addPhoto")} disabled={gallery.length >= 24}
              onFile={async (file) => {
                const r = await uploadImage("gallery", file);
                // Solo la foto nuova: le didascalie non ancora salvate restano.
                setGallery((items) => [...items, { url: r.url, caption: null }]);
              }}
            />
          </div>
          {gallery.length === 0 ? (
            <p className="rounded-xl border border-dashed border-ink-200 p-6 text-center text-sm text-ink-500">{t("siteEditor.galleryEmpty")}</p>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {gallery.map((item, i) => (
                <li key={item.url} className="rounded-2xl border border-ink-900/10 bg-white p-2">
                  {/* eslint-disable-next-line @next/next/no-img-element -- foto caricata dal club */}
                  <img src={item.url} alt="" className="aspect-video w-full rounded-xl object-cover" />
                  <Input
                    className="mt-2 h-9" placeholder={t("siteEditor.caption")} aria-label={t("siteEditor.caption")} maxLength={200}
                    value={item.caption ?? ""}
                    onChange={(e) => {
                      const caption = e.target.value;
                      setGallery((items) => items.map((g, j) => (j === i ? { ...g, caption: caption || null } : g)));
                      setDirty(true);
                    }}
                  />
                  <div className="mt-2 flex justify-between">
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => moveGallery(i, -1)} aria-label={t("siteEditor.moveUp")}>↑</Button>
                      <Button size="sm" variant="ghost" disabled={i === gallery.length - 1} onClick={() => moveGallery(i, 1)} aria-label={t("siteEditor.moveDown")}>↓</Button>
                    </div>
                    <Button size="sm" variant="ghost" className="text-rose-600" onClick={() => { setGallery((items) => items.filter((_, j) => j !== i)); setDirty(true); }}>
                      {t("siteEditor.remove")}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      {/* --- Colori del club, con l'anteprima della copertina --- */}
      <BrandCard
        site={site} hero={hero} logo={logo} colors={colors}
        onChange={(key, value) => { setColors((c) => ({ ...c, [key]: value })); setDirty(true); }}
        onReset={() => { setColors({ brand_primary: "", brand_secondary: "", brand_accent: "" }); setDirty(true); }}
      />

      {/* --- Allenatori --- */}
      <Card>
        <CardHeader
          title={t("siteEditor.coachesTitle")} subtitle={t("siteEditor.coachesHint")}
          action={<Button size="sm" variant="secondary" disabled={coaches.length >= 12} onClick={() => { setCoaches((c) => [...c, { name: "", role: null, photo_url: null }]); setDirty(true); }}>{t("siteEditor.addCoach")}</Button>}
        />
        {coaches.length === 0 ? (
          <p className="text-sm text-ink-500">{t("siteEditor.coachesEmpty")}</p>
        ) : (
          <ul className="space-y-3">
            {coaches.map((coach, i) => {
              const update = (patch: Partial<Coach>) => { setCoaches((list) => list.map((c, j) => (j === i ? { ...c, ...patch } : c))); setDirty(true); };
              return (
                <li key={i} className="flex flex-col gap-3 rounded-2xl border border-ink-900/10 bg-white p-3 sm:flex-row sm:items-end">
                  <ImageSlot
                    label={t("siteEditor.coachPhoto")} url={coach.photo_url} compact
                    onUpload={async (file) => { const r = await uploadImage("coach", file); update({ photo_url: r.url }); }}
                    onRemove={() => update({ photo_url: null })}
                  />
                  <div className="grid flex-1 gap-3 sm:grid-cols-2">
                    <Field label={t("siteEditor.coachName")} htmlFor={`coach-name-${i}`}>
                      <Input id={`coach-name-${i}`} maxLength={120} value={coach.name} onChange={(e) => update({ name: e.target.value })} />
                    </Field>
                    <Field label={t("siteEditor.coachRole")} htmlFor={`coach-role-${i}`}>
                      <Input id={`coach-role-${i}`} maxLength={120} placeholder={t("siteEditor.coachRolePlaceholder")} value={coach.role ?? ""} onChange={(e) => update({ role: e.target.value || null })} />
                    </Field>
                    <Field label={t("siteEditor.coachGrade")} htmlFor={`coach-grade-${i}`}>
                      <Input id={`coach-grade-${i}`} maxLength={60} placeholder={t("siteEditor.coachGradePlaceholder")} value={coach.grade ?? ""} onChange={(e) => update({ grade: e.target.value || null })} />
                    </Field>
                    <Field label={t("siteEditor.coachBio")} htmlFor={`coach-bio-${i}`}>
                      <Input id={`coach-bio-${i}`} maxLength={400} value={coach.bio ?? ""} onChange={(e) => update({ bio: e.target.value || null })} />
                    </Field>
                  </div>
                  <Button size="sm" variant="ghost" className="text-rose-600" onClick={() => { setCoaches((list) => list.filter((_, j) => j !== i)); setDirty(true); }}>
                    {t("siteEditor.remove")}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {/* --- Il mini-sito: numeri, punti di forza, storia, novità, video --- */}
      <RowsCard
        title={t("siteEditor.highlightsTitle")} hint={t("siteEditor.highlightsHint")} max={6} items={highlights}
        onChange={(items) => { setHighlights(items); setDirty(true); }} make={() => ({ value: "", label: "" })}
        render={(h, update, i) => (
          <div className="grid flex-1 gap-3 sm:grid-cols-[8rem_1fr]">
            <Field label={t("siteEditor.highlightValue")} htmlFor={`hl-value-${i}`}><Input id={`hl-value-${i}`} maxLength={12} placeholder="40+" value={h.value} onChange={(e) => update({ value: e.target.value })} /></Field>
            <Field label={t("siteEditor.highlightLabel")} htmlFor={`hl-label-${i}`}><Input id={`hl-label-${i}`} maxLength={60} placeholder={t("siteEditor.highlightLabelPlaceholder")} value={h.label} onChange={(e) => update({ label: e.target.value })} /></Field>
          </div>
        )}
      />
      <RowsCard
        title={t("siteEditor.pillarsTitle")} hint={t("siteEditor.pillarsHint")} max={6} items={pillars}
        onChange={(items) => { setPillars(items); setDirty(true); }} make={() => ({ title: "", text: null })}
        render={(p, update, i) => (
          <div className="grid flex-1 gap-3">
            <Field label={t("siteEditor.rowTitle")} htmlFor={`pl-title-${i}`}><Input id={`pl-title-${i}`} maxLength={60} value={p.title} onChange={(e) => update({ title: e.target.value })} /></Field>
            <Field label={t("siteEditor.rowText")} htmlFor={`pl-text-${i}`}><Textarea id={`pl-text-${i}`} rows={2} maxLength={300} value={p.text ?? ""} onChange={(e) => update({ text: e.target.value || null })} /></Field>
          </div>
        )}
      />
      <RowsCard
        title={t("siteEditor.historyTitle")} hint={t("siteEditor.historyHint")} max={20} items={history}
        onChange={(items) => { setHistory(items); setDirty(true); }} make={() => ({ year: "", title: "", text: null })}
        render={(h, update, i) => (
          <div className="grid flex-1 gap-3 sm:grid-cols-[7rem_1fr]">
            <Field label={t("siteEditor.historyYear")} htmlFor={`hs-year-${i}`}><Input id={`hs-year-${i}`} type="number" min={1882} max={2100} value={String(h.year)} onChange={(e) => update({ year: e.target.value })} /></Field>
            <Field label={t("siteEditor.rowTitle")} htmlFor={`hs-title-${i}`}><Input id={`hs-title-${i}`} maxLength={120} value={h.title} onChange={(e) => update({ title: e.target.value })} /></Field>
            <div className="sm:col-span-2">
              <Field label={t("siteEditor.rowText")} htmlFor={`hs-text-${i}`}><Textarea id={`hs-text-${i}`} rows={2} maxLength={600} value={h.text ?? ""} onChange={(e) => update({ text: e.target.value || null })} /></Field>
            </div>
          </div>
        )}
      />
      <RowsCard
        title={t("siteEditor.newsTitle")} hint={t("siteEditor.newsHint")} max={30} items={news} addFirst
        onChange={(items) => { setNews(items); setDirty(true); }}
        make={() => ({ date: new Date().toISOString().slice(0, 10), title: "", text: null, image_url: null, link_url: null })}
        render={(n, update, i) => (
          <div className="flex flex-1 flex-col gap-3 sm:flex-row">
            <ImageSlot
              label={t("siteEditor.newsImage")} url={n.image_url} compact
              onUpload={async (file) => { const r = await uploadImage("news", file); update({ image_url: r.url }); }}
              onRemove={() => update({ image_url: null })}
            />
            <div className="grid flex-1 gap-3 sm:grid-cols-[10rem_1fr]">
              <Field label={t("siteEditor.newsDate")} htmlFor={`nw-date-${i}`}><Input id={`nw-date-${i}`} type="date" value={n.date} onChange={(e) => update({ date: e.target.value })} /></Field>
              <Field label={t("siteEditor.rowTitle")} htmlFor={`nw-title-${i}`}><Input id={`nw-title-${i}`} maxLength={140} value={n.title} onChange={(e) => update({ title: e.target.value })} /></Field>
              <div className="sm:col-span-2">
                <Field label={t("siteEditor.rowText")} htmlFor={`nw-text-${i}`}><Textarea id={`nw-text-${i}`} rows={3} maxLength={2000} value={n.text ?? ""} onChange={(e) => update({ text: e.target.value || null })} /></Field>
              </div>
              <div className="sm:col-span-2">
                <Field label={t("siteEditor.newsLink")} htmlFor={`nw-link-${i}`}><Input id={`nw-link-${i}`} type="url" placeholder="https://..." value={n.link_url ?? ""} onChange={(e) => update({ link_url: e.target.value || null })} /></Field>
              </div>
            </div>
          </div>
        )}
      />
      <RowsCard
        title={t("siteEditor.videosTitle")} hint={t("siteEditor.videosHint")} max={12} items={videos}
        onChange={(items) => { setVideos(items); setDirty(true); }} make={() => ({ url: "", caption: null })}
        render={(v, update, i) => (
          <div className="grid flex-1 gap-3 sm:grid-cols-2">
            <Field label={t("siteEditor.videoUrl")} htmlFor={`vd-url-${i}`}><Input id={`vd-url-${i}`} type="url" placeholder="https://www.youtube.com/watch?v=..." value={v.url} onChange={(e) => update({ url: e.target.value })} /></Field>
            <Field label={t("siteEditor.caption")} htmlFor={`vd-cap-${i}`}><Input id={`vd-cap-${i}`} maxLength={200} value={v.caption ?? ""} onChange={(e) => update({ caption: e.target.value || null })} /></Field>
          </div>
        )}
      />

      {/* --- Contatti e social --- */}
      <Card>
        <CardHeader title={t("siteEditor.contactsTitle")} subtitle={t("siteEditor.contactsHint")} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("siteEditor.phone")} htmlFor="site-phone"><Input id="site-phone" type="tel" maxLength={40} value={text.contact_phone} onChange={set("contact_phone")} /></Field>
          <Field label="Email" htmlFor="site-email"><Input id="site-email" type="email" maxLength={255} value={text.contact_email} onChange={set("contact_email")} /></Field>
          <Field label={t("siteEditor.address")} htmlFor="site-address"><Input id="site-address" maxLength={300} value={text.address} onChange={set("address")} /></Field>
          <Field label={t("siteEditor.mapUrl")} htmlFor="site-map" hint={t("siteEditor.mapHint")}><Input id="site-map" type="url" placeholder="https://maps.google.com/..." value={text.map_url} onChange={set("map_url")} /></Field>
          <Field label="Instagram" htmlFor="site-ig"><Input id="site-ig" type="url" placeholder="https://instagram.com/..." value={text.instagram_url} onChange={set("instagram_url")} /></Field>
          <Field label="Facebook" htmlFor="site-fb"><Input id="site-fb" type="url" placeholder="https://facebook.com/..." value={text.facebook_url} onChange={set("facebook_url")} /></Field>
          <Field label="YouTube" htmlFor="site-yt"><Input id="site-yt" type="url" placeholder="https://youtube.com/..." value={text.youtube_url} onChange={set("youtube_url")} /></Field>
          <Field label="TikTok" htmlFor="site-tt"><Input id="site-tt" type="url" placeholder="https://tiktok.com/@..." value={text.tiktok_url} onChange={set("tiktok_url")} /></Field>
          <Field label={t("siteEditor.website")} htmlFor="site-web"><Input id="site-web" type="url" placeholder="https://..." value={text.website_url} onChange={set("website_url")} /></Field>
        </div>
      </Card>

      <div className="sticky bottom-4 z-10 flex justify-end">
        <Button size="lg" loading={saving} onClick={save} className={cn(dirty && "animate-pulse-ring")}>
          {t("siteEditor.save")}
        </Button>
      </div>
    </>
  );
}

/** Una lista che la segreteria compila a righe (numeri, storia, novità,
 *  video): aggiungi, togli, sposta. Le righe vuote non si salvano. */
function RowsCard<T>({ title, hint, items, max, make, render, onChange, addFirst = false }: {
  title: string; hint: string; items: T[]; max: number; make: () => T; addFirst?: boolean;
  render: (item: T, update: (patch: Partial<T>) => void, i: number) => ReactNode; onChange: (items: T[]) => void;
}) {
  const { t } = useI18n();
  const move = (i: number, delta: number) => {
    const j = i + delta;
    if (j < 0 || j >= items.length) return;
    const next = [...items];
    [next[i], next[j]] = [next[j] as T, next[i] as T];
    onChange(next);
  };
  return (
    <Card>
      <CardHeader
        title={title} subtitle={hint}
        action={<Button size="sm" variant="secondary" disabled={items.length >= max} onClick={() => onChange(addFirst ? [make(), ...items] : [...items, make()])}>{t("siteEditor.addRow")} <span className="font-normal text-ink-500">({items.length}/{max})</span></Button>}
      />
      {items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-ink-200 p-5 text-center text-sm text-ink-500">{t("siteEditor.rowsEmpty")}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((item, i) => (
            <li key={i} className="flex flex-col gap-3 rounded-2xl border border-ink-900/10 bg-white p-3 sm:flex-row sm:items-start">
              {render(item, (patch) => onChange(items.map((x, j) => (j === i ? { ...x, ...patch } : x))), i)}
              <div className="flex gap-1 sm:flex-col">
                <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label={t("siteEditor.moveUp")}>↑</Button>
                <Button size="sm" variant="ghost" disabled={i === items.length - 1} onClick={() => move(i, 1)} aria-label={t("siteEditor.moveDown")}>↓</Button>
                <Button size="sm" variant="ghost" className="text-rose-600" onClick={() => onChange(items.filter((_, j) => j !== i))} aria-label={t("siteEditor.remove")}>✕</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** I tre colori del club e l'anteprima dal vivo della copertina, calcolata
 *  con la stessa regola dell'API (lib/brand.ts ↔ club/brand.py): il testo
 *  sui bottoni diventa bianco o nero da solo, e un colore troppo chiaro per
 *  i titoli si scurisce. Gli avvisi lo dicono con parole semplici. */
function BrandCard({ site, hero, logo, colors, onChange, onReset }: {
  site: SiteAdmin; hero: string | null; logo: string | null; colors: Record<BrandKey, string>;
  onChange: (key: BrandKey, value: string) => void; onReset: () => void;
}) {
  const { t } = useI18n();
  const parsed = Object.fromEntries(BRAND_KEYS.map((k) => [k, normalizeHex(colors[k])])) as Record<BrandKey, string | null | undefined>;
  const invalid = BRAND_KEYS.filter((k) => parsed[k] === undefined);
  const theme = brandTheme(parsed.brand_primary ?? null, parsed.brand_secondary ?? null, parsed.brand_accent ?? null);
  const labels: Record<BrandKey, { label: string; hint: string }> = {
    brand_primary: { label: t("siteEditor.brandPrimary"), hint: t("siteEditor.brandPrimaryHint") },
    brand_secondary: { label: t("siteEditor.brandSecondary"), hint: t("siteEditor.brandSecondaryHint") },
    brand_accent: { label: t("siteEditor.brandAccent"), hint: t("siteEditor.brandAccentHint") },
  };
  const fallback: Record<BrandKey, string> = { brand_primary: theme.primary, brand_secondary: theme.secondary, brand_accent: theme.accent };
  const ratio = contrast(theme.primary, theme.on_primary);
  return (
    <Card>
      <CardHeader
        title={t("siteEditor.brandTitle")} subtitle={t("siteEditor.brandHint")}
        action={<Button size="sm" variant="ghost" onClick={onReset}>{t("siteEditor.brandReset")}</Button>}
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <div className="space-y-4">
          {BRAND_KEYS.map((key) => (
            <Field key={key} label={labels[key].label} htmlFor={`site-${key}`} hint={labels[key].hint}
              error={parsed[key] === undefined ? t("siteEditor.brandInvalid") : undefined}>
              <div className="flex items-center gap-2">
                <input
                  type="color" aria-label={labels[key].label}
                  className="h-11 w-14 shrink-0 cursor-pointer rounded-xl border border-ink-200 bg-white p-1"
                  value={(parsed[key] ?? fallback[key]).toLowerCase()}
                  onChange={(e) => onChange(key, e.target.value.toUpperCase())}
                />
                <Input
                  id={`site-${key}`} maxLength={7} placeholder={t("siteEditor.brandDefault", { color: fallback[key] })}
                  value={colors[key]} onChange={(e) => onChange(key, e.target.value)} className="font-mono uppercase"
                />
              </div>
            </Field>
          ))}
          <ul className="space-y-2 text-sm">
            <li className="flex items-start gap-2 text-ink-600">
              <span aria-hidden="true">✓</span>
              {t("siteEditor.brandReadable", {
                color: theme.on_primary === "#FFFFFF" ? t("siteEditor.brandWhite") : t("siteEditor.brandBlack"),
                ratio: ratio.toFixed(1),
              })}
            </li>
            {theme.warnings.map((w) => (
              <li key={w} className="flex items-start gap-2 rounded-xl bg-amber-50 px-3 py-2 text-amber-800">
                <span aria-hidden="true">⚠️</span>{t.dyn(`siteEditor.brandWarning.${w}`, w)}
              </li>
            ))}
            {!theme.custom && invalid.length === 0 && <li className="text-ink-500">{t("siteEditor.brandUsingJav")}</li>}
          </ul>
        </div>

        {/* L'anteprima: la stessa copertina della pagina, in piccolo. */}
        <div style={themeStyle(theme) as React.CSSProperties} aria-label={t("siteEditor.brandPreview")} role="img"
          className="overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/10">
          <div className="relative isolate h-32 overflow-hidden bg-club-cover-to">
            {/* eslint-disable-next-line @next/next/no-img-element -- anteprima della copertina caricata */}
            {hero && <img src={hero} alt="" className="absolute inset-0 -z-20 h-full w-full object-cover" />}
            <div className="absolute inset-0 -z-10 bg-gradient-to-br from-club-cover-from/80 via-club-cover-from/45 to-club-cover-to/90" />
            <div className="absolute -left-10 -top-10 -z-10 h-32 w-32 rounded-full bg-club-2/40 blur-2xl" />
            <p className="p-3 text-[10px] font-bold uppercase tracking-[0.25em] text-club-glow">{site.city ?? site.name}</p>
          </div>
          <div className="px-5 pb-5">
            <div className="-mt-10 flex items-end gap-3">
              <span className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white ring-4 ring-white shadow-soft">
                {/* eslint-disable-next-line @next/next/no-img-element -- anteprima del logo caricato */}
                {logo ? <img src={logo} alt="" className="h-full w-full object-contain p-1.5" /> : <span className="h-full w-full bg-club" />}
              </span>
              <p className="pb-1 text-lg font-semibold leading-tight text-ink-900">{site.name}</p>
            </div>
            <p className="mt-3 text-xs font-bold uppercase tracking-[0.2em] text-club-ink">{t("siteEditor.brandPreviewTitle")}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="inline-flex h-9 items-center rounded-xl bg-club px-4 text-sm font-semibold text-club-on">{t("site.fan.join")}</span>
              <span className="inline-flex h-9 items-center rounded-xl bg-white px-4 text-sm font-semibold text-ink-900 ring-1 ring-ink-200">{t("site.fan.sendMessage")}</span>
              <span className="inline-flex h-9 items-center rounded-xl bg-club-accent px-4 text-sm font-semibold text-club-on-accent">{t("siteEditor.brandAccentSample")}</span>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}

/** Una foto della pagina: anteprima subito (dal file scelto, prima ancora
 *  che il caricamento finisca), poi quella vera. */
function ImageSlot({ label, hint, url, wide = false, compact = false, onUpload, onRemove }: {
  label: string; hint?: string; url: string | null; wide?: boolean; compact?: boolean;
  onUpload: (file: File) => Promise<void>; onRemove: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const shown = preview ?? url;

  async function handle(file: File) {
    setPreview(URL.createObjectURL(file));
    setBusy(true);
    try {
      await onUpload(file);
    } catch (e) {
      toast({ tone: "error", title: t("siteEditor.uploadFailed"), text: (e as Error).message });
    } finally {
      setPreview(null);
      setBusy(false);
    }
  }

  return (
    <div className={cn(compact ? "w-28 shrink-0" : "")}>
      {!compact && <p className="mb-2 text-sm font-semibold text-ink-800">{label}</p>}
      <div className={cn("relative overflow-hidden rounded-2xl bg-ink-100 ring-1 ring-ink-900/10", wide ? "aspect-[16/7]" : "aspect-square", compact && "w-28")}>
        {shown ? (
          // eslint-disable-next-line @next/next/no-img-element -- anteprima di una foto caricata
          <img src={shown} alt="" className={cn("h-full w-full", wide ? "object-cover" : "object-contain bg-white")} />
        ) : (
          <span className="absolute inset-0 flex items-center justify-center text-xs text-ink-400">{t("siteEditor.noPhoto")}</span>
        )}
        {busy && <span className="absolute inset-0 flex items-center justify-center bg-white/70 text-xs font-semibold text-ink-700">{t("siteEditor.uploading")}</span>}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <UploadButton label={shown ? t("siteEditor.change") : t("siteEditor.upload")} ariaLabel={label} onFile={handle} disabled={busy} />
        {url && !busy && <Button size="sm" variant="ghost" className="text-rose-600" onClick={onRemove}>{t("siteEditor.remove")}</Button>}
      </div>
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

function UploadButton({ label, ariaLabel, onFile, disabled }: { label: ReactNode; ariaLabel?: string; onFile: (file: File) => Promise<void>; disabled?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  return (
    <>
      <input
        ref={ref} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" aria-hidden="true" tabIndex={-1}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          setBusy(true);
          try {
            await onFile(file);
          } catch (err) {
            toast({ tone: "error", title: t("siteEditor.uploadFailed"), text: (err as Error).message });
          } finally {
            setBusy(false);
          }
        }}
      />
      <Button size="sm" variant="secondary" loading={busy} disabled={disabled} aria-label={ariaLabel} onClick={() => ref.current?.click()}>{label}</Button>
    </>
  );
}

/** Chi dei propri atleti compare sul sito. L'interruttore si accende solo
 *  se la famiglia ha dato il consenso dal suo portale: il club non può
 *  deciderlo al posto suo. */
function AthletesCard() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<string | null>(null);
  const [page, setPage] = useState<AthleteStatus | null>(null);
  // Nell'unità dei corsi JAV gli atleti non hanno una scheda pubblica.
  const features = useClubFeatures();
  const { data, isLoading } = useQuery({
    queryKey: ["club", "site", "athletes"],
    queryFn: async (): Promise<AthleteStatus[]> => {
      const res = await fetch(`${BASE}/athletes`);
      if (!res.ok) throw new Error(await friendlyApiError(res));
      return res.json();
    },
  });

  async function toggle(a: AthleteStatus) {
    setPending(a.athlete_id);
    try {
      const rows = await send<AthleteStatus[]>(`/athletes/${a.athlete_id}/publish`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ published: !a.published }),
      });
      queryClient.setQueryData(["club", "site", "athletes"], rows);
    } catch (e) {
      toast({ tone: "error", title: t("siteEditor.saveFailed"), text: (e as Error).message });
    } finally {
      setPending(null);
    }
  }

  const rows = data ?? [];
  const withConsent = rows.filter((r) => r.consent).length;
  return (
    <Card>
      <CardHeader title={t("siteEditor.athletesTitle")} subtitle={t("siteEditor.athletesHint", { consent: withConsent, total: rows.length })} />
      {isLoading ? (
        <Skeleton className="h-40" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-ink-500">{t("siteEditor.athletesEmpty")}</p>
      ) : (
        <ul className="divide-y divide-ink-900/5">
          {rows.map((a) => (
            <li key={a.athlete_id} className="flex flex-wrap items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-ink-900">{a.first_name} {a.last_name}</p>
                <p className="text-xs text-ink-500">
                  {a.consent
                    ? t("siteEditor.consentSince", { date: fmt.shortDate(a.consent_given_at) }) + (a.show_photo ? ` · ${t("siteEditor.photoAllowed")}` : "")
                    : t("siteEditor.noConsent")}
                </p>
              </div>
              {a.belt && <BeltBadge code={a.belt} size="sm" showLabel={false} />}
              {a.consent ? <Badge tone="success">{t("siteEditor.consentYes")}</Badge> : <Badge tone="neutral">{t("siteEditor.consentNo")}</Badge>}
              {!features.courses && (
                <Button size="sm" variant="ghost" onClick={() => setPage(a)}>{t("athletePage.title")}</Button>
              )}
              <Switch
                checked={a.published} disabled={!a.consent || pending === a.athlete_id} onChange={() => toggle(a)}
                label={t("siteEditor.publishAthlete", { name: a.display_name })}
              />
            </li>
          ))}
        </ul>
      )}
      {page && (
        <Modal open onClose={() => setPage(null)} title={`${page.first_name} ${page.last_name}`} subtitle={t("athletePage.subtitle")} size="lg">
          <AthletePublicPageEditor athleteId={page.athlete_id} />
        </Modal>
      )}
    </Card>
  );
}

function Switch({ checked, disabled, onChange, label }: { checked: boolean; disabled?: boolean; onChange: () => void; label: string }) {
  return (
    <button
      type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={onChange}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-40",
        "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-500/25",
        checked ? "bg-emerald-500" : "bg-ink-200",
      )}
    >
      <span className={cn("inline-block h-5 w-5 rounded-full bg-white shadow transition-transform", checked ? "translate-x-5" : "translate-x-0.5")} />
    </button>
  );
}
