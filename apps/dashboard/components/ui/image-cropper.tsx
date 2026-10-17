"use client";

import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type PointerEvent as ReactPointerEvent } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

/** Il lato del quadrato che si manda al server: il server lo riduce ancora
 *  (AVATAR_MAX_SIDE, 800) e lo ricomprime (core/storage.py::optimize_image). */
const OUTPUT_SIDE = 800;
const MAX_ZOOM = 4;

/** Il ritaglio in pixel dell'immagine: il centro del quadrato e lo zoom (1 =
 *  il lato corto entra tutto). Non dipende dalla misura del riquadro, così
 *  girare il telefono non sposta niente. */
interface View { cx: number; cy: number; zoom: number }

function subscribeResize(cb: () => void) {
  window.addEventListener("resize", cb);
  return () => window.removeEventListener("resize", cb);
}

/** La foto scelta, prima di caricarla: si sposta col dito o col mouse, si
 *  ingrandisce (cursore, rotellina, due dita) e si vede subito come starà nel
 *  cerchio. «Usa questa foto» ritaglia il quadrato e lo passa a `onConfirm`
 *  come JPEG; il server lo ottimizza. `shape`: "round" per le foto profilo,
 *  "square" per un riquadro. */
export function ImageCropDialog({ file, shape = "round", onCancel, onConfirm }: {
  file: File | null;
  shape?: "round" | "square";
  onCancel: () => void;
  onConfirm: (cropped: File) => void | Promise<void>;
}) {
  if (typeof document === "undefined") return null;
  return createPortal(
    <AnimatePresence>
      {file && <CropBody key={`${file.name}-${file.size}-${file.lastModified}`} file={file} shape={shape} onCancel={onCancel} onConfirm={onConfirm} />}
    </AnimatePresence>,
    document.body,
  );
}

function CropBody({ file, shape, onCancel, onConfirm }: {
  file: File; shape: "round" | "square"; onCancel: () => void; onConfirm: (cropped: File) => void | Promise<void>;
}) {
  const { t } = useI18n();
  const [src] = useState(() => URL.createObjectURL(file));
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [failed, setFailed] = useState(false);
  // Il riquadro sta nello schermo anche su un telefono stretto.
  const width = useSyncExternalStore(subscribeResize, () => window.innerWidth, () => 400);
  const side = Math.max(220, Math.min(340, width - 64));
  const [view, setView] = useState<View>({ cx: 0, cy: 0, zoom: 1 });
  const [busy, setBusy] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<{ dist: number; zoom: number } | null>(null);

  useEffect(() => () => URL.revokeObjectURL(src), [src]);

  // Esc chiude solo il ritaglio, non la finestra che c'è sotto (la scheda
  // dell'atleta è anche lei un Modal che ascolta Esc).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopImmediatePropagation();
      onCancel();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onCancel]);

  /** La scala che copre il riquadro a zoom 1: l'immagine non lascia mai buchi. */
  const base = natural ? Math.max(side / natural.w, side / natural.h) : 1;
  /** Il lato del quadrato ritagliato, in pixel dell'immagine. */
  const cropOf = (zoom: number) => (natural ? Math.min(natural.w, natural.h) / zoom : 1);

  const clamp = useCallback((v: View): View => {
    if (!natural) return v;
    const zoom = Math.min(MAX_ZOOM, Math.max(1, v.zoom));
    const half = Math.min(natural.w, natural.h) / zoom / 2;
    return {
      zoom,
      cx: Math.min(natural.w - half, Math.max(half, v.cx)),
      cy: Math.min(natural.h - half, Math.max(half, v.cy)),
    };
  }, [natural]);

  /** Lo zoom intorno a un punto del riquadro (px, py): quel punto resta
   *  sotto il dito. */
  const zoomAt = useCallback((zoom: (current: number) => number, px: number, py: number) => {
    if (!natural) return;
    const short = Math.min(natural.w, natural.h);
    setView((v) => {
      const next = Math.min(MAX_ZOOM, Math.max(1, zoom(v.zoom)));
      const c = short / v.zoom;
      const c2 = short / next;
      const nx = v.cx - c / 2 + (px / side) * c;
      const ny = v.cy - c / 2 + (py / side) * c;
      return clamp({ zoom: next, cx: nx - (px / side) * c2 + c2 / 2, cy: ny - (py / side) * c2 + c2 / 2 });
    });
  }, [natural, side, clamp]);

  function center() {
    const img = imgRef.current;
    if (!img) return;
    const n = { w: img.naturalWidth, h: img.naturalHeight };
    setNatural(n);
    setView({ zoom: 1, cx: n.w / 2, cy: n.h / 2 });
  }

  function local(e: { clientX: number; clientY: number }) {
    const r = frameRef.current?.getBoundingClientRect();
    return { x: e.clientX - (r?.left ?? 0), y: e.clientY - (r?.top ?? 0) };
  }

  function onPointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const [a, b] = [...pointers.current.values()];
    if (a && b) pinch.current = { dist: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)), zoom: view.zoom };
  }

  function onPointerMove(e: ReactPointerEvent<HTMLDivElement>) {
    const prev = pointers.current.get(e.pointerId);
    if (!prev) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const [a, b] = [...pointers.current.values()];
    if (a && b && pinch.current) {
      const mid = local({ clientX: (a.x + b.x) / 2, clientY: (a.y + b.y) / 2 });
      const target = pinch.current.zoom * (Math.hypot(a.x - b.x, a.y - b.y) / pinch.current.dist);
      zoomAt(() => target, mid.x, mid.y);
      return;
    }
    const k = cropOf(view.zoom) / side;
    const dx = (e.clientX - prev.x) * k;
    const dy = (e.clientY - prev.y) * k;
    setView((v) => clamp({ ...v, cx: v.cx - dx, cy: v.cy - dy }));
  }

  function onPointerUp(e: ReactPointerEvent<HTMLDivElement>) {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
  }

  // La rotellina: un listener vero (non passivo), per non far scorrere la pagina.
  useEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const factor = Math.exp(-e.deltaY * 0.0015);
      zoomAt((z) => z * factor, e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  function onKeyDown(e: React.KeyboardEvent) {
    const step = cropOf(view.zoom) / 20;
    const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    const move = moves[e.key];
    if (move) {
      e.preventDefault();
      const [dx, dy] = move;
      setView((v) => clamp({ ...v, cx: v.cx + dx, cy: v.cy + dy }));
    } else if (e.key === "+" || e.key === "=") {
      zoomAt((z) => z * 1.15, side / 2, side / 2);
    } else if (e.key === "-") {
      zoomAt((z) => z / 1.15, side / 2, side / 2);
    }
  }

  async function confirm() {
    const img = imgRef.current;
    if (!img || !natural) return;
    setBusy(true);
    let cropped: File;
    try {
      const sw = cropOf(view.zoom);
      const sx = view.cx - sw / 2;
      const sy = view.cy - sw / 2;
      const out = Math.min(OUTPUT_SIDE, Math.round(sw));
      const canvas = document.createElement("canvas");
      canvas.width = out;
      canvas.height = out;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("canvas");
      // Un PNG trasparente non diventa nero nel JPEG.
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, out, out);
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(img, sx, sy, sw, sw, 0, 0, out, out);
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
      if (!blob) throw new Error("blob");
      const name = `${file.name.replace(/\.[^.]+$/, "") || "foto"}.jpg`;
      cropped = new File([blob], name, { type: "image/jpeg" });
    } catch {
      setFailed(true);
      setBusy(false);
      return;
    }
    // Un caricamento che non va lo segnala chi carica (con il suo avviso).
    try {
      await onConfirm(cropped);
    } finally {
      setBusy(false);
    }
  }

  // Dove disegnare l'immagine in un riquadro di `side * k` px.
  const s = base * view.zoom;
  const left = -(view.cx - cropOf(view.zoom) / 2) * s;
  const top = -(view.cy - cropOf(view.zoom) / 2) * s;
  const imgStyle = (k: number) => natural ? {
    width: natural.w, height: natural.h,
    transform: `translate(${left * k}px, ${top * k}px) scale(${s * k})`,
  } : undefined;
  const round = shape === "round";

  return (
    <div className="fixed inset-0 z-[110] flex items-end justify-center sm:items-center sm:p-6" role="dialog" aria-modal="true" aria-label={t("crop.title")}>
      <motion.div className="absolute inset-0 bg-ink-950/60 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onCancel} />
      <motion.div
        initial={{ y: 60, opacity: 0, scale: 0.98 }} animate={{ y: 0, opacity: 1, scale: 1 }} exit={{ y: 40, opacity: 0, scale: 0.98 }}
        transition={{ type: "spring", stiffness: 380, damping: 32 }}
        className="relative max-h-[94vh] w-full overflow-y-auto rounded-t-3xl bg-white p-5 shadow-lift sm:max-w-2xl sm:rounded-3xl sm:p-6"
      >
        <h2 className="text-lg text-ink-900">{t("crop.title")}</h2>
        <p className="mt-1 text-sm text-ink-500">{t("crop.hint")}</p>

        {failed ? (
          <p className="mt-5 rounded-2xl bg-rose-50 p-4 text-sm text-rose-700">{t("crop.failed")}</p>
        ) : (
          <div className="mt-5 flex flex-col items-center gap-5 sm:flex-row sm:items-start">
            <div
              ref={frameRef} tabIndex={0} onKeyDown={onKeyDown}
              onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
              className="relative shrink-0 cursor-grab touch-none select-none overflow-hidden rounded-2xl bg-ink-900 outline-none ring-offset-2 focus-visible:ring-4 focus-visible:ring-accent-300 active:cursor-grabbing"
              style={{ width: side, height: side }}
              aria-label={t("crop.frame")}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- anteprima locale del file scelto */}
              <img ref={imgRef} src={src} alt="" onLoad={center} onError={() => setFailed(true)} draggable={false}
                className={cn("absolute left-0 top-0 max-w-none origin-top-left", !natural && "opacity-0")} style={imgStyle(1)} />
              {/* Fuori dal cerchio si scurisce: si vede che cosa resta. */}
              <span aria-hidden="true" className={cn("pointer-events-none absolute inset-0 ring-2 ring-white/90", round ? "rounded-full" : "rounded-xl")}
                style={{ boxShadow: "0 0 0 9999px rgba(10, 12, 20, 0.55)" }} />
              {!natural && <span className="absolute inset-0 flex items-center justify-center text-sm text-white/70">…</span>}
            </div>

            <div className="flex w-full min-w-0 flex-1 flex-col items-center gap-4 sm:items-start">
              <p className="text-xs font-bold uppercase tracking-wider text-ink-400">{t("crop.preview")}</p>
              <div className="flex items-end gap-4">
                {[96, 56, 36].map((p) => (
                  <span key={p} className={cn("relative block shrink-0 overflow-hidden bg-ink-100 shadow-soft ring-2 ring-white", round ? "rounded-full" : "rounded-xl")} style={{ width: p, height: p }}>
                    {natural && (
                      // eslint-disable-next-line @next/next/no-img-element -- anteprima locale
                      <img src={src} alt="" draggable={false} className="absolute left-0 top-0 max-w-none origin-top-left" style={imgStyle(p / side)} />
                    )}
                  </span>
                ))}
              </div>
              <label className="w-full max-w-xs">
                <span className="mb-1 flex items-center justify-between text-xs font-semibold text-ink-600">
                  <span>🔍 {t("crop.zoom")}</span>
                  <span className="tabular-nums text-ink-400">{Math.round(view.zoom * 100)}%</span>
                </span>
                <input type="range" min={1} max={MAX_ZOOM} step={0.01} value={view.zoom} disabled={!natural}
                  onChange={(e) => { const z = Number(e.target.value); zoomAt(() => z, side / 2, side / 2); }}
                  className="w-full accent-brand-600" />
              </label>
              <button type="button" disabled={!natural} onClick={center} className="text-xs font-semibold text-brand-700 hover:underline disabled:opacity-50">
                ↺ {t("crop.reset")}
              </button>
            </div>
          </div>
        )}

        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="ghost" onClick={onCancel} disabled={busy}>{t("crop.cancel")}</Button>
          {!failed && <Button onClick={confirm} loading={busy} disabled={!natural}>{t("crop.use")}</Button>}
        </div>
      </motion.div>
    </div>
  );
}
