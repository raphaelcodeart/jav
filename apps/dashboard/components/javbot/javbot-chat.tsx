"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";
import type { BotAction, BotMessage } from "@/lib/javbot";
import { usePrefersReducedMotion } from "@/lib/motion";

/** La chat di JAVBOT: il bottone che galleggia e il pannello. Non sa da dove
 *  arrivano le risposte: l'area privata (components/javbot/javbot.tsx) e il
 *  sito (public-bot.tsx) le passano già pronte, insieme a che cosa fare
 *  quando si tocca un bottone.
 *
 *  Sul telefono il pannello è un foglio a tutto schermo; sul computer una
 *  finestrella in basso a destra. Escape chiude e il fuoco torna al bottone;
 *  le risposte nuove si annunciano a chi usa un lettore di schermo
 *  (aria-live); con "riduci movimento" niente animazioni. */
export interface JavbotChatProps {
  subtitle: string;
  disclaimer: string;
  placeholder: string;
  messages: BotMessage[];
  busy: boolean;
  error: string | null;
  maxLength: number;
  /** Il bottone galleggiante: dove sta (sopra la barra delle schede, sul telefono). */
  launcherClassName?: string;
  onOpen: () => void;
  onSend: (text: string) => void;
  onAction: (action: BotAction) => void;
  /** Se un bottone si può mostrare (una sezione che in quest'area non c'è, no). */
  actionAvailable?: (action: BotAction) => boolean;
  onReset?: () => void;
  open: boolean;
  setOpen: (open: boolean) => void;
}

export function JavbotChat(props: JavbotChatProps) {
  const { open, setOpen, onOpen } = props;
  const { t } = useI18n();
  const reduced = usePrefersReducedMotion();
  const launcherRef = useRef<HTMLButtonElement>(null);

  function show() {
    setOpen(true);
    onOpen();
  }

  function hide() {
    setOpen(false);
    // Il fuoco torna da dove si era partiti, non in cima alla pagina.
    requestAnimationFrame(() => launcherRef.current?.focus());
  }

  return (
    <>
      <AnimatePresence>
        {!open && (
          <motion.button
            ref={launcherRef}
            type="button"
            onClick={show}
            aria-label={t("javbot.open")}
            title={t("javbot.open")}
            initial={reduced ? false : { scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={reduced ? { opacity: 0 } : { scale: 0.6, opacity: 0 }}
            whileHover={reduced ? undefined : { y: -2 }}
            whileTap={reduced ? undefined : { scale: 0.94 }}
            className={cn(
              "group fixed right-4 z-40 flex h-14 items-center gap-2 rounded-full pl-2 pr-2 sm:pr-4 cursor-pointer",
              "bg-gradient-to-b from-brand-500 to-brand-600 text-white shadow-brand ring-1 ring-inset ring-white/25",
              "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-accent-300",
              props.launcherClassName ?? "bottom-5 sm:right-6 sm:bottom-6",
            )}
          >
            <BotAvatar size="md" />
            <span className="hidden sm:inline font-display text-sm tracking-wide">JAVBOT</span>
          </motion.button>
        )}
      </AnimatePresence>
      <AnimatePresence>{open && <ChatPanel {...props} reduced={reduced} onClose={hide} />}</AnimatePresence>
    </>
  );
}

function BotAvatar({ size = "md" }: { size?: "sm" | "md" }) {
  const box = size === "sm" ? "h-8 w-8" : "h-10 w-10";
  return (
    <span aria-hidden="true" className={cn("relative flex shrink-0 items-center justify-center rounded-full bg-white text-brand-600 shadow-soft", box)}>
      <svg viewBox="0 0 24 24" className={size === "sm" ? "h-5 w-5" : "h-6 w-6"} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3v3" />
        <circle cx="12" cy="2.5" r="1" fill="currentColor" />
        <rect x="4" y="6" width="16" height="12" rx="4" />
        <circle cx="9" cy="12" r="1.4" fill="currentColor" />
        <circle cx="15" cy="12" r="1.4" fill="currentColor" />
        <path d="M9.5 15.5h5" />
        <path d="M2 11v3M22 11v3" />
      </svg>
      <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full bg-emerald-500 ring-2 ring-white" />
    </span>
  );
}

function ChatPanel(props: JavbotChatProps & { reduced: boolean; onClose: () => void }) {
  const { messages, busy, error, reduced, onClose, onSend, onAction, actionAvailable, onReset, maxLength } = props;
  const { t } = useI18n();
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  // Il fuoco entra nella chat. Sul telefono sul pannello e non sul campo di
  // testo: la tastiera che sale da sola coprirebbe la risposta.
  useEffect(() => {
    if (window.matchMedia("(min-width: 640px)").matches) inputRef.current?.focus();
    else panelRef.current?.focus();
  }, []);

  // Sempre in fondo: l'ultima risposta è quella che conta.
  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTo({ top: list.scrollHeight, behavior: reduced ? "auto" : "smooth" });
  }, [messages.length, busy, reduced]);

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setDraft("");
    onSend(text);
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
    }
  }

  function onComposerKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  const lastBot = [...messages].reverse().find((m) => m.role === "bot");
  const quickReplies = !busy && lastBot && messages[messages.length - 1]?.id === lastBot.id ? lastBot.quick_replies : [];

  return (
    <motion.div
      ref={panelRef}
      tabIndex={-1}
      role="dialog"
      aria-labelledby={titleId}
      onKeyDown={onKeyDown}
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 28, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={reduced ? { opacity: 0 } : { opacity: 0, y: 20, scale: 0.98 }}
      transition={{ type: "spring", stiffness: 380, damping: 34 }}
      className={cn(
        "fixed z-[90] flex flex-col overflow-hidden bg-white outline-none",
        // Telefono: un foglio a tutto schermo. Computer: una finestra.
        "inset-0 sm:inset-auto sm:bottom-6 sm:right-6 sm:h-[min(680px,calc(100vh-3rem))] sm:w-[400px]",
        "sm:rounded-[28px] sm:shadow-lift sm:ring-1 sm:ring-ink-200/80",
      )}
    >
      <header className="relative flex items-center gap-3 bg-gradient-to-br from-brand-500 via-brand-600 to-brand-700 px-4 pb-4 pt-[max(env(safe-area-inset-top),16px)] text-white">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(18rem_8rem_at_100%_0%,rgb(249_228_15/0.28),transparent_70%)]" />
        <BotAvatar />
        <div className="relative min-w-0 flex-1">
          <h2 id={titleId} className="font-display text-lg leading-tight tracking-wide">JAVBOT</h2>
          <p className="truncate text-xs text-white/85">{props.subtitle}</p>
        </div>
        {onReset && (
          <HeaderButton label={t("javbot.reset")} onClick={onReset} disabled={busy}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h5M20 20v-5h-5M5.1 15A7 7 0 0018.4 17M18.9 9A7 7 0 005.6 7" />
          </HeaderButton>
        )}
        <HeaderButton label={t("javbot.close")} onClick={onClose}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </HeaderButton>
      </header>

      <div
        ref={listRef}
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-busy={busy}
        className="flex-1 space-y-3 overflow-y-auto overscroll-contain bg-ink-50/60 px-3 py-4"
      >
        <p className="mx-auto max-w-[18rem] text-center text-[11px] leading-snug text-ink-400">{props.disclaimer}</p>
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} reduced={reduced} onAction={onAction} actionAvailable={actionAvailable} busy={busy} />
        ))}
        {busy && <Typing reduced={reduced} />}
        {error && (
          <p role="alert" className="mx-2 rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-rose-200">
            {error}
          </p>
        )}
      </div>

      {quickReplies.length > 0 && (
        <div className="flex gap-2 overflow-x-auto border-t border-ink-100 bg-white px-3 py-2.5 [scrollbar-width:none]">
          {quickReplies.map((q, i) => (
            <motion.button
              key={q}
              type="button"
              initial={reduced ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: reduced ? 0 : i * 0.04 }}
              onClick={() => onSend(q)}
              className="shrink-0 cursor-pointer rounded-full bg-white px-3.5 py-1.5 text-xs font-semibold text-brand-700 ring-1 ring-brand-200 transition-colors hover:bg-brand-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
            >
              {q}
            </motion.button>
          ))}
        </div>
      )}

      <form onSubmit={submit} className="flex items-end gap-2 border-t border-ink-100 bg-white px-3 pt-3 pb-[max(env(safe-area-inset-bottom),12px)]">
        <label className="sr-only" htmlFor={`${titleId}-input`}>{props.placeholder}</label>
        <textarea
          id={`${titleId}-input`}
          ref={inputRef}
          rows={1}
          value={draft}
          maxLength={maxLength}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onComposerKey}
          placeholder={props.placeholder}
          className="max-h-32 min-h-11 flex-1 resize-none rounded-2xl bg-ink-50 px-4 py-2.5 text-[15px] text-ink-900 ring-1 ring-ink-200 placeholder:text-ink-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-400"
        />
        <motion.button
          type="submit"
          disabled={busy || !draft.trim()}
          whileTap={reduced ? undefined : { scale: 0.92 }}
          aria-label={t("javbot.send")}
          className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-full bg-gradient-to-b from-brand-500 to-brand-600 text-white shadow-brand disabled:cursor-not-allowed disabled:opacity-40"
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h13M13 6l6 6-6 6" />
          </svg>
        </motion.button>
      </form>
    </motion.div>
  );
}

function HeaderButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="relative flex h-10 w-10 cursor-pointer items-center justify-center rounded-full text-white/90 transition-colors hover:bg-white/15 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white disabled:opacity-50"
    >
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
        {children}
      </svg>
    </button>
  );
}

function MessageBubble({ message, reduced, onAction, actionAvailable, busy }: {
  message: BotMessage; reduced: boolean; onAction: (a: BotAction) => void;
  actionAvailable?: (a: BotAction) => boolean; busy: boolean;
}) {
  const { t } = useI18n();
  const mine = message.role === "user";
  const actions = message.actions.filter((a) => actionAvailable?.(a) ?? true);
  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className={cn("flex flex-col gap-1.5", mine ? "items-end" : "items-start")}
    >
      <span className="sr-only">{mine ? t("javbot.you") : "JAVBOT"}:</span>
      <div
        className={cn(
          "max-w-[88%] whitespace-pre-line break-words rounded-3xl px-4 py-2.5 text-[15px] leading-relaxed",
          mine
            ? "rounded-br-lg bg-gradient-to-b from-brand-500 to-brand-600 text-white shadow-brand"
            : "rounded-bl-lg bg-white text-ink-800 shadow-soft ring-1 ring-ink-100",
        )}
      >
        {message.text}
      </div>
      {actions.length > 0 && (
        <div className="flex max-w-[92%] flex-wrap gap-2">
          {actions.map((a, i) => (
            <ActionButton key={`${a.type}-${a.task_id ?? a.target ?? a.href ?? i}`} action={a} onAction={onAction} busy={busy} />
          ))}
        </div>
      )}
    </motion.div>
  );
}

function ActionButton({ action, onAction, busy }: { action: BotAction; onAction: (a: BotAction) => void; busy: boolean }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const base = "inline-flex min-h-9 items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-semibold transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 disabled:cursor-not-allowed disabled:opacity-50";

  // Una proposta già decisa: si dice com'è finita, non si ripropone.
  if ((action.type === "confirm_task" || action.type === "cancel_task") && action.task_status && action.task_status !== "PENDING") {
    if (action.type === "cancel_task") return null;
    const done = action.task_status === "DONE";
    return (
      <span className={cn(base, "cursor-default", done ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200" : "bg-ink-100 text-ink-500")}>
        {done ? `✓ ${t("javbot.done")}` : t("javbot.cancelled")}
      </span>
    );
  }
  if (action.type === "link" && action.href) {
    return (
      <Link href={action.href} className={cn(base, "bg-white text-brand-700 ring-1 ring-brand-200 hover:bg-brand-50")}>
        {action.label} <span aria-hidden="true">→</span>
      </Link>
    );
  }
  if (action.type === "copy" && action.value) {
    return (
      <button
        type="button"
        className={cn(base, "bg-white text-ink-800 ring-1 ring-ink-200 hover:bg-ink-50")}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(action.value ?? "");
            setCopied(true);
          } catch {
            setCopied(false);
          }
        }}
      >
        {copied ? `✓ ${t("javbot.copied")}` : action.label}
      </button>
    );
  }
  const tone =
    action.type === "confirm_task"
      ? "bg-gradient-to-b from-brand-500 to-brand-600 text-white shadow-brand hover:from-brand-400"
      : action.type === "cancel_task"
        ? "text-ink-600 hover:bg-ink-100"
        : "bg-white text-ink-800 ring-1 ring-ink-200 hover:ring-brand-300 hover:text-brand-700";
  return (
    <button type="button" disabled={busy} onClick={() => onAction(action)} className={cn(base, tone)}>
      {action.label}
    </button>
  );
}

function Typing({ reduced }: { reduced: boolean }) {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-2" aria-label={t("javbot.typing")} role="status">
      <div className="flex items-center gap-1 rounded-3xl rounded-bl-lg bg-white px-4 py-3 shadow-soft ring-1 ring-ink-100">
        {[0, 1, 2].map((i) =>
          reduced ? (
            <span key={i} className="h-2 w-2 rounded-full bg-ink-300" />
          ) : (
            <motion.span
              key={i}
              className="h-2 w-2 rounded-full bg-brand-400"
              animate={{ y: [0, -4, 0], opacity: [0.5, 1, 0.5] }}
              transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15, ease: "easeInOut" }}
            />
          ),
        )}
      </div>
      <span className="sr-only">{t("javbot.typing")}</span>
    </div>
  );
}
