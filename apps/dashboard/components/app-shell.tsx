"use client";

import { Fragment, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AccountGate } from "@/components/account-gate";
import { AreaSwitcher, useDualRoleAreas } from "@/components/area-switcher";
import { useClubBranding, type ClubBranding } from "@/lib/club-branding";
import { ShopCartButton, ShopCartPanel } from "@/components/shop-cart";
import { CartCheckoutModal, CartCheckoutShop } from "@/components/cart-checkout-modal";
import { LanguageSwitcher } from "@/components/language-switcher";
import { Javbot } from "@/components/javbot/javbot";
import { useI18n } from "@/lib/i18n/provider";
import type { Translator } from "@/lib/i18n/translate";
import type { NotificationRead } from "@/lib/types";

export interface NavItem {
  key: string;
  label: string;
  description?: string;
  icon: ReactNode;
  /** Notification `type` values that should light up this nav item's unread
      dot -- e.g. Anagrafiche Promoter opts into PROMOTER_APPROVAL_REQUESTED.
      A nav item with no notificationTypes never shows a dot. */
  notificationTypes?: string[];
  /** Il titolo del gruppo nel menu laterale ("Club", "Shop", ...): una voce
      che cambia gruppo rispetto alla precedente apre un'intestazione. */
  group?: string;
  /** L'etichetta corta per la barra in basso del telefono, dove ci stanno
      una decina di lettere ("Presenças" invece di "Presenças de hoje"). */
  shortLabel?: string;
}

interface AppShellProps {
  roleLabel: string;
  email?: string;
  navItems: NavItem[];
  activeKey: string;
  onNavigate: (key: string, filter?: string) => void;
  children: ReactNode;
  headerTitle?: string;
  headerSubtitle?: ReactNode;
  headerActions?: ReactNode;
  /** Center headerActions as a group instead of pushing it to the right with
      justify-between -- for pages with no headerSubtitle, justify-between
      would leave it looking stuck to the right against empty space rather
      than deliberately centered. Default false preserves the existing
      title/subtitle-on-left, actions-on-right layout. */
  centerHeaderActions?: boolean;
  /** La pagina a tutta larghezza (tabelle larghe, come la tabella atleti). */
  wide?: boolean;
  /** Le aree di un club (segreteria, treinador, famiglia, atleta): colori e
   *  logo del club (lib/club-branding.ts). La console della piattaforma no. */
  clubBranding?: boolean;
  /** Session 76: il carrello nella barra in alto, visibile da ogni scheda.
      Sta qui e non dentro lo Shop perché un carrello che si vede solo
      mentre si compra è un carrello che il cliente perde appena apre "I
      miei Ordini". Solo per l'area cliente: un amministratore non compra. */
  showCart?: boolean;
}

// How many nav items fit comfortably in the mobile bottom tab bar before the
// rest fold into the "Altro" sheet -- the classic native-app pattern (4-5
// primary tabs max).
const MOBILE_TAB_COUNT = 4;


const NOTIFICATION_TYPE_ICONS: Record<string, ReactNode> = {
  CONTRACT_CREATED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
  ),
  TICKET_CREATED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
  ),
  PRODUCT_REQUEST_CREATED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0zM11 8v6m-3-3h6" />
  ),
  PRODUCT_REQUEST_CUSTOMER_REPLY: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0zM11 8v6m-3-3h6" />
  ),
  PRODUCT_REQUEST_REPLY: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0zM11 8v6m-3-3h6" />
  ),
  PROMOTER_APPROVAL_REQUESTED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
  ),
  PROMOTER_APPROVED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
  ),
  PROMOTER_REJECTED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  ),
  COMMISSION_EARNED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2" />
  ),
  CASHBACK_RECEIVED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2" />
  ),
  WALLET_TRANSFER_RECEIVED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
  ),
  ORDER_CREDIT_APPLIED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
  ),
  ORDER_PAID: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16.5 7.5h-9v9h9v-9zM3 6a3 3 0 013-3h12a3 3 0 013 3v12a3 3 0 01-3 3H6a3 3 0 01-3-3V6z" />
  ),
  ORDER_CREATED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16.5 7.5h-9v9h9v-9zM3 6a3 3 0 013-3h12a3 3 0 013 3v12a3 3 0 01-3 3H6a3 3 0 01-3-3V6z" />
  ),
  ORDER_SHIPPED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0" />
  ),
};

function timeAgo(iso: string, t: Translator): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return t("time.now");
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return t("time.minutesAgo", { n: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t(hours === 1 ? "time.hourAgo" : "time.hoursAgo", { n: hours });
  const days = Math.floor(hours / 24);
  return t(days === 1 ? "time.dayAgo" : "time.daysAgo", { n: days });
}

async function fetchNotifications(): Promise<NotificationRead[]> {
  const res = await fetch("/api/proxy/notifications/mine");
  if (!res.ok) return [];
  return res.json();
}

/** Bell icon + unread badge + dropdown -- polls every 25s so a new
    notification shows up without a manual refresh, without needing
    WebSockets for what is, for now, a low-volume internal tool. The bell
    rings (a short wiggle) whenever the unread count goes up. */
function NotificationBell({ onOpenNotification }: { onOpenNotification: (n: NotificationRead) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const { t } = useI18n();

  const { data: notifications } = useQuery({
    queryKey: ["notifications", "mine"],
    queryFn: fetchNotifications,
    refetchInterval: 25000,
  });

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const list = notifications ?? [];
  const unreadCount = list.filter((n) => !n.is_read).length;

  async function handleClick(notification: NotificationRead) {
    setOpen(false);
    if (!notification.is_read) {
      await fetch(`/api/proxy/notifications/${notification.id}/read`, { method: "PATCH" });
      queryClient.invalidateQueries({ queryKey: ["notifications", "mine"] });
    }
    onOpenNotification(notification);
  }

  async function handleMarkAllRead() {
    await fetch("/api/proxy/notifications/mark-all-read", { method: "POST" });
    queryClient.invalidateQueries({ queryKey: ["notifications", "mine"] });
  }

  return (
    <div className="relative" ref={ref}>
      <motion.button
        key={unreadCount}
        animate={unreadCount > 0 ? { rotate: [0, -14, 12, -8, 5, 0] } : undefined}
        transition={{ duration: 0.7 }}
        whileTap={{ scale: 0.9 }}
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-10 w-10 items-center justify-center rounded-2xl bg-white ring-1 ring-ink-200 shadow-soft text-ink-700 hover:text-brand-600 cursor-pointer"
        aria-label={unreadCount > 0 ? t("notifications.unreadAria", { n: unreadCount }) : t("notifications.title")}
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        <AnimatePresence>
          {unreadCount > 0 && (
            <motion.span
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0 }}
              className="absolute -top-1 -right-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-500 px-1 text-[10px] font-bold text-white ring-2 ring-white animate-pulse-ring"
            >
              {unreadCount > 9 ? "9+" : unreadCount}
            </motion.span>
          )}
        </AnimatePresence>
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 460, damping: 32 }}
            className="absolute right-0 top-12 z-50 w-[22rem] max-w-[calc(100vw-2rem)] max-h-[440px] overflow-y-auto rounded-2xl bg-white shadow-lift ring-1 ring-ink-200 origin-top-right"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-ink-100 sticky top-0 bg-white/95 backdrop-blur">
              <p className="font-display text-sm text-ink-900">{t("notifications.title")}</p>
              {unreadCount > 0 && (
                <button onClick={handleMarkAllRead} className="text-xs font-semibold text-brand-600 hover:text-brand-700 cursor-pointer">
                  {t("notifications.markAllRead")}
                </button>
              )}
            </div>
            {list.length === 0 ? (
              <div className="text-center py-10 px-6">
                <div className="mx-auto h-12 w-12 rounded-2xl bg-accent-100 text-accent-700 flex items-center justify-center text-xl mb-3">✓</div>
                <p className="text-sm text-ink-500">{t("notifications.empty")}</p>
              </div>
            ) : (
              <div className="divide-y divide-ink-100">
                {list.map((n, i) => (
                  <motion.button
                    key={n.id}
                    initial={{ opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: Math.min(i, 8) * 0.03 }}
                    onClick={() => handleClick(n)}
                    className={`w-full flex items-start gap-3 px-4 py-3 text-left cursor-pointer hover:bg-ink-50 ${!n.is_read ? "bg-brand-50/60" : ""}`}
                  >
                    <span className="h-8 w-8 rounded-xl bg-brand-500/10 text-brand-600 shrink-0 flex items-center justify-center">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        {NOTIFICATION_TYPE_ICONS[n.type] ?? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01" />}
                      </svg>
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span className="text-sm font-semibold text-ink-900 truncate">{n.title}</span>
                        {!n.is_read && <span className="w-2 h-2 rounded-full bg-brand-500 shrink-0" />}
                      </span>
                      {n.body && <span className="block text-xs text-ink-500 mt-0.5 line-clamp-2">{n.body}</span>}
                      <span className="block text-[11px] text-ink-400 mt-1">
                        {t.dyn(`notification.${n.type}`, n.type)} · {timeAgo(n.created_at, t)}
                      </span>
                    </span>
                  </motion.button>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** In alto a sinistra: il logo del club nelle sue aree (se l'ha caricato),
 *  altrimenti JAV. È anche il bottone per tornare all'inizio dell'area, come
 *  nelle app: lo stesso della prima voce del menu. Il logo sta intero in un
 *  cerchio bianco (object-contain), mai ritagliato. */
function LogoMark({ compact = false, branding, onHome, homeLabel }: {
  compact?: boolean; branding?: ClubBranding | null; onHome?: () => void; homeLabel?: string;
}) {
  const content = branding?.logo_url ? (
    <>
      <motion.span whileHover={{ rotate: -6, scale: 1.05 }}
        className={`flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-white p-1.5 shadow-soft ring-1 ring-ink-100 ${compact ? "h-12 w-12" : "h-14 w-14"}`}>
        {/* eslint-disable-next-line @next/next/no-img-element -- logo caricato dal club */}
        <img src={branding.logo_url} alt={branding.name} className="h-full w-full object-contain" />
      </motion.span>
      {!compact && (
        <span className="min-w-0 text-left leading-tight">
          <span className="block font-display text-base leading-tight text-ink-900 line-clamp-2">{branding.name}</span>
          <span className="block text-[10px] font-semibold uppercase tracking-wider text-ink-400 truncate">JAV · Judo Arte e Vida</span>
        </span>
      )}
    </>
  ) : (
    <>
      <motion.span whileHover={{ rotate: -6, scale: 1.05 }} className="shrink-0 rounded-2xl bg-white shadow-soft ring-1 ring-ink-100 p-1">
        <Image src="/logo.png" alt="Jav" width={compact ? 36 : 44} height={compact ? 33 : 40} priority className="h-auto w-auto" />
      </motion.span>
      {!compact && (
        <span className="min-w-0 text-left leading-tight">
          <span className="block font-display text-lg text-ink-900">JAV</span>
          <span className="block text-[11px] font-semibold tracking-wide text-ink-500 truncate">Judo Arte e Vida</span>
        </span>
      )}
    </>
  );
  if (!onHome) return <div className="flex items-center gap-3 min-w-0">{content}</div>;
  return (
    <button type="button" onClick={onHome} aria-label={homeLabel} title={homeLabel}
      className="flex items-center gap-3 min-w-0 cursor-pointer rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400">
      {content}
    </button>
  );
}

function initialsOf(email?: string) {
  return ((email || "?").split("@")[0] ?? "?")
    .split(/[._-]/)
    .map((p) => p[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

/** Avatar menu in the top-right corner (classic dashboard corner). */
function UserMenu({ email, roleLabel, onOpenSettings }: { email?: string; roleLabel: string; onOpenSettings?: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const { hasBothRoles, isCustomerArea, clubAreas } = useDualRoleAreas();
  const { t } = useI18n();

  async function handleLogout() {
    // A full page load, and whatever the call answered (Session 85): a soft
    // router.push could hang on a page left open across a deploy, leaving
    // "Esci" doing nothing.
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    window.location.assign("/login");
  }

  const itemClass = "w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-ink-700 hover:bg-ink-50 hover:text-ink-900 cursor-pointer";

  return (
    <div className="relative" ref={ref}>
      <motion.button
        whileHover={{ scale: 1.06 }}
        whileTap={{ scale: 0.92 }}
        onClick={() => setOpen((v) => !v)}
        className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 text-xs font-bold text-white shadow-brand ring-2 ring-white cursor-pointer font-display"
        aria-label={t("shell.userMenu")}
      >
        {initialsOf(email)}
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 460, damping: 32 }}
            className="absolute right-0 top-12 z-50 w-60 rounded-2xl bg-white shadow-lift ring-1 ring-ink-200 overflow-hidden origin-top-right"
          >
            <div className="px-4 py-3 border-b border-ink-100 bg-gradient-to-br from-brand-50 to-white">
              <p className="truncate text-sm font-semibold text-ink-900">{email}</p>
              <p className="truncate text-xs text-ink-500">{roleLabel}</p>
            </div>
            {clubAreas.map((area) => (
              <Link key={area.href} href={area.href} onClick={() => setOpen(false)} className={itemClass}>
                <span className="w-4 text-center" aria-hidden="true">{area.icon}</span>
                {t(area.labelKey)}
              </Link>
            ))}
            {hasBothRoles && (
              <Link href={isCustomerArea ? "/promoter" : "/customer"} onClick={() => setOpen(false)} className={itemClass}>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4M16 17H4m0 0l4 4m-4-4l4-4" />
                </svg>
                {isCustomerArea ? t("shell.switchToPromoter") : t("shell.switchToCustomer")}
              </Link>
            )}
            {/* Session 87: le Impostazioni del cliente (il PIN dei JavCash) si
                raggiungono anche da qui, dove le cerca chi è abituato alle app. */}
            {onOpenSettings && (
              <button onClick={() => { setOpen(false); onOpenSettings(); }} className={itemClass}>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                {t("shell.settings")}
              </button>
            )}
            <button onClick={handleLogout} className={`${itemClass} text-rose-600 hover:text-rose-700`}>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
              {t("shell.logout")}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function greeting(t: Translator): string {
  const h = new Date().getHours();
  if (h < 12) return t("shell.goodMorning");
  if (h < 18) return t("shell.goodAfternoon");
  return t("shell.goodEvening");
}

const COLLAPSE_KEY = "jav-sidebar-collapsed";
const COLLAPSE_EVENT = "jav-sidebar-collapsed-change";

// The collapsed rail is a per-browser preference read from localStorage --
// through useSyncExternalStore, so the server render (no localStorage) and
// the first client render agree, then the stored value takes over.
function subscribeCollapsed(onChange: () => void) {
  window.addEventListener(COLLAPSE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(COLLAPSE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}
const readCollapsed = () => localStorage.getItem(COLLAPSE_KEY) === "1";

export function AppShell({
  roleLabel,
  email,
  navItems,
  activeKey,
  onNavigate,
  children,
  headerTitle,
  headerSubtitle,
  headerActions,
  showCart = false,
  centerHeaderActions = false,
  wide = false,
  clubBranding = false,
}: AppShellProps) {
  const branding = useClubBranding(clubBranding);
  // I corsi esterni (area del genitore e della scuola) non hanno JAVBOT.
  const pathname = usePathname();
  const noJavbot = !!pathname && (pathname.startsWith("/cursos") || pathname.startsWith("/escola"));
  const [moreOpen, setMoreOpen] = useState(false);
  const { t } = useI18n();
  // Il carrello vive qui, non dentro lo Shop: si apre da qualunque scheda, e
  // il checkout deve restare raggiungibile anche dopo averlo aperto da "I
  // miei Ordini" o dalla Contabilità.
  const [cartOpen, setCartOpen] = useState(false);
  const [cartCheckoutShop, setCartCheckoutShop] = useState<CartCheckoutShop | null>(null);
  // Remembered per browser: whoever prefers the slim rail keeps it.
  const collapsed = useSyncExternalStore(subscribeCollapsed, readCollapsed, () => false);

  function toggleCollapsed() {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? "0" : "1");
    window.dispatchEvent(new Event(COLLAPSE_EVENT));
  }

  const { data: notifications } = useQuery({
    queryKey: ["notifications", "mine"],
    queryFn: fetchNotifications,
    refetchInterval: 25000,
  });
  const unreadTypes = new Set((notifications ?? []).filter((n) => !n.is_read).map((n) => n.type));

  function handleOpenNotification(notification: NotificationRead) {
    const targetKey = navItems.find((item) => item.notificationTypes?.includes(notification.type))?.key;
    if (targetKey) onNavigate(targetKey);
  }

  // Il logo porta all'inizio dell'area: la prima voce del menu è sempre la
  // home (Início dell'atleta, Panoramica della segreteria, Início del treinador).
  const homeKey = navItems[0]?.key;
  const goHome = homeKey ? () => onNavigate(homeKey) : undefined;
  const homeLabel = navItems[0] ? t("staffClubs.logoHome", { section: navItems[0].label }) : undefined;

  const name = (email ?? "").split("@")[0]?.split(/[._-]/)[0] ?? "";
  const displayName = name ? name.charAt(0).toUpperCase() + name.slice(1) : "";
  const sidebarWidth = collapsed ? "lg:w-[88px]" : "lg:w-72";
  const contentPad = collapsed ? "lg:pl-[88px]" : "lg:pl-72";

  return (
    <div className="min-h-screen">
      {/* Desktop sidebar: a floating white rail with an active pill that
          slides between items (shared layout animation). */}
      <aside className={`hidden lg:flex fixed inset-y-0 left-0 z-30 p-3 transition-[width] duration-300 ${sidebarWidth}`}>
        <div className="flex h-full w-full flex-col rounded-3xl bg-white/90 backdrop-blur-xl ring-1 ring-ink-200/70 shadow-soft overflow-hidden">
          <div className={`flex items-center ${collapsed ? "justify-center" : "justify-between"} px-4 pt-5 pb-4`}>
            <LogoMark compact={collapsed} branding={branding} onHome={goHome} homeLabel={homeLabel} />
          </div>

          <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 space-y-1">
            {navItems.map((item, index) => {
              const active = item.key === activeKey;
              const hasUnread = item.notificationTypes?.some((t) => unreadTypes.has(t)) ?? false;
              const opensGroup = !!item.group && item.group !== navItems[index - 1]?.group;
              return (
                <Fragment key={item.key}>
                {opensGroup && !collapsed && (
                  <p className="px-3 pt-4 pb-1 text-[10px] font-bold uppercase tracking-[0.18em] text-ink-400">{item.group}</p>
                )}
                {opensGroup && collapsed && index > 0 && <div className="mx-3 my-2 h-px bg-ink-100" />}
                <button
                  key={item.key}
                  onClick={() => onNavigate(item.key)}
                  title={collapsed ? item.label : undefined}
                  className={`relative w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-semibold cursor-pointer group ${
                    collapsed ? "justify-center" : ""
                  } ${active ? "text-white" : "text-ink-600 hover:text-ink-900 hover:bg-ink-50"}`}
                >
                  {active && (
                    <motion.span
                      layoutId="sidebar-active"
                      className="absolute inset-0 rounded-2xl bg-gradient-to-r from-brand-500 to-brand-600 shadow-brand"
                      transition={{ type: "spring", stiffness: 420, damping: 34 }}
                    />
                  )}
                  <span
                    className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-transform group-hover:scale-110 [&_svg]:h-5 [&_svg]:w-5 ${
                      active ? "bg-white/20" : "bg-ink-100/80 text-ink-600 group-hover:bg-brand-50 group-hover:text-brand-600"
                    }`}
                  >
                    {item.icon}
                    {hasUnread && <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-accent-400 ring-2 ring-white" />}
                  </span>
                  {!collapsed && <span className="relative flex-1 text-left truncate">{item.label}</span>}
                </button>
                </Fragment>
              );
            })}
          </nav>

          <div className="p-3">
            {!collapsed && (
              <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-ink-800 to-ink-950 p-4 text-white mb-2">
                <div className="absolute -right-4 -top-6 font-display text-6xl text-white/10 select-none" aria-hidden="true">柔</div>
                <p className="text-[11px] uppercase tracking-[0.18em] text-accent-300 font-bold">{t("shell.yourRole")}</p>
                <p className="font-display text-sm mt-1 truncate">{roleLabel}</p>
              </div>
            )}
            <button
              onClick={toggleCollapsed}
              className="w-full flex items-center justify-center gap-2 rounded-xl py-2 text-xs font-semibold text-ink-500 hover:bg-ink-50 hover:text-ink-900 cursor-pointer"
              aria-label={collapsed ? t("shell.expandMenu") : t("shell.collapseMenu")}
            >
              <motion.svg animate={{ rotate: collapsed ? 180 : 0 }} className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 6l-6 6 6 6" />
              </motion.svg>
              {!collapsed && t("shell.collapse")}
            </button>
          </div>
        </div>
      </aside>

      {/* Top bar: greeting on the left, icon cluster on the right. */}
      <header className={`sticky top-0 z-40 ${contentPad} transition-[padding] duration-300`}>
        <div className="flex items-center justify-between gap-3 px-4 sm:px-6 lg:px-8 h-[72px] bg-white/75 backdrop-blur-xl border-b border-ink-100/80">
          <div className="flex items-center gap-3 min-w-0">
            <div className="lg:hidden">
              <LogoMark compact branding={branding} onHome={goHome} homeLabel={homeLabel} />
            </div>
            <div className="min-w-0 hidden sm:block">
              {/* The greeting depends on the user's clock, which the server
                  doesn't have: the text may differ after hydration, on purpose. */}
              <p className="text-xs font-semibold text-ink-500" suppressHydrationWarning>
                {greeting(t)}
                {displayName ? `, ${displayName}` : ""} 👋
              </p>
              {headerTitle && <p className="font-display text-base text-ink-900 truncate">{headerTitle}</p>}
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3 shrink-0">
            {showCart && <ShopCartButton onOpen={() => setCartOpen(true)} />}
            <LanguageSwitcher />
            <AreaSwitcher />
            <NotificationBell onOpenNotification={handleOpenNotification} />
            <UserMenu
              email={email}
              roleLabel={roleLabel}
              onOpenSettings={navItems.some((item) => item.key === "settings") ? () => onNavigate("settings") : undefined}
            />
          </div>
        </div>
      </header>

      {/* Main content: each section enters with a short fade/rise. Motion
          leaves `transform: none` once it settles, so fixed-position modals
          inside never get re-anchored to <main> (see globals.css). */}
      <div className={`${contentPad} transition-[padding] duration-300`}>
        <main className={`mx-auto ${wide ? "max-w-none" : "max-w-7xl"} px-4 sm:px-6 lg:px-8 pt-6 sm:pt-8 pb-32 lg:pb-10`}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={activeKey}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            >
              {(headerTitle || headerSubtitle || headerActions) && (
                <div className={`mb-7 flex flex-col gap-4 ${centerHeaderActions ? "" : "md:flex-row md:items-end md:justify-between"}`}>
                  <div className="min-w-0">
                    {headerTitle && <h1 className="text-2xl sm:text-3xl text-ink-900">{headerTitle}</h1>}
                    {headerSubtitle && <div className="text-sm text-ink-500 mt-1.5">{headerSubtitle}</div>}
                  </div>
                  {headerActions && <div className={centerHeaderActions ? "w-full" : "flex flex-wrap gap-3"}>{headerActions}</div>}
                </div>
              )}
              <AccountGate>{children}</AccountGate>
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* Mobile bottom tab bar: a floating pill above the home indicator,
          big touch targets, a bubble that slides to the active tab. */}
      {navItems.length > 0 && <nav className="lg:hidden fixed bottom-0 inset-x-0 z-40 px-3 pb-[max(env(safe-area-inset-bottom),12px)] pointer-events-none">
        <div className="pointer-events-auto mx-auto max-w-md flex items-stretch rounded-[28px] bg-white/95 backdrop-blur-xl ring-1 ring-ink-200 shadow-lift p-1.5">
          {navItems.slice(0, MOBILE_TAB_COUNT).map((item) => {
            const active = item.key === activeKey;
            const hasUnread = item.notificationTypes?.some((t) => unreadTypes.has(t)) ?? false;
            return (
              <button
                key={item.key}
                onClick={() => onNavigate(item.key)}
                className={`relative flex-1 flex flex-col items-center justify-center gap-0.5 py-2 rounded-3xl cursor-pointer ${active ? "text-white" : "text-ink-500"}`}
              >
                {active && (
                  <motion.span
                    layoutId="tabbar-active"
                    className="absolute inset-0 rounded-3xl bg-gradient-to-b from-brand-500 to-brand-600 shadow-brand"
                    transition={{ type: "spring", stiffness: 480, damping: 34 }}
                  />
                )}
                <span className="relative flex h-7 w-7 items-center justify-center [&_svg]:h-6 [&_svg]:w-6">
                  {item.icon}
                  {hasUnread && <span className="absolute -top-0.5 -right-1 h-2.5 w-2.5 rounded-full bg-accent-400 ring-2 ring-white" />}
                </span>
                <span className="relative text-[10px] font-bold truncate max-w-[72px]">{item.shortLabel ?? item.label}</span>
              </button>
            );
          })}
          {navItems.length > MOBILE_TAB_COUNT && (
            <button onClick={() => setMoreOpen(true)} className="flex-1 flex flex-col items-center justify-center gap-0.5 py-2 rounded-3xl cursor-pointer text-ink-500">
              <span className="flex h-7 w-7 items-center justify-center">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </span>
              <span className="text-[10px] font-bold">{t("shell.more")}</span>
            </button>
          )}
        </div>
      </nav>}

      {/* Mobile "Altro": every section as a big tile in a bottom sheet. */}
      <AnimatePresence>
        {moreOpen && (
          <div className="lg:hidden fixed inset-0 z-50 flex items-end">
            <motion.div className="absolute inset-0 bg-ink-900/35 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMoreOpen(false)} />
            <motion.div
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 36 }}
              className="relative w-full rounded-t-[32px] bg-white p-5 pb-[max(env(safe-area-inset-bottom),20px)] shadow-lift max-h-[80vh] overflow-y-auto"
            >
              <div className="mx-auto mb-4 h-1.5 w-10 rounded-full bg-ink-200" aria-hidden="true" />
              <p className="font-display text-ink-900 mb-4">{t("shell.allSections")}</p>
              <div className="grid grid-cols-3 gap-3">
                {navItems.map((item, i) => {
                  const active = item.key === activeKey;
                  return (
                    <motion.button
                      key={item.key}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.025 }}
                      whileTap={{ scale: 0.94 }}
                      onClick={() => {
                        onNavigate(item.key);
                        setMoreOpen(false);
                      }}
                      className={`flex flex-col items-center gap-2 rounded-2xl p-3 text-center cursor-pointer ring-1 ${
                        active ? "bg-brand-500 text-white ring-brand-500 shadow-brand" : "bg-ink-50 text-ink-700 ring-ink-100"
                      }`}
                    >
                      <span className="flex h-10 w-10 items-center justify-center [&_svg]:h-6 [&_svg]:w-6">{item.icon}</span>
                      <span className="text-[11px] font-bold leading-tight">{item.label}</span>
                    </motion.button>
                  );
                })}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {showCart && (
        <ShopCartPanel
          open={cartOpen}
          onClose={() => setCartOpen(false)}
          onCheckout={(shop) => {
            // Il pannello si chiude: modificare il carrello mentre se ne sta
            // pagando il contenuto e' il modo piu' rapido per pagare una cosa
            // diversa da quella che si e' confermata.
            setCartOpen(false);
            // Solo i negozi che hanno una finestra di checkout: il carrello
            // del catalogo interno arrivera' con la sua.
            if (shop !== "catalog") setCartCheckoutShop(shop);
          }}
        />
      )}
      {cartCheckoutShop && <CartCheckoutModal shop={cartCheckoutShop} onClose={() => setCartCheckoutShop(null)} />}

      {/* JAVBOT, l'assistente: qui una volta sola, quindi in ogni pagina
          privata di ogni ruolo. Cambia scheda con lo stesso onNavigate del
          menu, e solo verso sezioni che quest'area ha davvero. */}
      {!noJavbot && <Javbot navKeys={navItems.map((item) => item.key)} onNavigate={(key) => onNavigate(key)} />}
    </div>
  );
}
