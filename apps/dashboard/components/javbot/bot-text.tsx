"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useI18n } from "@/lib/i18n/provider";

// Il testo di JAVBOT ha un Markdown minimo (javbot/schemas.py::BotMessageRead):
// **grassetto**, righe che iniziano con «- » o «• » (elenchi), link nudi o
// [etichetta](url), a capo, e i rimandi alle fonti [1]. Si costruiscono i
// nodi React a mano, mai dangerouslySetInnerHTML: il testo può contenere
// pezzi di documenti caricati da altri, e quello che non è uno di questi
// segni resta testo e basta.

const LIST_ITEM = /^\s*[-•]\s+(.*)$/;
// Nell'ordine: grassetto, link con etichetta, link nudo, rimando a una fonte.
const INLINE = /\*\*(.+?)\*\*|\[([^\]\n]+)\]\(([^)\s]+)\)|(https?:\/\/[^\s<>()]*[^\s<>().,;:!?'"»])|\[(\d{1,2})\]/g;

/** Solo http(s) o un percorso di questo sito: niente javascript:, data:, //altrove. */
function safeHref(raw: string): string | null {
  const href = raw.trim();
  if (/^https?:\/\//i.test(href)) return href;
  if (href.startsWith("/") && !href.startsWith("//") && !href.startsWith("/\\")) return href;
  return null;
}

function BotLink({ href, children }: { href: string; children: ReactNode }) {
  const cls = "font-semibold text-brand-700 underline decoration-brand-300 underline-offset-2 break-words hover:decoration-brand-600";
  if (href.startsWith("/")) return <Link href={href} className={cls}>{children}</Link>;
  return <a href={href} target="_blank" rel="noopener noreferrer" className={cls}>{children}</a>;
}

function inline(text: string, key: string, sourceLabel: (n: string) => string, bold = false): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(INLINE)) {
    const start = m.index ?? 0;
    if (start > last) out.push(text.slice(last, start));
    const k = `${key}-${i++}`;
    if (m[1] !== undefined) {
      // Dentro il grassetto valgono link e fonti, non un altro grassetto.
      out.push(bold ? m[0] : <strong key={k} className="font-semibold text-ink-900">{inline(m[1], k, sourceLabel, true)}</strong>);
    } else if (m[2] !== undefined && m[3] !== undefined) {
      const href = safeHref(m[3]);
      out.push(href ? <BotLink key={k} href={href}>{m[2]}</BotLink> : m[2]);
    } else if (m[4] !== undefined) {
      out.push(<BotLink key={k} href={m[4]}>{m[4].replace(/^https?:\/\/(www\.)?/i, "")}</BotLink>);
    } else if (m[5] !== undefined) {
      out.push(
        <sup key={k} className="mx-0.5 inline-flex h-4 min-w-4 -translate-y-0.5 items-center justify-center rounded-full bg-brand-100 px-1 align-baseline text-[10px] font-bold leading-none text-brand-700"
          aria-label={sourceLabel(m[5])} title={sourceLabel(m[5])}>
          {m[5]}
        </sup>,
      );
    }
    last = start + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Block = { kind: "p"; lines: string[] } | { kind: "ul"; items: string[] };

function blocks(text: string): Block[] {
  const out: Block[] = [];
  for (const line of text.replace(/\r\n?/g, "\n").split("\n")) {
    const item = LIST_ITEM.exec(line);
    const prev = out[out.length - 1];
    if (item) {
      if (prev?.kind === "ul") prev.items.push(item[1] ?? "");
      else out.push({ kind: "ul", items: [item[1] ?? ""] });
    } else if (!line.trim()) {
      // Una riga vuota chiude il paragrafo: il prossimo testo ne apre uno nuovo.
      if (prev) out.push({ kind: "p", lines: [] });
    } else if (prev?.kind === "p") {
      prev.lines.push(line);
    } else {
      out.push({ kind: "p", lines: [line] });
    }
  }
  return out.filter((b) => (b.kind === "p" ? b.lines.length > 0 : b.items.length > 0));
}

/** Il testo di un messaggio di JAVBOT, con paragrafi, elenchi, grassetti e link. */
export function BotText({ text }: { text: string }) {
  const { t } = useI18n();
  const sourceLabel = (n: string) => t("jbx.sourceRef", { n });
  return (
    <div className="space-y-2">
      {blocks(text).map((b, bi) =>
        b.kind === "ul" ? (
          <ul key={bi} className="space-y-1">
            {b.items.map((item, ii) => (
              <li key={ii} className="flex gap-2">
                <span aria-hidden="true" className="mt-[0.6em] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400" />
                <span className="min-w-0">{inline(item, `${bi}-${ii}`, sourceLabel)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p key={bi}>
            {b.lines.map((line, li) => (
              <span key={li}>
                {li > 0 && <br />}
                {inline(line, `${bi}-${li}`, sourceLabel)}
              </span>
            ))}
          </p>
        ),
      )}
    </div>
  );
}
