"use client";

import { useState, useSyncExternalStore } from "react";
import { Modal } from "@/components/ui/modal";
import { useI18n } from "@/lib/i18n/provider";
import type { NewsPost } from "@/lib/public-site";

export interface PlayableVideo {
  youtube_id: string;
  title: string;
  /** "2026-05-10": i video del canale hanno la data, quelli scelti a mano no. */
  published?: string | null;
}

/** I video del club: il primo grande, gli altri accanto, e un tocco apre il
 *  lettore. Il lettore è youtube-nocookie.com (nessun cookie finché il video
 *  non parte) e l'indirizzo si costruisce qui dall'id: l'API non manda mai
 *  un indirizzo da mettere in un iframe. */
export function ClubVideos({ videos }: { videos: PlayableVideo[] }) {
  const { t, fmt } = useI18n();
  const [open, setOpen] = useState<PlayableVideo | null>(null);
  if (videos.length === 0) return null;
  return (
    <>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {videos.map((v, i) => (
          <li key={v.youtube_id} className={i === 0 ? "sm:col-span-2 lg:row-span-2" : undefined}>
            <button
              type="button"
              onClick={() => setOpen(v)}
              className="group relative block h-full w-full overflow-hidden rounded-3xl bg-ink-950 text-left shadow-soft ring-1 ring-ink-900/10 transition-transform hover:-translate-y-1 motion-reduce:transition-none motion-reduce:hover:translate-y-0 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-club/40 cursor-pointer"
              aria-label={`${t("site.judoka.playVideo")}: ${v.title}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- copertina servita da YouTube */}
              <img src={`https://i.ytimg.com/vi/${v.youtube_id}/${i === 0 ? "maxresdefault" : "hqdefault"}.jpg`} alt="" loading="lazy"
                onError={(e) => { const img = e.currentTarget; if (!img.src.endsWith("/hqdefault.jpg")) img.src = `https://i.ytimg.com/vi/${v.youtube_id}/hqdefault.jpg`; }}
                className="aspect-video h-full w-full object-cover opacity-85 transition duration-500 group-hover:scale-[1.03] group-hover:opacity-100 motion-reduce:transition-none" />
              <span className="absolute inset-0 bg-gradient-to-t from-ink-950/90 via-ink-950/10 to-transparent" aria-hidden="true" />
              <span className={`absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-club text-club-on shadow-lift transition-transform group-hover:scale-110 motion-reduce:transition-none ${i === 0 ? "h-20 w-20 text-3xl" : "h-14 w-14 text-xl"}`} aria-hidden="true">
                ▶
              </span>
              <span className="absolute inset-x-0 bottom-0 p-4">
                <span className={`line-clamp-2 font-semibold text-white ${i === 0 ? "text-lg" : "text-sm"}`}>{v.title}</span>
                {v.published && <span className="mt-1 block text-xs text-white/70">{fmt.shortDate(v.published)}</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <Modal open={open !== null} onClose={() => setOpen(null)} title={open?.title ?? ""} size="xl">
        {open && (
          <div className="relative aspect-video overflow-hidden rounded-xl bg-black">
            <iframe
              src={`https://www.youtube-nocookie.com/embed/${open.youtube_id}?autoplay=1&rel=0&modestbranding=1`}
              title={open.title}
              allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
              allowFullScreen
              className="absolute inset-0 h-full w-full"
            />
          </div>
        )}
      </Modal>
    </>
  );
}

/** Le novità del club come i post di una pagina Facebook: il logo e il
 *  nome del club, la data, il testo (lungo si apre con "Ver mais") e la
 *  foto. Le prime tre si vedono, le altre con "Mostrar mais". */
export function NewsFeed({ posts, clubName, logoUrl, initials }: { posts: NewsPost[]; clubName: string; logoUrl: string | null; initials: string }) {
  const { t, fmt } = useI18n();
  const [all, setAll] = useState(false);
  const shown = all ? posts : posts.slice(0, 3);
  return (
    <div className="space-y-5">
      {shown.map((p) => <Post key={`${p.date}-${p.title}`} post={p} clubName={clubName} logoUrl={logoUrl} initials={initials} date={fmt.date(new Date(`${p.date}T12:00:00`), { day: "numeric", month: "long", year: "numeric" })} />)}
      {posts.length > 3 && !all && (
        <button type="button" onClick={() => setAll(true)} className="w-full rounded-2xl bg-white py-3 text-sm font-semibold text-club-ink shadow-soft ring-1 ring-ink-900/5 transition hover:ring-club">
          {t("site.fan.moreNews", { n: posts.length - 3 })}
        </button>
      )}
    </div>
  );
}

function Post({ post, clubName, logoUrl, initials, date }: { post: NewsPost; clubName: string; logoUrl: string | null; initials: string; date: string }) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const long = (post.text?.length ?? 0) > 280;
  const text = post.text && long && !expanded ? `${post.text.slice(0, 260).trimEnd()}…` : post.text;
  return (
    <article className="overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-ink-900/5">
      <header className="flex items-center gap-3 p-4 pb-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white ring-2 ring-club/30">
          {logoUrl ? (
            // eslint-disable-next-line @next/next/no-img-element -- logo caricato dal club
            <img src={logoUrl} alt="" className="h-full w-full object-contain p-1" />
          ) : (
            <span className="flex h-full w-full items-center justify-center bg-club text-sm font-bold text-club-on">{initials}</span>
          )}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink-900">{clubName}</p>
          <p className="text-xs text-ink-500"><time dateTime={post.date}>{date}</time></p>
        </div>
      </header>
      <div className="px-4 pb-4">
        <h3 className="text-lg leading-snug text-ink-900">{post.title}</h3>
        {text && <p className="mt-2 whitespace-pre-line text-[15px] leading-relaxed text-ink-700">{text}</p>}
        {long && (
          <button type="button" onClick={() => setExpanded((v) => !v)} className="mt-1 text-sm font-semibold text-club-ink hover:underline">
            {expanded ? t("site.fan.seeLess") : t("site.fan.seeMore")}
          </button>
        )}
      </div>
      {post.image_url && (
        // eslint-disable-next-line @next/next/no-img-element -- foto caricata dal club
        <img src={post.image_url} alt="" loading="lazy" className="max-h-[32rem] w-full bg-ink-50 object-cover" />
      )}
      {post.link_url && (
        <a href={post.link_url} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 border-t border-ink-900/5 px-4 py-3 text-sm font-semibold text-club-ink hover:bg-ink-50">
          {t("site.fan.readMore")} <span aria-hidden="true">↗</span>
        </a>
      )}
    </article>
  );
}

/** La mappa si carica solo quando la si chiede: un iframe di Google Maps
 *  all'apertura della pagina manderebbe a Google ogni visitatore, anche chi
 *  non la guarda (e senza un consenso). Prima c'è un riquadro con
 *  l'indirizzo e il bottone. */
export function ClubMap({ query, mapUrl }: { query: string; mapUrl: string | null }) {
  const { t } = useI18n();
  const [show, setShow] = useState(false);
  const src = `https://www.google.com/maps?q=${encodeURIComponent(query)}&output=embed`;
  return (
    <div className="relative overflow-hidden rounded-3xl bg-ink-900 shadow-soft ring-1 ring-ink-900/10">
      {show ? (
        <iframe src={src} title={t("site.fan.mapTitle")} loading="lazy" referrerPolicy="no-referrer-when-downgrade" className="h-80 w-full border-0" />
      ) : (
        <div className="relative flex h-80 flex-col items-center justify-center gap-4 overflow-hidden p-6 text-center text-white">
          <div className="absolute inset-0 -z-0 opacity-30 [background-image:linear-gradient(rgba(255,255,255,.12)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.12)_1px,transparent_1px)] [background-size:32px_32px]" aria-hidden="true" />
          <span className="relative flex h-14 w-14 items-center justify-center rounded-full bg-club text-2xl text-club-on shadow-lift" aria-hidden="true">📍</span>
          <p className="relative max-w-sm text-sm text-white/85">{query}</p>
          <div className="relative flex flex-wrap justify-center gap-2">
            <button type="button" onClick={() => setShow(true)} className="h-10 rounded-xl bg-white px-4 text-sm font-semibold text-ink-900 transition hover:-translate-y-px">
              {t("site.fan.showMap")}
            </button>
            <a href={mapUrl ?? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`} target="_blank" rel="noopener noreferrer"
              className="inline-flex h-10 items-center rounded-xl px-4 text-sm font-semibold text-white ring-1 ring-white/40 transition hover:bg-white/10">
              {t("site.fan.directions")} ↗
            </a>
          </div>
          <p className="relative text-[11px] text-white/55">{t("site.fan.mapPrivacy")}</p>
        </div>
      )}
    </div>
  );
}

function subscribeScroll(onChange: () => void): () => void {
  window.addEventListener("scroll", onChange, { passive: true });
  window.addEventListener("resize", onChange);
  return () => {
    window.removeEventListener("scroll", onChange);
    window.removeEventListener("resize", onChange);
  };
}

function barVisible(): boolean {
  const form = document.getElementById("mensagem");
  const formTop = form ? form.getBoundingClientRect().top : Infinity;
  return window.scrollY > 520 && formTop > window.innerHeight * 0.6;
}

/** Sul telefono, dopo la copertina, una barra in fondo con "Inscrever" e
 *  "Mensagem": le due cose per cui si apre la pagina di un club. Sparisce
 *  quando si arriva al modulo, che le ha già. */
export function MobileClubBar({ joinHref, joinLabel, messageLabel }: { joinHref: string; joinLabel: string; messageLabel: string }) {
  const visible = useSyncExternalStore(subscribeScroll, barVisible, () => false);
  return (
    <div className={`fixed inset-x-0 bottom-0 z-40 border-t border-ink-900/10 bg-white/95 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md transition-transform duration-300 motion-reduce:transition-none md:hidden ${visible ? "translate-y-0" : "translate-y-full"}`}
      aria-hidden={!visible}>
      {/* pr-20: a destra c'è il bottone di JAVBOT, che non deve coprire "Mensagem". */}
      <div className="flex gap-2 pr-20">
        <a href={joinHref} tabIndex={visible ? 0 : -1} className="flex h-12 flex-1 items-center justify-center rounded-2xl bg-club font-semibold text-club-on shadow-soft">{joinLabel}</a>
        <a href="#mensagem" tabIndex={visible ? 0 : -1} className="flex h-12 flex-1 items-center justify-center rounded-2xl bg-white font-semibold text-ink-900 ring-1 ring-ink-200">✉ {messageLabel}</a>
      </div>
    </div>
  );
}
