"use client";

import dynamic from "next/dynamic";
import Image from "next/image";
import Link from "next/link";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { BeltBadge } from "@/components/ui/belt";
import { LanguageSwitcher } from "@/components/language-switcher";
import { useI18n } from "@/lib/i18n/provider";

// The 3D scene is only ever loaded on the auth pages, never inside the app,
// and never on the server: three.js is a big download and needs a canvas.
const DojoScene = dynamic(() => import("@/components/auth/dojo-scene"), {
  ssr: false,
  loading: () => <SceneFallback />,
});

/** What shows while the scene loads (and where WebGL is unavailable): the
 *  same mood, painted in CSS. */
function SceneFallback() {
  return (
    <div className="absolute inset-0 bg-[radial-gradient(60%_60%_at_50%_70%,rgb(228_63_33/0.25),transparent),linear-gradient(180deg,#fff,#fbf7ec)]">
      <div className="absolute inset-x-10 bottom-10 h-40 rounded-[40px] bg-[repeating-linear-gradient(90deg,#fbf7ec_0_48px,#e8e3d6_48px_96px)] ring-8 ring-brand-500 [transform:perspective(600px)_rotateX(55deg)]" />
    </div>
  );
}

const FEATURES = [
  { icon: "🥋", key: "auth.feature1" },
  { icon: "🏆", key: "auth.feature2" },
  { icon: "🎖️", key: "auth.feature3" },
] as const;

/** Shared frame of login, password reset and sign-up: il dojo 3D come
 *  sfondo a tutto schermo e la scheda del modulo al centro, sul telefono come
 *  sul computer; sotto, i tre punti di forza e le cinture. */
export function AuthLayout({ children, title, subtitle }: { children: ReactNode; title?: ReactNode; subtitle?: ReactNode }) {
  const { t } = useI18n();
  return (
    <main className="relative min-h-[100dvh] overflow-hidden bg-gradient-to-b from-white to-[#fbf7ec]">
      <div className="absolute inset-0" aria-hidden="true">
        <DojoScene />
      </div>
      {/* Un velo chiaro dietro la scheda: il testo si legge su qualunque fotogramma. */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_55%_at_50%_45%,rgba(255,255,255,0.92),rgba(255,255,255,0.55)_60%,rgba(255,255,255,0.15))]" aria-hidden="true" />
      {/* Il contenitore fisso fuori dal selettore: il selettore è già `relative`
          e `fixed` passato come classe perderebbe (la bandiera finiva a sinistra,
          tagliata fuori dallo schermo). */}
      <div className="fixed right-3 top-3 z-30 sm:right-4 sm:top-4">
        <LanguageSwitcher />
      </div>

      <div className="relative z-10 mx-auto flex min-h-[100dvh] w-full max-w-md flex-col items-center justify-center px-4 py-10">
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6 flex items-center gap-3">
          {/* Il logo porta al sito pubblico. */}
          <Link href="/" aria-label="Judo Arte e Vida" className="rounded-2xl bg-white p-1.5 shadow-soft ring-1 ring-ink-100 transition hover:-translate-y-0.5 hover:shadow-lift">
            <Image src="/judoartevida-logo.jpg" alt="Judo Arte e Vida" width={120} height={52} priority className="h-12 w-auto" />
          </Link>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.05 }}
          className="relative w-full rounded-[32px] bg-white/95 p-6 shadow-lift ring-1 ring-ink-100 backdrop-blur sm:p-9"
        >
          <div className="absolute -top-px left-10 right-10 h-1 rounded-b-full bg-gradient-to-r from-brand-500 via-accent-400 to-ink-500" aria-hidden="true" />
          {title && <h1 className="text-center text-2xl text-ink-900">{title}</h1>}
          {subtitle && <p className="mt-1.5 text-center text-sm text-ink-500">{subtitle}</p>}
          <div className={title || subtitle ? "mt-7" : ""}>{children}</div>
        </motion.div>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {FEATURES.map((f, i) => (
            <motion.p key={f.key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 + i * 0.1 }}
              className="inline-flex items-center gap-2 rounded-full bg-white/90 px-3 py-1.5 text-xs font-semibold text-ink-700 shadow-soft ring-1 ring-ink-100 backdrop-blur">
              <span aria-hidden="true">{f.icon}</span>{t(f.key)}
            </motion.p>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {["WHITE", "YELLOW", "ORANGE", "GREEN", "BLUE", "BROWN", "BLACK_1"].map((b, i) => (
            <motion.span key={b} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 + i * 0.06 }}>
              <BeltBadge code={b} size="sm" showLabel={false} />
            </motion.span>
          ))}
        </div>
      </div>
    </main>
  );
}
