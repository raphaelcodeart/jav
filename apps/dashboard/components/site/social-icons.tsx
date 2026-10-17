import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

// Le icone dei social della pagina di un club. Gli indirizzi arrivano già
// controllati dall'API (site.check_social_url: Facebook porta solo a
// facebook.com, e così via): qui si disegnano e basta.

const PATHS: Record<string, ReactNode> = {
  facebook: <path d="M13.5 21v-7.5h2.6l.4-3h-3V8.6c0-.9.3-1.5 1.6-1.5h1.6V4.4c-.3 0-1.2-.1-2.3-.1-2.3 0-3.9 1.4-3.9 4v2.2H8v3h2.5V21h3Z" />,
  instagram: (
    <>
      <rect x="3.5" y="3.5" width="17" height="17" rx="5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="17.3" cy="6.7" r="1.1" />
    </>
  ),
  youtube: <path d="M21.6 7.2a2.5 2.5 0 0 0-1.8-1.8C18.2 5 12 5 12 5s-6.2 0-7.8.4A2.5 2.5 0 0 0 2.4 7.2 26 26 0 0 0 2 12a26 26 0 0 0 .4 4.8 2.5 2.5 0 0 0 1.8 1.8C5.8 19 12 19 12 19s6.2 0 7.8-.4a2.5 2.5 0 0 0 1.8-1.8A26 26 0 0 0 22 12a26 26 0 0 0-.4-4.8ZM10 15V9l5.2 3L10 15Z" />,
  tiktok: <path d="M16.6 3c.3 2.2 1.6 3.7 3.9 3.9v2.6c-1.4.1-2.6-.3-3.9-1.1v5.3c0 3.6-2.6 6.1-6 6.1a5.8 5.8 0 0 1-5.9-5.9c0-3.5 2.9-6.2 6.6-5.8v2.8c-1.9-.4-3.7.8-3.7 2.9 0 1.7 1.3 3 3 3 1.9 0 3.1-1.2 3.1-3.4V3h2.9Z" />,
  whatsapp: <path d="M12 2.5a9.4 9.4 0 0 0-8.1 14.2L2.6 21.5l4.9-1.3A9.4 9.4 0 1 0 12 2.5Zm0 17.1c-1.4 0-2.8-.4-4-1.1l-.3-.2-2.9.8.8-2.8-.2-.3A7.7 7.7 0 1 1 12 19.6Zm4.3-5.8c-.2-.1-1.4-.7-1.6-.8-.2-.1-.4-.1-.5.1l-.7.9c-.1.2-.3.2-.5.1a6.3 6.3 0 0 1-3.1-2.7c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4l-.7-1.7c-.2-.4-.4-.4-.5-.4h-.5c-.2 0-.4.1-.6.3-.2.2-.8.8-.8 2s.8 2.3.9 2.5c.1.2 1.6 2.5 4 3.5 1.5.6 2 .7 2.8.6.4-.1 1.4-.6 1.6-1.1.2-.5.2-1 .1-1.1l-.6-.5Z" />,
  website: (
    <>
      <circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3.5 12h17M12 3.5c2.3 2.4 3.4 5.2 3.4 8.5s-1.1 6.1-3.4 8.5c-2.3-2.4-3.4-5.2-3.4-8.5S9.7 5.9 12 3.5Z" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </>
  ),
};

// Nel piè di pagina scuro ogni icona si accende del colore del suo social.
const DARK_HOVER: Record<string, string> = {
  facebook: "hover:bg-[#1877F2] hover:ring-[#1877F2]",
  instagram: "hover:bg-gradient-to-br hover:from-[#feda75] hover:via-[#d62976] hover:to-[#4f5bd5] hover:ring-[#d62976]",
  youtube: "hover:bg-[#FF0000] hover:ring-[#FF0000]",
  tiktok: "hover:bg-black hover:ring-[#25F4EE]",
  whatsapp: "hover:bg-[#25D366] hover:ring-[#25D366]",
  website: "hover:bg-brand-600 hover:ring-brand-600",
};

export interface SocialLink {
  kind: "facebook" | "instagram" | "youtube" | "tiktok" | "whatsapp" | "website";
  url: string;
  label: string;
}

/** Il disegno di un social, da solo (il bottone WhatsApp, il piè di pagina). */
export function SocialGlyph({ kind, className }: { kind: SocialLink["kind"]; className?: string }) {
  return <svg viewBox="0 0 24 24" className={className ?? "h-5 w-5"} fill="currentColor" aria-hidden="true">{PATHS[kind]}</svg>;
}

/** wa.me vuole solo cifre col prefisso del paese: un numero portoghese di 9
 *  cifre scritto senza +351 lo riceve. */
export function whatsappUrl(phone: string): string | null {
  let digits = phone.replace(/[^\d+]/g, "");
  if (digits.startsWith("+")) digits = digits.slice(1);
  else if (digits.startsWith("00")) digits = digits.slice(2);
  else if (digits.length === 9) digits = `351${digits}`;
  digits = digits.replace(/\D/g, "");
  return digits.length >= 8 ? `https://wa.me/${digits}` : null;
}

/** Il bottone verde «Scrivici su WhatsApp», sotto un numero di telefono. */
export function WhatsAppButton({ phone, label, className }: { phone: string; label: string; className?: string }) {
  const url = whatsappUrl(phone);
  if (!url) return null;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer"
      className={cn("inline-flex h-10 items-center gap-2 rounded-xl bg-[#25D366] px-4 text-sm font-semibold text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-[#1ebe5a] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#25D366]/30", className)}>
      <SocialGlyph kind="whatsapp" className="h-5 w-5" />
      {label}
    </a>
  );
}

export function SocialIcons({ links, className, tone = "light" }: { links: SocialLink[]; className?: string; tone?: "light" | "plain" | "dark" }) {
  if (links.length === 0) return null;
  return (
    <ul className={cn("flex flex-wrap gap-2", className)}>
      {links.map((s) => (
        <li key={s.kind}>
          <a
            href={s.url} target="_blank" rel="noopener noreferrer" aria-label={s.label} title={s.label}
            className={cn(
              "inline-flex h-11 w-11 items-center justify-center rounded-full transition hover:-translate-y-0.5",
              "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-club/30",
              tone === "light" ? "bg-white text-club-ink shadow-soft ring-1 ring-ink-900/5 hover:bg-club hover:text-club-on"
                : tone === "dark" ? cn("bg-white/10 text-white ring-1 ring-white/15", DARK_HOVER[s.kind])
                : "bg-ink-100 text-ink-700 hover:bg-club hover:text-club-on",
            )}
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">{PATHS[s.kind]}</svg>
          </a>
        </li>
      ))}
    </ul>
  );
}
