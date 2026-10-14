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
  website: (
    <>
      <circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3.5 12h17M12 3.5c2.3 2.4 3.4 5.2 3.4 8.5s-1.1 6.1-3.4 8.5c-2.3-2.4-3.4-5.2-3.4-8.5S9.7 5.9 12 3.5Z" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </>
  ),
};

export interface SocialLink {
  kind: "facebook" | "instagram" | "youtube" | "website";
  url: string;
  label: string;
}

export function SocialIcons({ links, className, tone = "light" }: { links: SocialLink[]; className?: string; tone?: "light" | "plain" }) {
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
              tone === "light" ? "bg-white text-club-ink shadow-soft ring-1 ring-ink-900/5 hover:bg-club hover:text-club-on" : "bg-ink-100 text-ink-700 hover:bg-club hover:text-club-on",
            )}
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">{PATHS[s.kind]}</svg>
          </a>
        </li>
      ))}
    </ul>
  );
}
