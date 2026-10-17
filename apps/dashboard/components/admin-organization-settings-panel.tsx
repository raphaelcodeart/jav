"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";
import type { OrganizationSettingsRead } from "@/lib/types";

async function fetchSettings(): Promise<OrganizationSettingsRead> {
  const res = await fetch("/api/proxy/organizations/me/settings");
  if (!res.ok) throw new Error("Impossibile caricare le impostazioni aziendali.");
  return res.json();
}

/** Company-wide configuration: the bank account customers wire bonifico
    payments to (orders, contracts, Shop), and how contracts earn cashback. Was previously only settable by editing .env on the
    server; this is the dashboard-editable version. */
export function AdminOrganizationSettingsPanel() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { data: settings, error: loadError } = useQuery({
    queryKey: ["admin", "organization-settings"],
    queryFn: fetchSettings,
  });

  const [iban, setIban] = useState("");
  const [holder, setHolder] = useState("");
  const [instructions, setInstructions] = useState("");
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (settings) {
      setIban(settings.bank_iban ?? "");
      setHolder(settings.bank_account_holder ?? "");
      setInstructions(settings.bank_transfer_instructions ?? "");
    }
  }, [settings]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaveLoading(true);
    setSaveError(null);
    try {
      const res = await fetch("/api/proxy/organizations/me/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bank_iban: iban.trim() || null,
          bank_account_holder: holder.trim() || null,
          bank_transfer_instructions: instructions.trim() || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "organization-settings"] });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      setSaveError(err.message || t("adm.org.saveFailed"));
    } finally {
      setSaveLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
        <h3 className="text-sm font-semibold text-slate-900 mb-1">{t("adm.org.bankTitle")}</h3>
        <p className="text-xs text-slate-500 mb-4">
          {t("adm.org.bankText")}
        </p>
        {loadError && <p className="text-sm text-rose-400 mb-3">{t("adm.org.loadFailed")}</p>}
        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-600 uppercase block">IBAN</label>
              <input
                value={iban}
                onChange={(e) => setIban(e.target.value)}
                placeholder="IT00 A000 0000 0000 0000 0000 000"
                className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-brand-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-600 uppercase block">{t("adm.org.holder")}</label>
              <input
                value={holder}
                onChange={(e) => setHolder(e.target.value)}
                placeholder="Jav Srl"
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500"
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-600 uppercase block">
              {t("adm.org.instructions")}
            </label>
            <textarea
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder={t("adm.org.instructionsPlaceholder")}
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500 resize-none"
            />
            <p className="text-[10px] text-slate-500">{t("adm.org.instructionsHint")}</p>
          </div>
          <button
            type="submit"
            disabled={saveLoading}
            className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
          >
            {saveLoading ? t("adm.client.saving") : t("common.save")}
          </button>
          {saveError && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{saveError}</div>
          )}
          {saveSuccess && (
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">{t("adm.org.saved")}</div>
          )}
        </form>
      </div>

      {settings && <NetworkSocialsCard settings={settings} />}

      <ContractCashbackSettingsCard current={settings?.contract_instalment_cashback_mode ?? null} />
    </div>
  );
}

const SOCIAL_FIELDS = [
  { key: "social_facebook_url", label: "Facebook", placeholder: "https://facebook.com/..." },
  { key: "social_instagram_url", label: "Instagram", placeholder: "https://instagram.com/..." },
  { key: "social_youtube_url", label: "YouTube", placeholder: "https://youtube.com/@..." },
  { key: "social_tiktok_url", label: "TikTok", placeholder: "https://tiktok.com/@..." },
] as const;
type SocialKey = (typeof SOCIAL_FIELDS)[number]["key"];

/** I social di JudoArteVida: le icone nel piè di pagina di ogni pagina del
 *  sito. Ognuno solo verso il suo sito (l'API lo controlla). */
function NetworkSocialsCard({ settings }: { settings: OrganizationSettingsRead }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [values, setValues] = useState<Record<SocialKey, string>>(() =>
    Object.fromEntries(SOCIAL_FIELDS.map((f) => [f.key, settings[f.key] ?? ""])) as Record<SocialKey, string>);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch("/api/proxy/organizations/me/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.fromEntries(SOCIAL_FIELDS.map((f) => [f.key, values[f.key].trim() || null]))),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const saved: OrganizationSettingsRead = await res.json();
      setValues(Object.fromEntries(SOCIAL_FIELDS.map((f) => [f.key, saved[f.key] ?? ""])) as Record<SocialKey, string>);
      await queryClient.invalidateQueries({ queryKey: ["admin", "organization-settings"] });
      setMessage({ ok: true, text: t("orgSocials.saved") });
    } catch (err) {
      setMessage({ ok: false, text: (err as Error).message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
      <h3 className="text-sm font-semibold text-slate-900 mb-1">{t("orgSocials.title")}</h3>
      <p className="text-xs text-slate-500 mb-4">{t("orgSocials.text")}</p>
      <form onSubmit={save} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {SOCIAL_FIELDS.map((f) => (
            <div key={f.key} className="space-y-1">
              <label htmlFor={f.key} className="text-xs font-semibold text-slate-600 uppercase block">{f.label}</label>
              <input id={f.key} type="url" value={values[f.key]} placeholder={f.placeholder} maxLength={500}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-brand-500" />
            </div>
          ))}
        </div>
        <button type="submit" disabled={saving}
          className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
          {saving ? t("orgSocials.saving") : t("orgSocials.save")}
        </button>
        {message && (
          <p className={`p-3 rounded-lg text-xs ${message.ok ? "bg-emerald-500/10 text-emerald-700" : "bg-rose-500/10 text-rose-700"}`}>{message.text}</p>
        )}
      </form>
    </div>
  );
}

const CASHBACK_MODES: { key: "PER_INSTALMENT" | "UPFRONT" }[] = [
  { key: "PER_INSTALMENT" },
  { key: "UPFRONT" },
];

/** How a contract paid in 3 or 12 instalments earns its JavCash cashback
    (Session 59). The choice applies to each contract at the moment its first
    instalment is paid: changing it later never credits a contract twice. */
function ContractCashbackSettingsCard({ current }: { current: "PER_INSTALMENT" | "UPFRONT" | null }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const active = current ?? "PER_INSTALMENT";

  async function choose(mode: "PER_INSTALMENT" | "UPFRONT") {
    if (mode === active) return;
    setSaving(mode);
    setError(null);
    try {
      const res = await fetch("/api/proxy/organizations/me/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contract_instalment_cashback_mode: mode }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "organization-settings"] });
    } catch (err: any) {
      setError(err.message || t("adm.org.saveSettingFailed"));
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="glass-card rounded-2xl p-6 border-slate-200 bg-white/70">
      <h3 className="text-sm font-semibold text-slate-900 mb-1">{t("adm.org.cashbackTitle")}</h3>
      <p className="text-xs text-slate-500 mb-4">
        {t("adm.org.cashbackText")}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {CASHBACK_MODES.map((mode) => {
          const selected = mode.key === active;
          return (
            <button
              key={mode.key}
              type="button"
              onClick={() => choose(mode.key)}
              disabled={saving !== null}
              className={`text-left p-4 rounded-xl border transition cursor-pointer disabled:cursor-wait ${
                selected
                  ? "bg-brand-500/10 border-brand-500/50"
                  : " bg-slate-900/5 border-slate-300 hover:bg-slate-100"
              }`}
            >
              <span className="flex items-center gap-2">
                <span className={`w-4 h-4 rounded-full border-2 shrink-0 ${selected ? "border-brand-500 bg-brand-500" : "border-slate-500"}`} />
                <span className="text-sm font-semibold text-slate-900">
                  {t.dyn(`adm.org.cashback.${mode.key}.title`, mode.key)}
                  {mode.key === "PER_INSTALMENT" && <span className="ml-1.5 text-[10px] font-normal text-slate-500">{t("adm.org.default")}</span>}
                </span>
              </span>
              <span className="block text-xs text-slate-500 mt-1.5">{saving === mode.key ? t("adm.client.saving") : t.dyn(`adm.org.cashback.${mode.key}.body`, "")}</span>
            </button>
          );
        })}
      </div>
      {error && <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{error}</div>}
    </div>
  );
}
