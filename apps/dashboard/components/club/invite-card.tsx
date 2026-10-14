"use client";

import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { clubGet, type Invite, type Pricing } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";
import { shareOrCopyLink } from "@/lib/share-link";

/** Il link personale per invitare un amico nel club, e quanto ha reso: ogni
 *  mensilità pagata da una famiglia invitata dà credito nel wallet, da usare
 *  quando si pagano le quote (apps/api/app/domains/club/referrals.py). Sotto,
 *  che cosa comprende l'iscrizione annuale: le famiglie lo chiedono. */
export function InviteCard() {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const { data: invite } = useQuery({ queryKey: ["club", "invite"], queryFn: () => clubGet<Invite>("/invite") });
  const { data: pricing } = useQuery({ queryKey: ["club", "pricing"], queryFn: () => clubGet<Pricing>("/pricing") });
  if (!invite) return null;
  const url = `${typeof window === "undefined" ? "" : window.location.origin}${invite.path}`;

  async function share() {
    const result = await shareOrCopyLink({ url, title: t("invite.shareTitle"), text: t("invite.shareText") });
    if (result === "copied") toast({ tone: "success", title: t("invite.copied") });
    if (result === "failed") toast({ tone: "error", title: t("invite.copyFailed") });
  }

  return (
    <section className="glass-card rounded-3xl p-5 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base text-ink-900">🤝 {t("invite.title")}</h3>
          <p className="text-sm text-ink-500 mt-1">
            {t("invite.text", { amount: fmt.euro(invite.credit_per_month_cents) })}
          </p>
        </div>
        <Button size="sm" onClick={share}>{t("invite.share")}</Button>
      </div>
      <code className="block rounded-xl bg-ink-50 px-3 py-2 text-xs text-ink-700 break-all">{url}</code>
      <p className="text-xs text-ink-500">
        {t("invite.stats", { n: invite.invited_count, amount: fmt.euro(invite.earned_cents) })}
      </p>
      {pricing?.enrollment_includes && (
        <p className="text-xs text-ink-500 border-t border-ink-100 pt-3">
          <span className="font-semibold text-ink-700">{t("invite.enrollmentIncludes")}</span> {pricing.enrollment_includes}
        </p>
      )}
    </section>
  );
}
