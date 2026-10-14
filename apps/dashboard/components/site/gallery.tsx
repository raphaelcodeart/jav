"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { useI18n } from "@/lib/i18n/provider";
import type { GalleryItem } from "@/lib/public-site";

/** Le foto del club: una griglia, e un tocco apre la foto grande con la
 *  sua didascalia. Le immagini sotto la piega si caricano solo quando
 *  servono (loading="lazy"). */
export function Gallery({ items, clubName }: { items: GalleryItem[]; clubName: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<number | null>(null);
  const current = open !== null ? items[open] : undefined;
  return (
    <>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {items.map((item, i) => (
          <li key={item.url} className={i === 0 ? "col-span-2 row-span-2" : undefined}>
            <button
              type="button"
              onClick={() => setOpen(i)}
              className="group relative block h-full w-full overflow-hidden rounded-2xl bg-ink-100 cursor-zoom-in focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-500/30"
              aria-label={item.caption ?? t("site.gallery.photoOf", { club: clubName, n: i + 1 })}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- foto caricate dal club */}
              <img src={item.url} alt="" loading="lazy" className="aspect-square h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
              {item.caption && (
                <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-ink-950/80 to-transparent p-3 text-left text-xs font-semibold text-white">
                  {item.caption}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      <Modal open={current !== undefined} onClose={() => setOpen(null)} title={current?.caption ?? clubName} size="xl">
        {current && (
          // eslint-disable-next-line @next/next/no-img-element -- foto caricate dal club
          <img src={current.url} alt={current.caption ?? ""} className="max-h-[75vh] w-full rounded-xl object-contain" />
        )}
      </Modal>
    </>
  );
}
