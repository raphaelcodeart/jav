"use client";

import { VOICE_INPUT_ENABLED } from "@/components/javbot/use-voice-input";
import { useState } from "react";
import { JavbotChat } from "@/components/javbot/javbot-chat";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import { NAV_TARGETS, requestJavbotPay, type BotAction, type BotMessage, type PayKind } from "@/lib/javbot";

const BASE = "/api/proxy/javbot";

/** JAVBOT nell'area privata: montato una volta in AppShell, quindi presente
 *  in ogni pagina di ogni ruolo. Le risposte le scrive il backend
 *  (apps/api/app/domains/javbot) nella lingua dell'interfaccia; qui si
 *  mostrano e si eseguono i bottoni:
 *  - `navigate` cambia scheda con `onNavigate` di AppShell, solo se la
 *    sezione esiste nell'area di chi scrive;
 *  - `open_pay` va alla scheda del club e chiede a family-home di aprire
 *    "Carica un pagamento" (lib/javbot.ts::requestJavbotPay);
 *  - `confirm_task` / `cancel_task` mandano al server solo l'id del compito:
 *    che cosa si esegue (l'ordine, il messaggio) è già scritto lì. */
export function Javbot({ navKeys, onNavigate }: { navKeys: string[]; onNavigate: (key: string) => void }) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<BotMessage[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    />
  );
}
