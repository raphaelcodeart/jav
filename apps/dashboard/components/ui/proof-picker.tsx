"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo } from "react";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// La prova di pagamento: due bottoni grandi, sempre visibili, «Scatta una
// foto» (apre la fotocamera del telefono) e «Allega un file» (galleria, PDF
// della banca, screenshot di MB Way), e l'anteprima di ciò che si è scelto.
// Due input separati di proposito: con `capture` alcuni telefoni aprono
// solo la fotocamera e non lasciano scegliere un file.

const ACCEPT = "image/jpeg,image/png,application/pdf";

export function ProofPicker({ file, onFile, optional = false, className }: {
  file: File | null; onFile: (f: File | null) => void; optional?: boolean; className?: string;
}) {
  const { t } = useI18n();
  const preview = useMemo(() => (file && file.type.startsWith("image/") ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const pick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) onFile(f);
    e.target.value = "";
  };

  return (
    <div className={cn("space-y-2", className)}>
      <p className="flex items-center justify-between text-xs font-bold uppercase tracking-wide text-ink-500">
        <span>🧾 {t("proof.title")}</span>
        {optional && <span className="font-semibold normal-case tracking-normal text-ink-400">{t("proof.optional")}</span>}
      </p>
      <AnimatePresence mode="wait" initial={false}>
        {file ? (
          <motion.div key="file" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
            className="flex items-center gap-3 rounded-2xl bg-emerald-50 p-3 ring-1 ring-emerald-200">
            {preview ? (
              // eslint-disable-next-line @next/next/no-img-element -- anteprima locale del file scelto
              <img src={preview} alt="" className="h-16 w-16 shrink-0 rounded-xl object-cover ring-2 ring-white" />
            ) : (
              <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-xl bg-white text-3xl ring-1 ring-emerald-200">📄</span>
            )}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-ink-900">✓ {file.name}</span>
              <span className="block text-xs text-ink-500">{(file.size / 1024 / 1024).toFixed(1)} MB · {t("proof.ready")}</span>
            </span>
            <button type="button" onClick={() => onFile(null)} className="cursor-pointer rounded-xl px-3 py-2 text-sm font-semibold text-rose-600 hover:bg-white">
              {t("proof.remove")}
            </button>
          </motion.div>
        ) : (
          <motion.div key="pick" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="grid grid-cols-2 gap-2">
            <label className="group flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 px-3 py-4 text-center text-white shadow-brand transition hover:brightness-110 active:scale-[0.98]">
              <span className="text-3xl transition-transform group-hover:scale-110" aria-hidden="true">📷</span>
              <span className="text-sm font-bold">{t("proof.takePhoto")}</span>
              <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={pick} />
            </label>
            <label className="group flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-2xl border-2 border-dashed border-brand-300 bg-brand-50/60 px-3 py-4 text-center text-brand-800 transition hover:border-brand-500 hover:bg-brand-50 active:scale-[0.98]">
              <span className="text-3xl transition-transform group-hover:scale-110" aria-hidden="true">📎</span>
              <span className="text-sm font-bold">{t("proof.attachFile")}</span>
              <input type="file" accept={ACCEPT} className="sr-only" onChange={pick} />
            </label>
          </motion.div>
        )}
      </AnimatePresence>
      {!file && <p className="text-xs text-ink-500">{t("proof.hint")}</p>}
    </div>
  );
}
