"use client";

import { VOICE_INPUT_ENABLED } from "@/components/javbot/use-voice-input";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { JavbotChat } from "@/components/javbot/javbot-chat";
import { friendlyApiError } from "@/lib/api-error";
import type { MessageKey } from "@/lib/i18n/messages/it";
import { useI18n } from "@/lib/i18n/provider";
import { NAV_TARGETS, requestJavbotPay, type BotAction, type BotMessage, type PayKind } from "@/lib/javbot";

const BASE = "/api/proxy/javbot";
const AVAILABLE_KEY = ["javbot", "available"];

// Gli esempi della chat vuota, per area: quello che JAVBOT sa fare davvero
// lì (le azioni di javbot/actions.py), non domande generiche. La segreteria
// (/club) lavora come lo staff.
const EXAMPLES: Record<"family" | "staff" | "athlete", MessageKey[]> = {
  family: ["jbx.ex.family1", "jbx.ex.family2", "jbx.ex.family3"],
  staff: ["jbx.ex.staff1", "jbx.ex.staff2", "jbx.ex.staff3"],
  athlete: ["jbx.ex.athlete1", "jbx.ex.athlete2", "jbx.ex.athlete3"],
};

function areaOf(pathname: string | null): "family" | "staff" | "athlete" {
  if (/^\/(staff|club)(\/|$)/.test(pathname ?? "")) return "staff";
  if (/^\/atleta(\/|$)/.test(pathname ?? "")) return "athlete";
  return "family";
}

/** JAVBOT nell'area privata: montato una volta in AppShell, quindi presente
 *  in ogni pagina di ogni ruolo. Le risposte le scrive il backend
 *  (apps/api/app/domains/javbot) nella lingua dell'interfaccia; qui si
 *  mostrano e si eseguono i bottoni:
 *  - `navigate` cambia scheda con `onNavigate` di AppShell, solo se la
 *    sezione esiste nell'area di chi scrive;
 *  - `open_pay` va alla scheda del club e chiede a family-home di aprire
 *    "Carica un pagamento" (lib/javbot.ts::requestJavbotPay);
 *  - `confirm_task` / `cancel_task` mandano al server solo l'id del compito:
 *    che cosa si esegue (l'ordine, il messaggio) è già scritto lì;
 *  - `say` lo gestisce la chat: è un messaggio come un altro.
 *  JAVBOT è solo per gli adulti: al minorenne con il solo accesso da atleta
 *  il server risponde `available: false` (o 403), e la bolla non c'è. */
export function Javbot({ navKeys, onNavigate }: { navKeys: string[]; onNavigate: (key: string) => void }) {
  const { t, locale } = useI18n();
  const area = areaOf(usePathname());
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<BotMessage[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  // Una volta per sessione: l'età non cambia da una pagina all'altra.
  // Se la verifica fallisce si nasconde: meglio niente bolla che una bolla muta.
  const { data: availability } = useQuery({
    queryKey: AVAILABLE_KEY,
    queryFn: async () => {
      const res = await fetch(`${BASE}/available`);
      if (!res.ok) return { available: false };
      return (await res.json()) as { available: boolean };
    },
    staleTime: 30 * 60_000,
    retry: false,
  });

  function navKeyFor(target: string | null | undefined): string | null {
    return (NAV_TARGETS[target ?? ""] ?? []).find((key) => navKeys.includes(key)) ?? null;
  }

  async function call(path: string, init?: RequestInit): Promise<BotMessage[] | null> {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${BASE}${path}`, {
        ...init,
        headers: init?.body ? { "Content-Type": "application/json" } : undefined,
      });
      if (res.status === 403) {
        // Il server dice che JAVBOT non è per questo conto: via la bolla.
        queryClient.setQueryData(AVAILABLE_KEY, { available: false });
        setOpen(false);
        return null;
      }
      if (!res.ok) {
        setError(res.status === 429 ? await friendlyApiError(res) : t("javbot.error"));
        return null;
      }
      const data = await res.json();
      return data.messages as BotMessage[];
    } catch {
      setError(t("javbot.error"));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function load() {
    if (loaded || busy) return;
    const loadedMessages = await call(`/conversation?lang=${locale}`);
    if (loadedMessages) {
      setMessages(loadedMessages);
      setLoaded(true);
    }
  }

  async function send(text: string) {
    const temp: BotMessage = { id: `local-${Date.now()}`, role: "user", text, actions: [], quick_replies: [] };
    setMessages((prev) => [...prev, temp]);
    const exchange = await call("/messages", { method: "POST", body: JSON.stringify({ text, lang: locale }) });
    setMessages((prev) => {
      const without = prev.filter((m) => m.id !== temp.id);
      return exchange ? [...without, ...exchange] : [...without, temp];
    });
  }

  async function decide(action: BotAction) {
    const accept = action.type === "confirm_task";
    const exchange = await call(`/tasks/${action.task_id}/${accept ? "confirm" : "cancel"}`, {
      method: "POST", body: JSON.stringify({ lang: locale }),
    });
    if (!exchange) return;
    // I bottoni della proposta, nei messaggi già a video, non si ripropongono.
    // Lo stato vero lo dice il server alla prossima apertura.
    const status = accept ? "DONE" : "CANCELLED";
    setMessages((prev) => [
      ...prev.map((m) => ({
        ...m,
        actions: m.actions.map((a) => (a.task_id === action.task_id ? { ...a, task_status: status } : a)),
      })),
      ...exchange,
    ]);
  }

  async function reset() {
    const fresh = await call("/conversation/reset", { method: "POST", body: JSON.stringify({ lang: locale }) });
    if (fresh) setMessages(fresh);
  }

  function onAction(action: BotAction) {
    if (action.type === "confirm_task" || action.type === "cancel_task") {
      void decide(action);
      return;
    }
    if (action.type === "navigate") {
      const key = navKeyFor(action.target);
      if (key) {
        onNavigate(key);
        setOpen(false);
      }
      return;
    }
    if (action.type === "open_pay") {
      onNavigate("club");
      requestJavbotPay((action.kind === "fees" ? "fees" : "choose") as PayKind);
      setOpen(false);
    }
  }

  function actionAvailable(action: BotAction): boolean {
    if (action.type === "navigate") return navKeyFor(action.target) !== null;
    if (action.type === "open_pay") return navKeys.includes("club");
    return true;
  }

  if (!availability?.available) return null;

  return (
    <JavbotChat
      transcribeUrl={VOICE_INPUT_ENABLED ? "/api/proxy/javbot/transcribe" : undefined}
      open={open}
      setOpen={setOpen}
      onOpen={() => void load()}
      subtitle={t("javbot.subtitle")}
      disclaimer={t("javbot.disclaimer")}
      placeholder={t("javbot.placeholder")}
      messages={messages}
      busy={busy}
      error={error}
      maxLength={1000}
      // Sul telefono sopra la barra delle schede; sul computer nell'angolo.
      launcherClassName="bottom-[calc(max(env(safe-area-inset-bottom),12px)+84px)] lg:bottom-6 sm:right-6"
      onSend={(text) => void send(text)}
      onAction={onAction}
      actionAvailable={actionAvailable}
      onReset={() => void reset()}
      regulationArea={area === "staff" ? "staff" : "member"}
      examples={EXAMPLES[area].map((key) => t(key))}
    />
  );
}
