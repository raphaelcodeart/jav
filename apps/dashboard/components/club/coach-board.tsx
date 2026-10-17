"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Pagination, usePaged } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { EventPost, NewsCard, NewsModal, type FeedItem, type NewsPost } from "@/components/club/club-board";
import { clubGet, clubSend } from "@/lib/club";
import { useI18n } from "@/lib/i18n/provider";

// Il «Mural» dell'area del treinador (apps/api/app/domains/club/news.py, i
// post dei treinadores): la bacheca come la vedono i soci, e i suoi post da
// scrivere, correggere, nascondere o togliere. Solo per i soci del club,
// niente post fissati: la segreteria vede tutto e modera dalla sua console.

interface StaffBoard { feed: FeedItem[]; mine: NewsPost[] }

export function CoachBoard() {
  const { t } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState("feed");
  const [editing, setEditing] = useState<NewsPost | "new" | null>(null);
  const { data, isLoading } = useQuery({ queryKey: ["club", "staff", "board"], queryFn: () => clubGet<StaffBoard>("/staff/board") });
  const feed = usePaged(data?.feed ?? [], 10);
  const mine = usePaged(data?.mine ?? [], 10);
  const refresh = () => qc.invalidateQueries({ queryKey: ["club"] });

  async function patch(post: NewsPost, changes: Partial<NewsPost>, ok: string) {
    try {
      await clubSend(`/staff/news/${post.id}`, "PATCH", changes);
      await refresh();
      toast({ tone: "success", title: ok });
    } catch (e) {
      toast({ tone: "error", title: t("board.saveError"), text: (e as Error).message });
    }
  }
  async function remove(post: NewsPost) {
    if (!window.confirm(t("board.confirmDelete", { title: post.title }))) return;
    try {
      await clubSend(`/staff/news/${post.id}`, "DELETE");
      await refresh();
      toast({ tone: "success", title: t("board.deleted") });
    } catch (e) {
      toast({ tone: "error", title: t("board.saveError"), text: (e as Error).message });
    }
  }

  return (
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-700 via-brand-600 to-ink-950 p-6 text-white shadow-lift">
        <motion.div aria-hidden="true" className="pointer-events-none absolute -right-10 -top-16 h-56 w-56 rounded-full bg-accent-400/30 blur-3xl"
          animate={{ scale: [1, 1.15, 1] }} transition={{ duration: 9, repeat: Infinity, ease: "easeInOut" }} />
        <p className="text-xs font-bold uppercase tracking-[0.22em] text-white/80">📰 {t("board.eyebrow")}</p>
        <h2 className="mt-1 text-2xl">{t("coach2.board.title")}</h2>
        <p className="mt-2 max-w-xl text-sm text-white/80">{t("coach2.board.intro")}</p>
        <Button className="relative mt-4" variant="accent" onClick={() => setEditing("new")}>＋ {t("coach2.board.newPost")}</Button>
      </section>
      <Tabs value={tab} onChange={setTab} items={[
        { key: "feed", label: `🏯 ${t("coach2.board.tabFeed")}` },
        { key: "mine", label: `✍️ ${t("coach2.board.tabMine")}${data?.mine.length ? ` · ${data.mine.length}` : ""}` },
      ]} />
      {isLoading || !data ? <Skeleton className="h-64" /> : tab === "feed" ? (
        data.feed.length === 0 ? <EmptyState icon={<span className="text-3xl">📰</span>} title={t("board.noNews")} text={t("board.noNewsText")} /> : (
          <div className="mx-auto max-w-2xl space-y-4">
            {feed.items.map((i) => i.post
              ? <NewsCard key={`p-${i.post.id}`} post={i.post} />
              : i.event ? <EventPost key={`e-${i.event.id}`} event={i.event} /> : null)}
            <Pagination page={feed.page} pages={feed.pages} onChange={(p) => { feed.setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
          </div>
        )
      ) : data.mine.length === 0 ? (
        <EmptyState icon={<span className="text-3xl">✍️</span>} title={t("coach2.board.noMine")} text={t("coach2.board.noMineText")}
          action={<Button onClick={() => setEditing("new")}>{t("coach2.board.newPost")}</Button>} />
      ) : (
        <div className="mx-auto max-w-2xl space-y-4">
          {mine.items.map((p) => (
            <NewsCard key={p.id} post={p} actions={<>
              <Button size="sm" variant="secondary" onClick={() => setEditing(p)}>✎ {t("board.edit")}</Button>
              <Button size="sm" variant="ghost" onClick={() => patch(p, { published: !p.published }, p.published ? t("board.hidden") : t("board.publishedDone"))}>
                {p.published ? `🙈 ${t("board.hide")}` : `🚀 ${t("board.publish")}`}
              </Button>
              <Button size="sm" variant="ghost" className="ml-auto text-rose-600" onClick={() => remove(p)}>{t("board.delete")}</Button>
            </>} />
          ))}
          <Pagination page={mine.page} pages={mine.pages} onChange={mine.setPage} />
        </div>
      )}
      {editing && <NewsModal mode="staff" post={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
