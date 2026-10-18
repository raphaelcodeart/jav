"use client";

import { motion } from "motion/react";
import { BeltSwatch, beltBackground } from "@/components/game/belt";
import { GAME_INTL, QUALIFICATION_LABELS, useGameText, type GameLang } from "@/components/game/i18n";
import { cn } from "@/lib/cn";

// Il medagliere della Dojo Academy e il diploma da scaricare: un'immagine
// disegnata nel browser, per gioco. C'è scritto FAC-SÍMILE in diagonale e,
// in fondo, che non è un documento ufficiale né una graduação federativa.

export interface Diploma { code: string; kind: "GRADE" | "QUALIFICATION"; pct: number; on: string }

const TEXT: Record<GameLang, Record<"title" | "certify" | "grade" | "qual" | "with" | "on" | "cheers" | "stamp" | "note" | "medals" | "medalsText" | "none" | "download", string>> = {
  pt: {
    title: "Diploma", certify: "Certifica-se, no jogo e com muito orgulho, que", grade: "foi aprovado(a) no exame de",
    qual: "obteve a qualificação de", with: "com", on: "em", cheers: "Parabéns! Grande sucesso!", stamp: "FAC-SÍMILE",
    note: "Diploma do jogo JAV Games · Dojo Academy. Não é um documento oficial nem uma graduação federativa.",
    medals: "Medalheiro", medalsText: "Cada graduação e qualificação dá uma medalha e um diploma (a fingir) para descarregar.",
    none: "Ainda sem medalhas: passa o primeiro exame!", download: "Descarregar diploma",
  },
  it: {
    title: "Diploma", certify: "Si attesta, per gioco e con grande orgoglio, che", grade: "ha superato l'esame di",
    qual: "ha ottenuto la qualifica di", with: "con il", on: "il", cheers: "Complimenti! Grande successo!", stamp: "FAC-SIMILE",
    note: "Diploma del gioco JAV Games · Dojo Academy. Non è un documento ufficiale né un grado federale.",
    medals: "Medagliere", medalsText: "Ogni grado e qualifica dà una medaglia e un diploma (per finta) da scaricare.",
    none: "Ancora nessuna medaglia: supera il primo esame!", download: "Scarica il diploma",
  },
  en: {
    title: "Diploma", certify: "This certifies, in the game and with great pride, that", grade: "passed the exam for",
    qual: "earned the qualification of", with: "with", on: "on", cheers: "Congratulations! A great success!", stamp: "SPECIMEN",
    note: "JAV Games · Dojo Academy game diploma. Not an official document or a federation grade.",
    medals: "Medal case", medalsText: "Every grade and qualification earns a medal and a (make-believe) diploma to download.",
    none: "No medals yet: pass your first exam!", download: "Download diploma",
  },
};

function fill(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, grade: string) {
  // La cintura sul diploma: stessi colori di BeltSwatch, disegnati a mano.
  const bg = beltBackground(grade);
  const colors: string[] = bg.match(/#[0-9a-f]{6}/gi) ?? [bg];
  const c = (i: number) => colors[i] ?? "#000000";
  if (bg.startsWith("repeating")) {
    for (let i = 0; i * (w / 7) < w; i++) { ctx.fillStyle = c(i % 2); ctx.fillRect(x + i * (w / 7), y, w / 7 + 1, h); }
  } else if (colors.length === 2) {
    ctx.fillStyle = c(0); ctx.fillRect(x, y, w / 2, h);
    ctx.fillStyle = c(1); ctx.fillRect(x + w / 2, y, w / 2, h);
  } else { ctx.fillStyle = c(0); ctx.fillRect(x, y, w, h); }
  ctx.strokeStyle = "rgba(0,0,0,.35)"; ctx.lineWidth = 3; ctx.strokeRect(x, y, w, h);
  ctx.fillStyle = "rgba(0,0,0,.18)"; ctx.fillRect(x + w / 2 - w * 0.08, y, w * 0.16, h);
}

export function downloadDiploma(d: Diploma, opts: { name: string; label: string; lang: GameLang }) {
  const t = TEXT[opts.lang];
  const W = 1600, H = 1130;
  const canvas = document.createElement("canvas");
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const serif = "Georgia, 'Times New Roman', serif";
  ctx.fillStyle = "#fffaf0"; ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = "#b45309"; ctx.lineWidth = 14; ctx.strokeRect(40, 40, W - 80, H - 80);
  ctx.strokeStyle = "#1e1b4b"; ctx.lineWidth = 3; ctx.strokeRect(70, 70, W - 140, H - 140);
  // La filigrana.
  ctx.save(); ctx.translate(W / 2, H / 2); ctx.rotate(-0.42);
  ctx.font = `bold 210px ${serif}`; ctx.fillStyle = "rgba(220,38,38,.09)"; ctx.textAlign = "center"; ctx.fillText(t.stamp, 0, 70);
  ctx.restore();
  ctx.textAlign = "center"; ctx.fillStyle = "#1e1b4b";
  ctx.font = `600 34px ${serif}`; ctx.fillText("JAV GAMES · DOJO ACADEMY", W / 2, 170);
  ctx.font = `bold 110px ${serif}`; ctx.fillText(t.title, W / 2, 300);
  ctx.font = `italic 36px ${serif}`; ctx.fillStyle = "#44403c"; ctx.fillText(t.certify, W / 2, 390);
  ctx.font = `bold 78px ${serif}`; ctx.fillStyle = "#111827"; ctx.fillText(opts.name, W / 2, 490, W - 260);
  ctx.font = `italic 36px ${serif}`; ctx.fillStyle = "#44403c"; ctx.fillText(d.kind === "GRADE" ? t.grade : t.qual, W / 2, 570);
  ctx.font = `bold 70px ${serif}`; ctx.fillStyle = "#b45309";
  const icon = d.kind === "QUALIFICATION" ? `${QUALIFICATION_LABELS[d.code]?.icon ?? ""} ` : "";
  ctx.fillText(`${icon}${opts.label}`, W / 2, 665, W - 260);
  if (d.kind === "GRADE") fill(ctx, W / 2 - 200, 700, 400, 46, d.code);
  const date = new Date(`${d.on}T12:00:00`).toLocaleDateString(GAME_INTL[opts.lang], { day: "numeric", month: "long", year: "numeric" });
  ctx.font = `34px ${serif}`; ctx.fillStyle = "#1f2937"; ctx.fillText(`${t.with} ${d.pct}% · ${t.on} ${date}`, W / 2, 815);
  ctx.font = `bold 46px ${serif}`; ctx.fillStyle = "#15803d"; ctx.fillText(`🎉 ${t.cheers} 🎉`, W / 2, 895);
  // Il timbro del gioco.
  ctx.save(); ctx.translate(W - 250, H - 250); ctx.rotate(-0.25);
  ctx.strokeStyle = "rgba(220,38,38,.75)"; ctx.lineWidth = 6; ctx.beginPath(); ctx.arc(0, 0, 105, 0, Math.PI * 2); ctx.stroke();
  ctx.font = `bold 30px ${serif}`; ctx.fillStyle = "rgba(220,38,38,.8)"; ctx.fillText(t.stamp, 0, 10);
  ctx.restore();
  ctx.font = `24px ${serif}`; ctx.fillStyle = "#6b7280"; ctx.fillText(t.note, W / 2, H - 110, W - 200);
  const a = document.createElement("a");
  a.href = canvas.toDataURL("image/png");
  a.download = `dojo-academy-${d.code.toLowerCase()}.png`;
  a.click();
}

/** Il medagliere: una medaglia per grado e qualifica, ognuna con il suo diploma. */
export function MedalCase({ diplomas, name }: { diplomas: Diploma[]; name: string }) {
  const { grade, qualification, lang } = useGameText();
  const t = TEXT[lang];
  return (
    <section className="rounded-3xl bg-white p-5 shadow-soft ring-1 ring-ink-900/5">
      <h2 className="text-lg text-ink-900">🏅 {t.medals}</h2>
      <p className="mt-1 text-sm text-ink-500">{t.medalsText}</p>
      {diplomas.length === 0 ? <p className="mt-4 rounded-2xl bg-ink-50 p-4 text-sm text-ink-600">{t.none}</p> : (
        <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {diplomas.map((d, i) => {
            const label = d.kind === "GRADE" ? grade(d.code) : qualification(d.code);
            return (
              <motion.li key={d.code} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.03 }}>
                <button type="button" onClick={() => downloadDiploma(d, { name, label, lang })} title={t.download}
                  className="group flex h-full w-full cursor-pointer flex-col items-center gap-2 rounded-2xl bg-gradient-to-b from-amber-50 to-white p-3 text-center ring-1 ring-amber-200 transition hover:-translate-y-0.5 hover:shadow-soft">
                  <span className={cn("flex h-14 w-14 items-center justify-center rounded-full text-2xl shadow-inner ring-4",
                    d.kind === "GRADE" ? "bg-gradient-to-br from-amber-300 to-amber-500 ring-amber-200" : "bg-gradient-to-br from-emerald-300 to-emerald-500 ring-emerald-200")}>
                    {d.kind === "GRADE" ? "🥋" : QUALIFICATION_LABELS[d.code]?.icon}
                  </span>
                  {d.kind === "GRADE" && <BeltSwatch grade={d.code} className="h-2.5 w-12" />}
                  <span className="text-sm font-semibold leading-tight text-ink-900">{label}</span>
                  <span className="text-xs text-ink-500">{d.pct}%</span>
                  <span className="text-xs font-semibold text-brand-700 group-hover:underline">⬇ {t.download}</span>
                </button>
              </motion.li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
