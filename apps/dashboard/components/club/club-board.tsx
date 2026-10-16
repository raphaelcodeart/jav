"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Textarea } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { friendlyApiError } from "@/lib/api-error";
import { clubGet, clubSend } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

// La bacheca del club (apps/api/app/domains/club/news.py): le notizie che la
// segreteria pubblica, come un post (titolo, testo, foto, video o link), e i
// documenti del club condivisi con atleti e famiglie. `NewsAdminPanel` è il
// lato della segreteria, `ClubBoard` quello di atleti e famiglie.

export interface NewsPost {
  id: string;
  title: string;
  body: string | null;
  image_url: string | null;
  video_url: string | null;
  link_url: string | null;
  pinned: boolean;
  published: boolean;
  published_at: string;
  author_name: string | null;
  /** CLUB: solo i soci; NETWORK: tutto il circuito. */
  audience?: "CLUB" | "NETWORK";
  /** Chi firma: il club, o JudoArteVida. */
  club?: { name: string; slug: string | null; logo_url: string | null } | null;
  likes?: number;
  liked?: boolean;
}

interface FeedEvent {
  id: string; name: string; kind: string; level: string; status: string; starts_on: string; ends_on: string;
  location: string | null; organizer: string | null; image_url: string | null; registration_deadline: string;
  club_name: string | null; network: boolean;
}

interface FeedItem { type: "POST" | "EVENT"; date: string; post: NewsPost | null; event: FeedEvent | null }

interface BoardDocument {
  id: string;
  category: string;
  title: string;
  issued_on: string | null;
  expires_on: string | null;
  notes: string | null;
  original_filename: string;
  created_at: string;
}

interface Board { news: NewsPost[]; documents: BoardDocument[]; feed?: FeedItem[] }

const DOC_ICONS: Record<string, string> = {
  DECLARATION: "📝", FEDERATION: "🥋", MINUTES: "📒", TAX: "🧾", SOCIAL_SECURITY: "🛡️", SPORTS: "🏅",
  INSURANCE: "☂️", STATUTES: "📜", OTHER: "📁",
};

/** L'indirizzo da incorporare per un video di YouTube o Vimeo; null per
 *  qualunque altro link, che resta un link. */
export function videoEmbedUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\.|^m\./, "");
    let id: string | null = null;
    if (host === "youtu.be") id = u.pathname.slice(1).split("/")[0] ?? null;
    else if (host === "youtube.com" || host === "youtube-nocookie.com") {
      id = u.searchParams.get("v") ?? u.pathname.match(/^\/(?:shorts|embed|live)\/([\w-]+)/)?.[1] ?? null;
    }
    if (id && /^[\w-]{6,20}$/.test(id)) return `https://www.youtube-nocookie.com/embed/${id}`;
    if (host === "vimeo.com" || host === "player.vimeo.com") {
      const vid = u.pathname.match(/(\d{6,12})/)?.[1];
      if (vid) return `https://player.vimeo.com/video/${vid}`;
    }
  } catch {
    return null;
  }
  return null;
}

function hostOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

// --- Un post ---------------------------------------------------------------------------------------

export function NewsCard({ post, fresh = false, actions, likeable = false }: { post: NewsPost; fresh?: boolean; actions?: React.ReactNode; likeable?: boolean }) {
  const { t, fmt } = useI18n();
  const embed = videoEmbedUrl(post.video_url);
  const queryClient = useQueryClient();
  const [like, setLike] = useState({ n: post.likes ?? 0, on: !!post.liked });
  async function toggleLike() {
    setLike((l) => ({ n: l.n + (l.on ? -1 : 1), on: !l.on }));
    try {
      const res = await clubSend<{ likes: number; liked: boolean }>(`/board/posts/${post.id}/like`, "POST");
      setLike({ n: res.likes, on: res.liked });
      void queryClient.invalidateQueries({ queryKey: ["club", "board"] });
    } catch {
      setLike({ n: post.likes ?? 0, on: !!post.liked });
    }
  }
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5"
    >
      <header className="flex items-start gap-3 px-5 pt-5">
        {post.club?.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- logo del club o di JudoArteVida
          <img src={post.club.logo_url} alt="" className="h-11 w-11 shrink-0 rounded-full bg-white object-cover ring-2 ring-ink-100" />
        ) : (
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-accent-500 text-lg text-white" aria-hidden="true">📰</span>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ink-900">{post.club?.name ?? ""}</p>
          <p className="text-xs text-ink-500">
            {post.author_name ? `${post.author_name} · ` : ""}{fmt.shortDate(post.published_at)}
            {post.audience === "NETWORK" ? ` · 🌍 ${t("board.audienceNetworkShort")}` : ` · 🏯 ${t("board.audienceClubShort")}`}
          </p>
          <h3 className="mt-1 text-lg leading-snug text-ink-900">{post.title}</h3>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1">
          {post.pinned && <Badge tone="warning">📌 {t("board.pinned")}</Badge>}
          {!post.published && <Badge tone="neutral">{t("board.draft")}</Badge>}
          {fresh && <Badge tone="brand" dot>{t("board.new")}</Badge>}
        </div>
      </header>
      {post.body && <p className="whitespace-pre-line px-5 pt-3 text-sm leading-relaxed text-ink-700">{post.body}</p>}
      {post.image_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={post.image_url} alt="" loading="lazy" className="mt-4 max-h-[480px] w-full object-cover" />
      )}
      {embed ? (
        <div className="mt-4 aspect-video w-full bg-ink-950">
          <iframe src={embed} title={post.title} className="h-full w-full" loading="lazy"
            allow="accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen" allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin" />
        </div>
      ) : post.video_url && (
        <a href={post.video_url} target="_blank" rel="noopener noreferrer" className="mx-5 mt-4 flex items-center gap-3 rounded-2xl bg-ink-950 px-4 py-3 text-sm font-semibold text-white hover:bg-ink-800">
          <span className="text-xl" aria-hidden="true">▶️</span>{t("board.watchVideo")} · {hostOf(post.video_url)}
        </a>
      )}
      {post.link_url && (
        <a href={post.link_url} target="_blank" rel="noopener noreferrer"
          className="mx-5 mt-4 flex items-center gap-3 rounded-2xl bg-ink-50 px-4 py-3 ring-1 ring-ink-100 hover:ring-brand-300">
          <span className="text-xl" aria-hidden="true">🔗</span>
          <span className="min-w-0"><span className="block truncate text-sm font-semibold text-brand-700">{hostOf(post.link_url)}</span>
            <span className="block truncate text-xs text-ink-500">{post.link_url}</span></span>
        </a>
      )}
      {likeable ? (
        <div className="mt-4 flex items-center gap-3 border-t border-ink-100 px-5 py-3">
          <motion.button type="button" whileTap={{ scale: 1.25 }} onClick={toggleLike}
            className={`inline-flex cursor-pointer items-center gap-2 rounded-full px-4 py-1.5 text-sm font-semibold ring-1 transition ${like.on ? "bg-rose-50 text-rose-600 ring-rose-200" : "bg-white text-ink-600 ring-ink-200 hover:bg-ink-50"}`}>
            <span aria-hidden="true">{like.on ? "❤️" : "🤍"}</span> {like.n > 0 ? like.n : ""} {t("board.like")}
          </motion.button>
        </div>
      ) : <div className="h-5" />}
      {actions && <footer className="flex flex-wrap gap-2 border-t border-ink-100 px-5 py-3">{actions}</footer>}
    </motion.article>
  );
}

// --- La bacheca di atleti e famiglie ------------------------------------------------------------------

const SEEN_KEY = "jav.board.seen";

function readSeen(): string | null {
  try { return window.localStorage.getItem(SEEN_KEY); } catch { return null; }
}

/** Le notizie e i documenti del club. `compact` (nell'area dell'atleta)
 *  mostra le ultime notizie e i documenti in una colonna sola. */
export function ClubBoard({ compact = false }: { compact?: boolean }) {
  const { t } = useI18n();
  const { data, isLoading, error } = useQuery({ queryKey: ["club", "board"], queryFn: () => clubGet<Board>("/board") });
  // L'ultima visita, letta una volta: le notizie più nuove hanno «Nuovo».
  const [seen] = useState(() => (typeof window === "undefined" ? null : readSeen()));
  const [all, setAll] = useState(false);
  // Segna come lette le notizie di adesso, per la prossima visita.
  useEffect(() => {
    const newest = data?.news.reduce<string | null>((m, p) => (!m || p.published_at > m ? p.published_at : m), null);
    if (newest) {
      try { window.localStorage.setItem(SEEN_KEY, newest); } catch { /* il browser non salva: niente «Nuovo» */ }
    }
  }, [data]);

  if (isLoading) return <Skeleton className="h-64" />;
  if (error || !data) return <EmptyState icon={<span className="text-3xl">📰</span>} title={t("board.loadError")} text={(error as Error)?.message} />;

  // Il flusso: i post del club, del circuito e di JudoArteVida, e le prove in arrivo come post.
  const items: FeedItem[] = data.feed ?? data.news.map((p) => ({ type: "POST", date: p.published_at, post: p, event: null }));
  const shown = compact && !all ? items.slice(0, 4) : items;

  const news = (
    <div className="space-y-4">
      {items.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">📰</span>} title={t("board.noNews")} text={t("board.noNewsText")} />
      ) : shown.map((i) => i.post
        ? <NewsCard key={`p-${i.post.id}`} post={i.post} likeable fresh={!!seen && i.post.published_at > seen} />
        : i.event ? <EventPost key={`e-${i.event.id}`} event={i.event} /> : null)}
      {compact && items.length > shown.length && (
        <Button variant="secondary" onClick={() => setAll(true)}>{t("board.showAll", { n: items.length })}</Button>
      )}
    </div>
  );
  const docs = <BoardDocuments docs={data.documents} />;

  if (compact) return <div className="space-y-6">{news}{data.documents.length > 0 && docs}</div>;
  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-700 via-brand-600 to-ink-950 p-6 text-white shadow-lift sm:p-8">
        <motion.div aria-hidden="true" className="pointer-events-none absolute -right-10 -top-16 h-56 w-56 rounded-full bg-accent-400/30 blur-3xl"
          animate={{ scale: [1, 1.15, 1] }} transition={{ duration: 9, repeat: Infinity, ease: "easeInOut" }} />
        <p className="text-xs font-bold uppercase tracking-[0.22em] text-white/80">📰 {t("board.eyebrow")}</p>
        <h1 className="mt-1 text-3xl">{t("board.title")}</h1>
        <p className="mt-2 max-w-xl text-white/80">{t("board.intro")}</p>
      </section>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        {news}
        <aside className="lg:sticky lg:top-6">{docs}</aside>
      </div>
    </div>
  );
}

const EVENT_STYLE: Record<string, { icon: string; bg: string }> = {
  COMPETITION: { icon: "🏆", bg: "from-brand-500 to-brand-800" }, STAGE: { icon: "🥋", bg: "from-sky-500 to-sky-800" },
  REFEREEING: { icon: "🧑‍⚖️", bg: "from-violet-500 to-violet-800" }, EDUCATION: { icon: "🎓", bg: "from-emerald-500 to-emerald-800" },
  MEETING: { icon: "🤝", bg: "from-amber-500 to-amber-700" }, OTHER: { icon: "📌", bg: "from-ink-500 to-ink-800" },
};

/** Una prova in arrivo come post: locandina o icona, data, luogo, iscrizioni. */
function EventPost({ event: e }: { event: FeedEvent }) {
  const { t, fmt } = useI18n();
  const style = EVENT_STYLE[e.kind] ?? EVENT_STYLE.OTHER!;
  const start = new Date(`${e.starts_on}T12:00:00`);
  return (
    <motion.article initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5">
      <div className={`relative flex h-36 items-end bg-gradient-to-br p-4 text-white ${style.bg}`}>
        {e.image_url && (
          // eslint-disable-next-line @next/next/no-img-element -- locandina caricata dal club
          <img src={e.image_url} alt="" className="absolute inset-0 h-full w-full object-cover opacity-80" loading="lazy" />
        )}
        {!e.image_url && <span className="absolute right-4 top-3 text-6xl opacity-60" aria-hidden="true">{style.icon}</span>}
        <span className="relative rounded-2xl bg-white/95 px-3 py-1.5 text-center text-ink-900 shadow">
          <span className="block font-display text-2xl leading-none">{start.getDate()}</span>
          <span className="block text-[10px] font-bold uppercase">{fmt.date(start, { month: "short" })}</span>
        </span>
        <span className="relative ml-3 rounded-full bg-black/40 px-3 py-1 text-xs font-semibold backdrop-blur">📅 {t("board.eventPost")}</span>
      </div>
      <div className="space-y-1 p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">{e.network ? t("jcal.network") : e.club_name}</p>
        <h3 className="text-lg leading-snug text-ink-900">{e.name}</h3>
        <p className="text-sm text-ink-500">📍 {e.location ?? "—"}{e.organizer ? ` · ${e.organizer}` : ""}</p>
        {e.status === "OPEN" && <p className="text-sm font-semibold text-emerald-700">✅ {t("jcal.until", { date: fmt.shortDate(e.registration_deadline) })}</p>}
      </div>
    </motion.article>
  );
}

function BoardDocuments({ docs }: { docs: BoardDocument[] }) {
  const { t, fmt } = useI18n();
  const toast = useToast();

  async function open(doc: BoardDocument) {
    // La finestra si apre subito, nel clic: dopo un'attesa i browser la bloccano.
    const win = window.open("", "_blank");
    try {
      const { url } = await clubGet<{ url: string }>(`/board/documents/${doc.id}/url`);
      if (win) win.location.replace(url);
      else window.location.assign(url);
    } catch (e) {
      win?.close();
      toast({ tone: "error", title: t("board.openError"), text: (e as Error).message });
    }
  }

  return (
    <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5">
      <h2 className="text-lg text-ink-900">📁 {t("board.documents")}</h2>
      {docs.length === 0 ? (
        <p className="mt-2 text-sm text-ink-500">{t("board.noDocuments")}</p>
      ) : (
        <ul className="mt-3 divide-y divide-ink-100">
          {docs.map((d) => (
            <li key={d.id}>
              <button type="button" onClick={() => open(d)} className="group flex w-full items-center gap-3 py-3 text-left cursor-pointer">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-lg ring-1 ring-brand-100" aria-hidden="true">{DOC_ICONS[d.category] ?? "📁"}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-ink-900 group-hover:text-brand-700">{d.title}</span>
                  <span className="block truncate text-xs text-ink-500">
                    {t.dyn(`clubDocs.cat.${d.category}`, d.category)} · {fmt.shortDate(d.issued_on ?? d.created_at)}
                  </span>
                  {d.notes && <span className="block text-xs text-ink-600">{d.notes}</span>}
                </span>
                <span className="text-brand-600" aria-hidden="true">↗</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --- La segreteria ---------------------------------------------------------------------------------

/** Le notizie del club: scriverle, correggerle, fissarle in cima, toglierle. */
/** Le chiamate della console: del club (`/club/admin/news`) o di JudoArteVida (`/platform-news`). */
function newsApi(mode: "club" | "platform") {
  const base = mode === "club" ? "/api/proxy/club/admin/news" : "/api/proxy/platform-news";
  async function call<T>(path: string, method = "GET", body?: unknown): Promise<T> {
    const init: RequestInit = { method };
    if (body instanceof FormData) init.body = body;
    else if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "Content-Type": "application/json" }; }
    const res = await fetch(`${base}${path}`, init);
    if (!res.ok) throw new Error(await friendlyApiError(res));
    return (res.status === 204 ? undefined : await res.json()) as T;
  }
  return call;
}

export function NewsAdminPanel({ mode = "club" }: { mode?: "club" | "platform" }) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const api = newsApi(mode);
  const { data, isLoading } = useQuery({ queryKey: ["club", "admin", "news", mode], queryFn: () => api<NewsPost[]>("") });
  const [editing, setEditing] = useState<NewsPost | "new" | null>(null);

  async function patch(post: NewsPost, changes: Partial<NewsPost>, ok: string) {
    try {
      await api(`/${post.id}`, "PATCH", changes);
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: ok });
    } catch (e) {
      toast({ tone: "error", title: t("board.saveError"), text: (e as Error).message });
    }
  }
  async function remove(post: NewsPost) {
    if (!window.confirm(t("board.confirmDelete", { title: post.title }))) return;
    try {
      await api(`/${post.id}`, "DELETE");
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: t("board.deleted") });
    } catch (e) {
      toast({ tone: "error", title: t("board.saveError"), text: (e as Error).message });
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-ink-600">{t("board.adminIntro")}</p>
        <Button onClick={() => setEditing("new")}>＋ {t("board.newPost")}</Button>
      </div>
      {isLoading ? <Skeleton className="h-64" /> : (data ?? []).length === 0 ? (
        <EmptyState icon={<span className="text-3xl">📰</span>} title={t("board.noNews")} text={t("board.adminEmpty")}
          action={<Button onClick={() => setEditing("new")}>{t("board.firstPost")}</Button>} />
      ) : (
        <div className="mx-auto max-w-2xl space-y-4">
          {(data ?? []).map((p) => (
            <NewsCard key={p.id} post={p} actions={<>
              <Button size="sm" variant="secondary" onClick={() => setEditing(p)}>✎ {t("board.edit")}</Button>
              <Button size="sm" variant="ghost" onClick={() => patch(p, { pinned: !p.pinned }, p.pinned ? t("board.unpinned") : t("board.pinnedDone"))}>
                📌 {p.pinned ? t("board.unpin") : t("board.pin")}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => patch(p, { published: !p.published }, p.published ? t("board.hidden") : t("board.publishedDone"))}>
                {p.published ? `🙈 ${t("board.hide")}` : `🚀 ${t("board.publish")}`}
              </Button>
              <Button size="sm" variant="ghost" className="ml-auto text-rose-600" onClick={() => remove(p)}>{t("board.delete")}</Button>
            </>} />
          ))}
        </div>
      )}
      {editing && <NewsModal mode={mode} post={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function NewsModal({ post, onClose, mode }: { post: NewsPost | null; onClose: () => void; mode: "club" | "platform" }) {
  const api = newsApi(mode);
  const [audience, setAudience] = useState<"CLUB" | "NETWORK">(post?.audience ?? (mode === "platform" ? "NETWORK" : "CLUB"));
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState(post?.title ?? "");
  const [body, setBody] = useState(post?.body ?? "");
  const [image, setImage] = useState<string | null>(post?.image_url ?? null);
  const [video, setVideo] = useState(post?.video_url ?? "");
  const [link, setLink] = useState(post?.link_url ?? "");
  const [pinned, setPinned] = useState(post?.pinned ?? false);
  const [published, setPublished] = useState(post?.published ?? true);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const { url } = await api<{ url: string }>("/image", "POST", form);
      setImage(url);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    const payload = { title, body: body || null, image_url: image, video_url: video.trim() || null, link_url: link.trim() || null, pinned, published, audience };
    try {
      if (post) await api(`/${post.id}`, "PATCH", payload);
      else await api("", "POST", payload);
      await queryClient.invalidateQueries({ queryKey: ["club"] });
      toast({ tone: "success", title: post ? t("board.saved") : published ? t("board.publishedDone") : t("board.savedDraft") });
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const preview: NewsPost = {
    id: "preview", title: title || t("board.titlePlaceholder"), body: body || null, image_url: image,
    video_url: video.trim() || null, link_url: link.trim() || null, pinned, published,
    published_at: post?.published_at ?? new Date().toISOString(), author_name: post?.author_name ?? null, audience,
  };

  return (
    <Modal open onClose={onClose} size="xl" title={post ? t("board.editTitle") : t("board.newPost")}
      footer={<>
        <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        <Button onClick={save} loading={busy} disabled={!title.trim() || uploading}>
          {published ? t("board.publishButton") : t("board.saveDraft")}
        </Button>
      </>}
    >
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <Field label={t("board.titleLabel")}>
            <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={t("board.titlePlaceholder")} />
          </Field>
          <Field label={t("board.bodyLabel")}>
            <Textarea rows={6} value={body} maxLength={10000} onChange={(e) => setBody(e.target.value)} placeholder={t("board.bodyPlaceholder")} />
          </Field>
          <Field label={t("board.photo")} hint={t("board.photoHint")}>
            <div className="flex flex-wrap items-center gap-2">
              <Input ref={input} type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} />
              {uploading && <span className="text-xs text-ink-500">{t("board.uploading")}</span>}
              {image && <Button size="sm" variant="ghost" onClick={() => setImage(null)}>{t("board.removePhoto")}</Button>}
            </div>
          </Field>
          <Field label={t("board.video")} hint={t("board.videoHint")}>
            <Input value={video} maxLength={500} onChange={(e) => setVideo(e.target.value)} placeholder="https://youtu.be/…" inputMode="url" />
          </Field>
          <Field label={t("board.link")} hint={t("board.linkHint")}>
            <Input value={link} maxLength={500} onChange={(e) => setLink(e.target.value)} placeholder="https://…" inputMode="url" />
          </Field>
          {mode === "club" && (
            <div>
              <p className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-500">{t("board.audience")}</p>
              <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label={t("board.audience")}>
                {([["CLUB", "🏯", t("board.audienceClub")], ["NETWORK", "🌍", t("board.audienceNetwork")]] as const).map(([key, icon, label]) => (
                  <button key={key} type="button" role="radio" aria-checked={audience === key} onClick={() => setAudience(key)}
                    className={`cursor-pointer rounded-2xl p-3 text-left text-sm ring-1 ${audience === key ? "bg-brand-50 ring-2 ring-brand-400" : "bg-white ring-ink-200 hover:ring-ink-300"}`}>
                    <span className="mr-1" aria-hidden="true">{icon}</span>{label}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="flex flex-wrap gap-5 text-sm text-ink-700">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={pinned} onChange={(e) => setPinned(e.target.checked)} />📌 {t("board.pinLabel")}
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={published} onChange={(e) => setPublished(e.target.checked)} />🚀 {t("board.publishLabel")}
            </label>
          </div>
          {error && <p className="text-sm text-rose-600">{error}</p>}
        </div>
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-500">{t("board.preview")}</p>
          <NewsCard post={preview} />
        </div>
      </div>
    </Modal>
  );
}
