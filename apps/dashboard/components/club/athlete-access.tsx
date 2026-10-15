"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { clubGet, clubSend } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

interface AthleteLogin {
  athlete_id: string;
  has_login: boolean;
  is_self: boolean;
  username: string | null;
  email: string | null;
  active: boolean;
  qr_active_until: string | null;
}

interface AthleteQr extends AthleteLogin {
  url: string;
  qr_image: string;
}

/** L'accesso dell'atleta alla sua area, gestito dal titolare del conto
 *  (club/athlete_access.py): nome utente e password (o l'email del ragazzo),
 *  il QR per entrare al volo, spegnere l'accesso. Il QR si vede una volta
 *  sola, appena creato: il codice in chiaro non si salva da nessuna parte. */
export function AthleteAccess({ athleteId, firstName }: { athleteId: string; firstName: string }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = ["club", "athlete", athleteId, "login"];
  const { data, isLoading } = useQuery({ queryKey: key, queryFn: () => clubGet<AthleteLogin>(`/athletes/${athleteId}/login`) });
  const [username, setUsername] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [qr, setQr] = useState<AthleteQr | null>(null);

  if (isLoading || !data) return <Skeleton className="h-48" />;
  if (data.is_self) {
    return (
      <div className="rounded-2xl bg-ink-50 p-5 text-sm text-ink-700">
        <p>{t("athleteAccess.self")}</p>
        <a href={`/atleta?a=${athleteId}`} className="mt-3 inline-flex font-semibold text-brand-700 hover:underline">{t("athleteAccess.openArea")} →</a>
      </div>
    );
  }

  const shownUsername = username ?? data.username ?? suggest(firstName);
  const shownEmail = email ?? data.email ?? "";

  async function run<T>(fn: () => Promise<T>, ok: string): Promise<T | undefined> {
    setBusy(true);
    try {
      const out = await fn();
      await queryClient.invalidateQueries({ queryKey: key });
      toast({ tone: "success", title: ok });
      return out;
    } catch (e) {
      toast({ tone: "error", title: t("athleteAccess.failed"), text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    const body: Record<string, string> = {};
    if (!data!.has_login || shownUsername !== data!.username) body.username = shownUsername;
    if (shownEmail !== (data!.email ?? "")) body.email = shownEmail;
    if (password) body.password = password;
    const out = await run(() => clubSend<AthleteLogin>(`/athletes/${athleteId}/login`, "PUT", body), data!.has_login ? t("athleteAccess.updated") : t("athleteAccess.created"));
    if (out) { setPassword(""); setUsername(null); setEmail(null); }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-gradient-to-br from-brand-50 to-white p-4 ring-1 ring-brand-100">
        <div>
          <p className="font-semibold text-ink-900">{t("athleteAccess.title", { name: firstName })}</p>
          <p className="text-sm text-ink-600">{t("athleteAccess.intro")}</p>
        </div>
        {data.has_login ? (
          data.active ? <Badge tone="success" dot>{t("athleteAccess.on")}</Badge> : <Badge tone="warning" dot>{t("athleteAccess.off")}</Badge>
        ) : <Badge tone="neutral">{t("athleteAccess.none")}</Badge>}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("athleteAccess.username")} htmlFor="aa-user" hint={t("athleteAccess.usernameHint")}>
          <Input id="aa-user" autoCapitalize="none" spellCheck={false} maxLength={40} value={shownUsername}
            onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/\s+/g, ""))} />
        </Field>
        <Field label={data.has_login ? t("athleteAccess.newPassword") : t("athleteAccess.password")} htmlFor="aa-pass" hint={t("athleteAccess.passwordHint")}>
          <Input id="aa-pass" type="text" autoComplete="new-password" minLength={6} maxLength={128} value={password}
            onChange={(e) => setPassword(e.target.value)} placeholder={data.has_login ? "••••••" : ""} />
        </Field>
        <div className="sm:col-span-2">
          <Field label={t("athleteAccess.email")} htmlFor="aa-mail" hint={t("athleteAccess.emailHint")}>
            <Input id="aa-mail" type="email" maxLength={255} value={shownEmail} onChange={(e) => setEmail(e.target.value)} />
          </Field>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button loading={busy} onClick={save} disabled={!data.has_login && password.length < 6}>
          {data.has_login ? t("athleteAccess.save") : t("athleteAccess.create")}
        </Button>
        {data.has_login && data.active && (
          <Button variant="ghost" className="text-rose-600" disabled={busy}
            onClick={() => run(() => clubSend(`/athletes/${athleteId}/login`, "DELETE"), t("athleteAccess.disabled"))}>
            {t("athleteAccess.disable")}
          </Button>
        )}
        {data.has_login && (
          <a href={`/atleta?a=${athleteId}`} className="inline-flex h-10 items-center rounded-xl px-4 text-sm font-semibold text-brand-700 hover:bg-brand-50">
            {t("athleteAccess.openArea")} →
          </a>
        )}
      </div>

      {data.has_login && data.active && (
        <section className="rounded-2xl border border-ink-900/10 bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-semibold text-ink-900">{t("athleteAccess.qrTitle")}</p>
              <p className="text-sm text-ink-600">{t("athleteAccess.qrText")}</p>
              {data.qr_active_until && !qr && (
                <p className="mt-1 text-xs text-ink-500">{t("athleteAccess.qrActive", { date: fmt.shortDate(data.qr_active_until) })}</p>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled={busy}
                onClick={async () => { const out = await run(() => clubSend<AthleteQr>(`/athletes/${athleteId}/login/qr`, "POST"), t("athleteAccess.qrCreated")); if (out) setQr(out); }}>
                {data.qr_active_until ? t("athleteAccess.qrNew") : t("athleteAccess.qrCreate")}
              </Button>
              {data.qr_active_until && (
                <Button variant="ghost" size="sm" className="text-rose-600" disabled={busy}
                  onClick={async () => { await run(() => clubSend(`/athletes/${athleteId}/login/qr`, "DELETE"), t("athleteAccess.qrRevoked")); setQr(null); }}>
                  {t("athleteAccess.qrRevoke")}
                </Button>
              )}
            </div>
          </div>
          {qr && (
            <div className="mt-4 flex flex-col items-center gap-3 rounded-2xl bg-ink-50 p-4 text-center">
              {/* eslint-disable-next-line @next/next/no-img-element -- QR disegnato dall'API, data URI */}
              <img src={qr.qr_image} alt={t("athleteAccess.qrAlt", { name: firstName })} className="h-56 w-56 rounded-xl bg-white p-2" />
              <p className="max-w-sm text-xs text-ink-600">{t("athleteAccess.qrOnce")}</p>
              <div className="flex flex-wrap justify-center gap-2">
                <Button size="sm" variant="secondary" onClick={() => window.print()}>🖨 {t("athleteAccess.print")}</Button>
                <Button size="sm" variant="secondary" onClick={async () => { await navigator.clipboard.writeText(qr.url); toast({ tone: "success", title: t("athleteAccess.copied") }); }}>
                  🔗 {t("athleteAccess.copyLink")}
                </Button>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

/** "Tiago" → "tiago" più due cifre: un'idea, che il genitore cambia. */
function suggest(firstName: string): string {
  const base = firstName.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "") || "atleta";
  return `${base}.${String(Math.abs(hash(firstName)) % 90 + 10)}`;
}

function hash(s: string): number {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0;
  return h;
}
