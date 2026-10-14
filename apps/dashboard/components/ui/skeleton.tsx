import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("rounded-xl bg-gradient-to-r from-ink-100 via-ink-50 to-ink-100 animate-shimmer", className)} />;
}
