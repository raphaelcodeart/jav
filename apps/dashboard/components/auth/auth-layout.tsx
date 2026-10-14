"use client";

import dynamic from "next/dynamic";
import Image from "next/image";
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

/** Shared frame of login, password reset and sign-up: a 3D dojo on one
 *  side, the form on a white card on the other (stacked on phones). */
export function AuthLayout({ children, title, subtitle }: { children: ReactNode; title?: ReactNode; subtitle?: ReactNode }) {
  const { t } = useI18n();
  return (
    <main className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      <section className="relative overflow-hidden min-h-[300px] lg:min-h-screen bg-gradient-to-b from-white to-[#fbf7ec]">
        <div className="absolute inset-0">
          <DojoScene />
        </div>
        {/* A soft white veil where the headline sits, so it reads on any frame. */}
        <div className="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-white via-white/70 to-transparent pointer-events-none hidden lg:block" aria-hidden="true" />
        <div className="relative z-10 p-6 sm:p-10 flex flex-col h-full pointer-events-none">
          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-3">
            <div className="rounded-2xl bg-white/90 backdrop-blur p-1.5 shadow-soft ring-1 ring-ink-100">
              <Image src="/logo.png" alt="Jav" width={52} height={47} priority />
            </div>
            <div className="leading-tight rounded-2xl bg-white/85 backdrop-blur px-3 py-1.5 shadow-soft ring-1 ring-ink-100">
              <p className="font-display text-xl text-ink-900">JAV</p>
              <p className="text-xs font-semibold text-ink-500">Judo Arte e Vida</p>
            </div>
          </motion.div>
          <div className="mt-auto hidden lg:block max-w-md">
            <motion.h2
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
              className="text-4xl xl:text-5xl leading-[1.05] text-ink-900"
            >
              {t("auth.headline")} <span className="text-gradient-brand">{t("auth.headlineAccent")}</span>
            </motion.h2>
            <div className="mt-6 space-y-2.5">
              {FEATURES.map((f, i) => (
                <motion.p
                  key={f.key}
                  initial={{ opacity: 0, x: -16 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.1 }}
                  className="inline-flex items-center gap-3 rounded-2xl bg-white/85 backdrop-blur px-4 py-2.5 text-sm font-semibold text-ink-800 shadow-soft ring-1 ring-ink-100 mr-2"
                >
                  <span className="text-lg">{f.icon}</span>
                  {t(f.key)}
                </motion.p>
              ))}
            </div>
            <div className="mt-6 flex gap-3">
              {["WHITE", "YELLOW", "ORANGE", "GREEN", "BLUE", "BROWN", "BLACK_1"].map((b, i) => (
                <motion.span key={b} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 + i * 0.06 }}>
                  <BeltBadge code={b} size="sm" showLabel={false} />
                </motion.span>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="relative flex items-center justify-center px-4 py-10 sm:px-8 -mt-10 lg:mt-0">
        {/* Above the 3D scene on phones (the card overlaps it), in the corner
            of the form column on a computer. */}
        <LanguageSwitcher className="fixed lg:absolute right-4 top-4 z-30" />
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: "spring", stiffness: 200, damping: 24, delay: 0.05 }}
          className="relative w-full max-w-md rounded-[32px] bg-white p-7 sm:p-9 shadow-lift ring-1 ring-ink-100"
        >
          <div className="absolute -top-px left-10 right-10 h-1 rounded-b-full bg-gradient-to-r from-brand-500 via-accent-400 to-ink-500" aria-hidden="true" />
          {title && <h1 className="text-2xl text-ink-900">{title}</h1>}
          {subtitle && <p className="text-sm text-ink-500 mt-1.5">{subtitle}</p>}
          <div className={title || subtitle ? "mt-7" : ""}>{children}</div>
        </motion.div>
      </section>
    </main>
  );
}
