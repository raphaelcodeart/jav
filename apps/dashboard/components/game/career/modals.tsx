"use client";

import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { cn } from "@/lib/cn";
import type { GameEvent, WeekReport } from "./engine";
import { money, type CareerKey, type CareerT } from "./i18n";
import { LedgerTable } from "./panel-club";
import { BeltBadge, MEDAL_EMOJI, logText } from "./ui";

// Le finestre del gioco: l'evento da decidere, il riepilogo della settimana e il "ricomincia".

const EVENT_ICON: Record<GameEvent["kind"], string> = {
  NEW_ATHLETE: "🙋", TALENT: "🌟", SPONSOR: "🤝", PARENT_COMPLAINT: "😤", EQUIPMENT_BREAK: "💥",
};

const EVENT_BUTTONS: Record<GameEvent["kind"], [CareerKey, CareerKey]> = {
  NEW_ATHLETE: ["ev_accept", "ev_decline"],
  TALENT: ["ev_accept", "ev_decline"],
  SPONSOR: ["ev_accept", "ev_decline"],
  PARENT_COMPLAINT: ["ev_talk", "ev_ignore"],
  EQUIPMENT_BREAK: ["ev_repair", "ev_later"],
};

export function EventModal({ event, open, t, locale, onResolve, onClose }: {
  event: GameEvent; open: boolean; t: CareerT; locale: string;
  onResolve: (accept: boolean) => void; onClose: () => void;
}) {
  const vars: Record<string, string | number> = {};
  if (event.kind === "NEW_ATHLETE" || event.kind === "TALENT") {
    vars.name = event.athlete.name;
    vars.age = event.athlete.age;
    vars.belt = t(`belt_${event.athlete.belt}`);
  } else if (event.kind === "SPONSOR") {
    vars.name = event.sponsor.name;
    vars.n = money(event.sponsor.perMonth, locale);
  } else if (event.kind === "PARENT_COMPLAINT") {
    vars.name = event.athleteName;
  } else {
    vars.n = money(event.cost, locale);
  }
  const [yes, no] = EVENT_BUTTONS[event.kind];
  return (
    <Modal open={open} onClose={onClose} title={t(`ev_${event.kind}_title`)} size="sm">
      <div className="text-center">
        <motion.p initial={{ scale: 0.4, rotate: -15 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring", stiffness: 300, damping: 14 }} className="text-6xl" aria-hidden="true">
          {EVENT_ICON[event.kind]}
        </motion.p>
        <p className="mt-3 text-base text-ink-700">{t(`ev_${event.kind}_text`, vars)}</p>
        {(event.kind === "NEW_ATHLETE" || event.kind === "TALENT") && (
          <div className="mt-3 flex justify-center gap-3 text-sm font-semibold text-ink-700">
            <BeltBadge belt={event.athlete.belt} t={t} small />
            <span>🥋 {event.athlete.tecnica}</span>
            <span>💪 {event.athlete.fisico}</span>
          </div>
        )}
        <div className="mt-5 grid grid-cols-2 gap-2">
          <Button variant="secondary" size="lg" onClick={() => onResolve(false)}>{t(no)}</Button>
          <Button variant="primary" size="lg" onClick={() => onResolve(true)}>{t(yes)}</Button>
        </div>
      </div>
    </Modal>
  );
}

export function ReportModal({ report, t, locale, onClose }: { report: WeekReport; t: CareerT; locale: string; onClose: () => void }) {
  return (
    <Modal open onClose={onClose} title={t("weekRecap", { w: report.week })} footer={<Button onClick={onClose} size="lg">{t("ok")} ➜</Button>}>
      <div className="space-y-4">
        <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
          className="flex items-center justify-center gap-3 rounded-2xl bg-gradient-to-r from-accent-200 to-accent-400 py-4 text-ink-900 shadow-accent">
          <span className="text-3xl" aria-hidden="true">⭐</span>
          <span className="font-display text-3xl">{t("xpGained", { n: report.xp })}</span>
        </motion.div>
        {report.medal && (
          <motion.p initial={{ scale: 0.5 }} animate={{ scale: [0.5, 1.15, 1] }} className="text-center font-display text-2xl text-ink-900">
            {MEDAL_EMOJI[report.medal]} {t("medalWon", { medal: t(`medal_${report.medal}`) })}
          </motion.p>
        )}
        <ul className="space-y-1.5">
          {report.lines.map((l, i) => (
            <motion.li key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.05 * i }}
              className="rounded-xl bg-ink-50 px-3 py-2 text-sm text-ink-800">
              {logText(t, l)}
            </motion.li>
          ))}
        </ul>
        {report.clubResults.length > 0 && (
          <div>
            <p className="mb-2 text-sm font-bold text-ink-900">🏯 {t("athletesResults")}</p>
            <ul className="space-y-1">
              {report.clubResults.map((r, i) => (
                <li key={i} className={cn("flex justify-between rounded-xl px-3 py-2 text-sm", r.medal ? "bg-accent-50 font-bold" : "bg-ink-50")}>
                  <span>{r.name}</span>
                  <span>{r.medal ? `${MEDAL_EMOJI[r.medal]} ${t(`medal_${r.medal}`)}` : t("noMedal", { n: r.wins })}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {report.monthClosed && (
          <div>
            <p className="mb-2 text-sm font-bold text-ink-900">🧾 {t("monthClosed")}</p>
            <LedgerTable l={report.monthClosed} t={t} locale={locale} />
          </div>
        )}
      </div>
    </Modal>
  );
}

export function RestartModal({ open, busy, t, onCancel, onConfirm }: { open: boolean; busy: boolean; t: CareerT; onCancel: () => void; onConfirm: () => void }) {
  return (
    <Modal open={open} onClose={onCancel} title={t("restartTitle")} size="sm"
      footer={<><Button variant="ghost" onClick={onCancel}>{t("cancel")}</Button><Button variant="danger" loading={busy} onClick={onConfirm}>{t("restartConfirm")}</Button></>}>
      <p className="text-sm text-ink-600">{t("restartText")}</p>
    </Modal>
  );
}
