"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { AVATARS, CITIES, HERO_COLORS, type City, type HeroColor } from "./engine";
import type { CareerT } from "./i18n";
import { COLOR_GRAD, COLOR_HEX, Judoka, Tatami } from "./ui";

// Schermata "nuova carriera": nome, avatar, colore e città di partenza.

export function ColorPicker({ value, onChange, label }: { value: HeroColor; onChange: (c: HeroColor) => void; label: string }) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-bold text-ink-800">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {HERO_COLORS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => onChange(c)}
            aria-pressed={value === c}
            aria-label={c}
            className={cn("h-11 w-11 cursor-pointer rounded-full ring-2 ring-offset-2 transition", value === c ? "ring-ink-900 scale-110" : "ring-transparent")}
            style={{ background: COLOR_HEX[c] }}
          />
        ))}
      </div>
    </fieldset>
  );
}

export function CityPicker({ value, onChange, label }: { value: City; onChange: (c: City) => void; label: string }) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-bold text-ink-800">{label}</legend>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {CITIES.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => onChange(c)}
            aria-pressed={value === c}
            className={cn(
              "h-11 cursor-pointer rounded-xl px-3 text-sm font-semibold ring-1 transition",
              value === c ? "bg-ink-900 text-white ring-ink-900" : "bg-white text-ink-700 ring-ink-200 hover:ring-brand-300",
            )}
          >
            📍 {c}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export function NewCareer({ defaultName, t, busy, onStart }: {
  defaultName: string; t: CareerT; busy: boolean;
  onStart: (v: { name: string; avatar: string; color: HeroColor; city: City }) => void;
}) {
  const [name, setName] = useState(defaultName);
  const [avatar, setAvatar] = useState<string>(AVATARS[0]);
  const [color, setColor] = useState<HeroColor>("red");
  const [city, setCity] = useState<City>("Lagos");

  return (
    <div className="mx-auto max-w-2xl">
      <div className={cn("relative overflow-hidden rounded-[2rem] bg-gradient-to-br p-5 text-white shadow-lift sm:p-7", COLOR_GRAD[color])}>
        <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-accent-300/40 blur-3xl" aria-hidden="true" />
        <motion.p initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="relative text-xs font-bold uppercase tracking-[0.25em] text-white/80">
          Judo Career
        </motion.p>
        <h2 className="relative mt-1 font-display text-2xl leading-tight sm:text-3xl">{t("newTitle")}</h2>
        <p className="relative mt-2 max-w-md text-sm text-white/90">{t("newSub")}</p>
        <Tatami className="relative mt-3 h-40">
          <div className="absolute inset-x-0 bottom-3 flex items-end justify-center gap-3">
            <motion.span key={avatar} initial={{ scale: 0.4, rotate: -20 }} animate={{ scale: 1, rotate: 0 }} className="mb-16 text-4xl drop-shadow" aria-hidden="true">{avatar}</motion.span>
            <Judoka belt="WHITE" pose="win" size={80} />
          </div>
        </Tatami>
      </div>

      <form
        className="mt-4 space-y-5 rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-100"
        onSubmit={(e) => { e.preventDefault(); onStart({ name, avatar, color, city }); }}
      >
        <label className="block">
          <span className="mb-2 block text-sm font-bold text-ink-800">{t("newName")}</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={24}
            required
            className="h-12 w-full rounded-xl border border-ink-200 bg-ink-50 px-4 text-base font-semibold text-ink-900 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-200"
          />
        </label>
        <fieldset>
          <legend className="mb-2 text-sm font-bold text-ink-800">{t("newAvatar")}</legend>
          <div className="flex flex-wrap gap-2">
            {AVATARS.map((a) => (
              <button
                key={a}
                type="button"
                onClick={() => setAvatar(a)}
                aria-pressed={avatar === a}
                className={cn("flex h-12 w-12 cursor-pointer items-center justify-center rounded-2xl text-2xl ring-2 transition", avatar === a ? "bg-accent-100 ring-accent-500 scale-110" : "bg-ink-50 ring-transparent hover:ring-ink-200")}
              >
                {a}
              </button>
            ))}
          </div>
        </fieldset>
        <ColorPicker value={color} onChange={setColor} label={t("newColor")} />
        <CityPicker value={city} onChange={setCity} label={t("newCity")} />
        <Button type="submit" size="xl" className="w-full" loading={busy} disabled={!name.trim()}>
          {t("newStart")} 🥋
        </Button>
      </form>
    </div>
  );
}
