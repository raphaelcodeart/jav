"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { friendlyApiError } from "@/lib/api-error";
import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n/provider";

// La casella "Messaggi": ciò che arriva dal sito pubblico (docs/club-portal.md,
// "Messaggi dal sito"). La segreteria vede i messaggi del suo club
// (/club/admin/messages: il club lo decide l'API, non questa pagina); la
// console di JudoArteVida quelli scritti a JAV, e il superadmin può guardare
// anche quelli di un club (/contact-messages?club=...). Si risponde con
// l'email di chi ha scritto: il programma di posta si apre già compilato.

interface ContactMessage {
  id: string;
  club: { id: string; name: string; slug: string } | null;
  name: string;
  email: string;
  phone: string | null;
  message: string;
  /** GENERAL, SPONSOR, ENROLMENT, EVENTS, OTHER: lo sceglie chi scrive. */
  topic: string;
  locale: string;
  status: "NEW" | "READ" | "ARCHIVED";
  created_at: string;
  emailed_at: string | null;
}

interface Inbox {
  items: ContactMessage[];
  counts: Record<"NEW" | "READ" | "ARCHIVED", number>;
}

type View = "inbox" | "archived";

const TOPICS = ["GENERAL", "SPONSOR", "ENROLMENT", "EVENTS", "NEW_CLUB", "OTHER"] as const;
const TOPIC_ICONS: Record<string, string> = { GENERAL: "💬", SPONSOR: "🤝", ENROLMENT: "🥋", EVENTS: "🏆", NEW_CLUB: "🏯", OTHER: "📎" };

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

export function ContactInbox({ mode, canFilterClubs = false }: { mode: "club" | "platform"; canFilterClubs?: boolean }) {
  const { t, fmt } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [view, setView] = useState<View>("inbox");
  // Il superadmin parte da «Tutti»: i messaggi a JudoArteVida e quelli dei club.
  const [club, setClub] = useState(canFilterClubs ? "all" : "jav");
  const [topic, setTopic] = useState<string>("");
  const [pending, setPending] = useState<string | null>(null);

  const base = mode === "club" ? "/api/proxy/club/admin/messages" : "/api/proxy/contact-messages";
  const params = new URLSearchParams();
  if (mode === "platform") params.set("club", club);
  if (view === "archived") params.set("status", "ARCHIVED");
  const qs = params.toString();
  const key = ["contact-messages", mode, club, view];
  const { data, isLoading, error } = useQuery({ queryKey: key, queryFn: () => getJson<Inbox>(`${base}${qs ? `?${qs}` : ""}`) });
  const clubs = useQuery({
    queryKey: ["clubs"],
    queryFn: () => getJson<{ id: string; name: string; kind?: string }[]>("/api/proxy/clubs"),
    enabled: mode === "platform" && canFilterClubs,
  });

  async function setStatus(m: ContactMessage, status: ContactMessage["status"]) {
    setPending(m.id);
    try {
      const res = await fetch(`${base}/${m.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["contact-messages"] });
    } catch (e) {
      toast({ tone: "error", title: t("inbox.failed"), text: (e as Error).message });
    } finally {
      setPending(null);
    }
  }

  const counts = data?.counts ?? { NEW: 0, READ: 0, ARCHIVED: 0 };
  const showClub = mode === "platform" && club !== "jav";
  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Tabs
          value={view} onChange={(k) => setView(k as View)}
          items={[
            { key: "inbox", label: t("inbox.tabInbox"), count: counts.NEW + counts.READ },
            { key: "archived", label: t("inbox.tabArchived"), count: counts.ARCHIVED },
          ]}
        />
        <div className="flex flex-col gap-2 sm:flex-row">
        <Select value={topic} onChange={(e) => setTopic(e.target.value)} className="sm:w-56" aria-label={t("inbox.topicFilter")}>
          <option value="">{t("inbox.topicAll")}</option>
          {TOPICS.map((k) => <option key={k} value={k}>{TOPIC_ICONS[k]} {t(`site.contactForm.topic.${k}`)}</option>)}
        </Select>
        {mode === "platform" && canFilterClubs && (
          <Select value={club} onChange={(e) => setClub(e.target.value)} className="sm:w-72" aria-label={t("inbox.filterLabel")}>
            <option value="jav">{t("inbox.filterJav")}</option>
            <option value="all">{t("inbox.filterAll")}</option>
            {(clubs.data ?? []).filter((c) => c.kind !== "JAV_COURSES").map((c) => <option key={c.id} value={c.id}>🏯 {c.name}</option>)}
          </Select>
        )}
        </div>
      </div>
      {counts.NEW > 0 && view === "inbox" && (
        <p className="text-sm font-semibold text-brand-700">{t("inbox.newCount", { n: counts.NEW })}</p>
      )}

      {isLoading ? (
        <Skeleton className="h-48" />
      ) : error ? (
        <EmptyState title={t("inbox.loadFailed")} text={(error as Error).message} />
      ) : !data || data.items.filter((m) => !topic || m.topic === topic).length === 0 ? (
        <EmptyState
          icon={<span className="text-3xl" aria-hidden="true">✉️</span>}
          title={view === "archived" ? t("inbox.emptyArchived") : t("inbox.empty")}
          text={mode === "club" ? t("inbox.emptyTextClub") : t("inbox.emptyTextJav")}
        />
      ) : (
        <ul className="space-y-3">
          {data.items.filter((m) => !topic || m.topic === topic).map((m) => {
            const subject = encodeURIComponent(t("inbox.replySubject", { club: m.club?.name ?? "JudoArteVida" }));
            const quoted = encodeURIComponent(`\n\n---\n${m.message}`);
            return (
              <li key={m.id} className={cn("glass-card rounded-2xl p-5", m.status === "NEW" && "ring-2 ring-brand-200")}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 font-semibold text-ink-900">
                      {m.name}
                      {m.status === "NEW" && <Badge tone="brand" dot>{t("inbox.new")}</Badge>}
                      {m.topic && m.topic !== "GENERAL" && (
                        <Badge tone={m.topic === "SPONSOR" || m.topic === "NEW_CLUB" ? "warning" : "neutral"}>{TOPIC_ICONS[m.topic]} {t.dyn(`site.contactForm.topic.${m.topic}`, m.topic)}</Badge>
                      )}
                      {showClub && <Badge tone="neutral">{m.club ? m.club.name : "JudoArteVida"}</Badge>}
                    </p>
                    <p className="mt-0.5 text-sm text-ink-500">
                      <a href={`mailto:${m.email}`} className="hover:text-brand-700">{m.email}</a>
                      {m.phone && <> · <a href={`tel:${m.phone.replace(/\s+/g, "")}`} className="hover:text-brand-700">{m.phone}</a></>}
                      {" · "}{t.dyn(`inbox.locale.${m.locale}`, m.locale.toUpperCase())}
                    </p>
                  </div>
                  <p className="shrink-0 text-xs text-ink-500">
                    {fmt.date(new Date(m.created_at), { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </p>
                </div>
                <p className="mt-3 whitespace-pre-line break-words text-sm leading-relaxed text-ink-800">{m.message}</p>
                {!m.emailed_at && <p className="mt-2 text-xs text-ink-400">{t("inbox.notEmailed")}</p>}
                <div className="mt-4 flex flex-wrap gap-2">
                  <a
                    href={`mailto:${m.email}?subject=${subject}&body=${quoted}`}
                    onClick={() => { if (m.status === "NEW") void setStatus(m, "READ"); }}
                    className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-gradient-to-b from-brand-500 to-brand-600 px-3.5 text-sm font-semibold text-white shadow-brand hover:from-brand-400"
                  >
                    ↩ {t("inbox.reply")}
                  </a>
                  {m.status === "NEW" && (
                    <Button size="sm" variant="secondary" loading={pending === m.id} onClick={() => setStatus(m, "READ")}>{t("inbox.markRead")}</Button>
                  )}
                  {m.status === "READ" && (
                    <Button size="sm" variant="ghost" loading={pending === m.id} onClick={() => setStatus(m, "NEW")}>{t("inbox.markUnread")}</Button>
                  )}
                  {m.status !== "ARCHIVED" ? (
                    <Button size="sm" variant="ghost" loading={pending === m.id} onClick={() => setStatus(m, "ARCHIVED")}>{t("inbox.archive")}</Button>
                  ) : (
                    <Button size="sm" variant="ghost" loading={pending === m.id} onClick={() => setStatus(m, "READ")}>{t("inbox.restore")}</Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
