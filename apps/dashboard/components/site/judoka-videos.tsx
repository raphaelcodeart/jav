"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { useI18n } from "@/lib/i18n/provider";

export interface JudokaVideo {
  id: string;
  youtube_id: string;
  caption: string | null;
}

/** I video della scheda di un judoca: copertine in griglia, e un tocco apre
 *  il lettore. Il lettore è quello di youtube-nocookie.com, che non lascia
 *  cookie finché il video non parte, e l'indirizzo si costruisce qui
 *  dall'id: l'API non manda mai un indirizzo da mettere in un iframe. */
export function JudokaVideos({ videos, name }: { videos: JudokaVideo[]; name: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<JudokaVideo | null>(null);
  const title = (v: JudokaVideo, i: number) => v.caption ?? t("site.judoka.videoOf", { name, n: i + 1 });
  return (
    <>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {videos.map((v, i) => (
          <li key={v.id}>
            <button
              type="button"
              onClick={() => setOpen(v)}
              className="group relative block w-full overflow-hidden rounded-3xl bg-ink-900 text-left shadow-soft ring-1 ring-ink-900/10 transition-transform hover:-translate-y-1 motion-reduce:transition-none motion-reduce:hover:translate-y-0 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-500/40 cursor-pointer"
              aria-label={`${t("site.judoka.playVideo")}: ${title(v, i)}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- copertina servita da YouTube */}
              <img src={`https://i.ytimg.com/vi/${v.youtube_id}/hqdefault.jpg`} alt="" loading="lazy" className="aspect-video w-full object-cover opacity-90 transition-opacity group-hover:opacity-100" />
              <span className="absolute left-1/2 top-[40%] flex h-14 w-14 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-brand-500 text-xl text-white shadow-brand transition-transform group-hover:scale-110 motion-reduce:transition-none" aria-hidden="true">
                ▶
              </span>
              <span className="block px-4 py-3">
                <span className="line-clamp-2 text-sm font-semibold text-white">{title(v, i)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      <Modal open={open !== null} onClose={() => setOpen(null)} title={open ? title(open, videos.indexOf(open)) : name} size="xl">
        {open && (
          <div className="relative aspect-video overflow-hidden rounded-xl bg-black">
            <iframe
              src={`https://www.youtube-nocookie.com/embed/${open.youtube_id}?autoplay=1&rel=0&modestbranding=1`}
              title={title(open, videos.indexOf(open))}
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
