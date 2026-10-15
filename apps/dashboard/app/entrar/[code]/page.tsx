"use client";

import { use, useEffect, useRef, useState } from "react";
import { AuthLayout } from "@/components/auth/auth-layout";
import { useI18n } from "@/lib/i18n/provider";

/** Dove porta il QR dell'atleta: il codice vale come nome utente e password
 *  insieme. Si entra e si va dritti nella propria area. */
export default function QrLogin({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const { t } = useI18n();
  const [error, setError] = useState<string | null>(null);
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    fetch("/api/auth/login-code", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }) })
      .then(async (res) => {
        if (res.ok) {
          window.location.replace("/atleta");
          return;
        }
        const body = await res.json().catch(() => ({}));
        setError(body.error ?? t("qrLogin.failed"));
      })
      .catch(() => setError(t("login.connectionError")));
  }, [code, t]);

  return (
    <AuthLayout title={t("qrLogin.title")} subtitle={error ? undefined : t("qrLogin.wait")}>
      {error ? (
        <div className="space-y-4">
          <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700 ring-1 ring-rose-200" role="alert">{error}</p>
          <a href="/login" className="inline-flex font-semibold text-brand-700 hover:underline">{t("qrLogin.useLogin")} →</a>
        </div>
      ) : (
        <div className="flex justify-center py-6"><span className="h-10 w-10 animate-spin rounded-full border-4 border-brand-200 border-t-brand-600" /></div>
      )}
    </AuthLayout>
  );
}
