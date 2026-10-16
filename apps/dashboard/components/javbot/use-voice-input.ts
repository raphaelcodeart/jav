"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

/** Il microfono di JAVBOT (docs/javbot.md, «Il microfono»): registra la voce
 *  nel browser, la manda a `url` (l'API la gira a Whisper sul nostro server,
 *  non la salva) e passa il testo a `onText`. Il testo va nel campo: chi
 *  parla lo rilegge e lo invia, niente parte da solo.
 *
 *  Senza MediaRecorder o senza microfono `supported` è falso e il bottone
 *  non compare. Dopo `MAX_SECONDS` la registrazione si ferma da sola. */
export type VoiceState = "idle" | "recording" | "transcribing";
export type VoiceError = "denied" | "tooLong" | "busy" | "empty" | "error";

export const MAX_SECONDS = 60;
// Opus dove c'è (Chrome, Firefox, Android), mp4/aac su Safari e iPhone.
const MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

const noSubscribe = () => () => {};
const canRecord = () => typeof MediaRecorder !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);

function pickMime(): string | undefined {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return undefined;
  return MIME_TYPES.find((m) => MediaRecorder.isTypeSupported(m));
}

export function useVoiceInput({ url, lang, onText }: { url?: string; lang: string; onText: (text: string) => void }) {
  // Solo nel browser: sul server non c'è navigator, e la prima resa deve
  // essere uguale nei due posti.
  const supported = useSyncExternalStore(noSubscribe, canRecord, () => false) && Boolean(url);
  const [state, setState] = useState<VoiceState>("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<VoiceError | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const cancelled = useRef(false);
  const onTextRef = useRef(onText);
  useEffect(() => {
    onTextRef.current = onText;
  }, [onText]);

  const release = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }, []);

  // Chiudendo la chat a metà: il microfono si spegne e niente si manda.
  useEffect(() => () => {
    cancelled.current = true;
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
    release();
  }, [release]);

  const send = useCallback(async (blob: Blob) => {
    if (!url) return;
    if (blob.size < 1000) {
      setError("empty");
      setState("idle");
      return;
    }
    setState("transcribing");
    try {
      const form = new FormData();
      const ext = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
      form.append("audio", blob, `voice.${ext}`);
      form.append("lang", lang);
      const res = await fetch(url, { method: "POST", body: form });
      if (!res.ok) {
        setError(res.status === 413 ? "tooLong" : res.status === 503 || res.status === 429 ? "busy" : "error");
        return;
      }
      const text = String((await res.json()).text ?? "").trim();
      if (!text) setError("empty");
      else onTextRef.current(text);
    } catch {
      setError("error");
    } finally {
      setState("idle");
    }
  }, [url, lang]);

  const stop = useCallback(() => {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
  }, []);

  const start = useCallback(async () => {
    if (state !== "idle") return;
    setError(null);
    let media: MediaStream;
    try {
      media = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      setError("denied");
      return;
    }
    const mime = pickMime();
    const rec = mime ? new MediaRecorder(media, { mimeType: mime }) : new MediaRecorder(media);
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    rec.onstop = () => {
      release();
      recorder.current = null;
      if (cancelled.current) return;
      void send(new Blob(chunks, { type: rec.mimeType || mime || "audio/webm" }));
    };
    stream.current = media;
    recorder.current = rec;
    cancelled.current = false;
    rec.start();
    setSeconds(0);
    setState("recording");
    const began = Date.now();
    timer.current = setInterval(() => {
      const s = Math.floor((Date.now() - began) / 1000);
      setSeconds(s);
      if (s >= MAX_SECONDS) stop();
    }, 250);
  }, [state, release, send, stop]);

  /** Ferma senza trascrivere. */
  const cancel = useCallback(() => {
    cancelled.current = true;
    stop();
    setState("idle");
  }, [stop]);

  return { supported, state, seconds, error, start, stop, cancel, clearError: () => setError(null) };
}
