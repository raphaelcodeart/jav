"use client";

import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { JavbotChat } from "@/components/javbot/javbot-chat";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import type { BotAction, BotMessage } from "@/lib/javbot";

/** Il club della pagina aperta (/clubes/<slug>, /c/<slug>): il contesto
 *  della domanda, così "orari?" sulla pagina di un club parla di quello. */
function clubSlugOf(pathname: string | null): string | null {
  const match = /^\/(?:clubes|c)\/([^/?#]+)/.exec(pathname ?? "");
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

// Ogni pagina del sito monta la sua cornice (SiteShell), quindi anche la
// chat: la conversazione si tiene nella scheda del browser (sessionStorage),
// così aprendo un club dal bottone della chat non si ricomincia da capo.
const STORAGE_KEY = "javbot-public";

function readStored(): BotMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.slice(-40) : [];
  } catch {
    return [];
  }
}

/** JAVBOT sul sito pubblico: guida chi non è ancora cliente tra club, orari,
 *  prezzi (se il club li pubblica) e iscrizione. Nessun login e nessuna
 *  memoria sul server: la conversazione vive nella scheda del browser, e
 *  l'API non vede né restituisce dati di nessuno. */
export function PublicJavbot() {
  const { t, locale } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  // Letto al primo render: a pannello chiuso i messaggi non si disegnano,
  // quindi server e browser mostrano la stessa cosa.
  const [messages, setStoredMessages] = useState<BotMessage[]>(readStored);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setMessages(update: (prev: BotMessage[]) => BotMessage[]) {
    setStoredMessages((prev) => {
      const next = update(prev);
      try {
        window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next.slice(-40)));
      } catch {
        // Navigazione privata o spazio pieno: la chat funziona lo stesso.
      }
      return next;
    });
  }

  async function ask(text: string) {
    const stamp = Date.now();
    if (text) setMessages((prev) => [...prev, { id: `u-${stamp}`, role: "user", text, actions: [], quick_replies: [] }]);
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/public/bot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang: locale, club_slug: clubSlugOf(pathname) }),
      });
      if (!res.ok) {
        setError(res.status === 429 ? await friendlyApiError(res) : t("javbot.error"));
        return;
      }
      const data = await res.json();
      setMessages((prev) => [...prev, { id: `b-${stamp}`, role: "bot", text: data.text, actions: data.actions, quick_replies: data.quick_replies }]);
    } catch {
      setError(t("javbot.error"));
    } finally {
      setBusy(false);
    }
  }

  function onAction(action: BotAction) {
    if (action.type === "link" && action.href) {
      router.push(action.href);
      setOpen(false);
    }
  }

  return (
    <JavbotChat
      transcribeUrl={"/api/public/bot/transcribe"}
      open={open}
      setOpen={setOpen}
      // Il messaggio vuoto è il saluto: solo la prima volta che si apre.
      onOpen={() => {
        if (messages.length === 0 && !busy) void ask("");
      }}
      subtitle={t("publicBot.subtitle")}
      disclaimer={t("publicBot.disclaimer")}
      placeholder={t("publicBot.placeholder")}
      messages={messages}
      busy={busy}
      error={error}
      maxLength={500}
      onSend={(text) => void ask(text)}
      onAction={onAction}
    />
  );
}
