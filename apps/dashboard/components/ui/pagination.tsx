"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

/** I numeri da mostrare: sempre la prima e l'ultima, le vicine a quella
 *  corrente, e «…» nei buchi (1 … 4 5 6 … 12). */
function pageList(page: number, pages: number): (number | "…")[] {
  const out: (number | "…")[] = [];
  for (let p = 1; p <= pages; p++) {
    if (p === 1 || p === pages || Math.abs(p - page) <= 1) out.push(p);
    else if (out[out.length - 1] !== "…") out.push("…");
  }
  return out;
}

/** Le pagine 1 2 3 … di un elenco lungo, con ‹ e ›. Niente se c'è una pagina sola. */
export function Pagination({ page, pages, onChange, className }: {
  page: number; pages: number; onChange: (page: number) => void; className?: string;
}) {
  const { t } = useI18n();
  if (pages <= 1) return null;
  const go = (p: number) => onChange(Math.min(pages, Math.max(1, p)));
  const btn = "inline-flex h-10 min-w-10 cursor-pointer items-center justify-center rounded-xl px-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-40";
  return (
    <nav aria-label={t("pager.label")} className={cn("flex flex-wrap items-center justify-center gap-1.5", className)}>
      <button type="button" className={cn(btn, "bg-white text-ink-700 ring-1 ring-ink-200 hover:bg-ink-50")} disabled={page <= 1}
        onClick={() => go(page - 1)} aria-label={t("pager.prev")}>‹</button>
      {pageList(page, pages).map((p, i) => p === "…" ? (
        <span key={`gap-${i}`} className="px-1 text-ink-400">…</span>
      ) : (
        <button key={p} type="button" onClick={() => go(p)} aria-current={p === page ? "page" : undefined}
          className={cn(btn, p === page ? "bg-brand-600 text-white shadow-soft" : "bg-white text-ink-700 ring-1 ring-ink-200 hover:bg-ink-50")}>
          {p}
        </button>
      ))}
      <button type="button" className={cn(btn, "bg-white text-ink-700 ring-1 ring-ink-200 hover:bg-ink-50")} disabled={page >= pages}
        onClick={() => go(page + 1)} aria-label={t("pager.next")}>›</button>
    </nav>
  );
}

/** Un elenco già in memoria diviso in pagine. Si torna a pagina 1 quando
 *  l'elenco cambia (un filtro, una ricerca). */
export function usePaged<T>(items: T[], size = 20) {
  const [page, setPage] = useState(1);
  const [seen, setSeen] = useState(`${items.length}:${size}`);
  const pages = Math.max(1, Math.ceil(items.length / size));
  // L'elenco è cambiato: si riparte dalla prima pagina (durante il render,
  // come vuole React, non in un effetto).
  if (seen !== `${items.length}:${size}`) {
    setSeen(`${items.length}:${size}`);
    setPage(1);
  }
  const current = Math.min(page, pages);
  const slice = useMemo(() => items.slice((current - 1) * size, current * size), [items, current, size]);
  return { items: slice, page: current, pages, setPage, total: items.length };
}
